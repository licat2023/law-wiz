# 部署说明

开发和生产通过 Docker Compose 运行两个站点、Spring Boot 业务后端、知识库后端、AI 服务、MySQL、Redis 和 RustFS。两个站点分别代理同源 `/api`。业务合同和报告存入 RustFS，AI 服务调用生成模型并检索法条，知识库调用嵌入服务。

## 本地 Demo

以下命令都在 `deploy/` 中执行。将 `.env.dev.example` 复制为 `.env.dev`。首次运行可用知识库镜像生成管理员 bcrypt 哈希及签名密钥。

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml build
docker compose --env-file .env.dev -f docker-compose.dev.yml run --rm --no-deps knowledge-base python -c "import bcrypt,getpass; print(bcrypt.hashpw(getpass.getpass('Admin password: ').encode(), bcrypt.gensalt()).decode())"
docker compose --env-file .env.dev -f docker-compose.dev.yml run --rm --no-deps knowledge-base python -c "import secrets; print(secrets.token_urlsafe(48))"
```

将输出分别填入 `KB_ADMIN_PASSWORD_HASH` 和 `KB_JWT_SECRET`。密码哈希用单引号包围。MySQL 首次启动创建业务表。初始化空知识库后启动管理站点。

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml up -d --wait mysql redis
docker compose --env-file .env.dev -f docker-compose.dev.yml run --rm --no-deps knowledge-base python -m app.infrastructure.database
docker compose --env-file .env.dev -f docker-compose.dev.yml up -d --wait knowledge-base-frontend
```

用管理员打开默认地址 `http://127.0.0.1:5174`，创建默认知识库并上传演示语料。按 [知识库服务授权](../knowledge_base/README.md#身份与服务授权) 在 `.env.dev` 填写 `KB_SERVICE_KEYS_JSON`、`LAWWIZ_KNOWLEDGE_BASE_SERVICE_KEY` 和 `LAWWIZ_KNOWLEDGE_BASE_DEFAULT_ID`。执行下列命令使新环境变量生效并启动全栈，默认业务地址为 `http://127.0.0.1:5173`。

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml up -d --wait
```

已有开发卷时复用数据并直接执行全栈启动命令。开发 Compose 默认使用模型替身和开发嵌入。连接真实服务时，在 `.env.dev` 中设置 `LAWWIZ_ALLOW_FAKE_MODEL=false`、`KB_EMBEDDING_MODE=remote` 并填写相应配置。自定义知识库数据库口令包含 URL 特殊字符时，请提供密码经过 URL 编码的 `KB_DATABASE_URL`。

如果本机 `.env` 已保存真实嵌入配置，可在开发命令中按顺序指定 `--env-file .env --env-file .env.dev`。后一个文件中的同名配置会覆盖前一个文件，可从 `.env.dev` 去掉重复的 `KB_EMBEDDING_*` 项。`LAWWIZ_ALLOW_FAKE_MODEL=true` 可以和远程嵌入同时使用，可在知识库管理后台独立验证检索。普通问答需要配置 `LAWWIZ_MODEL_*` 并关闭模型替身。

开发容器运行 Vite。修改页面源码前，可在另一个终端运行以下命令，让 Compose Watch 同步两个 `src/` 目录并触发热更新。依赖、配置或后端源码修改后，用 `up -d --build --wait` 重建。

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml watch --no-up
```

## Compose 部署

在 `deploy/` 复制 `.env.example` 并填写各项凭据。`LAWWIZ_MODEL_*` 注入 AI 服务，`KB_EMBEDDING_*` 供知识库调用真实嵌入。`LAWWIZ_AI_SERVICE_TOKEN` 用于内部调用，生产至少 32 字符。两个数据库分别使用各自的凭据。AI 服务只接收知识库 reader 凭据，业务 writer 入口还要求管理员白名单。

首次部署可先启动知识库，再由管理员创建默认库。首次为知识库建表时可用空的服务凭证映射 `{}`。有实际库 ID 后设置默认库 ID 和 reader 映射，再启用业务后端。Compose 在解析完整配置时会校验必填变量，先填齐 `.env.example` 的必填项；只启动知识库时可临时给默认库 ID 填待初始化值。

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d --wait mysql redis
docker compose -f docker-compose.prod.yml run --rm --no-deps knowledge-base python -m app.infrastructure.database
docker compose -f docker-compose.prod.yml up -d --wait knowledge-base-frontend
# 按下文接通管理站点。创建默认库并填写授权后，用 up 应用新配置。
docker compose -f docker-compose.prod.yml up -d --wait knowledge-base
docker compose -f docker-compose.prod.yml up -d --wait
```

MySQL 镜像以 `mysql:9.7` 为底镜像并内置初始化脚本。首次启动创建业务表和独立知识库账号，已有数据库卷跳过初始化。新业务文件使用 `lawwiz-rustfs`。原业务文件保留在 `lawwiz-data`，知识库原文件和 Chroma 位于 `lawwiz-kb-data`，关系库位于 `lawwiz-mysql`。

已有数据库升级时，先按业务后端说明审核并执行报告追问迁移 SQL，再按知识库说明创建关键词表。知识库构建成功后，可以在本目录用一次性容器访问内部数据库，先以 `--schema-sql` 审核，再以 `--create-tables` 应用结构变更。知识库启动后用同一命令入口和 `--knowledge-base <库ID>` 分批排入重建任务。[业务后端说明](../backend/README.md) · [知识库升级](../knowledge_base/README.md#已有库升级)

```bash
docker compose -f docker-compose.prod.yml run --rm --no-deps knowledge-base \
  python -m scripts.rebuild_keyword_index --schema-sql
```

Compose 默认启用混合检索。可通过部署 `.env` 的 `KB_RETRIEVAL_STRATEGY` 选择向量、混合或重排。重排服务按目标环境的资源预算独立部署，完整端点和调用限制通过 `KB_RERANK_*` 配置。

## 迁移或回退业务文件

在同一 Compose 项目保留 MySQL 与旧业务文件卷。备份数据库和旧文件，保存旧版 Compose 配置、环境和业务镜像标签。暂停上传及新审查，等待在途业务任务结束后停止业务容器。核对旧卷可读，配置 RustFS 凭据并启动数据服务。迁移命令按文件记录读取，逐个核对大小和 SHA-256，复制后重新读取校验。全部验证通过才更新数据库定位。命令逐条输出 JSON 结果，最后报告验证与切换数量，可保存日志用于比对。

```bash
docker compose -f docker-compose.prod.yml up -d --wait mysql redis rustfs
docker compose -f docker-compose.prod.yml stop backend
docker compose -f docker-compose.prod.yml run --rm --no-deps backend --lawwiz.file-migration=check
docker compose -f docker-compose.prod.yml run --rm --no-deps backend --lawwiz.file-migration=copy
docker compose -f docker-compose.prod.yml up -d --wait
```

回退前同样暂停写入并停业务容器。以下命令以旧业务服务的用户身份挂载可写旧文件卷，将 RustFS 文件回补到旧路径并核对后更新数据库定位。用实际 Compose 项目名对应的旧卷替换例子中的卷名。定位都回到 `local` 后，才切回旧业务镜像。两份对象数据保留至回退窗口结束。

```bash
docker compose -f docker-compose.prod.yml run --rm --no-deps \
  -e LAWWIZ_STORAGE_LOCAL_ROOT=/app/.rollback \
  -v lawwiz_lawwiz-data:/app/.rollback:rw backend --lawwiz.file-migration=rollback
```

让保存的旧版编排引用备份的 Python 镜像标签，沿用原来的 Compose 项目名，再用 `up -d --no-deps --no-build --pull never --wait backend` 只切回业务后端。通过业务站点核对登录、旧报告和回退前新增的报告均可读取。

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
| 业务后端 | 384 MiB |
| AI 服务 | 256 MiB |
| RustFS | 256 MiB |
| 知识库（单 worker） | 512 MiB |
| 业务前端 | 32 MiB |
| 知识库管理前端 | 32 MiB |

部署到共享主机前，以真实语料、模型和并发请求核对 Java、AI 与 RustFS 的实际内存占用。
