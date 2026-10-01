from __future__ import annotations

import enum
from typing import Type

from sqlalchemy import Enum as SAEnum


def postgres_enum(enum_cls: Type[enum.Enum], name: str) -> SAEnum:
    """A Postgres ENUM stored by the members' string VALUES (not their names)."""
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda cls: [member.value for member in cls],
    )
