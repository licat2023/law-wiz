# AGENTS.md — 智法宝（law-wiz）

面向在本仓库工作的 AI 代理与协作者的约定。**只写对未来任务有用的信息**：
操作历史、已关闭的 Issue 编号、临时绕过手段属于 commit message，不属于本文件。

业务 FastAPI 负责用户、文件、审查和问答状态。独立 AI 服务运行两个 Agent，通过只读凭据访问知识库。知识库独立持有文档、索引和 Chroma。

开始、恢复或接手需要施工记录的工作前，先读 [任务总索引](docs/tasks/README.md)。已有对应任务时再读主文档，核对有效需求、当前理解、状态、负责人、依赖和已有改动。文件范围、施工进度和验证记录维护在 [任务目录](docs/tasks/) 对应主文档中。

[目录说明](docs/FILE_MAP.md) 记录实际目录和文件职责。目录结构或职责变化时同步更新。

## 仓库布局

| 目录 | 职责 |
| --- | --- |
| `backend/` | 业务 FastAPI，`app/domains/` 按领域组织 |
| `ai-service/` | 独立推理服务，运行合同审查与法律问答 Agent |
| `frontend/` | 智法宝用户界面 |
| `knowledge_base/backend/` | 知识库 FastAPI、文档入库、索引和检索 |
| `knowledge_base/frontend/` | 知识库管理界面 |
| `deploy/` | 部署编排与数据库账号初始化 |
| `docs/` | 设计、接口、架构决策和任务记录 |
| `tools/` | 语料和文档辅助工具 |

`contracts/` 管合同版本和正文，`contract_review/` 管审查任务、规则和报告。业务后端通过内部 HTTP 发送结构化输入并持久化结果。新增业务 ORM 模型须登记到 `app/infrastructure/database/models.py`。知识库模型登记在 `app/infrastructure/models.py`。

业务后端通过统一 HTTP 客户端访问知识库。知识库解析入库文件、切分并发布索引，业务后端本地提取审查合同的正文。知识库生产嵌入使用远程服务，内嵌 Chroma 由单 worker 持有。

## 常用命令

各后端执行 `uv sync --frozen --extra dev`、`uv run --extra dev ruff check app` 和 `uv run --extra dev ruff format --check app`。各前端执行 `pnpm install --frozen-lockfile`、`pnpm run lint` 和 `pnpm run build`。

开发和生产启动、空库初始化及站点配置见 [部署说明](deploy/README.md)。构建两个站点时保持相对 `/api`，各前端容器连接自己的后端。通过 [Demo 指南](docs/06-MVP演示指南.md) 核对入库、审查报告与问答引用。

从公开栏目采集法规、用 Docling 转换和修订入库时，见 [法规语料工具](tools/legal-corpus/README.md)。

## 硬性约束

违反以下任一条，通常以**难以定位**的方式失败，而非直接报错：

- **Python 必须是 3.14 标准构建**。free-threaded（含 `3.14t`）不可用 —— `uv venv --python 3.14`
  会选中它，而它装不上 `chromadb`，报错却指向 Rust。建环境时写解释器的绝对路径；
  另建议在 `app/__init__.py` 里做 `Py_GIL_DISABLED` 预检。见 ADR-0009。
- **后端依赖不得出现 `paddlepaddle` / `torch` / `paddleocr`**。本地 OCR 需 1.2–2 GB 内存，
  容器会被 OOM Killer 静默杀掉，表现为"启动后无故退出"。当前不实现 OCR；后续接入只考虑云端 API。
- **每个容器必须设 `mem_limit`**。部署主机内存极紧且已承载其它服务，不设上限会连带拖垮同机应用。
- **MySQL 固定 `mysql:9.7`，不用 `latest`**。见 ADR-0008。
- **`.gitignore` 里 `models/` 必须保持锚定为 `/models/`**。写成不带斜杠的 `models/` 会连带忽略
  `backend/app/models/`，使克隆下来的仓库缺少整个数据层。见下方"验证纪律"。
- **唯一索引不得包含 `deleted_at`**：MySQL 唯一索引不约束 `NULL`。见 ADR-0007。
- **接口中的 ID 一律按字符串处理**，前端不得参与算术（后端为 BIGINT UNSIGNED，超出 JS 安全整数范围）。
- **按响应体的 `code` 判断成败**，不依赖 HTTP 状态码。
- **AI 相关接口必须带 `Idempotency-Key`**（`POST /reviews`、`POST /qa/sessions/{id}/messages`）。
- **同一个外部能力只在一处封装**，其它地方复用该封装。一期**不建 Provider 接口体系**
  （ADR-0012）—— 业务代码里不要出现同一个厂商 SDK 的分散调用，那会让将来真要替换时无处下手。
- **数据库访问一律走异步栈**：`AsyncSession` + aiomysql（`infrastructure/database/session.py`），
  路由 / 服务 / 流水线统一 `await`；**不要**引入同步 `Session`、`create_engine` 或 pymysql 驱动
  —— 异步上下文里用同步会话会抛 `MissingGreenlet`，同步驱动会阻塞事件循环。Redis 同理，用 `redis.asyncio`。
- **不要访问 ORM 关系属性**（`task.report`、`session.messages` 之类）：异步会话下它会触发
  隐式 IO 抛 `MissingGreenlet`，改用显式 `select(...)` 查询。
- **时间戳列必须同时给 Python 侧取值**（`default=` / `onupdate=`，见 `infrastructure/database/base.py`）：
  MySQL 不支持 `INSERT ... RETURNING`，只写 `server_default` 的话，插入后读该列会触发
  隐式 SELECT —— 异步会话里同样抛 `MissingGreenlet`，而 **SQLite 测试测不出来**
  （SQLite 支持 RETURNING），只有连真实 MySQL 才暴露。实测：C-01 曾返回 50000 而 143 个用例全绿。
- **重活一律过 `asyncio.to_thread`**：bcrypt 口令哈希、PDF 解析与报告生成、向量检索、
  同步计算与外部 SDK 调用、本地磁盘读写都已移出事件循环（`domains/auth/security.py`、各领域的
  `service.py` / `pipeline.py`）。**新增这类调用时照做** —— 在 `async def` 里直接同步调用
  会占住事件循环（期间所有请求排队），而**功能测试不会发现**。

## 验证纪律

**验证必须针对全新 clone，不能只针对工作区。** 二者可以不一致：`.gitignore` 曾误忽略
`backend/app/models/`，导致"工作区 33 个测试全绿、克隆下来的仓库却缺少整个数据层"。

低成本做法：

```bash
git archive --format=tar HEAD | tar -x -C <临时目录>
# 在临时目录里跑上面的后端与前端命令
```

**注意 `git grep` 默认只搜索已跟踪文件** —— 被忽略或未跟踪的文件里的问题不会被它发现。
需要覆盖全树时改用 `Get-ChildItem -Recurse | Select-String` 并排除依赖目录。

## 协作模型

功能点 → GitHub Issue → 分支 → PR → 评审。完整规则见 ADR-0001 与 `docs/03-概要设计.md` §7。

- 每个功能点一个 Issue；标签为 `M<模块号>` + 技术域 + 类型，期数用 **Milestone**（不是标签）
- 把关人由**评审过程中的评论**确定，投票在 PR 中人工计票（把关人 2 票、其他成员各 1 票、弃权计为反对）
- 代码缺陷、安全漏洞、违反契约、跨切片直接读写对方数据表属**技术缺陷**，由把关人直接驳回，不进入投票
- 提交信息：`<类型>(<模块>): <简述>`，类型为 `feat` / `fix` / `docs` / `refactor` / `test` / `chore`

## 环境注意

- **`git push` 在本机的 TLS 配置**：全局 `~/.gitconfig` 设了 `http.sslBackend = openssl`，它在本机
  连 GitHub 会失败（`unexpected eof while reading`）。本仓库已设仓库级 `schannel` 覆盖。
  克隆到新机器后若推送失败，先检查这一项。
- **命令要在各自项目目录执行**，不要共用业务后端与知识库的 Python 环境。
- **用 `law-wiz.code-workspace` 打开工作区**：两个后端的顶层包都叫 `app`，各自使用独立的解释器和分析范围。
- 仓库可能公开：**凭据、主机地址、端口、连接方式一律不写入仓库**，理由见根 `README.md` 的「凭据纪律」。

## 文档权威来源

| 关心什么 | 看哪里 |
| --- | --- |
| 领域术语的准确定义 | `CONTEXT.md`（唯一权威） |
| 功能需求与功能点编号 | `docs/01-需求说明书.md` |
| 技术选型与资源约束 | `docs/02-技术栈.md` |
| 分层架构、分期边界、团队分工 | `docs/03-概要设计.md` |
| 表结构与字段语义 | `docs/04-数据库设计.md` |
| 接口契约与错误码 | `docs/05-接口设计.md`（接口真源是代码与 `/openapi.json`） |
| 为什么这样决策、否决了什么 | `docs/adr/` |

`docs/05` 冻结的是**形状**（字段名、类型、错误码），变更需在仓库内可见。
