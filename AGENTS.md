# AGENTS.md — 智法宝（law-wiz）

面向在本仓库工作的 AI 代理与协作者的约定。**只写对未来任务有用的信息**：
操作历史、已关闭的 Issue 编号、临时绕过手段属于 commit message，不属于本文件。

> **当前状态**：仓库只有目录骨架、设计文档与依赖声明，**实现代码尚未编写**。
> 下文命令中依赖实现的部分（启动、测试、迁移），要等对应代码落地后才能跑通。

## 仓库布局

monorepo，四个顶层目录各司其职：

| 目录 | 内容 |
| --- | --- |
| `backend/` | FastAPI（Python 3.14）。`app/` 按**功能纵切面**组织，不按技术分层 |
| `frontend/` | Vue 3 + Element Plus + Vite 单页应用 |
| `deploy/` | 部署编排与说明（编排文件待编写） |
| `docs/` | 设计文档 01–05、`adr/`、`assets/`（插图的 Mermaid 单一真源） |
| `tools/` | 一次性脚本与渲染工具 |

`backend/app/` 的分层：`core/`（配置、错误码、响应体、密码与令牌）、`api/`（横切依赖与中间件）、
`infra/`（数据库、Redis）、`models/`（15 张表的 ORM，**集中登记**以保证 Alembic 不漏表）、
`slices/`（纵切面，每个含 `schemas.py` / `service.py` / `router.py`）。

新增切片的步骤见 `backend/app/slices/README.md`。**跨切片共享代码只能进 `core/` / `infra/` / `models/`**，
不允许两个切片互相 import 对方的 `service.py`。

## 常用命令

**后端** —— `--extra dev` 不可省：`ruff` 与 `pytest` 都在该 extra 里，漏掉会得到 `program not found`。

```bash
cd backend
uv sync --extra dev                        # 锁文件已入库；加 --frozen 可校验它没被改脏
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev pytest
uv run uvicorn app.main:app --reload --port 8000
```

**前端**

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm dev                                   # http://localhost:5173，/api 已代理到 127.0.0.1:8000
pnpm run lint
pnpm run format:check
pnpm run build                              # = vue-tsc --noEmit && vite build
```

## 硬性约束

违反以下任一条，通常以**难以定位**的方式失败，而非直接报错：

- **Python 必须是 3.14 标准构建**。free-threaded（含 `3.14t`）不可用 —— `uv venv --python 3.14`
  会选中它，而它装不上 `chromadb`，报错却指向 Rust。建环境时写解释器的绝对路径；
  另建议在 `app/__init__.py` 里做 `Py_GIL_DISABLED` 预检。见 ADR-0009。
- **后端依赖不得出现 `paddlepaddle` / `torch` / `paddleocr`**。本地 OCR 需 1.2–2 GB 内存，
  容器会被 OOM Killer 静默杀掉，表现为"启动后无故退出"。OCR 走云端 API。
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
- **命令要在各自目录下执行**：`uv` 命令在 `backend/`，`pnpm` 命令在 `frontend/`。
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
