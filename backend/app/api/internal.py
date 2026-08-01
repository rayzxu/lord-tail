from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException

router = APIRouter()


@router.post("/internal/content/reload")
def reload_content(x_lord_tail_internal_token: str = Header(default="")) -> dict[str, Any]:
    expected = os.getenv("LORD_TAIL_INTERNAL_CONTENT_TOKEN", "")
    if not expected or not x_lord_tail_internal_token or not hmac.compare_digest(expected, x_lord_tail_internal_token):
        raise HTTPException(401, "内部内容重载凭证无效")
    from ..catalog import reload_catalog, validate_map_tile_kinds_catalog
    from ..content.character_config import validate_character_configs
    from ..storylets.config import load_arc_definitions, load_definitions, validate_storylet_catalog
    from ..systems.characters import reload_character_registry

    reload_catalog()
    reload_character_registry()
    load_definitions.cache_clear(); load_arc_definitions.cache_clear()
    validate_character_configs(); validate_map_tile_kinds_catalog(); validate_storylet_catalog()
    return {"reloaded": True}
