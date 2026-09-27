"""法律问答 Agent（M3）。

本模块承载一次问答中的 AI 决策：先调用向量检索 Tool 取得可引用法条，
再调用结构化 LLM Tool 生成回答。它不管理 HTTP、会话生命周期或后台任务，
这些编排职责仍由 ``router -> service -> pipeline`` 承担。

``ai-service`` 中的 ``BaseAgent`` / ``Runtime`` 是未部署的独立原型，缺少
产品请求所必需的用户身份、会话和持久化上下文；因此不能让产品 API 反向代理到
该原型。这里直接复用已部署后端的 M3 链路，避免两套问答业务逻辑发生漂移。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessError, ErrorCode
from app.infra import llm, vector
from app.models.knowledge import KbChunk, KbDocument
from app.models.qa import QaCitation, QaMessage
from app.slices.qa import prompts


@dataclass(slots=True)
class CitationCandidate:
    """一条可被 Agent 引用的法条片段及其可读元数据。"""

    index: int
    chunk: KbChunk
    document: KbDocument
    score: float


@dataclass(slots=True)
class LegalQaAnswer:
    """Agent 的结构化输出。

    ``used_indexes`` 由模型回报；后续只能据此创建引用，不能把所有检索命中
    冒充为实际依据。这是回答溯源的关键约束。
    """

    content: str
    used_indexes: object
    candidates: list[CitationCandidate]


class LegalQaAgent:
    """处理法律问题的正式业务 Agent。

    Tool 边界：
    - ``app.infra.vector``：RAG 检索；
    - ``app.infra.llm``：受 JSON Schema 约束的回答生成。

    业务代码只通过这两个 infra 封装使用外部能力，真实厂商替换无需改 Agent。
    """

    async def invoke(self, *, db: AsyncSession, question: str) -> LegalQaAnswer:
        """执行一次“检索 → 受约束生成”的问答决策。"""
        context, candidates = await self._retrieve_context(db, question)
        result = llm.complete_structured(
            prompts.QA_SYSTEM,
            prompts.QA_USER_TEMPLATE.format(context=context, question=question),
            prompts.QA_SCHEMA,
        )
        content = str(result.get("answer") or "").strip()
        if not content:
            raise BusinessError(ErrorCode.LLM_BAD_RESPONSE, "模型未返回回答内容")
        return LegalQaAnswer(
            content=content,
            used_indexes=result.get("used_indexes"),
            candidates=candidates,
        )

    async def _retrieve_context(
        self, db: AsyncSession, question: str
    ) -> tuple[str, list[CitationCandidate]]:
        """调用检索 Tool，并过滤已删除或已废止的语料。"""
        hits = vector.search(question, top_k=prompts.MAX_CONTEXT_CHUNKS)
        if not hits:
            return "（未检索到相关法条）", []

        chunk_ids = [int(hit.chunk_id) for hit in hits if hit.chunk_id.isdigit()]
        if not chunk_ids:
            return "（未检索到相关法条）", []
        chunks = {
            chunk.id: chunk
            for chunk in (await db.execute(select(KbChunk).where(KbChunk.id.in_(chunk_ids)))).scalars().all()
        }
        document_ids = {chunk.kb_document_id for chunk in chunks.values()}
        documents = {
            document.id: document
            for document in (
                await db.execute(select(KbDocument).where(KbDocument.id.in_(document_ids)))
            )
            .scalars()
            .all()
        }

        candidates: list[CitationCandidate] = []
        lines: list[str] = []
        for hit in hits:
            if not hit.chunk_id.isdigit():
                continue
            chunk = chunks.get(int(hit.chunk_id))
            if chunk is None:
                continue
            document = documents.get(chunk.kb_document_id)
            # 已删除或已废止的法条不能作为回答依据。
            if document is None or document.deleted_at is not None or document.abolished_date is not None:
                continue

            index = len(candidates) + 1
            label = chunk.law_name or document.law_name or document.title
            article_no = chunk.article_no or document.article_no
            if article_no:
                label = f"{label} {article_no}"
            candidates.append(CitationCandidate(index=index, chunk=chunk, document=document, score=hit.score))
            lines.append(f"[{index}] {label}\n{chunk.content}")

        return ("\n\n".join(lines) if lines else "（未检索到相关法条）"), candidates

    @staticmethod
    def record_citations(
        db: AsyncSession, *, message: QaMessage, answer: LegalQaAnswer
    ) -> list[QaCitation]:
        """仅为模型声明实际使用的片段创建可溯源引用记录。"""
        used_indexes = _parse_indexes(answer.used_indexes)
        citations: list[QaCitation] = []
        for candidate in answer.candidates:
            if candidate.index not in used_indexes:
                continue
            citation = QaCitation(
                qa_message_id=message.id,
                kb_document_id=candidate.document.id,
                kb_chunk_id=candidate.chunk.id,
                quoted_text=candidate.chunk.content,
                relevance_score=candidate.score,
            )
            db.add(citation)
            citations.append(citation)
        return citations


def _parse_indexes(value: object) -> set[int]:
    """容忍数字字符串，但拒绝非正整数，避免模型编造索引污染引用。"""
    if not isinstance(value, list):
        return set()
    return {
        int(item)
        for item in value
        if (isinstance(item, int) and not isinstance(item, bool) and item > 0)
        or (isinstance(item, str) and item.isdigit() and int(item) > 0)
    }
