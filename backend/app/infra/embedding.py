"""嵌入能力的唯一封装。

stub 实现：**确定性哈希向量** —— 同一文本永远得到同一向量，维度取
`LAWWIZ_EMBEDDING_DIM`。它的检索质量毫无意义，唯一用途是**把检索流程
跑通**（开发与测试）。

真实语义嵌入由 AI 队友在 `embedding_provider=cloud` 时替换本文件内部实现，
签名不变。调用方用「模块属性」写法（见 llm.py 的说明）。
"""

from __future__ import annotations

import hashlib
import math

from app.core.config import get_settings

_settings = get_settings()


def embed(text: str) -> list[float]:
    """把文本映射为向量（stub 版：确定性伪随机向量，已归一化）。"""
    dim = _settings.embedding_dim
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    vector: list[float] = []
    for i in range(dim):
        digest = hashlib.sha256(seed + bytes([i % 256, (i // 256) % 256])).digest()
        value = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
        vector.append(value * 2.0 - 1.0)
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]
