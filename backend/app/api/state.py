from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..engine.mutations import (
    apply_value_delta,
    change_resource,
    ensure_changes,
    ensure_resource_key,
    resolve_building,
    resolve_unit,
    set_resource,
    update_tile_for_building,
)
from ..engine.state import mutation_result, require_state
from ..systems import demographics, diplomacy, military
from ..engine.types import TurnContext
from .schemas import (
    ArmyMutationRequest,
    BattleResolveRequest,
    BuildingMutationRequest,
    DiplomacyMutationRequest,
    ResourceMutationRequest,
    ValueDeltaRequest,
)

router = APIRouter()


@router.get("/state")
@router.get("/hermes/state")
def state_read() -> dict[str, Any]:
    return {"state": require_state()}


@router.get("/demographics")
@router.get("/hermes/demographics")
def demographics_read() -> dict[str, Any]:
    state = require_state()
    demographics.normalize_demographics(state)
    return {"demographics": state["demographics"]}


@router.post("/state/resources")
@router.post("/hermes/resources")
def state_resources(request: ResourceMutationRequest) -> dict[str, Any]:
    state = require_state()
    for resource, value in request.values.items():
        if resource == "population":
            old_population = int(state["resources"].get("population", 0))
            demographics.set_total_population(state, value)
            new_population = int(state["resources"].get("population", 0))
            state.setdefault("changes", {})["population"] = state.setdefault("changes", {}).get("population", 0) + new_population - old_population
            continue
        set_resource(state, resource, value)
    for resource, delta in request.changes.items():
        if resource == "population":
            old_population = int(state["resources"].get("population", 0))
            demographics.change_total_population(state, delta)
            new_population = int(state["resources"].get("population", 0))
            state.setdefault("changes", {})["population"] = state.setdefault("changes", {}).get("population", 0) + new_population - old_population
            continue
        ensure_resource_key(resource)
        change_resource(state["resources"], ensure_changes(state), resource, delta)
    return mutation_result(state, "状态接口已更新资源。")


@router.post("/state/population")
@router.post("/hermes/population")
def state_population(request: ValueDeltaRequest) -> dict[str, Any]:
    state = require_state()
    if request.value is None and request.delta is None:
        raise HTTPException(422, "必须提供 value 或 delta")
    old_population = int(state["resources"].get("population", 0))
    if request.value is not None:
        demographics.set_total_population(state, request.value)
    if request.delta is not None:
        demographics.change_total_population(state, request.delta)
    new_population = int(state["resources"].get("population", 0))
    state.setdefault("changes", {})["population"] = state.setdefault("changes", {}).get("population", 0) + new_population - old_population
    return mutation_result(state, "状态接口已更新人口。")


@router.post("/state/morale")
@router.post("/hermes/morale")
def state_morale(request: ValueDeltaRequest) -> dict[str, Any]:
    state = require_state()
    apply_value_delta(state, "morale", request)
    return mutation_result(state, "状态接口已更新民心。")


@router.post("/state/army")
@router.post("/hermes/army")
def state_army(request: ArmyMutationRequest) -> dict[str, Any]:
    state = require_state()
    unit_id, unit = resolve_unit(request.unit)
    current = int(state["army"].get(unit_id, 0))
    if request.value is None and request.delta is None:
        raise HTTPException(422, "必须提供 value 或 delta")
    if request.value is not None:
        current = request.value
    if request.delta is not None:
        current += request.delta
    military.set_unit_count(state, unit_id, current)
    return mutation_result(state, f"状态接口已更新{unit['name']}。")


@router.post("/state/battles/resolve")
@router.post("/hermes/battles/resolve")
def state_battle_resolve(request: BattleResolveRequest) -> dict[str, Any]:
    state = require_state()
    context = TurnContext(command=request.label or "battle_resolve", actor=request.source)
    try:
        battle_result = military.resolve_battle(state, request.model_dump(), context)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    body = mutation_result(state, "战斗已经结算。", context.events)
    body["battle_result"] = battle_result
    return body


@router.post("/state/diplomacy")
@router.post("/hermes/diplomacy")
def state_diplomacy(request: DiplomacyMutationRequest) -> dict[str, Any]:
    state = require_state()
    diplomacy.set_stance(state, request.faction, request.status)
    return mutation_result(state, "状态接口已更新外交关系。")


@router.get("/state/diplomacy")
@router.get("/hermes/diplomacy")
def state_diplomacy_read() -> dict[str, Any]:
    state = require_state()
    return {"factions": diplomacy.faction_detail(state)}


@router.post("/state/buildings")
@router.post("/hermes/buildings")
def state_buildings(request: BuildingMutationRequest) -> dict[str, Any]:
    state = require_state()
    _, building = resolve_building(request.building)
    name = building["name"]
    current = int(state["buildings"].get(name, 0))
    if request.action == "build":
        state["buildings"][name] = current + request.count
        update_tile_for_building(state, building, request.x, request.y)
        demographics.recalculate_housing(state)
        return mutation_result(state, f"状态接口已建立{name}。")
    state["buildings"][name] = max(0, current - request.count)
    update_tile_for_building(state, building, request.x, request.y, destroy=True)
    demographics.recalculate_housing(state)
    return mutation_result(state, f"状态接口已摧毁{name}。")
