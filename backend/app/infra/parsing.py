"""文件格式识别与文本提取。

⚠️ **不信任扩展名与 `Content-Type`，一律依据文件头魔数判断**
（见 05-接口设计 §5.3）。扩展名可以随便改，请求头可以随便填，只有文件内容
的第一段字节是改不掉的。

**文本化分流**（见 03-概要设计 §5.1）：文本型 PDF / DOCX 直接解析，
**不做 OCR** —— 对已含文本的文件做 OCR 只会引入识别误差。
图片与扫描件无法本地提取，返回 `None`，由上层交给 OCR 能力处理。
"""

from __future__ import annotations

import io
import zipfile
from enum import StrEnum

from app.core.errors import BusinessError, ErrorCode


class FileFormat(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    JPEG = "jpeg"
    PNG = "png"

    @property
    def mime_type(self) -> str:
        return {
            FileFormat.PDF: "application/pdf",
            FileFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            FileFormat.JPEG: "image/jpeg",
            FileFormat.PNG: "image/png",
        }[self]

    @property
    def is_text_extractable(self) -> bool:
        """能否**本地**提取文本。图片需要 OCR，不在此列。"""
        return self in (FileFormat.PDF, FileFormat.DOCX)


# ---- 魔数 ----

_PDF_MAGIC = b"%PDF-"
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# DOCX 是 ZIP 容器，其签名与普通 zip 相同，因此需要进一步确认内部结构
_ZIP_MAGIC = b"PK\x03\x04"


def _looks_like_docx(data: bytes) -> bool:
    """ZIP 签名不够 —— 必须确认它确实是 Word 文档。

    否则 `.xlsx`、`.zip` 都会被当作 `.docx` 接受，与"不信任扩展名"的初衷相悖。
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
    except zipfile.BadZipFile, OSError:
        return False
    return "[Content_Types].xml" in names and any(n.startswith("word/") for n in names)


def detect_format(data: bytes) -> FileFormat | None:
    """按魔数判断格式。无法识别时返回 `None`（调用方应回 `41501`）。"""
    if data.startswith(_PDF_MAGIC):
        return FileFormat.PDF
    if data.startswith(_JPEG_MAGIC):
        return FileFormat.JPEG
    if data.startswith(_PNG_MAGIC):
        return FileFormat.PNG
    if data.startswith(_ZIP_MAGIC) and _looks_like_docx(data):
        return FileFormat.DOCX
    return None


def extract_text(data: bytes, fmt: FileFormat) -> str | None:
    """提取纯文本。

    返回 `None` 表示**本地无法提取**（图片、扫描件），应由上层走 OCR；
    返回空字符串表示"能解析但里面没有文本"（例如纯图形 PDF），
    两者含义不同，调用方需分别处理。
    """
    if fmt is FileFormat.PDF:
        return _extract_pdf(data)
    if fmt is FileFormat.DOCX:
        return _extract_docx(data)
    return None


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    # ⚠️ 魔数只能证明"开头像 PDF"，不能证明文件完整。损坏的文件必须转成业务错误
    # 返回，否则第三方解析库抛出的各种异常会变成 500，把内部细节暴露出去。
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        raise BusinessError(ErrorCode.PARAM_INVALID, "PDF 内容无法解析，请确认文件未损坏") from exc
    return "\n".join(pages).strip()


def _extract_docx(data: bytes) -> str:
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
        paragraphs = [p.text for p in document.paragraphs]
    except Exception as exc:
        raise BusinessError(ErrorCode.PARAM_INVALID, "Word 内容无法解析，请确认文件未损坏") from exc
    return "\n".join(paragraphs).strip()
