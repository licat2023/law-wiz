# 部署说明

开发和生产均通过 Docker Compose 运行六个服务：业务前端、业务后端、知识库管理前端、知识库后端、MySQL 和 Redis。两个站点分别代理同源 `/api`。模型由业务后端调用，嵌入由知识库调用。

## 本地 Demo

以下命令都在 `deploy/` 中执行。将 `.env.dev.example` 复制为 `.env.dev`。首次运行可用知识库镜像生成管理员 bcrypt 哈希及签名密钥。

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml build
docker compose --env-file .env.dev -f docker-compose.dev.yml run --rm --no-deps knowledge-base python -c "import bcrypt,getpass; print(bcrypt.hashpw(getpass.getpass('Admin password: ').encode(), bcrypt.gensalt()).decode())"
docker compose --env-file .env.dev -f docker-compose.dev.yml run --rm --no-deps knowledge-base python -c "import secrets; print(secrets.token_urlsafe(48))"
```

将输出分别填入 `KB_ADMIN_PASSWORD_HASH` 和 `KB_JWT_SECRET`。密码哈希用单引号包围。先启动数据服务，只为两个空库执行各自的建表命令，再启动管理站点。

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml up -d --wait mysql redis
docker compose --env-file .env.dev -f docker-compose.dev.yml run --rm --no-deps knowledge-base python -m app.infrastructure.database
docker compose --env-file .env.dev -f docker-compose.dev.yml run --rm --no-deps backend python -m app.infrastructure.database.bootstrap
docker compose --env-file .env.dev -f docker-compose.dev.yml up -d --wait knowledge-base-frontend
```

用管理员打开默认地址 `http://127.0.0.1:5174`，创建默认知识库并上传演示语料。按 [知识库服务授权](../knowledge_base/README.md#身份与服务授权) 在 `.env.dev` 填写 `KB_SERVICE_KEYS_JSON`、`LAWWIZ_KNOWLEDGE_BASE_SERVICE_KEY` 和 `LAWWIZ_KNOWLEDGE_BASE_DEFAULT_ID`。执行下列命令使新环境变量生效并启动全栈，默认业务地址为 `http://127.0.0.1:5173`。

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml up -d --wait
```

已有开发卷时复用数据并直接执行全栈启动命令。开发 Compose 默认使用模型替身和开发嵌入。连接真实服务时，在 `.env.dev` 中设置 `LAWWIZ_ALLOW_FAKE_MODEL=false`、`KB_EMBEDDING_MODE=remote` 并填写相应配置。自定义知识库数据库口令包含 URL 特殊字符时，请提供密码经过 URL 编码的 `KB_DATABASE_URL`。

开发容器运行 Vite。修改页面源码前，可在另一个终端运行以下命令，让 Compose Watch 同步两个 `src/` 目录并触发热更新。依赖、配置或后端源码修改后，用 `up -d --build --wait` 重建。

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml watch --no-up
```

## Compose 部署

在 `deploy/` 复制 `.env.example` 并填写各项凭据。`LAWWIZ_MODEL_*` 供业务后端调用模型，`KB_EMBEDDING_*` 供知识库调用真实嵌入。两个数据库使用各自的账号与凭据。业务 reader 与可选 writer 分开授权，writer 入口还要求业务管理员白名单。

首次部署可先启动知识库，再由管理员创建默认库。首次为知识库建表时可用空的服务凭证映射 `{}`。有实际库 ID 后设置默认库 ID 和 reader 映射，再启用业务后端。Compose 在解析完整配置时会校验必填变量，先填齐 `.env.example` 的必填项；只启动知识库时可临时给默认库 ID 填待初始化值。

```bash
docker compose -f docker-compose.prod.yml up -d --wait mysql redis
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml run --rm --no-deps knowledge-base python -m app.infrastructure.database
docker compose -f docker-compose.prod.yml up -d --wait knowledge-base-frontend
# 按下文接通管理站点。创建默认库并填写授权后，用 up 应用新配置。
docker compose -f docker-compose.prod.yml up -d --wait knowledge-base
docker compose -f docker-compose.prod.yml run --rm --no-deps backend python -m app.infrastructure.database.bootstrap
docker compose -f docker-compose.prod.yml up -d --wait
```

MySQL 首次启动通过 `mysql-init/20-knowledge-base.sh` 创建独立知识库及账号。已有卷跳过镜像初始化脚本。业务文件卷为 `lawwiz-data`，知识库原文件和 Chroma 位于 `lawwiz-kb-data`，数据库位于 `lawwiz-mysql`。

已有数据库升级时，先按业务后端说明审核并执行报告追问迁移 SQL，再按知识库说明创建关键词表。知识库构建成功后，可以在本目录用一次性容器访问内部数据库，先以 `--schema-sql` 审核，再以 `--create-tables` 应用结构变更。知识库启动后用同一命令入口和 `--knowledge-base <库ID>` 分批排入重建任务。[业务后端说明](../backend/README.md) · [知识库升级](../knowledge_base/README.md#已有库升级)

```bash
docker compose -f docker-compose.prod.yml run --rm --no-deps \
  -v ../knowledge_base/backend/scripts:/app/scripts:ro knowledge-base \
  python -m scripts.rebuild_keyword_index --schema-sql
```

Compose 默认启用混合检索。可通过部署 `.env` 的 `KB_RETRIEVAL_STRATEGY` 选择向量、混合或重排。重排服务按目标环境的资源预算独立部署，完整端点和调用限制通过 `KB_RERANK_*` 配置。

## 站点与健康检查

生产 Compose 构建并运行两个 Nginx 站点。站点端口只绑定宿主机回环地址，由 `LAWWIZ_FRONTEND_PORT`（默认 8080）和 `KB_FRONTEND_PORT`（默认 8180）设置。1Panel OpenResty 继续管理各站点的域名和 HTTPS，将业务站点的全部路径转发到业务前端端口，将独立管理站点的全部路径转发到知识库管理前端端口。

从旧发布方式迁移时，先构建并启动新镜像，通过回环地址核对页面和 API，随后把两个 OpenResty 站点切换为整站反向代理并移除旧静态根目录和单独的 `/api` 代理规则。保留既有数据库与文件卷，沿用各自的升级流程。

完成所需数据库升级后，在 `deploy/` 构建并启动新版容器。

```bash
docker compose -f docker-compose.prod.yml up -d --build --wait
```

OpenResty 的站点代理须传递原始 `Host`，用 `$remote_addr` 设置 `X-Forwarded-For`，用 `$scheme` 设置 `X-Forwarded-Proto`。业务认证依赖原始客户端 IP 限流。两层代理均需容纳上传和模型调用，OpenResty 可按内层配置设置业务站点 `client_max_body_size 21m`、知识库管理站点 `client_max_body_size 50m` 以及 `proxy_read_timeout 310s`。业务容器负责页面路由回退，管理界面使用 hash 路由。

两个前端容器检查首页。通过业务站点的 `/api/health` 检查业务服务，通过管理站点的 `/api/ready` 检查知识库的数据库和 Chroma。按响应的 `request_id` 查询后端日志。

## 内存预算

| 容器 | 生产上限 |
| --- | --- |
| MySQL | 384 MiB |
| Redis | 96 MiB |
| 业务后端（含 Agent） | 640 MiB |
| 知识库（单 worker） | 512 MiB |
| 业务前端 | 32 MiB |
| 知识库管理前端 | 32 MiB |

业务后端的配置上限沿用原业务与 AI 容器上限之和。部署到共享主机前，以真实语料、模型和并发请求核对实际内存占用。
