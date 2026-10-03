"""Durable job queue worker — a slot-refill ThreadPool that claims and processes
jobs, plus a stale-processing reaper. Runs as its own container:

    python -m app.workers.job_pool

Kept SEPARATE from Celery (which is cron/fan-out only): this owns per-tenant
fairness, priority, DB-level dedup, and crash recovery.
"""

from __future__ import annotations

import os
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import contextmanager
from pathlib import Path

from app.config import get_settings
from app.db.session import SessionLocal
from app.logging_config import configure_logging, get_logger
from app.services.async_job_service import AsyncJobService, default_worker_id

configure_logging(component="job_pool")
logger = get_logger().child({"component": "job_pool"})


# The container healthcheck reads this file's age (docker-compose.yml, jobs).
LIVENESS_FILE = Path(os.environ.get("JOB_POOL_LIVENESS_FILE", "/tmp/job_pool.alive"))


def _touch_liveness() -> None:
    try:
        LIVENESS_FILE.touch()
    except OSError:
        pass


class JobPoolRunner:
    def __init__(self) -> None:
        s = get_settings()
        self.pool_size = s.job_pool_size
        self.idle_poll_seconds = s.job_idle_poll_seconds
        self.stale_processing_seconds = s.job_stale_processing_seconds
        self.reap_interval_seconds = s.job_reap_interval_seconds
        self.server_event_poll_seconds = s.server_event_poll_seconds
        self.worker_id = default_worker_id()
        self._shutdown = threading.Event()

    def _reap_stale_jobs(self) -> None:
        db = SessionLocal()
        try:
            AsyncJobService(db).reclaim_stale_processing_jobs(self.stale_processing_seconds)
        except Exception as exc:  # noqa: BLE001 — reaper must never take the pool down
            logger.error("job_pool.reap_failed", exc)
        finally:
            db.close()

    def _worker_loop(self, slot: int) -> None:
        while not self._shutdown.is_set():
            db = SessionLocal()
            try:
                job = AsyncJobService(db).claim_next(self.worker_id)
                if job is None:
                    db.close()
                    if self._shutdown.wait(timeout=self.idle_poll_seconds):
                        return
                    continue
                job_id = job.id
                with self._claim_heartbeat(job_id):
                    AsyncJobService(db).process_job(job_id)
            except Exception as exc:  # noqa: BLE001 — a slot must never die
                logger.error("job_pool.slot_failed", exc, {"slot": slot})
                db.rollback()
                self._shutdown.wait(timeout=1.0)
            finally:
                db.close()

    @contextmanager
    def _claim_heartbeat(self, job_id):
        """Keep a running job's claimed_at fresh so the stale reaper (which requeues
        PROCESSING jobs older than job_stale_processing_seconds) never runs a long
        job twice. Only a dead worker's jobs go stale."""
        stop = threading.Event()
        interval = max(self.stale_processing_seconds / 3, 1.0)

        def beat() -> None:
            while not stop.wait(timeout=interval):
                db = SessionLocal()
                try:
                    AsyncJobService(db).touch_claim(job_id)
                except Exception as exc:  # noqa: BLE001 — a missed beat is retried
                    logger.warn("job_pool.heartbeat_failed", {"jobId": str(job_id), "detail": str(exc)[:200]})
                    db.rollback()
                finally:
                    db.close()

        thread = threading.Thread(target=beat, name=f"heartbeat-{job_id}", daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=5)

    def _server_event_loop(self) -> None:
        """Send due Server Events to the Conversions API (spec §3.2 step 3). Drains
        a full batch at once; idles between polls when nothing is due."""
        from app.services.server_event_sender import ServerEventSender

        while not self._shutdown.is_set():
            db = SessionLocal()
            handled = 0
            try:
                handled = ServerEventSender(db).send_due()
            except Exception as exc:  # noqa: BLE001 — the sender must never die
                logger.error("job_pool.server_events_failed", exc)
                db.rollback()
            finally:
                db.close()
            if not handled and self._shutdown.wait(timeout=self.server_event_poll_seconds):
                return

    def run(self) -> None:
        logger.info("job_pool.started", {"poolSize": self.pool_size, "workerId": self.worker_id})
        self._reap_stale_jobs()  # startup reap
        last_reap = time.monotonic()
        with ThreadPoolExecutor(max_workers=self.pool_size + 1, thread_name_prefix="jobslot") as pool:
            futures = [pool.submit(self._worker_loop, i) for i in range(self.pool_size)]
            futures.append(pool.submit(self._server_event_loop))
            while not self._shutdown.is_set():
                _touch_liveness()
                if time.monotonic() - last_reap >= self.reap_interval_seconds:
                    self._reap_stale_jobs()
                    last_reap = time.monotonic()
                self._shutdown.wait(timeout=1.0)
            wait(futures, timeout=30)
        logger.info("job_pool.stopped", {})

    def stop(self) -> None:
        self._shutdown.set()


def main() -> None:
    runner = JobPoolRunner()

    def handle_stop(*_args: object) -> None:
        runner.stop()

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    runner.run()


if __name__ == "__main__":
    main()
