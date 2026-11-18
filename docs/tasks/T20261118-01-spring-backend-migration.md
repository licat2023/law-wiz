# 智法宝独立 AI 服务与 Java 业务后端迁移

## 用户需求依据

- R1，本次聊天，用户要求“规划计划拆AI并将后端转为SpringBoot+Mybatis+Redsi+RustFS”。
- R2，本次聊天，用户设置执行目标“拆AI并将后端转为SpringBoot+Mybatis+Redsi+RustFS”。采用此前对话中的 AI 拆分、Java 接管、RustFS 切换和本地回退演练顺序。
- R3，本次聊天，用户对遗留改动的处理选择“进行提交然后在当前工作区开展工作”。已在现有分支分别提交文档纠正、编辑器配置、历史 AI 方案和架构调研。迁移以其后的干净 HEAD `f06f890` 为基线。

## 当前任务理解

交付独立 Python AI 服务和由 Java 21、Spring Boot、MyBatis、MySQL、Redis、RustFS 组成的业务后端。业务后端拥有用户、审查、问答、任务调度及文件权限。AI 服务执行审查和法律问答，使用只读凭据检索独立知识库。RustFS 保存业务合同和 PDF 报告。知识库独立持有自己的数据、文件和 Chroma。

沿用前端同源 `/api`、接口字段和错误码、字符串 ID、现有数据库及业务文件。能在干净源码副本启动开发和生产编排，用空库及已有数据验证登录、上传、审查、PDF、普通问答、报告追问、引用、失败回填、限流及幂等。交付历史对象复制、校验、切换和回退方法。实际线上切换需另行安排。

实施选择：将 Redsi 理解为 Redis。先让现有业务后端通过内网 HTTP 调用 AI，再逐步接入 Java，并以 RustFS 作为业务文件写入目标。首版保持进程内任务调度。迁移验收使用隔离 Compose 和脱敏数据。

## 实施方案

1. 从当前后端导出 OpenAPI 和 MySQL DDL，保存测试样本与结果。以 Python 标准构建对照现有行为。
2. 移动现有 Agent 和模型调用到 `ai-service/`。为两个业务请求提供类型明确的内网接口，传请求和追踪标识。鉴权、并发、超时与错误转换集中在服务入口。过渡业务后端保留数据库和文件流水线。
3. 在 `backend-java/` 按现有领域实现业务 API。先迁登录和问答来验证旧库、Redis 及服务间调用，再迁文件、审查和知识库转发。Java 完成后将其设为业务站点上游。
4. 用实际容器验证 MySQL 无符号 ID、RustFS S3 读写和持久化。沿用 SHA-256 对象键，按数据库记录迁移旧卷，运行校验和增量补齐。演练恢复本地文件和旧业务后端。
5. 从干净源码验收完整 Compose、故障路径及资源占用，更新目录说明、部署、接口和示例。

## 分工与施工清单

| 路径 | 职责 | 变更 | 状态 | 验证要求 |
| --- | --- | --- | --- | --- |
| `ai-service/{ai_service/,tests/,pyproject.toml,uv.lock,Dockerfile,.dockerignore,README.md}` | 独立运行两个 Agent、检索并接入模型 | 新增及移动 | 已完成 | 4 项独立回归及 Docker 调用通过 |
| `backend/app/{core/agent.py,core/citations.py,domains/contract_review/,domains/legal_qa/,infrastructure/{ai_service,knowledge_base,llm}.py,api/health.py,config.py,lifespan.py}`、`backend/{tests/,pyproject.toml,uv.lock,.env.example,README.md}` | 过渡业务流程通过 HTTP 调用 AI，保留权限、状态和数据 | 修改及移动 | 已完成 | 5 项回归和开发容器端到端通过 |
| `backend-java/{pom.xml,Dockerfile,.dockerignore,.gitignore,README.md,src/main/java/,src/main/resources/,src/test/java/}` | Spring Boot、MyBatis、Redis、业务 HTTP、文档处理与对象存储 | 新增 | 施工中 | API 对照、实际 MySQL 与 Redis、文件样本与故障 |
| `backend-java/src/{main,test}/java/com/lawwiz/business/files/` | 文件内容识别、上传去重、权限校验与 RustFS 对象读写 | 新增 | 已完成 | 实际 RustFS 上传和 SHA-256 校验通过，旧卷读取纳入审查联调 |
| `deploy/{docker-compose.dev.yml,docker-compose.prod.yml,.env.dev.example,.env.example,README.md}` | 服务编排、配置与启动 | 修改 | 施工中 | 空库与既有库、健康检查和容器预算 |
| `deploy/` 迁移工具 | 旧文件清单、复制、哈希验证和切换回退 | 新增，路径待定 | 待施工 | 幂等迁移、缺失或损坏检测、回退可读取新增文件 |
| `AGENTS.md`、`README.md`、`docs/{FILE_MAP.md,02-技术栈.md,03-概要设计.md,05-接口设计.md,06-MVP演示指南.md}`、`law-wiz.code-workspace` | 技术与部署入口、路径和接口说明 | 修改 | 待施工 | 对照最终目录和运行行为 |
| `docs/tasks/{README.md,T20261118-01-spring-backend-migration.md}` | 跟踪需求、状态和验收依据 | 修改及新增 | 施工中 | 链接、状态和实际验证一致 |

## 验证结果与未解决事项

- 当前分支无合并、变基或暂存遗留。业务报告追问的 5 项基线测试通过，知识库现有 Ruff 检查通过。
- 本机 Docker 可用，已有 MySQL 9.7、Redis、Java 21 Maven 构建镜像及 RustFS 1.0.5 镜像。端到端、真实模型和主机并发内存仍待验证。
- AI 拆分阶段从暂存树导出干净源码。两个 Python 环境的 Ruff 检查、格式检查和共 9 项回归通过。隔离开发 Compose 构建并启动业务后端、独立 AI 服务及真实 MySQL、Redis、知识库，验证合同上传、审查成功、可下载 PDF、普通问答与报告追问。使用开发模型和空检索样本核对无依据行为，容器日志确认两类请求实际经过内部 HTTP。保留导出的 OpenAPI 及 13 表 MySQL DDL 用于 Java 对照。
- Java 鉴权切片使用 Spring Boot 4.0.9、MyBatis Starter 4.0.1 和 Java 21。对同一隔离 MySQL 9.7 和 Redis，验证旧用户登录、旧 JWT 读取资料、旧刷新令牌在 Java 轮换、Python 识别 Java 新 JWT 和新密码哈希。重复邮箱返回 40902，资料更新和注销后旧刷新令牌失效通过。无符号用户编号 `9223372036854775815` 可通过 MyBatis、JWT 和 API 往返，JSON 保持字符串。
- Java 问答容器通过实际 HTTP 调用独立 AI，验证重复提交复用消息、会话列表和归档、两轮风险项追问、跨用户拒绝以及旧后端读取 Java 写入的历史。用隔离库中的一条已索引法规样本验证 Java 保存真实检索命中的引用、旧后端读取同一引用。使用开发模型。
- RustFS 1.0.5 独立容器验证了 S3 签名请求建桶及对象写入、读取和重启后字节一致。Java 容器通过实际 RustFS 上传合同，重复上传复用文件 ID，下载校验 SHA-256 与原件一致。历史数据迁移仍待实施。
