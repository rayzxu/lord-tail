from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Query

from ...content.character_config import load_anatomy, load_character_registry, load_equipment_slots
from ...content.models import ArchiveRequest, DeleteRequest, RollbackRequest
from ...content.publish import (
    archive_content, audit_entries, delete_proposal, hard_delete, revision_entries,
    rollback_revision,
)
from ...content.references import reference_report
from ...content.repository import content_type_metadata, get_document, list_documents, published_revision

router = APIRouter(prefix="/admin-api/v1")
DELETE_PROPOSAL_SECRET = secrets.token_urlsafe(32)


@router.get("/meta")
def meta() -> dict[str, Any]:
    return {"name": "Lord Tail Admin", "version": 1, "registry_revision": published_revision(), "ports": {"admin_api": 8001, "admin_ui": 5174}}


@router.get("/content-types")
def content_types() -> dict[str, Any]:
    rows = content_type_metadata()
    return {"content_types": rows, "total": len(rows)}


@router.get("/schemas/{content_type}")
def content_schema(content_type: str) -> dict[str, Any]:
    schemas: dict[str, dict[str, Any]] = {
        "story_arc": {"type": "object", "required": ["schema_version", "id", "title", "entry_node", "nodes"], "ui_editor": "graph", "node_kinds": ["choice", "automatic", "timed", "terminal"], "condition_ops": ["fact_equals", "fact_gte", "fact_lte", "choice_was", "resource_minimum", "season_any", "any"], "automatic_presentations": ["transition_log", "silent"]},
        "storylet": {"type": "object", "required": ["schema_version", "chain_id", "nodes"], "ui_editor": "storylet"},
        "preset_character": {"type": "object", "required": ["id", "name", "kind", "age", "body_preset_id"], "ui_editor": "character"},
        "item": {"type": "object", "required": ["name", "type"], "ui_editor": "item"},
        "body_part": {"type": "object", "required": ["label", "category", "side"], "ui_editor": "anatomy"},
        "equipment_slot": {"type": "object", "required": ["label", "virtual", "group"], "ui_editor": "anatomy"},
    }
    return {"content_type": content_type, "schema": schemas.get(content_type, {"type": "object", "ui_editor": "json"})}


@router.get("/content/{content_type}")
def content_list(content_type: str, query: str = "", status: str = "", tag: str = "") -> dict[str, Any]:
    rows = list_documents(content_type)
    normalized = query.casefold().strip()
    if normalized:
        rows = [item for item in rows if normalized in item["id"].casefold() or normalized in item["title"].casefold()]
    if status:
        rows = [item for item in rows if item["status"] == status]
    if tag:
        rows = [item for item in rows if tag in item.get("tags", [])]
    summaries = [{key: value for key, value in item.items() if key != "document"} for item in rows]
    return {"content": summaries, "total": len(summaries), "registry_revision": published_revision()}


@router.get("/content/{content_type}/{content_id}")
def content_detail(content_type: str, content_id: str) -> dict[str, Any]:
    item = get_document(content_type, content_id)
    return {**item, "references": reference_report(content_type, content_id)}


@router.get("/content/{content_type}/{content_id}/references")
def content_references(content_type: str, content_id: str) -> dict[str, Any]:
    get_document(content_type, content_id)
    return reference_report(content_type, content_id)


@router.post("/content/{content_type}/{content_id}/archive")
def content_archive(content_type: str, content_id: str, request: ArchiveRequest) -> dict[str, Any]:
    return archive_content(content_type, content_id, expected_revision=request.expected_revision, archived=True, summary=request.summary)


@router.post("/content/{content_type}/{content_id}/restore")
def content_restore(content_type: str, content_id: str, request: ArchiveRequest) -> dict[str, Any]:
    return archive_content(content_type, content_id, expected_revision=request.expected_revision, archived=False, summary=request.summary)


@router.post("/content/{content_type}/{content_id}/delete-proposal")
def content_delete_proposal(content_type: str, content_id: str) -> dict[str, Any]:
    return delete_proposal(content_type, content_id, DELETE_PROPOSAL_SECRET)


@router.post("/content/{content_type}/{content_id}/delete")
def content_delete(content_type: str, content_id: str, request: DeleteRequest) -> dict[str, Any]:
    return hard_delete(content_type, content_id, expected_revision=request.expected_revision, proposal_token=request.proposal_token, confirmation=request.confirmation, secret=DELETE_PROPOSAL_SECRET)


@router.get("/revisions")
def revisions() -> dict[str, Any]:
    rows = revision_entries()
    return {"revisions": rows, "total": len(rows)}


@router.post("/revisions/{revision_id}/rollback")
def revision_rollback(revision_id: str, request: RollbackRequest) -> dict[str, Any]:
    return rollback_revision(revision_id, request.summary)


@router.get("/audit")
def audit(limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, Any]:
    rows = audit_entries(limit)
    return {"audit": rows, "total": len(rows)}


@router.get("/registry/status")
def registry_status() -> dict[str, Any]:
    return {
        "revision": published_revision(), "valid": True,
        "character_registry": {"kinds": len(load_character_registry().get("kinds", {})), "components": len(load_character_registry().get("components", {}))},
        "body_parts": len(load_anatomy().get("body_parts", {})),
        "equipment_slots": len(load_equipment_slots().get("slots", {})),
    }
