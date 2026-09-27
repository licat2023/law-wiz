"""问答生成流水线（异步）。

⚠️ 约定与其它流水线相同：**异步函数**、由 `BackgroundTasks` 调度、
只调用 `app/infra/*` 的封装，不实现任何 AI 能力。

⚠️ **`qa_message` 没有状态列与错误列**（见 04-数据库设计 §5.14，消息表只增不改）。
因此生成失败时**无法记录"失败状态"**，只能把说明写进 `content` ——
前端看到的就是这条内容。`has_citation` 同时置为 `false`，
使"这条回答没有依据"在界面上是显式的。
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now_beijing
from app.core.config import get_settings
from app.core.errors import BusinessError
from app.infra.concurrency import pipeline_gate
from app.infra.db.session import SessionLocal
from app.models.qa import QaMessage, QaSession
from app.slices.qa.agent import LegalQaAgent

logger = logging.getLogger("lawwiz.qa")

_settings = get_settings()

_GENERATION_FAILED = "回答生成失败，请稍后重试。"

# Agent 无状态，可在进程内复用；数据库会话仍由每次流水线调用传入。
legal_qa_agent = LegalQaAgent()


async def run_answer_pipeline(*, message_id: int, session_id: int) -> None:
    """生成 assistant 消息的内容与引用。**异常一律写进消息内容**，不向外抛。"""
    async with SessionLocal() as db:
        # ⚠️ 并发闸门：必须在第一次用数据库之前取得（见 review/pipeline.py 的同处说明）
        if not await pipeline_gate.acquire():
            await _write_failure(db, message_id, "服务繁忙，请稍后重试")
            return
        try:
            message = await db.get(QaMessage, message_id)
            session = await db.get(QaSession, session_id)
            if message is None or session is None:
                logger.warning("消息 %s 或会话 %s 不存在，跳过生成", message_id, session_id)
                return

            question = await _load_question(db, session_id=session_id, before_message_id=message_id)
            if question is None:
                await _write_failure(db, message, "未找到对应的提问，无法生成回答。")
                return

            started = time.perf_counter()
            answer = await legal_qa_agent.invoke(db=db, question=question)
            elapsed_ms = int((time.perf_counter() - started) * 1000)

            citations = legal_qa_agent.record_citations(db, message=message, answer=answer)
            message.content = answer.content
            message.has_citation = bool(citations)
            message.model_name = _settings.llm_model
            message.latency_ms = elapsed_ms
            await db.commit()
            logger.info("消息 %s 生成完成，引用 %d 条，耗时 %dms", message_id, len(citations), elapsed_ms)

        except BusinessError as exc:
            await _write_failure(db, message_id, str(exc.message))
        except Exception:
            logger.exception("消息 %s 生成失败", message_id)
            await _write_failure(db, message_id, _GENERATION_FAILED)
        finally:
            pipeline_gate.release()


async def _load_question(db: AsyncSession, *, session_id: int, before_message_id: int) -> str | None:
    """取该 assistant 消息之前最近的一条 user 消息作为提问。"""
    return await db.scalar(
        select(QaMessage.content)
        .where(
            QaMessage.qa_session_id == session_id,
            QaMessage.role == "user",
            QaMessage.id < before_message_id,
        )
        .order_by(QaMessage.id.desc())
        .limit(1)
    )


async def _write_failure(db: AsyncSession, message: QaMessage | int, reason: str) -> None:
    """把失败写进消息内容。**`qa_message` 没有状态列，这是唯一的记录方式。**"""
    message_id = message if isinstance(message, int) else message.id
    try:
        await db.rollback()
        target = await db.get(QaMessage, message_id)
        if target is None:
            return
        target.content = _GENERATION_FAILED if reason == _GENERATION_FAILED else f"回答生成失败：{reason}"
        target.has_citation = False
        target.created_at = target.created_at or now_beijing()
        await db.commit()
    except Exception:
        logger.exception("写入回答失败状态时又出错了")
