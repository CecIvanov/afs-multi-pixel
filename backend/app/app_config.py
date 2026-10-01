"""app_config.py — the single source of truth for app identity, for Python.

The FastAPI service and Celery workers read the app's name, plan catalog and
feature-flag defaults from the one file (``app.config.json``) via this module.
Infrastructure values (database URL, Redis URL, secrets) stay in
``config.Settings`` / the environment; identity lives here so there is exactly
one place to set the application's name.

    from app.app_config import get_app_config
    cfg = get_app_config()
    cfg.name                      # "My Shopify App"
    cfg.database_name("dev")      # "myapp_dev"
    cfg.plans                     # [{"handle": "free", ...}, ...] by rank
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any


def _find_config_path() -> Path | None:
    override = os.environ.get("APP_CONFIG_PATH")
    if override:
        return Path(override)
    # Walk up from this file until app.config.json is found (repo root on the host;
    # copied into the image at /app/app.config.json in the container).
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        candidate = parent / "app.config.json"
        if candidate.is_file():
            return candidate
    # Not found (e.g. an unusual container layout) — fall back to defaults rather
    # than crashing at import time. Identity also arrives via env vars (APP_NAME…).
    return None


@dataclass(frozen=True)
class AppConfig:
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.raw.get("app", {}).get("name", "My Shopify App")

    @property
    def handle(self) -> str:
        return self.raw.get("app", {}).get("handle", "my-shopify-app")

    @property
    def slug(self) -> str:
        return self.raw.get("app", {}).get("slug", "myapp")

    @property
    def celery_key_prefix(self) -> str:
        ids = self.raw.get("identifiers", {})
        return ids.get("celeryKeyPrefix", self.slug)

    @property
    def plans(self) -> list[dict[str, Any]]:
        plans = self.raw.get("billing", {}).get("plans", [])
        return sorted(plans, key=lambda p: p.get("rank", 0))

    @property
    def billing_mode(self) -> str:
        return self.raw.get("billing", {}).get("mode", "managed")

    def database_name(self, env: str | None = None) -> str:
        env = env or os.environ.get("APP_ENV", "dev")
        prefix = self.raw.get("identifiers", {}).get("databaseNamePrefix", self.slug)
        return prefix if env in ("prod", "production") else f"{prefix}_{env}"


@lru_cache
def get_app_config() -> AppConfig:
    path = _find_config_path()
    if path is None or not path.is_file():
        return AppConfig(raw={})
    return AppConfig(raw=json.loads(path.read_text(encoding="utf-8")))
