from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..engine import request_audit

router = APIRouter()


@router.get("/debug/request-log")
def request_log() -> dict[str, Any]:
    return {"events": request_audit.read_events()}


@router.delete("/debug/request-log")
def clear_request_log() -> dict[str, Any]:
    request_audit.clear_events()
    return {"status": "cleared"}
