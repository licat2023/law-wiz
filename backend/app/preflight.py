"""智法宝后端 —— 运行环境预检（preflight）。

**必须在任何其他模块导入之前执行。** 由 `app/__init__.py` 调用，
使检查在任何入口（uvicorn、pytest、alembic、脚本）下都生效。

检查项与理由见 ADR-0009：目标开发机上 `uv venv --python 3.14` 会**选中
free-threaded 解释器**（该解释器满足版本约束但无 GIL），而 `chromadb` 等
核心依赖在 free-threaded 上无法安装 —— 表现为安装中途报 Rust 工具链错误，
与 Python 毫无关系，极难定位。此处 fail-fast，避免把排查成本转嫁给团队。
"""

from __future__ import annotations

import sys
import sysconfig
from typing import Final

# 与 pyproject.toml 的 requires-python 保持一致
MIN_PYTHON: Final = (3, 14)
MAX_PYTHON_EXCLUSIVE: Final = (3, 15)


def _fail(title: str, detail: str, fix: str) -> None:
    message = (
        f"\n{'=' * 68}\n【环境预检未通过】{title}\n{'=' * 68}\n{detail}\n\n修复方式：\n{fix}\n{'=' * 68}\n"
    )
    raise RuntimeError(message)


def check_runtime() -> None:
    """校验解释器版本与构建类型。不通过则拒绝启动。"""
    version = sys.version_info[:2]

    if version < MIN_PYTHON:
        _fail(
            f"Python 版本过低：当前 {version[0]}.{version[1]}，要求 >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
            "本项目使用 Python 3.14 的语法与新特性。",
            "  uv python install 3.14\n  uv venv --python 3.14\n  uv sync",
        )

    if version >= MAX_PYTHON_EXCLUSIVE:
        _fail(
            f"Python 版本过高：当前 {version[0]}.{version[1]}，要求 < {MAX_PYTHON_EXCLUSIVE[0]}.{MAX_PYTHON_EXCLUSIVE[1]}",
            "项目尚未在更高版本上验证。3.15 在编写时仍处于 beta，不作为项目基线。",
            f"  uv venv --python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}\n  uv sync",
        )

    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        _fail(
            "检测到 free-threaded Python（无 GIL 构建）",
            (
                "本项目要求**标准构建**。原因（详见 ADR-0009）：\n"
                "  1. chromadb 等核心依赖在 free-threaded 上无 wheel，需从源码编译并失败；\n"
                "  2. 本项目负载为 I/O 密集型（等 LLM / OCR / 数据库），httpx 请求时会释放 GIL，\n"
                "     free-threading 无收益；\n"
                "  3. free-threaded 构建的内存占用与单线程性能更差，而服务器仅 1.7 GiB 内存。\n\n"
                f"当前解释器：{sys.executable}"
            ),
            (
                "用**绝对路径**指定标准解释器重建环境（不要只写版本号，\n"
                "因为 uv 会优先选中已安装的 free-threaded 解释器）：\n\n"
                "  # 先找到标准解释器路径\n"
                "  uv python list\n\n"
                "  # 用它建环境（把下面的路径换成实际的）\n"
                '  uv venv --python "C:\\Users\\<你>\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe"\n'
                "  uv sync\n"
            ),
        )


def describe_runtime() -> dict[str, object]:
    """供 /health 返回，使部署后能自查运行环境（见 05-接口设计 §5.7）。"""
    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "free_threading": bool(sysconfig.get_config_var("Py_GIL_DISABLED")),
        "implementation": sys.implementation.name,
    }
