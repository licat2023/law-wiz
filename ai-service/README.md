# 智法宝 AI 服务

在独立 Python 3.14 标准环境运行合同审查与法律问答 Agent。服务接收业务后端提供的合同正文、风险规则、问题和已授权的报告追问上下文，通过只读凭据检索知识库。

使用开发或生产 Compose 启动，配置入口见[部署说明](../deploy/README.md)。在本目录使用 `uv run --frozen --extra dev python -m unittest discover -s tests` 验证内网鉴权和两个结构化推理接口。
