"""固定/语义叶子切分与文档层级；法条父块保持完整。"""

import math
import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.documents.parsing import TextBlock, markdown_blocks
from app.errors import invalid


class ChunkOptions(BaseModel):
    chunking_strategy: Literal["fixed", "semantic"] = "fixed"
    chunk_size: int = Field(default=800, ge=1, le=8000)
    chunk_overlap: int = Field(default=100, ge=0, le=4000)
    hierarchical_index: bool = False
    semantic_threshold: float = Field(default=0.45, ge=0, le=2)

    @model_validator(mode="after")
    def valid_overlap(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("重叠必须小于分块长度")
        return self


@dataclass
class SplitChunk:
    key: str
    parent_key: str | None
    level: int
    chunk_no: int
    content: str
    char_start: int
    char_end: int
    title_path: str = ""
    page_number: int | None = None
    article_no: str | None = None
    is_leaf: bool = True


def semantic_units(text: str, size: int, *, max_units: int = 10000) -> list[tuple[int, int]]:
    bounds = []
    for match in re.finditer(r"[^。！？!?\n]+[。！？!?\n]*|[。！？!?\n]+", text):
        for start in range(match.start(), match.end(), size):
            if len(bounds) >= max_units:
                raise invalid("语义候选块超过数量上限，请增大分块长度")
            bounds.append((start, min(start + size, match.end())))
    return bounds


def _distance(a, b):
    norm = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return 1 - sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 1.0


def split_document(
    text: str,
    options: ChunkOptions,
    blocks: list[TextBlock] | None = None,
    *,
    semantic_vectors: list[list[float]] | None = None,
    legal: bool = False,
    article_no: str | None = None,
    max_chunks: int = 10000,
) -> list[SplitChunk]:
    if not text.strip():
        return []
    blocks = blocks or markdown_blocks(text)
    articles = (
        list(
            re.finditer(
                r"(?m)^[ \t　]*(?:#{1,6}[ \t]+)?(第[ \t]*[一二三四五六七八九十百千零〇0-9]+[ \t]*条(?:之[一二三四五六七八九十百千零〇0-9]+)?)",
                text,
            )
        )
        if legal
        else []
    )
    declared_article = article_no.strip() if legal and isinstance(article_no, str) else ""
    has_articles = bool(articles or declared_article)
    if articles:
        sections = [
            TextBlock(
                m.start(),
                articles[i + 1].start() if i + 1 < len(articles) else len(text),
                re.sub(r"\s", "", m[1]),
            )
            for i, m in enumerate(articles)
        ]
    elif declared_article:
        sections = [TextBlock(0, len(text), declared_article)]
    elif options.hierarchical_index:
        sections = blocks
    else:
        sections = [TextBlock(0, len(text))]
    hierarchy = options.hierarchical_index or has_articles
    result = []
    if hierarchy:
        result.append(SplitChunk("root", None, 0, 0, text, 0, len(text), is_leaf=False))
    units = []
    vector_map = {}
    if options.chunking_strategy == "semantic":
        units = semantic_units(text, options.chunk_size, max_units=max_chunks)
        if semantic_vectors is None or len(semantic_vectors) != len(units):
            raise ValueError("语义分块需要每个候选句子的真实嵌入")
        vector_map = dict(zip(units, semantic_vectors, strict=True))
    starts = [a for a, _ in units]
    ends = [b for _, b in units]
    block_starts = [b.start for b in blocks]
    for section_no, section in enumerate(sections):
        if len(result) >= max_chunks:
            raise invalid("分块超过数量上限，请调整分块设置")
        start, end = section.start, section.end
        if not text[start:end].strip():
            continue
        parent = f"section-{section_no}" if hierarchy else None
        article = section.title_path if has_articles else None
        if article and len(article) > 64:
            raise invalid("法条编号超过 64 字符")
        if hierarchy:
            result.append(
                SplitChunk(
                    parent,
                    "root",
                    1,
                    len(result),
                    text[start:end],
                    start,
                    end,
                    section.title_path,
                    section.page_number,
                    article,
                    False,
                )
            )
        ranges = []
        if options.chunking_strategy == "fixed":
            cursor = start
            while cursor < end:
                stop = min(cursor + options.chunk_size, end)
                if len(ranges) + len(result) >= max_chunks:
                    raise invalid("分块超过数量上限，请增大分块长度或减小重叠")
                ranges.append((cursor, stop))
                if stop == end:
                    break
                cursor = stop - options.chunk_overlap
        else:
            candidates = [
                (max(a, start), min(b, end), vector_map[(a, b)])
                for a, b in units[bisect_right(ends, start) : bisect_left(starts, end)]
            ]
            cursor = start
            previous = None
            for a, b, vector in candidates:
                boundary = previous is not None and _distance(previous, vector) > options.semantic_threshold
                if a > cursor and (boundary or b - cursor > options.chunk_size):
                    ranges.append((cursor, a))
                    cursor = a
                previous = vector
            if cursor < end:
                ranges.append((cursor, end))
        for a, b in ranges:
            if not text[a:b].strip():
                continue
            if len(result) >= max_chunks:
                raise invalid("分块超过数量上限，请调整分块设置")
            at = bisect_right(block_starts, a) - 1
            locator = blocks[at] if at >= 0 and a < blocks[at].end else section
            result.append(
                SplitChunk(
                    f"leaf-{len(result)}",
                    parent,
                    2 if hierarchy else 0,
                    len(result),
                    text[a:b],
                    a,
                    b,
                    section.title_path or locator.title_path,
                    locator.page_number,
                    article,
                )
            )
    return result
