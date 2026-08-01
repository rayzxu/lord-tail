from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import logging
from typing import Any

from fastapi import HTTPException

from ..engine import scenes
from ..engine.time import time_key, time_point_from_state
from ..systems import scheduled_events
from .effects import execute_effects
from .graph import condition_matches
from .runs import (
    canonical_definition, definition_for_run, definition_hash, execution_context,
    find_visit, next_run_id, next_visit_id, public_visit, run_by_id, visit_by_id,
)

MAX_AUTOMATIC_STEPS = 16
logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _event_by_id(state: dict[str, Any], event_id: str) -> dict[str, Any]:
    for event in state.get("scheduled_events", {}).get("entries", []):
        if event.get("id") == event_id:
            return event
    raise HTTPException(404, "未找到剧情图关联的计划事件")


def _remove_event(state: dict[str, Any], event_id: str | None) -> None:
    if event_id:
        state["scheduled_events"]["entries"] = [
            event for event in state.get("scheduled_events", {}).get("entries", [])
            if event.get("id") != event_id
        ]


def _node(graph: dict[str, Any], node_id: str) -> dict[str, Any]:
    node = graph.get("nodes", {}).get(node_id)
    if not isinstance(node, dict):
        raise HTTPException(500, f"invalid_authored_graph: 节点不存在 {node_id}")
    return node


class _SafeFormat(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render(run: dict[str, Any], node: dict[str, Any]) -> str:
    values = dict(run.get("facts", {}))
    for role, snapshot in run.get("cast_snapshots", {}).items():
        values[f"{role}_name"] = snapshot.get("name", role)
        values[f"{role}_role"] = snapshot.get("role", "")
    return str(node.get("narrative_template_md", node.get("title", ""))).format_map(_SafeFormat(values))


def _new_visit(state: dict[str, Any], run: dict[str, Any], node_id: str, *, legacy_id: str | None = None) -> dict[str, Any]:
    graph = definition_for_run(run)
    node = _node(graph, node_id)
    visit = {
        "visit_id": next_visit_id(state), "legacy_instance_id": legacy_id,
        "node_id": node_id, "node_kind": node["kind"], "status": "ready",
        "choice_id": None, "scene_id": None, "scheduled_event_id": None,
        "freeform_steps_used": 0, "narrative_md": _render(run, node),
        "effects_result": None, "transition_to": None,
        "transition_seq": int(run.get("transition_seq", 0)),
        "created_time": time_point_from_state(state), "activated_time": None,
        "resolved_time": None, "updated_at": _now(),
    }
    if not visit["legacy_instance_id"]:
        from .runs import next_legacy_instance_id
        visit["legacy_instance_id"] = next_legacy_instance_id(state)
    run.setdefault("node_visits", []).append(visit)
    return visit


def _choice(node: dict[str, Any], choice_id: str) -> dict[str, Any]:
    choice = next((row for row in node.get("choices", []) if row.get("id") == choice_id), None)
    if not isinstance(choice, dict):
        raise HTTPException(422, "invalid_choice: 该选择不属于当前剧情节点")
    return choice


def _automatic_transition(state: dict[str, Any], run: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    transitions = [row for row in node.get("transitions", []) if isinstance(row, dict)]
    if isinstance(node.get("transition"), dict):
        transitions.append(node["transition"])
    matches = [row for row in transitions if row.get("when") and condition_matches(row["when"], state, run)]
    if matches:
        return max(matches, key=lambda row: int(row.get("priority", 0)))
    fallback = [row for row in transitions if not row.get("when")]
    if len(fallback) != 1:
        raise HTTPException(500, "invalid_authored_graph: automatic transition 缺少唯一 fallback")
    return fallback[0]


def _close_arc_scene(state: dict[str, Any], run_id: str, summary: str) -> None:
    scene = state.get("active_scene")
    if not isinstance(scene, dict):
        return
    flags = scene.get("flags", {})
    if (flags.get("story_arc_run_id") or flags.get("story_arc_chain_id")) != run_id:
        raise HTTPException(409, "node_not_current: 当前场景不属于该剧情图")
    scenes.end_scene(state, summary=summary, outcome={"story_arc_run_id": run_id}, allow_story_arc=True)


def _start_scene(state: dict[str, Any], run: dict[str, Any], visit: dict[str, Any], node: dict[str, Any]) -> None:
    if state.get("active_scene") is not None:
        raise HTTPException(409, "当前已有进行中的场景，剧情节点已排队")
    scene = scenes.start_scene(
        state, str(node.get("scene_type") or run.get("scene_type") or "daily"),
        str(node.get("title") or visit["node_id"]),
        participants=[{"role": role, **snapshot} for role, snapshot in run.get("cast_snapshots", {}).items()],
        flags={
            "source": "story_arc", "story_arc_run_id": run["id"],
            "story_arc_chain_id": run["id"], "story_arc_definition_id": run["definition_id"],
            "story_arc_node_id": visit["node_id"], "story_arc_visit_id": visit["visit_id"],
            "story_event_id": visit["legacy_instance_id"],
            "entry_scheduled_event_id": run.get("entry_scheduled_event_id"),
            "blocking": bool(node.get("blocking", True)),
        },
    )
    visit["scene_id"] = scene["id"]
    state["storylets"]["focused_arc_id"] = run["id"]


def _schedule_timed(state: dict[str, Any], run: dict[str, Any], visit: dict[str, Any], node: dict[str, Any]) -> None:
    event = scheduled_events.schedule_event(
        state, event_type="story_arc_node", title=str(node.get("title") or visit["node_id"]),
        description_md=visit["narrative_md"], in_days=int(node.get("after_days", 0) or 0),
        in_hours=int(node.get("after_hours", 0) or 0), visibility="player",
        importance=4 if run.get("priority") == "major" else 2,
        related={"people": list(run.get("cast", {}).values()), "scheduled_events": [run.get("entry_scheduled_event_id")]},
        flags={
            "story_arc_definition_id": run["definition_id"], "story_arc_run_id": run["id"],
            "story_arc_chain_id": run["id"], "story_arc_node_id": visit["node_id"],
            "story_arc_visit_id": visit["visit_id"], "story_event_id": visit["legacy_instance_id"],
            "entry_scheduled_event_id": run.get("entry_scheduled_event_id"),
            "blocking": bool(node.get("blocking", True)),
        }, created_by="story_arc_runtime",
    )
    event["schedule"]["repeat"] = None
    visit["scheduled_event_id"] = event["id"]
    run["pending_node_event_id"] = event["id"]


def _effect_summary(result: dict[str, Any]) -> str:
    changes = result.get("resource_changes", {})
    if not isinstance(changes, dict) or not changes:
        return "剧情状态已更新"
    return "，".join(f"{key} {int(value):+d}" for key, value in changes.items())


def _log_visit(run: dict[str, Any], visit: dict[str, Any], node: dict[str, Any], result: dict[str, Any]) -> None:
    if node.get("presentation", "transition_log") == "silent":
        return
    run.setdefault("transition_log", []).append({
        "visit_id": visit["visit_id"], "node_id": visit["node_id"],
        "kind": node["kind"], "title": node.get("title", visit["node_id"]),
        "narrative_md": visit["narrative_md"], "effects_summary": _effect_summary(result),
        "transition_to": visit.get("transition_to"), "activated_time": deepcopy(visit.get("activated_time")),
    })


def _execute(state: dict[str, Any], run: dict[str, Any], visit: dict[str, Any], node: dict[str, Any], *, actor: str, choice: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    executable = choice or {
        "id": f"{node.get('kind')}:{visit['node_id']}", "label": str(node.get("title") or visit["node_id"]),
        "description_md": visit["narrative_md"], "effects": node.get("effects", []),
    }
    raw_events, result, followups = execute_effects(state, execution_context(run, visit, node), executable, actor=actor)
    if followups:
        raise HTTPException(500, "invalid_authored_graph: schema v2 不允许 schedule_followup")
    return [event.model_dump() for event in raw_events], result


def _next_occurrence_key(route_id: str, due_day: int) -> str:
    year = (max(1, due_day) - 1) // 360 + 1
    season = ("spring", "summer", "autumn", "winter")[((max(1, due_day) - 1) % 360) // 90]
    return f"caravan:{route_id}:year_{year}:{season}"


def _schedule_series(state: dict[str, Any], run: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any] | None:
    series = graph.get("series", {}) if isinstance(graph.get("series"), dict) else {}
    if not series:
        return None
    route_id = str(run.get("facts", {}).get("route_id") or series.get("route_id") or "default")
    outcome_key = str(run.get("facts", {}).get(str(series.get("outcome_fact", "departure_reason")), "normal_trade"))
    rule = series.get("outcomes", {}).get(outcome_key, series.get("default", {}))
    if not isinstance(rule, dict) or rule.get("schedule") is False:
        return None
    in_days = max(1, int(rule.get("in_days", 90)))
    occurrence_key = _next_occurrence_key(route_id, int(state.get("time", {}).get("calendar_day", 1)) + in_days)
    for event in state.get("scheduled_events", {}).get("entries", []):
        if event.get("flags", {}).get("occurrence_key") == occurrence_key and event.get("status") not in {"cancelled", "missed"}:
            return event
    entry = _event_by_id(state, str(run["entry_scheduled_event_id"]))
    event = scheduled_events.schedule_event(
        state, event_type=str(series.get("event_type") or entry.get("type") or "caravan_arrival"),
        title=str(graph.get("title", "商队到访")), description_md=str(graph.get("description_md", "商队将再次来到领地。")),
        in_days=in_days, visibility="player", importance=int(graph.get("importance", 3)),
        flags={
            "story_arc_definition_id": graph["id"], "series_id": series.get("id", route_id),
            "route_id": route_id, "occurrence_key": occurrence_key,
            "inherited_arc_facts": deepcopy(rule.get("inherit_facts", {})),
        }, created_by="story_arc_runtime",
    )
    event["schedule"]["repeat"] = None
    return event


def _complete_visit(run: dict[str, Any], visit: dict[str, Any], choice_id: str, result: dict[str, Any], target: str | None) -> None:
    visit.update({
        "status": "completed", "choice_id": choice_id, "effects_result": deepcopy(result),
        "transition_to": target, "resolved_time": visit.get("resolved_time"), "updated_at": _now(),
    })
    if visit["node_id"] not in run.setdefault("visited_nodes", []):
        run["visited_nodes"].append(visit["node_id"])


def _resolve_terminal(state: dict[str, Any], run: dict[str, Any], visit: dict[str, Any], node: dict[str, Any], *, actor: str) -> list[dict[str, Any]]:
    events, result = _execute(state, run, visit, node, actor=actor)
    visit["resolved_time"] = time_point_from_state(state)
    _complete_visit(run, visit, f"terminal:{visit['node_id']}", result, None)
    _log_visit(run, visit, node, result)
    if state.get("active_scene"):
        _close_arc_scene(state, run["id"], f"剧情终局：{node.get('title', visit['node_id'])}")
    entry = scheduled_events.resolve_event(
        state, str(run["entry_scheduled_event_id"]), result_md=visit["narrative_md"],
        outcome={"story_arc_run_id": run["id"], "facts": deepcopy(run.get("facts", {})), "node_visits": deepcopy(run.get("node_visits", []))},
        resolved_by="story_arc_runtime",
    )
    ops = {str(effect.get("op")) for effect in node.get("effects", []) if isinstance(effect, dict)}
    next_event = _schedule_series(state, run, definition_for_run(run)) if "schedule_series_occurrence" in ops else None
    run.update({
        "status": "completed", "current_node_id": visit["node_id"], "current_visit_id": None,
        "pending_node_event_id": None, "resolved_time": time_point_from_state(state),
        "terminal_visit_id": visit["visit_id"], "entry_event_result": entry.get("result_md", ""),
    })
    if next_event:
        run["next_occurrence_event_id"] = next_event["id"]
    if state["storylets"].get("current_instance_id") == visit.get("legacy_instance_id"):
        state["storylets"]["current_instance_id"] = None
    return events


def _activate(state: dict[str, Any], run: dict[str, Any], visit: dict[str, Any], *, timed_ready: bool = False, actor: str = "story_arc_runtime", depth: int = 0) -> list[dict[str, Any]]:
    if depth >= MAX_AUTOMATIC_STEPS:
        raise HTTPException(500, "invalid_authored_graph: automatic 节点超过安全步数")
    node = _node(definition_for_run(run), visit["node_id"])
    run["current_node_id"] = visit["node_id"]
    run["current_visit_id"] = visit["visit_id"]
    visit["activated_time"] = time_point_from_state(state); visit["updated_at"] = _now()
    kind = str(node["kind"])
    if kind == "timed" and not timed_ready:
        visit["status"] = "ready"; _schedule_timed(state, run, visit, node); return []
    if kind in {"choice", "timed"}:
        visit["status"] = "awaiting_choice"; run["pending_node_event_id"] = None
        state["storylets"]["current_instance_id"] = visit["legacy_instance_id"]
        _start_scene(state, run, visit, node); return []
    if kind == "terminal":
        return _resolve_terminal(state, run, visit, node, actor=actor)
    events, result = _execute(state, run, visit, node, actor=actor)
    transition = _automatic_transition(state, run, node)
    target = str(transition["to"])
    visit["resolved_time"] = time_point_from_state(state)
    _complete_visit(run, visit, f"automatic:{visit['node_id']}", result, target)
    _log_visit(run, visit, node, result)
    run["transition_seq"] = int(run.get("transition_seq", 0)) + 1
    return events + _activate(state, run, _new_visit(state, run, target), actor=actor, depth=depth + 1)


def try_activate_arc_entry(state: dict[str, Any], event_id: str, *, seed: int = 1) -> dict[str, Any]:
    from ..engine.scenes import VALID_SCENE_TYPES
    from .config import EFFECT_OPS, get_arc_definition
    from .graph import analyze_graph
    from .service import _instantiate_on_state, normalize_storylet_state

    normalize_storylet_state(state)
    event = _event_by_id(state, event_id)
    definition_id = str(event.get("flags", {}).get("story_arc_definition_id", ""))
    existing = next((run for run in state["storylets"]["arc_runs"].values() if run.get("entry_scheduled_event_id") == event_id), None)
    if existing:
        event.setdefault("flags", {}).update({"story_arc_run_id": existing["id"], "story_arc_chain_id": existing["id"]})
        return {"status": "idempotent", "run_id": existing["id"], "event_id": event_id, "arc": public_arc(state, existing["id"])}
    if event.get("status") not in {"scheduled", "due"}:
        return {"status": "ignored", "run_id": None, "event_id": event_id}
    if state.get("active_scene") is not None:
        event["status"] = "due"
        event.setdefault("flags", {}).update({"queued_for_scene": True, "activation_state": "queued"})
        event["updated_at"] = _now()
        return {"status": "queued", "run_id": None, "event_id": event_id, "reason": "scene_busy"}

    detached = deepcopy(state)
    entry = _event_by_id(detached, event_id)
    graph = canonical_definition(get_arc_definition(definition_id))
    analyze_graph(graph, effect_ops=EFFECT_OPS, valid_scene_types=VALID_SCENE_TYPES)
    temporary = _instantiate_on_state(detached, definition_id, node_key=str(graph["entry_node"]), seed=seed)
    # schedule_event normalizes the collection and replaces event dictionaries.
    # Never continue mutating the stale reference captured before instantiation.
    entry = _event_by_id(detached, event_id)
    temporary_event_id = temporary.get("scheduled_event_id")
    _remove_event(detached, temporary_event_id)
    old_chain_id = temporary["chain_id"]
    old_chain = detached["storylets"]["chains"].pop(old_chain_id)
    detached["storylets"]["instances"] = [item for item in detached["storylets"]["instances"] if item.get("id") != temporary["id"]]
    run_id = next_run_id(detached)
    run = {
        "id": run_id, "runtime_version": 3, "definition_id": definition_id,
        "definition_version": int(graph.get("version", 1)), "definition_hash": definition_hash(graph),
        "definition_snapshot": graph, "definition_snapshot_origin": "published_at_start",
        "status": "active", "entry_scheduled_event_id": event_id,
        "current_node_id": str(graph["entry_node"]), "current_visit_id": None,
        "cast": deepcopy(old_chain.get("cast", {})), "cast_snapshots": deepcopy(old_chain.get("cast_snapshots", {})),
        "facts": deepcopy(old_chain.get("facts", {})), "obligations": deepcopy(old_chain.get("obligations", [])),
        "seed": int(seed), "transition_seq": 0, "pending_node_event_id": None,
        "node_visits": [], "visited_nodes": [], "transition_log": [],
        "started_time": time_point_from_state(detached), "resolved_time": None,
        "series_id": entry.get("flags", {}).get("series_id"), "occurrence_key": entry.get("flags", {}).get("occurrence_key"),
        "category": graph.get("category", "daily"), "priority": graph.get("priority", "major"),
        "scene_type": graph.get("scene_type", "daily"),
    }
    inherited = entry.get("flags", {}).get("inherited_arc_facts", {})
    if isinstance(inherited, dict):
        run["facts"].update(deepcopy(inherited))
    detached["storylets"]["arc_runs"][run_id] = run
    for character in detached.get("characters", {}).get("entries", []):
        narrative = character.get("components", {}).get("narrative", {})
        ids = narrative.get("active_chain_ids", [])
        narrative["active_chain_ids"] = [run_id if value == old_chain_id else value for value in ids]
    visit = _new_visit(detached, run, str(graph["entry_node"]), legacy_id=str(temporary["id"]))
    entry["status"] = "active"
    entry["activated_time"] = time_point_from_state(detached)
    entry.setdefault("flags", {}).update({
        "story_arc_run_id": run_id, "story_arc_chain_id": run_id,
        "story_event_id": visit["legacy_instance_id"], "story_arc_visit_id": visit["visit_id"],
        "blocking": True, "activation_state": "activated",
    })
    entry["flags"].pop("queued_for_scene", None); entry["schedule"]["repeat"] = None; entry["updated_at"] = _now()
    _activate(detached, run, visit)
    state.clear(); state.update(detached)
    logger.info("story_arc_activated run_id=%s definition_id=%s event_id=%s", run_id, definition_id, event_id)
    return {"status": "activated", "run_id": run_id, "event_id": event_id, "arc": public_arc(state, run_id)}


def start_arc_from_scheduled_event(state: dict[str, Any], definition_id: str, event_id: str, *, seed: int = 1) -> dict[str, Any]:
    event = _event_by_id(state, event_id)
    event.setdefault("flags", {})["story_arc_definition_id"] = definition_id
    result = try_activate_arc_entry(state, event_id, seed=seed)
    if result["status"] == "queued":
        raise HTTPException(409, "当前已有进行中的场景，剧情入口已排队")
    if not result.get("arc"):
        raise HTTPException(409, "剧情入口当前不能激活")
    return result["arc"]


def choose_arc_node(state: dict[str, Any], run_id: str, visit_or_legacy_id: str, choice_id: str, *, expected_transition_seq: int | None = None, actor: str = "player") -> dict[str, Any]:
    run = run_by_id(state, run_id)
    visit = visit_by_id(run, visit_or_legacy_id)
    if visit.get("status") == "completed":
        if visit.get("choice_id") == choice_id:
            return {
                "idempotent": True, "run_id": run_id, "visit_id": visit["visit_id"], "choice_id": choice_id,
                "arc": public_arc(state, run_id), "chain": public_arc(state, run_id)["chain"],
                "transition": {"from": visit["node_id"], "to": visit.get("transition_to")},
                "terminal": run.get("status") == "completed", "events": [], "result": deepcopy(visit.get("effects_result") or {}),
            }
        raise HTTPException(409, "choice_conflict: 该节点已经选择了另一项裁断")
    if run.get("status") == "completed":
        raise HTTPException(409, "arc_already_resolved: 剧情图已经结束")
    if run.get("current_visit_id") != visit["visit_id"]:
        raise HTTPException(409, "node_not_current: 该节点已不是当前节点")
    if expected_transition_seq is not None and int(run.get("transition_seq", 0)) != int(expected_transition_seq):
        raise HTTPException(409, "stale_transition_seq: 页面中的剧情节点已经过期")
    if visit.get("status") != "awaiting_choice":
        raise HTTPException(409, "node_not_current: 当前节点不能选择")

    detached = deepcopy(state)
    run = run_by_id(detached, run_id); visit = visit_by_id(run, visit_or_legacy_id)
    node = _node(definition_for_run(run), visit["node_id"]); choice = _choice(node, choice_id)
    transition = choice.get("transition")
    if not isinstance(transition, dict):
        raise HTTPException(500, "invalid_authored_graph: choice 缺少 transition")
    before_log = len(run.get("transition_log", []))
    events, result = _execute(detached, run, visit, node, actor=actor, choice=choice)
    target = str(transition["to"]); visit["resolved_time"] = time_point_from_state(detached)
    _complete_visit(run, visit, choice_id, result, target)
    node_event_id = visit.get("scheduled_event_id")
    if node_event_id and node_event_id != run.get("entry_scheduled_event_id"):
        scheduled_events.resolve_event(detached, node_event_id, result_md=choice.get("description_md", choice["label"]), outcome=result, resolved_by="story_arc_runtime")
    _close_arc_scene(detached, run_id, f"剧情节点已裁定：{choice['label']}")
    if detached["storylets"].get("current_instance_id") == visit.get("legacy_instance_id"):
        detached["storylets"]["current_instance_id"] = None
    run["transition_seq"] = int(run.get("transition_seq", 0)) + 1
    events.extend(_activate(detached, run, _new_visit(detached, run, target), actor=actor))
    if detached.get("active_scene") is None:
        activate_queued_nodes(detached)
    new_log = deepcopy(run.get("transition_log", [])[before_log:])
    state.clear(); state.update(detached)
    logger.info("story_arc_choice run_id=%s visit_id=%s choice_id=%s terminal=%s", run_id, visit["visit_id"], choice_id, run.get("status") == "completed")
    payload = public_arc(state, run_id)
    return {
        "idempotent": False, "run_id": run_id, "visit_id": visit["visit_id"], "choice_id": choice_id,
        "arc": payload, "chain": payload["chain"], "instance": public_visit(run_by_id(state, run_id), visit_by_id(run_by_id(state, run_id), visit["visit_id"]), node),
        "next_instance": payload.get("current_instance"), "transition": {"from": visit["node_id"], "to": target},
        "terminal": payload["run"].get("status") == "completed", "events": events, "result": result,
        "transition_log": new_log,
    }


def activate_timed_node(state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    flags = event.get("flags", {}); run_id = str(flags.get("story_arc_run_id") or flags.get("story_arc_chain_id") or "")
    run = state.get("storylets", {}).get("arc_runs", {}).get(run_id)
    if not isinstance(run, dict) or run.get("status") != "active":
        return {"status": "ignored"}
    visit = visit_by_id(run, str(flags.get("story_arc_visit_id") or flags.get("story_event_id") or ""))
    if run.get("current_visit_id") != visit["visit_id"]:
        return {"status": "idempotent"}
    if state.get("active_scene") is not None:
        event["status"] = "due"; event.setdefault("flags", {})["queued_for_scene"] = True
        return {"status": "queued"}
    detached = deepcopy(state); event_copy = _event_by_id(detached, str(event["id"])); run_copy = run_by_id(detached, run_id); visit_copy = visit_by_id(run_copy, visit["visit_id"])
    event_copy["status"] = "active"; event_copy.setdefault("flags", {}).pop("queued_for_scene", None)
    _activate(detached, run_copy, visit_copy, timed_ready=True)
    state.clear(); state.update(detached)
    return {"status": "activated", "run_id": run_id, "arc": public_arc(state, run_id)}


def activate_queued_nodes(state: dict[str, Any]) -> dict[str, Any] | None:
    if state.get("active_scene") is not None:
        return None
    candidates = []
    for event in state.get("scheduled_events", {}).get("entries", []):
        flags = event.get("flags", {}) if isinstance(event.get("flags"), dict) else {}
        if event.get("status") == "due" and flags.get("queued_for_scene"):
            candidates.append(event)
    if not candidates:
        return None
    candidates.sort(key=lambda event: (-int(event.get("importance", 0)), time_key(event["schedule"]["due_time"]), str(event.get("id"))))
    event = candidates[0]
    if event.get("type") == "story_arc_node":
        return activate_timed_node(state, event)
    return try_activate_arc_entry(state, str(event["id"]), seed=int(event.get("flags", {}).get("story_arc_seed", 2001)))


def public_arc(state: dict[str, Any], run_id: str) -> dict[str, Any]:
    run = run_by_id(state, run_id); graph = definition_for_run(run)
    current = visit_by_id(run, str(run["current_visit_id"])) if run.get("current_visit_id") else None
    node = _node(graph, current["node_id"]) if current else (_node(graph, str(run["current_node_id"])) if run.get("current_node_id") else None)
    budget = (node or {}).get("interaction_budget", graph.get("interaction_budget", {}))
    maximum = int(budget.get("max_freeform_steps", budget.get("default_max_freeform_steps", 2)) if isinstance(budget, dict) else 2)
    used = int(current.get("freeform_steps_used", 0)) if current else 0
    legal_choices = []
    if current and current.get("status") == "awaiting_choice" and node:
        legal_choices = [{key: deepcopy(value) for key, value in choice.items() if key not in {"effects", "transition"}} for choice in node.get("choices", [])]
    timeline = []
    for visit in run.get("node_visits", []):
        visit_node = _node(graph, str(visit["node_id"]))
        timeline.append({
            "visit_id": visit["visit_id"], "node_id": visit["node_id"], "title": visit_node.get("title", visit["node_id"]),
            "status": "active" if visit.get("visit_id") == run.get("current_visit_id") and run.get("status") == "active" else visit.get("status"),
            "selected_choice_id": visit.get("choice_id"),
        })
    public_node = None
    if node:
        public_node = {key: deepcopy(value) for key, value in node.items() if key not in {"effects", "transition", "transitions", "choices"}}
        public_node["choices"] = legal_choices
    public_run = {key: deepcopy(value) for key, value in run.items() if key != "definition_snapshot"}
    # One-release compatibility aliases.
    public_run["current_instance_id"] = current.get("legacy_instance_id") if current else None
    return {
        "run": public_run, "chain": deepcopy(public_run),
        "definition": {"id": graph["id"], "version": graph.get("version", 1), "hash": run.get("definition_hash"), "title": graph.get("title", graph["id"])},
        "current_node": public_node, "current_visit": deepcopy(current),
        "current_instance": public_visit(run, current, node) if current and node else None,
        "timeline": timeline, "legal_choices": legal_choices, "transition_log": deepcopy(run.get("transition_log", [])),
        "interaction_budget": {"used": used, "maximum": maximum, "freeform_allowed": used < maximum},
    }


def focused_arc_id(state: dict[str, Any]) -> str | None:
    runs = state.get("storylets", {}).get("arc_runs", {})
    scene = state.get("active_scene")
    if isinstance(scene, dict):
        candidate = scene.get("flags", {}).get("story_arc_run_id") or scene.get("flags", {}).get("story_arc_chain_id")
        if candidate in runs and runs[candidate].get("status") == "active":
            return str(candidate)
    explicit = state.get("storylets", {}).get("focused_arc_id")
    if explicit in runs and runs[explicit].get("status") == "active":
        return str(explicit)
    current_legacy = state.get("storylets", {}).get("current_instance_id")
    if current_legacy:
        matched = find_visit(state, str(current_legacy))
        if matched and matched[0].get("status") == "active":
            return str(matched[0]["id"])
    queued_ids = []
    for event in state.get("scheduled_events", {}).get("entries", []):
        flags = event.get("flags", {})
        run_id = flags.get("story_arc_run_id") or flags.get("story_arc_chain_id")
        if event.get("status") == "due" and flags.get("queued_for_scene") and run_id in runs:
            queued_ids.append(str(run_id))
    if queued_ids:
        return queued_ids[0]
    active = [run for run in runs.values() if isinstance(run, dict) and run.get("status") == "active"]
    active.sort(key=lambda run: (time_key(run.get("started_time", {})), str(run.get("id"))))
    return str(active[0]["id"]) if active else None


def list_active_arcs(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [public_arc(state, run["id"]) for run in state.get("storylets", {}).get("arc_runs", {}).values() if isinstance(run, dict) and run.get("status") == "active"]


def current_arc(state: dict[str, Any]) -> dict[str, Any] | None:
    run_id = focused_arc_id(state)
    return public_arc(state, run_id) if run_id else None


def audit_arc_consistency(state: dict[str, Any], run_id: str) -> list[str]:
    run = state.get("storylets", {}).get("arc_runs", {}).get(run_id)
    if not isinstance(run, dict):
        return ["run_missing"]
    errors: list[str] = []
    visits = [visit for visit in run.get("node_visits", []) if isinstance(visit, dict)]
    ids = [visit.get("visit_id") for visit in visits]
    if len(ids) != len(set(ids)): errors.append("duplicate_visit_id")
    entry = next((event for event in state.get("scheduled_events", {}).get("entries", []) if event.get("id") == run.get("entry_scheduled_event_id")), None)
    if entry is None: errors.append("entry_event_missing")
    if run.get("definition_hash") != definition_hash(definition_for_run(run)): errors.append("run_definition_hash_mismatch")
    current = next((visit for visit in visits if visit.get("visit_id") == run.get("current_visit_id")), None)
    if run.get("status") == "active":
        if current is None: errors.append("current_visit_missing")
        if entry and entry.get("status") != "active": errors.append("entry_event_not_active")
    if len([visit for visit in visits if visit.get("status") == "awaiting_choice"]) > 1: errors.append("multiple_awaiting_visits")
    if run.get("status") == "completed":
        if run.get("current_visit_id"): errors.append("completed_run_has_current_visit")
        if entry and entry.get("status") != "resolved": errors.append("completed_entry_event_not_resolved")
    scene = state.get("active_scene")
    if isinstance(scene, dict) and (scene.get("flags", {}).get("story_arc_run_id") or scene.get("flags", {}).get("story_arc_chain_id")) == run_id:
        if scene.get("flags", {}).get("story_arc_visit_id") != run.get("current_visit_id"): errors.append("scene_visit_mismatch")
    return errors


def debug_arc_state(state: dict[str, Any]) -> dict[str, Any]:
    runs = state.get("storylets", {}).get("arc_runs", {})
    queued_entry_ids: list[str] = []
    queued_timed_ids: list[str] = []
    for event in state.get("scheduled_events", {}).get("entries", []):
        if event.get("status") != "due" or not event.get("flags", {}).get("queued_for_scene"):
            continue
        (queued_timed_ids if event.get("type") == "story_arc_node" else queued_entry_ids).append(str(event.get("id")))
    return {
        "focused_arc_id": focused_arc_id(state),
        "active_run_ids": [str(run_id) for run_id, run in runs.items() if isinstance(run, dict) and run.get("status") == "active"],
        "queued_entry_event_ids": queued_entry_ids, "queued_timed_event_ids": queued_timed_ids,
        "runs": [{
            "id": run_id, "definition_id": run.get("definition_id"),
            "definition_version": run.get("definition_version"), "definition_hash": run.get("definition_hash"),
            "current_visit_id": run.get("current_visit_id"), "transition_seq": run.get("transition_seq"),
            "consistency_errors": audit_arc_consistency(state, str(run_id)),
        } for run_id, run in runs.items() if isinstance(run, dict)],
    }
