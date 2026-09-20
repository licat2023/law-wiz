"""全部 ORM 模型。

⚠️ 本模块**必须导入所有模型**：Alembic 的 `--autogenerate` 依赖
`Base.metadata` 中已注册的表，漏导入任何一张表都会导致迁移脚本缺表。

新增切片的负责人各自在此登记自己的模型（见 `app/slices/README.md` 步骤 2）。
"""

from __future__ import annotations

from app.infra.db.base import Base
from app.models.contract import Contract, ContractVersion
from app.models.file import FileObject
from app.models.user import User, UserProfile

__all__ = [
    "Base",
    "Contract",
    "ContractVersion",
    "FileObject",
    "User",
    "UserProfile",
]
