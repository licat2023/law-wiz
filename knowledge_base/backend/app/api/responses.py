"""共享的知识库请求基类及响应体。"""

from pydantic import BaseModel, ConfigDict


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Envelope[T](BaseModel):
    code: int = 0
    data: T | None = None
    request_id: str = ""
    message: str = ""


def ok(request, data):
    """封装成功结果并关联请求追踪号。"""
    return {"code": 0, "data": data, "request_id": request.state.request_id}


def page(items, total, page_number, page_size):
    return {"items": items, "total": total, "page": page_number, "page_size": page_size}
