# 智法宝后端（law-wiz backend）

FastAPI 后端，承载一期（M1 用户管理、M2 合同智能审查、M3 法律 AI 问答）。

## 快速开始

```powershell
# 1) 建虚拟环境 —— ⚠️ 必须用标准解释器的【绝对路径】，理由见下
uv venv --python "C:\Users\<你>\AppData\Local\Python\pythoncore-3.14-64\python.exe"

# 2) 安装依赖
uv sync --extra dev

# 3) 配置
Copy-Item .env.example .env    # 按需修改
```

> **当前 `app/` 下只有空目录**：`main.py`、数据库迁移（`alembic/`）、部署编排都还没写。
> 因此「起依赖 → 建表 → 启动」这三步要等第一份实现落地时才能跑通，命令届时补回本文。

启动后：

| 地址 | 用途 |
| --- | --- |
| http://127.0.0.1:8000/docs | Swagger UI（**契约的唯一真源**，由代码生成） |
| http://127.0.0.1:8000/openapi.json | OpenAPI 描述，导入 Apifox 用 |
| http://127.0.0.1:8000/api/v1/health | 健康检查（含运行环境自查） |

## ⚠️ 建环境时为什么必须写解释器的绝对路径

实测：**`uv venv --python 3.14` 会选中 free-threaded 解释器**（它满足版本约束但无 GIL）。
在该环境下 `chromadb` 无法安装 —— 解析器会退回 2023 年的 `chromadb 0.3.23`，
随后其传递依赖 `tokenizers` 需从源码编译并拉取 Rust 工具链，安装中途失败。
**报错指向 Rust，与 Python 毫无关系，极难定位。**

**因此建环境时必须写绝对路径**（上面第 1 步）。原实现还有第二道防线：
`app/preflight.py` 在导入任何模块前检查 `Py_GIL_DISABLED`，不通过则拒绝启动，
且该检查在 `app/__init__.py` 中执行，任何入口都绕不过。骨架阶段这道防线尚未恢复，
写入口代码时应当一并补回。

完整实验数据与被否决的方案见 [`docs/adr/0009-python-version-and-free-threading.md`](../docs/adr/0009-python-version-and-free-threading.md)。

## 目录结构

```
app/
├── __init__.py        包标记（原实现的运行环境预检在此执行，见上文）
├── main.py            应用入口：配置校验 → 中间件 → 异常处理器 → 路由
├── core/              框架级原语：配置、错误码与响应体、密码与令牌
├── api/               横切依赖：request_id、当前用户、数据库会话
├── infra/             外部世界接入：数据库、Redis
├── models/            全部 ORM 模型（集中，保证 Alembic 不漏表）
└── slices/            功能纵切面，每个含 schemas / service / router
```

> 以上是**目标结构**，当前仓库里只有空目录。切片划分由团队认领时决定，
> 见 [`app/slices/README.md`](app/slices/README.md)。

**为什么按纵切面而不是 `models/ services/ api/`**：本项目的分工是「一人负责一条端到端
链路」（ADR-0001）。技术分层会让每个功能改动横跨三个目录，PR 冲突面大；
纵切面分目录让一个人的改动集中在自己目录内，模块边界在文件系统上一眼可见。
详见 [`app/slices/README.md`](app/slices/README.md)。

## 三条硬性约束（做错会导致返工或事故）

### 1. ⛔ 不得引入 `paddlepaddle`、`torch`、`paddleocr`

服务器可用内存约 950 MiB，而本地 OCR 运行时需 1.2–2 GB。一旦引入，
容器启动即被 OOM Killer 静默杀掉，表现为"容器启动后无故退出"，排查成本极高。
**一期 OCR 走云端 API**。

### 2. ⛔ 唯一索引不得包含 `deleted_at`

MySQL 的唯一索引**不约束 `NULL`**。`uk(phone, deleted_at)` 里，
`deleted_at IS NULL` 的那些行**完全不受唯一性保护**，同一手机号可插入任意多行 ——
唯一性约束等于不存在。实测证据见 [ADR-0007](../docs/adr/0007-soft-delete-scope.md)。

**只有需要保留历史的表用软删除**（`contract`、`review_task`、`kb_document`、
`qa_session`、`file_object`）；**`user` 表硬删除**（《个人信息保护法》下注销时
保留手机号与邮箱是隐私风险）。

### 3. ⛔ 同一个外部能力只在一处封装

大模型、OCR、向量存储、对象存储、签章、时间戳、区块链七类能力，每一类**只允许有
一处封装**，其它地方复用它。业务代码里散落同一个厂商 SDK 的调用，会让将来真要替换时
无处下手。**一期不建 Provider 接口体系** —— 接口形状要由第二个实现来决定，不靠猜
（见 [ADR-0012](../docs/adr/0012-defer-capability-abstraction.md)）。

## 契约变更流程

`app/slices/*/schemas.py` 中的 Pydantic 模型**就是接口契约本身**，
`/openapi.json` 由它们自动生成。

**改字段名 = 改契约**，必须：

1. 同步修改 [`docs/05-接口设计.md`](../docs/05-接口设计.md)；
2. 在 PR 描述中说明影响范围（哪些前端 / 客户端受影响）；
3. 知会被影响的人。

契约冻结后**只允许新增可选字段与新增接口**，不得删除字段、不得改变类型或语义
（见 05-接口设计 §4.4）。

## 依赖分组

| 组 | 内容 | 何时需要 |
| --- | --- | --- |
| 默认 | Web 框架、ORM、Redis、密码学、文件解析、HTTP | 总是 |
| `--extra vector` | `chromadb` | M2/M3 的 AI 底座需要真实向量检索时 |
| `--extra dev` | pytest、ruff | 开发与测试 |

`chromadb` **单独成组**的理由：它是唯一体积较大且带原生扩展的依赖，
且只在 RAG 链路需要。默认装它会让"只想改认证接口"的人也被拖慢。

## 测试

```powershell
uv run pytest              # 全部
uv run pytest -k auth      # 只跑认证
uv run ruff check .        # 静态检查
```
