"""知识库管理员登录输入。"""

from pydantic import Field

from app.api.responses import Payload


class Login(Payload):
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=72)
