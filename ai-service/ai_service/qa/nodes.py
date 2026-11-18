"""实现 Agent 工作流各步骤。"""

import logging
import re
from itertools import islice

from pydantic import ValidationError

from ai_service.errors import InferenceError
from ai_service.llm import DeepSeekInvocationError, invoke_chat
from ai_service.qa.prompts import LEGAL_QA_PROMPT, REPORT_FOLLOWUP_PROMPT
from ai_service.qa.schemas import FollowupAnswer
from ai_service.qa.state import LegalQaState

logger = logging.getLogger("lawwiz.qa")
_EVIDENCE_MISSING = "未找到直接法律依据"


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
                if source.document_id
                and source.knowledge_base_chunk_id
                and source.quoted_text
                and source.quoted_text.strip()
            ]
        }

    async def generate_answer(self, state: LegalQaState) -> LegalQaState:
        """无有效检索来源时返回固定提示；模型返回空文本时作为失败处理。"""
        if state.get("report"):
            return await self._generate_followup(state)
        if not state.get("sources"):
            return {"answer": "未找到直接法律依据，无法给出确定性回答。"}
        if self._llm is not None:
            messages = LEGAL_QA_PROMPT.format_messages(question=state["question"], sources=state["sources"])
            response = await invoke_chat(self._llm, messages)
            content = response.content if isinstance(response.content, str) else ""
            if content.strip():
                return {"answer": content.strip(), "model_name": self._model_name(response)}
            raise DeepSeekInvocationError("模型返回空回答")
        return {"answer": f"依据已检索到的法律材料，针对“{state['question']}”应结合具体合同事实判断。"}

    async def _generate_followup(self, state: LegalQaState) -> LegalQaState:
        report = state["report"]
        assert report is not None
        original = report.risk_description or report.summary or "已关联审查报告。"
        if report.is_dismissed:
            original += "\n该风险项已被标记为误报。"
        prefix = f"报告原有分析\n{original}\n\n本轮依据与建议\n"
        candidates = list(islice(state.get("sources", []), 5))
        next_step = "可先核对报告标出的条款和实际履行记录，再确认需要补充的材料。"
        if not candidates or self._llm is None:
            reason = (
                f"知识库暂不可用，本轮{_EVIDENCE_MISSING}。"
                if state.get("retrieval_unavailable")
                else f"本轮{_EVIDENCE_MISSING}。"
            )
            return {"answer": f"{prefix}{reason}{next_step}", "sources": []}

        sources = "\n\n".join(
            f"[{i}] {citation.law_name or citation.title or ''} {citation.article_no or ''}\n{citation.quoted_text}"
            for i, citation in enumerate(candidates, start=1)
        )
        messages = REPORT_FOLLOWUP_PROMPT.format_messages(
            report=report,
            history="\n".join(f"{message.role}：{message.content}" for message in state.get("history", [])),
            question=state["question"],
            sources=sources,
        )
        response = await invoke_chat(self._llm, messages)
        content = response.content if isinstance(response.content, str) else ""
        content = content.strip()
        if content.startswith("```json\n") and content.endswith("\n```"):
            content = content.removeprefix("```json\n").removesuffix("\n```")
        try:
            followup = FollowupAnswer.model_validate_json(content)
        except ValidationError as exc:
            raise DeepSeekInvocationError("模型未返回有效的报告追问结果") from exc
        text = followup.answer.strip()
        if not text:
            raise DeepSeekInvocationError("模型返回空回答")
        # 引用标号按保存后实际展示的顺序重排，避免引用候选 3 却只展示引用 1。
        selected = [i for i in dict.fromkeys(followup.citations) if 1 <= i <= len(candidates)]
        cited = [candidates[i - 1] for i in selected]
        numbers = {str(candidate): number for number, candidate in enumerate(selected, start=1)}

        def citation_label(match: re.Match[str]) -> str:
            number = numbers.get(match[1])
            return f"[{number}]" if number is not None else "（引文未核实）"

        text = re.sub(r"\[([0-9]+)\]", citation_label, text)
        if not cited:
            text = f"本轮{_EVIDENCE_MISSING}。\n{text}"
        return {"answer": prefix + text, "sources": cited, "model_name": self._model_name(response)}

    def _model_name(self, response) -> str | None:
        model_name = response.response_metadata.get("model_name")
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
