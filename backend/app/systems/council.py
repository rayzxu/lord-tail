from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException

from ..ai.analysis import analyze_realm
from ..ai.config import load_council_policies
from ..ai.proposals import directive_from_proposal, generate_proposals
from ..engine.history import append_history_entry
from ..engine.time import add_to_time_point, current_time_key, time_key, time_point_from_state
from ..engine.types import TurnEvent

COUNCIL_EVENT_TYPE = "council_session"
MEETING_STATUSES = {"open", "resolved", "cancelled"}
DIRECTIVE_STATUSES = {"active", "completed", "expired", "suspended", "replaced"}
MANAGEMENT_MODES = {"delegated", "advisory", "manual"}
LOWER_IS_BETTER_TARGETS = {"hostile_neighbors", "at_war_count", "war_risk"}


def normalize_council_state(state: dict[str, Any]) -> None:
    council = state.setdefault("council", {})
    if not isinstance(council, dict):
        council = {}
        state["council"] = council
    council.setdefault("current_meeting", None)
    council.setdefault("history", [])
    council["next_id"] = max(1, int(council.get("next_id", 1) or 1))
    council["next_directive_id"] = max(1, int(council.get("next_directive_id", 1) or 1))
    council.setdefault("last_regular_time", None)
    council.setdefault("last_requested_review_time", None)
    council.setdefault("emergency_cooldowns", {})
    meeting = council.get("current_meeting")
    if isinstance(meeting, dict):
        meeting.setdefault("status", "open")
        if meeting["status"] not in MEETING_STATUSES:
            meeting["status"] = "open"
        meeting.setdefault("proposals", [])
        meeting.setdefault("crisis_summary", [])
    directive = state.get("strategic_directive")
    if isinstance(directive, dict):
        directive.setdefault("status", "active")
        if directive["status"] not in DIRECTIVE_STATUSES:
            directive["status"] = "active"
        directive.setdefault("executed_strategic_turns", 0)
        directive.setdefault("progress", {})
        directive.setdefault("completed_targets", [])
        directive.setdefault("suspension_reason", None)
    else:
        state["strategic_directive"] = None
    management = state.setdefault("management_ai", {})
    if not isinstance(management, dict):
        management = {}
        state["management_ai"] = management
    management.setdefault("enabled", True)
    mode = str(management.get("mode") or "delegated")
    management["mode"] = mode if mode in MANAGEMENT_MODES else "delegated"
    management.setdefault("last_decision", None)
    management.setdefault("pending_advice", None)
    management["planner_seed"] = int(management.get("planner_seed", 0) or 0)
    management["consecutive_no_action_turns"] = max(0, int(management.get("consecutive_no_action_turns", 0) or 0))
    management.setdefault("action_slot", None)
    management.setdefault("accepted_action", None)


def _event_with_trigger(state: dict[str, Any], trigger_key: str) -> dict[str, Any] | None:
    for event in state.get("scheduled_events", {}).get("entries", []):
        if (
            event.get("type") == COUNCIL_EVENT_TYPE
            and event.get("flags", {}).get("trigger_key") == trigger_key
            and event.get("status") in {"scheduled", "due", "active"}
        ):
            return event
    return None


def schedule_council(
    state: dict[str, Any],
    *,
    reason: str,
    trigger_key: str,
    due_time: dict[str, Any] | None = None,
    in_days: int | None = None,
    title: str = "领主议会",
) -> dict[str, Any]:
    normalize_council_state(state)
    existing = _event_with_trigger(state, trigger_key)
    if existing:
        return existing
    from .scheduled_events import schedule_event

    return schedule_event(
        state,
        event_type=COUNCIL_EVENT_TYPE,
        title=title,
        description_md="财政官、军事统帅与外交官已经备好账册和陈奏，等待领主选择未来数月的方针。",
        due_time=due_time,
        in_days=in_days,
        clock_24=load_council_policies()["meeting"]["regular_clock_24"],
        importance=5,
        flags={"trigger_key": trigger_key, "reason": reason, "blocking": True},
        created_by="council",
    )


def ensure_initial_council(state: dict[str, Any]) -> dict[str, Any] | None:
    normalize_council_state(state)
    council = state["council"]
    if council.get("history") or state.get("strategic_directive") or council.get("current_meeting"):
        return None
    return schedule_council(
        state,
        reason="initial",
        trigger_key="initial-council",
        due_time={"calendar_day": 1, "clock_24": "09:00"},
        title="首次领主议会",
    )


def _next_meeting_id(state: dict[str, Any]) -> str:
    normalize_council_state(state)
    value = int(state["council"]["next_id"])
    state["council"]["next_id"] = value + 1
    return f"council_{value:06d}"


def _next_directive_id(state: dict[str, Any]) -> str:
    normalize_council_state(state)
    value = int(state["council"]["next_directive_id"])
    state["council"]["next_directive_id"] = value + 1
    return f"directive_{value:06d}"


def crisis_summary(analysis: dict[str, Any]) -> list[str]:
    config = load_council_policies()["meeting"]["emergency"]
    metrics = analysis["metrics"]
    rows: list[str] = []
    food_runway = metrics.get("food_runway_days")
    gold_runway = metrics.get("gold_runway_days")
    if food_runway is not None and food_runway < config["food_runway_days_below"]:
        rows.append(f"粮食预计只能维持 {food_runway:g} 天。")
    if gold_runway is not None and gold_runway < config["gold_runway_days_below"] and metrics.get("gold_net_turn", 0) < 0:
        rows.append(f"金库预计只能维持 {gold_runway:g} 天，且净收入为负。")
    if metrics.get("at_war_count", 0) > 0 and metrics.get("military_readiness", 999) < config["military_readiness_below"]:
        rows.append(f"领地处于战争，战备值只有 {metrics.get('military_readiness', 0):g}。")
    if metrics.get("external_threat", 0) > metrics.get("defensive_power", 0) * config["threat_defense_ratio_above"]:
        rows.append("最强外部威胁已经显著超过领地防御能力。")
    return rows


def open_meeting_from_event(state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    normalize_council_state(state)
    current = state["council"].get("current_meeting")
    if isinstance(current, dict) and current.get("status") == "open":
        return current
    analysis = analyze_realm(state)
    meeting = {
        "id": _next_meeting_id(state),
        "event_id": event.get("id"),
        "status": "open",
        "reason": str(event.get("flags", {}).get("reason") or "regular"),
        "trigger_key": str(event.get("flags", {}).get("trigger_key") or event.get("id")),
        "opened_time": time_point_from_state(state),
        "analysis_snapshot": analysis,
        "crisis_summary": crisis_summary(analysis),
        "proposals": generate_proposals(analysis),
        "resolved_proposal_id": None,
        "resolved_time": None,
        "management_mode": None,
    }
    state["council"]["current_meeting"] = meeting
    return meeting


def current_meeting(state: dict[str, Any]) -> dict[str, Any] | None:
    normalize_council_state(state)
    meeting = state["council"].get("current_meeting")
    return meeting if isinstance(meeting, dict) and meeting.get("status") == "open" else None


def resolve_meeting(state: dict[str, Any], meeting_id: str, proposal_id: str, management_mode: str) -> dict[str, Any]:
    normalize_council_state(state)
    meeting = state["council"].get("current_meeting")
    if not isinstance(meeting, dict) or meeting.get("id") != meeting_id:
        previous = next((item for item in state["council"]["history"] if item.get("id") == meeting_id), None)
        if previous and previous.get("resolved_proposal_id") == proposal_id and previous.get("management_mode") == management_mode:
            return {"meeting": previous, "directive": state.get("strategic_directive"), "idempotent": True}
        if previous:
            raise HTTPException(409, "该议会已经以不同选择解决")
        raise HTTPException(404, "未找到当前议会")
    if meeting.get("status") != "open":
        raise HTTPException(409, "议会已经结束")
    if management_mode not in MANAGEMENT_MODES:
        raise HTTPException(422, "未知领地管理模式")
    proposal = next((item for item in meeting.get("proposals", []) if item.get("id") == proposal_id), None)
    if proposal is None:
        raise HTTPException(422, "所选提案不属于当前议会")

    previous_directive = state.get("strategic_directive")
    if isinstance(previous_directive, dict) and previous_directive.get("status") == "active":
        previous_directive["status"] = "replaced"
        previous_directive["suspension_reason"] = f"由议会 {meeting_id} 替换"
    policy = load_council_policies()["meeting"]
    started = time_point_from_state(state)
    expires = add_to_time_point(started, days=int(policy["directive_duration_days"]))
    directive = directive_from_proposal(
        proposal,
        directive_id=_next_directive_id(state),
        meeting_id=meeting_id,
        started_time=started,
        expires_time=expires,
        duration_turns=int(policy["directive_duration_strategic_turns"]),
    )
    state["strategic_directive"] = directive
    state["management_ai"]["mode"] = management_mode
    state["management_ai"]["pending_advice"] = None
    state["management_ai"]["accepted_action"] = None
    state["management_ai"]["consecutive_no_action_turns"] = 0
    meeting["status"] = "resolved"
    meeting["resolved_proposal_id"] = proposal_id
    meeting["resolved_time"] = started
    meeting["management_mode"] = management_mode
    state["council"]["history"].append(deepcopy(meeting))
    state["council"]["current_meeting"] = None
    state["council"]["last_regular_time"] = started

    from . import scheduled_events

    event_id = meeting.get("event_id")
    if event_id:
        try:
            scheduled_events.resolve_event(
                state,
                str(event_id),
                result_md=f"领主采纳「{proposal['title']}」，并选择{management_mode}管理模式。",
                outcome={"proposal_id": proposal_id, "directive_id": directive["id"]},
                resolved_by="player",
            )
        except HTTPException:
            pass
    schedule_council(
        state,
        reason="regular",
        trigger_key=f"regular:{directive['id']}",
        due_time=expires,
        title="战略方针复议",
    )
    active_scene = state.get("active_scene")
    if isinstance(active_scene, dict) and active_scene.get("type") == "council":
        from ..engine import scenes

        scenes.end_scene(state, summary=f"议会结束，领主采纳「{proposal['title']}」。")
    entry = append_history_entry(
        state,
        title=f"领主议会：{proposal['title']}",
        summary_md=f"领主选择了**{proposal['title']}**，管理模式为 `{management_mode}`。方针持续至第 {expires['calendar_day']} 日。",
        details_md=proposal.get("speech_md", ""),
        source="council",
        importance=4,
        tags=["council", "strategy", proposal["domain"]],
        related={"scheduled_events": [event_id] if event_id else []},
        created_by="backend",
    )
    state["last_history_entries_created"] = [entry]
    return {"meeting": meeting, "directive": directive, "idempotent": False}


def request_review(state: dict[str, Any]) -> dict[str, Any]:
    normalize_council_state(state)
    if current_meeting(state):
        raise HTTPException(409, "已经有一场开放的议会")
    policy = load_council_policies()["meeting"]
    last = state["council"].get("last_requested_review_time")
    if isinstance(last, dict):
        cooldown_minutes = int(policy["requested_review_cooldown_days"]) * 24 * 60
        if current_time_key(state) - time_key(last) < cooldown_minutes:
            raise HTTPException(409, "主动复议仍在冷却期")
    state["council"]["last_requested_review_time"] = time_point_from_state(state)
    event = schedule_council(
        state,
        reason="requested",
        trigger_key=f"requested:{current_time_key(state)}",
        due_time=time_point_from_state(state),
        title="领主主动复议",
    )
    from .scheduled_events import activate_due_events

    events = activate_due_events(state, source="council_request")
    meeting = current_meeting(state)
    if meeting and state.get("active_scene") is None:
        from ..engine import scenes

        scenes.start_scene(
            state,
            "council",
            event.get("title", "领主议会"),
            flags={"source": "council_request", "scheduled_event_id": event.get("id"), "meeting_id": meeting["id"]},
        )
    return {"event": event, "meeting": meeting, "events": [item.model_dump() for item in events]}


def _target_completed(key: str, target: Any, actual: Any) -> bool:
    if actual is None:
        return False
    try:
        return float(actual) <= float(target) if key in LOWER_IS_BETTER_TARGETS else float(actual) >= float(target)
    except (TypeError, ValueError):
        return actual == target


def update_directive_after_turn(state: dict[str, Any]) -> list[TurnEvent]:
    normalize_council_state(state)
    directive = state.get("strategic_directive")
    if not isinstance(directive, dict) or directive.get("status") != "active":
        return []
    directive["executed_strategic_turns"] = int(directive.get("executed_strategic_turns", 0)) + 1
    metrics = analyze_realm(state)["metrics"]
    progress = {}
    completed = []
    for key, target in directive.get("targets", {}).items():
        actual = metrics.get(key)
        done = _target_completed(key, target, actual)
        progress[key] = {"target": target, "actual": actual, "completed": done}
        if done:
            completed.append(key)
    directive["progress"] = progress
    directive["completed_targets"] = completed
    expired = current_time_key(state) >= time_key(directive["expires_time"])
    all_completed = bool(progress) and len(completed) == len(progress)
    events: list[TurnEvent] = []
    if all_completed or expired:
        directive["status"] = "completed" if all_completed else "expired"
        kind = "directive_completed" if all_completed else "directive_expired"
        message = f"战略方针「{directive['title']}」{'已经完成' if all_completed else '已经到期'}。"
        events.append(TurnEvent(phase="council", kind=kind, message=message, data={"directive": deepcopy(directive)}))
        schedule_council(
            state,
            reason="completed" if all_completed else "expired",
            trigger_key=f"{kind}:{directive['id']}",
            due_time=time_point_from_state(state),
            title="战略方针复议",
        )
    return events


def emergency_trigger(state: dict[str, Any]) -> tuple[str, list[str]] | None:
    normalize_council_state(state)
    analysis = analyze_realm(state)
    reasons = crisis_summary(analysis)
    threshold = int(load_council_policies()["meeting"]["emergency"]["no_action_turns"])
    if state["management_ai"]["consecutive_no_action_turns"] >= threshold:
        reasons.append("当前方针连续多个战略回合只能等待，已经无法形成合法行动。")
    if not reasons:
        return None
    metrics = analysis["metrics"]
    emergency = load_council_policies()["meeting"]["emergency"]
    if metrics.get("food_runway_days") is not None and metrics["food_runway_days"] < emergency["food_runway_days_below"]:
        key = "food_crisis"
    elif metrics.get("at_war_count", 0):
        key = "war_readiness"
    elif state["management_ai"]["consecutive_no_action_turns"] >= threshold:
        key = "directive_stalled"
    else:
        key = "realm_crisis"
    return key, reasons


def schedule_emergency_if_needed(state: dict[str, Any]) -> list[TurnEvent]:
    found = emergency_trigger(state)
    if found is None or current_meeting(state):
        return []
    key, reasons = found
    cooldowns = state["council"]["emergency_cooldowns"]
    policy = load_council_policies()["meeting"]
    previous = cooldowns.get(key)
    if isinstance(previous, dict) and current_time_key(state) - time_key(previous) < int(policy["emergency_cooldown_days"]) * 24 * 60:
        return []
    cooldowns[key] = time_point_from_state(state)
    event = schedule_council(
        state,
        reason="emergency",
        trigger_key=f"emergency:{key}:{state.get('turn', 1)}",
        due_time=time_point_from_state(state),
        title="紧急领主议会",
    )
    return [TurnEvent(
        phase="council",
        kind="emergency_council_scheduled",
        severity="warning",
        message="领地危机迫使大臣请求紧急议事。",
        data={"event": event, "trigger_key": key, "reasons": reasons},
    )]


def set_management_mode(state: dict[str, Any], mode: str) -> dict[str, Any]:
    normalize_council_state(state)
    if mode not in MANAGEMENT_MODES:
        raise HTTPException(422, "未知领地管理模式")
    state["management_ai"]["mode"] = mode
    if mode != "advisory":
        state["management_ai"]["pending_advice"] = None
    return state["management_ai"]
