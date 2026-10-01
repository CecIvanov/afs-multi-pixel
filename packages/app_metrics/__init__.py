"""Prometheus metrics for the backend (HTTP + Celery worker) with multiprocess
support. Domain series (outbound integrations, queues) are left as one commented
example — add your own next to WORKER_TASKS.

Gotchas baked in:
- Multi-worker uvicorn needs PROMETHEUS_MULTIPROC_DIR wiped+created on start and
  each process to mark itself dead on exit, or dead workers leak stale counters.
- Bound label cardinality: normalize routes (UUID -> {id}) and return a fixed
  UNMATCHED_ROUTE for 404/405 so scanners don't mint a series per probe.
"""

from __future__ import annotations

import atexit
import os
import re
import shutil
import threading
import time
from typing import Callable

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match

_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)
_TENANT_PATH = re.compile(
    r"^/api/v1/tenants/(?P<tenant_id>[0-9a-f-]{36})(?:/|$)", re.IGNORECASE
)

SYSTEM_TENANT_ID = "_system"
UNMATCHED_ROUTE = "{unmatched}"
_METRIC_PREFIX = os.getenv("APP_METRIC_PREFIX", "app")

METRICS_PATHS = frozenset({"/metrics", "/health", "/api/v1/health"})

HTTP_REQUESTS = Counter(
    f"{_METRIC_PREFIX}_http_requests_total",
    "Inbound HTTP requests",
    ["service", "env", "method", "route", "status", "tenant_id"],
)
HTTP_DURATION = Histogram(
    f"{_METRIC_PREFIX}_http_request_duration_seconds",
    "Inbound HTTP request duration",
    ["service", "env", "method", "route", "tenant_id"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)
WORKER_TASKS = Counter(
    f"{_METRIC_PREFIX}_worker_tasks_total",
    "Celery task executions",
    ["service", "env", "task", "status", "tenant_id"],
)
WORKER_TASK_DURATION = Histogram(
    f"{_METRIC_PREFIX}_worker_task_duration_seconds",
    "Celery task duration",
    ["service", "env", "task", "tenant_id"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)
PROCESS_THREADS = Gauge(
    f"{_METRIC_PREFIX}_process_threads",
    "Active Python threads in the process",
    ["service", "env"],
    multiprocess_mode="livesum",
)

# --- Example: add your app's own outbound-integration series here -----------
# OUTBOUND_REQUESTS = Counter(
#     f"{_METRIC_PREFIX}_outbound_requests_total",
#     "Outbound calls to an external service",
#     ["service", "env", "target", "operation", "status", "tenant_id"],
# )

_multiprocess_shutdown_registered = False


def prometheus_multiprocess_enabled() -> bool:
    return bool(os.environ.get("PROMETHEUS_MULTIPROC_DIR"))


def prepare_prometheus_multiprocess_dir(path: str | None = None) -> str | None:
    """Reset the shared multiprocess metrics dir (call once before workers start)."""
    resolved = (path or os.environ.get("PROMETHEUS_MULTIPROC_DIR") or "").strip()
    if not resolved:
        return None
    shutil.rmtree(resolved, ignore_errors=True)
    os.makedirs(resolved, exist_ok=True)
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = resolved
    return resolved


def register_prometheus_multiprocess_shutdown() -> None:
    """Mark this worker dead on exit so stale counter files are ignored."""
    global _multiprocess_shutdown_registered
    if _multiprocess_shutdown_registered or not prometheus_multiprocess_enabled():
        return
    pid = os.getpid()
    atexit.register(lambda: multiprocess.mark_process_dead(pid))
    _multiprocess_shutdown_registered = True


def deployment_env() -> str:
    return os.getenv("APP_ENV", "development")


def normalize_tenant_id(value: str | None) -> str:
    return value.strip() if value and value.strip() else "unknown"


def normalize_route(path: str) -> str:
    return _UUID.sub("{id}", path.rstrip("/") or "/")


def resolve_route(request: Request) -> str:
    for route in request.app.routes:
        match, _scope = route.matches(request.scope)
        if match == Match.FULL and getattr(route, "path", None):
            return normalize_route(route.path)
    # 404/405: echoing the raw path would mint one series per scanner probe.
    return UNMATCHED_ROUTE


def tenant_id_from_header(request: Request) -> str:
    header = request.headers.get("X-Tenant-Id", "").strip()
    if header:
        return header
    match = _TENANT_PATH.match(request.url.path)
    return match.group("tenant_id") if match else "unknown"


def metrics_response() -> Response:
    service = os.getenv("APP_METRICS_SERVICE", "unknown")
    env = deployment_env()
    PROCESS_THREADS.labels(service=service, env=env).set(threading.active_count())

    multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR", "").strip()
    if multiproc_dir and os.path.isdir(multiproc_dir):
        mp_registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(mp_registry)
        mp_payload = generate_latest(mp_registry)
        if f"{_METRIC_PREFIX}_".encode() not in mp_payload:
            payload = generate_latest()
        elif f"{_METRIC_PREFIX}_process_threads".encode() in mp_payload:
            # livesum already exported this pid's gauge; repeating the HELP line or
            # sample makes Prometheus reject the WHOLE scrape.
            payload = mp_payload
        else:
            payload = mp_payload + _local_process_gauge_payload()
    else:
        payload = generate_latest()
    return Response(payload, media_type=CONTENT_TYPE_LATEST)


def _local_process_gauge_payload() -> bytes:
    body = generate_latest(REGISTRY).decode("utf-8")
    name = f"{_METRIC_PREFIX}_process_threads"
    kept = [
        line
        for line in body.splitlines()
        if line.startswith(f"# HELP {name}")
        or line.startswith(f"# TYPE {name}")
        or line.startswith(name + "{")
    ]
    return ("\n".join(kept) + "\n").encode("utf-8") if kept else b""


def record_http_request(
    *, service: str, method: str, path: str, status: int, duration_seconds: float,
    tenant_id: str = "unknown", route: str | None = None,
) -> None:
    normalized = route or normalize_route(path)
    tenant = normalize_tenant_id(tenant_id)
    env = deployment_env()
    HTTP_REQUESTS.labels(
        service=service, env=env, method=method.upper(), route=normalized,
        status=str(status), tenant_id=tenant,
    ).inc()
    HTTP_DURATION.labels(
        service=service, env=env, method=method.upper(), route=normalized, tenant_id=tenant,
    ).observe(duration_seconds)


def record_worker_task(
    *, service: str, task: str, status: str, duration_seconds: float, tenant_id: str = "unknown",
) -> None:
    tenant = normalize_tenant_id(tenant_id)
    env = deployment_env()
    WORKER_TASKS.labels(service=service, env=env, task=task, status=status, tenant_id=tenant).inc()
    WORKER_TASK_DURATION.labels(service=service, env=env, task=task, tenant_id=tenant).observe(
        duration_seconds
    )


class PrometheusMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, service: str, tenant_resolver: Callable[[Request], str] | None = None) -> None:
        super().__init__(app)
        self.service = service
        self.tenant_resolver = tenant_resolver or tenant_id_from_header
        os.environ.setdefault("APP_METRICS_SERVICE", service)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path in METRICS_PATHS or request.method == "OPTIONS":
            return await call_next(request)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            record_http_request(
                service=self.service, method=request.method, path=path,
                route=resolve_route(request), status=status,
                duration_seconds=time.perf_counter() - started,
                tenant_id=self.tenant_resolver(request),
            )
        return response
