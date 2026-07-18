from __future__ import annotations

import re
from typing import Any


def first_mentioned(catalog: dict[str, dict[str, Any]], command: str) -> dict[str, Any] | None:
    return next((entry for name, entry in catalog.items() if name in command), None)


def command_coordinate(command: str) -> tuple[int, int] | None:
    match = re.search(r"\b([A-Ja-j])\s*(10|[1-9])\b", command)
    if not match:
        return None
    return ord(match.group(1).upper()) - 64, int(match.group(2))
