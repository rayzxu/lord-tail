from __future__ import annotations

import json
import time
from collections import deque
from typing import Any

MAX_AUDIT_EVENTS = 1000
_EVENTS: deque[dict[str, Any]] = deque(maxlen=MAX_AUDIT_EVENTS)


def _safe_json(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return raw.decode("utf-8", errors="replace")[:4000]


def record_request(method: str, path: str, status_code: int, body: bytes, duration_ms: float) -> None:
    _EVENTS.append({
        "timestamp": time.time(),
        "method": method.upper(),
        "path": path,
        "api": f"{method.upper()} {path}",
        "status_code": status_code,
        "request_body": _safe_json(body),
        "duration_ms": round(duration_ms, 2),
    })


def read_events() -> list[dict[str, Any]]:
    return list(_EVENTS)


def clear_events() -> None:
    _EVENTS.clear()
