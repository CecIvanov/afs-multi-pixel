"""Structured JSON logger (Python).

Output shape is byte-identical to the TypeScript logger in packages/logger so a
single log query joins the Node and Python services:

    {"ts", "level", "event", "context", "message"?, "error"?}

Keep the two in lockstep — a parity test guards the shape.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, TextIO

LogLevel = str
LogContext = dict[str, Any]
LogTransport = Callable[[dict[str, Any]], None]

LEVEL_PRIORITY: dict[str, int] = {"debug": 10, "info": 20, "warn": 30, "error": 40}


def resolve_level(value: str | None = None) -> LogLevel:
    normalized = (value or os.getenv("LOG_LEVEL", "info")).lower()
    return normalized if normalized in LEVEL_PRIORITY else "info"


def console_transport(entry: dict[str, Any]) -> None:
    line = json.dumps(entry, default=str, ensure_ascii=False)
    stream: TextIO = sys.stderr if entry.get("level") == "error" else sys.stdout
    print(line, file=stream, flush=True)


_default_transport = console_transport


def _serialize_error(error: BaseException | Any) -> dict[str, str]:
    if isinstance(error, BaseException):
        payload: dict[str, str] = {"name": error.__class__.__name__, "message": str(error)}
        if error.__traceback__ is not None:
            payload["stack"] = "".join(traceback.format_exception(error))
        return payload
    return {"name": "Error", "message": str(error)}


@dataclass
class AppLogger:
    level: LogLevel = "info"
    base_context: LogContext = field(default_factory=dict)
    transport: LogTransport = field(default=_default_transport)

    def child(self, context: LogContext) -> "AppLogger":
        return AppLogger(
            level=self.level,
            base_context={**self.base_context, **context},
            transport=self.transport,
        )

    def _should_log(self, level: LogLevel) -> bool:
        return LEVEL_PRIORITY[level] >= LEVEL_PRIORITY[self.level]

    def _emit(
        self,
        level: LogLevel,
        event: str,
        context: LogContext | None = None,
        *,
        message: str | None = None,
        error: BaseException | Any | None = None,
    ) -> None:
        if not self._should_log(level):
            return
        entry: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": level,
            "event": event,
            "context": {**self.base_context, **(context or {})},
        }
        if message:
            entry["message"] = message
        if error is not None:
            entry["error"] = _serialize_error(error)
        self.transport(entry)

    def debug(self, event: str, context: LogContext | None = None, message: str | None = None) -> None:
        self._emit("debug", event, context, message=message)

    def info(self, event: str, context: LogContext | None = None, message: str | None = None) -> None:
        self._emit("info", event, context, message=message)

    def warn(self, event: str, context: LogContext | None = None, message: str | None = None) -> None:
        self._emit("warn", event, context, message=message)

    def error(
        self,
        event: str,
        error: BaseException | Any,
        context: LogContext | None = None,
        message: str | None = None,
    ) -> None:
        self._emit("error", event, context, message=message, error=error)


def create_logger(
    *,
    level: LogLevel | None = None,
    base_context: LogContext | None = None,
    transport: LogTransport | None = None,
) -> AppLogger:
    return AppLogger(
        level=level or resolve_level(),
        base_context=base_context or {},
        transport=transport or _default_transport,
    )


class _MemoryTransport:
    """Captures log entries in memory for assertions in tests."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def __call__(self, entry: dict[str, Any]) -> None:
        self.entries.append(entry)

    def reset(self) -> None:
        self.entries.clear()


def create_memory_transport() -> tuple[LogTransport, _MemoryTransport]:
    memory = _MemoryTransport()
    return memory, memory


NOOP_LOGGER = create_logger(transport=lambda _entry: None, level="error")
