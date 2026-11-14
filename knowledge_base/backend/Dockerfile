FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/
WORKDIR /app
RUN python -c "import sys, sysconfig; assert sys.version_info[:2] == (3, 14), sys.version; assert not sysconfig.get_config_var('Py_GIL_DISABLED'), 'free-threaded 构建不可用'"
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
RUN uv sync --frozen --no-dev
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && mkdir -p /app/.data && chown -R app:app /app
USER app
EXPOSE 8100
# Chroma持久化目录由此进程独占；不得增加workers或共享给其他进程。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100", "--workers", "1"]
