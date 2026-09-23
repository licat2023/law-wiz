"""流水线并发闸门。

**为什么需要**：审查 / 索引 / 问答三条流水线都在后台跑，每条都会占数据库
连接、占内存（PDF 解析可能放大数十倍）。**不限制并发，就等于把
"同时能做多少重活"交给了调用方** —— 任一登录用户反复发起审查即可把
数据库连接池（`pool_size=5`）占满，服务对所有人不可用。

⚠️ **与限流是两个维度，不能互相替代**：
- 限流（`docs/05 §4.5`）约束**请求频率** —— 10 次/分/用户；
- 本闸门约束**同时在跑的流水线数量** —— 无论请求从多少个账号发起。

**取舍（知情项）**：等待者最多等 `ACQUIRE_TIMEOUT_SECONDS` 秒。
等待超时则任务以 `42901` 失败并给出可读原因，**而不是无限期挂住** ——
"失败得清楚"优于"卡住不动"。规模上界由限流保证。

**异步实现**：用 `asyncio.Semaphore` —— 等待时让出事件循环，不占线程。
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("lawwiz.concurrency")

# 同时执行的重活数量。取值依据是**内存**而不是 CPU：
# 部署主机可用内存约 950 MiB，而 PDF 解析 + 生成报告的组合开销可能到百 MB 级。
DEFAULT_MAX_CONCURRENT = 2

# 排队等待上限。超过则任务失败（而不是继续等下去）。
ACQUIRE_TIMEOUT_SECONDS = 60.0


class PipelineGate:
    """有界并发闸门。测试可自行构造小容量/短超时的实例。"""

    def __init__(
        self,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        timeout_seconds: float = ACQUIRE_TIMEOUT_SECONDS,
    ) -> None:
        self._max_concurrent = max_concurrent
        self._timeout_seconds = timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._held = 0  # 已占用槽位，用于检测"release 多于 acquire"

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    async def acquire(self, timeout: float | None = None) -> bool:
        """占用一个槽位。返回是否成功（超时返回 False，不抛异常）。"""
        wait = self._timeout_seconds if timeout is None else timeout
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=wait)
        except TimeoutError:
            logger.warning("流水线并发已满（上限 %d），等待 %.0f 秒后放弃", self._max_concurrent, wait)
            return False
        self._held += 1
        return True

    def release(self) -> None:
        """释放槽位。

        ⚠️ 计数受检：重复释放会直接抛 `ValueError`，
        把"release 多于 acquire"这种错误在测试中立刻暴露，
        而不是让容量被悄悄放大。
        """
        if self._held <= 0:
            raise ValueError("release 多于 acquire：槽位未被占用")
        self._held -= 1
        self._semaphore.release()


# 进程内单例：三条流水线共用同一个上限
pipeline_gate = PipelineGate()
