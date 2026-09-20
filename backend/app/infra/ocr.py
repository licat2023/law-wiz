"""OCR 能力的唯一封装。

约定与 `llm.py` 相同：
- 外部能力单点封装（业务代码不得直接调用任何 OCR 厂商 SDK）；
- AI 队友接入真实云端 OCR（`ocr_provider=cloud`）时**只改本文件内部**；
- 调用方用「模块属性」写法（`from app.infra import ocr` + `ocr.ocr_extract_text(...)`）。

本地 OCR 不在任何一期（服务器内存装不下，见 ADR-0003）。
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.errors import BusinessError, ErrorCode

_settings = get_settings()


def ocr_extract_text(data: bytes) -> str:
    """对图片 / 扫描件做文字识别，返回纯文本。

    错误行为约定：
    - 能力未接入（`ocr_provider=stub`）→ `BusinessError(OCR_UNAVAILABLE)`；
    - 已接入但返回无法解析 → `BusinessError(OCR_BAD_RESPONSE)`。
    """
    if _settings.ocr_provider == "stub":
        raise BusinessError(ErrorCode.OCR_UNAVAILABLE, "OCR 能力尚未接入，无法识别图片文字")
    raise BusinessError(ErrorCode.OCR_UNAVAILABLE, f"OCR 提供方 {_settings.ocr_provider!r} 的实现尚未落地")
