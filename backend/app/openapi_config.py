"""OpenAPI metadata shared by the service app-factory."""

OPENAPI_VERSION = "0.1.0"

SERVICE_OPENAPI_DESCRIPTION = (
    "Backend API for the Shopify app. Internal endpoints under /api/v1/internal/* "
    "are guarded by the X-Internal-Key shared secret and are called only by the "
    "Node BFF, never the internet."
)

OPENAPI_TAGS = [
    {"name": "Platform", "description": "Health and platform endpoints."},
    {"name": "Internal", "description": "Node BFF -> backend endpoints (shared-key guarded)."},
]

# Documents the X-Internal-Key header as an API-key security scheme.
INTERNAL_API_KEY_SECURITY_SCHEME = {
    "InternalApiKey": {
        "type": "apiKey",
        "in": "header",
        "name": "X-Internal-Key",
    }
}
