from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager

from app_metrics import (
    PrometheusMiddleware,
    metrics_response,
    register_prometheus_multiprocess_shutdown,
)
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from starlette.responses import JSONResponse, Response

from app.config import get_settings
from app.logging_config import configure_logging, get_logger
from app.middleware import RequestLoggingMiddleware
from app.middleware.request_logging import get_request_id, get_tenant_id, resolve_inbound_tenant_id
from app.openapi_config import (
    INTERNAL_API_KEY_SECURITY_SCHEME,
    OPENAPI_TAGS,
    OPENAPI_VERSION,
    SERVICE_OPENAPI_DESCRIPTION,
)


def _configure_openapi(app: FastAPI, *, title: str, description: str) -> None:
    if not get_settings().enable_openapi_docs:
        return

    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        from fastapi.openapi.utils import get_openapi

        schema = get_openapi(
            title=title, version=OPENAPI_VERSION, description=description,
            routes=app.routes, tags=OPENAPI_TAGS,
        )
        components = schema.setdefault("components", {})
        components.setdefault("securitySchemes", {}).update(INTERNAL_API_KEY_SECURITY_SCHEME)
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


def build_service_app(
    *,
    service: str,
    routers: Sequence[APIRouter],
    on_startup: Callable[[], None] | None = None,
    openapi_title: str | None = None,
    openapi_description: str | None = None,
) -> FastAPI:
    """Build a FastAPI app with logging, metrics, correlation and error handlers.

    `on_startup` is an optional bootstrap callable run in a daemon thread at
    startup (e.g. warming a cache) — the reusable seam that replaced a hardcoded
    domain import.
    """
    logger = configure_logging(component=service)
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        register_prometheus_multiprocess_shutdown()
        if on_startup is not None:
            import threading

            threading.Thread(target=on_startup, name=f"{service}-bootstrap", daemon=True).start()
        yield

    title = openapi_title or settings.app_name
    description = openapi_description or SERVICE_OPENAPI_DESCRIPTION
    docs = settings.enable_openapi_docs
    app = FastAPI(
        title=title,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    _configure_openapi(app, title=title, description=description)
    app.add_middleware(
        PrometheusMiddleware,
        service=service,
        tenant_resolver=lambda request: get_tenant_id() or resolve_inbound_tenant_id(request),
    )
    app.add_middleware(RequestLoggingMiddleware)
    for router in routers:
        app.include_router(router)

    @app.get("/metrics")
    def prometheus_metrics() -> Response:
        return metrics_response()

    @app.exception_handler(HTTPException)
    async def log_http_exception(request: Request, exc: HTTPException) -> Response:
        if exc.status_code >= 400:
            get_logger().warn(
                "api.response.error",
                {
                    "requestId": request.headers.get("X-Request-Id") or get_request_id() or None,
                    "method": request.method,
                    "path": request.url.path,
                    "status": exc.status_code,
                    "detail": exc.detail,
                },
            )
        return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def log_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        get_logger().error(
            "api.unhandled_exception",
            exc,
            {
                "requestId": request.headers.get("X-Request-Id") or get_request_id() or None,
                "method": request.method,
                "path": request.url.path,
            },
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    logger.info("api.application.started", {"env": settings.app_env, "service": service})
    return app
