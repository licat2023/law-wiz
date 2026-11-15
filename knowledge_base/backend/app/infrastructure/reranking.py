"""通过独立服务的 TEI /rerank 接口调用 Cross-Encoder。"""

import asyncio
import math

import httpx

from app.errors import AppError


class RemoteReranker:
    """提供整批的分数；响应异常或超过总时限时由检索层保留融合顺序。"""

    def __init__(self, client: httpx.AsyncClient, endpoint: str, token: str, timeout: float):
        self.client = client
        self.endpoint = endpoint
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.timeout = timeout

    async def rank(self, query: str, texts: list[str]) -> list[float]:
        """按输入位置返回 0–1 分数，服务返回的排序由调用方复核。"""
        try:
            async with asyncio.timeout(self.timeout):
                response = await self.client.post(
                    self.endpoint,
                    headers=self.headers,
                    json={"query": query, "texts": texts, "truncate": True, "raw_scores": False},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                ranks = response.json()
                if not isinstance(ranks, list) or len(ranks) != len(texts):
                    raise ValueError("unexpected result count")
                scores = {}
                for rank in ranks:
                    index, score = rank["index"], rank["score"]
                    if (
                        type(index) is not int
                        or not 0 <= index < len(texts)
                        or index in scores
                        or type(score) not in (int, float)
                        or not math.isfinite(score)
                        or not 0 <= score <= 1
                    ):
                        raise ValueError("invalid rerank score or index")
                    scores[index] = float(score)
                return [scores[i] for i in range(len(texts))]
        except (TimeoutError, ValueError, KeyError, TypeError, OverflowError, httpx.HTTPError) as exc:
            raise AppError(50201, "重排服务不可用或返回格式无效", 502) from exc
