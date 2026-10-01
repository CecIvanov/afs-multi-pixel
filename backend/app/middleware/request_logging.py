"""Request correlation + structured access logging.

Mints (or propagates) an X-Request-Id per request, resolves a tenant id from the
path or X-Tenant-Id header, stores both in ContextVars (so worker/outbound code
can read them), logs api.request.received/completed, and echoes X-Request-Id on
the response. Health/metrics probes are skipped to keep logs quiet.

Phase 1 extends resolve_inbound_tenant_id with a shop-domain -> tenant lookup.
"""

from __future__ import annotations

import re
import time
import uuid
from contextvars import ContextVar

from app_metrics import METRICS_PATHS
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging_config import get_logger

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
tenant_id_ctx: ContextVar[str] = ContextVar("tenant_id", default="")

_TENANT_PATH = re.compile(
    r"^/api/v1/tenants/(?P<tenant_id>[0-9a-f-]{36})(?:/|$)", re.IGNORECASE
)


def get_request_id() -> str:
    return request_id_ctx.get()


def get_tenant_id() -> str:
    return tenant_id_ctx.get()


def resolve_inbound_tenant_id(request: Request) -> str:
    match = _TENANT_PATH.match(request.url.path)
    if match:
        return match.group("tenant_id")
    return request.headers.get("X-Tenant-Id", "").strip()


def is_health_probe(path: str) -> bool:
    return path in METRICS_PATHS


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if is_health_probe(request.url.path):
            return await call_next(request)

        logger = get_logger()
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request_id_ctx.set(request_id)

        tenant_id = resolve_inbound_tenant_id(request)
        tenant_id_ctx.set(tenant_id)

        req_logger = logger.child(
            {
                "requestId": request_id,
                "method": request.method,
                "path": request.url.path,
                **({"tenantId": tenant_id} if tenant_id else {}),
            }
        )
        if request.method != "OPTIONS":
            req_logger.info("api.request.received")

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            req_logger.error("api.request.failed", exc, {"durationMs": duration_ms})
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        if request.method != "OPTIONS":
            ctx = {"status": response.status_code, "durationMs": duration_ms}
            if response.status_code >= 500:
                req_logger.error("api.request.completed", RuntimeError(f"HTTP {response.status_code}"), ctx)
            elif response.status_code >= 400:
                req_logger.warn("api.request.completed", ctx)
            else:
                req_logger.info("api.request.completed", ctx)

        response.headers["X-Request-Id"] = request_id
        return response
