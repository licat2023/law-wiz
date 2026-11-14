# 后端重构文件清单

记录 Demo 重构的目录职责、文件归属和验收。实施基线为当前分支的工作区内容，包含已有未提交实现。

## 目录职责

| 目录 | 职责 |
| --- | --- |
| `backend/app/domains/auth/` | 用户、登录和令牌 |
| `backend/app/domains/files/` | 上传、格式识别和文件读取 |
| `backend/app/domains/contracts/` | 合同版本及该版本的正文 |
| `backend/app/domains/contract_review/` | 审查任务、风险规则、Agent 和报告 |
| `backend/app/domains/legal_qa/` | 问答会话、消息、Agent 和引用快照 |
| `backend/app/api/`、`backend/app/core/` | HTTP 入口及应用公共契约 |
| `backend/app/infrastructure/` | 数据库、存储、缓存、模型与 KB 连接 |
| `knowledge_base/backend/app/knowledge_bases/` | 库设置和访问范围 |
| `knowledge_base/backend/app/documents/` | 文档、原文件、修订、解析及导入 |
| `knowledge_base/backend/app/indexing/` | 切分、嵌入、处理任务与索引发布 |
| `knowledge_base/backend/app/retrieval/` | 查询生效索引和组装来源 |
| `frontend/`、`knowledge_base/frontend/` | 业务界面和知识库管理界面 |
| `deploy/` | 两个后端、数据库与缓存的部署编排 |

## 施工顺序与验收

1. 迁移领域与 Agent。核对 OpenAPI、空库模型登记、合同解析、审查报告和问答引用。
2. 拆分知识库。核对原文件和正文上传、权限、索引发布、检索和失败时的旧索引。
3. 清理旧脚本和测试、更新配置与文档。在独立目录验证依赖、静态检查、前端构建与本地 Demo。

保留 `/api/reviews`、`/api/qa` 和 KB 管理接口的契约。单独部署 KB，业务后端直接运行 Agent。两个后端各自使用现有第三方解析依赖，不建共享包。语料经管理后台或入库接口提交。沿用独立数据库、MySQL 初始化入口和现有数据卷。

## 验收结果

- 干净源码副本使用两个 `uv.lock` 和两个 `pnpm-lock.yaml` 安装成功。两个后端 Ruff 检查及格式通过，两个前端 lint 和构建通过。知识库管理前端构建提示 Element Plus 包体较大。
- 业务 OpenAPI 保留原公开路径与方法，移除两个内部 AI HTTP 接口。知识库 OpenAPI 保留原路径与方法。业务与知识库空库分别登记 13 张和 8 张表。
- 知识库使用实际 Chroma 验证管理员登录、只读凭证写入拒绝、Markdown 和 DOCX 入库、空索引与已建索引分页、旧生效索引在新版本失败后仍可检索。
- 业务验证注册和登录、本地 DOCX 表格顺序与 PDF 页数、审查完成和 PDF 下载、知识文档兼容查询、问答引用落库，以及损坏 PDF 的审查失败状态。
- Demo 使用 SQLite 空库、Redis 内存替身、开发嵌入和模型替身。模型 SDK 客户端已单独验证创建及关闭。Compose 配置解析通过，Docker 守护进程未运行，真实 MySQL、Redis、远程模型和远程嵌入尚未联调。
- 重构前的 AI 工程、旧 `scripts/` 与 `tests/` 可从本地 Git 分支 `codex/pre-backend-refactor` 追溯。

## 文件清单

| 路径 | 职责 | 变更 | 状态 | 验证 |
| --- | --- | --- | --- | --- |
| `ai-service/.dockerignore` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/.env.example` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/Dockerfile` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/README.md` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/ai-core/pyproject.toml` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/ai-core/src/ai_core/__init__.py` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/ai-core/src/ai_core/agents/__init__.py` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/ai-core/src/ai_core/agents/contract_review/__init__.py` → `backend/app/domains/contract_review/agent/__init__.py` | 目录职责与包入口 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `ai-service/ai-core/src/ai_core/agents/contract_review/agent.py` → `backend/app/domains/contract_review/agent/agent.py` | Agent 调用入口 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `ai-service/ai-core/src/ai_core/agents/contract_review/graph.py` → `backend/app/domains/contract_review/agent/graph.py` | Agent 工作流 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `ai-service/ai-core/src/ai_core/agents/contract_review/nodes.py` → `backend/app/domains/contract_review/agent/nodes.py` | 推理或检索步骤 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `ai-service/ai-core/src/ai_core/agents/contract_review/prompts.py` → `backend/app/domains/contract_review/agent/prompts.py` | 提示词 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `ai-service/ai-core/src/ai_core/agents/contract_review/state.py` → `backend/app/domains/contract_review/agent/state.py` | 工作流状态 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `ai-service/ai-core/src/ai_core/agents/legal_qa/__init__.py` → `backend/app/domains/legal_qa/agent/__init__.py` | 目录职责与包入口 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `ai-service/ai-core/src/ai_core/agents/legal_qa/agent.py` → `backend/app/domains/legal_qa/agent/agent.py` | Agent 调用入口 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `ai-service/ai-core/src/ai_core/agents/legal_qa/graph.py` → `backend/app/domains/legal_qa/agent/graph.py` | Agent 工作流 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `ai-service/ai-core/src/ai_core/agents/legal_qa/nodes.py` → `backend/app/domains/legal_qa/agent/nodes.py` | 推理或检索步骤 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `ai-service/ai-core/src/ai_core/agents/legal_qa/prompts.py` → `backend/app/domains/legal_qa/agent/prompts.py` | 提示词 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `ai-service/ai-core/src/ai_core/agents/legal_qa/state.py` → `backend/app/domains/legal_qa/agent/state.py` | 工作流状态 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `ai-service/ai-core/src/ai_core/llm/__init__.py` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/ai-core/src/ai_core/llm/deepseek.py` → `backend/app/infrastructure/llm.py` | 工程配置或文档 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `ai-service/ai-core/src/ai_core/models/__init__.py` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/ai-core/src/ai_core/models/contracts.py` → `backend/app/core/agent.py`、`backend/app/core/citations.py`、`backend/app/domains/contract_review/agent/schemas.py`、`backend/app/domains/legal_qa/agent/schemas.py` | 工程配置或文档 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `ai-service/ai-core/src/ai_core/runtime/__init__.py` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/ai-core/src/ai_core/runtime/core/__init__.py` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/ai-core/src/ai_core/runtime/core/base_agent.py` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/ai-core/src/ai_core/runtime/exceptions.py` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/ai-core/src/ai_core/runtime/registry.py` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/ai-core/src/ai_core/runtime/runtime.py` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/ai-core/src/ai_core/tools/__init__.py` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/ai-core/src/ai_core/tools/knowledge_base.py` → `backend/app/infrastructure/knowledge_base.py` | 工程配置或文档 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `ai-service/ai-core/tests/test_boundaries.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/ai-core/tests/test_core_migration.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/ai-core/tests/test_deepseek.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/ai-core/tests/test_legal_qa.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/ai-core/tests/test_runtime.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/backend/app/__init__.py` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/backend/app/api/__init__.py` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/backend/app/api/agent.py` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/backend/app/api/exception_handlers.py` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/backend/app/core/config.py` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/backend/app/main.py` → `backend/app/lifespan.py` | 应用和路由入口 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `ai-service/backend/pyproject.toml` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/backend/tests/test_api.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/backend/tests/test_exception_handlers.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/pyproject.toml` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/pyrightconfig.json` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `ai-service/uv.lock` | 独立 AI 服务工程 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/app/api/internal.py` | 应用实现 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/app/core/config.py` → `backend/app/config.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/core/security.py` → `backend/app/domains/auth/security.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/infra/__init__.py` → `backend/app/infrastructure/__init__.py` | 目录职责与包入口 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/infra/ai_service.py` | 应用实现 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/app/infra/cache.py` → `backend/app/infrastructure/cache.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/infra/concurrency.py` → `backend/app/infrastructure/concurrency.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/infra/db/__init__.py` → `backend/app/infrastructure/database/__init__.py` | 目录职责与包入口 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/infra/db/base.py` → `backend/app/infrastructure/database/base.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/infra/db/bootstrap.py` → `backend/app/infrastructure/database/bootstrap.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/infra/db/session.py` → `backend/app/infrastructure/database/session.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/infra/knowledge_base.py` → `backend/app/infrastructure/knowledge_base.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/infra/parsing.py` → `backend/app/domains/files/formats.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/infra/ratelimit.py` → `backend/app/infrastructure/ratelimit.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/infra/risk_rules.py` → `backend/app/domains/contract_review/risk_rules.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/infra/storage.py` → `backend/app/infrastructure/storage.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/models/__init__.py` → `backend/app/infrastructure/database/models.py` | 目录职责与包入口 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/models/contract.py` → `backend/app/domains/contracts/models.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/models/file.py` → `backend/app/domains/files/models.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/models/knowledge.py` → `backend/app/domains/contract_review/rule_models.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/models/qa.py` → `backend/app/domains/legal_qa/models.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/models/review.py` → `backend/app/domains/contract_review/models.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/models/user.py` → `backend/app/domains/auth/models.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/README.md` | 工程入口与运行说明 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/app/slices/__init__.py` | 目录职责与包入口 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/app/slices/auth/__init__.py` → `backend/app/domains/auth/__init__.py` | 目录职责与包入口 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/auth/router.py` → `backend/app/domains/auth/router.py` | HTTP 路由 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/auth/schemas.py` → `backend/app/domains/auth/schemas.py` | 请求和响应契约 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/auth/service.py` → `backend/app/domains/auth/service.py` | 领域用例 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/files/__init__.py` → `backend/app/domains/files/__init__.py` | 目录职责与包入口 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/files/router.py` → `backend/app/domains/files/router.py` | HTTP 路由 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/files/schemas.py` → `backend/app/domains/files/schemas.py` | 请求和响应契约 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/files/service.py` → `backend/app/domains/files/service.py` | 领域用例 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/health/__init__.py` | 目录职责与包入口 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/app/slices/health/router.py` → `backend/app/api/health.py` | HTTP 路由 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/knowledge_base/__init__.py` → `backend/app/domains/knowledge_base/__init__.py` | 目录职责与包入口 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/knowledge_base/router.py` → `backend/app/domains/knowledge_base/router.py` | HTTP 路由 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/knowledge_base/schemas.py` → `backend/app/domains/knowledge_base/schemas.py` | 请求和响应契约 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/knowledge_base/service.py` → `backend/app/domains/knowledge_base/service.py` | 领域用例 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/qa/__init__.py` → `backend/app/domains/legal_qa/__init__.py` | 目录职责与包入口 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/qa/pipeline.py` → `backend/app/domains/legal_qa/pipeline.py` | 业务后台任务 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/qa/router.py` → `backend/app/domains/legal_qa/router.py` | HTTP 路由 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/qa/schemas.py` → `backend/app/domains/legal_qa/schemas.py` | 请求和响应契约 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/qa/service.py` → `backend/app/domains/legal_qa/service.py` | 领域用例 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/review/__init__.py` → `backend/app/domains/contract_review/__init__.py` | 目录职责与包入口 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/review/pipeline.py` → `backend/app/domains/contract_review/pipeline.py` | 业务后台任务 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/review/report.py` → `backend/app/domains/contract_review/report.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/review/router.py` → `backend/app/domains/contract_review/router.py` | HTTP 路由 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/review/schemas.py` → `backend/app/domains/contract_review/schemas.py` | 请求和响应契约 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/app/slices/review/service.py` → `backend/app/domains/contract_review/service.py` | 领域用例 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `backend/scripts/README.md` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/scripts/apply_knowledge_references.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/scripts/core_legal_corpus.json` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/scripts/import_core_legal_corpus.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/scripts/migrate_knowledge_base.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/scripts/plan_knowledge_upgrade.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/conftest.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/test_ai_service.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/test_api_contract.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/test_auth.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/test_concurrency.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/test_core_corpus.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/test_db_bootstrap.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/test_files.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/test_health.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/test_knowledge_base.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/test_knowledge_migration.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/test_models.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/test_parsing.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/test_qa.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/test_ratelimit.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/test_remote_knowledge.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/test_request_id.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `backend/tests/test_review.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `deploy/tests/test_deployment.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `knowledge_base/backend/app/auth.py` → `knowledge_base/backend/app/api/auth.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `knowledge_base/backend/app/chunking.py` → `knowledge_base/backend/app/indexing/chunking.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `knowledge_base/backend/app/db.py` → `knowledge_base/backend/app/infrastructure/database.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `knowledge_base/backend/app/embedding.py` → `knowledge_base/backend/app/infrastructure/embedding.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `knowledge_base/backend/app/jobs.py` → `knowledge_base/backend/app/indexing/jobs.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `knowledge_base/backend/app/models.py` → `knowledge_base/backend/app/knowledge_bases/models.py`、`knowledge_base/backend/app/documents/models.py`、`knowledge_base/backend/app/indexing/models.py`、`knowledge_base/backend/app/infrastructure/models.py`、`knowledge_base/backend/app/infrastructure/idempotency_models.py` | 持久化模型或模型登记 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `knowledge_base/backend/app/parsing.py` → `knowledge_base/backend/app/documents/parsing.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `knowledge_base/backend/app/retrieval.py` → `knowledge_base/backend/app/retrieval/service.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `knowledge_base/backend/app/routers.py` → `knowledge_base/backend/app/api/auth_router.py`、`knowledge_base/backend/app/api/deps.py`、`knowledge_base/backend/app/knowledge_bases/router.py`、`knowledge_base/backend/app/documents/router.py`、`knowledge_base/backend/app/indexing/router.py`、`knowledge_base/backend/app/retrieval/router.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `knowledge_base/backend/app/schemas.py` → `knowledge_base/backend/app/api/responses.py`、`knowledge_base/backend/app/api/auth_schemas.py`、`knowledge_base/backend/app/knowledge_bases/schemas.py`、`knowledge_base/backend/app/documents/schemas.py`、`knowledge_base/backend/app/indexing/schemas.py`、`knowledge_base/backend/app/retrieval/schemas.py` | 请求和响应契约 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `knowledge_base/backend/app/service.py` → `knowledge_base/backend/app/knowledge_bases/service.py`、`knowledge_base/backend/app/documents/service.py`、`knowledge_base/backend/app/documents/imports.py`、`knowledge_base/backend/app/indexing/service.py`、`knowledge_base/backend/app/infrastructure/idempotency.py`、`knowledge_base/backend/app/infrastructure/storage.py` | 领域用例 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `knowledge_base/backend/app/vector.py` → `knowledge_base/backend/app/infrastructure/vector_store.py` | 应用实现 | 迁移 | 已完成 | 目标文件已核对，应用通过静态及 Demo 检查 |
| `knowledge_base/backend/scripts/probe_integrations.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `knowledge_base/backend/tests/__init__.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `knowledge_base/backend/tests/conftest.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `knowledge_base/backend/tests/test_api.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `knowledge_base/backend/tests/test_jobs.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `knowledge_base/backend/tests/test_processing.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `knowledge_base/backend/tests/test_vector.py` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `knowledge_base/frontend/tests/api.test.mjs` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `knowledge_base/frontend/tests/security.test.mjs` | 旧测试、脚本或样例 | 退役 | 已完成 | 旧路径已清理，原件可从 Git 追溯 |
| `AGENTS.md` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `CONTEXT.md` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `README.md` | 工程入口与运行说明 | 更新 | 已完成 | 路径和使用入口已核对 |
| `backend/.env.example` | 环境配置示例 | 更新 | 已完成 | 路径和使用入口已核对 |
| `backend/Dockerfile` | 后端镜像构建 | 更新 | 已完成 | 构建输入已核对，镜像构建未验证 |
| `backend/README.md` | 工程入口与运行说明 | 更新 | 已完成 | 路径和使用入口已核对 |
| `backend/app/api/__init__.py` | 目录职责与包入口 | 更新 | 已完成 | 静态检查与所属后端 Demo 通过 |
| `backend/app/api/deps.py` | 应用实现 | 更新 | 已完成 | 静态检查与所属后端 Demo 通过 |
| `backend/app/api/ratelimit.py` | 应用实现 | 更新 | 已完成 | 静态检查与所属后端 Demo 通过 |
| `backend/app/core/idempotency.py` | 应用实现 | 更新 | 已完成 | 静态检查与所属后端 Demo 通过 |
| `backend/app/domains/__init__.py` | 目录职责与包入口 | 新增 | 已完成 | 静态检查与所属后端 Demo 通过 |
| `backend/app/domains/contracts/__init__.py` | 目录职责与包入口 | 新增 | 已完成 | 静态检查与所属后端 Demo 通过 |
| `backend/app/domains/contracts/service.py` | 领域用例 | 新增 | 已完成 | 静态检查与所属后端 Demo 通过 |
| `backend/app/domains/contracts/text_extraction.py` | 应用实现 | 新增 | 已完成 | 静态检查与所属后端 Demo 通过 |
| `backend/app/main.py` | 应用和路由入口 | 更新 | 已完成 | 静态检查与所属后端 Demo 通过 |
| `backend/pyproject.toml` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `backend/pyrightconfig.json` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `backend/uv.lock` | 锁定后端依赖 | 更新 | 已完成 | 路径和使用入口已核对 |
| `deploy/.env.example` | 环境配置示例 | 更新 | 已完成 | 路径和使用入口已核对 |
| `deploy/README.md` | 工程入口与运行说明 | 更新 | 已完成 | 路径和使用入口已核对 |
| `deploy/docker-compose.prod.yml` | 工程配置或文档 | 更新 | 已完成 | Compose 配置解析通过，容器运行未验证 |
| `docs/02-技术栈.md` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `docs/03-概要设计.md` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `docs/04-数据库设计.md` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `docs/05-接口设计.md` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `docs/06-MVP演示指南.md` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `docs/08-AI-Service架构与代码审查.md` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `docs/09-Agent基础设施平台设计建议.md` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `docs/FILE_MAP.md` | 施工清单 | 新增 | 已完成 | 路径和使用入口已核对 |
| `docs/assets/fig-architecture.mmd` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `docs/assets/fig-architecture.png` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `docs/assets/fig-architecture.svg` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `knowledge_base/README.md` | 工程入口与运行说明 | 更新 | 已完成 | 路径和使用入口已核对 |
| `knowledge_base/backend/Dockerfile` | 后端镜像构建 | 更新 | 已完成 | 构建输入已核对，镜像构建未验证 |
| `knowledge_base/backend/app/api/__init__.py` | 目录职责与包入口 | 新增 | 已完成 | 静态检查与所属后端 Demo 通过 |
| `knowledge_base/backend/app/documents/__init__.py` | 目录职责与包入口 | 新增 | 已完成 | 静态检查与所属后端 Demo 通过 |
| `knowledge_base/backend/app/indexing/__init__.py` | 目录职责与包入口 | 新增 | 已完成 | 静态检查与所属后端 Demo 通过 |
| `knowledge_base/backend/app/infrastructure/__init__.py` | 目录职责与包入口 | 新增 | 已完成 | 静态检查与所属后端 Demo 通过 |
| `knowledge_base/backend/app/knowledge_bases/__init__.py` | 目录职责与包入口 | 新增 | 已完成 | 静态检查与所属后端 Demo 通过 |
| `knowledge_base/backend/app/lifespan.py` | 应用资源生命周期 | 新增 | 已完成 | 静态检查与所属后端 Demo 通过 |
| `knowledge_base/backend/app/main.py` | 应用和路由入口 | 更新 | 已完成 | 静态检查与所属后端 Demo 通过 |
| `knowledge_base/backend/app/retrieval/__init__.py` | 目录职责与包入口 | 新增 | 已完成 | 静态检查与所属后端 Demo 通过 |
| `knowledge_base/backend/pyproject.toml` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `knowledge_base/backend/pyrightconfig.json` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `knowledge_base/backend/uv.lock` | 锁定后端依赖 | 更新 | 已完成 | 路径和使用入口已核对 |
| `knowledge_base/frontend/README.md` | 工程入口与运行说明 | 更新 | 已完成 | 路径和使用入口已核对 |
| `knowledge_base/frontend/package.json` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `law-wiz.code-workspace` | 工程配置或文档 | 更新 | 已完成 | 路径和使用入口已核对 |
| `frontend/src/`、`knowledge_base/frontend/src/`、`deploy/mysql-init/` | 前端源码和空库账号初始化 | 不变更 | 已完成 | 沿用原前端源码与 MySQL 初始化入口 |
| `backend/.vscode/settings.json`、`knowledge_base/backend/.vscode/settings.json` | 本地编辑器设置 | 更新 | 已完成 | 路径和使用入口已核对 |
