"""Meta's Graph API: Check with Meta (can this Conversions API token send to this
pixel? spec §4) and sending Server Events to the Conversions API (spec §3.2)."""

from __future__ import annotations

from typing import Any

import httpx

from app.services.market_service import PixelCheck, interpret_pixel_check

GRAPH_URL = "https://graph.facebook.com/v26.0"
# Replaced in tests with an httpx.MockTransport.
_transport: httpx.BaseTransport | None = None


def check_pixel_with_meta(pixel_id: str, token: str) -> PixelCheck:
    try:
        with httpx.Client(transport=_transport, timeout=15.0) as client:
            # An Events Manager token can't read the pixel (GET /<pixel> is "(#100) Missing
            # Permission"), but it can post events. One empty event records nothing: Meta
            # checks the token against the pixel, then refuses the event's missing fields.
            # Don't post empty data instead: Meta refuses that before checking the token.
            response = client.post(f"{GRAPH_URL}/{pixel_id}/events", data={"data": "[{}]", "access_token": token})
    except httpx.HTTPError as exc:
        return PixelCheck(ok=False, error=f"Couldn't reach Meta: {exc.__class__.__name__}. Try again.")
    try:
        body = response.json()
    except ValueError:
        body = {}
    return interpret_pixel_check(response.status_code, body if isinstance(body, dict) else {})


def post_events(pixel_id: str, body: dict[str, Any]):
    """POST /<pixel>/events. Never raises: an unreachable Meta is status 0."""
    from app.services.server_event_sender import MetaAnswer

    try:
        with httpx.Client(transport=_transport, timeout=20.0) as client:
            response = client.post(f"{GRAPH_URL}/{pixel_id}/events", json=body)
    except httpx.HTTPError as exc:
        return MetaAnswer(status=0, body={"error": {"message": f"Meta couldn't be reached: {exc.__class__.__name__}"}})
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    return MetaAnswer(status=response.status_code, body=payload if isinstance(payload, dict) else {})
