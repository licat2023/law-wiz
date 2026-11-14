"""Chroma 的唯一接入点；每个嵌入空间独立集合。"""

import hashlib
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings


class VectorStore:
    def __init__(self, root: Path):
        root = root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=root.as_posix(),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    def _collection(self, fingerprint: str):
        name = "kb_" + hashlib.sha256(fingerprint.encode()).hexdigest()[:32]
        return self.client.get_or_create_collection(
            name, embedding_function=None, metadata={"hnsw:space": "cosine"}
        )

    def upsert(self, fingerprint, kb_id, document_id, index_id, ids, texts, embeddings):
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
        for collection in self.client.list_collections():
            self.client.get_collection(collection.name, embedding_function=None).delete(
                where={"document_id": document_id},
            )

    def delete_index(self, fingerprint, index_id):
        self._collection(fingerprint).delete(where={"index_id": index_id})

    def heartbeat(self):
        return self.client.heartbeat()
