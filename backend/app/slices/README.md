# 纵切面（slices）

目录按**纵切面**而非技术分层组织，与 [ADR-0001](../../docs/adr/0001-monorepo-and-vertical-slice-collaboration.md) 的分工模型一致：
每个切片自带 `schemas.py` / `service.py` / `router.py`，可由一人端到端负责。

公共部分只在 `app/core/`（配置、错误、安全原语）与 `app/infra/`（外部世界接入）。

| 切片 | 模块 | 分期 | 把关人 |
| --- | --- | --- | --- |
| `auth` | M1 用户管理 | **P1** | A（基座与数据层） |
| `files` | M2 文件接入与文本化 | **P1** | B（M2 主干） |
| `review` | M2 合同智能审查 | **P1** | B |
| `knowledge` | M3 法律知识库 | **P1** | C（AI 底座与 M3） |
| `qa` | M3 法律 AI 问答 | **P1** | C |

## 为什么按纵切面分目录，而不是 `models/ services/ api/`

技术分层（`models/`、`services/`、`api/`）会让**每一个功能改动都要横跨三个目录**，
而本项目的分工是「一人负责一条端到端链路」。纵切面分目录使：

- 一个人的改动**集中在自己的目录内**，PR 冲突面小；
- 模块边界在文件系统上一眼可见，评审时"有没有越界"可直接判断；
- 每个切片可独立测试，服务层不依赖 HTTP，能被脚本与后台任务直接调用。

**跨切片的共享代码必须有明确归属**：要么进 `app/core/`（框架级原语），
要么进 `app/infra/`（外部世界接入），要么进 `app/models/`（ORM 模型）。
**不允许两个切片互相 import 对方的 `service.py`** —— 需要协作时经接口或事件。

## 为什么 ORM 模型集中在 `app/models/` 而不放在各切片内

Alembic 的 `--autogenerate` 依赖 `Base.metadata` 中已注册的全部表。
模型分散在各切片时，任何一处漏导入都会导致**迁移脚本静默缺表** ——
这类问题要到生产建库时才发现。集中在一处、由 `app/models/__init__.py` 统一导出，
是更稳的做法。

## 新增一个切片的步骤

1. 建目录 `app/slices/<name>/`，含 `__init__.py`、`schemas.py`、`service.py`、`router.py`；
2. 在 `app/models/` 下加模型，并在 `app/models/__init__.py` 的导入与 `__all__` 中登记；
3. 在 `app/main.py` 的 `register_routers()` 中挂载路由；
4. 在上表补一行（切片、模块、分期、把关人）。
