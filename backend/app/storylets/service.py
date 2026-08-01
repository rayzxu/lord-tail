from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from ..engine import scenes
from ..engine.history import append_history_entry
from ..engine.time import time_point_from_state
from ..systems.characters import create_character, get_character
from ..systems.scheduled_events import resolve_event, schedule_event
from .casting import cast_storylet
from .config import get_definition, load_definitions
from .effects import execute_effects
from .instances import instance_by_id, public_instance
from .parameters import generate_parameters
from .relationships import create_household, create_relationship, normalize_relationship_state
from .triggers import evaluate_triggers

INSTANCE_STATUSES = {"ready", "active", "awaiting_choice", "resolved", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def normalize_storylet_state(state: dict[str, Any]) -> None:
    raw = state.setdefault("storylets", {})
    instances = raw.get("instances") if isinstance(raw.get("instances"), list) else []
    raw["instances"] = [item for item in instances if isinstance(item, dict)]
    raw.setdefault("current_instance_id", None)
    raw["chains"] = raw.get("chains") if isinstance(raw.get("chains"), dict) else {}
    raw["cooldowns"] = raw.get("cooldowns") if isinstance(raw.get("cooldowns"), dict) else {}
    raw["recent_template_ids"] = raw.get("recent_template_ids") if isinstance(raw.get("recent_template_ids"), list) else []
    raw["recent_cast"] = raw.get("recent_cast") if isinstance(raw.get("recent_cast"), dict) else {}
    max_instance = 0
    max_chain = 0
    for instance in raw["instances"]:
        try:
            max_instance = max(max_instance, int(str(instance.get("id", "")).removeprefix("story_evt_")))
        except ValueError:
            pass
        if instance.get("status") not in INSTANCE_STATUSES:
            instance["status"] = "failed"
    for chain_id in raw["chains"]:
        try:
            max_chain = max(max_chain, int(str(chain_id).removeprefix("story_chain_")))
        except ValueError:
            pass
    raw["next_instance_id"] = max(max_instance + 1, int(raw.get("next_instance_id", 1) or 1))
    raw["next_chain_id"] = max(max_chain + 1, int(raw.get("next_chain_id", 1) or 1))
    director = raw.setdefault("director", {})
    defaults = {"enabled": True, "seed": 2001, "last_run_time": None, "last_decision": None, "major_events_this_turn": 0, "minor_events_this_turn": 0}
    for key, value in defaults.items():
        director.setdefault(key, value)
    normalize_relationship_state(state)


def _next_instance_id(state: dict[str, Any]) -> str:
    seq = int(state["storylets"]["next_instance_id"])
    state["storylets"]["next_instance_id"] = seq + 1
    return f"story_evt_{seq:06d}"


def _next_chain_id(state: dict[str, Any]) -> str:
    seq = int(state["storylets"]["next_chain_id"])
    state["storylets"]["next_chain_id"] = seq + 1
    return f"story_chain_{seq:06d}"


class _SafeFormat(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render_narrative(definition: dict[str, Any], facts: dict[str, Any], snapshots: dict[str, Any]) -> str:
    values = dict(facts)
    for role, snapshot in snapshots.items():
        values[f"{role}_name"] = snapshot.get("name", role)
        values[f"{role}_role"] = snapshot.get("role", "")
    return str(definition.get("narrative_template_md", definition.get("title", ""))).format_map(_SafeFormat(values))


def _instantiate_on_state(
    state: dict[str, Any], definition_id: str, *, node_key: str, seed: int,
    focus_character_id: str | None = None, chain_id: str | None = None,
    inherited_cast: dict[str, str] | None = None, inherited_snapshots: dict[str, Any] | None = None,
    inherited_facts: dict[str, Any] | None = None, due_in_days: int = 0,
) -> dict[str, Any]:
    normalize_storylet_state(state)
    definition = get_definition(definition_id, node_key)
    chain = state["storylets"]["chains"].get(chain_id, {}) if chain_id else {}
    chain_facts = deepcopy(inherited_facts or chain.get("facts", {}))
    ok, trigger_facts, reasons = evaluate_triggers(state, definition, chain_facts=chain_facts)
    if not ok and definition.get("source_kind") != "chain":
        raise HTTPException(422, "; ".join(reasons))
    parameter_input = {**trigger_facts, "eligible_classes": trigger_facts.get("eligible_classes", [])}
    facts = generate_parameters(state, definition, parameter_input, seed=seed, chain_facts=chain_facts)
    if inherited_cast is None:
        cast_draft = cast_storylet(state, definition, {**facts, **parameter_input}, seed=seed, focus_character_id=focus_character_id)
        cast = cast_draft["cast"]
        snapshots = cast_draft["cast_snapshots"]
        generated = cast_draft["generated_characters"]
        relationship_drafts = cast_draft.get("relationship_drafts", [])
        household_draft = cast_draft.get("household_draft")
    else:
        cast, snapshots, generated = deepcopy(inherited_cast), deepcopy(inherited_snapshots or {}), {}
        relationship_drafts, household_draft = [], None
    if "saved_gold" in facts and cast.get("petitioner"):
        petitioner_token = cast["petitioner"]
        if petitioner_token.startswith("@generated:"):
            economy = generated["petitioner"].setdefault("components", {}).setdefault("economy_agent", {"wealth": 0, "income": 0, "debts": []})
            economy["wealth"] = max(int(economy.get("wealth", 0)), int(facts["saved_gold"]))
            available_savings = int(economy["wealth"])
        else:
            try:
                available_savings = int(get_character(state, petitioner_token).get("components", {}).get("economy_agent", {}).get("wealth", 0))
            except KeyError:
                available_savings = 0
        facts["saved_gold"] = min(int(facts["saved_gold"]), max(0, available_savings))
        if isinstance(facts.get("building_cost"), dict):
            facts["requested_support"] = {**facts["building_cost"], "gold": max(0, int(facts["building_cost"].get("gold", 0)) - int(facts["saved_gold"]))}
    instance_id = _next_instance_id(state)
    for role, payload in generated.items():
        payload["components"]["provenance"]["created_by_story_event_id"] = instance_id
        payload["components"]["provenance"]["population_origin"]["materialized_by_event"] = instance_id
        character = create_character(state, payload)
        cast[role] = character["id"]
        snapshots[role]["id"] = character["id"]
    if isinstance(household_draft, dict):
        member_ids = [cast[role] for role in household_draft.get("member_roles", []) if cast.get(role)]
        household = create_household(state, {
            "member_ids": member_ids, "head_character_id": cast.get(household_draft.get("head_role", ""), ""),
            "class_id": household_draft.get("class_id", ""), "wealth": sum(int(get_character(state, member_id).get("components", {}).get("economy_agent", {}).get("wealth", 0)) for member_id in member_ids),
            "created_by_story_event_id": instance_id,
        })
        for member_id in member_ids:
            member = get_character(state, member_id)
            member["components"]["household"] = {"household_id": household["id"], "home_tile": household["home_tile"], "member_ids": member_ids, "dependent_ids": []}
        for relationship in relationship_drafts:
            create_relationship(state, {
                "from_character_id": cast.get(relationship["from_role"]), "to_character_id": cast.get(relationship["to_role"]),
                "type": relationship["type"], "strength": relationship.get("strength", 50), "source_story_event_id": instance_id,
            })
    chain_id = chain_id or _next_chain_id(state)
    chain = state["storylets"]["chains"].setdefault(chain_id, {
        "id": chain_id, "definition_id": definition_id, "status": "active", "facts": deepcopy(facts),
        "cast": deepcopy(cast), "cast_snapshots": deepcopy(snapshots), "completed_nodes": [], "obligations": [], "instance_ids": [],
    })
    chain["facts"] = {**chain.get("facts", {}), **deepcopy(facts)}
    chain["cast"] = {**chain.get("cast", {}), **deepcopy(cast)}
    chain["cast_snapshots"] = {**chain.get("cast_snapshots", {}), **deepcopy(snapshots)}
    instance = {
        "id": instance_id, "definition_id": definition_id, "node_key": node_key,
        "title": str(definition.get("title", definition_id)), "category": str(definition.get("category", "daily")),
        "chain_id": chain_id, "seed": int(seed), "status": "ready", "priority": definition.get("priority", "major"),
        "blocking": bool(definition.get("blocking", True)), "scene_type": definition.get("scene_type", "daily"),
        "created_time": time_point_from_state(state), "activated_time": None, "resolved_time": None,
        "scheduled_event_id": None, "scene_id": None, "cast": deepcopy(cast), "cast_snapshots": deepcopy(snapshots),
        "facts": deepcopy(facts), "choice_ids": [str(choice["id"]) for choice in definition.get("choices", [])],
        "narrative_md": _render_narrative(definition, facts, snapshots), "narrative_source": "local_template",
        "selected_choice_id": None, "result": None, "followup_instance_ids": [], "version": 1,
        "created_at": _now(), "updated_at": _now(),
    }
    related_people = [value for value in cast.values() if value and not value.startswith("@")]
    scheduled = schedule_event(
        state, event_type="storylet_event", title=instance["title"], description_md=instance["narrative_md"],
        in_days=due_in_days, visibility="player", importance=4 if instance["priority"] == "major" else 2,
        related={"people": related_people, "tiles": [f"{facts.get('tile', {}).get('x')}:{facts.get('tile', {}).get('y')}"] if isinstance(facts.get("tile"), dict) else [], "buildings": [facts.get("building_id")] if facts.get("building_id") else []},
        flags={"story_event_id": instance_id, "story_chain_id": chain_id, "facts_frozen": True, "blocking": instance["blocking"], "participants": [{"role": role, **snapshot} for role, snapshot in snapshots.items()]},
        created_by="storylet_director",
    )
    instance["scheduled_event_id"] = scheduled["id"]
    state["storylets"]["instances"].append(instance)
    chain["instance_ids"].append(instance_id)
    for character_id in cast.values():
        if character_id == "player_lord":
            continue
        try:
            character = get_character(state, character_id)
        except KeyError:
            continue
        narrative = character.setdefault("components", {}).setdefault("narrative", {})
        if chain_id not in narrative.setdefault("active_chain_ids", []):
            narrative["active_chain_ids"].append(chain_id)
    return instance


def instantiate_storylet(
    state: dict[str, Any], definition_id: str, *, node_key: str = "petition", seed: int,
    focus_character_id: str | None = None, commit: bool = False,
) -> dict[str, Any]:
    detached = deepcopy(state)
    instance = _instantiate_on_state(detached, definition_id, node_key=node_key, seed=seed, focus_character_id=focus_character_id)
    if commit:
        state.clear(); state.update(detached)
        return public_instance(instance_by_id(state, instance["id"]), get_definition(definition_id, node_key))
    return {"commit": False, "instance": public_instance(instance, get_definition(definition_id, node_key)), "generated_characters": [snapshot for role, snapshot in instance["cast_snapshots"].items() if instance["cast"].get(role, "").startswith("@generated:")]}


def activate_storylet_for_event(state: dict[str, Any], scheduled_event: dict[str, Any]) -> dict[str, Any]:
    normalize_storylet_state(state)
    instance_id = str(scheduled_event.get("flags", {}).get("story_event_id", ""))
    instance = instance_by_id(state, instance_id)
    if instance.get("status") == "ready":
        instance["status"] = "awaiting_choice"
        instance["activated_time"] = time_point_from_state(state)
        instance["updated_at"] = _now()
        if instance.get("blocking"):
            state["storylets"]["current_instance_id"] = instance["id"]
        append_history_entry(
            state, title=f"剧情事件发生：{instance['title']}", summary_md=instance["narrative_md"],
            source="storylet", importance=4 if instance.get("priority") == "major" else 2,
            tags=["storylet", instance["definition_id"], instance["node_key"], "activated"],
            related={"people": list(instance.get("cast", {}).values()), "scheduled_events": [scheduled_event.get("id")], "storylet_chains": [instance["chain_id"]]}, created_by="storylet_director",
        )
    return instance


def _create_followup(state: dict[str, Any], parent: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    followup = _instantiate_on_state(
        state, parent["definition_id"], node_key=spec["node_key"], seed=int(parent["seed"]) + len(parent.get("followup_instance_ids", [])) + 1009,
        chain_id=parent["chain_id"], inherited_cast=parent["cast"], inherited_snapshots=parent["cast_snapshots"],
        inherited_facts=state["storylets"]["chains"][parent["chain_id"]].get("facts", {}), due_in_days=int(spec.get("in_days", 0)),
    )
    parent.setdefault("followup_instance_ids", []).append(followup["id"])
    return followup


def choose_storylet(state: dict[str, Any], instance_id: str, choice_id: str, *, actor: str = "player") -> dict[str, Any]:
    normalize_storylet_state(state)
    current = instance_by_id(state, instance_id)
    if current.get("status") == "resolved":
        if current.get("selected_choice_id") == choice_id:
            return {"idempotent": True, "instance": public_instance(current, get_definition(current["definition_id"], current["node_key"])), "events": []}
        raise HTTPException(409, "该事件已经选择了另一项裁断")
    if current.get("status") != "awaiting_choice":
        raise HTTPException(409, "该事件尚未激活或已不能选择")
    detached = deepcopy(state)
    instance = instance_by_id(detached, instance_id)
    definition = get_definition(instance["definition_id"], instance["node_key"])
    choice = next((item for item in definition.get("choices", []) if item.get("id") == choice_id), None)
    if choice is None or choice_id not in instance.get("choice_ids", []):
        raise HTTPException(422, "该选择不属于此事件")
    events, result, followup_specs = execute_effects(detached, instance, choice, actor=actor)
    for spec in followup_specs:
        followup = _create_followup(detached, instance, spec)
        result.setdefault("followup_instance_ids", []).append(followup["id"])
    if result.get("project_id"):
        chain = detached["storylets"]["chains"][instance["chain_id"]]
        chain["facts"]["project_id"] = result["project_id"]
        chain["facts"]["project_status"] = "active"
    instance["status"] = "resolved"; instance["selected_choice_id"] = choice_id; instance["result"] = result
    instance["resolved_time"] = time_point_from_state(detached); instance["updated_at"] = _now()
    chain = detached["storylets"]["chains"][instance["chain_id"]]
    if instance["node_key"] not in chain.setdefault("completed_nodes", []):
        chain["completed_nodes"].append(instance["node_key"])
    has_active_obligation = any(item.get("status") == "active" for item in chain.get("obligations", []))
    has_pending_project = bool(result.get("project_id")) or chain.get("facts", {}).get("project_status") == "active"
    if not followup_specs and not has_active_obligation and not has_pending_project:
        chain["status"] = "completed"
    resolve_event(detached, instance["scheduled_event_id"], result_md=f"选择：**{choice['label']}**\n\n{choice.get('description_md', '')}", outcome=result, resolved_by=actor)
    scene = detached.get("active_scene")
    if isinstance(scene, dict) and scene.get("flags", {}).get("story_event_id") == instance_id:
        scenes.end_scene(detached, summary=f"剧情事件已裁定：{choice['label']}", outcome={"story_event_id": instance_id, "choice_id": choice_id})
    if detached["storylets"].get("current_instance_id") == instance_id:
        detached["storylets"]["current_instance_id"] = None
    detached["storylets"]["cooldowns"][instance["definition_id"]] = int(detached.get("time", {}).get("calendar_day", 1)) + int(definition.get("cooldown_days", 45))
    detached["storylets"]["recent_template_ids"] = (detached["storylets"].get("recent_template_ids", []) + [instance["definition_id"]])[-10:]
    if instance.get("priority") == "major":
        primary_ids = {instance.get("cast", {}).get("petitioner")}
        for character_id in list(detached["storylets"]["recent_cast"]):
            if character_id not in primary_ids:
                detached["storylets"]["recent_cast"][character_id] = 0
        for character_id in primary_ids:
            if character_id:
                detached["storylets"]["recent_cast"][character_id] = int(detached["storylets"]["recent_cast"].get(character_id, 0)) + 1
    state.clear(); state.update(detached)
    return {"idempotent": False, "instance": public_instance(instance_by_id(state, instance_id), definition), "events": [event.model_dump() for event in events], "result": result}


def process_construction_followups(state: dict[str, Any], turn_events: list[Any]) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    completed = {str((event.data if hasattr(event, "data") else event.get("data", {})).get("project_id")) for event in turn_events if (event.kind if hasattr(event, "kind") else event.get("kind")) == "project_completed"}
    if not completed:
        return created
    normalize_storylet_state(state)
    for chain in state["storylets"]["chains"].values():
        if str(chain.get("facts", {}).get("project_id")) not in completed or "construction_completed" in chain.get("completed_nodes", []):
            continue
        chain["facts"]["project_status"] = "completed"
        parent_id = chain.get("instance_ids", [None])[0]
        if not parent_id:
            continue
        parent = instance_by_id(state, parent_id)
        followup = _create_followup(state, parent, {"node_key": "construction_completed", "in_days": 0})
        created.append(followup)
    return created


def list_storylets(state: dict[str, Any], *, status: str | None = None, chain_id: str | None = None, character_id: str | None = None) -> list[dict[str, Any]]:
    normalize_storylet_state(state)
    rows = state["storylets"]["instances"]
    if status: rows = [row for row in rows if row.get("status") == status]
    if chain_id: rows = [row for row in rows if row.get("chain_id") == chain_id]
    if character_id: rows = [row for row in rows if character_id in row.get("cast", {}).values()]
    return [public_instance(row, get_definition(row["definition_id"], row["node_key"])) for row in rows]


def current_storylet(state: dict[str, Any]) -> dict[str, Any] | None:
    normalize_storylet_state(state)
    instance_id = state["storylets"].get("current_instance_id")
    if not instance_id:
        return None
    instance = instance_by_id(state, instance_id)
    return public_instance(instance, get_definition(instance["definition_id"], instance["node_key"]))
