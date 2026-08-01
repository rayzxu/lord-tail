from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .api import agent_tools, council, debug, game, internal, runs, state, storylets
from .catalog import TALENTS, public_catalog, validate_map_tile_kinds_catalog
from .engine import request_audit
from .systems.military import validate_unit_combat_catalog
from .ai.config import load_council_policies
from .storylets.config import validate_storylet_catalog

validate_unit_combat_catalog()
validate_map_tile_kinds_catalog()
load_council_policies()
validate_storylet_catalog()

app = FastAPI(title="Lord Tail Engine", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def audit_api_requests(request: Request, call_next):
    body = await request.body()
    started = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - started) * 1000
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/debug/"):
        request_audit.record_request(request.method, path, response.status_code, body, duration_ms)
    return response


app.include_router(game.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(agent_tools.router, prefix="/api")
app.include_router(state.router, prefix="/api")
app.include_router(council.router, prefix="/api")
app.include_router(debug.router, prefix="/api")
app.include_router(storylets.router, prefix="/api")
app.include_router(internal.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/talents")
def talents() -> list[dict[str, Any]]:
    return [{"id": key, **talent} for key, talent in TALENTS.items()]


@app.get("/api/catalog")
def catalog() -> dict[str, Any]:
    return public_catalog()
