# 部署说明

部署包含智法宝业务后端、独立知识库、MySQL 和 Redis。业务前端与知识库管理前端分别构建为静态站点。模型由业务后端调用，嵌入由知识库调用。

## 本地 Demo

从仓库根目录启动数据库和缓存。

```bash
docker compose -f deploy/docker-compose.dev.yml up -d
```

1. 按 [知识库说明](../knowledge_base/README.md) 配置管理员、数据库及嵌入，初始化空库并启动后端和管理界面。
2. 用管理员创建默认知识库并上传演示语料。将库 ID 写入 `KB_SERVICE_KEYS_JSON` 的 reader 授权，重启知识库使配置生效。
3. 按 [业务后端说明](../backend/README.md) 配置 `LAWWIZ_KNOWLEDGE_BASE_*` 和模型，初始化业务空库并启动后端。在 `frontend/` 安装依赖并启动前端。

知识库可用开发嵌入，业务后端可启用模型替身。语料通过管理后台或知识库 HTTP API 显式入库。开发替身用于演示流程，真实语义召回与模型输出依赖远程服务。

## Compose 部署

在 `deploy/` 复制 `.env.example` 并填写各项凭据。`LAWWIZ_MODEL_*` 供业务后端调用模型，`KB_EMBEDDING_*` 供知识库调用真实嵌入。两个数据库使用各自的账号与凭据。业务 reader 与可选 writer 分开授权，writer 入口还要求业务管理员白名单。

首次部署可先启动知识库，再由管理员创建默认库。首次为知识库建表时可用空的服务凭证映射 `{}`。有实际库 ID 后设置默认库 ID 和 reader 映射，再启用业务后端。Compose 在解析完整配置时会校验必填变量，先填齐 `.env.example` 的必填项；只启动知识库时可临时给默认库 ID 填待初始化值。

```bash
docker compose -f docker-compose.prod.yml up -d --wait mysql redis
docker compose -f docker-compose.prod.yml build knowledge-base backend
docker compose -f docker-compose.prod.yml run --rm --no-deps knowledge-base python -m app.infrastructure.database
docker compose -f docker-compose.prod.yml up -d --wait knowledge-base
# 创建默认库、填写实际 ID 并重启知识库后，再初始化并启动业务后端。
docker compose -f docker-compose.prod.yml up -d --wait knowledge-base
docker compose -f docker-compose.prod.yml run --rm --no-deps backend python -m app.infrastructure.database.bootstrap
docker compose -f docker-compose.prod.yml up -d --wait backend
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

在 `frontend/` 和 `knowledge_base/frontend/` 分别执行 `pnpm install --frozen-lockfile` 与 `pnpm run build`。将两个 `dist/` 发布到各自静态站点，分别把同站点的 `/api` 代理到对应后端。业务站点需将前端页面路由回退至 `index.html`。

业务服务检查 `/api/health`，知识库使用 `/api/ready` 检查数据库和 Chroma。按响应的 `request_id` 查询两个后端日志。

## 内存预算

| 容器 | 当前上限 |
| --- | --- |
| MySQL | 384 MiB |
| Redis | 96 MiB |
| 业务后端（含 Agent） | 640 MiB |
| 知识库（单 worker） | 512 MiB |

业务后端的配置上限沿用原业务与 AI 容器上限之和。部署到共享主机前，以真实语料、模型和并发请求核对实际内存占用。
