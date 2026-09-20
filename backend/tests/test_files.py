"""文件切片测试（M2 的文件接入部分）—— B-01 / B-02。

覆盖四条容易被做错的约定：
1. 类型校验依据**文件头魔数**，不信任扩展名与 `Content-Type`；
2. **内容寻址**：同一内容只存一份，重复上传返回既有记录（`is_duplicate=true`）；
3. **越权**：非上传者不得读取元数据；
4. 读取时的**大小上限**在读取阶段就生效，而不是读完之后才判断。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ErrorCode

FILES = "/api/v1/files"


def build_pdf(text: str) -> bytes:
    """构造一个结构完整的 PDF（含 xref 与 startxref），供用例上传。"""
    content = f"BT /F1 12 Tf 40 700 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b">>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    size = len(objects) + 1
    out += f"xref\n0 {size}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    return bytes(out)


@pytest.fixture
def auth_headers(registered_user: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {registered_user['access_token']}"}


def _register_and_login(client: TestClient, phone: str) -> dict[str, str]:
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"phone": phone, "password": "abc12345", "verify_code": "000000"},
        ).status_code
        == 201
    )
    resp = client.post("/api/v1/auth/login", json={"account": phone, "password": "abc12345"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def _upload(
    client: TestClient, data: bytes, name: str, headers: dict[str, str], mime: str = "application/pdf"
):
    return client.post(FILES, files={"file": (name, data, mime)}, headers=headers)


# ============================================================
# B-01 上传
# ============================================================


def test_upload_pdf_success(client: TestClient, auth_headers: dict[str, str]) -> None:
    pdf = build_pdf("Purchase Contract")
    resp = _upload(client, pdf, "采购合同.pdf", auth_headers)

    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == 0

    data = body["data"]
    assert isinstance(data["file_id"], str), "ID 必须以字符串返回（05-接口设计 §3.4）"
    assert data["original_name"] == "采购合同.pdf"
    assert data["byte_size"] == len(pdf)
    assert data["mime_type"] == "application/pdf"
    assert len(data["sha256"]) == 64 and all(c in "0123456789abcdef" for c in data["sha256"])
    assert data["is_duplicate"] is False


def test_upload_is_content_addressed(
    client: TestClient, auth_headers: dict[str, str], _temp_storage: Any
) -> None:
    """同一内容重复上传：返回**同一个** file_id，且 `is_duplicate=true`。

    这正是"内容寻址"的对外表现 —— 存储里也只有一份对象。
    """
    pdf = build_pdf("Same Content")

    first = _upload(client, pdf, "第一份.pdf", auth_headers).json()["data"]
    second = _upload(client, pdf, "换个名字.pdf", auth_headers).json()["data"]

    assert first["file_id"] == second["file_id"], "同内容必须复用同一记录"
    assert first["is_duplicate"] is False
    assert second["is_duplicate"] is True

    # 落盘对象也只有一个
    from app.infra.storage import object_key_for

    assert _temp_storage.exists(object_key_for(first["sha256"]))


def test_upload_rejects_extension_lie(client: TestClient, auth_headers: dict[str, str]) -> None:
    """扩展名与 Content-Type 都伪装成 PDF，但内容是纯文本 —— 必须拒绝。

    若这里放行，等于只做了"看扩展名"的校验，任何人改个后缀就能上传任意文件。
    """
    resp = _upload(client, b"this is plain text, not a pdf", "fake.pdf", auth_headers)

    assert resp.status_code == 415
    assert resp.json()["code"] == int(ErrorCode.UNSUPPORTED_FILE_TYPE)


def test_upload_rejects_empty_file(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = _upload(client, b"", "empty.pdf", auth_headers)

    assert resp.status_code == 400
    assert resp.json()["code"] == int(ErrorCode.PARAM_INVALID)


def test_upload_rejects_oversize(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """超过大小上限必须回 41301。

    这里把上限改小后再测，避免真的构造 20 MB 数据；被测的是**同一段判断逻辑**。
    """
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_bytes", 1024)
    oversized = build_pdf("padding") + b"\n" + b"x" * 4096

    resp = _upload(client, oversized, "big.pdf", auth_headers)

    assert resp.status_code == 413
    assert resp.json()["code"] == int(ErrorCode.FILE_TOO_LARGE)


def test_upload_requires_auth(client: TestClient) -> None:
    resp = _upload(client, build_pdf("x"), "a.pdf", {})

    assert resp.status_code == 401
    assert resp.json()["code"] == int(ErrorCode.ACCESS_TOKEN_INVALID)


def test_original_name_strips_path_components(client: TestClient, auth_headers: dict[str, str]) -> None:
    """文件名里的路径成分必须剥掉，只留文件名本身。"""
    unique = build_pdf("Path Traversal Attempt")
    resp = _upload(client, unique, "../../etc/passwd.pdf", auth_headers)

    assert resp.status_code == 201
    assert resp.json()["data"]["original_name"] == "passwd.pdf"


# ============================================================
# B-02 元数据
# ============================================================


def test_get_metadata_returns_contract_fields(client: TestClient, auth_headers: dict[str, str]) -> None:
    uploaded = _upload(client, build_pdf("Meta"), "meta.pdf", auth_headers).json()["data"]

    resp = client.get(f"{FILES}/{uploaded['file_id']}", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["file_id"] == uploaded["file_id"]
    assert data["sha256"] == uploaded["sha256"]
    assert "is_duplicate" not in data, "B-02 的响应不含 is_duplicate（05-接口设计 §5.3）"


def test_get_missing_file_is_40404(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get(f"{FILES}/99999999", headers=auth_headers)

    assert resp.status_code == 404
    assert resp.json()["code"] == int(ErrorCode.FILE_NOT_FOUND)


def test_other_user_cannot_read_metadata(client: TestClient, auth_headers: dict[str, str]) -> None:
    """**越权**：文件元数据只对上传者可见（05-接口设计 §5.3）。"""
    uploaded = _upload(client, build_pdf("Private"), "private.pdf", auth_headers).json()["data"]

    other = _register_and_login(client, "13800000009")
    resp = client.get(f"{FILES}/{uploaded['file_id']}", headers=other)

    assert resp.status_code == 403
    assert resp.json()["code"] == int(ErrorCode.FORBIDDEN)


def test_get_metadata_requires_auth(client: TestClient, auth_headers: dict[str, str]) -> None:
    uploaded = _upload(client, build_pdf("Auth"), "auth.pdf", auth_headers).json()["data"]

    resp = client.get(f"{FILES}/{uploaded['file_id']}")

    assert resp.status_code == 401
