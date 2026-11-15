# 项目目录说明

记录仓库当前目录及主要文件的职责。

## 目录职责

| 目录 | 职责 |
| --- | --- |
| `backend/app/domains/auth/`、`backend/app/domains/files/` | 用户、登录、令牌及文件上传与读取 |
| `backend/app/domains/contracts/` | 合同版本与该版本的正文 |
| `backend/app/domains/contract_review/` | 审查任务、风险规则、Agent 和报告 |
| `backend/app/domains/legal_qa/` | 普通问答、审查报告追问、Agent 和引用快照 |
| `backend/app/api/`、`backend/app/core/` | HTTP 入口与应用公共契约 |
| `backend/app/infrastructure/` | 数据库、存储、缓存、模型与知识库连接 |
| `knowledge_base/backend/app/knowledge_bases/` | 库设置与访问范围 |
| `knowledge_base/backend/app/documents/` | 文档、原文件、修订、解析与导入 |
| `knowledge_base/backend/app/indexing/` | 切分、嵌入、关键词倒排、处理任务与索引发布 |
| `knowledge_base/backend/app/retrieval/` | 从生效索引召回候选，融合、重排并组装来源 |
| `frontend/`、`knowledge_base/frontend/` | 业务界面与知识库管理界面 |
| `deploy/` | 两个后端、数据库与缓存的部署编排 |
| `docs/`、`docs/adr/` | 需求、设计、接口和架构决策 |
| `docs/assets/`、`tools/` | 文档插图、图源与渲染脚本 |
| `tools/legal-corpus/` | 公开法规采集、Docling 转换和知识库写入命令 |
| `docs/tasks/` | 可恢复任务的总索引和实施记录 |
