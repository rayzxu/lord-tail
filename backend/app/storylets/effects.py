from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException

from ..engine.history import append_history_entry
from ..engine.types import TurnContext, TurnEvent
from ..systems import construction
from ..systems.characters import append_memory, get_character, patch_component
from .relationships import create_relationship, update_relationship


def _arc_state(state: dict[str, Any], instance: dict[str, Any]) -> dict[str, Any]:
    run_id = str(instance.get("arc_run_id") or instance.get("chain_id") or "")
    run = state.get("storylets", {}).get("arc_runs", {}).get(run_id)
    if isinstance(run, dict):
        return run
    chain = state.get("storylets", {}).get("chains", {}).get(run_id)
    if isinstance(chain, dict):
        return chain
    raise HTTPException(500, "剧情执行上下文缺少 Run")


def _character_for_role(state: dict[str, Any], instance: dict[str, Any], role: str) -> dict[str, Any]:
    character_id = instance.get("cast", {}).get(role)
    if not character_id or character_id == "player_lord":
        raise HTTPException(422, f"角色槽 {role} 没有 NPC")
    try:
        return get_character(state, character_id)
    except KeyError as exc:
        raise HTTPException(422, f"角色槽 {role} 的人物已经不存在") from exc


def _change_resource(state: dict[str, Any], key: str, delta: int) -> None:
    if key not in state.get("resources", {}):
        raise HTTPException(422, f"未知资源：{key}")
    after = int(state["resources"].get(key, 0)) + int(delta)
    if after < 0:
        raise HTTPException(422, f"资源不足：{key}")
    state["resources"][key] = after
    state.setdefault("changes", {})[key] = int(state.get("changes", {}).get(key, 0)) + int(delta)


def _start_construction(state: dict[str, Any], instance: dict[str, Any], events: list[TurnEvent]) -> dict[str, Any]:
    facts = instance["facts"]
    petitioner = _character_for_role(state, instance, "petitioner")
    economy = petitioner.setdefault("components", {}).setdefault("economy_agent", {"wealth": 0, "income": 0, "debts": []})
    contribution = min(max(0, int(economy.get("wealth", 0))), max(0, int(facts.get("saved_gold", 0))))
    if contribution:
        economy["wealth"] = int(economy.get("wealth", 0)) - contribution
        _change_resource(state, "gold", contribution)
    context = TurnContext(command="storylet construction", actor="storylet")
    tile = facts.get("tile", {})
    try:
        project = construction.start_project(state, str(facts["building_id"]), int(tile["x"]), int(tile["y"]), context)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f"建设后果无法执行：{exc}") from exc
    events.extend(context.events)
    return {"project_id": project["id"], "petitioner_contribution": contribution}


def _append_hook(character: dict[str, Any], hook: str) -> None:
    narrative = character.setdefault("components", {}).setdefault("narrative", {})
    hooks = narrative.setdefault("hooks", [])
    if hook and hook not in hooks:
        hooks.append(hook)


def execute_effects(state: dict[str, Any], instance: dict[str, Any], choice: dict[str, Any], *, actor: str) -> tuple[list[TurnEvent], dict[str, Any], list[dict[str, Any]]]:
    events: list[TurnEvent] = []
    result: dict[str, Any] = {"choice_id": choice["id"], "resource_changes": {}, "project_id": None, "obligations": []}
    followups: list[dict[str, Any]] = []
    for effect in choice.get("effects", []):
        op = effect.get("op")
        if op == "change_resources":
            for key, delta in effect.get("changes", {}).items():
                _change_resource(state, key, int(delta)); result["resource_changes"][key] = result["resource_changes"].get(key, 0) + int(delta)
        elif op == "change_resources_from_fact":
            multiplier = int(effect.get("multiplier", 1))
            for key, value in instance["facts"].get(str(effect.get("fact")), {}).items():
                delta = int(value) * multiplier; _change_resource(state, key, delta); result["resource_changes"][key] = result["resource_changes"].get(key, 0) + delta
        elif op == "change_morale":
            _change_resource(state, "morale", int(effect.get("delta", 0)))
        elif op == "change_authority":
            _change_resource(state, "authority", int(effect.get("delta", 0)))
        elif op == "start_construction_from_facts":
            details = _start_construction(state, instance, events); result.update(details)
        elif op == "append_character_memory":
            character = _character_for_role(state, instance, str(effect.get("role", "")))
            append_memory(state, character["id"], [f"{effect.get('text', '')} [{instance['id']}]"])
        elif op == "patch_character_component":
            character = _character_for_role(state, instance, str(effect.get("role", "")))
            patch_component(state, character["id"], str(effect.get("component_id", "")), deepcopy(effect.get("values", {})))
        elif op == "set_character_hook":
            _append_hook(_character_for_role(state, instance, str(effect.get("role", ""))), str(effect.get("hook", "")))
        elif op == "clear_character_hook":
            character = _character_for_role(state, instance, str(effect.get("role", "")))
            hooks = character.get("components", {}).get("narrative", {}).get("hooks", [])
            character["components"]["narrative"]["hooks"] = [value for value in hooks if value != effect.get("hook")]
        elif op == "create_relationship":
            first = instance.get("cast", {}).get(str(effect.get("from_role", "")))
            second = instance.get("cast", {}).get(str(effect.get("to_role", "")))
            create_relationship(state, {**effect, "from_character_id": first, "to_character_id": second, "source_story_event_id": instance["id"]})
        elif op == "update_relationship":
            update_relationship(state, str(effect.get("relationship_id", "")), effect)
        elif op == "create_obligation":
            debtor_role = str(effect.get("debtor_role", "petitioner"))
            debtor_id = "player_lord" if debtor_role == "player_lord" else instance.get("cast", {}).get(debtor_role)
            obligation = {
                "id": f"{instance['chain_id']}:{len(instance.get('obligations', [])) + len(result['obligations']) + 1}",
                "kind": str(effect.get("kind", "storylet_debt")), "debtor_id": debtor_id,
                "creditor_id": str(effect.get("creditor", "player_lord")),
                "amount_gold": int(instance["facts"].get("requested_support", {}).get("gold", 0)),
                "collateral": instance["facts"].get("collateral_variant"), "status": "active", "created_by": instance["id"],
            }
            chain = _arc_state(state, instance)
            chain.setdefault("obligations", []).append(obligation)
            result["obligations"].append(deepcopy(obligation))
            if debtor_id and debtor_id != "player_lord":
                character = get_character(state, debtor_id)
                character.setdefault("components", {}).setdefault("economy_agent", {"wealth": 0, "income": 0, "debts": []}).setdefault("debts", []).append(deepcopy(obligation))
                _append_hook(character, "building_debt")
        elif op == "settle_obligation":
            chain = _arc_state(state, instance)
            active = next((item for item in chain.get("obligations", []) if item.get("status") == "active"), None)
            if active:
                if not effect.get("forgiven") and active.get("debtor_id") != "player_lord":
                    debtor = get_character(state, active["debtor_id"])
                    economy = debtor.setdefault("components", {}).setdefault("economy_agent", {"wealth": 0, "income": 0, "debts": []})
                    paid = min(int(active.get("amount_gold", 0)), int(economy.get("wealth", 0)))
                    economy["wealth"] = int(economy.get("wealth", 0)) - paid
                    _change_resource(state, "gold", paid)
                    active["paid_gold"] = paid
                    active["status"] = "settled" if paid >= int(active.get("amount_gold", 0)) else "defaulted"
                else:
                    active["status"] = "forgiven" if effect.get("forgiven") else "settled"
                result["settled_obligation"] = deepcopy(active)
        elif op == "schedule_followup":
            followups.append({"node_key": str(effect.get("node_key", "")), "in_days": max(0, int(effect.get("in_days", 0)))})
        elif op == "set_arc_fact":
            key = str(effect.get("key", ""))
            if not key:
                raise HTTPException(422, "set_arc_fact 缺少 key")
            value = deepcopy(effect.get("value"))
            _arc_state(state, instance).setdefault("facts", {})[key] = value
            instance.setdefault("facts", {})[key] = deepcopy(value)
            result.setdefault("arc_fact_changes", {})[key] = value
        elif op == "increment_arc_fact":
            key = str(effect.get("key", ""))
            if not key:
                raise HTTPException(422, "increment_arc_fact 缺少 key")
            delta = int(effect.get("delta", 1))
            facts = _arc_state(state, instance).setdefault("facts", {})
            facts[key] = int(facts.get(key, 0)) + delta
            instance.setdefault("facts", {})[key] = facts[key]
            result.setdefault("arc_fact_changes", {})[key] = facts[key]
        elif op in {"resolve_entry_event", "schedule_series_occurrence"}:
            result.setdefault("runtime_effects", []).append(deepcopy(effect))
        elif op == "confiscate_saved_gold":
            character = _character_for_role(state, instance, str(effect.get("role", "petitioner")))
            economy = character.setdefault("components", {}).setdefault("economy_agent", {"wealth": 0, "income": 0, "debts": []})
            amount = min(int(economy.get("wealth", 0)), int(instance["facts"].get("saved_gold", 0)))
            economy["wealth"] = int(economy.get("wealth", 0)) - amount
            _change_resource(state, "gold", amount); result["resource_changes"]["gold"] = result["resource_changes"].get("gold", 0) + amount
        elif op == "append_history":
            entry = append_history_entry(
                state, title=f"剧情事件：{instance['title']}",
                summary_md=f"领主选择了 **{choice['label']}**。\n\n{choice.get('description_md', '')}",
                source="storylet", importance=4 if instance.get("priority") == "major" else 3,
                tags=["storylet", instance["definition_id"], instance["node_key"], choice["id"]],
                related={"people": list(instance.get("cast", {}).values()), "scheduled_events": [instance.get("scheduled_event_id")], "storylet_chains": [instance["chain_id"]]},
                created_by=actor,
            )
            result.setdefault("history_entry_ids", []).append(entry["id"])
        elif op == "emit_turn_event":
            events.append(TurnEvent(phase="storylet", kind=str(effect.get("kind", "storylet_effect")), message=str(effect.get("message", choice["label"])), data={"story_event_id": instance["id"]}))
        else:
            raise HTTPException(422, f"不支持的 Storylet effect：{op}")
    events.append(TurnEvent(phase="storylet", kind="storylet_choice_resolved", message=f"剧情事件已裁定：{choice['label']}", data={"story_event_id": instance["id"], "choice_id": choice["id"], "result": result}))
    return events, result, followups
