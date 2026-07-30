from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..catalog import BUILDINGS, BUILDINGS_BY_NAME, RESOURCES, UNITS
from ..engine.hermes_context import catalog_summary, compact_state_for_agent, public_action_contract
from ..engine.hermes_actions import VALID_EVENT_SEVERITIES
from ..engine.mutations import tile_at
from ..engine.state import mutation_result, require_state
from ..systems import characters

router = APIRouter()

DescribeTargetType = Literal[
    "realm",
    "lord",
    "tile",
    "resource",
    "building",
    "unit",
    "diplomacy",
    "army_status",
    "character",
    "item",
]


class AgentEventRequest(BaseModel):
    phase: str = "events"
    kind: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=500)
    severity: Literal["info", "warning", "critical"] = "info"
    data: dict[str, Any] = Field(default_factory=dict)


def _description_rules() -> dict[str, Any]:
    return {
        "allow_state_mutation": False,
        "language": "zh-CN",
        "style": "中世纪领地管理；具体、可感知、避免现代词汇",
    }


def _realm_target(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": state.get("realm_name"),
        "turn": state.get("turn"),
        "season": state.get("season"),
        "weather": state.get("weather"),
        "time": state.get("time", {}),
        "game_mode": state.get("game_mode", "strategic"),
        "active_scene": state.get("active_scene"),
        "resources": state.get("resources", {}),
        "buildings": state.get("buildings", {}),
        "laws": state.get("laws", []),
        "diplomacy": state.get("diplomacy", {}),
    }


def _lord_target(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": state.get("lord_name"),
        "gender": state.get("lord_gender"),
        "appearance": state.get("appearance"),
        "personality": state.get("personality"),
        "talents": state.get("talents", []),
    }


def _lookup_by_id_or_name(items: dict[str, dict[str, Any]], by_name: dict[str, dict[str, Any]], key: str) -> dict[str, Any] | None:
    if key in items:
        return {"id": key, **items[key]}
    item = by_name.get(key)
    return item.copy() if item else None


def _resolve_target(
    state: dict[str, Any],
    target_type: DescribeTargetType,
    x: int | None,
    y: int | None,
    key: str | None,
    name: str | None,
    faction: str | None,
) -> dict[str, Any]:
    if target_type == "realm":
        return _realm_target(state)
    if target_type == "lord":
        return _lord_target(state)
    if target_type == "tile":
        if x is None or y is None:
            raise HTTPException(422, "描述 tile 必须提供 x 和 y")
        tile = tile_at(state, x, y)
        if tile is None:
            raise HTTPException(404, "未找到地图格")
        return tile
    if target_type == "resource":
        resource_key = key or name
        if not resource_key or resource_key not in RESOURCES:
            raise HTTPException(422, "未知资源")
        return {"id": resource_key, **RESOURCES[resource_key], "value": state.get("resources", {}).get(resource_key, 0)}
    if target_type == "building":
        building_key = key or name
        if not building_key:
            raise HTTPException(422, "描述 building 必须提供 key 或 name")
        building = _lookup_by_id_or_name(BUILDINGS, BUILDINGS_BY_NAME, building_key)
        if not building:
            raise HTTPException(422, "未知建筑")
        building["count"] = state.get("buildings", {}).get(building.get("name"), 0)
        return building
    if target_type == "unit":
        unit_key = key or name
        if not unit_key or unit_key not in UNITS:
            raise HTTPException(422, "未知兵种")
        return {"id": unit_key, **UNITS[unit_key], "count": state.get("army", {}).get(unit_key, 0)}
    if target_type == "diplomacy":
        faction_name = faction or name or key
        if not faction_name:
            raise HTTPException(422, "描述 diplomacy 必须提供 faction/name/key")
        diplomacy = state.get("diplomacy", {})
        if faction_name not in diplomacy:
            raise HTTPException(404, "未找到外交对象")
        return {"faction": faction_name, "state": diplomacy[faction_name]}
    if target_type == "army_status":
        return {"army": state.get("army", {}), "army_status": state.get("army_status", {})}
    if target_type == "character":
        character_key = key or name
        if not character_key:
            raise HTTPException(422, "描述 character 必须提供 key 或 name")
        try:
            return characters.public_character_entry(characters.get_character(state, character_key))
        except KeyError:
            matches = [item for item in characters.list_characters(state) if item.get("name") == character_key]
            if matches:
                return matches[0]
            raise HTTPException(404, "未找到人物")
    return {"key": key, "name": name, "faction": faction, "x": x, "y": y}


@router.get("/agent/context")
def agent_context() -> dict[str, Any]:
    state = require_state()
    return {
        "mode": "lord-tail-agent-context",
        "state": compact_state_for_agent(state),
        "catalog_summary": catalog_summary(),
        "allowed_actions": public_action_contract(),
        "mutation_api": {
            "read": "GET /api/state",
            "time": "GET /api/time",
            "time_advance": "POST /api/state/time/advance",
            "strategic_turn": "POST /api/game/strategic-turn",
            "council_read": "GET /api/council/current",
            "council_resolve": "POST /api/council/{meeting_id}/resolve",
            "strategy_read": "GET /api/strategy/current",
            "strategy_analysis": "GET /api/strategy/analysis",
            "strategy_advice": "GET /api/strategy/advice",
            "legal_actions": "GET /api/actions/legal",
            "execute_action": "POST /api/actions/execute",
            "scene_start": "POST /api/game/scenes",
            "scene_step": "POST /api/game/scenes/current/step",
            "scene_advance_time": "POST /api/game/scenes/current/advance-time",
            "scene_end": "POST /api/game/scenes/current/end",
            "resources": "POST /api/state/resources",
            "population": "POST /api/state/population",
            "morale": "POST /api/state/morale",
            "army": "POST /api/state/army",
            "diplomacy": "POST /api/state/diplomacy",
            "buildings": "POST /api/state/buildings",
            "battles": "POST /api/state/battles/resolve",
            "events": "POST /api/agent/events",
            "scheduled_events_read": "GET /api/events",
            "scheduled_event_schedule": "POST /api/state/events/schedule",
            "scheduled_event_check_due": "POST /api/state/events/check-due",
            "scheduled_event_cancel": "POST /api/state/events/{event_id}/cancel",
            "scheduled_event_reschedule": "POST /api/state/events/{event_id}/reschedule",
            "scheduled_event_resolve": "POST /api/state/events/{event_id}/resolve",
            "history": "POST /api/state/history",
            "characters_read": "GET /api/characters",
            "character_upsert": "POST /api/state/characters",
            "character_patch": "PATCH /api/state/characters/{character_id}",
        },
    }


@router.get("/agent/describe-context")
def describe_context(
    target_type: DescribeTargetType = Query(...),
    x: int | None = None,
    y: int | None = None,
    key: str | None = None,
    name: str | None = None,
    faction: str | None = None,
) -> dict[str, Any]:
    state = require_state()
    return {
        "target_type": target_type,
        "target": _resolve_target(state, target_type, x, y, key, name, faction),
        "surrounding_state": {
            "realm": _realm_target(state),
            "lord": _lord_target(state),
            "characters": characters.list_characters(state, include_inactive=False)[:30],
            "recent_events": state.get("recent_events", [])[-10:],
        },
        "catalog_summary": catalog_summary(),
        "description_rules": _description_rules(),
    }


@router.post("/agent/events")
def record_agent_event(request: AgentEventRequest) -> dict[str, Any]:
    if request.severity not in VALID_EVENT_SEVERITIES:
        raise HTTPException(422, "severity 必须是 info/warning/critical")
    state = require_state()
    event = request.model_dump()
    state.setdefault("recent_events", []).append(event)
    state["recent_events"] = state["recent_events"][-50:]
    return mutation_result(state, f"书记官事件已入册：{request.kind}")
