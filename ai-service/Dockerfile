FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
WORKDIR /app
RUN python -c "import sysconfig; assert not sysconfig.get_config_var('Py_GIL_DISABLED')"
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY ai_service ./ai_service
RUN groupadd --system app && useradd --system --gid app app
USER app
EXPOSE 8200
CMD ["uvicorn", "ai_service.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8200"]
