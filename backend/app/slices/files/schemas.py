"""文件切片的对外契约（Pydantic 模型）。

字段与 05-接口设计 §5.3 逐字一致；ID 一律为**字符串**（见 §3.4）。
"""

from __future__ import annotations

from pydantic import BaseModel


class FileData(BaseModel):
    """B-02 响应，也是 B-01 响应的主体部分。"""

    file_id: str
    original_name: str | None = None
    byte_size: int
    mime_type: str | None = None
    sha256: str


class UploadFileData(FileData):
    """B-01 响应。多一个 `is_duplicate`。"""

    is_duplicate: bool
