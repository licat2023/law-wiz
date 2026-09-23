"""智法宝后端应用包。

导入本包即执行运行环境预检（见 `preflight.py`）。
放在这里而不是 `main.py`，是为了让**任何**入口都能生效 ——
uvicorn、pytest、alembic、运维脚本，一个都不能绕过。
"""

from __future__ import annotations

from app.preflight import check_runtime, describe_runtime

check_runtime()

__all__ = ["check_runtime", "describe_runtime"]
