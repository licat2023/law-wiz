"""法条切分。

⚠️ **法律文本必须按条切分，不得按固定字符数硬切**（04-数据库设计 §4.3）。
按字符数硬切会把一条法条截成两半，**检索到半句话会直接导致错误的法律依据** ——
这是本项目最不能接受的失败形态之一。

切分规则**由后端决定，不由调用方传入**（05-接口设计 §5.5）：若允许调用方指定，
就可能出现按字符硬切的情况。

`char_start` / `char_end` 保留在**原文**中的偏移，使检索结果能精确定位回原文、
支撑"回答溯源"，也供前端做高亮。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 条号：第一条 / 第五百八十五条 / 第 12 条 / 第一百零一条
_ARTICLE_RE = re.compile(r"第\s*[一二三四五六七八九十百千零〇0-9]+\s*条")

# 单个分块的字数上限。仅用于**保护性兜底**：万一某"条"异常长（例如整篇都没换行），
# 不切会超出嵌入模型与提示词的长度预算。正常情况下不会触发。
_MAX_CHUNK_CHARS = 4000


@dataclass
class Chunk:
    chunk_no: int
    chunk_type: str
    article_no: str | None
    char_start: int
    char_end: int
    content: str


def _normalized_article(match: re.Match[str]) -> str:
    """去掉条号内部的空格：`第 12 条` → `第12条`。"""
    return match.group(0).replace(" ", "")


def split_into_chunks(text: str) -> list[Chunk]:
    """把语料切成块。优先按"条"，找不到条号时退化为按段落。"""
    if not text or not text.strip():
        return []

    matches = list(_ARTICLE_RE.finditer(text))
    if matches:
        return _split_by_article(text, matches)
    return _split_by_paragraph(text)


def _split_by_article(text: str, matches: list[re.Match[str]]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)

        raw = text[start:end]
        leading = len(raw) - len(raw.lstrip())
        body = raw.strip()
        if not body:
            continue

        chunks.extend(
            _maybe_split_long(
                body,
                char_start=start + leading,
                chunk_type="article",
                article_no=_normalized_article(match),
                first_chunk_no=len(chunks) + 1,
            )
        )
    return chunks


def _split_by_paragraph(text: str) -> list[Chunk]:
    """退路：整篇没有条号时（例如某些案例、模板），按空行分段。

    仍然**不是**按字符数硬切 —— 段落是作者本来的语义单位。
    """
    chunks: list[Chunk] = []
    offset = 0
    paragraph_start: int | None = None
    paragraph_end = 0

    for line in text.split("\n"):
        line_length = len(line)
        if line.strip():
            if paragraph_start is None:
                paragraph_start = offset
            paragraph_end = offset + line_length
        elif paragraph_start is not None:
            chunks.append(_make(len(chunks) + 1, "paragraph", None, paragraph_start, paragraph_end, text))
            paragraph_start = None
        offset += line_length + 1  # +1 是行尾的换行符

    if paragraph_start is not None:
        chunks.append(_make(len(chunks) + 1, "paragraph", None, paragraph_start, paragraph_end, text))
    return chunks


def _make(
    chunk_no: int,
    chunk_type: str,
    article_no: str | None,
    start: int,
    end: int,
    text: str,
) -> Chunk:
    return Chunk(
        chunk_no=chunk_no,
        chunk_type=chunk_type,
        article_no=article_no,
        char_start=start,
        char_end=end,
        content=text[start:end].strip(),
    )


def _maybe_split_long(
    body: str,
    *,
    char_start: int,
    chunk_type: str,
    article_no: str | None,
    first_chunk_no: int,
) -> list[Chunk]:
    """仅对超长的块做保护性再切分，切点仍尽量落在句号处。"""
    if len(body) <= _MAX_CHUNK_CHARS:
        return [
            Chunk(
                chunk_no=first_chunk_no,
                chunk_type=chunk_type,
                article_no=article_no,
                char_start=char_start,
                char_end=char_start + len(body),
                content=body,
            )
        ]

    pieces: list[Chunk] = []
    cursor = 0
    number = first_chunk_no
    while cursor < len(body):
        window = body[cursor : cursor + _MAX_CHUNK_CHARS]
        cut = window.rfind("。")
        cut = len(window) if cut <= 0 else cut + 1
        piece = body[cursor : cursor + cut]
        pieces.append(
            Chunk(
                chunk_no=number,
                chunk_type=chunk_type,
                article_no=article_no,
                char_start=char_start + cursor,
                char_end=char_start + cursor + len(piece),
                content=piece,
            )
        )
        cursor += cut
        number += 1
    return pieces
