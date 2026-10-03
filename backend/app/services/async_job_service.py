"""Durable DB-backed job queue engine.

Idempotency at two layers: WebhookEvent (delivery-level) and this table's
partial-unique pending-dedupe index (work-level). claim_next uses FOR UPDATE SKIP
LOCKED under per-tenant + global in-flight caps; failures retry on the event
backoff schedule (job_retry_schedule_seconds) into a FAILED dead-letter;
reclaim_stale_processing_jobs requeues jobs orphaned by dead workers (mandatory — otherwise one orphan wedges a tenant's queue).
"""

from __future__ import annotations

import os
import socket
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging_config import get_logger
from app.models import AsyncJob, AsyncJobOperation, AsyncJobStatus, WebhookEvent, WebhookEventStatus

logger = get_logger().child({"component": "job_queue"})

_PRIORITY: dict[AsyncJobOperation, int] = {
    AsyncJobOperation.APP_UNINSTALL: 1000,
    AsyncJobOperation.SHOP_REDACT: 1000,
    AsyncJobOperation.CUSTOMER_DATA_REQUEST: 85,
    AsyncJobOperation.CUSTOMER_REDACT: 85,
    AsyncJobOperation.TOKEN_REFRESH: 80,
    AsyncJobOperation.SCOPES_UPDATE: 70,
    AsyncJobOperation.ORDERS_CREATE: 60,
    AsyncJobOperation.MARKETS_SYNC: 60,
    AsyncJobOperation.SUBSCRIPTION_CHECK: 75,
    # Publishing a changed mapping comes before re-syncs: the storefront acts on it.
    AsyncJobOperation.PIXEL_MAPPING_PUBLISH: 65,
    AsyncJobOperation.STOREFRONT_HOSTS_SYNC: 40,
    AsyncJobOperation.EXAMPLE_OP: 50,
    AsyncJobOperation.SHOP_INFO_FETCH: 10,
}


GDPR_OPERATIONS = (
    AsyncJobOperation.SHOP_REDACT,
    AsyncJobOperation.CUSTOMER_DATA_REQUEST,
    AsyncJobOperation.CUSTOMER_REDACT,
)


def priority_for(operation: AsyncJobOperation) -> int:
    return _PRIORITY.get(operation, 50)


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def claim_limits() -> tuple[int, int]:
    s = get_settings()
    return s.job_tenant_in_flight_limit, s.job_global_in_flight_limit


class AsyncJobService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- enqueue -------------------------------------------------------------
    def enqueue(
        self,
        *,
        tenant_id: uuid.UUID,
        operation: AsyncJobOperation,
        topic: str,
        dedupe_key: str | None = None,
        shopify_webhook_id: str | None = None,
        webhook_event_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
        scheduled_at: datetime | None = None,
    ) -> AsyncJob:
        dedupe_key = dedupe_key or operation.value
        for _attempt in range(2):
            existing = self.db.scalar(
                select(AsyncJob).where(
                    AsyncJob.tenant_id == tenant_id,
                    AsyncJob.operation == operation,
                    AsyncJob.dedupe_key == dedupe_key,
                    AsyncJob.status == AsyncJobStatus.PENDING,
                )
            )
            if existing:
                return self._coalesce(existing, topic, shopify_webhook_id, webhook_event_id, payload, scheduled_at)

            job = AsyncJob(
                tenant_id=tenant_id,
                operation=operation,
                topic=topic,
                dedupe_key=dedupe_key,
                priority=priority_for(operation),
                shopify_webhook_id=shopify_webhook_id,
                webhook_event_id=webhook_event_id,
                payload=payload,
                scheduled_at=scheduled_at,
                status=AsyncJobStatus.PENDING,
                max_attempts=len(get_settings().job_retry_schedule_seconds) + 1,
            )
            try:
                # A savepoint: losing the race on the pending-dedupe index must not
                # roll back the caller's work (the stored webhook event).
                with self.db.begin_nested():
                    self.db.add(job)
                    self.db.flush()
            except IntegrityError:
                # Another arrival created the same pending job a moment ago: fold
                # into it instead of failing (which answered Shopify 500).
                continue
            self.db.commit()
            self.db.refresh(job)
            logger.info("job.enqueued", {"jobId": str(job.id), "operation": operation.value, "coalesced": False})
            return job
        raise RuntimeError(f"could not enqueue {operation.value} for tenant {tenant_id}")

    def _coalesce(
        self,
        existing: AsyncJob,
        topic: str,
        shopify_webhook_id: str | None,
        webhook_event_id: uuid.UUID | None,
        payload: dict[str, Any] | None,
        scheduled_at: datetime | None,
    ) -> AsyncJob:
        """Fold a new arrival into the pending job. The webhook event it replaces is
        marked processed (else it stayed "received" forever)."""
        if webhook_event_id and existing.webhook_event_id and existing.webhook_event_id != webhook_event_id:
            replaced = self.db.get(WebhookEvent, existing.webhook_event_id)
            if replaced is not None:
                replaced.status = WebhookEventStatus.PROCESSED
                replaced.processed_at = datetime.now(UTC)
                replaced.error_message = f"coalesced into job {existing.id}"
        existing.topic = topic
        if shopify_webhook_id:
            existing.shopify_webhook_id = shopify_webhook_id
        if webhook_event_id:
            existing.webhook_event_id = webhook_event_id
        if payload is not None:
            existing.payload = payload
        existing.scheduled_at = scheduled_at
        existing.priority = priority_for(existing.operation)
        self.db.commit()
        self.db.refresh(existing)
        logger.info("job.enqueued", {"jobId": str(existing.id), "operation": existing.operation.value, "coalesced": True})
        return existing

    def enqueue_shop_info_fetch(self, tenant_id: uuid.UUID, *, topic: str = "install/shop_info") -> AsyncJob:
        return self.enqueue(tenant_id=tenant_id, operation=AsyncJobOperation.SHOP_INFO_FETCH, topic=topic)

    def enqueue_markets_sync(self, tenant_id: uuid.UUID, *, topic: str = "install/markets") -> AsyncJob:
        return self.enqueue(tenant_id=tenant_id, operation=AsyncJobOperation.MARKETS_SYNC, topic=topic)

    def enqueue_token_refresh(self, tenant_id: uuid.UUID, *, topic: str = "scheduled/token_refresh") -> AsyncJob:
        return self.enqueue(tenant_id=tenant_id, operation=AsyncJobOperation.TOKEN_REFRESH, topic=topic)

    def purge_tenant_active_jobs(self, tenant_id: uuid.UUID) -> int:
        """Drop pending/in-flight jobs when a tenant uninstalls so a dead tenant
        can't hold in-flight slots. (Never touches the running APP_UNINSTALL job's
        own row — that has already been claimed/processing by the caller.)"""
        result = self.db.execute(
            delete(AsyncJob).where(
                AsyncJob.tenant_id == tenant_id,
                AsyncJob.status == AsyncJobStatus.PENDING,
                # GDPR requests must still be answered after an uninstall.
                AsyncJob.operation.not_in(GDPR_OPERATIONS),
            )
        )
        self.db.commit()
        return int(result.rowcount or 0)

    # --- claim ---------------------------------------------------------------
    def claim_next(self, worker_id: str) -> AsyncJob | None:
        tenant_limit, global_limit = claim_limits()
        for _ in range(20):
            candidate = self.db.execute(
                text(
                    """
                    SELECT j.id, j.tenant_id
                    FROM async_jobs j
                    WHERE j.status = 'pending'
                      AND (j.scheduled_at IS NULL OR j.scheduled_at <= NOW())
                      AND (SELECT COUNT(*)::int FROM async_jobs p
                           WHERE p.tenant_id = j.tenant_id AND p.status = 'processing') < :tenant_limit
                      AND (SELECT COUNT(*)::int FROM async_jobs g
                           WHERE g.status = 'processing') < :global_limit
                    ORDER BY j.priority DESC, j.created_at ASC
                    FOR UPDATE OF j SKIP LOCKED
                    LIMIT 1
                    """
                ),
                {"tenant_limit": tenant_limit, "global_limit": global_limit},
            ).first()
            if not candidate:
                self.db.rollback()
                return None

            job_id, tenant_id = candidate[0], candidate[1]
            # Serialize per-tenant claims on the tenant row so the caps hold under races.
            self.db.execute(text("SELECT id FROM tenants WHERE id = :tid FOR UPDATE"), {"tid": tenant_id})
            tenant_in_flight = self.db.scalar(
                text("SELECT COUNT(*)::int FROM async_jobs WHERE tenant_id = :tid AND status = 'processing'"),
                {"tid": tenant_id},
            )
            global_in_flight = self.db.scalar(
                text("SELECT COUNT(*)::int FROM async_jobs WHERE status = 'processing'")
            )
            if int(tenant_in_flight or 0) >= tenant_limit or int(global_in_flight or 0) >= global_limit:
                self.db.rollback()
                continue

            row = self.db.execute(
                text(
                    """
                    UPDATE async_jobs
                    SET status = 'processing', claimed_by = :worker_id, claimed_at = NOW(),
                        started_at = NOW(), attempt_count = attempt_count + 1, updated_at = NOW()
                    WHERE id = :job_id AND status = 'pending'
                    RETURNING id
                    """
                ),
                {"worker_id": worker_id, "job_id": job_id},
            ).first()
            if not row:
                self.db.rollback()
                continue
            self.db.commit()
            job = self.db.get(AsyncJob, row[0])
            if job:
                logger.info("job.claimed", {"jobId": str(job.id), "operation": job.operation.value, "attempt": job.attempt_count})
            return job
        return None

    # --- process -------------------------------------------------------------
    def process_job(self, job_id: uuid.UUID) -> None:
        from app.models import Tenant
        from app.services.shopify_tenant_credentials import is_admin_job_blocked_when_refresh_revoked
        from app.services.shopify_token_refresh_service import ShopifyRefreshTokenRevokedError

        job = self.db.get(AsyncJob, job_id)
        if job is None:
            return

        # A tenant whose offline refresh chain is dead can't call the Admin API, so
        # a job that needs it would just 401 until it dead-letters. Short-circuit it
        # to COMPLETED with zero Shopify calls. Lifecycle/local ops (uninstall,
        # redact, scopes_update) stay allowed — the app must still wind down, and a
        # re-auth clears the revoked flag so normal work resumes.
        tenant = self.db.get(Tenant, job.tenant_id)
        if tenant is not None and is_admin_job_blocked_when_refresh_revoked(tenant, job.operation):
            logger.info(
                "job.skipped_revoked_refresh_token",
                {"jobId": str(job.id), "operation": job.operation.value},
            )
            self._complete_job(job)
            return

        try:
            self._dispatch_with_auth_recovery(job)
            self._complete_job(job)
        except ShopifyRefreshTokenRevokedError:
            # The refresh chain went dead mid-job (reactive recovery, or the
            # token_refresh op itself, has now marked the tenant revoked). Nothing
            # more this job can do — complete it rather than retry five doomed times.
            self.db.rollback()
            self._complete_job(job)
            logger.info(
                "job.skipped_revoked_refresh_token",
                {"jobId": str(job.id), "operation": job.operation.value, "marked": True},
            )
        except Exception as exc:  # noqa: BLE001 — record + retry/fail, never crash the worker
            self.db.rollback()
            self._retry_or_fail(job, str(exc))

    def _dispatch_with_auth_recovery(self, job: AsyncJob) -> None:
        """Run the handler; on a Shopify 401/403, force-refresh the offline token
        once and retry. This is the reactive half of offline-token upkeep — the
        proactive beat should renew before expiry, but if a token is somehow stale
        when a job runs (clock skew, a missed beat, a just-rotated token), one
        forced refresh rescues the job instead of dead-lettering it. Never applies
        to the token-refresh job itself (that would recurse)."""
        from app.services.job_processors import dispatch_job
        from app.services.shopify_oauth_refresh_errors import is_shopify_auth_error

        try:
            dispatch_job(self.db, job)
            return
        except Exception as exc:  # noqa: BLE001
            if job.operation == AsyncJobOperation.TOKEN_REFRESH or not is_shopify_auth_error(str(exc)):
                raise
            captured = exc

        self.db.rollback()
        from app.models import Tenant
        from app.services.shopify_tenant_credentials import is_tenant_refresh_token_revoked
        from app.services.shopify_token_refresh_service import ShopifyTokenRefreshService

        tenant = self.db.get(Tenant, job.tenant_id)
        if tenant is None or is_tenant_refresh_token_revoked(tenant):
            raise captured
        refreshed = ShopifyTokenRefreshService(self.db).refresh_tenant_tokens(
            tenant, reason=f"401_recovery:{job.operation.value}", force=True
        )
        if not refreshed:
            raise captured
        # Retry the handler once with the fresh token now on the tenant row.
        reloaded = self.db.get(AsyncJob, job.id)
        if reloaded is None:
            raise captured
        dispatch_job(self.db, reloaded)
        logger.info("job.auth_recovered", {"jobId": str(job.id), "operation": job.operation.value})

    def _complete_job(self, job: AsyncJob) -> None:
        persisted = self.db.get(AsyncJob, job.id)
        if persisted is None:
            # The handler deleted its own job row (e.g. shop redact removes every
            # tenant-scoped row incl. this job) — nothing left to finalize.
            return
        persisted.status = AsyncJobStatus.COMPLETED
        persisted.finished_at = datetime.now(UTC)
        persisted.last_error = None
        if persisted.webhook_event_id:
            event = self.db.get(WebhookEvent, persisted.webhook_event_id)
            if event and event.status != WebhookEventStatus.PROCESSED:
                event.status = WebhookEventStatus.PROCESSED
                event.processed_at = datetime.now(UTC)
                self.db.add(event)
        self.db.add(persisted)
        self.db.commit()

    def _fail_job(self, job: AsyncJob, message: str) -> None:
        job.status = AsyncJobStatus.FAILED
        job.finished_at = datetime.now(UTC)
        job.last_error = message
        job.last_error_at = datetime.now(UTC)
        if job.webhook_event_id:
            event = self.db.get(WebhookEvent, job.webhook_event_id)
            if event:
                event.status = WebhookEventStatus.FAILED
                event.error_message = message
                self.db.add(event)
        self.db.add(job)
        self.db.commit()
        logger.error("job.failed", None, {"jobId": str(job.id), "operation": job.operation.value, "error": message})

    def _retry_or_fail(self, job: AsyncJob, message: str) -> None:
        settings = get_settings()
        job = self.db.get(AsyncJob, job.id) or job
        job.last_error = message
        job.last_error_at = datetime.now(UTC)
        if job.attempt_count >= job.max_attempts:
            self._fail_job(job, message)
            return
        schedule = settings.job_retry_schedule_seconds
        delay = schedule[min(max(job.attempt_count - 1, 0), len(schedule) - 1)]
        job.status = AsyncJobStatus.PENDING
        job.scheduled_at = datetime.now(UTC) + timedelta(seconds=delay)
        job.claimed_by = None
        job.claimed_at = None
        job.started_at = None
        self.db.add(job)
        self.db.commit()
        logger.warn("job.retry_scheduled", {"jobId": str(job.id), "attempt": job.attempt_count, "delaySeconds": delay})

    # --- maintenance ---------------------------------------------------------
    def touch_claim(self, job_id: uuid.UUID) -> None:
        """Heartbeat of a running job (job_pool): it isn't stale."""
        self.db.execute(
            update(AsyncJob)
            .where(AsyncJob.id == job_id, AsyncJob.status == AsyncJobStatus.PROCESSING)
            .values(claimed_at=datetime.now(UTC))
        )
        self.db.commit()

    def reclaim_stale_processing_jobs(self, older_than_seconds: int | None = None) -> int:
        settings = get_settings()
        cutoff = datetime.now(UTC) - timedelta(
            seconds=older_than_seconds if older_than_seconds is not None else settings.job_stale_processing_seconds
        )
        now = datetime.now(UTC)
        stale = (
            AsyncJob.status == AsyncJobStatus.PROCESSING,
            AsyncJob.claimed_at.is_not(None),
            AsyncJob.claimed_at < cutoff,
        )
        exhausted = self.db.execute(
            update(AsyncJob)
            .where(*stale, AsyncJob.attempt_count >= AsyncJob.max_attempts)
            .values(status=AsyncJobStatus.FAILED, finished_at=now, claimed_by=None, claimed_at=None,
                    started_at=None, last_error="reclaimed: stale processing (attempts exhausted)")
        )
        requeued = self.db.execute(
            update(AsyncJob)
            .where(*stale, AsyncJob.attempt_count < AsyncJob.max_attempts)
            .values(status=AsyncJobStatus.PENDING, claimed_by=None, claimed_at=None,
                    started_at=None, scheduled_at=now, last_error="reclaimed: stale processing (requeued)")
        )
        self.db.commit()
        count = int(exhausted.rowcount or 0) + int(requeued.rowcount or 0)
        if count:
            logger.warn("job.reclaimed_stale", {"count": count})
        return count

    def purge_retention(self) -> dict[str, int]:
        settings = get_settings()
        now = datetime.now(UTC)
        completed = self.db.execute(
            delete(AsyncJob).where(
                AsyncJob.status == AsyncJobStatus.COMPLETED,
                AsyncJob.finished_at.is_not(None),
                AsyncJob.finished_at < now - timedelta(hours=settings.job_completed_retention_hours),
            )
        )
        failed = self.db.execute(
            delete(AsyncJob).where(
                AsyncJob.status == AsyncJobStatus.FAILED,
                AsyncJob.finished_at.is_not(None),
                AsyncJob.finished_at < now - timedelta(days=settings.job_failed_retention_days),
            )
        )
        self.db.commit()
        return {"completed_deleted": int(completed.rowcount or 0), "failed_deleted": int(failed.rowcount or 0)}
