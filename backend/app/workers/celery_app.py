"""Celery app — cron + fan-out only (NOT the durable webhook job queue, which is
Phase 2). The app name, queue and Redis key prefix are env-scoped so dev / staging
/ prod never share broker keys or consume each other's tasks on one Redis.
"""

from datetime import timedelta

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings
from app.logging_config import configure_logging
from app.workers import logging as worker_logging  # noqa: F401 — Celery signal handlers
from app.workers import metrics as worker_metrics  # noqa: F401 — Celery signal handlers

configure_logging(component="worker")

settings = get_settings()

celery_app = Celery(
    f"{settings.celery_task_queue}_{settings.app_env}",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    timezone="UTC",
    worker_hijack_root_logger=False,
    worker_redirect_stdouts=False,
    # Publishing a task must never block a web request: fail fast if the broker is
    # momentarily unreachable (the caller swallows it; scheduled reconcile backfills).
    task_publish_retry=False,
    broker_connection_timeout=2,
    # Task state lives in the app's own DB (the Phase 2 job queue), not Celery's
    # result store, so results are ignored — this also keeps `.delay()` from
    # touching the result backend when publishing.
    task_ignore_result=True,
    task_default_queue=settings.celery_task_queue,
    task_queues={
        settings.celery_task_queue: {
            "exchange": settings.celery_task_queue,
            "routing_key": settings.celery_task_queue,
        }
    },
    task_default_exchange=settings.celery_task_queue,
    task_default_routing_key=settings.celery_task_queue,
    broker_transport_options={
        "global_keyprefix": settings.celery_redis_key_prefix,
        "socket_connect_timeout": 2,
        "socket_timeout": 2,
    },
    result_backend_transport_options={"global_keyprefix": settings.celery_redis_key_prefix},
    beat_schedule={
        f"{settings.app_env}-heartbeat": {
            "task": "app.workers.tasks.heartbeat",
            "schedule": timedelta(minutes=settings.celery_beat_heartbeat_minutes),
            "options": {"queue": settings.celery_task_queue},
        },
        # Retention: purge old completed/failed jobs and processed webhook events.
        f"{settings.app_env}-purge-job-retention": {
            "task": "app.workers.tasks.purge_job_retention",
            "schedule": timedelta(hours=1),
            "options": {"queue": settings.celery_task_queue},
        },
        f"{settings.app_env}-purge-webhook-retention": {
            "task": "app.workers.tasks.purge_webhook_retention",
            "schedule": timedelta(hours=1),
            "options": {"queue": settings.celery_task_queue},
        },
        # Billing drift reconcile — catches plan changes made outside the app.
        f"{settings.app_env}-billing-reconcile": {
            "task": "app.workers.tasks.dispatch_billing_reconcile",
            "schedule": crontab(hour=2, minute=0),
            "options": {"queue": settings.celery_task_queue},
        },
        # Offline-token upkeep — enqueue a durable refresh job for any tenant whose
        # Shopify offline access token (or refresh chain) is nearing expiry, so
        # background workers never hit a dead token. See shopify_token_refresh_service.
        f"{settings.app_env}-shopify-token-refresh": {
            "task": "app.workers.tasks.dispatch_shopify_token_refresh",
            "schedule": timedelta(minutes=settings.celery_beat_token_refresh_minutes),
            "options": {"queue": settings.celery_task_queue},
        },
    },
)

celery_app.autodiscover_tasks(["app.workers"])
