"""Application settings — infrastructure config via pydantic-settings.

Identity (name, plan catalog) comes from app.config.json (see app_config.py); this
holds the infra wiring layered from the environment / .env. Every field has a
default so the app boots for local development without a full .env.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.app_config import get_app_config

_manifest = get_app_config()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Identity (defaults from app.config.json; env vars override in Docker) ---
    app_name: str = _manifest.name
    app_env: str = "development"
    debug: bool = False

    # --- Database ---
    database_url: str = "postgresql://afsmultipixel_dev:test123@127.0.0.1:5432/afsmultipixel_dev"
    database_pool_size: int = 5
    database_max_overflow: int = 5

    # --- Redis / Celery ---
    redis_url: str = "redis://127.0.0.1:6379/1"
    celery_task_queue: str = _manifest.slug
    celery_redis_key_prefix: str = f"{_manifest.slug}:"
    # Example beat cadence (minutes) — see workers/celery_app.py.
    celery_beat_heartbeat_minutes: int = 15

    # --- Service-to-service trust boundary ---
    internal_api_key: str = "dev-internal-key"

    # --- Shopify app credentials (needed BACKEND-side for offline-token refresh) ---
    # The Node BFF also uses these; the backend needs them to POST the
    # grant_type=refresh_token exchange. Sourced from .credentials.<stack>.
    shopify_api_key: str = ""
    shopify_api_secret: str = ""
    # Refresh an offline access token this many minutes before it expires, and
    # renew the whole refresh chain this many days before IT expires.
    shopify_token_refresh_lead_minutes: int = 5
    shopify_refresh_token_renew_lead_days: int = 7
    # Cadence of the discovery beat that enqueues due token refreshes.
    celery_beat_token_refresh_minutes: int = 1

    # --- Toggles ---
    enable_openapi_docs: bool = True
    enable_dev_routes: bool = True
    billing_enforcement_enabled: bool = True

    # --- Durable async job queue (Phase 2) ---
    job_pool_size: int = 8
    job_tenant_in_flight_limit: int = 4
    job_global_in_flight_limit: int = 16
    job_idle_poll_seconds: float = 5.0
    # The event backoff (spec §3.2): retry after 1 min, 5 min, 30 min, 2 h, 6 h,
    # then dead-letter. A job gets one attempt plus one per delay.
    job_retry_schedule_seconds: tuple[int, ...] = (60, 300, 1800, 7200, 21600)
    job_stale_processing_seconds: int = 120
    job_reap_interval_seconds: float = 30.0
    job_completed_retention_hours: int = 48
    job_failed_retention_days: int = 7
    webhook_events_retention_hours: int = 24

    # --- App-specific settings ------------------------------------------------
    # Add your app's own configuration below. Anything the app needs at runtime
    # that isn't identity (which lives in app.config.json) belongs here.
    # example_external_api_url: str = "https://api.example.com"

    # Encryption at rest for Conversions API tokens and the Relay private key
    # (app.services.token_cipher). Sourced from .credentials.<stack>; empty fails closed.
    token_enc_key: str = ""
    # The app's public URL (the Node BFF). The Relay endpoint published to the
    # storefront is <shopify_app_url>/api/events.
    shopify_app_url: str = ""
    # Relays accepted per minute (spec §3.2), per shopper IP and per shop.
    relay_rate_limit_per_ip: int = 120
    relay_rate_limit_per_shop: int = 6000
    # How often the job pool's sender looks for due Server Events.
    server_event_poll_seconds: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
