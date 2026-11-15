"""注册所有知识库 ORM 模型，供启动和建表命令使用。"""

from app.documents.models import Document, DocumentRevision, ImportRecord
from app.indexing.models import Chunk, IndexRevision, KeywordLeaf, KeywordPosting, ProcessingJob
from app.infrastructure.database import Base
from app.infrastructure.idempotency_models import IdempotencyRecord
from app.knowledge_bases.models import KnowledgeBase

__all__ = [
    "Base",
    "Chunk",
    "Document",
    "DocumentRevision",
    "IdempotencyRecord",
    "ImportRecord",
    "IndexRevision",
    "KeywordLeaf",
    "KeywordPosting",
    "KnowledgeBase",
    "ProcessingJob",
]
