from __future__ import annotations

from typing import Any

from fastapi import HTTPException


VALID_SCENE_TYPES = {"dialogue", "caravan", "diplomacy", "battle", "court", "council", "lord_event", "daily", "sexual"}


def normalize_scene_state(state: dict[str, Any]) -> None:
    state.setdefault("game_mode", "strategic")
    state.setdefault("active_scene", None)
    state.setdefault("scene_seq", 0)
    scene = state.get("active_scene")
    if isinstance(scene, dict):
        scene.setdefault("status", "active")
        scene.setdefault("elapsed_hours", 0)
        scene.setdefault("elapsed_minutes", 0)
        scene.setdefault("elapsed_days", 0)
        scene.setdefault("time_locked", True)
        scene.setdefault("participants", [])
        scene.setdefault("flags", {})
        scene.setdefault("summary", "")
        scene.setdefault("recent_messages", [])
        state["game_mode"] = "scene"
    elif state.get("game_mode") == "scene":
        state["game_mode"] = "strategic"


def _next_scene_id(state: dict[str, Any]) -> str:
    state["scene_seq"] = int(state.get("scene_seq", 0)) + 1
    return f"scene_{state['scene_seq']}"


def start_scene(
    state: dict[str, Any],
    scene_type: str,
    title: str,
    participants: list[dict[str, Any]] | None = None,
    flags: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalize_scene_state(state)
    if state.get("active_scene") is not None:
        raise HTTPException(409, "当前已有进行中的场景")
    if scene_type not in VALID_SCENE_TYPES:
        raise HTTPException(422, f"未知场景类型：{scene_type}")
    scene = {
        "id": _next_scene_id(state),
        "type": scene_type,
        "title": title or "未命名场景",
        "status": "active",
        "started_turn": state.get("turn", 1),
        "started_calendar_day": state.get("time", {}).get("calendar_day", 1),
        "elapsed_hours": 0,
        "elapsed_minutes": 0,
        "elapsed_days": 0,
        "time_locked": True,
        "participants": participants or [],
        "flags": flags or {},
        "summary": "",
        "recent_messages": [],
    }
    state["active_scene"] = scene
    state["game_mode"] = "scene"
    return scene


def require_active_scene(state: dict[str, Any]) -> dict[str, Any]:
    normalize_scene_state(state)
    scene = state.get("active_scene")
    if not isinstance(scene, dict):
        raise HTTPException(409, "当前没有进行中的场景")
    return scene


def append_scene_message(
    state: dict[str, Any],
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    scene = require_active_scene(state)
    scene.setdefault("recent_messages", []).append({
        "role": role,
        "content": content,
        "metadata": metadata or {},
    })
    scene["recent_messages"] = scene["recent_messages"][-30:]


def end_scene(state: dict[str, Any], summary: str = "", outcome: dict[str, Any] | None = None) -> dict[str, Any]:
    scene = require_active_scene(state)
    flags = scene.get("flags", {}) if isinstance(scene.get("flags"), dict) else {}
    if flags.get("source") == "storylet" and flags.get("blocking") and flags.get("story_event_id"):
        from ..storylets.instances import instance_by_id

        try:
            instance = instance_by_id(state, str(flags["story_event_id"]))
        except HTTPException:
            instance = None
        if isinstance(instance, dict) and instance.get("status") in {"active", "awaiting_choice"}:
            raise HTTPException(409, "该剧情事件必须先完成领主裁断，不能直接结束场景")
    scene["status"] = "completed"
    scene["summary"] = summary or scene.get("summary", "")
    scene["outcome"] = outcome or {}
    archived = dict(scene)
    state.setdefault("recent_events", []).append({
        "phase": "scene",
        "kind": "scene_completed",
        "severity": "info",
        "message": summary or f"场景结束：{scene.get('title', scene.get('id'))}",
        "data": {"scene": archived},
    })
    state["recent_events"] = state["recent_events"][-50:]
    state["active_scene"] = None
    state["game_mode"] = "strategic"
    return archived
