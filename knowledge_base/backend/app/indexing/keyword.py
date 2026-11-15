"""构建按索引版本管理的关键词倒排，并在数据库内计算 BM25。"""

import asyncio
import math
import re
import unicodedata
from collections import Counter
from hashlib import blake2s

from sqlalchemy import case, delete, func, insert, select

from app.indexing.models import KeywordLeaf, KeywordPosting

_WORDS = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+|[^\W_\u3400-\u4dbf\u4e00-\u9fff]+")
_DIGITS = "零一二三四五六七八九"
_ARTICLE = re.compile(
    r"第\s*([零〇一二两三四五六七八九十百千万0-9]+)\s*条(?:\s*之\s*([零〇一二两三四五六七八九十百千万0-9]+))?"
)
_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}
_K1, _B = 1.2, 0.75


def _number(text):
    text = text.replace("〇", "零").replace("两", "二")
    if not any(unit in text for unit in _UNITS):
        return "".join(str(_DIGITS.index(c)) if c in _DIGITS else c for c in text).lstrip("0") or "0"
    if any(c.isdecimal() for c in text):
        return text
    total = section = digit = 0
    for char in text:
        unit = _UNITS.get(char)
        if unit == 10000:
            total += (section + digit) * unit
            section = digit = 0
        elif unit:
            section += (digit or 1) * unit
            digit = 0
        else:
            digit = _DIGITS.index(char)
    return str(total + section + digit)


def _article(match):
    suffix = f":{_number(match[2])}" if match[2] else ""
    return f"article:{_number(match[1])}{suffix}"


def _terms(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    articles = [_article(match) for match in _ARTICLE.finditer(text)]
    words = []
    for match in _WORDS.finditer(_ARTICLE.sub(" ", text)):
        word = match[0]
        if len(word) > 1 and "\u3400" <= word[0] <= "\u9fff":
            words.extend(word[i : i + 2] for i in range(len(word) - 1))
        else:
            words.append(word)
    return articles, words


def _digest(term):
    return blake2s(term.encode(), digest_size=16).hexdigest()


def _prepare(index_id, leaves, identifiers, title):
    lengths, postings = [], []
    for chunk in leaves:
        chunk_id = identifiers[chunk.key]
        articles, words = _terms(f"{title}\n{chunk.content}")
        if chunk.article_no:
            articles.extend(_terms(chunk.article_no)[0])
        counts = Counter(articles + words)
        lengths.append({"chunk_id": chunk_id, "index_id": index_id, "length": sum(counts.values())})
        postings.extend(
            {"chunk_id": chunk_id, "term": _digest(term), "frequency": count}
            for term, count in counts.items()
        )
    return lengths, postings


async def write_keyword_index(db, index_id, leaves, identifiers, title):
    """写入当前事务。提交由索引处理器与向量发布指针一起完成。"""
    for offset in range(0, len(leaves), 16):
        lengths, postings = await asyncio.to_thread(
            _prepare, index_id, leaves[offset : offset + 16], identifiers, title
        )
        await db.execute(insert(KeywordLeaf), lengths)
        if postings:
            await db.execute(insert(KeywordPosting), postings)


async def delete_keyword_indexes(db, index_ids):
    """删除倒排记录并保留供历史引用查看的正文块。支持索引 ID 子查询。"""
    leaves = select(KeywordLeaf.chunk_id).where(KeywordLeaf.index_id.in_(index_ids))
    await db.execute(delete(KeywordPosting).where(KeywordPosting.chunk_id.in_(leaves)))
    await db.execute(delete(KeywordLeaf).where(KeywordLeaf.index_id.in_(index_ids)))


def _query_terms(query):
    articles, words = _terms(query)
    # 优先保留完整法条编号，限制长用户问题的 SQL 参数和排序开销。
    terms = list(dict.fromkeys(articles + words))[:128]
    return [_digest(term) for term in terms], {_digest(term) for term in set(articles).intersection(terms)}


async def keyword_search(db, active_indexes, query, limit):
    """在已通过权限与时效过滤的版本中返回 BM25 排名和关键词覆盖的版本数。"""
    scoped = KeywordLeaf.index_id.in_(active_indexes)
    count, avg_length, versions = (
        await db.execute(
            select(
                func.count(), func.avg(KeywordLeaf.length), func.count(KeywordLeaf.index_id.distinct())
            ).where(scoped)
        )
    ).one()
    terms, articles = await asyncio.to_thread(_query_terms, query)
    if not count or not avg_length or not terms:
        return [], versions
    match = KeywordPosting.term.in_(terms)
    counts = (
        await db.execute(
            select(KeywordPosting.term, func.count())
            .join(KeywordLeaf, KeywordPosting.chunk_id == KeywordLeaf.chunk_id)
            .where(scoped, match)
            .group_by(KeywordPosting.term)
        )
    ).all()
    if not counts:
        return [], versions
    weights = {term: math.log1p((count - df + 0.5) / (df + 0.5)) for term, df in counts}
    weight = case(weights, value=KeywordPosting.term, else_=0.0)
    frequency = KeywordPosting.frequency
    norm = _K1 * (1 - _B + _B * KeywordLeaf.length / float(avg_length))
    score = func.sum(weight * frequency * (_K1 + 1) / (frequency + norm))
    rank = (
        select(KeywordPosting.chunk_id, score)
        .join(KeywordLeaf, KeywordPosting.chunk_id == KeywordLeaf.chunk_id)
        .where(scoped, match)
        .group_by(KeywordPosting.chunk_id)
        .order_by(score.desc(), KeywordPosting.chunk_id)
        .limit(limit)
    )
    if articles:
        # 明确给出的条号是关键词候选的约束，语义路仍可召回相关联的其他条文。
        rank = rank.having(func.sum(case((KeywordPosting.term.in_(articles), 1), else_=0)) > 0)
    return (await db.execute(rank)).all(), versions
