from __future__ import annotations

from fastapi import Header, HTTPException

from app.config import get_settings
from app.db.session import get_db

__all__ = ["get_db", "verify_internal_key"]


def verify_internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    """Guard /internal/* routes with the Node<->Python shared secret.

    NOTE: request-scoped dependencies must be pulled in with Depends(get_db), never
    `db: Session = next(get_db())` as a default argument — that evaluates the
    generator once at import time and leaks a single shared session.
    """
    settings = get_settings()
    if x_internal_key != settings.internal_api_key:
        raise HTTPException(status_code=401, detail="Invalid internal API key")
