"""审查报告的 PDF 生成。

字体用 reportlab 内置的简体中文 CID 字体 `STSong-Light` —— **不需要外部字体
文件**，不增加镜像体积，已实测中文可正常渲染且可被 pypdf 回读。

⚠️ 报告必须**区分三类依据**（03-概要设计 §5.3）：检索到的法条、人工规则、
模型推断。这是报告可信度的基础 —— 把模型推断写法条，是本项目最不能接受的失败。
"""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

_FONT = "STSong-Light"
_FONT_REGISTERED = False

_PAGE_W, _PAGE_H = A4
_MARGIN_X = 56
_TOP_Y = _PAGE_H - 64
_BOTTOM_Y = 64
_LINE_H = 17

_SOURCE_LABEL = {
    "retrieved_law": "依据：检索到的法条",
    "rule": "依据：审查规则",
    "llm_inference": "依据：模型推断（未找到直接法律依据，仅供参考）",
}

_LEVEL_LABEL = {"high": "高风险", "medium": "中风险", "low": "低风险"}


def _ensure_font() -> None:
    global _FONT_REGISTERED
    if not _FONT_REGISTERED:
        pdfmetrics.registerFont(UnicodeCIDFont(_FONT))
        _FONT_REGISTERED = True


def _wrap(text: str, width_chars: int) -> list[str]:
    """按显示宽度折行。

    中文按 1 个宽度单位、ASCII 按 0.5 计 —— 这样中英混排的折行位置才合理。
    不用 `textwrap` 是因为它按字符数算，中文行会明显偏短。
    """
    lines: list[str] = []
    current = ""
    used = 0.0
    for char in text:
        w = 0.5 if char.isascii() else 1.0
        if used + w > width_chars:
            lines.append(current)
            current, used = char, w
        else:
            current += char
            used += w
    if current:
        lines.append(current)
    return lines or [""]


class _ReportCanvas:
    """带自动翻页与折行的简易排版器。"""

    def __init__(self, buffer: io.BytesIO) -> None:
        _ensure_font()
        self._canvas = canvas.Canvas(buffer, pagesize=A4)
        self._y = _TOP_Y

    def text(self, content: str, *, size: int = 11, indent: int = 0, gap: int = 4) -> None:
        self._canvas.setFont(_FONT, size)
        usable = _PAGE_W - 2 * _MARGIN_X - indent
        width_chars = int(usable / (size * 0.5))
        for line in _wrap(content, width_chars):
            self._new_page_if_needed()
            self._canvas.drawString(_MARGIN_X + indent, self._y, line)
            self._y -= _LINE_H * (size / 11)
        self._y -= gap

    def rule(self) -> None:
        self._new_page_if_needed()
        self._canvas.setLineWidth(0.4)
        self._canvas.line(_MARGIN_X, self._y + 4, _PAGE_W - _MARGIN_X, self._y + 4)
        self._y -= 8

    def _new_page_if_needed(self) -> None:
        if self._y < _BOTTOM_Y:
            self._canvas.showPage()
            self._y = _TOP_Y

    def finish(self) -> None:
        self._canvas.showPage()
        self._canvas.save()


def build_report_pdf(
    *,
    contract_title: str,
    summary: str | None,
    counts: dict[str, int],
    extracted_terms: dict[str, Any] | None,
    risk_points: list[dict[str, Any]],
) -> bytes:
    """生成报告 PDF，返回字节内容（随后按内容寻址存入对象存储）。"""
    buffer = io.BytesIO()
    doc = _ReportCanvas(buffer)

    doc.text("合同风险审查报告", size=18, gap=10)
    doc.text(f"合同名称：{contract_title}", size=12)
    doc.rule()

    doc.text(
        "风险统计："
        f"高风险 {counts.get('high', 0)} 处，"
        f"中风险 {counts.get('medium', 0)} 处，"
        f"低风险 {counts.get('low', 0)} 处",
        size=12,
    )
    if summary:
        doc.text(f"审查结论：{summary}", gap=8)

    if extracted_terms:
        doc.text("一、合同要素", size=14, gap=6)
        labels = {
            "parties": "合同各方",
            "amount": "合同金额",
            "payment_terms": "付款条款",
            "liability": "违约责任",
            "jurisdiction": "争议解决",
            "term": "合同期限",
        }
        for key, label in labels.items():
            value = extracted_terms.get(key)
            if not value:
                continue
            rendered = "；".join(value) if isinstance(value, list) else str(value)
            doc.text(f"· {label}：{rendered}", indent=12)

    doc.text("二、风险点明细", size=14, gap=6)
    if not risk_points:
        doc.text("本次审查未发现风险点。", indent=12)
    for index, point in enumerate(risk_points, start=1):
        level = _LEVEL_LABEL.get(str(point.get("risk_level")), str(point.get("risk_level")))
        doc.text(f"{index}. 【{level}】{point.get('clause_title') or '未标注条款'}", size=12, gap=2)
        if point.get("clause_text"):
            doc.text(f"条款原文：{point['clause_text']}", indent=12)
        doc.text(f"问题：{point.get('description') or ''}", indent=12)
        if point.get("suggestion"):
            doc.text(f"建议：{point['suggestion']}", indent=12)
        if point.get("legal_basis"):
            doc.text(f"法律依据：{point['legal_basis']}", indent=12)
        doc.text(
            _SOURCE_LABEL.get(str(point.get("source_type")), "依据：未标注"),
            indent=12,
            gap=10,
        )

    doc.finish()
    return buffer.getvalue()
