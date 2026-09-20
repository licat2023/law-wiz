"""AI 能力接缝的测试（`app/infra/llm.py`、`ocr.py`、`embedding.py`、`vector.py`）。

这组用例的价值：**把"AI 封装的行为契约"固定下来**。队友替换封装内部实现时，
这些用例必须继续通过 —— 否则业务代码依赖的错误行为就变了。

⚠️ 不测"模型答得好不好"，只测**接口行为**：能力未接入时怎么失败、
开发替身返回什么形状、向量检索能否往返。
"""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.errors import BusinessError, ErrorCode
from app.infra import embedding, llm, ocr, vector

# ============================================================
# llm
# ============================================================


def test_llm_stub_raises_structured_failure() -> None:
    """能力未接入时抛 `LLM_UNAVAILABLE`，而不是返回假数据或抛 500。"""
    with pytest.raises(BusinessError) as excinfo:
        llm.complete_structured("system", "user", {"properties": {}})

    assert excinfo.value.code == ErrorCode.LLM_UNAVAILABLE


def test_llm_fake_provider_returns_schema_shaped_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """`fake` 是**开发/演示替身**：按 schema 形状返回占位结论，使链路可跑通。"""
    monkeypatch.setattr(get_settings(), "llm_provider", "fake")

    terms = llm.complete_structured("s", "u", {"properties": {"parties": {}}})
    assert terms["parties"], "条款提取的占位结果应包含 parties"

    analysis = llm.complete_structured("s", "u", {"properties": {"risk_points": {}}})
    assert analysis["risk_points"], "风险分析的占位结果应包含风险点"
    # 三种依据类型都要出现，前端的区分呈现才有得测
    source_types = {point["source_type"] for point in analysis["risk_points"]}
    assert source_types == {"retrieved_law", "rule", "llm_inference"}


def test_production_rejects_fake_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """**生产环境必须拒绝 fake** —— 写死的假风险结论比"暂时不可用"危险得多。"""
    from app.main import _validate_startup_config

    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "allow_fixed_verify_code", False)
    monkeypatch.setattr(settings, "jwt_secret", "a-real-production-secret")
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "llm_provider", "fake")

    with pytest.raises(RuntimeError, match="fake"):
        _validate_startup_config()


# ============================================================
# ocr
# ============================================================


def test_ocr_stub_raises_structured_failure() -> None:
    with pytest.raises(BusinessError) as excinfo:
        ocr.ocr_extract_text(b"\xff\xd8\xff")

    assert excinfo.value.code == ErrorCode.OCR_UNAVAILABLE


# ============================================================
# embedding + vector
# ============================================================


def test_embedding_is_deterministic_and_normalized() -> None:
    """stub 嵌入必须**确定性**：同一文本永远同一向量（否则缓存与检索不可复现）。"""
    first = embedding.embed("违约责任")
    second = embedding.embed("违约责任")

    assert first == second
    assert len(first) == get_settings().embedding_dim
    assert abs(sum(v * v for v in first) - 1.0) < 1e-6, "向量应已归一化"


def test_vector_memory_backend_round_trip() -> None:
    """内存后端是**真实可用**的：索引后能检索回来（检索质量无意义）。"""
    vector.clear()
    vector.index_document(
        7,
        [
            {"chunk_id": "7-0", "text": "当事人应当按照约定全面履行自己的义务"},
            {"chunk_id": "7-1", "text": "合同的成立时间以最后一方签字盖章为准"},
        ],
    )

    hits = vector.search("履行 义务", top_k=2)

    assert len(hits) == 2
    assert {hit.chunk_id for hit in hits} == {"7-0", "7-1"}
    assert all(hit.doc_id == 7 for hit in hits)
    assert hits[0].score >= hits[1].score, "结果应按相似度降序"

    vector.clear()
    assert vector.search("任何内容", top_k=5) == [], "清空后不应有命中"


def test_vector_unsupported_backend_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """未实现的后端必须显式报错，而不是静默降级成内存实现。"""
    monkeypatch.setattr(get_settings(), "vector_backend", "chroma")

    with pytest.raises(BusinessError) as excinfo:
        vector.search("x")

    assert excinfo.value.code == ErrorCode.VECTOR_UNAVAILABLE
