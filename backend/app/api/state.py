from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..engine.history import append_history_entry, auto_record_turn_events, normalize_history, update_history_entry
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
from ..systems import characters, demographics, diplomacy, military, scheduled_events
from ..engine.types import TurnContext
from .schemas import (
    ArmyMutationRequest,
    BattleResolveRequest,
    BuildingMutationRequest,
    CharacterComponentPatchRequest,
    CharacterEquipItemRequest,
    CharacterItemGrantRequest,
    CharacterMemoryAppendRequest,
    CharacterPatchRequest,
    CharacterReproductiveContentRequest,
    CharacterReproductiveContentsClearExpiredRequest,
    CharacterSexualEncounterRequest,
    CharacterUnequipItemRequest,
    CharacterUpsertRequest,
    DiplomacyMutationRequest,
    HistoryEntryRequest,
    HistoryPatchRequest,
    ResourceMutationRequest,
    ScheduledEventCancelRequest,
    ScheduledEventRescheduleRequest,
    ScheduledEventResolveRequest,
    ScheduledEventScheduleRequest,
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


@router.get("/characters")
@router.get("/hermes/characters")
def characters_read(
    status: str | None = None,
    faction: str | None = None,
    include_inactive: bool = True,
) -> dict[str, Any]:
    state = require_state()
    entries = characters.list_characters(state, status=status, faction=faction, include_inactive=include_inactive)
    return {"characters": entries, "total": len(entries)}


@router.get("/characters/registry")
@router.get("/hermes/characters/registry")
def characters_registry() -> dict[str, Any]:
    return characters.character_registry()


@router.get("/characters/kinds")
@router.get("/hermes/characters/kinds")
def characters_kinds() -> dict[str, Any]:
    registry = characters.character_registry()
    return {"kinds": registry["kinds"], "components": registry["components"]}


@router.get("/items")
@router.get("/hermes/items")
def items_read() -> dict[str, Any]:
    return characters.public_items_catalog()


@router.get("/lord/components")
@router.get("/hermes/lord/components")
def lord_components_read() -> dict[str, Any]:
    state = require_state()
    return {"lord": characters.public_lord_components(state)}


@router.patch("/state/lord/components/{component_id}")
@router.patch("/hermes/lord/components/{component_id}")
def state_lord_component_patch(component_id: str, request: CharacterComponentPatchRequest) -> dict[str, Any]:
    if not component_id or "/" in component_id:
        raise HTTPException(422, "component_id 不合法")
    state = require_state()
    components = state.setdefault("lord_components", {})
    current = components.get(component_id)
    if not isinstance(current, dict):
        current = {}
    current.update(request.values)
    components[component_id] = current
    characters.normalize_lord_components(state)
    characters.refresh_realm_item_effects(state)
    body = mutation_result(state, f"领主组件已更新：{component_id}")
    body["lord"] = characters.public_lord_components(state)
    return body


@router.get("/characters/{character_id}")
@router.get("/hermes/characters/{character_id}")
def character_detail(character_id: str) -> dict[str, Any]:
    state = require_state()
    try:
        character = characters.get_character(state, character_id)
    except KeyError as error:
        raise HTTPException(404, "未找到人物") from error
    return {"character": characters.public_character_entry(character)}


@router.post("/state/characters")
@router.post("/hermes/characters")
def state_character_upsert(request: CharacterUpsertRequest) -> dict[str, Any]:
    state = require_state()
    character, created = characters.upsert_character(state, request.model_dump())
    body = mutation_result(state, f"人物账册已{'新增' if created else '更新'}：{character['name']}")
    body["character"] = characters.public_character_entry(character)
    body["created"] = created
    return body


@router.patch("/state/characters/{character_id}")
@router.patch("/hermes/characters/{character_id}")
def state_character_patch(character_id: str, request: CharacterPatchRequest) -> dict[str, Any]:
    state = require_state()
    try:
        character = characters.update_character(state, character_id, request.model_dump(exclude_none=True))
    except KeyError as error:
        raise HTTPException(404, "未找到人物") from error
    body = mutation_result(state, f"人物账册已更新：{character['name']}")
    body["character"] = characters.public_character_entry(character)
    return body


@router.post("/state/characters/{character_id}/memory")
@router.post("/hermes/characters/{character_id}/memory")
def state_character_memory_append(character_id: str, request: CharacterMemoryAppendRequest) -> dict[str, Any]:
    state = require_state()
    entries = list(request.entries)
    if request.entry:
        entries.append(request.entry)
    if not entries:
        raise HTTPException(422, "必须提供 entry 或 entries")
    try:
        character = characters.append_memory(state, character_id, entries)
    except KeyError as error:
        raise HTTPException(404, "未找到人物") from error
    body = mutation_result(state, f"人物记忆已追加：{character['name']}")
    body["character"] = characters.public_character_entry(character)
    return body


@router.patch("/state/characters/{character_id}/components/{component_id}")
@router.patch("/hermes/characters/{character_id}/components/{component_id}")
def state_character_component_patch(character_id: str, component_id: str, request: CharacterComponentPatchRequest) -> dict[str, Any]:
    state = require_state()
    try:
        character = characters.patch_component(state, character_id, component_id, request.values)
    except KeyError as error:
        raise HTTPException(404, "未找到人物") from error
    body = mutation_result(state, f"人物组件已更新：{character['name']} / {component_id}")
    body["character"] = characters.public_character_entry(character)
    return body


@router.post("/state/lord/items")
@router.post("/hermes/lord/items")
def state_lord_item_grant(request: CharacterItemGrantRequest) -> dict[str, Any]:
    state = require_state()
    lord = characters.grant_item(state, "player_lord", request.item_id, request.quantity)
    body = mutation_result(state, "领主物品已入账。")
    body["lord"] = lord
    body["item_effects"] = state.get("item_effects", {})
    return body


@router.post("/state/lord/equipment/equip")
@router.post("/hermes/lord/equipment/equip")
def state_lord_item_equip(request: CharacterEquipItemRequest) -> dict[str, Any]:
    state = require_state()
    lord = characters.equip_item(state, "player_lord", request.item_id, request.slot, request.auto_add)
    body = mutation_result(state, "领主装备已更新。")
    body["lord"] = lord
    body["item_effects"] = state.get("item_effects", {})
    return body


@router.post("/state/lord/equipment/unequip")
@router.post("/hermes/lord/equipment/unequip")
def state_lord_item_unequip(request: CharacterUnequipItemRequest) -> dict[str, Any]:
    state = require_state()
    lord = characters.unequip_item(state, "player_lord", request.slot, request.item_id)
    body = mutation_result(state, "领主装备已卸下。")
    body["lord"] = lord
    body["item_effects"] = state.get("item_effects", {})
    return body


@router.post("/state/characters/{character_id}/items")
@router.post("/hermes/characters/{character_id}/items")
def state_character_item_grant(character_id: str, request: CharacterItemGrantRequest) -> dict[str, Any]:
    state = require_state()
    try:
        character = characters.grant_item(state, character_id, request.item_id, request.quantity)
    except KeyError as error:
        raise HTTPException(404, "未找到人物") from error
    body = mutation_result(state, f"人物物品已入账：{character['name']}")
    body["character"] = characters.public_character_entry(character)
    body["item_effects"] = state.get("item_effects", {})
    return body


@router.post("/state/characters/{character_id}/equipment/equip")
@router.post("/hermes/characters/{character_id}/equipment/equip")
def state_character_item_equip(character_id: str, request: CharacterEquipItemRequest) -> dict[str, Any]:
    state = require_state()
    try:
        character = characters.equip_item(state, character_id, request.item_id, request.slot, request.auto_add)
    except KeyError as error:
        raise HTTPException(404, "未找到人物") from error
    body = mutation_result(state, f"人物装备已更新：{character['name']}")
    body["character"] = characters.public_character_entry(character)
    body["item_effects"] = state.get("item_effects", {})
    return body


@router.post("/state/characters/{character_id}/equipment/unequip")
@router.post("/hermes/characters/{character_id}/equipment/unequip")
def state_character_item_unequip(character_id: str, request: CharacterUnequipItemRequest) -> dict[str, Any]:
    state = require_state()
    try:
        character = characters.unequip_item(state, character_id, request.slot, request.item_id)
    except KeyError as error:
        raise HTTPException(404, "未找到人物") from error
    body = mutation_result(state, f"人物装备已卸下：{character['name']}")
    body["character"] = characters.public_character_entry(character)
    body["item_effects"] = state.get("item_effects", {})
    return body


@router.post("/state/characters/{character_id}/sexual-encounters")
@router.post("/hermes/characters/{character_id}/sexual-encounters")
def state_character_sexual_encounter(character_id: str, request: CharacterSexualEncounterRequest) -> dict[str, Any]:
    state = require_state()
    try:
        character = characters.append_sexual_encounter(state, character_id, request.model_dump())
    except KeyError as error:
        raise HTTPException(404, "未找到人物") from error
    body = mutation_result(state, f"人物性经历统计已更新：{character['name']}")
    body["character"] = characters.public_character_entry(character)
    return body


@router.post("/state/characters/{character_id}/reproductive-contents")
@router.post("/hermes/characters/{character_id}/reproductive-contents")
def state_character_reproductive_content(character_id: str, request: CharacterReproductiveContentRequest) -> dict[str, Any]:
    state = require_state()
    try:
        character = characters.append_reproductive_content(state, character_id, request.model_dump())
    except KeyError as error:
        raise HTTPException(404, "未找到人物") from error
    body = mutation_result(state, f"人物内容物状态已更新：{character['name']}")
    body["character"] = characters.public_character_entry(character)
    return body


@router.post("/state/characters/{character_id}/reproductive-contents/clear-expired")
@router.post("/hermes/characters/{character_id}/reproductive-contents/clear-expired")
def state_character_reproductive_contents_clear_expired(
    character_id: str,
    request: CharacterReproductiveContentsClearExpiredRequest,
) -> dict[str, Any]:
    state = require_state()
    try:
        character, removed = characters.clear_expired_reproductive_contents(state, character_id, request.now)
    except KeyError as error:
        raise HTTPException(404, "未找到人物") from error
    body = mutation_result(state, f"人物过期内容物已清理：{character['name']}")
    body["character"] = characters.public_character_entry(character)
    body["removed"] = removed
    return body


@router.get("/history")
@router.get("/hermes/history")
def history_read(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tag: str | None = None,
    source: str | None = None,
    min_importance: int = Query(default=1, ge=1, le=5),
    visibility: str = "player",
) -> dict[str, Any]:
    state = require_state()
    normalize_history(state)
    entries = [
        entry
        for entry in state["history"]["entries"]
        if int(entry.get("importance", 0)) >= min_importance
        and (not tag or tag in entry.get("tags", []))
        and (not source or entry.get("source") == source)
        and (visibility == "all" or entry.get("visibility") == visibility)
    ]
    entries.sort(key=lambda entry: (int(entry.get("calendar_day", 0)), str(entry.get("clock_24", "")), entry.get("id", "")), reverse=True)
    return {"entries": entries[offset: offset + limit], "total": len(entries)}


@router.get("/history/{entry_id}")
@router.get("/hermes/history/{entry_id}")
def history_detail(entry_id: str) -> dict[str, Any]:
    state = require_state()
    normalize_history(state)
    for entry in state["history"]["entries"]:
        if entry["id"] == entry_id:
            return {"entry": entry}
    raise HTTPException(404, "未找到历史条目")


@router.get("/events")
@router.get("/hermes/events")
def scheduled_events_read(
    status: str | None = None,
    visibility: str = "player",
    limit: int = Query(default=50, ge=1, le=200),
    include_secret: bool = False,
) -> dict[str, Any]:
    state = require_state()
    scheduled_events.normalize_scheduled_events(state)
    entries = [
        event
        for event in state["scheduled_events"]["entries"]
        if (not status or event.get("status") == status)
        and (include_secret or visibility == "all" or event.get("visibility") == visibility)
    ]
    entries.sort(key=lambda event: (
        int(event.get("schedule", {}).get("due_time", {}).get("calendar_day", 0)),
        str(event.get("schedule", {}).get("due_time", {}).get("clock_24", "")),
        event.get("id", ""),
    ))
    return {
        "events": entries[:limit],
        "total": len(entries),
        "context": scheduled_events.event_context(state),
    }


@router.post("/state/history")
@router.post("/hermes/history")
def state_history(request: HistoryEntryRequest) -> dict[str, Any]:
    state = require_state()
    entry = append_history_entry(
        state,
        title=request.title,
        summary_md=request.summary_md,
        details_md=request.details_md,
        source=request.source,
        importance=request.importance,
        visibility=request.visibility,
        tags=request.tags,
        related=request.related,
        created_by=request.created_by,
    )
    state["last_history_entries_created"] = [entry]
    body = mutation_result(state, "书记官已将此事写入编年史。")
    body["history_entry"] = entry
    return body


@router.patch("/state/history/{entry_id}")
@router.patch("/hermes/history/{entry_id}")
def state_history_patch(entry_id: str, request: HistoryPatchRequest) -> dict[str, Any]:
    state = require_state()
    try:
        entry = update_history_entry(state, entry_id, request.model_dump(exclude_none=True))
    except KeyError as error:
        raise HTTPException(404, "未找到历史条目") from error
    state["last_history_entries_created"] = []
    body = mutation_result(state, "书记官已修订编年史。")
    body["history_entry"] = entry
    return body


@router.post("/state/events/schedule")
@router.post("/hermes/events/schedule")
def state_event_schedule(request: ScheduledEventScheduleRequest) -> dict[str, Any]:
    state = require_state()
    event = scheduled_events.schedule_event(
        state,
        event_type=request.event_type,
        title=request.title,
        description_md=request.description_md,
        due_time=request.due_time,
        in_days=request.in_days,
        in_hours=request.in_hours,
        in_minutes=request.in_minutes,
        clock_24=request.clock_24,
        visibility=request.visibility,
        importance=request.importance,
        related=request.related,
        conditions=request.conditions,
        flags=request.flags,
        created_by=request.created_by,
    )
    body = mutation_result(state, f"长期事件已安排：{event['title']}")
    body["scheduled_event"] = event
    return body


@router.post("/state/events/{event_id}/cancel")
@router.post("/hermes/events/{event_id}/cancel")
def state_event_cancel(event_id: str, request: ScheduledEventCancelRequest) -> dict[str, Any]:
    state = require_state()
    event = scheduled_events.cancel_event(state, event_id, reason_md=request.reason_md, cancelled_by=request.cancelled_by)
    body = mutation_result(state, f"长期事件已取消：{event['title']}")
    body["scheduled_event"] = event
    return body


@router.post("/state/events/{event_id}/reschedule")
@router.post("/hermes/events/{event_id}/reschedule")
def state_event_reschedule(event_id: str, request: ScheduledEventRescheduleRequest) -> dict[str, Any]:
    state = require_state()
    event = scheduled_events.reschedule_event(
        state,
        event_id,
        due_time=request.due_time,
        in_days=request.in_days,
        in_hours=request.in_hours,
        in_minutes=request.in_minutes,
        clock_24=request.clock_24,
        reason_md=request.reason_md,
    )
    body = mutation_result(state, f"长期事件已改期：{event['title']}")
    body["scheduled_event"] = event
    return body


@router.post("/state/events/{event_id}/resolve")
@router.post("/hermes/events/{event_id}/resolve")
def state_event_resolve(event_id: str, request: ScheduledEventResolveRequest) -> dict[str, Any]:
    state = require_state()
    event = scheduled_events.resolve_event(
        state,
        event_id,
        result_md=request.result_md,
        outcome=request.outcome,
        resolved_by=request.resolved_by,
    )
    body = mutation_result(state, f"长期事件已解决：{event['title']}")
    body["scheduled_event"] = event
    return body


@router.post("/state/events/check-due")
@router.post("/hermes/events/check-due")
def state_events_check_due() -> dict[str, Any]:
    state = require_state()
    events = scheduled_events.activate_due_events(state, source="api")
    return mutation_result(state, f"已检查到期事件：{len(events)} 件", events)


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
    auto_record_turn_events(state, context.events)
    body["history_entries_created"] = state.get("last_history_entries_created", [])
    body["battle_result"] = battle_result
    return body


@router.post("/state/diplomacy")
@router.post("/hermes/diplomacy")
def state_diplomacy(request: DiplomacyMutationRequest) -> dict[str, Any]:
    state = require_state()
    context = TurnContext(command=f"外交姿态变更：{request.faction} -> {request.status}", actor="api")
    diplomacy.set_stance(state, request.faction, request.status, context)
    auto_record_turn_events(state, context.events)
    return mutation_result(state, "状态接口已更新外交关系。", context.events)


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
