from __future__ import annotations

import json
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .models import DraftCreateRequest, now_iso
from .repository import DRAFT_DIR, ensure_work_dirs, get_document, revision_for, validate_content_identity
from .validation import validation_payload


def _path(draft_id: str) -> Path:
    if not draft_id.startswith("draft_") or len(draft_id) > 80 or any(char in draft_id for char in "/\\."):
        raise HTTPException(422, "无效 draft id")
    return DRAFT_DIR / f"{draft_id}.json"


def _write(draft: dict[str, Any]) -> dict[str, Any]:
    ensure_work_dirs()
    path = _path(str(draft["id"]))
    from .repository import atomic_write_json

    atomic_write_json(path, draft)
    return deepcopy(draft)


def draft_by_id(draft_id: str) -> dict[str, Any]:
    path = _path(draft_id)
    if not path.exists():
        raise HTTPException(404, "未找到草稿")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise HTTPException(500, "草稿文件损坏")
    return value


def list_drafts() -> list[dict[str, Any]]:
    ensure_work_dirs()
    rows = []
    for path in sorted(DRAFT_DIR.glob("draft_*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(item, dict):
            rows.append(item)
    rows.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return rows


def _template(content_type: str, content_id: str) -> dict[str, Any]:
    if content_type == "story_arc":
        return {
            "schema_version": 2, "id": content_id, "version": 1, "title": content_id,
            "category": "daily", "priority": "major", "scene_type": "daily",
            "entry_node": "opening", "max_blocking_decisions": 2,
            "interaction_budget": {"default_max_freeform_steps": 2, "choices_visible_immediately": True},
            "roles": {}, "parameters": {},
            "nodes": {
                "opening": {"kind": "choice", "title": "开场", "blocking": True, "narrative_template_md": "## 开场\n\n等待领主裁断。", "choices": [{"id": "resolve", "label": "作出裁断", "description_md": "结束此事。", "effects": [], "transition": {"to": "resolved"}}]},
                "resolved": {"kind": "terminal", "title": "终幕", "blocking": False, "narrative_template_md": "## 终幕\n\n书记官封存卷宗。", "effects": [{"op": "resolve_entry_event"}]},
            },
        }
    if content_type == "storylet":
        return {"schema_version": 1, "chain_id": content_id, "nodes": [{"id": content_id, "node_key": "petition", "title": content_id, "category": "daily", "source_kind": "realm", "priority": "minor", "base_weight": 1, "cooldown_days": 45, "blocking": True, "scene_type": "daily", "triggers": {}, "roles": {}, "parameters": {}, "narrative_template_md": "## 新事件\n\n等待领主裁断。", "choices": [{"id": "acknowledge", "label": "知晓", "description_md": "书记官记录此事。", "effects": [{"op": "append_history"}]}]}]}
    if content_type == "preset_character":
        return {"schema_version": 1, "id": content_id, "name": content_id, "kind": "commoner", "gender": "未说明", "age": 18, "role": "领民", "description_md": "", "body_preset_id": "common", "components": {}, "initial_inventory": [], "initial_equipment": {}, "tags": [], "status": "active"}
    if content_type == "item":
        return {"name": content_id, "type": "misc", "allowed_slots": [], "occupied_slots": [], "armor": 0, "damage": 0, "weight": 0, "durability": 100, "warmth": 0, "value": 0, "description": "", "effects": {"character_attributes": {}, "realm_resources": {}}}
    if content_type == "character_kind":
        return {"label": content_id, "components": ["health"]}
    if content_type == "character_component":
        return {}
    if content_type == "character_attribute":
        return {"name": content_id, "label": content_id, "influence": ""}
    if content_type == "body_part":
        return {"label": content_id, "category": "limb", "side": "both", "parent_id": None, "pair_id": None, "adult_only": False, "sex_restriction": "any", "tags": []}
    if content_type == "equipment_slot":
        return {"label": content_id, "body_part_id": None, "virtual": True, "group": "public", "adult_only": False, "examples": []}
    return {"label": content_id, "slots": []}


def create_draft(request: DraftCreateRequest) -> dict[str, Any]:
    validate_content_identity(request.content_type, request.content_id)
    if request.operation == "update":
        published = get_document(request.content_type, request.content_id)
        document = deepcopy(request.document or published["document"])
        base_revision = published["revision"]
    else:
        try:
            get_document(request.content_type, request.content_id)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
        else:
            raise HTTPException(409, "相同 id 的正式内容已经存在")
        document = deepcopy(request.document or _template(request.content_type, request.content_id))
        base_revision = "missing"
    timestamp = now_iso()
    draft = {
        "id": f"draft_{uuid.uuid4().hex}", "content_type": request.content_type,
        "content_id": request.content_id, "operation": request.operation,
        "base_revision": base_revision, "document": document, "status": "editing",
        "revision": revision_for(document), "validation": validation_payload(request.content_type, request.content_id, document),
        "created_at": timestamp, "updated_at": timestamp,
    }
    return _write(draft)


def update_draft(draft_id: str, document: dict[str, Any], expected_revision: str = "") -> dict[str, Any]:
    draft = draft_by_id(draft_id)
    if expected_revision and expected_revision != draft.get("revision"):
        raise HTTPException(409, detail={"code": "content_revision_conflict", "server_revision": draft.get("revision")})
    draft["document"] = deepcopy(document)
    draft["revision"] = revision_for(document)
    draft["validation"] = validation_payload(draft["content_type"], draft["content_id"], document)
    draft["updated_at"] = now_iso()
    draft["status"] = "editing"
    return _write(draft)


def validate_draft(draft_id: str) -> dict[str, Any]:
    draft = draft_by_id(draft_id)
    draft["validation"] = validation_payload(draft["content_type"], draft["content_id"], draft["document"])
    draft["updated_at"] = now_iso()
    _write(draft)
    return draft["validation"]


def delete_draft(draft_id: str) -> None:
    path = _path(draft_id)
    if not path.exists():
        raise HTTPException(404, "未找到草稿")
    path.unlink()
