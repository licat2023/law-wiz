"""使用知识库公开 API 幂等创建语料并按当前修订提交更新。"""

import hashlib

import httpx

from storage import read_json, write_json


class KnowledgeBaseError(ValueError):
    """知识库响应中的业务错误，保留错误码供修订冲突判断。"""

    def __init__(self, code, message):
        super().__init__(f"知识库错误 {code}，{message}")
        self.code = code


def request_document(client, method, path, **kwargs):
    """按响应体 code 判断成败并返回 data。"""
    response = client.request(method, path, **kwargs)
    try:
        envelope = response.json()
        code = envelope["code"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"知识库返回无效响应，HTTP {response.status_code}") from exc
    if code != 0:
        raise KnowledgeBaseError(code, envelope.get("message", "请求失败"))
    return envelope["data"]


def _same_document(remote, payload):
    return all((remote[k] or "").strip() == payload[k].strip() for k in ("title", "content")) and (
        remote.get("metadata") == payload["metadata"]
    )


def _persist(state_path, state, key, remote):
    state[key] = {"document_id": remote["id"], "revision": remote["revision"]}
    write_json(state_path, state)


def upload(client, endpoint, state_path, key, payload):
    """提交单条记录，恢复中断创建，并保留并发编辑结果供人工核对。"""
    state = read_json(state_path, {})
    entry = state.get(key)
    if entry is None or "pending" in entry:
        pending = entry["pending"] if entry else payload
        if entry is None:
            state[key] = {"pending": pending}
            write_json(state_path, state)
        idempotency_key = "legal-corpus-" + hashlib.sha256(key.encode()).hexdigest()
        remote = request_document(
            client, "POST", endpoint, json=pending, headers={"Idempotency-Key": idempotency_key}
        )
        _persist(state_path, state, key, remote)
        if pending == payload:
            return "created", remote
        entry = state[key]
    path = f"{endpoint}/{entry['document_id']}"
    remote = request_document(client, "GET", path)
    if _same_document(remote, payload):
        _persist(state_path, state, key, remote)
        return "skipped", remote
    if remote["revision"] != entry["revision"]:
        raise ValueError(f"修订冲突，记录为 {entry['revision']}，服务端为 {remote['revision']}")
    try:
        result = request_document(client, "PATCH", path, json=payload | {"revision": remote["revision"]})
    except KnowledgeBaseError as exc:
        if exc.code != 40901:
            raise
        result = request_document(client, "GET", path)
        if not _same_document(result, payload):
            raise ValueError(f"修订冲突，服务端当前修订为 {result['revision']}") from exc
    _persist(state_path, state, key, result)
    return "updated", result


def ingest_batch(root, *, api, token, kb_id, only_id=None):
    """将当前采集批次的已转换条目写入指定库，记录服务端索引状态。"""
    manifest = read_json(root / "manifest.json")
    converted = read_json(root / "conversion.json")
    if not manifest or not converted:
        raise ValueError("缺少采集或转换清单")
    if only_id and only_id not in converted:
        raise ValueError("指定来源 ID 不在转换清单中")
    # 不同服务环境和库使用独立映射，凭据只用于当前 HTTP 请求。
    destination = hashlib.sha256(f"{api.rstrip('/')}:{kb_id}".encode()).hexdigest()[:20]
    state_path = root / f"import-state-{destination}.json"
    endpoint = f"/api/knowledge-bases/{kb_id}/documents"
    results = []
    with httpx.Client(base_url=api, headers={"Authorization": f"Bearer {token}"}, timeout=30) as client:
        for item_id, conversion in converted.items():
            if only_id and item_id != only_id:
                continue
            item = manifest["records"][item_id]
            result = {"id": item_id, "status": "failed"}
            try:
                assets = [item.get("body") or {}, *item.get("attachments", [])]
                hashes = {asset.get("sha256") for asset in assets}
                if (
                    item["status"] != "saved"
                    or conversion["status"] != "converted"
                    or conversion["input_sha256"] not in hashes
                ):
                    raise ValueError("原件尚未转换或已更新，请重新转换")
                content = (root / conversion["path"]).read_bytes()
                if hashlib.sha256(content).hexdigest() != conversion["output_sha256"]:
                    raise ValueError("Markdown 摘要与转换清单不一致")
                payload = {
                    "title": item["title"],
                    "content": content.decode().strip(),
                    "metadata": item["metadata"],
                }
                key = f"{manifest['namespace']}:{item_id}"
                action, remote = upload(client, endpoint, state_path, key, payload)
                result.update(
                    status=action,
                    document_id=remote["id"],
                    revision=remote["revision"],
                    index_status=remote.get("status"),
                    active_index_id=remote.get("active_index_id"),
                )
            except (OSError, ValueError, httpx.TransportError) as exc:
                result["error"] = str(exc)
            results.append(result)
            write_json(root / f"import-run-{destination}.json", results)
    return results
