# 独立知识库

`backend` 独立持有文档、修订、分块、任务、原文件和内嵌 Chroma；`frontend` 是独立 Vue 管理界面。业务后端及其中的 Agent 通过同一个 HTTP 客户端检索。知识库拥有独立数据库、原文件卷与 Chroma 目录。

## 本地运行

从 `backend/.env.example` 复制本地配置，设置异步数据库 URL、管理员 bcrypt 密码哈希、至少32字符的独立 JWT 签名密钥和嵌入服务。配置值只放环境或未跟踪的 `.env`，不能提交真实连接和凭据。

```bash
cd knowledge_base/backend
uv sync --frozen --extra dev
uv run python -m app.infrastructure.database
uv run uvicorn app.main:app --reload --port 8100
```

Windows 环境创建时指定标准 Python 3.14 的绝对路径。Chroma 若无法打开本地数据库，可将 `KB_DATA_ROOT` 指向可写的短路径，避开带非 ASCII 字符的路径。开发可用 aiosqlite（需 dev extra）；生产必须是 `mysql+aiomysql`。`python -m app.infrastructure.database` 只初始化空库，不升级或删除已有业务数据库。

```bash
cd knowledge_base/frontend
pnpm install --frozen-lockfile
pnpm dev
```

界面开发端口5174，通过 Vite 将 `/api` 转发到本地8100端口；需要其他地址时使用未跟踪环境文件中的 `KB_API_TARGET`。界面只使用管理员登录令牌，不接触服务凭证。生产构建 `pnpm build`，将 `dist` 发布到独立静态站点，并将同站点 `/api` 反向代理至知识库后端；SPA回退到 `index.html`。保持与业务前端分站点，避免API路径冲突。

## 身份与服务授权

管理入口使用知识库自己的用户名、密码哈希与 JWT，不接受业务 JWT。`KB_SERVICE_KEYS_JSON` 是服务凭证到应用/知识库的映射：

```json
{
  "<业务只读凭证>": {"application_id": "law-wiz", "knowledge_base_ids": ["<默认库ID>"], "role": "reader"},
  "<业务写入凭证>": {"application_id": "law-wiz", "knowledge_base_ids": ["<默认库ID>"], "role": "writer"}
}
```

真实服务凭证至少16字符，分别生成且不复用签名密钥。智法宝的普通查询与 Agent 共用 reader。业务兼容写入入口需要 writer 和业务管理员白名单；首次创建知识库使用独立管理员身份，之后将实际ID登记到服务授权与调用方默认库配置。其他应用必须使用不同凭证、应用ID和库白名单。

bcrypt哈希可在安装依赖后用交互式密码输入生成：

```bash
uv run python -c "import bcrypt,getpass; print(bcrypt.hashpw(getpass.getpass('管理员密码: ').encode(),bcrypt.gensalt()).decode())"
```

`.env` 中含 `$` 的密码哈希用单引号包围。签名密钥和服务凭证可用 `python -c "import secrets; print(secrets.token_urlsafe(48))"` 分别生成。不要将密钥放入前端环境变量。

## 语料入库

管理员在管理后台创建库，上传本机下载的原文件或新建 Markdown 文档。程序可向 `POST /api/knowledge-bases/{kb_id}/documents` 提交 multipart 文件或 JSON 正文与 `metadata`。文件由知识库解析，清洗后的 Markdown 从正文进入后续流程。切分、嵌入和索引发布统一由知识库处理。使用 `Idempotency-Key` 重试相同请求，更新现有来源时用文档 ID 和当前修订号更新。

`app/knowledge_bases/` 负责库和权限范围，`app/documents/` 负责文件、修订、解析与导入，`app/indexing/` 负责切分与发布，`app/retrieval/` 负责搜索，`app/infrastructure/` 负责持久化和外部接入。

## 处理和持久化约束

支持 DOCX、文本 PDF、UTF-8 Markdown 和 TXT。旧 DOC 和扫描件 OCR 暂未支持。切分支持固定、语义与可选层级索引。所有来源偏移以修订全文的 Unicode 字符为单位，使用半开区间，界面转换为 UTF-16 位置。

检索结果的 `content` 是命中片段。法条命中的 `article_chunk_id` 指向响应中的 `article_contents`，同一条文只传一次。每次检索最多返回 16,000 字符的完整条文，另受 `KB_MAX_TEXT_CHARS` 约束。超限条文从结果中省略，并设置 `article_limit_reached`。

任务状态与租约持久化在独立数据库。新修订索引就绪前继续读取旧生效索引；失败保留旧版本，删除使文档先不可见。Chroma只保存索引向量，实际可见性由关系库生效版本控制。

生产只启用真实远程embeddings，模型名与维度必须匹配实际服务；改变向量空间应重建索引。开发替身必须显式设置 `KB_EMBEDDING_MODE=development`，生产禁止此模式。`KB_AUTO_CREATE_SCHEMA=false`，通过显式命令建表。

内嵌Chroma只能由一个API worker持有整个数据目录；不得多进程共享或在该目录上再起Chroma服务。持久化挂载 `/app/.data`，同时备份关系库及该目录；恢复时必须来自同一备份窗口。上传/解析/索引限制由 `KB_MAX_*`、处理租约和并发配置控制。

## 验证与发布

```bash
cd knowledge_base/backend
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
cd ../frontend
pnpm run lint
pnpm run format:check
pnpm run build
```

生产编排、数据库账号初始化和容量预算见 [部署说明](../deploy/README.md)。
