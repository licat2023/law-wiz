# 智法宝独立 AI 服务与 Java 业务后端迁移

## 用户需求依据

- R1，本次聊天，用户要求“规划计划拆AI并将后端转为SpringBoot+Mybatis+Redsi+RustFS”。
- R2，本次聊天，用户设置执行目标“拆AI并将后端转为SpringBoot+Mybatis+Redsi+RustFS”。采用此前对话中的 AI 拆分、Java 接管、RustFS 切换和本地回退演练顺序。
- R3，本次聊天，用户对遗留改动的处理选择“进行提交然后在当前工作区开展工作”。已在现有分支分别提交文档纠正、编辑器配置、历史 AI 方案和架构调研。迁移以其后的干净 HEAD `f06f890` 为基线。
- R4，本次聊天，用户要求“继续完成上一轮因 usage limit 中断的任务。先检查当前工作区状态，避免重复执行已经完成的修改或命令，然后从未完成步骤继续。保留原有任务范围，不要停下来等人确认。”继续使用当前工作区，并按最新 Docker 文件交换约定验收。
- R5，本次聊天，用户说明“嵌入模型不是.env提供的有，而且这个项目不上生产，目前也是开发阶段，所以直接弄随便弄”。补充联调以本机开发环境为范围，复用已有嵌入配置。

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
| `backend-java/{pom.xml,Dockerfile,.dockerignore,.gitignore,README.md,src/main/java/,src/main/resources/,src/test/java/}` | Spring Boot、MyBatis、Redis、业务 HTTP、文档处理与对象存储 | 新增 | 已完成 | 干净源码构建，5 项 Java 测试和 25 个 API 路径及方法对照通过 |
| `backend-java/src/{main,test}/java/com/lawwiz/business/files/` | 文件内容识别、流式上传、去重、权限校验与 RustFS 对象读写 | 新增 | 已完成 | 实际 RustFS 两份 19 MiB 并发上传、去重及读回哈希验证通过 |
| `backend-java/src/{main,test}/java/com/lawwiz/business/review/`、`backend-java/{pom.xml,Dockerfile}` | 审查任务、正文提取、生成中文 PDF 和保存报告 | 新增及修改 | 已完成 | DOCX 顺序、长文审查、中文 PDF、风险及模型故障回填通过 |
| `backend-java/src/main/java/com/lawwiz/business/knowledge/` | 转发已有知识库兼容 API，保持读写权限与响应字段 | 新增 | 已完成 | 独立知识库授权写入、索引、读回、检索和拒绝无权写入通过 |
| `deploy/{docker-compose.dev.yml,docker-compose.prod.yml,.env.dev.example,.env.example,README.md}` | 服务编排、配置与启动 | 修改 | 已完成 | 开发栈通过实际嵌入与问答引用验证，生产编排曾用测试端点验证 |
| `backend-java/src/main/java/com/lawwiz/business/files/FileMigration.java`、`deploy/mysql-init/{Dockerfile,10-business-schema.sql}` | 历史对象复制、哈希校验、回退和以镜像初始化空库 | 新增 | 已完成 | 空业务库 13 张表，缺件拒绝、重复复制及两版下载对照通过 |
| `knowledge_base/backend/Dockerfile` | 将已有索引升级脚本随镜像交付 | 修改 | 已完成 | 从容器输出关键词表升级 DDL |
| `AGENTS.md`、`README.md`、`backend/README.md`、`knowledge_base/README.md`、`docs/{FILE_MAP.md,02-技术栈.md,03-概要设计.md,04-数据库设计.md,05-接口设计.md,06-MVP演示指南.md}`、`law-wiz.code-workspace` | 技术与部署入口、路径、文件定位、备份和接口说明 | 修改 | 已完成 | 按最终目录、初始化行为与回退命令核对 |
| `docs/tasks/{README.md,T20261118-01-spring-backend-migration.md}` | 跟踪需求、状态和验收依据 | 修改及新增 | 已完成 | 链接、状态和实际验证一致 |

## 验证结果与未解决事项

- 业务报告追问的 5 项基线测试与知识库 Ruff 检查通过。
- AI 拆分阶段从暂存树导出干净源码。两个 Python 环境的 Ruff 检查、格式检查和共 9 项回归通过。隔离开发 Compose 构建并启动业务后端、独立 AI 服务及真实 MySQL、Redis、知识库，验证合同上传、审查成功、可下载 PDF、普通问答与报告追问。使用开发模型和空检索样本核对无依据行为，容器日志确认两类请求实际经过内部 HTTP。保留导出的 OpenAPI 及 13 表 MySQL DDL 用于 Java 对照。
- Java 鉴权切片使用 Spring Boot 4.0.9、MyBatis Starter 4.0.1 和 Java 21。对同一隔离 MySQL 9.7 和 Redis，验证旧用户登录、旧 JWT 读取资料、旧刷新令牌在 Java 轮换、Python 识别 Java 新 JWT 和新密码哈希。重复邮箱返回 40902，资料更新和注销后旧刷新令牌失效通过。无符号用户编号 `9223372036854775815` 可通过 MyBatis、JWT 和 API 往返，JSON 保持字符串。
- Java 问答容器通过实际 HTTP 调用独立 AI，验证重复提交复用消息、会话列表和归档、两轮风险项追问、跨用户拒绝以及旧后端读取 Java 写入的历史。用隔离库中的一条已索引法规样本验证 Java 保存真实检索命中的引用、旧后端读取同一引用。使用开发模型。
- RustFS 1.0.5 验证建桶、对象读写和重启持久化。Java 以临时文件流式上传，两份 19 MiB 合同并发成功，重复上传复用文件 ID，从实际对象存储读回校验通过。负载完成时，Java 容器观测值从 383.3 MiB 降至 256 MiB，两轮均无 OOM 或重启。该数据是本机样本观测，未测目标主机生产并发。
- Java 审查读取 RustFS 合同并生成中文 PDF。实际 MySQL 验证风险规则、报告计数和误报标记。系统存下 24 万字符合同正文，在 AI 输入上限内成功生成审查结果。知识库兼容入口实测授权写入、索引、分块及检索，未授权写入返回 40301。
- 从 Git 暂存树导出干净源码构建。开发和隔离生产编排均启动，两个站点代理通过，前端生产构建和两套 ESLint、5 项 Java 回归通过。OpenAPI 对照 20 个路径共 25 个 HTTP 操作，路径参数名称按占位符核对。开发文档可打开，生产文档和固定验证码均关闭。健康检查的 `runtime` 提供 `java_version` 和启动时间，Java OpenAPI 中的响应 `data` 为通用类型。开发使用模型替身，生产编排连接本地协议替身，验证实际 HTTP 交互和模型 503 经服务转换后持久化为 `failed`/`50301`。
- 隔离已有库共校验 13 个对象，覆盖旧卷与 RustFS 混合数据、缺件拒绝、复制重试和全部回退。缺件时数据库定位保持不变。生产编排按文档回退 3 个对象后，旧版 Python 登录并下载 Java 新生成的 PDF，字节与回退前相同。复制回 RustFS 后，Java 再次下载得到相同文件。
- 按 R5 启动本机 `lawwiz-dev`，由 `.env` 提供已有嵌入设置，由 Git 忽略的 `.env.dev` 提供本地账号及服务授权。实际服务返回 4096 维向量。两个标注为开发样本的文档成功索引，纯向量检索把交付验收样本排在首位。业务站点的问答通过独立 AI 服务检索并保存预期引文。两个前端均可访问，八个容器健康。生成模型配置缺少密钥，继续使用开发替身。本轮范围为本机开发联调。
