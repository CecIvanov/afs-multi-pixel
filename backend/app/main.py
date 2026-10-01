from app.api.internal_routes import router as internal_router
from app.api.routes import router
from app.app_factory import build_service_app

# The single API service. Phase 1 mounts the platform (health) + internal
# (Shopify install/session-sync/uninstall, tenant lookup) routers.
app = build_service_app(service="api", routers=[router, internal_router])
