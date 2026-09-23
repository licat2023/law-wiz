"""流水线并发闸门的测试（`app/infra/concurrency.py`）。

⚠️ 这里验证的是**闸门本身**的行为，不涉及真实流水线 —— 后者见
`test_review.py::test_pipeline_fails_task_when_concurrency_is_full`。
"""

from __future__ import annotations

import pytest

from app.infra.concurrency import PipelineGate, pipeline_gate


async def test_gate_enforces_capacity() -> None:
    """容量用尽后必须**超时返回 False**，而不是阻塞等待 —— 阻塞会占住事件循环。"""
    gate = PipelineGate(max_concurrent=2, timeout_seconds=0.05)

    assert await gate.acquire() is True
    assert await gate.acquire() is True
    assert await gate.acquire() is False, "第三个应超时失败"

    gate.release()
    assert await gate.acquire() is True, "释放后应能再取到"


async def test_release_twice_raises() -> None:
    """重复 release 必须立刻报错。

    闸门自带占用计数就是为了这个：否则"释放多于占用"会**悄悄放大容量**，
    并发上限失效且无任何征兆。
    """
    gate = PipelineGate(max_concurrent=1)

    assert await gate.acquire() is True
    gate.release()

    with pytest.raises(ValueError):
        gate.release()


def test_module_gate_has_a_bounded_default() -> None:
    """进程内单例必须有明确的并发上限（不是无限）。"""
    assert pipeline_gate.max_concurrent >= 1
    assert pipeline_gate.max_concurrent <= 8, "上限不该大到失去意义（内存约束下 2 左右合适）"
