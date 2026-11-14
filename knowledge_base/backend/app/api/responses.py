"""共享的知识库请求基类及响应体。"""

from pydantic import BaseModel, ConfigDict


class Payload(BaseModel):
    # 请求模型拒绝未声明字段，让拼写错误和旧字段在入参校验时暴露。
    model_config = ConfigDict(extra="forbid")


class Envelope[T](BaseModel):
    # 调用方通过 code 判断业务结果，0 表示成功。
    code: int = 0
    data: T | None = None
    request_id: str = ""
    message: str = ""


def ok(request, data):
    """封装成功结果并关联请求追踪号。"""
    return {"code": 0, "data": data, "request_id": request.state.request_id}


def page(items, total, page_number, page_size):
    """返回列表和分页元数据，其中 total 是过滤后、分页前的总数。"""
    return {"items": items, "total": total, "page": page_number, "page_size": page_size}
