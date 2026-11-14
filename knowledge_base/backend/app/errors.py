"""定义供 HTTP 层统一封装的业务错误与入参错误。"""


class AppError(Exception):
    """携带稳定业务码、对外提示和对应的 HTTP 状态。"""

    def __init__(self, code: int, message: str, status: int = 400):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


def invalid(message: str) -> AppError:
    """使用统一业务码 40001 表示无效请求。"""
    return AppError(40001, message)
