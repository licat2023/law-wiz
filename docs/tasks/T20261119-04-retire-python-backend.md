# 退役 Python 业务后端并整理本地主分支

## 用户需求依据

- R1，本次聊天，用户要求“之前有一份后端迁移向SpringBoot的任务，现在在git迁出原后端备份分支后，在主分支将原后端删除，并清空相关历史记录和文档记录（除了任务留档的那些）”。
- R2，本次聊天，用户明确希望 `main` 对齐 `codex/ai-core-knowledge-base` 最新提交。已核对该提交为 `1bbd694`，包括 Spring Boot 迁移和后续业务功能。用户回复“确认对齐需求，继续推进任务”。
- R3，本次聊天，用户补充“另外快进过后codex/ai-core-knowledge-base分支标记删除，本地使用main开发”。

## 当前任务理解

将本地 `main` 从 `ef1f7e3` 快进到 `1bbd694`，在该基线上退役旧 Python 业务后端。清除本地 `main` 可达的旧后端路径和已废弃的专门历史文档，当前共享文档使用 Spring Boot 业务后端。保留 `docs/tasks/` 的实施与验收材料、独立 AI、独立知识库和已有数据升级能力。旧版代码和原始历史以本地 `codex/legacy-python-backend` 为备份。交付时本地检出 `main`，删除原开发分支的本地引用。远端发布不在本次授权范围。

## 实施方案

1. 验证备份分支的旧后端树与 `1bbd694` 相同。在独立副本清理工作区并提交。
2. 在单分支临时克隆内过滤旧路径和废弃文档，对照过滤前后的当前源码树，检查留档与部署上下文。
3. 验证完成后以比较原分支位置的方式更新本地 `main`，切换当前工作区，将旧目录中 Git 忽略的本机文件移至 `.data/legacy-python-backend-1bbd694/`，删除已备份的原开发分支。核对提交、留档和工作区状态。

## 分工与施工清单

主 agent 负责全部路径、验证与本地分支操作。

| 路径 | 职责 | 变更 | 状态 | 验证要求 |
| --- | --- | --- | --- | --- |
| `backend/` | 旧 Python 业务后端 | 移除目录和主分支路径历史 | 已完成 | 备份文件树一致，主分支路径不可达 |
| `backend/scripts/upgrade_qa_report_followup.sql` → `deploy/migrations/20261116-qa-report-followup.sql` | 已有 MySQL 业务库补齐报告追问字段 | 保留 SQL 逻辑并迁移入口 | 已完成 | 与备份核对 DDL，验证旧表加列、外键和旧数据 |
| `AI-RAG-后续实施计划.md`、`docs/07-v0.3.0开发记录.md`、`docs/08-AI-Service架构与代码审查.md`、`docs/09-Agent基础设施平台设计建议.md`、`docs/superpowers/{plans/2026-11-06-ai-core-knowledge-base.md,specs/2026-11-06-ai-core-knowledge-base-design.md}` | 退役实现的早期计划、设计和开发记录 | 移除文件及主分支路径历史 | 已完成 | 路径不可达，任务留档完整 |
| `AGENTS.md`、`README.md`、`.gitignore`、`law-wiz.code-workspace`、`deploy/README.md`、`docs/{01-需求说明书.md,03-概要设计.md,04-数据库设计.md,05-接口设计.md,FILE_MAP.md,adr/0001-monorepo-and-vertical-slice-collaboration.md}` | 当前架构、部署、工作区与文档入口 | 修正当前说明及链接 | 已完成 | 目标存在，两个 Compose 上下文有效 |
| `docs/assets/fig-architecture.{mmd,png,svg}` → `docs/assets/fig-demo-architecture.{mmd,png,svg}`、`docs/assets/README.md`、`tools/render-mmd.mjs` | 当前架构图的源、交付图片与渲染示例 | 重绘，清除旧图路径历史 | 已完成 | 渲染产物和引用一致 |
| `frontend/src/api/auth.ts`、`frontend/src/views/QaView.vue` | 账号接口和问答断线恢复的代码说明 | 更新注释 | 已完成 | 前端 lint 和构建 |
| `docs/tasks/README.md`、`docs/tasks/T20261119-04-retire-python-backend.md` | 任务入口和施工验收 | 登记与同步 | 已完成 | 历史任务与原文件内容一致 |

## 验证结果与未解决事项

- 备份分支 `codex/legacy-python-backend` 指向 `1bbd694`，与该提交的 `backend/` Git 树一致，包含 74 个文件。
- 在单分支干净副本过滤旧后端、六份废弃文档和旧架构图。85 个提交过滤后为 60 个，当前源码树在过滤前后相同。历史路径检查与 Git 对象完整性检查通过。逐文件核对原任务留档以及 Java、AI、知识库、Compose 与业务空库初始化文件。
- Java 21 构建成功，10 项测试通过。业务前端和知识库管理前端的 lint 与生产构建通过。开发和生产 Compose 均解析出 8 个服务，所有构建上下文和 Dockerfile 存在。
- 迁移 SQL 的语句与备份分支一致。独立 MySQL 9.7 验证已有会话和空值默认保留、接受有效报告关联，并拒绝不存在的报告。
- 核对 8 个编辑器工作区目录、10 份文档中的相对链接和新版架构图的 PNG、SVG。
- 本地 `main` 从 `ef1f7e3` 快进到 `1bbd694`，随后采用过滤后的历史并在原工作区检出。已删除本地 `codex/ai-core-knowledge-base`。旧后端目录剩余的 16 项本机文件和目录整体移入 Git 忽略的备份位置，移动前后顶层条目一致。本次为本地交付。
