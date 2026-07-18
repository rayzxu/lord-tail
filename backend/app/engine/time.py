from __future__ import annotations

from typing import Any

from .types import TurnContext, TurnEvent

TURN_DAYS = 9
HOURS_PER_DAY = 24
MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = HOURS_PER_DAY * MINUTES_PER_HOUR
DEFAULT_TIME_OF_DAY = "morning"
TIME_OF_DAY_BY_HOUR = [
    (5, "night"),
    (11, "morning"),
    (14, "noon"),
    (18, "afternoon"),
    (22, "evening"),
    (24, "night"),
]
SEASONS = ["春季", "夏季", "秋季", "冬季"]


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def season_for_day(calendar_day: int) -> str:
    index = ((max(1, calendar_day) - 1) // 90) % len(SEASONS)
    return SEASONS[index]


def time_of_day_for_hour(hour: int) -> str:
    normalized = hour % HOURS_PER_DAY
    for maximum, label in TIME_OF_DAY_BY_HOUR:
        if normalized < maximum:
            return label
    return DEFAULT_TIME_OF_DAY


def format_clock_24(hour: int, minute: int = 0) -> str:
    return f"{hour % HOURS_PER_DAY:02d}:{minute % MINUTES_PER_HOUR:02d}"


def _normalize_clock(hour: Any, minute: Any = 0) -> tuple[int, int, int]:
    total_minutes = max(0, _int(hour, 6)) * MINUTES_PER_HOUR + max(0, _int(minute, 0))
    days_from_clock, minutes_in_day = divmod(total_minutes, MINUTES_PER_DAY)
    normalized_hour, normalized_minute = divmod(minutes_in_day, MINUTES_PER_HOUR)
    return days_from_clock, normalized_hour, normalized_minute


def apply_clock_fields(time_state: dict[str, Any], hour: int, minute: int = 0) -> None:
    hour = hour % HOURS_PER_DAY
    minute = minute % MINUTES_PER_HOUR
    clock = format_clock_24(hour, minute)
    time_state["hour"] = hour
    time_state["hour_24"] = hour
    time_state["minute"] = minute
    time_state["clock"] = clock
    time_state["clock_24"] = clock
    time_state["time_of_day"] = time_of_day_for_hour(hour)


def normalize_time(state: dict[str, Any]) -> None:
    time_state = state.setdefault("time", {})
    calendar_day = max(1, _int(time_state.get("calendar_day", 1), 1))
    turn_days = max(1, _int(time_state.get("turn_days", TURN_DAYS), TURN_DAYS))
    raw_hour = time_state.get("hour", time_state.get("hour_24", 6))
    raw_minute = time_state.get("minute", 0)
    days_from_clock, hour, minute = _normalize_clock(raw_hour, raw_minute)
    calendar_day += days_from_clock
    time_state["calendar_day"] = calendar_day
    time_state["turn_days"] = turn_days
    time_state["day_in_turn"] = ((calendar_day - 1) % turn_days) + 1
    apply_clock_fields(time_state, hour, minute)
    time_state["season"] = str(time_state.get("season") or state.get("season") or season_for_day(calendar_day))
    time_state["weather"] = str(time_state.get("weather") or state.get("weather") or "细雨")
    state.setdefault("game_mode", "strategic")
    state.setdefault("active_scene", None)
    state.setdefault("scene_seq", 0)
    sync_legacy_time_fields(state)


def sync_legacy_time_fields(state: dict[str, Any]) -> None:
    time_state = state.setdefault("time", {})
    calendar_day = max(1, _int(time_state.get("calendar_day", 1), 1))
    time_state["season"] = season_for_day(calendar_day)
    state["season"] = time_state.get("season", state.get("season", "春季"))
    state["weather"] = time_state.get("weather", state.get("weather", "细雨"))


def advance_calendar(state: dict[str, Any], *, days: int = 0, hours: int = 0, minutes: int = 0) -> int:
    normalize_time(state)
    time_state = state["time"]
    total_minutes = (
        _int(time_state.get("hour", 6), 6) * MINUTES_PER_HOUR
        + _int(time_state.get("minute", 0), 0)
        + max(0, hours) * MINUTES_PER_HOUR
        + max(0, minutes)
    )
    days_from_minutes, minutes_in_day = divmod(total_minutes, MINUTES_PER_DAY)
    hour, minute = divmod(minutes_in_day, MINUTES_PER_HOUR)
    total_days = max(0, days) + days_from_minutes
    time_state["calendar_day"] = max(1, _int(time_state.get("calendar_day", 1), 1) + total_days)
    apply_clock_fields(time_state, hour, minute)
    time_state["day_in_turn"] = ((time_state["calendar_day"] - 1) % time_state["turn_days"]) + 1
    sync_legacy_time_fields(state)
    return total_days


def advance_strategic_clock(state: dict[str, Any], context: TurnContext, *, days: int | None = None) -> None:
    normalize_time(state)
    advance_days = state["time"]["turn_days"] if days is None else max(0, days)
    if advance_days:
        advance_calendar(state, days=advance_days)
    state["turn"] = _int(state.get("turn", 1), 1) + 1
    context.events.append(TurnEvent(
        phase="end_turn",
        kind="advanced",
        message=f"第 {state['turn'] - 1} 轮的裁决已经落定，领地时间推进 {advance_days} 天。",
        data={
            "turn": state["turn"],
            "calendar_day": state["time"]["calendar_day"],
            "clock_24": state["time"]["clock_24"],
            "advanced_days": advance_days,
            "turn_days": state["time"]["turn_days"],
        },
    ))


def due_strategic_turns(state: dict[str, Any]) -> int:
    normalize_time(state)
    turn_days = max(1, _int(state["time"].get("turn_days", TURN_DAYS), TURN_DAYS))
    expected_turn = ((max(1, _int(state["time"].get("calendar_day", 1), 1)) - 1) // turn_days) + 1
    return max(0, expected_turn - max(1, _int(state.get("turn", 1), 1)))


def advance_scene_time(state: dict[str, Any], *, hours: int = 0, days: int = 0, minutes: int = 0, reason: str = "") -> list[TurnEvent]:
    normalize_time(state)
    advanced_days = advance_calendar(state, days=days, hours=hours, minutes=minutes)
    scene = state.get("active_scene")
    if isinstance(scene, dict):
        elapsed_minutes = (
            max(0, _int(scene.get("elapsed_hours", 0), 0)) * MINUTES_PER_HOUR
            + max(0, _int(scene.get("elapsed_minutes", 0), 0))
            + max(0, hours) * MINUTES_PER_HOUR
            + max(0, minutes)
        )
        extra_days, scene_minutes = divmod(elapsed_minutes, MINUTES_PER_DAY)
        scene_hours, scene_minutes = divmod(scene_minutes, MINUTES_PER_HOUR)
        scene["elapsed_hours"] = scene_hours
        scene["elapsed_minutes"] = scene_minutes
        scene["elapsed_days"] = max(0, _int(scene.get("elapsed_days", 0), 0) + max(0, days) + extra_days)
    return [TurnEvent(
        phase="scene_time",
        kind="advanced",
        message=reason or f"场景时间推进 {advanced_days} 天 {max(0, hours) % HOURS_PER_DAY} 小时 {max(0, minutes) % MINUTES_PER_HOUR} 分钟。",
        data={
            "days": days,
            "hours": hours,
            "minutes": minutes,
            "advanced_calendar_days": advanced_days,
            "calendar_day": state["time"]["calendar_day"],
            "day_in_turn": state["time"]["day_in_turn"],
            "hour_24": state["time"]["hour_24"],
            "minute": state["time"]["minute"],
            "clock_24": state["time"]["clock_24"],
            "time_of_day": state["time"]["time_of_day"],
            "due_strategic_turns": due_strategic_turns(state),
        },
    )]


def current_time_summary(state: dict[str, Any]) -> dict[str, Any]:
    normalize_time(state)
    return {
        "turn": state.get("turn", 1),
        "time": state.get("time", {}),
        "game_mode": state.get("game_mode", "strategic"),
        "active_scene": state.get("active_scene"),
    }
