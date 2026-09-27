# Backend 运维工具

## 导入首批核心法律语料

在已完成数据库迁移的环境中执行：

```powershell
cd backend
uv run --extra dev python tools/import_core_legal_corpus.py
```

脚本读取 `core_legal_corpus.json`，按内容哈希跳过已存在的法规，并按 `rule_code`
跳过已存在的风险规则，因此可以重复执行。导入后应通过知识库 D-02 接口触发向量化。

当前包是 MVP 演示种子：含民法典合同相关条文、电子签名法、合同编通则司法解释和
3 条人工风险规则。它不是完整法规库；后续扩充必须保留官方来源 URL、生效日期与
结构化元数据，且不得混入未经授权的大规模裁判文书。
