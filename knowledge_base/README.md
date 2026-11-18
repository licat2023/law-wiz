# 独立知识库

`backend` 独立持有文档、修订、分块、任务、原文件和内嵌 Chroma；`frontend` 是独立 Vue 管理界面。业务后端转发兼容接口，独立 AI 服务通过 HTTP 检索。知识库拥有独立数据库、原文件卷与 Chroma 目录。

## 本地运行

按 [全容器部署说明](../deploy/README.md) 生成管理员凭据、初始化空库并启动知识库后端和管理站点。管理界面通过自己的站点访问同源 `/api`，登录使用知识库管理员令牌，服务凭证由后端持有。

## 身份与服务授权

管理入口使用知识库自己的用户名、密码哈希与 JWT，不接受业务 JWT。`KB_SERVICE_KEYS_JSON` 是服务凭证到应用/知识库的映射：

```json
{
  "<业务只读凭证>": {"application_id": "law-wiz", "knowledge_base_ids": ["<默认库ID>"], "role": "reader"},
  "<业务写入凭证>": {"application_id": "law-wiz", "knowledge_base_ids": ["<默认库ID>"], "role": "writer"}
}
```

真实服务凭证至少16字符，分别生成且不复用签名密钥。智法宝的普通查询与 Agent 共用 reader。业务兼容写入入口需要 writer 和业务管理员白名单；首次创建知识库使用独立管理员身份，之后将实际ID登记到服务授权与调用方默认库配置。其他应用必须使用不同凭证、应用ID和库白名单。

密码哈希及签名密钥生成命令见 [部署说明](../deploy/README.md)。`.env` 中含 `$` 的密码哈希用单引号包围。用同一随机生成命令单独生成服务凭证，并在部署环境文件中配置。

## 语料入库

管理员在管理后台创建库，上传本机下载的原文件或新建 Markdown 文档。程序可向 `POST /api/knowledge-bases/{kb_id}/documents` 提交 multipart 文件或 JSON 正文与 `metadata`。文件由知识库解析，清洗后的 Markdown 从正文进入后续流程。切分、嵌入和索引发布统一由知识库处理。使用 `Idempotency-Key` 重试相同请求，更新现有来源时用文档 ID 和当前修订号更新。

`app/knowledge_bases/` 负责库和权限范围，`app/documents/` 负责文件、修订、解析与导入，`app/indexing/` 负责切分与发布，`app/retrieval/` 负责搜索，`app/infrastructure/` 负责持久化和外部接入。

## 处理和持久化约束

支持 DOCX、文本 PDF、UTF-8 Markdown 和 TXT。旧 DOC 和扫描件 OCR 暂未支持。切分支持固定、语义与可选层级索引。所有来源偏移以修订全文的 Unicode 字符为单位，使用半开区间，界面转换为 UTF-16 位置。

检索结果的 `content` 是命中片段。法条命中的 `article_chunk_id` 指向响应中的 `article_contents`，同一条文只传一次。每次检索最多返回 16,000 字符的完整条文，另受 `KB_MAX_TEXT_CHARS` 约束。超限条文从结果中省略，并设置 `article_limit_reached`。

任务状态与租约持久化在独立数据库。新修订索引就绪前继续读取旧生效索引；失败保留旧版本，删除使文档先不可见。Chroma只保存索引向量，实际可见性由关系库生效版本控制。

## 混合检索与重排

索引任务给同一批叶块建立 Chroma 向量和 SQL 关键词倒排。关键词处理采用中文相邻二字、标准化法条编号及词频统计，索引内容包含叶块正文、法规标题和法条号。向量写入完成后，数据库在同一事务写入关键词索引并切换生效版本。两路使用相同的库、版本、文档类型、层级和时效过滤。混合检索用 RRF 按名次合并候选，单路故障时使用可用候选。结果按完整法条去重，并保留命中片段及来源定位。

### 已有库升级

空库按部署说明初始化。已有库先审核两张新增关键词表的 MySQL DDL，使用有建表权限的维护连接执行升级。应用连接的运行权限沿用现有配置。

```bash
cd knowledge_base/backend
uv run python -m scripts.rebuild_keyword_index --schema-sql
uv run python -m scripts.rebuild_keyword_index --create-tables
uv run python -m scripts.rebuild_keyword_index --knowledge-base <库ID> --limit 100
```

第二条命令只创建缺失的关键词表和相应索引。第三条命令检查指定库中当前可用、尚未生成关键词索引的文档，并通过既有后台处理器重建。新索引发布前旧向量继续可查。可分批重复执行，输出任务 ID 供查看结果。存在待处理或失败修订的文档通过管理页处理后重新核对。

### 策略与评测

直接启动服务时默认 `KB_RETRIEVAL_STRATEGY=vector`。仓库的生产 Compose 默认启用 `hybrid`。管理员可在知识库「检索测试」比较向量、混合召回和混合召回与重排，展开四个阶段的候选与状态。通过 `KB_RETRIEVAL_CANDIDATES` 调整单路候选数。

需要重排时，单独部署兼容 TEI `/rerank` 的 Cross-Encoder 服务。将完整端点填入 `KB_RERANK_ENDPOINT`，按需配置 `KB_RERANK_API_KEY`。通过 `KB_RERANK_CANDIDATES` 限制每次提交数，并用 `KB_RERANK_TIMEOUT_SECONDS` 限制整次调用。端点未配置、超时或响应异常时使用 RRF 顺序。中文样本可用独立的 CPU TEI 服务验证，模型和候选数以目标环境评测为准。[TEI 重排接口](https://huggingface.co/docs/text-embeddings-inference/quick_tour) · [实测模型 mMARCO MiniLM](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1)

将测试管理员令牌放入 `KB_EVALUATION_TOKEN` 环境变量，然后运行：

```bash
uv run python -m scripts.evaluate_retrieval --base-url <测试服务地址> --knowledge-base <库ID> --output <本地报告路径>
```

随附评测集覆盖法条号、精确术语、口语、近义歧义、失效及无答案问题。报告记录 Recall@K、MRR@K、P95、负例及降级状态。失效对照只有在包含失效内容的请求确实召回旧法规时才算有效。部署前用实际嵌入服务和生产相近的语料规模复测。

## 运行资源

生产只启用真实远程embeddings，模型名与维度必须匹配实际服务；改变向量空间应重建索引。开发替身必须显式设置 `KB_EMBEDDING_MODE=development`，生产禁止此模式。`KB_AUTO_CREATE_SCHEMA=false`，通过显式命令建表。

内嵌Chroma只能由一个API worker持有整个数据目录；不得多进程共享或在该目录上再起Chroma服务。持久化挂载 `/app/.data`，同时备份关系库及该目录；恢复时必须来自同一备份窗口。上传/解析/索引限制由 `KB_MAX_*`、处理租约和并发配置控制。

## 验证与发布

```bash
cd knowledge_base/backend
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev python -m unittest discover -s tests -v
cd ../frontend
pnpm run lint
pnpm run format:check
pnpm run build
```

生产编排、数据库账号初始化和容量预算见 [部署说明](../deploy/README.md)。
