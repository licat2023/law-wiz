"""时间工具。

全项目统一使用**北京时间（UTC+8）的 naive datetime**，与 04-数据库设计 §2.1
的存储约定一致：`DATETIME(3)` 存北京时间，**不使用 `TIMESTAMP`**，
避免会话时区导致的隐式转换。
"""

from __future__ import annotations

import datetime as dt

_BEIJING = dt.timezone(dt.timedelta(hours=8))


def now_beijing() -> dt.datetime:
    """当前北京时间（不带时区信息，直接入库）。"""
    return dt.datetime.now(_BEIJING).replace(tzinfo=None)


def to_iso(value: dt.datetime | None) -> str | None:
    """序列化为接口返回用的时间字符串。**所有切片都必须用它，不要自己 isoformat。**

    ⚠️ 契约要求（05-接口设计 §3）：**ISO 8601 带时区偏移**，如
    `2026-09-20T15:58:19.637+08:00`。

    库里存的是**北京时间（naive）**，因此这里补上 `+08:00`；微秒截断为**毫秒**，
    与 `DATETIME(3)` 的精度一致。

    为什么必须带偏移：不带偏移的时间字符串会被 `new Date()` 按**浏览器本地时区**
    解释 —— 时区不是 +08:00 的机器上，时间就显示错了。
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=_BEIJING)
    return value.replace(microsecond=(value.microsecond // 1000) * 1000).isoformat(timespec="milliseconds")
