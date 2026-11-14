class AppError(Exception):
    def __init__(self, code: int, message: str, status: int = 400):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


def invalid(message: str) -> AppError:
    return AppError(40001, message)
