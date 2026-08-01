from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Query

from ..engine.state import mutation_result, require_state, result
from ..storylets.config import get_definition, load_arc_definitions, load_definitions
from ..storylets.director import run_director
from ..storylets.instances import instance_by_id, public_choice, public_instance
from ..storylets.relationships import relationships_for, create_relationship, update_relationship
from ..storylets.service import choose_storylet, current_storylet, instantiate_storylet, list_storylets, normalize_storylet_state
from ..storylets.runtime import choose_arc_node, current_arc, debug_arc_state, focused_arc_id, list_active_arcs, public_arc
from ..storylets.runs import definition_for_run, find_visit, public_visit, run_by_id, visit_by_id
from .schemas import RelationshipCreateRequest, RelationshipPatchRequest, StoryletChoiceRequest, StoryletDirectorRequest, StoryletPreviewRequest

router = APIRouter()


def _choice_narrative(payload: dict[str, Any], choice_id: str) -> str:
    rows = payload.get("transition_log", [])
    if not isinstance(rows, list) or not rows:
        return f"剧情事件已裁定：{choice_id}"
    return "\n\n---\n\n".join(str(row.get("narrative_md", "")) for row in rows if isinstance(row, dict) and row.get("narrative_md"))


@router.get("/story-arcs/current")
def story_arc_current() -> dict[str, Any]:
    state = require_state(); normalize_storylet_state(state)
    focused = focused_arc_id(state)
    return {"focused_arc_id": focused, "arc": current_arc(state), "active_arcs": list_active_arcs(state)}


@router.get("/story-arcs/debug")
def story_arc_debug() -> dict[str, Any]:
    state = require_state(); normalize_storylet_state(state)
    return debug_arc_state(state)


@router.get("/story-arcs/{chain_id}")
def story_arc_detail(chain_id: str) -> dict[str, Any]:
    state = require_state(); normalize_storylet_state(state)
    return public_arc(state, chain_id)


@router.get("/storylets/current")
def storylet_current() -> dict[str, Any]:
    state = require_state()
    return {"instance": current_storylet(state)}


@router.get("/storylets")
def storylet_list(status: str | None = None, chain_id: str | None = None, character_id: str | None = None) -> dict[str, Any]:
    state = require_state()
    rows = list_storylets(state, status=status, chain_id=chain_id, character_id=character_id)
    return {"instances": rows, "total": len(rows), "current_instance_id": state["storylets"].get("current_instance_id")}


@router.get("/storylets/{story_event_id}")
def storylet_detail(story_event_id: str) -> dict[str, Any]:
    state = require_state(); normalize_storylet_state(state)
    matched = find_visit(state, story_event_id)
    if matched:
        run, visit = matched
        node = definition_for_run(run)["nodes"][visit["node_id"]]
        return {"instance": public_visit(run, visit, node), "visit": deepcopy(visit), "run": public_arc(state, run["id"]), "chain": public_arc(state, run["id"])["chain"]}
    instance = instance_by_id(state, story_event_id)
    return {"instance": public_instance(instance, get_definition(instance["definition_id"], instance["node_key"])), "chain": deepcopy(state["storylets"]["chains"].get(instance["chain_id"], {}))}


@router.get("/storylets/{story_event_id}/choices")
def storylet_choices(story_event_id: str) -> dict[str, Any]:
    state = require_state(); normalize_storylet_state(state)
    matched = find_visit(state, story_event_id)
    if matched:
        run, visit = matched
        node = definition_for_run(run)["nodes"][visit["node_id"]]
        choices = public_visit(run, visit, node)["choices"]
        return {"choices": choices, "status": visit.get("status")}
    instance = instance_by_id(state, story_event_id)
    definition = get_definition(instance["definition_id"], instance["node_key"])
    allowed = set(instance.get("choice_ids", []))
    return {"choices": [public_choice(choice) for choice in definition.get("choices", []) if choice.get("id") in allowed], "status": instance.get("status")}


@router.post("/storylets/{story_event_id}/choose")
def storylet_choose(story_event_id: str, request: StoryletChoiceRequest) -> dict[str, Any]:
    state = require_state(); payload = choose_storylet(
        state, story_event_id, request.choice_id, actor=request.actor,
        expected_transition_seq=request.expected_transition_seq,
    )
    body = result(state, _choice_narrative(payload, request.choice_id), [], "state-api", payload.get("events", []))
    body.update(payload)
    return body


@router.post("/story-arcs/{run_id}/visits/{visit_id}/choose")
def story_arc_visit_choose(run_id: str, visit_id: str, request: StoryletChoiceRequest) -> dict[str, Any]:
    state = require_state(); normalize_storylet_state(state)
    payload = choose_arc_node(
        state, run_id, visit_id, request.choice_id, actor=request.actor,
        expected_transition_seq=request.expected_transition_seq,
    )
    body = result(state, _choice_narrative(payload, request.choice_id), [], "state-api", payload.get("events", []))
    body.update(payload)
    return body


@router.get("/characters/{character_id}/relationships")
def character_relationships(character_id: str) -> dict[str, Any]:
    rows = relationships_for(require_state(), character_id)
    return {"relationships": rows, "total": len(rows)}


@router.post("/state/characters/relationships")
def relationship_create(request: RelationshipCreateRequest) -> dict[str, Any]:
    state = require_state(); edge = create_relationship(state, request.model_dump())
    body = mutation_result(state, "人物关系已建立"); body["relationship"] = edge
    return body


@router.patch("/state/characters/relationships/{relationship_id}")
def relationship_patch(relationship_id: str, request: RelationshipPatchRequest) -> dict[str, Any]:
    state = require_state(); edge = update_relationship(state, relationship_id, request.model_dump(exclude_none=True))
    body = mutation_result(state, "人物关系已更新"); body["relationship"] = edge
    return body


@router.get("/households")
def household_list() -> dict[str, Any]:
    state = require_state(); normalize_storylet_state(state)
    return {"households": deepcopy(state["households"]["entries"]), "total": len(state["households"]["entries"])}


@router.get("/households/{household_id}")
def household_detail(household_id: str) -> dict[str, Any]:
    state = require_state(); normalize_storylet_state(state)
    for household in state["households"]["entries"]:
        if household.get("id") == household_id:
            return {"household": deepcopy(household)}
    from fastapi import HTTPException
    raise HTTPException(404, "未找到家庭")


@router.get("/debug/storylets/definitions")
def debug_definitions() -> dict[str, Any]:
    rows = [{key: value for key, value in definition.items() if not key.startswith("_")} for definition in load_definitions().values()]
    arcs = [{key: value for key, value in definition.items() if not key.startswith("_")} for definition in load_arc_definitions().values()]
    return {"definitions": rows, "story_arcs": arcs, "total": len(rows), "arc_total": len(arcs)}


@router.post("/debug/storylets/preview")
def debug_preview(request: StoryletPreviewRequest) -> dict[str, Any]:
    state = require_state()
    return instantiate_storylet(state, request.definition_id, node_key=request.node_key, seed=request.seed, focus_character_id=request.focus_character_id, commit=False)


@router.post("/debug/storylets/instantiate")
def debug_instantiate(request: StoryletPreviewRequest) -> dict[str, Any]:
    state = require_state()
    instance = instantiate_storylet(state, request.definition_id, node_key=request.node_key, seed=request.seed, focus_character_id=request.focus_character_id, commit=True)
    return {"instance": instance, "state": state}


@router.post("/debug/storylets/run-director")
def debug_director(request: StoryletDirectorRequest) -> dict[str, Any]:
    return run_director(require_state(), source_kind=request.source_kind, focus_character_id=request.focus_character_id, seed=request.seed, commit=request.commit)
