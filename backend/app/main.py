from app.api.internal_routes import router as internal_router
from app.api.routes import router
from app.app_factory import build_service_app

# The single API service. Phase 1 mounts the platform (health) + internal
# (Shopify install/session-sync/uninstall, tenant lookup) routers.


def _republish_storefronts() -> None:
    """App start: queue a republish of the Relay key and endpoint for every shop."""
    from app.db.session import SessionLocal
    from app.logging_config import get_logger
    from app.services.storefront_publisher import queue_publish_for_all_shops

    db = SessionLocal()
    try:
        get_logger().info("storefront.republish_on_start", {"shops": queue_publish_for_all_shops(db)})
    except Exception as exc:  # noqa: BLE001 — a failed republish must not stop the API
        get_logger().error("storefront.republish_on_start_failed", exc)
    finally:
        db.close()


app = build_service_app(service="api", routers=[router, internal_router], on_startup=_republish_storefronts)
