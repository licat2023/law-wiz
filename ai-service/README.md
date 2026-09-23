# 智法宝 AI Service

这是智法宝的轻量级 FastAPI Agent 服务原型。它将 HTTP 接口、业务编排和具体 Agent 实现分层，便于后续替换 `DemoAgent` 为合同审查、问答等真实能力。

## 代码结构与职责

- `app/main.py`：FastAPI 应用入口；注册 v1 Agent 路由。
- `app/api/v1/agent.py`：HTTP 适配层；接收请求模型、调用服务，并转换为响应模型。
- `app/schemas/agent.py`：Pydantic 请求/响应契约；`requestId` 与 `agentCode` 是面向 API 的别名，仍兼容 Python 的蛇形字段名。
- `app/service/agent_service.py`：业务服务层；创建注册中心与运行时，并将调用参数交给运行时处理。
- `app/agent/registry.py`：Agent 注册中心；维护 `agent_code -> Agent` 的映射，当前注册 `demo`。
- `app/agent/runtime.py`：调度层；按 `agent_code` 查找 Agent 并调用其统一的 `invoke` 契约；当 Agent 不存在时抛出领域错误。
- `app/agent/core/base_agent.py`：抽象接口；规定所有 Agent 都实现 `invoke(message, scene)`。
- `app/agent/core/demo_agent.py`：可运行的示例实现；用于验证从 API 到 Agent 的整条调用链。

调用链：`POST /api/v1/agent/test` → `AgentService` → `AgentRuntime` → `AgentRegistry` → `BaseAgent.invoke`。

## 运行

安装依赖后，从 `ai-service` 目录启动：

```bash
uvicorn app.main:app --reload
```

请求示例：

```json
{
  "requestId": "demo-001",
  "agentCode": "demo",
  "message": "请测试服务",
  "scene": "CONNECTIVITY_TEST"
}
```

`agentCode` 可省略，此时服务默认调用 `demo`。
