"""知识库管理员登录输入。"""

from pydantic import Field

from app.api.responses import Payload


class Login(Payload):
    # 这里限制输入字符数。bcrypt 校验仍会拒绝过长的密码字节串。
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=72)
