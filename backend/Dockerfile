# 后端镜像（Python 3.14）。
#
# ⚠️ 三条不能改的约束：
# 1. 基座必须是**标准构建**的 3.14 —— free-threaded 变体装不上部分依赖，且本项目
#    的等待都在外部 API（httpx 会释放 GIL），线程不是瓶颈（ADR-0009）。构建期断言兜底。
# 2. **不装** `torch` / `paddlepaddle` / `paddleocr`：本地 OCR 需 1.2–2 GB 内存，
#    容器会被 OOM Killer 静默杀掉（容量约束见 docs/02 §3.9）。
# 3. 依赖用 `uv.lock` **冻结安装**，保证与开发/CI 一致。

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# 用官方 uv 二进制，版本与仓库开发环境一致（uv.lock 由它生成）
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/

WORKDIR /app

# 构建期断言：基座必须是标准构建的 Python 3.14（ADR-0009）。
# 放在装依赖之前 —— 基座不对就没有继续构建的意义。
RUN python -c "import sys, sysconfig; assert sys.version_info[:2] == (3, 14), sys.version; assert not sysconfig.get_config_var('Py_GIL_DISABLED'), 'free-threaded 构建不可用'"

# 先只拷依赖清单，命中层缓存：源码改动不会导致重装依赖
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# 再拷源码、迁移脚本与 alembic 配置
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

# 非 root 运行；/app/.data 供生产数据卷挂载（本地存储、Chroma 持久化）
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && mkdir -p /app/.data && chown -R app:app /app
USER app

EXPOSE 8000

# --proxy-headers + --forwarded-allow-ips：生产经 1Panel 的 OpenResty 反代，
# 若不开，限流按 IP 计数会把所有请求算作同一来源（见风险清单 #1）。
# 端口只绑定在宿主机 127.0.0.1（见 compose），外部无法直连，故信任全部转发头。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
