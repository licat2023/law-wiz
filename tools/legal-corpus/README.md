# 法规语料工具

使用 Playwright 从公开栏目保存法规正文及附件，用 Docling 生成 Markdown，再通过知识库的文档 API 写入目标库。工具在独立环境运行，默认手动采集，每栏目最多一页，每次最多五条，单路访问。原件、转换产物和日志适合保存在仓库已忽略的 `.data/` 或其他本地目录。

## 安装和采集

在本目录使用标准构建的 Python 3.14，将其绝对路径传给 `uv sync --frozen --python`。锁文件配置 CPU 版模型依赖，支持 Windows 和 Linux。

```powershell
uv run playwright install chromium
uv run python corpus.py --out ../../.data/legal-corpus collect --doc-type regulation --max-pages 2
uv run python corpus.py --out ../../.data/legal-corpus collect --doc-type local_regulation
uv run python corpus.py --out ../../.data/legal-corpus convert
```

`sources.toml` 包含重庆市商务委员会的行政法规和市政府规章栏目。清单以站点发布条目的 ID 标识法规，记录原始链接、附件、可识别的公布及施行和废止日期，并保留原日期供核对。栏目网页发布日期单独保存。站点另发新条目会产生不同的来源 ID，人工核对法规沿革时以来源页面为准。

`manifest.json` 保存已采集条目和失败原因，`collection-run.json` 保存本次计数、结果和页面响应。重跑复用原件，`collect --refresh` 重新读取来源。使用 `collect --only-id <来源ID>` 补采单条，或加上 `--refresh` 核对该条变化。请求仅抓取配置站点的公开链接，并检查其 robots.txt。两个栏目及其访问规则可从来源站点核对。[行政法规栏目](https://sww.cq.gov.cn/zwgk_247/zfxxgkml/lzyj/xzfg/) · [市政府规章栏目](https://sww.cq.gov.cn/zwgk_247/zfxxgkml/lzyj/bmgz/)

## 转换和写入

默认转换采集的 HTML 正文。若清单中有 Word 附件，用 `convert --format docx --only-id <来源ID>` 选择 DOCX。文本型 PDF 保留表格识别，需要先预下载本地模型，建议一次转换一个文件。转换失败的原件仍可在 `artifacts/` 查阅。转换结果及原件摘要保存在 `conversion.json`。

```powershell
uv run docling-tools models download layout tableformer --output-dir ../../.data/docling-models
uv run python corpus.py --out ../../.data/legal-corpus convert --format pdf --models ../../.data/docling-models --only-id <来源ID>
```

配置 `LEGAL_CORPUS_KB_URL` 及有目标库写权限的 `LEGAL_CORPUS_KB_TOKEN`。先确认在管理端选对知识库，建议启用层级分块。用目标库 UUID 执行以下命令。

```powershell
uv run python corpus.py --out ../../.data/legal-corpus ingest --kb-id <知识库UUID>
```

每个输出目录按目标库保存导入状态，首次创建可从中断重放。应保留状态文件并让同一输出目录由一次运行独占。内容及元数据相同会跳过，变化会提交新的文档修订。工具会读取冲突后的服务端版本，只有服务端内容已经与本次提交一致时才接受结果。出现人工编辑或其他差异时，先在管理端核对服务器修订。 `import-run-*.json` 记录导入时的索引状态，索引由知识库后台异步发布。以管理端显示的生效版本和索引任务结果确认最终可检索状态。

## 验证

```powershell
uv run python -m unittest discover -v
uv run ruff check .
uv run ruff format --check .
```
