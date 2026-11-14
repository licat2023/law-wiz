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

## 当前任务：目录与文档清理

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
