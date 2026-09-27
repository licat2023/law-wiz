"""向量检索的唯一封装。

约定与 `llm.py` 相同：单点封装、AI 队友只改内部、模块属性调用。

`vector_backend=memory` 是**真实可用**的进程内实现（重启即失）——
因此索引 / 检索流程不需要等真实后端就能开发与测试，检索质量无意义；
`vector_backend=chroma` 使用本地 PersistentClient，索引在进程重启后仍可使用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
_CHROMA_CLIENT: Any | None = None
_CHROMA_CLIENT_PATH: str | None = None
_CHROMA_COLLECTION: Any | None = None
_CHROMA_COLLECTION_KEY: tuple[str, str] | None = None


def index_document(doc_id: int, chunks: list[dict]) -> None:
    """把一个文档的全部块写入索引。

    `chunks` 每项形如 `{"chunk_id": str, "text": str}`。
    """
    backend = _ensure_backend()
    if backend == "chroma":
        collection = _get_chroma_collection()
        # 同一文档重新分块时，旧分块可能已不存在。先按文档删掉可防止
        # 旧向量继续被召回；随后 upsert 让重复索引保持幂等。
        collection.delete(where={"doc_id": doc_id})
        collection.upsert(
            ids=[str(chunk["chunk_id"]) for chunk in chunks],
            documents=[str(chunk["text"]) for chunk in chunks],
            embeddings=[embedding.embed(str(chunk["text"])) for chunk in chunks],
            metadatas=[{"doc_id": doc_id} for _ in chunks],
        )
        return
    for chunk in chunks:
        _MEMORY.append((doc_id, chunk["chunk_id"], chunk["text"], embedding.embed(chunk["text"])))


def search(query: str, top_k: int = 5) -> list[VectorHit]:
    """按余弦相似度返回最相近的 top_k 个块。空索引返回空列表。"""
    backend = _ensure_backend()
    query_vec = embedding.embed(query)
    if backend == "chroma":
        collection = _get_chroma_collection()
        indexed_count = collection.count()
        if indexed_count == 0:
            return []
        result = collection.query(query_embeddings=[query_vec], n_results=min(top_k, indexed_count))
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        return [
            VectorHit(
                doc_id=int(metadata.get("doc_id", 0)),
                chunk_id=str(chunk_id),
                text=str(text),
                score=1.0 - float(distance),
            )
            for chunk_id, text, metadata, distance in zip(ids, documents, metadatas, distances, strict=True)
        ]
    scored = [
        VectorHit(doc_id=doc_id, chunk_id=chunk_id, text=text, score=_cosine(query_vec, vec))
        for doc_id, chunk_id, text, vec in _MEMORY
    ]
    scored.sort(key=lambda hit: hit.score, reverse=True)
    return scored[:top_k]


def clear() -> None:
    """清空当前后端索引；测试默认仅触及 memory。"""
    global _CHROMA_COLLECTION, _CHROMA_COLLECTION_KEY

    _MEMORY.clear()
    if _settings.vector_backend == "chroma":
        client = _get_chroma_client()
        try:
            client.delete_collection(_settings.chroma_collection)
        except Exception as exc:
            # Chroma 在集合尚不存在时以 ValueError 表示；这对测试清理和
            # 首次启动都是正常情况。不同 Chroma 小版本使用 ValueError 或
            # NotFoundError，故不直接依赖它的异常类；其他错误仍应暴露。
            if not _collection_missing(exc):
                raise _vector_unavailable("清空 Chroma 集合失败", exc) from exc
        _CHROMA_COLLECTION = None
        _CHROMA_COLLECTION_KEY = None


def _ensure_backend() -> str:
    if _settings.vector_backend not in {"memory", "chroma"}:
        raise BusinessError(ErrorCode.VECTOR_UNAVAILABLE, f"向量后端 {_settings.vector_backend!r} 尚未实现")
    return _settings.vector_backend


def _get_chroma_client() -> Any:
    global _CHROMA_CLIENT, _CHROMA_CLIENT_PATH
    if _CHROMA_CLIENT is None or _settings.chroma_path != _CHROMA_CLIENT_PATH:
        try:
            import chromadb
        except ImportError as exc:
            raise BusinessError(ErrorCode.VECTOR_UNAVAILABLE, "Chroma 依赖未安装") from exc
        try:
            _CHROMA_CLIENT = chromadb.PersistentClient(path=_settings.chroma_path)
            _CHROMA_CLIENT_PATH = _settings.chroma_path
        except Exception as exc:
            raise _vector_unavailable("初始化 Chroma 向量库失败", exc) from exc
    return _CHROMA_CLIENT


def _get_chroma_collection() -> Any:
    global _CHROMA_COLLECTION, _CHROMA_COLLECTION_KEY
    key = (_settings.chroma_path, _settings.chroma_collection)
    if _CHROMA_COLLECTION is None or key != _CHROMA_COLLECTION_KEY:
        try:
            _CHROMA_COLLECTION = _get_chroma_client().get_or_create_collection(
                name=_settings.chroma_collection,
                metadata={"hnsw:space": "cosine"},
            )
            _CHROMA_COLLECTION_KEY = key
        except Exception as exc:
            raise _vector_unavailable("打开 Chroma 集合失败", exc) from exc
    return _CHROMA_COLLECTION


def _vector_unavailable(message: str, exc: Exception) -> BusinessError:
    """把 Chroma 的实现异常转换为稳定的业务错误，原始细节仅留在异常链。"""
    return BusinessError(ErrorCode.VECTOR_UNAVAILABLE, message)


def _collection_missing(exc: Exception) -> bool:
    """兼容 Chroma 版本间的“集合不存在”异常差异。"""
    return exc.__class__.__name__ == "NotFoundError" or "does not exist" in str(exc).lower()


def _cosine(a: list[float], b: list[float]) -> float:
    # 向量已归一化，点积即余弦相似度。
    # strict=True：两边维度不同说明嵌入实现出了问题，应立刻暴露而不是静默截断。
    return sum(x * y for x, y in zip(a, b, strict=True))
