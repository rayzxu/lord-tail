from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .types import TurnEvent

DEFAULT_RELATED = {
    "people": [],
    "factions": [],
    "tiles": [],
    "buildings": [],
    "resources": [],
    "scheduled_events": [],
    "turn_events": [],
}

IMPORTANT_KINDS = {
    "project_completed",
    "building_completed_effect",
    "law_enacted",
    "battle_resolved",
    "stance_changed",
    "food_depleted",
    "treasury_empty",
    "rebellion_risk",
    "war_warning",
    "scene_ended",
    "scene_completed",
    "caravan_arrived",
    "caravan_cancelled",
    "plague",
    "fire",
    "famine",
}

SOURCE_BY_PHASE = {
    "construction": "pipeline",
    "player_action": "pipeline",
    "military": "battle",
    "diplomacy": "diplomacy",
    "events": "pipeline",
    "scene": "scene",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clock_24(state: dict[str, Any]) -> str:
    time = state.get("time", {})
    if time.get("clock_24") or time.get("clock"):
        return str(time.get("clock_24") or time.get("clock"))
    hour = int(time.get("hour_24", time.get("hour", 6))) % 24
    minute = int(time.get("minute", 0)) % 60
    return f"{hour:02d}:{minute:02d}"


def _clean_related(related: dict[str, Any] | None = None) -> dict[str, list[Any]]:
    clean = {key: list(value) for key, value in DEFAULT_RELATED.items()}
    if not isinstance(related, dict):
        return clean
    for key in clean:
        value = related.get(key)
        if isinstance(value, list):
            clean[key] = value
    return clean


def normalize_history(state: dict[str, Any]) -> None:
    history = state.setdefault("history", {})
    entries = history.get("entries", [])
    if not isinstance(entries, list):
        entries = []
    normalized: list[dict[str, Any]] = []
    max_seen = 0
    for index, raw in enumerate(entries, start=1):
        if not isinstance(raw, dict):
            continue
        entry = dict(raw)
        entry_id = str(entry.get("id") or f"hist_{index:06d}")
        entry["id"] = entry_id
        try:
            if entry_id.startswith("hist_"):
                max_seen = max(max_seen, int(entry_id.split("_", 1)[1]))
        except (IndexError, ValueError):
            pass
        entry.setdefault("turn", state.get("turn", 1))
        entry.setdefault("calendar_day", state.get("time", {}).get("calendar_day", 1))
        entry.setdefault("clock_24", _clock_24(state))
        entry.setdefault("season", state.get("season", state.get("time", {}).get("season", "春季")))
        entry.setdefault("weather", state.get("weather", state.get("time", {}).get("weather", "细雨")))
        entry["title"] = str(entry.get("title") or "未命名历史")
        entry["summary_md"] = str(entry.get("summary_md") or "")
        entry["details_md"] = str(entry.get("details_md") or "")
        entry["source"] = str(entry.get("source") or "system")
        entry["importance"] = max(1, min(5, int(entry.get("importance", 3))))
        entry["visibility"] = str(entry.get("visibility") or "player")
        tags = entry.get("tags", [])
        entry["tags"] = [str(tag) for tag in tags] if isinstance(tags, list) else []
        entry["related"] = _clean_related(entry.get("related"))
        entry["created_by"] = str(entry.get("created_by") or "backend")
        entry.setdefault("created_at", _now())
        entry.setdefault("updated_at", entry["created_at"])
        normalized.append(entry)
    history["entries"] = normalized
    history["next_id"] = max(int(history.get("next_id", 1) or 1), max_seen + 1)


def _next_history_id(state: dict[str, Any]) -> str:
    normalize_history(state)
    history = state["history"]
    next_id = int(history.get("next_id", 1))
    history["next_id"] = next_id + 1
    return f"hist_{next_id:06d}"


def append_history_entry(
    state: dict[str, Any],
    *,
    title: str,
    summary_md: str,
    details_md: str = "",
    source: str = "system",
    importance: int = 3,
    visibility: str = "player",
    tags: list[str] | None = None,
    related: dict[str, Any] | None = None,
    created_by: str = "backend",
) -> dict[str, Any]:
    normalize_history(state)
    timestamp = _now()
    time = state.get("time", {})
    entry = {
        "id": _next_history_id(state),
        "turn": int(state.get("turn", 1)),
        "calendar_day": int(time.get("calendar_day", 1)),
        "clock_24": _clock_24(state),
        "season": str(state.get("season") or time.get("season") or "春季"),
        "weather": str(state.get("weather") or time.get("weather") or "细雨"),
        "title": str(title)[:160] or "未命名历史",
        "summary_md": str(summary_md)[:8000],
        "details_md": str(details_md)[:20000],
        "source": str(source or "system")[:60],
        "importance": max(1, min(5, int(importance))),
        "visibility": str(visibility or "player")[:40],
        "tags": [str(tag)[:60] for tag in (tags or [])],
        "related": _clean_related(related),
        "created_by": str(created_by or "backend")[:60],
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    state["history"]["entries"].append(entry)
    return entry


def update_history_entry(state: dict[str, Any], entry_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    normalize_history(state)
    for entry in state["history"]["entries"]:
        if entry["id"] != entry_id:
            continue
        for key in ("title", "summary_md", "details_md", "source", "visibility", "created_by"):
            if key in patch:
                entry[key] = str(patch[key])
        if "importance" in patch:
            entry["importance"] = max(1, min(5, int(patch["importance"])))
        if isinstance(patch.get("tags"), list):
            entry["tags"] = [str(tag)[:60] for tag in patch["tags"]]
        if isinstance(patch.get("related"), dict):
            entry["related"] = _clean_related(patch["related"])
        entry["updated_at"] = _now()
        return entry
    raise KeyError(entry_id)


def _event_dict(event: TurnEvent | dict[str, Any]) -> dict[str, Any]:
    if isinstance(event, dict):
        return event
    return event.model_dump() if hasattr(event, "model_dump") else event.dict()


def _event_importance(event: dict[str, Any]) -> int:
    severity = event.get("severity", "info")
    kind = str(event.get("kind", ""))
    data = event.get("data", {}) if isinstance(event.get("data"), dict) else {}
    if severity == "critical" or kind in {"battle_resolved", "food_depleted", "rebellion_risk", "plague", "fire", "famine"}:
        return 5
    if kind in {"law_enacted", "stance_changed", "war_warning", "caravan_cancelled"}:
        return 4
    if kind == "relation_changed" and abs(int(data.get("after", 0)) - int(data.get("before", 0))) >= 20:
        return 4
    if kind in {"project_completed", "building_completed_effect", "caravan_arrived", "treasury_empty", "scene_ended", "scene_completed"}:
        return 3
    if severity == "warning":
        return 3
    return 0


def _should_record_event(event: dict[str, Any]) -> bool:
    kind = str(event.get("kind", ""))
    severity = event.get("severity", "info")
    return kind in IMPORTANT_KINDS or severity in {"warning", "critical"} or _event_importance(event) >= 3


def _event_tags(event: dict[str, Any]) -> list[str]:
    phase = str(event.get("phase", "events"))
    kind = str(event.get("kind", "event"))
    tags = {phase, kind}
    if "battle" in kind or phase == "military":
        tags.add("battle")
        tags.add("military")
    if "diplomacy" in phase or "relation" in kind or "stance" in kind or "war" in kind:
        tags.add("diplomacy")
    if "building" in kind or "project" in kind or phase == "construction":
        tags.add("construction")
    if kind.startswith("scene_") or phase == "scene":
        tags.add("scene")
    if kind in {"food_depleted", "treasury_empty", "rebellion_risk"}:
        tags.add("crisis")
    return sorted(tags)


def _event_related(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data", {}) if isinstance(event.get("data"), dict) else {}
    related = _clean_related()
    faction = data.get("faction")
    if faction:
        related["factions"].append(str(faction))
    building = data.get("building")
    if building:
        related["buildings"].append(str(building))
    resource = data.get("resource")
    if resource:
        related["resources"].append(str(resource))
    x, y = data.get("x"), data.get("y")
    if isinstance(x, int) and isinstance(y, int):
        related["tiles"].append(f"{x}:{y}")
    battle_id = data.get("id")
    if battle_id:
        related["turn_events"].append(str(battle_id))
    scene = data.get("scene") if isinstance(data.get("scene"), dict) else None
    if scene:
        for participant in scene.get("participants", []):
            if isinstance(participant, dict) and participant.get("name"):
                related["people"].append(str(participant["name"]))
    return related


def _event_title(event: dict[str, Any]) -> str:
    kind = str(event.get("kind", "event"))
    data = event.get("data", {}) if isinstance(event.get("data"), dict) else {}
    if kind == "project_completed":
        return f"{data.get('building', '建筑')}竣工"
    if kind == "building_completed_effect":
        return f"{data.get('building', '新建筑')}入档"
    if kind == "law_enacted":
        return "领主发布法令"
    if kind == "battle_resolved":
        return str(data.get("label") or "战斗结算")
    if kind in {"stance_changed", "relation_changed"}:
        return f"{data.get('faction', '某方势力')}外交变化"
    if kind == "war_warning":
        return f"{data.get('faction', '敌对势力')}逼近战争边缘"
    if kind == "scene_ended":
        scene = data.get("scene") if isinstance(data.get("scene"), dict) else {}
        return f"场景结束：{scene.get('title', '领主事件')}"
    return str(event.get("message") or kind)[:80]


def auto_record_turn_events(state: dict[str, Any], events: list[TurnEvent | dict[str, Any]]) -> list[dict[str, Any]]:
    normalize_history(state)
    created: list[dict[str, Any]] = []
    seen_turn_event_ids = {
        related_id
        for entry in state["history"]["entries"]
        for related_id in entry.get("related", {}).get("turn_events", [])
    }
    for raw in events:
        event = _event_dict(raw)
        if not _should_record_event(event):
            continue
        kind = str(event.get("kind", "event"))
        marker = f"{state.get('turn', 1)}:{kind}:{event.get('message', '')}:{event.get('data', {})}"
        if marker in seen_turn_event_ids:
            continue
        related = _event_related(event)
        related["turn_events"].append(marker)
        entry = append_history_entry(
            state,
            title=_event_title(event),
            summary_md=str(event.get("message") or ""),
            details_md="",
            source=SOURCE_BY_PHASE.get(str(event.get("phase", "")), "pipeline"),
            importance=_event_importance(event),
            visibility="player",
            tags=_event_tags(event),
            related=related,
            created_by="backend",
        )
        created.append(entry)
        seen_turn_event_ids.add(marker)
    state["last_history_entries_created"] = created
    return created


def select_history_context(
    state: dict[str, Any],
    *,
    tags: list[str] | None = None,
    people: list[str] | None = None,
    factions: list[str] | None = None,
    tiles: list[str] | None = None,
    min_importance: int = 3,
    limit: int = 12,
) -> list[dict[str, Any]]:
    normalize_history(state)
    tag_set = {str(tag) for tag in (tags or [])}
    people_set = {str(item) for item in (people or [])}
    faction_set = {str(item) for item in (factions or [])}
    tile_set = {str(item) for item in (tiles or [])}
    rows: list[tuple[int, dict[str, Any]]] = []
    for entry in state["history"]["entries"]:
        if entry.get("visibility") not in {"player", "hint"}:
            continue
        if int(entry.get("importance", 0)) < min_importance:
            continue
        score = int(entry.get("importance", 0)) * 10
        related = entry.get("related", {})
        entry_tags = set(entry.get("tags", []))
        if tag_set:
            hits = len(tag_set & entry_tags)
            if not hits:
                continue
            score += hits * 5
        if people_set:
            hits = len(people_set & set(related.get("people", [])))
            if not hits:
                continue
            score += hits * 5
        if faction_set:
            hits = len(faction_set & set(related.get("factions", [])))
            if not hits:
                continue
            score += hits * 5
        if tile_set:
            hits = len(tile_set & set(related.get("tiles", [])))
            if not hits:
                continue
            score += hits * 5
        score += int(entry.get("calendar_day", 0))
        rows.append((score, entry))
    rows.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "id": entry["id"],
            "turn": entry.get("turn"),
            "calendar_day": entry.get("calendar_day"),
            "clock_24": entry.get("clock_24"),
            "season": entry.get("season"),
            "title": entry.get("title"),
            "summary_md": entry.get("summary_md"),
            "source": entry.get("source"),
            "importance": entry.get("importance"),
            "tags": entry.get("tags", []),
            "related": entry.get("related", {}),
        }
        for _, entry in rows[:limit]
    ]
