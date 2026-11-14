"""批量远程 embeddings 接入；向量空间配置形成稳定指纹。"""

import hashlib
import math

import httpx

from app.errors import AppError


def _normalize(vector: list[float], dimensions: int) -> list[float]:
    if (
        not isinstance(vector, list)
        or len(vector) != dimensions
        or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector)
    ):
        raise AppError(50201, "嵌入服务返回的向量维度或数值无效", 502)
    scale = max(map(abs, vector))
    if not scale:
        raise AppError(50201, "嵌入服务返回了零向量", 502)
    scaled = [v / scale for v in vector]
    norm = math.sqrt(sum(v * v for v in scaled))
    return [v / norm for v in scaled]


class RemoteEmbedding:
    def __init__(self, client: httpx.AsyncClient, base_url: str, key: str, model: str, dimensions: int):
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.key = key
        self.model = model
        self.dimensions = dimensions
        self.fingerprint = hashlib.sha256(
            f"remote:{self.base_url}:{model}:{dimensions}:l2".encode()
        ).hexdigest()[:24]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        result = []
        for offset in range(0, len(texts), 64):
            batch = texts[offset : offset + 64]
            try:
                response = await self.client.post(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.key}"},
                    json={"model": self.model, "input": batch},
                )
                response.raise_for_status()
                items = response.json()["data"]
                if (
                    not isinstance(items, list)
                    or len(items) != len(batch)
                    or sorted(i["index"] for i in items) != list(range(len(batch)))
                ):
                    raise ValueError("invalid indices")
                result.extend(
                    _normalize(i["embedding"], self.dimensions)
                    for i in sorted(items, key=lambda i: i["index"])
                )
            except AppError:
                raise
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                raise AppError(50201, "嵌入服务不可用或返回格式无效，请检查模型配置后重试", 502) from exc
        return result


class DevelopmentEmbedding:
    """明确开发/测试模式使用的流程替身，不提供语义质量。"""

    dimensions = 16
    fingerprint = "development-hash-16-v1"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            _normalize([b / 127.5 - 1 for b in hashlib.sha256(text.encode()).digest()[:16]], 16)
            for text in texts
        ]
