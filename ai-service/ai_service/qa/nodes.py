"""实现 Agent 工作流各步骤。"""

import logging
import re
from contextlib import aclosing
from itertools import islice

from pydantic import ValidationError
from pydantic_core import from_json

from ai_service.errors import InferenceError
from ai_service.llm import DeepSeekInvocationError, invoke_chat, stream_chat
from ai_service.qa.prompts import LEGAL_QA_PROMPT, REPORT_FOLLOWUP_PROMPT
from ai_service.qa.schemas import GroundedAnswer
from ai_service.qa.state import AnswerDelta, LegalQaState

logger = logging.getLogger("lawwiz.qa")
_CITATION_MARKER = re.compile(r"\[([0-9]+)\]")
_PREVIEW_MARKERS = re.compile(r"\[[0-9]+\]|\[[0-9]*$")
_MAX_MODEL_OUTPUT = 160_000


class LegalQaNodes:
    """问答图的节点使用注入的检索和模型客户端。"""

    def __init__(self, search_laws, llm=None) -> None:
        self._search_laws = search_laws
        self._llm = llm

    async def retrieve_law(self, state: LegalQaState) -> LegalQaState:
        """以当前问题为主检索，报告追问加入风险与最近提问线索。"""
        context = state["context"]
        report = state.get("report")
        query = state["question"]
        if report:
            prior_question = next(
                (message.content for message in reversed(state.get("history", [])) if message.role == "user"),
                None,
            )
            focus = [value for value in (report.risk_label, report.risk_description, prior_question) if value]
            if focus:
                # 保留完整用户问题的提示词，检索字符串遵守知识库的 4000 字符上限。
                query = f"{query[:3200]}\n{' '.join(focus)}"[:4000]
        try:
            sources = await self._search_laws(query, request_id=context.request_id, trace_id=context.trace_id)
        except InferenceError as exc:
            if not report or exc.status not in {404, 503}:
                raise
            logger.warning("报告追问无法检索知识库，request_id=%s status=%s", context.request_id, exc.status)
            return {"sources": [], "retrieval_unavailable": True}
        return {
            "sources": [
                source
                for source in sources
                if source.document_type != "template"
                and source.document_id
                and source.knowledge_base_chunk_id
                and source.quoted_text
                and source.quoted_text.strip()
            ]
        }

    async def generate_answer(self, state: LegalQaState) -> LegalQaState:
        """生成答复，并只保留模型实际使用的本轮依据。"""
        if state.get("report"):
            return await self._generate_followup(state)
        if self._llm is None:
            return {"answer": "法律问答暂不可用，请稍后重试。", "sources": []}
        candidates = list(islice(state.get("sources", []), 5))
        messages = LEGAL_QA_PROMPT.format_messages(
            question=state["question"], sources=self._format(candidates)
        )
        return await self._answer_from_model(messages, candidates, emit=state.get("emit"))

    async def _generate_followup(self, state: LegalQaState) -> LegalQaState:
        report = state["report"]
        assert report is not None
        original = report.risk_description or report.summary or "已关联审查报告。"
        if report.is_dismissed:
            original += "\n该风险项已被标记为误报。"
        prefix = f"报告原有分析\n{original}\n\n本轮依据与建议\n"
        candidates = list(islice(state.get("sources", []), 5))
        next_step = "可先核对报告标出的条款和实际履行记录，再确认需要补充的材料。"
        if state.get("retrieval_unavailable") or self._llm is None:
            reason = "知识库暂不可用。" if state.get("retrieval_unavailable") else ""
            return {"answer": f"{prefix}{reason}{next_step}", "sources": []}

        messages = REPORT_FOLLOWUP_PROMPT.format_messages(
            report=report,
            history="\n".join(f"{message.role}：{message.content}" for message in state.get("history", [])),
            question=state["question"],
            sources=self._format(candidates),
        )
        return await self._answer_from_model(messages, candidates, prefix=prefix, emit=state.get("emit"))

    @staticmethod
    def _format(candidates) -> str:
        return "\n\n".join(
            f"[{i}] {citation.law_name or citation.title or ''} {citation.article_no or ''}\n{citation.quoted_text}"
            for i, citation in enumerate(candidates, start=1)
        )

    async def _answer_from_model(
        self, messages, candidates, *, prefix: str = "", emit: AnswerDelta | None = None
    ) -> LegalQaState:
        if emit is None:
            response = await invoke_chat(self._llm, messages)
            content = response.content if isinstance(response.content, str) else ""
            model_name = self._model_name(response)
        else:
            content, model_name = await self._stream_model(messages, prefix, emit)
        content = content.strip()
        if content.startswith("```json\n") and content.endswith("\n```"):
            content = content.removeprefix("```json\n").removesuffix("\n```")
        try:
            result = GroundedAnswer.model_validate_json(content)
        except ValidationError as exc:
            raise DeepSeekInvocationError("模型未返回有效的问答结果") from exc
        selected = {str(i): candidates[i - 1] for i in result.citations if 1 <= i <= len(candidates)}
        numbers: dict[str, int] = {}

        def citation_label(match: re.Match[str]) -> str:
            candidate = match[1]
            if candidate not in selected:
                return ""
            number = numbers.setdefault(candidate, len(numbers) + 1)
            return f"[{number}]"

        # 字典以正文首次出现顺序编号；未在正文引用的候选不写入结果。
        text = _CITATION_MARKER.sub(citation_label, result.answer).strip()
        if not text:
            raise DeepSeekInvocationError("模型返回空回答")
        cited = [selected[candidate] for candidate in numbers]
        return {"answer": prefix + text, "sources": cited, "model_name": model_name}

    async def _stream_model(self, messages, prefix: str, emit: AnswerDelta) -> tuple[str, str | None]:
        content = ""
        emitted = ""
        model_name = None
        async with aclosing(stream_chat(self._llm, messages)) as chunks:
            async for chunk in chunks:
                reported_model = chunk.response_metadata.get("model_name")
                if isinstance(reported_model, str):
                    model_name = reported_model
                if not isinstance(chunk.content, str) or not chunk.content:
                    continue
                content += chunk.content
                if len(content) > _MAX_MODEL_OUTPUT:
                    raise DeepSeekInvocationError("模型返回的问答结果过长")
                try:
                    partial = from_json(
                        content.lstrip().removeprefix("```json\n"), allow_partial="trailing-strings"
                    )
                except ValueError:
                    continue
                text = partial.get("answer") if isinstance(partial, dict) else None
                if not isinstance(text, str):
                    continue
                # 引用编号等完整结构校验后再展示，避免预览中的编号和最终引文不一致。
                text = _PREVIEW_MARKERS.sub("", text.lstrip()[:12000])
                if text and text.startswith(emitted) and text != emitted:
                    await emit((prefix if not emitted else "") + text[len(emitted) :])
                    emitted = text
        return content, model_name or self._model_name()

    def _model_name(self, response=None) -> str | None:
        model_name = response.response_metadata.get("model_name") if response is not None else None
        if not isinstance(model_name, str):
            model_name = getattr(self._llm, "model_name", None)
        return model_name if isinstance(model_name, str) else None

    async def validate_citations(self, state: LegalQaState) -> LegalQaState:
        """从本次检索结果保留可定位且含有引用文本的来源。"""
        sources = [
            source
            for source in state.get("sources", [])
            if source.document_id and source.knowledge_base_chunk_id and source.quoted_text
        ]
        return {"sources": sources}
