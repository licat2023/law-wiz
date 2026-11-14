"""文档解析的唯一封装；偏移以保存的解析全文为准。"""

import io
import re
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

from app.errors import AppError, invalid


@dataclass
class TextBlock:
    start: int
    end: int
    title_path: str = ""
    page_number: int | None = None


@dataclass
class ParsedDocument:
    text: str
    format: str
    blocks: list[TextBlock]
    page_count: int | None = None

    def block_data(self):
        return [asdict(block) for block in self.blocks]


def _push_heading(path: list[tuple[int, str]], level: int, title: str):
    while path and path[-1][0] >= level:
        path.pop()
    path.append((level, title))


def markdown_blocks(text: str) -> list[TextBlock]:
    headers = []
    fence = None
    offset = 0
    for line in text.splitlines(keepends=True):
        marker = re.match(r" {0,3}(`{3,}|~{3,})(.*)", line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        elif marker:
            fence = marker[1]
        elif match := re.match(r" {0,3}(#{1,6})[ \t]+(.+)", line):
            headers.append((offset, len(match[1]), match[2].strip()))
        offset += len(line)
    if not headers:
        return [TextBlock(0, len(text))]
    blocks = []
    path = []
    if headers[0][0]:
        blocks.append(TextBlock(0, headers[0][0]))
    for i, (start, level, title) in enumerate(headers):
        _push_heading(path, level, title)
        end = headers[i + 1][0] if i + 1 < len(headers) else len(text)
        blocks.append(TextBlock(start, end, " / ".join(title for _, title in path)))
    return blocks


def extract_document(
    data: bytes,
    filename: str,
    *,
    max_bytes: int = 20 * 1024 * 1024,
    max_pages: int = 300,
    max_chars: int = 2_000_000,
    max_unpacked_bytes: int = 64 * 1024 * 1024,
) -> ParsedDocument:
    if not data or len(data) > max_bytes:
        raise invalid("文件为空或超过上传大小上限")
    fmt = Path(filename).suffix.lower().lstrip(".")
    try:
        if fmt in {"md", "markdown", "txt"}:
            if data.startswith((b"%PDF-", b"PK\x03\x04")) or b"\x00" in data:
                raise invalid("文件内容与扩展名不符")
            text = data.decode("utf-8-sig")
            blocks = markdown_blocks(text) if fmt != "txt" else [TextBlock(0, len(text))]
            result = ParsedDocument(text, "markdown" if fmt in {"md", "markdown"} else "txt", blocks)
        elif fmt == "docx":
            result = _docx(data, max_unpacked_bytes)
        elif fmt == "pdf":
            result = _pdf(data, max_pages, max_chars)
        else:
            raise invalid("支持 DOCX、文本型 PDF、Markdown 和 UTF-8 TXT；旧 DOC 请先另存为 DOCX")
    except AppError:
        raise
    except Exception as exc:
        raise invalid("文件无法解析，请检查格式、编码或文件是否损坏") from exc
    if not result.text.strip():
        raise invalid("未提取到正文；扫描件需要先转换为文本，当前不支持 OCR")
    if len(result.text) > max_chars:
        raise invalid("解析文本超过长度上限")
    return result


def _docx(data: bytes, max_unpacked: int) -> ParsedDocument:
    import docx
    from docx.table import Table

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(info.file_size for info in archive.infolist()) > max_unpacked:
            raise invalid("Word 解压后大小超过处理上限")
        if "word/document.xml" not in archive.namelist():
            raise invalid("文件内容不是有效 DOCX")
    document = docx.Document(io.BytesIO(data))
    parts = []
    blocks = []
    cursor = 0
    title = []
    for block in document.iter_inner_content():
        if isinstance(block, Table):
            body = "\n".join("\t".join(cell.text for cell in row.cells) for row in block.rows)
        else:
            body = block.text
            style = block.style.name if block.style else ""
            if style.startswith("Heading ") and style[8:].isdigit():
                level = int(style[8:])
                _push_heading(title, level, body)
        if not body.strip():
            continue
        if parts:
            cursor += 1
        blocks.append(TextBlock(cursor, cursor + len(body), " / ".join(value for _, value in title)))
        parts.append(body)
        cursor += len(body)
    return ParsedDocument("\n".join(parts), "docx", blocks)


def _pdf(data: bytes, max_pages: int, max_chars: int) -> ParsedDocument:
    from pypdf import PdfReader

    if not data.startswith(b"%PDF-"):
        raise invalid("文件内容不是有效 PDF")
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise invalid("请先解除 PDF 密码保护")
    if len(reader.pages) > max_pages:
        raise invalid("PDF 页数超过处理上限")
    parts, blocks, cursor = [], [], 0
    for i, page in enumerate(reader.pages):
        content = page.get_contents()
        if content is not None and len(content.get_data()) > 16 * 1024 * 1024:
            raise invalid("PDF 单页内容超过处理上限")
        body = page.extract_text() or ""
        if parts:
            cursor += 1
        blocks.append(TextBlock(cursor, cursor + len(body), page_number=i + 1))
        parts.append(body)
        cursor += len(body)
        if cursor > max_chars:
            raise invalid("解析文本超过长度上限")
    return ParsedDocument("\n".join(parts), "pdf", blocks, len(reader.pages))
