CONTRACT_TERM_EXTRACTION_PROMPT = """提取合同关键条款。仅输出一个 JSON 对象，不要 Markdown 或额外说明。
JSON 字段为：parties（字符串数组）、amount、payment_terms、liability、jurisdiction、term；未知字段使用 null 或空数组。"""

CONTRACT_RISK_ANALYSIS_PROMPT = """依据提供的法条与风险规则识别合同风险。仅输出一个 JSON 对象，不要 Markdown 或额外说明。
对象必须含 risk_points 数组；每项包含 risk_level（high/medium/low）、description、source_type（retrieved_law/rule/llm_inference），其余字段可选。"""
