from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException

from ..engine.time import time_point_from_state
from ..systems.characters import get_character

INVERSE_TYPES = {
    "parent": "child", "child": "parent", "spouse": "spouse", "sibling": "sibling",
    "employer": "employee", "employee": "employer", "debtor": "creditor", "creditor": "debtor",
    "guardian": "ward", "ward": "guardian", "patron": "client", "client": "patron",
    "rival": "rival", "friend": "friend",
}
SYMMETRIC_TYPES = {"spouse", "sibling", "rival", "friend"}


def normalize_relationship_state(state: dict[str, Any]) -> None:
    rel = state.setdefault("character_relationships", {})
    edges = rel.get("edges") if isinstance(rel.get("edges"), list) else []
    rel["edges"] = [edge for edge in edges if isinstance(edge, dict)]
    max_rel = 0
    for edge in rel["edges"]:
        try:
            max_rel = max(max_rel, int(str(edge.get("id", "")).removeprefix("rel_")))
        except ValueError:
            pass
    rel["next_id"] = max(max_rel + 1, int(rel.get("next_id", 1) or 1))
    households = state.setdefault("households", {})
    entries = households.get("entries") if isinstance(households.get("entries"), list) else []
    households["entries"] = [entry for entry in entries if isinstance(entry, dict)]
    max_household = 0
    for entry in households["entries"]:
        try:
            max_household = max(max_household, int(str(entry.get("id", "")).removeprefix("household_")))
        except ValueError:
            pass
    households["next_id"] = max(max_household + 1, int(households.get("next_id", 1) or 1))


def _age(character: dict[str, Any]) -> int | None:
    try:
        return int(character.get("age")) if character.get("age") is not None else None
    except (TypeError, ValueError):
        return None


def create_relationship(state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    normalize_relationship_state(state)
    from_id, to_id = str(payload.get("from_character_id", "")), str(payload.get("to_character_id", ""))
    if not from_id or not to_id or from_id == to_id:
        raise HTTPException(422, "关系两端必须是不同的已存在人物")
    try:
        first, second = get_character(state, from_id), get_character(state, to_id)
    except KeyError as exc:
        raise HTTPException(422, f"关系人物不存在：{exc.args[0]}") from exc
    relation_type = str(payload.get("type", ""))
    if relation_type not in INVERSE_TYPES:
        raise HTTPException(422, f"未知关系类型：{relation_type}")
    if relation_type == "spouse" and ((_age(first) or 0) < 18 or (_age(second) or 0) < 18):
        raise HTTPException(422, "未成年人物不能建立配偶关系")
    if relation_type == "parent" and _age(first) is not None and _age(second) is not None and _age(first) - _age(second) < 14:
        raise HTTPException(422, "父母与子女的年龄差不能小于十四岁")
    if relation_type in {"parent", "child"}:
        for edge in state["character_relationships"]["edges"]:
            if edge.get("status", "active") != "active":
                continue
            if edge.get("from_character_id") == to_id and edge.get("to_character_id") == from_id and edge.get("type") == relation_type:
                raise HTTPException(422, "父母/子女关系不能形成直接循环")
    if relation_type in SYMMETRIC_TYPES and from_id > to_id:
        from_id, to_id = to_id, from_id
    for edge in state["character_relationships"]["edges"]:
        if edge.get("status", "active") == "active" and edge.get("from_character_id") == from_id and edge.get("to_character_id") == to_id and edge.get("type") == relation_type:
            return edge
    seq = state["character_relationships"]["next_id"]
    state["character_relationships"]["next_id"] = seq + 1
    edge = {
        "id": f"rel_{seq:06d}", "from_character_id": from_id, "to_character_id": to_id,
        "type": relation_type, "inverse_type": INVERSE_TYPES[relation_type],
        "strength": max(0, min(100, int(payload.get("strength", 50)))), "status": "active",
        "started_time": time_point_from_state(state), "ended_time": None,
        "source_story_event_id": str(payload.get("source_story_event_id", "")),
        "metadata": deepcopy(payload.get("metadata", {})) if isinstance(payload.get("metadata"), dict) else {},
    }
    state["character_relationships"]["edges"].append(edge)
    return edge


def update_relationship(state: dict[str, Any], relationship_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    normalize_relationship_state(state)
    for edge in state["character_relationships"]["edges"]:
        if edge.get("id") != relationship_id:
            continue
        if "strength" in patch:
            edge["strength"] = max(0, min(100, int(patch["strength"])))
        if "status" in patch:
            edge["status"] = str(patch["status"])
            if edge["status"] != "active":
                edge["ended_time"] = time_point_from_state(state)
        if isinstance(patch.get("metadata"), dict):
            edge["metadata"] = {**edge.get("metadata", {}), **deepcopy(patch["metadata"])}
        return edge
    raise HTTPException(404, "未找到人物关系")


def relationships_for(state: dict[str, Any], character_id: str) -> list[dict[str, Any]]:
    normalize_relationship_state(state)
    try:
        get_character(state, character_id)
    except KeyError as exc:
        raise HTTPException(404, "未找到人物") from exc
    return [deepcopy(edge) for edge in state["character_relationships"]["edges"] if character_id in {edge.get("from_character_id"), edge.get("to_character_id")}]


def create_household(state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    normalize_relationship_state(state)
    member_ids = list(dict.fromkeys(str(value) for value in payload.get("member_ids", []) if value))
    for character_id in member_ids:
        try:
            get_character(state, character_id)
        except KeyError as exc:
            raise HTTPException(422, f"家庭成员不存在：{character_id}") from exc
    seq = state["households"]["next_id"]
    state["households"]["next_id"] = seq + 1
    household = {
        "id": f"household_{seq:06d}", "status": "active", "class_id": str(payload.get("class_id", "")),
        "home_tile": str(payload.get("home_tile", "")), "member_ids": member_ids,
        "head_character_id": str(payload.get("head_character_id") or (member_ids[0] if member_ids else "")),
        "wealth": max(0, int(payload.get("wealth", 0))),
        "created_by_story_event_id": str(payload.get("created_by_story_event_id", "")),
    }
    state["households"]["entries"].append(household)
    return household
