from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..ai.actions import execute_action, parse_command_action
from ..ai.planner import plan_management_action
from ..systems import construction, council, demographics, diplomacy, economy, events, military, scheduled_events, weather
from .history import auto_record_turn_events
from .narrative import events_to_report, serialize_events, suggest_next_actions
from . import scenes
from .time import advance_strategic_clock, current_time_key, set_time_point, time_key
from .types import TurnContext, TurnEvent

DEFAULT_SUGGESTIONS = ["在 E4 建造农田", "在 B2 建造伐木场", "在 F4 建造训练场"]


def run_start_turn(state: dict[str, Any], context: TurnContext) -> None:
    state["changes"] = {key: 0 for key in state["resources"]}
    workforce = state.setdefault("workforce", {"available": 0, "assigned": 0})
    workforce["available"] = state["resources"].get("population", 0)
    military.normalize_army_status(state)
    diplomacy.normalize_diplomacy_state(state)
    demographics.normalize_demographics(state)
    context.events.append(TurnEvent(phase="start_turn", kind="prepared", message=f"第 {state['turn']} 轮的结算开始。"))
    context.events.extend(scheduled_events.activate_due_events(state, source="start_turn"))


def run_income(state: dict[str, Any], context: TurnContext) -> None:
    economy.produce_resources(state, context)


def run_player_action(state: dict[str, Any], context: TurnContext) -> None:
    council.normalize_council_state(state)
    manual_action = parse_command_action(state, context.command, actor=context.actor)
    directive = state.get("strategic_directive")
    management = state["management_ai"]
    occupied_slot = management.get("action_slot")
    if isinstance(occupied_slot, dict) and int(occupied_slot.get("turn", -1)) == int(state.get("turn", 1)):
        if manual_action is not None:
            raise ValueError(
                f"第 {state.get('turn', 1)} 轮的战略行动已经由 "
                f"{occupied_slot.get('actor', '未知来源')} 使用"
            )
        context.events.append(TurnEvent(
            phase="management_action",
            kind="action_slot_already_used",
            message="本轮战略行动已由公开行动接口执行，管家不会获得第二次行动。",
            data={"action_slot": occupied_slot},
        ))
        return
    if manual_action is not None:
        execute_action(state, manual_action, context, directive=directive, enforce_budget=False)
        context.events.append(TurnEvent(
            phase="management_action",
            kind="manual_action_override",
            message="领主的明确命令覆盖了本轮管理 AI 行动；长期方针保持不变。",
            data={"action": manual_action, "directive_id": directive.get("id") if isinstance(directive, dict) else None},
        ))
        management["accepted_action"] = None
        return
    if not management.get("enabled", True) or not isinstance(directive, dict) or directive.get("status") != "active":
        context.events.append(TurnEvent(phase="player_action", kind="noop", message="本轮没有可执行的结构化战略行动。"))
        return
    mode = management.get("mode", "delegated")
    if mode == "manual":
        context.events.append(TurnEvent(phase="player_action", kind="manual_mode_noop", message="领地处于手动管理模式，本轮未下达战略行动。"))
        return
    if mode == "advisory":
        action = management.pop("accepted_action", None)
        if not isinstance(action, dict):
            context.events.append(TurnEvent(phase="management_action", kind="management_advice_missing", severity="warning", message="顾问方案尚未由领主确认。"))
            return
        decision = management.get("pending_advice")
    else:
        decision = plan_management_action(
            state,
            directive,
            mode=mode,
            seed=int(management.get("planner_seed", 0)) + int(state.get("turn", 1)),
        )
        action = decision["selected_action"]
    execute_action(state, action, context, directive=directive, enforce_budget=True)
    management["last_decision"] = decision
    management["pending_advice"] = None
    if action.get("type") == "wait":
        management["consecutive_no_action_turns"] += 1
    else:
        management["consecutive_no_action_turns"] = 0
    context.events.append(TurnEvent(
        phase="management_action",
        kind="management_ai_decision",
        message=f"领地管家依照「{directive['title']}」执行：{decision.get('selected_label', action.get('action_id'))}",
        data={"decision": decision, "action": action},
    ))


def run_construction(state: dict[str, Any], context: TurnContext) -> None:
    construction.advance_projects(state, context)


def run_weather(state: dict[str, Any], context: TurnContext) -> None:
    weather.advance_weather(state, context)


def run_military(state: dict[str, Any], context: TurnContext) -> None:
    military.advance_training(state, context)
    military.apply_upkeep(state, context)


def run_diplomacy(state: dict[str, Any], context: TurnContext) -> None:
    diplomacy.run_diplomacy_phase(state, context)


def run_demographics(state: dict[str, Any], context: TurnContext) -> None:
    demographics.run_demographics_phase(state, context)


def run_expenditure(state: dict[str, Any], context: TurnContext) -> None:
    economy.consume_population_food(state, context)
    economy.apply_building_maintenance(state, context)


def run_events(state: dict[str, Any], context: TurnContext) -> None:
    events.run_random_events(state, context)
    events.check_threshold_events(state, context)


def run_end_turn(state: dict[str, Any], context: TurnContext) -> None:
    advance_strategic_clock(state, context, days=context.advance_calendar_days)
    context.events.extend(scheduled_events.activate_due_events(state, source="end_turn"))


def _scheduled_event_turn_events(context: TurnContext) -> list[TurnEvent]:
    return [
        event
        for event in context.events
        if event.phase == "scheduled_events"
        and isinstance(event.data, dict)
        and isinstance(event.data.get("event"), dict)
        and event.data["event"].get("status") == "active"
    ]


def _start_scene_for_event_if_needed(state: dict[str, Any], event: dict[str, Any]) -> TurnEvent | None:
    if state.get("active_scene") is not None:
        return None
    on_due = event.get("on_due", {}) if isinstance(event.get("on_due"), dict) else {}
    scene_type = str(on_due.get("scene_type") or "daily")
    title = str(event.get("title") or event.get("type") or "到期事件")
    event_flags = event.get("flags", {}) if isinstance(event.get("flags"), dict) else {}
    if event_flags.get("story_arc_definition_id"):
        return None
    participants = event_flags.get("participants") if isinstance(event_flags.get("participants"), list) else []
    scene_flags = {
        "source": "storylet" if event.get("type") == "storylet_event" else "scheduled_event",
        "scheduled_event_id": event.get("id"),
        "scheduled_event_type": event.get("type"),
    }
    if event.get("type") == "storylet_event":
        scene_flags.update({
            "story_event_id": event_flags.get("story_event_id"),
            "story_chain_id": event_flags.get("story_chain_id"),
            "facts_frozen": True,
            "blocking": bool(event_flags.get("blocking", True)),
        })
    scene = scenes.start_scene(
        state,
        scene_type,
        title,
        participants=participants,
        flags=scene_flags,
    )
    if event.get("type") == "storylet_event" and event_flags.get("story_event_id"):
        from ..storylets.instances import instance_by_id

        instance_by_id(state, str(event_flags["story_event_id"]))["scene_id"] = scene["id"]
    return TurnEvent(
        phase="scene",
        kind="scene_started_for_scheduled_event",
        severity="warning" if int(event.get("importance", 0) or 0) >= 4 else "info",
        message=f"推进被事件打断，场景开始：{scene['title']}",
        data={"scene": scene, "event": event},
    )


def _open_scenes_for_activated_events(state: dict[str, Any], context: TurnContext) -> None:
    for turn_event in _scheduled_event_turn_events(context):
        scene_event = _start_scene_for_event_if_needed(state, turn_event.data["event"])
        if scene_event is not None:
            context.events.append(scene_event)
            break


def _interrupting_event_within_turn(state: dict[str, Any], days: int) -> dict[str, Any] | None:
    upcoming = scheduled_events.upcoming_events(state, days=max(0, days), min_importance=1, limit=1)
    return upcoming[0] if upcoming else None


def _advance_to_scheduled_event(state: dict[str, Any], event: dict[str, Any], context: TurnContext) -> None:
    due_time = event["schedule"]["due_time"]
    current_key = current_time_key(state)
    due_key = time_key(due_time)
    set_time_point(state, due_time)
    weather.advance_weather(state, context)
    interrupted_minutes = max(0, due_key - current_key)
    context.events.append(TurnEvent(
        phase="scheduled_events",
        kind="strategic_advance_interrupted",
        severity="warning",
        message=f"九天推进在第 {state['time']['calendar_day']} 日 {state['time']['clock_24']} 被「{event['title']}」打断。",
        data={
            "event_id": event.get("id"),
            "event_type": event.get("type"),
            "title": event.get("title"),
            "interrupted_minutes": interrupted_minutes,
            "calendar_day": state["time"]["calendar_day"],
            "clock_24": state["time"]["clock_24"],
        },
    ))
    context.events.extend(scheduled_events.activate_due_events(state, source="strategic_turn_interrupt"))
    _open_scenes_for_activated_events(state, context)


def try_interrupt_for_scheduled_events(state: dict[str, Any], context: TurnContext) -> bool:
    run_start_turn(state, context)
    if _scheduled_event_turn_events(context):
        _open_scenes_for_activated_events(state, context)
        context.events.append(TurnEvent(
            phase="scheduled_events",
            kind="strategic_advance_blocked_by_due_event",
            severity="warning",
            message="已有到期事件等待处理，九天推进没有继续执行。",
            data={"time": state.get("time", {})},
        ))
        return True
    if council.current_meeting(state):
        context.events.append(TurnEvent(
            phase="council",
            kind="strategic_advance_blocked_by_council",
            severity="warning",
            message="领主议会尚未裁定战略方针，九天推进没有继续执行。",
            data={"meeting": council.current_meeting(state)},
        ))
        return True
    directive = state.get("strategic_directive")
    management = state.get("management_ai", {})
    if (
        isinstance(directive, dict)
        and directive.get("status") == "active"
        and management.get("enabled", True)
        and management.get("mode") == "advisory"
        and parse_command_action(state, context.command, actor=context.actor) is None
        and not isinstance(management.get("accepted_action"), dict)
    ):
        decision = plan_management_action(
            state,
            directive,
            mode="advisory",
            seed=int(management.get("planner_seed", 0)) + int(state.get("turn", 1)),
        )
        management["pending_advice"] = decision
        context.events.append(TurnEvent(
            phase="management_action",
            kind="management_advice_required",
            severity="warning",
            message="顾问已经列出候选方案，等待领主确认后再推进九天。",
            data={"decision": decision},
        ))
        return True
    interrupting = _interrupting_event_within_turn(state, context.advance_calendar_days)
    if interrupting is None:
        return False
    _advance_to_scheduled_event(state, interrupting, context)
    return True


# 结算顺序：收入 -> 执行动作 -> 建筑 -> 军事 -> 外交 -> 人口/阶级经济 -> 天气 -> 支出 -> 事件。
TURN_PHASES = [
    run_income,
    run_player_action,
    run_construction,
    run_military,
    run_diplomacy,
    run_demographics,
    run_weather,
    run_expenditure,
    run_events,
    run_end_turn,
]


def build_narrative(context: TurnContext) -> str:
    return events_to_report(context.events)


def run_strategic_turn(
    state: dict[str, Any],
    command: str,
    *,
    actor: str = "player",
    advance_calendar_days: int = 9,
) -> tuple[str, list[str], list[dict[str, Any]]]:
    working = deepcopy(state)
    context = TurnContext(command=command, actor=actor, advance_calendar_days=advance_calendar_days)
    interrupted = try_interrupt_for_scheduled_events(working, context)
    if not interrupted:
        for phase in TURN_PHASES:
            phase(working, context)
        context.events.extend(council.update_directive_after_turn(working))
        context.events.extend(council.schedule_emergency_if_needed(working))
        from ..storylets.director import run_director
        from ..storylets.service import process_construction_followups

        followups = process_construction_followups(working, context.events)
        for followup in followups:
            context.events.append(TurnEvent(
                phase="storylet", kind="storylet_followup_scheduled",
                message=f"人物事件后续已进入日程：{followup['title']}",
                data={"story_event_id": followup["id"], "chain_id": followup["chain_id"]},
            ))
        decision = run_director(working, source_kind="realm", commit=True)
        if decision.get("instance"):
            instance = decision["instance"]
            context.events.append(TurnEvent(
                phase="storylet", kind="storylet_directed",
                message=f"领地现实酝酿出新的剧情事件：{instance['title']}",
                data={"story_event_id": instance["id"], "chain_id": instance["chain_id"]},
            ))
    auto_record_turn_events(working, context.events)
    narrative = build_narrative(context)
    context.suggestions = suggest_next_actions(working, context.events) or list(DEFAULT_SUGGESTIONS)
    state.clear()
    state.update(working)
    return narrative, context.suggestions, serialize_events(context.events)


def local_turn(state: dict[str, Any], command: str) -> tuple[str, list[str], list[dict[str, Any]]]:
    return run_strategic_turn(state, command)
