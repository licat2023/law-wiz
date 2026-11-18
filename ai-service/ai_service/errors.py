"""Errors exchanged with authorized callers of the inference service."""


class InferenceError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
