from __future__ import annotations

import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import app_metrics  # noqa: F401 — register collectors in this process
from app_metrics import metrics_response

_server_started = False
_server_lock = threading.Lock()
_METRIC_PREFIX = os.getenv("APP_METRIC_PREFIX", "app")


class _PrometheusHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] != "/metrics":
            self.send_error(404)
            return
        response = metrics_response()
        self.send_response(response.status_code)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(response.body)

    def log_message(self, format: str, *args) -> None:  # silence default logging
        return


def _bind(service: str | None) -> tuple[HTTPServer, int]:
    if service:
        os.environ.setdefault("APP_METRICS_SERVICE", service)
    port = int(os.getenv("WORKER_METRICS_PORT", "9100"))
    return HTTPServer(("0.0.0.0", port), _PrometheusHandler), port


def start_prometheus_metrics_server(*, service: str | None = None) -> None:
    """Expose /metrics on a background thread (for non-prefork processes / tests)."""
    global _server_started
    with _server_lock:
        if _server_started:
            return
        server, port = _bind(service)
        threading.Thread(target=server.serve_forever, name="prometheus-metrics", daemon=True).start()
        _server_started = True
        print(f"metrics on :{port} service={service or 'unknown'}", flush=True)


def run_prometheus_metrics_server_foreground(*, service: str | None = None) -> None:
    """Run /metrics in the current process until killed (the Celery worker sidecar)."""
    server, port = _bind(service)
    print(f"metrics on :{port} service={service or 'unknown'}", flush=True)
    server.serve_forever()


def assert_metrics_expose_app() -> None:
    if f"{_METRIC_PREFIX}_".encode() not in metrics_response().body:
        print("FATAL: /metrics missing app series in sidecar bootstrap", file=sys.stderr, flush=True)
        sys.exit(1)
