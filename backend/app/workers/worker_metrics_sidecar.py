"""Prometheus /metrics sidecar for the Celery worker container.

Celery prefork workers must not serve /metrics from the pool process — forked
children steal the listen socket — so this runs as a SEPARATE process in the same
container (see the worker command in docker-compose.yml).
"""

from __future__ import annotations

import os

from app.logging_config import configure_logging, get_logger
from app.workers.prometheus_server import (
    assert_metrics_expose_app,
    run_prometheus_metrics_server_foreground,
)


def main() -> None:
    configure_logging(component="worker_metrics")
    os.environ.setdefault("APP_METRICS_SERVICE", "worker")
    assert_metrics_expose_app()
    get_logger().info("worker.metrics_sidecar.ready", {"port": int(os.getenv("WORKER_METRICS_PORT", "9100"))})
    run_prometheus_metrics_server_foreground(service="worker")


if __name__ == "__main__":
    main()
