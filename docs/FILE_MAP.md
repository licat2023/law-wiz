# 项目目录说明

记录仓库当前目录及主要文件的职责。

## 目录职责

| 目录 | 职责 |
| --- | --- |
| `backend/app/domains/auth/`、`backend/app/domains/files/` | 用户、登录、令牌及文件上传与读取 |
| `backend/app/domains/contracts/` | 合同版本与该版本的正文 |
| `backend/app/domains/contract_review/` | 审查任务、风险规则和报告 |
| `backend/app/domains/legal_qa/` | 普通问答、审查报告追问和引用快照 |
| `backend/app/api/`、`backend/app/core/` | HTTP 入口与应用公共契约 |
| `backend/app/infrastructure/` | 数据库、存储、缓存、AI 服务与知识库连接 |
| `ai-service/ai_service/` | AI 服务入口、模型接入、法条引用检索、审查及问答工作流 |
| `ai-service/tests/` | 内部推理接口与引用行为验证 |
| `backend-java/` | 默认 Spring Boot 业务后端、MyBatis 映射、RustFS 访问和迁移命令 |
| `backend-java/src/main/java/com/lawwiz/business/qa/` | 问答会话、回答与引文持久化，以及 `QaAnswerStream.java` 的生成中正文发布 |
| `knowledge_base/backend/app/knowledge_bases/` | 库设置与访问范围 |
| `knowledge_base/backend/app/documents/` | 文档、原文件、修订、解析与导入 |
| `knowledge_base/backend/app/indexing/` | 切分、嵌入、关键词倒排、处理任务与索引发布 |
| `knowledge_base/backend/app/retrieval/` | 从生效索引召回候选，融合、重排并组装来源 |
| `frontend/`、`knowledge_base/frontend/` | 业务界面与知识库管理界面 |
| `frontend/src/components/` | 业务前端共用组件 |
| 两个前端目录的 `Dockerfile`、`nginx.conf` | Vite 开发镜像、生产静态站点镜像及同源 API 代理 |
| `deploy/` | 开发和生产全栈编排、环境样例、数据库账号初始化和站点部署说明 |
| `deploy/mysql-init/` | 基于 MySQL 9.7 的初始化镜像，内置业务表结构及知识库账号脚本 |
| `deploy/migrations/` | 已有业务数据库的升级 SQL |
| `docs/`、`docs/adr/` | 需求、设计、接口和架构决策 |
| `docs/assets/`、`tools/` | 文档插图、图源与渲染脚本 |
| `tools/legal-corpus/` | 公开法规采集、Docling 转换和知识库写入命令 |
| `docs/tasks/` | 可恢复任务的总索引、实施记录及对应的验收样本 |
