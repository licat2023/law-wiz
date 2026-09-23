"""ORM 模型层面的约定（方言相关，普通接口测试覆盖不到）。

⚠️ 这里放的是**换数据库方言才会暴露**的缺陷：SQLite 支持 `INSERT ... RETURNING`，
MySQL 不支持 —— 只跑 SQLite 的用例看不出差别。实测教训：C-01 发起审查在 MySQL 上
返回 50000（`MissingGreenlet`），而当时 143 个用例全绿。
"""

from __future__ import annotations

import app.models  # noqa: F401  确保全部模型已注册到 metadata
from app.infra.db.base import Base

_TIMESTAMP_COLUMNS = ("created_at", "updated_at", "generated_at")


def test_timestamp_columns_have_python_side_values() -> None:
    """时间戳列必须有 Python 侧取值，不能只依赖 `server_default`。

    MySQL 不支持 `INSERT ... RETURNING`：插入后 SQLAlchemy 不知道服务端写了什么，
    会把列标记为过期；异步会话里读它（例如放进响应体）会触发隐式 SELECT，
    而那次 IO 发生在 greenlet 之外 → `MissingGreenlet`。
    """
    checked = 0
    for table in Base.metadata.tables.values():
        for name in _TIMESTAMP_COLUMNS:
            column = table.columns.get(name)
            if column is None:
                continue
            checked += 1
            assert column.default is not None, (
                f"{table.name}.{name} 缺少 Python 侧默认值："
                "MySQL 上读取它会触发隐式 IO，异步会话将抛 MissingGreenlet"
            )
            if name == "updated_at":
                assert column.onupdate is not None, (
                    f"{table.name}.updated_at 缺少 onupdate：更新时不会刷新（docs/04 §2.3 要求）"
                )
    assert checked >= 15, f"应覆盖全部时间戳列，实际只检查到 {checked} 个（模型是否漏注册？）"
