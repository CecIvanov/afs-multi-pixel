"""Check with Meta: can this Conversions API token read this pixel? (spec §4)"""

from __future__ import annotations

import httpx

from app.services.market_service import PixelCheck, interpret_pixel_check

GRAPH_URL = "https://graph.facebook.com/v26.0"
PIXEL_FIELDS = "id,name,owner_business,is_unavailable"
# Replaced in tests with an httpx.MockTransport.
_transport: httpx.BaseTransport | None = None


def check_pixel_with_meta(pixel_id: str, token: str) -> PixelCheck:
    try:
        with httpx.Client(transport=_transport, timeout=15.0) as client:
            response = client.get(
                f"{GRAPH_URL}/{pixel_id}", params={"fields": PIXEL_FIELDS, "access_token": token}
            )
    except httpx.HTTPError as exc:
        return PixelCheck(ok=False, error=f"Couldn't reach Meta: {exc.__class__.__name__}. Try again.")
    try:
        body = response.json()
    except ValueError:
        body = {}
    return interpret_pixel_check(pixel_id, response.status_code, body if isinstance(body, dict) else {})
