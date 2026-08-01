from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from ..engine import scenes
from ..engine.time import time_point_from_state
from ..systems import scheduled_events
from .config import get_arc_definition, get_definition
from .effects import execute_effects
from .graph import condition_matches
from .instances import instance_by_id, public_choice, public_instance

MAX_AUTOMATIC_STEPS = 16


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _event_by_id(state: dict[str, Any], event_id: str) -> dict[str, Any]:
    for event in state.get("scheduled_events", {}).get("entries", []):
        if event.get("id") == event_id:
            return event
    raise HTTPException(404, "未找到剧情图关联的计划事件")


def _remove_event(state: dict[str, Any], event_id: str | None) -> None:
    if not event_id:
        return
    entries = state.get("scheduled_events", {}).get("entries", [])
    state["scheduled_events"]["entries"] = [event for event in entries if event.get("id") != event_id]


def _node(graph: dict[str, Any], node_id: str) -> dict[str, Any]:
    try:
        return graph["nodes"][node_id]
    except KeyError as exc:
        raise HTTPException(500, f"invalid_authored_graph: 节点不存在 {node_id}") from exc


def _choice_transition(node: dict[str, Any], choice_id: str) -> dict[str, Any]:
    choice = next((item for item in node.get("choices", []) if item.get("id") == choice_id), None)
    if not choice:
        raise HTTPException(422, "invalid_choice: 该选择不属于当前剧情节点")
    transition = choice.get("transition")
    if not isinstance(transition, dict):
        raise HTTPException(500, "invalid_authored_graph: choice 缺少 transition")
    return transition


def _automatic_transition(state: dict[str, Any], chain: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    transitions = [item for item in node.get("transitions", []) if isinstance(item, dict)]
    if isinstance(node.get("transition"), dict):
        transitions.append(node["transition"])
    matches = [item for item in transitions if item.get("when") and condition_matches(item["when"], state, chain)]
    if len(matches) > 1:
        raise HTTPException(500, "invalid_authored_graph: automatic transition 不唯一")
    if matches:
        return matches[0]
    fallback = [item for item in transitions if not item.get("when")]
    if len(fallback) != 1:
        raise HTTPException(500, "invalid_authored_graph: automatic transition 缺少唯一 fallback")
    return fallback[0]


def _instance_for_node(state: dict[str, Any], chain: dict[str, Any], node_id: str) -> dict[str, Any]:
    from .service import _instantiate_on_state

    instance = _instantiate_on_state(
        state,
        chain["definition_id"],
        node_key=node_id,
        seed=int(chain.get("seed", 1)) + int(chain.get("transition_seq", 0)) + 1009,
        chain_id=chain["id"],
        inherited_cast=chain.get("cast", {}),
        inherited_snapshots=chain.get("cast_snapshots", {}),
        inherited_facts=chain.get("facts", {}),
        due_in_days=0,
    )
    temporary_event_id = instance.get("scheduled_event_id")
    _remove_event(state, temporary_event_id)
    instance["scheduled_event_id"] = None
    instance["runtime_version"] = 2
    instance["arc_node_kind"] = _node(get_arc_definition(chain["definition_id"]), node_id).get("kind")
    return instance


def _close_arc_scene(state: dict[str, Any], chain_id: str, summary: str) -> None:
    scene = state.get("active_scene")
    if not isinstance(scene, dict):
        return
    if scene.get("flags", {}).get("story_arc_chain_id") != chain_id:
        raise HTTPException(409, "node_not_current: 当前场景不属于该剧情图")
    scenes.end_scene(state, summary=summary, outcome={"story_arc_chain_id": chain_id}, allow_story_arc=True)


def _start_node_scene(state: dict[str, Any], chain: dict[str, Any], instance: dict[str, Any], node: dict[str, Any]) -> None:
    if state.get("active_scene") is not None:
        raise HTTPException(409, "当前已有进行中的场景，剧情节点已排队")
    scene = scenes.start_scene(
        state,
        str(node.get("scene_type") or "daily"),
        str(node.get("title") or instance.get("title") or chain["definition_id"]),
        participants=[{"role": role, **snapshot} for role, snapshot in instance.get("cast_snapshots", {}).items()],
        flags={
            "source": "story_arc",
            "story_arc_chain_id": chain["id"],
            "story_arc_definition_id": chain["definition_id"],
            "story_arc_node_id": instance["node_key"],
            "story_event_id": instance["id"],
            "entry_scheduled_event_id": chain.get("entry_scheduled_event_id"),
            "blocking": bool(node.get("blocking", True)),
        },
    )
    instance["scene_id"] = scene["id"]


def _schedule_timed_node(state: dict[str, Any], chain: dict[str, Any], instance: dict[str, Any], node: dict[str, Any]) -> None:
    event = scheduled_events.schedule_event(
        state,
        event_type="story_arc_node",
        title=str(node.get("title") or instance["title"]),
        description_md=str(node.get("narrative_template_md", "")),
        in_days=int(node.get("after_days", 0) or 0),
        in_hours=int(node.get("after_hours", 0) or 0),
        visibility="player",
        importance=4 if instance.get("priority") == "major" else 2,
        related={"people": list(instance.get("cast", {}).values()), "scheduled_events": [chain.get("entry_scheduled_event_id")]},
        flags={
            "story_arc_definition_id": chain["definition_id"],
            "story_arc_chain_id": chain["id"],
            "story_arc_node_id": instance["node_key"],
            "story_event_id": instance["id"],
            "entry_scheduled_event_id": chain.get("entry_scheduled_event_id"),
            "blocking": bool(node.get("blocking", True)),
        },
        created_by="story_arc_runtime",
    )
    event["schedule"]["repeat"] = None
    instance["scheduled_event_id"] = event["id"]
    chain["pending_node_event_id"] = event["id"]


def _record_node_result(chain: dict[str, Any], instance: dict[str, Any], choice_id: str, result: dict[str, Any], target: str | None) -> None:
    chain.setdefault("node_results", {})[instance["node_key"]] = {
        "instance_id": instance["id"],
        "choice_id": choice_id,
        "result": deepcopy(result),
        "transition_to": target,
        "resolved_time": instance.get("resolved_time"),
        "transition_seq": int(chain.get("transition_seq", 0)),
    }
    if instance["node_key"] not in chain.setdefault("visited_nodes", []):
        chain["visited_nodes"].append(instance["node_key"])


def _execute_node_effects(state: dict[str, Any], instance: dict[str, Any], node: dict[str, Any], *, actor: str, choice: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    executable = choice or {
        "id": f"{node.get('kind', 'automatic')}:{instance['node_key']}",
        "label": str(node.get("title") or instance["title"]),
        "description_md": str(node.get("narrative_template_md", "")),
        "effects": node.get("effects", []),
    }
    events, result, followups = execute_effects(state, instance, executable, actor=actor)
    if followups:
        raise HTTPException(500, "invalid_authored_graph: schema v2 不允许 schedule_followup")
    return [event.model_dump() for event in events], result


def _next_occurrence_key(route_id: str, due_day: int) -> str:
    year = (max(1, due_day) - 1) // 360 + 1
    season_index = ((max(1, due_day) - 1) % 360) // 90
    season = ("spring", "summer", "autumn", "winter")[season_index]
    return f"caravan:{route_id}:year_{year}:{season}"


def _schedule_series(state: dict[str, Any], chain: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any] | None:
    series = graph.get("series", {}) if isinstance(graph.get("series"), dict) else {}
    if not series:
        return None
    route_id = str(chain.get("facts", {}).get("route_id") or series.get("route_id") or "default")
    outcome_key = str(chain.get("facts", {}).get(str(series.get("outcome_fact", "departure_reason")), "normal_trade"))
    rule = series.get("outcomes", {}).get(outcome_key, series.get("default", {}))
    if not isinstance(rule, dict) or rule.get("schedule") is False:
        return None
    in_days = max(1, int(rule.get("in_days", 90)))
    due_day = int(state.get("time", {}).get("calendar_day", 1)) + in_days
    occurrence_key = _next_occurrence_key(route_id, due_day)
    for event in state.get("scheduled_events", {}).get("entries", []):
        if event.get("flags", {}).get("occurrence_key") == occurrence_key and event.get("status") not in {"cancelled", "missed"}:
            return event
    entry_event = _event_by_id(state, str(chain["entry_scheduled_event_id"]))
    event = scheduled_events.schedule_event(
        state,
        event_type=str(series.get("event_type") or entry_event.get("type") or "caravan_arrival"),
        title=str(graph.get("title", "商队到访")),
        description_md=str(graph.get("description_md", "商队将再次沿旧路来到领地。")),
        in_days=in_days,
        visibility="player",
        importance=int(graph.get("importance", 3)),
        flags={
            "story_arc_definition_id": graph["id"], "series_id": series.get("id", route_id),
            "route_id": route_id, "occurrence_key": occurrence_key,
            "inherited_arc_facts": deepcopy(rule.get("inherit_facts", {})),
        },
        created_by="story_arc_runtime",
    )
    event["schedule"]["repeat"] = None
    return event


def _resolve_terminal(state: dict[str, Any], chain: dict[str, Any], instance: dict[str, Any], node: dict[str, Any], *, actor: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    instance["scheduled_event_id"] = chain.get("entry_scheduled_event_id")
    events, result = _execute_node_effects(state, instance, node, actor=actor)
    instance["status"] = "resolved"
    instance["selected_choice_id"] = f"terminal:{instance['node_key']}"
    instance["result"] = result
    instance["resolved_time"] = time_point_from_state(state)
    instance["updated_at"] = _now()
    _record_node_result(chain, instance, instance["selected_choice_id"], result, None)
    _close_arc_scene(state, chain["id"], f"剧情终局：{instance['title']}") if state.get("active_scene") else None
    entry_event = scheduled_events.resolve_event(
        state,
        str(chain["entry_scheduled_event_id"]),
        result_md=str(node.get("narrative_template_md", instance["title"])),
        outcome={"story_arc_chain_id": chain["id"], "facts": deepcopy(chain.get("facts", {})), "node_results": deepcopy(chain.get("node_results", {}))},
        resolved_by="story_arc_runtime",
    )
    runtime_ops = {
        str(effect.get("op"))
        for effect in node.get("effects", [])
        if isinstance(effect, dict)
    }
    next_event = _schedule_series(state, chain, get_arc_definition(chain["definition_id"])) if "schedule_series_occurrence" in runtime_ops else None
    chain["status"] = "completed"
    chain["current_node_id"] = instance["node_key"]
    chain["current_instance_id"] = None
    chain["pending_node_event_id"] = None
    chain["resolved_time"] = time_point_from_state(state)
    chain["terminal_instance_id"] = instance["id"]
    chain["entry_event_result"] = entry_event.get("result_md", "")
    if next_event:
        chain["next_occurrence_event_id"] = next_event["id"]
    if state["storylets"].get("current_instance_id") == instance["id"]:
        state["storylets"]["current_instance_id"] = None
    return events, result


def _activate_node(state: dict[str, Any], chain: dict[str, Any], instance: dict[str, Any], *, timed_ready: bool = False, actor: str = "story_arc_runtime", depth: int = 0) -> list[dict[str, Any]]:
    if depth >= MAX_AUTOMATIC_STEPS:
        raise HTTPException(500, "invalid_authored_graph: automatic 节点超过安全步数")
    graph = get_arc_definition(chain["definition_id"])
    node = _node(graph, instance["node_key"])
    kind = str(node["kind"])
    chain["current_node_id"] = instance["node_key"]
    chain["current_instance_id"] = instance["id"]
    instance["activated_time"] = time_point_from_state(state)
    instance["updated_at"] = _now()
    if kind == "timed" and not timed_ready:
        instance["status"] = "ready"
        _schedule_timed_node(state, chain, instance, node)
        return []
    if kind in {"choice", "timed"}:
        instance["status"] = "awaiting_choice"
        state["storylets"]["current_instance_id"] = instance["id"]
        chain["pending_node_event_id"] = None
        _start_node_scene(state, chain, instance, node)
        return []
    if kind == "terminal":
        terminal_events, _ = _resolve_terminal(state, chain, instance, node, actor=actor)
        return terminal_events
    events, result = _execute_node_effects(state, instance, node, actor=actor)
    transition = _automatic_transition(state, chain, node)
    target = str(transition["to"])
    instance["status"] = "resolved"
    instance["selected_choice_id"] = f"automatic:{instance['node_key']}"
    instance["result"] = result
    instance["resolved_time"] = time_point_from_state(state)
    _record_node_result(chain, instance, instance["selected_choice_id"], result, target)
    chain["transition_seq"] = int(chain.get("transition_seq", 0)) + 1
    next_instance = _instance_for_node(state, chain, target)
    return events + _activate_node(state, chain, next_instance, actor=actor, depth=depth + 1)


def start_arc_from_scheduled_event(state: dict[str, Any], definition_id: str, event_id: str, *, seed: int = 1) -> dict[str, Any]:
    for chain in state.get("storylets", {}).get("chains", {}).values():
        if chain.get("runtime_version") == 2 and chain.get("entry_scheduled_event_id") == event_id:
            return public_arc(state, chain["id"])
    detached = deepcopy(state)
    graph = get_arc_definition(definition_id)
    entry_event = _event_by_id(detached, event_id)
    from .service import _instantiate_on_state, normalize_storylet_state

    normalize_storylet_state(detached)
    instance = _instantiate_on_state(detached, definition_id, node_key=str(graph["entry_node"]), seed=seed)
    temporary_event_id = instance.get("scheduled_event_id")
    _remove_event(detached, temporary_event_id)
    instance["scheduled_event_id"] = event_id
    instance["runtime_version"] = 2
    instance["arc_node_kind"] = _node(graph, instance["node_key"])["kind"]
    chain = detached["storylets"]["chains"][instance["chain_id"]]
    inherited = entry_event.get("flags", {}).get("inherited_arc_facts", {})
    chain.update({
        "definition_version": int(graph.get("version", 1)), "runtime_version": 2, "status": "active",
        "current_node_id": instance["node_key"], "current_instance_id": instance["id"],
        "entry_scheduled_event_id": event_id, "series_id": entry_event.get("flags", {}).get("series_id"),
        "occurrence_key": entry_event.get("flags", {}).get("occurrence_key"), "visited_nodes": [],
        "node_results": {}, "transition_seq": 0, "pending_node_event_id": None,
        "started_time": time_point_from_state(detached), "resolved_time": None, "seed": int(seed),
    })
    if isinstance(inherited, dict):
        chain["facts"].update(deepcopy(inherited))
        instance["facts"].update(deepcopy(inherited))
    entry_event.setdefault("flags", {}).update({
        "story_arc_definition_id": definition_id, "story_arc_chain_id": chain["id"],
        "story_event_id": instance["id"], "blocking": True,
    })
    entry_event["schedule"]["repeat"] = None
    _activate_node(detached, chain, instance)
    state.clear(); state.update(detached)
    return public_arc(state, chain["id"])


def choose_arc_node(
    state: dict[str, Any], chain_id: str, instance_id: str, choice_id: str, *,
    expected_transition_seq: int | None = None, actor: str = "player",
) -> dict[str, Any]:
    original_chain = state.get("storylets", {}).get("chains", {}).get(chain_id)
    if not isinstance(original_chain, dict) or original_chain.get("runtime_version") != 2:
        raise HTTPException(404, "未找到 Story Arc")
    prior = original_chain.get("node_results", {}).get(original_chain.get("current_node_id"), {})
    if original_chain.get("status") == "completed":
        if prior.get("instance_id") == instance_id and prior.get("choice_id") == choice_id:
            return {"idempotent": True, "arc": public_arc(state, chain_id), "events": []}
        raise HTTPException(409, "arc_already_resolved: 剧情图已经结束")
    if original_chain.get("current_instance_id") != instance_id:
        completed = next((item for item in original_chain.get("node_results", {}).values() if item.get("instance_id") == instance_id), None)
        if completed and completed.get("choice_id") == choice_id:
            return {"idempotent": True, "arc": public_arc(state, chain_id), "events": []}
        raise HTTPException(409, "node_not_current: 该节点已不是当前节点")
    if expected_transition_seq is not None and int(original_chain.get("transition_seq", 0)) != int(expected_transition_seq):
        raise HTTPException(409, "stale_transition_seq: 页面中的剧情节点已经过期")

    detached = deepcopy(state)
    chain = detached["storylets"]["chains"][chain_id]
    instance = instance_by_id(detached, instance_id)
    if instance.get("status") != "awaiting_choice":
        raise HTTPException(409, "node_not_current: 当前节点不能选择")
    graph = get_arc_definition(chain["definition_id"])
    node = _node(graph, instance["node_key"])
    choice = next((item for item in node.get("choices", []) if item.get("id") == choice_id), None)
    if not choice or choice_id not in instance.get("choice_ids", []):
        raise HTTPException(422, "invalid_choice: 该选择不属于当前节点")
    transition = _choice_transition(node, choice_id)
    events, result = _execute_node_effects(detached, instance, node, actor=actor, choice=choice)
    target = str(transition["to"])
    instance["status"] = "resolved"
    instance["selected_choice_id"] = choice_id
    instance["result"] = result
    instance["resolved_time"] = time_point_from_state(detached)
    instance["updated_at"] = _now()
    _record_node_result(chain, instance, choice_id, result, target)
    node_event_id = instance.get("scheduled_event_id")
    if node_event_id and node_event_id != chain.get("entry_scheduled_event_id"):
        scheduled_events.resolve_event(detached, node_event_id, result_md=choice.get("description_md", choice["label"]), outcome=result, resolved_by="story_arc_runtime")
    _close_arc_scene(detached, chain_id, f"剧情节点已裁定：{choice['label']}")
    if detached["storylets"].get("current_instance_id") == instance_id:
        detached["storylets"]["current_instance_id"] = None
    chain["transition_seq"] = int(chain.get("transition_seq", 0)) + 1
    next_instance = _instance_for_node(detached, chain, target)
    events.extend(_activate_node(detached, chain, next_instance, actor=actor))
    state.clear(); state.update(detached)
    payload = public_arc(state, chain_id)
    return {
        "idempotent": False, "arc": payload, "chain": payload["chain"],
        "instance": public_instance(instance_by_id(state, instance_id), get_definition(chain["definition_id"], instance["node_key"])),
        "next_instance": payload.get("current_instance"), "transition": {"from": instance["node_key"], "to": target},
        "terminal": payload["chain"].get("status") == "completed", "events": events, "result": result,
    }


def activate_timed_node(state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    flags = event.get("flags", {})
    chain_id = str(flags.get("story_arc_chain_id", ""))
    chain = state.get("storylets", {}).get("chains", {}).get(chain_id)
    if not isinstance(chain, dict) or chain.get("status") != "active":
        return {"status": "ignored"}
    instance = instance_by_id(state, str(flags.get("story_event_id", "")))
    if chain.get("current_instance_id") != instance["id"]:
        return {"status": "idempotent"}
    if state.get("active_scene") is not None:
        event["status"] = "active"
        event.setdefault("flags", {})["queued_for_scene"] = True
        return {"status": "queued"}
    event["status"] = "active"
    event.setdefault("flags", {}).pop("queued_for_scene", None)
    _activate_node(state, chain, instance, timed_ready=True)
    return public_arc(state, chain_id)


def activate_queued_nodes(state: dict[str, Any]) -> dict[str, Any] | None:
    """Activate one due arc node after an unrelated scene releases the scene lock."""
    if state.get("active_scene") is not None:
        return None
    for event in state.get("scheduled_events", {}).get("entries", []):
        flags = event.get("flags", {}) if isinstance(event.get("flags"), dict) else {}
        if event.get("type") == "story_arc_node" and event.get("status") == "active" and flags.get("queued_for_scene"):
            return activate_timed_node(state, event)
    return None


def public_arc(state: dict[str, Any], chain_id: str) -> dict[str, Any]:
    chain = state.get("storylets", {}).get("chains", {}).get(chain_id)
    if not isinstance(chain, dict) or chain.get("runtime_version") != 2:
        raise HTTPException(404, "未找到 Story Arc")
    graph = get_arc_definition(chain["definition_id"])
    instance = None
    if chain.get("current_instance_id"):
        instance = instance_by_id(state, chain["current_instance_id"])
    current_node = _node(graph, str(chain.get("current_node_id"))) if chain.get("current_node_id") else None
    budget = (current_node or {}).get("interaction_budget", graph.get("interaction_budget", {}))
    maximum = int(budget.get("max_freeform_steps", budget.get("default_max_freeform_steps", 2)) if isinstance(budget, dict) else 2)
    used = int(instance.get("freeform_steps_used", 0)) if instance else 0
    legal_choices = []
    if instance and instance.get("status") == "awaiting_choice" and current_node:
        allowed = set(instance.get("choice_ids", []))
        legal_choices = [public_choice(choice) for choice in current_node.get("choices", []) if choice.get("id") in allowed]
    timeline = []
    for node_id in chain.get("visited_nodes", []):
        result = chain.get("node_results", {}).get(node_id, {})
        timeline.append({"node_id": node_id, "title": _node(graph, node_id).get("title", node_id), "status": "completed", "selected_choice_id": result.get("choice_id")})
    if chain.get("current_node_id") and chain.get("status") == "active":
        timeline.append({"node_id": chain["current_node_id"], "title": (current_node or {}).get("title", chain["current_node_id"]), "status": "active"})
    public_node = None
    if current_node:
        public_node = {
            key: deepcopy(value)
            for key, value in current_node.items()
            if key not in {"effects", "transition", "transitions", "choices"}
        }
        public_node["choices"] = legal_choices
    return {
        "chain": deepcopy(chain),
        "definition": {"id": graph["id"], "version": graph.get("version", 1), "title": graph.get("title", graph["id"])},
        "current_node": public_node,
        "current_instance": public_instance(instance, get_definition(chain["definition_id"], instance["node_key"])) if instance else None,
        "timeline": timeline,
        "legal_choices": legal_choices,
        "interaction_budget": {"used": used, "maximum": maximum, "freeform_allowed": used < maximum},
    }


def current_arc(state: dict[str, Any]) -> dict[str, Any] | None:
    active = [chain for chain in state.get("storylets", {}).get("chains", {}).values() if chain.get("runtime_version") == 2 and chain.get("status") == "active"]
    if not active:
        return None
    active.sort(key=lambda item: str(item.get("id")))
    return public_arc(state, active[0]["id"])


def audit_arc_consistency(state: dict[str, Any], chain_id: str) -> list[str]:
    """Return invariant violations without mutating state; useful for tests and save audits."""
    chain = state.get("storylets", {}).get("chains", {}).get(chain_id)
    if not isinstance(chain, dict) or chain.get("runtime_version") != 2:
        return ["chain_missing"]
    errors: list[str] = []
    instances = {item.get("id"): item for item in state.get("storylets", {}).get("instances", []) if isinstance(item, dict)}
    entry = next((item for item in state.get("scheduled_events", {}).get("entries", []) if item.get("id") == chain.get("entry_scheduled_event_id")), None)
    if entry is None:
        errors.append("entry_event_missing")
    current_id = chain.get("current_instance_id")
    if chain.get("status") == "active":
        if not current_id or current_id not in instances:
            errors.append("current_instance_missing")
        if entry and entry.get("status") != "active":
            errors.append("entry_event_not_active")
    if chain.get("status") == "completed":
        if current_id:
            errors.append("completed_chain_has_current_instance")
        if entry and entry.get("status") != "resolved":
            errors.append("completed_entry_event_not_resolved")
    scene = state.get("active_scene")
    if isinstance(scene, dict) and scene.get("flags", {}).get("story_arc_chain_id") == chain_id:
        if scene.get("flags", {}).get("story_event_id") != current_id:
            errors.append("scene_instance_mismatch")
    return errors
