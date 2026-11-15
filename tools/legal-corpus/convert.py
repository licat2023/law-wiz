"""在独立工具环境中将公开法规原件转换成可入库的 Markdown。"""

import hashlib
import re
from importlib.metadata import version

from storage import read_json, write_bytes, write_json

CHINESE_NUMBER = "一二三四五六七八九十百千万零〇0-9"
ARTICLE = re.compile(
    rf"^(?:#{{1,6}}\s+)?(?:\*\*\s*)?(第\s*[{CHINESE_NUMBER}]+\s*条(?:之[{CHINESE_NUMBER}]+)?)"
    r"(?:\s*\*\*|(?=\s|$))\s*(.*)$"
)
SECTION = re.compile(rf"^(?:#{{1,6}}\s+)?\**(第\s*[{CHINESE_NUMBER}]+\s*[编章节])\s*(.*?)\**$")
PAGE_NUMBER = re.compile(r"^(?:[-—]\s*\d+\s*[-—]|第\s*\d+\s*页(?:\s*/\s*共?\s*\d+\s*页)?)$")


def clean_markdown(text):
    """规范章和条的行首标识，保留段落、条序和 Markdown 表格。"""
    paragraphs = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "<!-- image -->" or PAGE_NUMBER.fullmatch(line):
            continue
        if match := ARTICLE.fullmatch(line):
            article, body = match.groups()
            paragraphs.extend(("", "### " + re.sub(r"\s+", "", article), ""))
            if body:
                if line.startswith("**") and body.endswith("**"):
                    body = body.removesuffix("**").rstrip()
                paragraphs.append(body)
        elif match := SECTION.fullmatch(line):
            section, label = match.groups()
            heading = re.sub(r"\s+", "", section)
            paragraphs.extend(("", f"## {heading} {label}".rstrip(), ""))
        else:
            paragraphs.append(raw_line.rstrip())
    refined = re.sub(r"\n{3,}", "\n\n", "\n".join(paragraphs)).strip()
    if len(re.findall(r"[\u3400-\u9fff]", refined)) < 8 or refined.count("\ufffd") > 3:
        raise ValueError("正文为空或含异常字符")
    return refined + "\n"


def make_converter(models):
    """启用 CPU 文本型 PDF 转换及表格识别，模型由本地目录提供。"""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import AcceleratorDevice, AcceleratorOptions, PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(
        do_ocr=False,
        artifacts_path=models,
        document_timeout=120,
        accelerator_options=AcceleratorOptions(num_threads=4, device=AcceleratorDevice.CPU),
    )
    return DocumentConverter(
        allowed_formats=[InputFormat.HTML, InputFormat.DOCX, InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
    )


def convert_file(converter, path):
    """返回结构化 Markdown，并将部分转换、异常或空正文报告为失败。"""
    from docling.datamodel.base_models import ConversionStatus

    result = converter.convert(path, raises_on_error=False, max_num_pages=120, max_file_size=20 * 1024 * 1024)
    if result.status is not ConversionStatus.SUCCESS:
        raise ValueError(f"Docling 转换状态为 {result.status.value}")
    return clean_markdown(result.document.export_to_markdown())


def convert_batch(root, *, fmt, models, only_id=None):
    """读取采集清单并记录每条转换结果。原件由采集阶段独立保存。"""
    manifest = read_json(root / "manifest.json")
    if not manifest:
        raise ValueError("未找到采集清单")
    records = manifest["records"]
    if only_id and only_id not in records:
        raise ValueError("指定来源 ID 不在采集清单中")
    path = root / "conversion.json"
    converted = read_json(path, {})
    converter = None
    results = []
    for item_id, item in records.items():
        if only_id and item_id != only_id:
            continue
        if item["status"] != "saved":
            continue
        assets = [item["body"], *item["attachments"]]
        asset = next((candidate for candidate in assets if candidate["format"] == fmt), None)
        result = {"id": item_id, "status": "failed"}
        if asset is None:
            result["error"] = f"没有 {fmt} 原件"
        elif fmt == "pdf" and (models is None or not models.is_dir()):
            result["error"] = "转换 PDF 需要预下载模型后提供 --models"
        else:
            original = root / asset["path"]
            try:
                if hashlib.sha256(original.read_bytes()).hexdigest() != asset["sha256"]:
                    raise ValueError("原件摘要与清单不一致")
                if converter is None:
                    converter = make_converter(models)
                content = convert_file(converter, original).encode()
                digest = hashlib.sha256(content).hexdigest()
                target = f"markdown/{digest}.md"
                write_bytes(root / target, content)
                result.update(
                    status="converted",
                    document_id=item_id,
                    input_sha256=asset["sha256"],
                    output_sha256=digest,
                    path=target,
                    docling_version=version("docling"),
                )
            except (OSError, RuntimeError, ValueError) as exc:
                result["error"] = str(exc)
        converted[item_id] = result
        results.append(result)
        write_json(path, converted)
    return results
