"""知识库写入请求的幂等键和内容摘要。"""

import hashlib
import json

from app.errors import AppError
from app.infrastructure.idempotency_models import IdempotencyRecord


def digest(value):
    body = (
        value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    )
    return hashlib.sha256(body).hexdigest()


async def idempotent(db, principal, scope, key, request_hash, action):
    record_id = (
        digest([principal.application_id, principal.role, principal.knowledge_base_ids, scope, key])
        if key
        else None
    )
    if record_id:
        record = await db.get(IdempotencyRecord, record_id)
        if record:
            if record.request_hash != request_hash:
                raise AppError(40902, "幂等键已用于另一请求", 409)
            return record.result
    result = await action()
    if record_id:
        db.add(IdempotencyRecord(id=record_id, request_hash=request_hash, result=result))
    await db.flush()
    return result
