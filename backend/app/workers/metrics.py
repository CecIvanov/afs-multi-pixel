"""Celery signal handlers: per-task Prometheus counters + multiprocess registration."""

from __future__ import annotations

import re
import time

from app_metrics import SYSTEM_TENANT_ID, record_worker_task, register_prometheus_multiprocess_shutdown
from celery.signals import task_postrun, task_prerun, worker_process_init

_task_started: dict[str, float] = {}
_TENANT_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


@worker_process_init.connect
def _init_worker_metrics_process(**_) -> None:
    register_prometheus_multiprocess_shutdown()


@task_prerun.connect
def _task_prerun(task_id: str, task, *args, **kwargs) -> None:
    _task_started[task_id] = time.perf_counter()


def _resolve_worker_tenant_id(args: tuple[object, ...], kwargs: dict[str, object]) -> str:
    tenant_id = kwargs.get("tenant_id")
    if isinstance(tenant_id, str) and _TENANT_ID_PATTERN.match(tenant_id.strip()):
        return tenant_id.strip()
    if args:
        candidate = args[0]
        if isinstance(candidate, str) and _TENANT_ID_PATTERN.match(candidate.strip()):
            return candidate.strip()
    return SYSTEM_TENANT_ID


@task_postrun.connect
def _task_postrun(
    task_id: str, task, retval, state, sender=None,
    args: tuple[object, ...] | None = None, kwargs: dict[str, object] | None = None, **_,
) -> None:
    started = _task_started.pop(task_id, None)
    if started is None:
        return
    record_worker_task(
        service="worker",
        task=task.name or "unknown",
        status="success" if state == "SUCCESS" else str(state).lower(),
        duration_seconds=time.perf_counter() - started,
        tenant_id=_resolve_worker_tenant_id(args or (), kwargs or {}),
    )
