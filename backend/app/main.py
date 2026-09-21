"""应用入口。

启动顺序：环境预检（在 `app/__init__.py` 里，导入即执行）→ 配置校验 →
建应用 → 中间件 → 异常处理器 → 路由。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.exception_handlers import register_exception_handlers
from app.api.middleware import RequestContextMiddleware
from app.core.config import get_settings
from app.preflight import describe_runtime

_settings = get_settings()

logging.basicConfig(
    level=logging.DEBUG if _settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("lawwiz")


def _validate_startup_config() -> None:
    """启动期配置校验。

    ⚠️ 这些检查的意义在于**把配置错误挡在启动阶段**，而不是让它在运行时
    以"某个用户注册失败"的形式暴露出来。
    """
    problems: list[str] = []

    if _settings.is_production:
        if _settings.allow_fixed_verify_code:
            problems.append(
                "生产环境禁止启用固定验证码（LAWWIZ_ALLOW_FIXED_VERIFY_CODE 必须为 false）。"
                "开发用固定验证码一旦上线，等于任何人可注册任意账号。"
            )
        if _settings.jwt_secret.startswith("dev-only"):
            problems.append("生产环境必须通过 LAWWIZ_JWT_SECRET 提供独立的令牌密钥。")
        if _settings.debug:
            problems.append("生产环境不应开启 debug。")
        if _settings.llm_provider == "fake":
            problems.append(
                "生产环境禁止使用 fake 的 LLM 提供方：它会产出**写死的假风险结论**，"
                "比「暂时不可用」危险得多。请改为 deepseek / ollama，或退回 stub。"
            )

    if _settings.storage_backend == "minio" and not _settings.minio_access_key:
        problems.append("storage_backend=minio 但未配置 minio_access_key。")

    if _settings.llm_provider in ("deepseek", "ollama") and not _settings.llm_api_base:
        problems.append(f"llm_provider={_settings.llm_provider} 但未配置 llm_api_base。")

    if problems:
        detail = "\n".join(f"  - {p}" for p in problems)
        raise RuntimeError(f"\n启动配置校验未通过：\n{detail}\n")


def register_routers(app: FastAPI) -> None:
    """挂载各纵切面路由。

    ⚠️ 新增切片时必须在此登记，否则路由静默不可达。
    """
    from app.slices.auth import router as auth_router
    from app.slices.files import router as files_router
    from app.slices.health import router as health_router
    from app.slices.kb import router as kb_router
    from app.slices.review import router as review_router

    app.include_router(health_router, prefix=_settings.api_prefix)
    app.include_router(auth_router, prefix=_settings.api_prefix)
    app.include_router(files_router, prefix=_settings.api_prefix)
    app.include_router(review_router, prefix=_settings.api_prefix)
    app.include_router(kb_router, prefix=_settings.api_prefix)

    # --- 以下切片已规划但尚未实现，见 app/slices/README.md ---
    # from app.slices.qa import router as qa_router                # C：M3 法律问答


def create_app() -> FastAPI:
    _validate_startup_config()

    app = FastAPI(
        title=f"{_settings.app_name} API",
        version="0.1.0",
        description=(
            "智法宝（law-wiz）—— AI 法律助手平台后端。\n\n"
            "接口契约见 docs/05-接口设计.md；**本页由代码自动生成，是契约的唯一真源**。"
        ),
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        debug=_settings.debug,
    )
    app.state.settings = _settings

    # 中间件顺序：RequestContext 在外，CORS 在内 —— 保证 CORS 的预检请求
    # 也能拿到 request_id 并被记入访问日志
    app.add_middleware(RequestContextMiddleware)
    if not _settings.is_production:
        # 生产由 OpenResty 同源代理，不开启宽泛 CORS（05-接口设计 §8）
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_settings.cors_origins,
            allow_credentials=False,  # 本设计不使用 Cookie（ADR-0010）
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )

    register_exception_handlers(app)
    register_routers(app)

    runtime = describe_runtime()
    logger.info(
        "应用已创建 env=%s python=%s free_threading=%s",
        _settings.app_env,
        runtime["python"],
        runtime["free_threading"],
    )
    return app


app = create_app()
