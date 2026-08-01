from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Response

from ...content.drafts import (
    create_draft, delete_draft, draft_by_id, list_drafts, update_draft, validate_draft,
)
from ...content.models import DraftCreateRequest, DraftUpdateRequest, PublishRequest
from ...content.publish import draft_diff, publish_draft
from ...storylets.config import EFFECT_OPS, load_arc_definitions
from ...storylets.graph import analyze_graph
from ...engine.scenes import VALID_SCENE_TYPES

router = APIRouter(prefix="/admin-api/v1")


@router.post("/drafts")
def draft_create(request: DraftCreateRequest) -> dict[str, Any]:
    return create_draft(request)


@router.get("/drafts")
def drafts_list() -> dict[str, Any]:
    rows = list_drafts()
    return {"drafts": rows, "total": len(rows)}


@router.get("/drafts/{draft_id}")
def draft_detail(draft_id: str) -> dict[str, Any]:
    return draft_by_id(draft_id)


@router.put("/drafts/{draft_id}")
def draft_update(draft_id: str, request: DraftUpdateRequest) -> dict[str, Any]:
    return update_draft(draft_id, request.document, request.expected_revision)


@router.delete("/drafts/{draft_id}", status_code=204)
def draft_delete(draft_id: str) -> Response:
    delete_draft(draft_id)
    return Response(status_code=204)


@router.post("/drafts/{draft_id}/clone")
def draft_clone(draft_id: str) -> dict[str, Any]:
    source = draft_by_id(draft_id)
    return create_draft(DraftCreateRequest(content_type=source["content_type"], content_id=source["content_id"], operation="update", document=deepcopy(source["document"])))


@router.post("/drafts/{draft_id}/validate")
def draft_validate(draft_id: str) -> dict[str, Any]:
    return validate_draft(draft_id)


@router.get("/drafts/{draft_id}/diff")
def draft_get_diff(draft_id: str) -> dict[str, Any]:
    return {"diff": draft_diff(draft_by_id(draft_id))}


@router.post("/drafts/{draft_id}/preview")
@router.post("/drafts/{draft_id}/simulate")
def draft_preview(draft_id: str) -> dict[str, Any]:
    draft = draft_by_id(draft_id)
    validation = validate_draft(draft_id)
    preview: dict[str, Any] = {"validation": validation, "content_type": draft["content_type"], "content_id": draft["content_id"]}
    if draft["content_type"] == "story_arc" and validation["valid"]:
        analysis = analyze_graph(draft["document"], effect_ops=EFFECT_OPS, valid_scene_types=VALID_SCENE_TYPES)
        preview["graph"] = {"reachable_nodes": sorted(analysis.reachable_nodes), "terminal_nodes": sorted(analysis.terminal_nodes), "path_count": len(analysis.paths), "paths": [list(path) for path in analysis.paths], "max_blocking_decisions": analysis.max_blocking_decisions}
    elif draft["content_type"] == "preset_character":
        preview["character"] = deepcopy(draft["document"])
    elif draft["content_type"] == "item":
        preview["item"] = deepcopy(draft["document"])
    return preview


@router.post("/drafts/{draft_id}/publish")
def draft_publish(draft_id: str, request: PublishRequest) -> dict[str, Any]:
    return publish_draft(draft_id, expected_revision=request.expected_revision, summary=request.summary, idempotency_key=request.idempotency_key)
