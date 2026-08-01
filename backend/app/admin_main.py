from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.admin import content, drafts
from .content.character_config import validate_character_configs
from .storylets.config import validate_storylet_catalog

validate_character_configs()
validate_storylet_catalog()

app = FastAPI(title="Lord Tail Admin API", version="1.0.0", docs_url="/admin-docs", openapi_url="/admin-openapi.json")
origin = os.getenv("LORD_TAIL_ADMIN_UI_ORIGIN", "http://127.0.0.1:5174")
app.add_middleware(CORSMiddleware, allow_origins=[origin], allow_credentials=False, allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type", "If-Match"])
app.include_router(content.router)
app.include_router(drafts.router)


@app.middleware("http")
async def local_admin_only(request: Request, call_next):
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "testclient"}:
        return JSONResponse({"detail": "Admin API 仅允许本机访问"}, status_code=403)
    return await call_next(request)


@app.get("/admin-health")
def health() -> dict[str, str]:
    return {"status": "ok"}
