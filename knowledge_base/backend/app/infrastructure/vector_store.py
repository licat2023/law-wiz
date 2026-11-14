"""Chroma 的唯一接入点；每个嵌入空间独立集合。"""

import hashlib
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings


class VectorStore:
    """同步操作进程独占的持久化 Chroma，异步调用方需把磁盘操作移出事件循环。"""

    def __init__(self, root: Path):
        root = root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=root.as_posix(),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    def _collection(self, fingerprint: str):
        """按嵌入指纹获取余弦距离集合，向量由调用方预先计算。"""
        name = "kb_" + hashlib.sha256(fingerprint.encode()).hexdigest()[:32]
        return self.client.get_or_create_collection(
            name, embedding_function=None, metadata={"hnsw:space": "cosine"}
        )

    def upsert(self, fingerprint, kb_id, document_id, index_id, ids, texts, embeddings):
        """分批写入叶块向量，确认索引下保存的 ID 集合与输入一致。"""
        collection = self._collection(fingerprint)
        for offset in range(0, len(ids), 128):
            batch = ids[offset : offset + 128]
            collection.upsert(
                ids=batch,
                documents=texts[offset : offset + 128],
                embeddings=embeddings[offset : offset + 128],
                metadatas=[{"kb_id": kb_id, "document_id": document_id, "index_id": index_id}] * len(batch),
            )
        stored = collection.get(where={"index_id": index_id}, include=[])
        if set(stored["ids"]) != set(ids):
            raise ValueError("向量写入数量不完整")

    def query(self, fingerprint, kb_id, active_indexes, embedding, top_k):
        """在指定库及候选索引内召回，返回块 ID 和裁剪至 0–1 的相似度。"""
        if not active_indexes:
            return []
        collection = self._collection(fingerprint)
        result = collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where={"$and": [{"kb_id": kb_id}, {"index_id": {"$in": active_indexes}}]},
            include=["distances"],
        )
        return [
            (chunk_id, max(0.0, min(1.0, 1 - distance)))
            for chunk_id, distance in zip(result["ids"][0], result["distances"][0], strict=True)
        ]

    def delete_document(self, document_id):
        """跨指纹集合删除该文档的向量，覆盖重建前使用的嵌入空间。"""
        for collection in self.client.list_collections():
            self.client.get_collection(collection.name, embedding_function=None).delete(
                where={"document_id": document_id},
            )

    def delete_index(self, fingerprint, index_id):
        """从指定嵌入空间删除某次索引写入的全部向量。"""
        self._collection(fingerprint).delete(where={"index_id": index_id})

    def heartbeat(self):
        """检查持久化向量客户端可用性，供就绪探针调用。"""
        return self.client.heartbeat()
