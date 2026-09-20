"""文件存储的单一封装（内容寻址）。

⚠️ **同一个外部能力只在此处封装**（见仓库根 AGENTS.md「硬性约束」）：
业务代码不得直接调用文件系统的存储路径，也不得分散调用对象存储 SDK。

**内容寻址**：对象路径为 `files/{sha256前两位}/{sha256}`，以内容哈希命名而非
UUID（见 04-数据库设计 §4.1）。由此获得两项性质：天然去重、完整性可自校验。

一期只实现 `local` 后端（配置默认 `LAWWIZ_STORAGE_BACKEND=local`）。
`minio` 后端属 P2 部署阶段 —— 依赖尚未引入，此处显式报错而不是静默降级，
避免"以为存进了对象存储，其实写在本地磁盘"。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import BusinessError, ErrorCode

_settings = get_settings()


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def object_key_for(digest: str) -> str:
    """内容寻址路径：`files/{前两位}/{完整哈希}`。"""
    return f"files/{digest[:2]}/{digest}"


class LocalStorage:
    """落盘存储。对象路径即 `root / object_key`。"""

    def __init__(self, root: str) -> None:
        self._root = Path(root)

    @property
    def bucket(self) -> str:
        # 本地后端没有"桶"的概念；写入一个固定值以满足 file_object.storage_bucket
        # 的非空约束（见 04-数据库设计 §5.3）。
        return "local"

    def _path(self, object_key: str) -> Path:
        return self._root / object_key

    def exists(self, object_key: str) -> bool:
        return self._path(object_key).is_file()

    def put(self, object_key: str, data: bytes) -> None:
        """写入对象。已存在则直接返回（内容寻址下同名必同内容）。

        ⚠️ 先写临时文件再 `replace` 原子改名：否则进程中途被杀会留下**半截文件**，
        而内容寻址的实现假设"存在即完整"，半截文件会永久污染该哈希对应的内容。
        """
        path = self._path(object_key)
        if path.is_file():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(path)

    def get(self, object_key: str) -> bytes:
        path = self._path(object_key)
        if not path.is_file():
            raise BusinessError(ErrorCode.FILE_NOT_FOUND, "文件内容不存在")
        return path.read_bytes()


_storage: LocalStorage | None = None


def get_storage() -> LocalStorage:
    """进程内单例。"""
    global _storage
    if _storage is None:
        if _settings.storage_backend != "local":
            raise RuntimeError(
                f"存储后端 {_settings.storage_backend!r} 尚未实现。"
                "一期仅支持 local；对象存储属 P2 部署阶段（依赖未引入）。"
            )
        _storage = LocalStorage(_settings.storage_local_root)
    return _storage
