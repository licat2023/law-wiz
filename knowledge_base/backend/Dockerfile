# 独立知识库镜像。原文件和嵌入索引使用 /app/.data 持久化，关系库单独配置。
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/
WORKDIR /app
# Chroma 依赖标准构建的 Python 3.14，在安装依赖前检查解释器。
RUN python -c "import sys, sysconfig; assert sys.version_info[:2] == (3, 14), sys.version; assert not sysconfig.get_config_var('Py_GIL_DISABLED'), 'free-threaded 构建不可用'"
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY scripts ./scripts
RUN uv sync --frozen --no-dev
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && mkdir -p /app/.data && chown -R app:app /app
USER app
EXPOSE 8100
# 内嵌 Chroma 持久化目录由一个进程独占。保持单 worker，并为每个实例使用独立目录。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100", "--workers", "1"]
