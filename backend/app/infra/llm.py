"""LLM 能力的唯一封装。

⚠️ **外部能力单点封装**（见仓库根 AGENTS.md 硬性约束）：业务代码不得出现
任何厂商 SDK 的直接调用，一律通过本模块。

**与 AI 队友的接缝**：对方接入真实服务（`llm_provider=deepseek/ollama`）时
**只改本文件内部**，不得改动函数签名与错误行为 —— 业务代码只依赖本文件
声明的契约。

错误行为约定（业务代码必须按此处理，任务式接口应把任务标记为 `failed`
而不是把异常直接抛给用户）：
- 能力未接入（`llm_provider=stub`）→ `BusinessError(LLM_UNAVAILABLE)`；
- 已接入但返回无法解析 / 不满足 schema，重试 `llm_max_retries` 次后
  → `BusinessError(LLM_BAD_RESPONSE)`。

⚠️ **调用方请用「模块属性」写法**：

    from app.infra import llm
    llm.complete_structured(...)

**不要** `from app.infra.llm import complete_structured` —— 后者在 import 时
就把函数对象绑定进调用方命名空间，之后对模块的替换（测试 monkeypatch、
运行期切 provider）都不会对调用方生效。
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.core.errors import BusinessError, ErrorCode

_settings = get_settings()


def complete_structured(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
    """调用 LLM，要求返回符合 JSON Schema 的结构化数据。

    这是异步流水线（条款提取、风险分析、问答生成）中**唯一的** LLM 入口。
    """
    if _settings.llm_provider == "stub":
        raise BusinessError(ErrorCode.LLM_UNAVAILABLE, "AI 能力尚未接入，无法完成该步骤")
    # 真实接入由 AI 队友实现；接入后此处应完成：构造请求 → 按 llm_max_retries
    # 重试解析 → 成功返回 dict，失败抛 BusinessError(LLM_BAD_RESPONSE)。
    raise BusinessError(ErrorCode.LLM_UNAVAILABLE, f"LLM 提供方 {_settings.llm_provider!r} 的实现尚未落地")
