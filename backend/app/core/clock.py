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
    """序列化为接口返回用的字符串；None 原样返回。"""
    return value.isoformat() if value else None
