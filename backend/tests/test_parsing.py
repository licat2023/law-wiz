"""文件解析（`app/infra/parsing.py`）的单元测试。

重点是 **PDF 页数上限**：`pypdf` 逐页 `extract_text` 会把各页文本读入内存后
一次性拼接，页数越多峰值内存越高。上传侧只限制 20 MB，而一个页数极多的
PDF 足以在约 950 MiB 可用内存下触发 OOM —— 必须由解析层兜住。
"""

from __future__ import annotations

import io

import pytest

from app.core.errors import BusinessError, ErrorCode
from app.infra import parsing
from app.infra.parsing import FileFormat


def _docx_bytes(text: str) -> bytes:
    import docx

    document = docx.Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_pdf_reports_page_count_and_text(make_pdf) -> None:
    data = make_pdf(["First page clause", "Second page clause", "Third page clause"])

    parsed = parsing.extract_text(data, FileFormat.PDF)

    assert parsed is not None
    assert parsed.page_count == 3
    assert "Second page clause" in parsed.text


def test_pdf_over_page_limit_is_rejected(make_pdf, monkeypatch) -> None:
    """超出上限时必须抛**业务错误**（而不是让 pypdf 把内存吃干）。"""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_pdf_pages", 2)
    data = make_pdf(["a", "b", "c"])

    with pytest.raises(BusinessError) as exc:
        parsing.extract_text(data, FileFormat.PDF)

    assert exc.value.code == ErrorCode.PARAM_INVALID
    assert "3" in exc.value.message and "2" in exc.value.message


def test_pdf_at_the_limit_is_accepted(make_pdf, monkeypatch) -> None:
    """恰好等于上限应放行（边界不能误伤）。"""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_pdf_pages", 2)
    data = make_pdf(["a", "b"])

    parsed = parsing.extract_text(data, FileFormat.PDF)

    assert parsed is not None and parsed.page_count == 2


def test_broken_pdf_is_a_business_error() -> None:
    """损坏文件仍须转成业务错误，而不是 500。"""
    with pytest.raises(BusinessError) as exc:
        parsing.extract_text(b"%PDF-1.4 garbage", FileFormat.PDF)

    assert exc.value.code == ErrorCode.PARAM_INVALID


def test_docx_has_no_page_count() -> None:
    parsed = parsing.extract_text(_docx_bytes("合同条款"), FileFormat.DOCX)

    assert parsed is not None
    assert "合同条款" in parsed.text
    assert parsed.page_count is None


def test_images_are_deferred_to_ocr() -> None:
    """图片本地无法提取，返回 None（由上层交给 OCR）。"""
    assert parsing.extract_text(b"\xff\xd8\xff\xe0junk", FileFormat.JPEG) is None
