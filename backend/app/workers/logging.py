"""Celery signal handlers: per-fork logging + per-task correlation context.

Gives every task run the Celery task id as its request id, so worker -> outbound
calls carry X-Request-Id and a run's logs tie together. Clears any tenant leaked
from a previous task on this worker's context.
"""

from __future__ import annotations

import uuid

from celery.signals import task_postrun, task_prerun, worker_process_init, worker_ready

from app.config import get_settings
from app.logging_config import configure_logging, get_logger
from app.middleware.request_logging import request_id_ctx, tenant_id_ctx


@worker_process_init.connect
def _init_worker_process(**_) -> None:
    configure_logging(component="worker")


@task_prerun.connect
def _bind_task_request_context(task_id=None, **_) -> None:
    request_id_ctx.set(str(task_id) if task_id else str(uuid.uuid4()))
    tenant_id_ctx.set("")


@task_postrun.connect
def _clear_task_request_context(**_) -> None:
    request_id_ctx.set("")
    tenant_id_ctx.set("")


@worker_ready.connect
def _log_worker_ready(sender=None, **_) -> None:
    get_logger().info(
        "worker.application.started",
        {"hostname": getattr(sender, "hostname", None), "queue": get_settings().celery_task_queue},
    )
