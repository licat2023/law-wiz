"""向量检索的唯一封装。

约定与 `llm.py` 相同：单点封装、AI 队友只改内部、模块属性调用。

`vector_backend=memory` 是**真实可用**的进程内实现（重启即失）——
因此索引 / 检索流程不需要等真实后端就能开发与测试，检索质量无意义；
持久化后端（chroma）由 AI 队友接入。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings
from app.core.errors import BusinessError, ErrorCode
from app.infra import embedding

_settings = get_settings()


@dataclass
class VectorHit:
    doc_id: int
    chunk_id: str
    text: str
    score: float


# (doc_id, chunk_id, text, vector)
_MEMORY: list[tuple[int, str, str, list[float]]] = []


def index_document(doc_id: int, chunks: list[dict]) -> None:
    """把一个文档的全部块写入索引。

    `chunks` 每项形如 `{"chunk_id": str, "text": str}`。
    """
    _ensure_backend()
    for chunk in chunks:
        _MEMORY.append((doc_id, chunk["chunk_id"], chunk["text"], embedding.embed(chunk["text"])))


def search(query: str, top_k: int = 5) -> list[VectorHit]:
    """按余弦相似度返回最相近的 top_k 个块。空索引返回空列表。"""
    _ensure_backend()
    query_vec = embedding.embed(query)
    scored = [
        VectorHit(doc_id=doc_id, chunk_id=chunk_id, text=text, score=_cosine(query_vec, vec))
        for doc_id, chunk_id, text, vec in _MEMORY
    ]
    scored.sort(key=lambda hit: hit.score, reverse=True)
    return scored[:top_k]


def clear() -> None:
    """清空内存索引。仅测试使用。"""
    _MEMORY.clear()


def _ensure_backend() -> None:
    if _settings.vector_backend != "memory":
        raise BusinessError(ErrorCode.VECTOR_UNAVAILABLE, f"向量后端 {_settings.vector_backend!r} 尚未实现")


def _cosine(a: list[float], b: list[float]) -> float:
    # 向量已归一化，点积即余弦相似度。
    # strict=True：两边维度不同说明嵌入实现出了问题，应立刻暴露而不是静默截断。
    return sum(x * y for x, y in zip(a, b, strict=True))
