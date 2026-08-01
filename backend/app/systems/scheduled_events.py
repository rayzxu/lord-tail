from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from ..catalog import EVENT_TEMPLATES
from ..engine.history import append_history_entry
from ..engine.time import (
    add_to_time_point,
    current_time_key,
    normalize_time,
    normalize_time_point,
    parse_clock_24,
    season_for_day,
    time_key,
    time_point_from_state,
)
from ..engine.types import TurnEvent

EVENT_STATUSES = {"scheduled", "due", "active", "resolved", "cancelled", "missed"}
EVENT_VISIBILITIES = {"player", "hint", "secret", "debug"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _template(event_type: str) -> dict[str, Any]:
    template = EVENT_TEMPLATES.get(event_type)
    if not isinstance(template, dict):
        raise HTTPException(422, f"未知长期事件类型：{event_type}")
    return template


def _next_event_id(state: dict[str, Any]) -> str:
    normalize_scheduled_events(state)
    scheduled = state["scheduled_events"]
    next_id = int(scheduled.get("next_id", 1))
    scheduled["next_id"] = next_id + 1
    return f"evt_{next_id:06d}"


def _clean_related(related: dict[str, Any] | None = None) -> dict[str, list[Any]]:
    clean = {
        "people": [],
        "factions": [],
        "tiles": [],
        "buildings": [],
        "history_entries": [],
    }
    if not isinstance(related, dict):
        return clean
    for key in clean:
        value = related.get(key)
        if isinstance(value, list):
            clean[key] = value
    return clean


def _resolve_due_time(
    state: dict[str, Any],
    *,
    due_time: dict[str, Any] | None = None,
    in_days: int | None = None,
    in_hours: int | None = None,
    in_minutes: int | None = None,
    clock_24: str | None = None,
) -> dict[str, Any]:
    if due_time is not None:
        resolved = normalize_time_point(due_time, state)
    else:
        resolved = add_to_time_point(
            time_point_from_state(state),
            days=max(0, int(in_days or 0)),
            hours=max(0, int(in_hours or 0)),
            minutes=max(0, int(in_minutes or 0)),
        )
    if clock_24:
        hour, minute = parse_clock_24(clock_24, resolved["clock_24"])
        resolved["clock_24"] = f"{hour:02d}:{minute:02d}"
    resolved["season"] = season_for_day(int(resolved["calendar_day"]))
    return resolved


def normalize_scheduled_events(state: dict[str, Any]) -> None:
    normalize_time(state)
    scheduled = state.setdefault("scheduled_events", {})
    entries = scheduled.get("entries", [])
    if not isinstance(entries, list):
        entries = []
    normalized: list[dict[str, Any]] = []
    max_seen = 0
    for index, raw in enumerate(entries, start=1):
        if not isinstance(raw, dict):
            continue
        event = dict(raw)
        event_id = str(event.get("id") or f"evt_{index:06d}")
        event["id"] = event_id
        try:
            if event_id.startswith("evt_"):
                max_seen = max(max_seen, int(event_id.split("_", 1)[1]))
        except (IndexError, ValueError):
            pass
        event_type = str(event.get("type") or "custom")
        event["type"] = event_type
        template = EVENT_TEMPLATES.get(event_type, {})
        event["title"] = str(event.get("title") or template.get("label") or event_type)
        event["description_md"] = str(event.get("description_md") or template.get("prompt_hint") or "")
        event["status"] = str(event.get("status") or "scheduled")
        if event["status"] not in EVENT_STATUSES:
            event["status"] = "scheduled"
        event["visibility"] = str(event.get("visibility") or template.get("default_visibility") or "player")
        if event["visibility"] not in EVENT_VISIBILITIES:
            event["visibility"] = "player"
        event["importance"] = max(1, min(5, int(event.get("importance", template.get("default_importance", 3)))))
        event["created_time"] = normalize_time_point(event.get("created_time"), state)
        schedule = event.setdefault("schedule", {})
        if not isinstance(schedule, dict):
            schedule = {}
        legacy_due = {
            "calendar_day": event.get("due_calendar_day", schedule.get("due_calendar_day")),
            "clock_24": event.get("due_clock_24", schedule.get("due_clock_24") or template.get("default_due_clock_24") or "06:00"),
        }
        schedule["due_time"] = normalize_time_point(schedule.get("due_time") or legacy_due, state)
        schedule["window_days"] = max(0, int(schedule.get("window_days", 1)))
        repeat = schedule.get("repeat", template.get("default_repeat"))
        schedule["repeat"] = deepcopy(repeat) if isinstance(repeat, dict) else None
        event["schedule"] = schedule
        event.setdefault("conditions", {})
        if not isinstance(event["conditions"], dict):
            event["conditions"] = {}
        on_due = event.setdefault("on_due", {})
        if not isinstance(on_due, dict):
            on_due = {}
        event["on_due"] = {
            "mode": str(on_due.get("mode") or "activate"),
            "scene_type": str(on_due.get("scene_type") or template.get("default_scene_type") or "daily"),
            "turn_event_kind": str(on_due.get("turn_event_kind") or template.get("turn_event_kind") or f"{event_type}_due"),
            "suggested_prompt": str(on_due.get("suggested_prompt") or template.get("prompt_hint") or event["title"]),
        }
        on_resolve = event.setdefault("on_resolve", {})
        if not isinstance(on_resolve, dict):
            on_resolve = {}
        event["on_resolve"] = {
            "record_history": bool(on_resolve.get("record_history", True)),
            "schedule_next": bool(on_resolve.get("schedule_next", bool(schedule["repeat"]))),
        }
        event["related"] = _clean_related(event.get("related"))
        event["flags"] = event.get("flags") if isinstance(event.get("flags"), dict) else {}
        event["result_md"] = str(event.get("result_md") or "")
        event["created_by"] = str(event.get("created_by") or "backend")
        event.setdefault("updated_at", _now())
        normalized.append(event)
    scheduled["entries"] = normalized
    scheduled["next_id"] = max(int(scheduled.get("next_id", 1) or 1), max_seen + 1)


def schedule_event(
    state: dict[str, Any],
    *,
    event_type: str,
    title: str | None = None,
    description_md: str = "",
    due_time: dict[str, Any] | None = None,
    in_days: int | None = None,
    in_hours: int | None = None,
    in_minutes: int | None = None,
    clock_24: str | None = None,
    visibility: str | None = None,
    importance: int | None = None,
    related: dict[str, Any] | None = None,
    conditions: dict[str, Any] | None = None,
    flags: dict[str, Any] | None = None,
    created_by: str = "backend",
) -> dict[str, Any]:
    template = _template(event_type)
    normalize_scheduled_events(state)
    due = _resolve_due_time(
        state,
        due_time=due_time,
        in_days=in_days,
        in_hours=in_hours,
        in_minutes=in_minutes,
        clock_24=clock_24 if clock_24 or due_time is not None else template.get("default_due_clock_24"),
    )
    event = {
        "id": _next_event_id(state),
        "type": event_type,
        "title": title or template.get("label") or event_type,
        "description_md": description_md or template.get("prompt_hint", ""),
        "status": "scheduled",
        "visibility": visibility or template.get("default_visibility", "player"),
        "importance": max(1, min(5, int(importance if importance is not None else template.get("default_importance", 3)))),
        "created_time": time_point_from_state(state),
        "schedule": {
            "due_time": due,
            "window_days": 1,
            "repeat": deepcopy(template.get("default_repeat")) if isinstance(template.get("default_repeat"), dict) else None,
        },
        "conditions": conditions or {},
        "on_due": {
            "mode": "activate",
            "scene_type": template.get("default_scene_type", "daily"),
            "turn_event_kind": template.get("turn_event_kind", f"{event_type}_due"),
            "suggested_prompt": template.get("prompt_hint", title or event_type),
        },
        "on_resolve": {
            "record_history": True,
            "schedule_next": bool(template.get("default_repeat")),
        },
        "related": _clean_related(related),
        "flags": flags or {},
        "result_md": "",
        "created_by": created_by,
        "updated_at": _now(),
    }
    state["scheduled_events"]["entries"].append(event)
    return event


def _conditions_block_event(state: dict[str, Any], event: dict[str, Any]) -> str:
    conditions = event.get("conditions", {})
    diplomacy = state.get("diplomacy", {})
    for faction in conditions.get("requires_not_at_war_with", []) if isinstance(conditions, dict) else []:
        entry = diplomacy.get(faction)
        if isinstance(entry, dict) and entry.get("at_war"):
            return f"正在与 {faction} 交战。"
        if entry == "战争":
            return f"正在与 {faction} 交战。"
    return ""


def due_events(state: dict[str, Any]) -> list[dict[str, Any]]:
    normalize_scheduled_events(state)
    now_key = current_time_key(state)
    return [
        event
        for event in state["scheduled_events"]["entries"]
        if event.get("status") in {"scheduled", "due"} and time_key(event["schedule"]["due_time"]) <= now_key
    ]


def active_events(state: dict[str, Any]) -> list[dict[str, Any]]:
    normalize_scheduled_events(state)
    return [event for event in state["scheduled_events"]["entries"] if event.get("status") == "active"]


def upcoming_events(state: dict[str, Any], *, days: int = 9, min_importance: int = 3, limit: int = 10) -> list[dict[str, Any]]:
    normalize_scheduled_events(state)
    now_key = current_time_key(state)
    horizon = now_key + max(0, days) * 24 * 60
    rows = [
        event
        for event in state["scheduled_events"]["entries"]
        if event.get("status") in {"scheduled", "due"}
        and int(event.get("importance", 0)) >= min_importance
        and now_key < time_key(event["schedule"]["due_time"]) <= horizon
    ]
    rows.sort(key=lambda event: time_key(event["schedule"]["due_time"]))
    return rows[:limit]


def event_context(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "urgent_due_events": due_events(state),
        "active_events": active_events(state),
        "upcoming_events": upcoming_events(state),
    }


def activate_due_events(state: dict[str, Any], *, source: str = "pipeline") -> list[TurnEvent]:
    events: list[TurnEvent] = []
    for event in due_events(state):
        blocked_reason = _conditions_block_event(state, event)
        if blocked_reason:
            event["status"] = "missed"
            event["result_md"] = blocked_reason
            event["updated_at"] = _now()
            events.append(TurnEvent(
                phase="scheduled_events",
                kind="scheduled_event_missed",
                severity="warning",
                message=f"{event['title']}未能发生：{blocked_reason}",
                data={"event": event, "source": source},
            ))
            continue
        event["status"] = "active"
        event["activated_time"] = time_point_from_state(state)
        event["updated_at"] = _now()
        if event.get("type") == "council_session":
            from .council import open_meeting_from_event

            meeting = open_meeting_from_event(state, event)
            event.setdefault("flags", {})["meeting_id"] = meeting["id"]
        elif event.get("type") == "storylet_event":
            from ..storylets.service import activate_storylet_for_event

            instance = activate_storylet_for_event(state, event)
            event.setdefault("flags", {})["storylet_status"] = instance.get("status")
        on_due = event.get("on_due", {})
        events.append(TurnEvent(
            phase="scheduled_events",
            kind=str(on_due.get("turn_event_kind") or f"{event['type']}_due"),
            severity="warning" if int(event.get("importance", 0)) >= 4 else "info",
            message=f"{event['title']}已经到期：{on_due.get('suggested_prompt') or event.get('description_md')}",
            data={"event": event, "source": source},
        ))
    if events:
        state.setdefault("recent_events", []).extend(event.model_dump() for event in events)
        state["recent_events"] = state["recent_events"][-50:]
    return events


def cancel_event(state: dict[str, Any], event_id: str, *, reason_md: str, cancelled_by: str = "backend") -> dict[str, Any]:
    event = _event_by_id(state, event_id)
    event["status"] = "cancelled"
    event["result_md"] = reason_md
    event["cancelled_by"] = cancelled_by
    event["updated_at"] = _now()
    _record_event_history_if_needed(state, event, "事件取消", cancelled_by)
    return event


def reschedule_event(
    state: dict[str, Any],
    event_id: str,
    *,
    due_time: dict[str, Any] | None = None,
    in_days: int | None = None,
    in_hours: int | None = None,
    in_minutes: int | None = None,
    clock_24: str | None = None,
    reason_md: str = "",
) -> dict[str, Any]:
    event = _event_by_id(state, event_id)
    event["schedule"]["due_time"] = _resolve_due_time(
        state,
        due_time=due_time,
        in_days=in_days,
        in_hours=in_hours,
        in_minutes=in_minutes,
        clock_24=clock_24,
    )
    event["status"] = "scheduled"
    if reason_md:
        event.setdefault("flags", {})["reschedule_reason_md"] = reason_md
    event["updated_at"] = _now()
    return event


def resolve_event(
    state: dict[str, Any],
    event_id: str,
    *,
    result_md: str,
    outcome: dict[str, Any] | None = None,
    resolved_by: str = "backend",
) -> dict[str, Any]:
    event = _event_by_id(state, event_id)
    event["status"] = "resolved"
    event["result_md"] = result_md
    event["outcome"] = outcome or {}
    event["resolved_by"] = resolved_by
    event["resolved_time"] = time_point_from_state(state)
    event["updated_at"] = _now()
    _record_event_history_if_needed(state, event, "事件解决", resolved_by)
    if event.get("on_resolve", {}).get("schedule_next"):
        next_event = schedule_next_occurrence(state, event)
        if next_event:
            event.setdefault("flags", {})["next_event_id"] = next_event["id"]
    return event


def schedule_next_occurrence(state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any] | None:
    repeat = event.get("schedule", {}).get("repeat")
    if not isinstance(repeat, dict):
        return None
    kind = repeat.get("kind")
    interval = max(1, int(repeat.get("interval", 1)))
    due_time = event.get("schedule", {}).get("due_time", time_point_from_state(state))
    if kind == "seasonly":
        next_due = add_to_time_point(due_time, days=90 * interval)
    elif kind == "daily":
        next_due = add_to_time_point(due_time, days=interval)
    else:
        return None
    until_time = repeat.get("until_time")
    if isinstance(until_time, dict) and time_key(next_due) > time_key(until_time):
        return None
    return schedule_event(
        state,
        event_type=event["type"],
        title=event.get("title"),
        description_md=event.get("description_md", ""),
        due_time=next_due,
        visibility=event.get("visibility", "player"),
        importance=int(event.get("importance", 3)),
        related=event.get("related", {}),
        conditions=event.get("conditions", {}),
        flags={"repeated_from": event.get("id")},
        created_by="system",
    )


def _event_by_id(state: dict[str, Any], event_id: str) -> dict[str, Any]:
    normalize_scheduled_events(state)
    for event in state["scheduled_events"]["entries"]:
        if event["id"] == event_id:
            return event
    raise HTTPException(404, "未找到长期事件")


def _record_event_history_if_needed(state: dict[str, Any], event: dict[str, Any], title_prefix: str, actor: str) -> None:
    if int(event.get("importance", 0)) < 3 and not event.get("on_resolve", {}).get("record_history"):
        return
    entry = append_history_entry(
        state,
        title=f"{title_prefix}：{event.get('title', event.get('type'))}",
        summary_md=event.get("result_md") or event.get("description_md") or event.get("title", ""),
        source="scheduled_event",
        importance=int(event.get("importance", 3)),
        tags=[str(event.get("type", "event")), "scheduled_event"],
        related={
            **_clean_related(event.get("related")),
            "scheduled_events": [event.get("id")],
        },
        created_by=actor,
    )
    event.setdefault("related", {}).setdefault("history_entries", []).append(entry["id"])
    state["last_history_entries_created"] = [entry]
