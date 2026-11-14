# 项目目录与施工清单

记录当前目录职责、清理范围和验收结果。重构或跨目录修改时，在这里更新相关路径及验证状态。

## 目录职责

| 目录 | 职责 |
| --- | --- |
| `backend/app/domains/auth/`、`backend/app/domains/files/` | 用户、登录、令牌及文件上传与读取 |
| `backend/app/domains/contracts/` | 合同版本与该版本的正文 |
| `backend/app/domains/contract_review/` | 审查任务、风险规则、Agent 和报告 |
| `backend/app/domains/legal_qa/` | 问答会话、消息、Agent 和引用快照 |
| `backend/app/api/`、`backend/app/core/` | HTTP 入口与应用公共契约 |
| `backend/app/infrastructure/` | 数据库、存储、缓存、模型与知识库连接 |
| `knowledge_base/backend/app/knowledge_bases/` | 库设置与访问范围 |
| `knowledge_base/backend/app/documents/` | 文档、原文件、修订、解析与导入 |
| `knowledge_base/backend/app/indexing/` | 切分、嵌入、处理任务与索引发布 |
| `knowledge_base/backend/app/retrieval/` | 查询生效索引并组装来源 |
| `frontend/`、`knowledge_base/frontend/` | 业务界面与知识库管理界面 |
| `deploy/` | 两个后端、数据库与缓存的部署编排 |
| `docs/`、`docs/adr/` | 需求、设计、接口和架构决策 |
| `docs/assets/`、`tools/` | 文档插图、图源与渲染脚本 |

## 当前任务：代码注释审查

按已跟踪的手写源码和配置检查文件职责、公开契约及关键约束。保留运行行为和生成的接口契约。先清点缺口，再补写或修正，最终在干净源码副本核对语法、接口描述和构建结果。

| 分工 | 负责人 | 验收标准 |
| --- | --- | --- |
| A 业务后端 | 业务后端协作者 | 公共接口、事务和兼容语义与实现相符，Python 语法及接口契约检查通过 |
| B 知识库后端 | 知识库后端协作者 | 文档、索引、检索和客户端契约与实现相符，Python 语法及接口契约检查通过 |
| C 两个前端 | 前端协作者 | 应用入口、可复用接口及关键状态边界有说明，lint 和构建通过 |
| D 部署、脚本和交付 | 主 agent | 配置与脚本解析通过，实际差异仅含本任务的注释和施工记录 |

下表内以花括号表示同一目录下的多个文件，分工栏同时标明唯一修改负责人。

| 路径 | 职责 | 变更 | 分工 | 状态 | 验证要求或结果 |
| --- | --- | --- | --- | --- | --- |
| `backend/app/api/{deps,exception_handlers,health,middleware,ratelimit}.py`、`backend/app/{config,main}.py`、`backend/app/core/{citations,errors,idempotency}.py` | HTTP 依赖、应用装配与公共契约 | 修改注释 | A | 已完成 | Ruff 通过，Python 语法树排除文档字符串后相同，OpenAPI 逐字节一致 |
| `backend/app/domains/auth/{router,schemas,security,service}.py`、`backend/app/domains/files/{formats,models,router,service}.py` | 账号、令牌与文件生命周期 | 修改注释 | A | 已完成 | Ruff 通过，Python 语法树排除文档字符串后相同，OpenAPI 逐字节一致 |
| `backend/app/domains/contracts/{models,service}.py`、`backend/app/domains/contract_review/{models,pipeline,risk_rules,router,rule_models,schemas,service}.py`、`backend/app/domains/contract_review/agent/{agent,graph,nodes,schemas,state}.py` | 合同版本、审查任务、规则与 Agent | 修改注释 | A | 已完成 | Ruff 通过，Python 语法树排除文档字符串后相同，OpenAPI 逐字节一致 |
| `backend/app/domains/legal_qa/{models,pipeline,router,service}.py`、`backend/app/domains/legal_qa/agent/{agent,graph,nodes,schemas,state}.py`、`backend/app/domains/knowledge_base/{router,schemas,service}.py` | 问答、引用与知识库代理 | 修改注释 | A | 已完成 | Ruff 通过，Python 语法树排除文档字符串后相同，OpenAPI 逐字节一致 |
| `backend/app/infrastructure/database/{base,bootstrap}.py`、`backend/app/infrastructure/{cache,knowledge_base,llm,storage}.py`、`backend/Dockerfile` | 数据库、外部客户端、文件存储与业务镜像 | 修改注释 | A | 已完成 | Ruff 通过，Python 语法树排除文档字符串后相同，OpenAPI 逐字节一致 |
| `knowledge_base/backend/app/api/{auth,auth_router,auth_schemas,deps,responses}.py`、`knowledge_base/backend/app/{config,errors,lifespan,main}.py`、`knowledge_base/backend/.env.example` | 鉴权、配置与服务入口 | 修改注释 | B | 已完成 | Ruff 通过，Python 语法树排除文档字符串后相同，OpenAPI 逐字节一致 |
| `knowledge_base/backend/app/documents/{imports,models,parsing,router,schemas,service}.py`、`knowledge_base/backend/app/indexing/{chunking,jobs,models,router,schemas,service}.py` | 文档处理、切分和索引发布 | 修改注释 | B | 已完成 | Ruff 通过，Python 语法树排除文档字符串后相同，OpenAPI 逐字节一致 |
| `knowledge_base/backend/app/infrastructure/{database,embedding,idempotency,idempotency_models,storage,vector_store}.py`、`knowledge_base/backend/app/knowledge_bases/{models,router,schemas,service}.py`、`knowledge_base/backend/app/retrieval/{router,schemas,service}.py` | 数据与向量存储、库权限、查询和引用 | 修改注释 | B | 已完成 | Ruff 通过，Python 语法树排除文档字符串后相同，OpenAPI 逐字节一致 |
| `frontend/src/{App.vue,env.d.ts,main.ts}`、`frontend/src/api/{auth,client,qa,review,types}.ts`、`frontend/src/router/index.ts`、`frontend/src/stores/auth.ts`、`frontend/src/styles/main.css`、`frontend/src/views/{LoginView,NotFoundView,RegisterView,ReviewDetailView,ReviewView}.vue`、`frontend/vite.config.ts` | 业务界面、会话、API 客户端和审查工作流 | 修改注释 | C | 已完成 | 两套前端 lint 和构建通过，移除注释后脚本、模板和样式一致 |
| `knowledge_base/frontend/{eslint.config.js,pnpm-workspace.yaml,vite.config.ts}`、`knowledge_base/frontend/src/{App.vue,api.ts,feedback.ts,main.ts,markdown.ts,polling.ts,style.css,types.ts}` | 管理端入口、传输、渲染和轮询 | 修改注释 | C | 已完成 | 两套前端 lint 和构建通过，移除注释后脚本、模板和样式一致 |
| `knowledge_base/frontend/src/components/{IndexSettings,SafeMarkdown}.vue`、`knowledge_base/frontend/src/views/{BasesView,DocumentView,LoginView,WorkspaceView}.vue` | 库、文档、索引和管理员界面 | 修改注释 | C | 已完成 | 两套前端 lint 和构建通过，移除注释后脚本、模板和样式一致 |
| `frontend/{index.html,.prettierignore}`、`knowledge_base/frontend/{index.html,.prettierignore}`、`knowledge_base/backend/{.dockerignore,pyproject.toml}` | 静态入口、生成文件排除规则和知识库依赖 | 修改注释 | D | 已完成 | 两套前端构建通过，HTML 去除注释后及配置解析结果一致 |
| `.gitattributes`、`.gitignore`、`backend/.env.example`、`knowledge_base/backend/Dockerfile`、`deploy/docker-compose.{dev,prod}.yml`、`deploy/mysql-init/20-knowledge-base.sh` | 文件规则、镜像和部署初始化 | 修改注释 | D | 已完成 | 排除规则与配置有效内容一致，开发和生产 Compose 解析及 Shell 语法通过 |
| `tools/render-mmd.mjs` | 以无头浏览器渲染图源 | 修改注释 | D | 已完成 | Node 语法和 SVG、PNG 实际渲染通过，单独暂存两条新增注释 |
| `docs/FILE_MAP.md` | 维护目录职责与任务进度 | 更新 | D | 已完成 | 清单展开路径与本次 135 个文件的差异一致 |

## 已完成任务：目录与文档清理

| 路径 | 职责 | 变更 | 状态 | 验证要求或结果 |
| --- | --- | --- | --- | --- |
| `docs/08-AI-Service架构与代码审查.md`、`docs/09-Agent基础设施平台设计建议.md` | 独立 AI 服务的旧审查与平台设想 | 移除 | 已完成 | 现行文档链接通过检查，原文可从 Git 历史查阅 |
| `README.md` | 项目与文档入口 | 更新 | 已完成 | 文档索引和本地链接通过检查 |
| `docs/assets/README.md` | 插图与渲染说明 | 更新 | 已完成 | 图源、引用及渲染脚本已核对 |
| `docs/FILE_MAP.md` | 目录职责与施工清单 | 更新 | 已完成 | 保留现行路径和重构验收限制 |
| `docs/export/对照报告-本地工作区-vs-上游.md` | 旧工作区与上游的本地对照快照 | 清理本地产物 | 已完成 | 快照基线已过期，已移入回收站 |
| 根目录及两个后端的 `.ruff_cache/`、两个后端的 `.pytest_cache/` 与 `app/` 下的 `__pycache__/` | 可再生的静态检查和 Python 缓存 | 清理本地产物 | 已完成 | 已移入回收站并确认原路径清空 |
| `frontend/dist/`、`knowledge_base/frontend/dist/` | 可再生的前端构建输出 | 清理本地产物 | 已完成 | 构建入口已核对，产物已移入回收站 |
| `knowledge_base/backend/pytest-of-licat/` | 旧自动化测试临时数据库 | 清理本地产物 | 已完成 | 目录只含测试数据库文件，已移入回收站 |

## 已完成重构的验证范围

业务后端内运行审查和问答 Agent，知识库独立部署。迁移明细见 Git 提交 `b9ae5f6`，其中记录了旧路径及验收明细。

重构当时在干净源码副本验证了依赖安装、两个后端的静态检查、两个前端的 lint 和构建。业务和知识库使用 SQLite 空库做 Demo 检查，知识库在实际 Chroma 上验证入库、索引与检索。Docker Compose 配置已解析，容器启动及真实 MySQL、Redis、远程模型与远程嵌入联调仍待验证。
