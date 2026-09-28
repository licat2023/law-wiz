# 智法宝 AI Service

独立于业务后端的 Agent 能力服务。它负责 AI 推理、LangGraph 工作流、LangChain 模型与 Tool；不直接访问 Backend 业务数据库。

## 代码结构与职责

- `app/main.py`、`app/api/v1/agent.py`：FastAPI 通用入口 `POST /api/v1/agent/invoke`。
- `app/service/agent_service.py`、`app/agent/core/`：AgentService、Runtime、Registry、BaseAgent、DemoAgent。
- `app/agent/legal_qa/`：薄 Agent 入口、State、Graph、Nodes、Prompts；流程为 `prepare_query → retrieve_law → generate_answer → validate_citations → finalize`。
- `app/agent/contract_review/`：薄 Agent 入口、State、Graph、Nodes、Prompts；流程为 `prepare_contract → extract_terms → retrieve_laws → retrieve_risk_rules → analyze_risks → validate_sources → finalize`。
- `app/tools/backend.py`：BackendClient、法规检索/风险规则 Tool 与自动化测试用 Fake Tool。
- `app/llm/deepseek.py`：DeepSeek 的唯一 LangChain 接入点；日志不记录 API Key。
- `app/schemas/contracts.py`：AgentContext、Input/Result、Citation、RiskPoint 等稳定契约。

调用链：`POST /api/v1/agent/invoke` → `AgentService` → `AgentRuntime` → `AgentRegistry` → `BaseAgent.invoke(input, context)`。

## 运行

安装依赖后，从 `ai-service` 目录启动：

```bash
uv sync --extra dev
uv run uvicorn app.main:app --reload --port 8001
```

请求示例：

```json
{
  "agentCode": "legal_qa",
  "input": {"question": "违约责任如何承担？"},
  "context": {"requestId": "request-001", "userId": "1", "sessionId": "2"}
}
```

`contract_review` 的 `input` 为 `{ "plain_text": "..." }`。文件解析、OCR 与业务持久化始终由 Backend 负责；Agent 只接收已经文本化的合同。

## 环境变量与测试

从 `.env.example` 复制变量名到本地环境或 `.env`，不得提交真实值：

- `AI_SERVICE_BACKEND_BASE_URL`、`AI_SERVICE_BACKEND_TOKEN`：访问受保护 Backend Internal API。
- `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`：真实模型配置；未完整配置时使用 Fake/离线能力，测试不依赖网络。
- `AI_SERVICE_REQUEST_TIMEOUT_SECONDS`：真实模型调用超时，默认 60 秒。

```powershell
uv run --extra dev ruff check .
uv run --extra dev python -m unittest discover -s tests
uv run --extra dev python -m compileall -q app
```
