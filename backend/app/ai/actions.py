from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from fastapi import HTTPException

from ..catalog import BUILDINGS, BUILDINGS_BY_NAME, UNITS, UNITS_BY_NAME
from ..engine.mutations import can_pay, change_resource, pay, tile_at
from ..engine.types import TurnContext, TurnEvent
from ..systems import construction, diplomacy, military
from .config import load_council_policies

ACTION_TYPES = {"build", "recruit", "tax_policy", "send_envoy", "wait"}


def _building_tags(building_id: str, building: dict[str, Any]) -> list[str]:
    tags = {"construction"}
    production = set(building.get("production", {}))
    housing = building.get("housing")
    if production & {"food", "meat"}:
        tags.update({"food", "agriculture"})
    if production & {"gold", "service_income"}:
        tags.update({"treasury", "commerce"})
    if production & {"wood", "stone", "iron", "tools", "craft_goods", "leather"}:
        tags.add("production")
    if production & {"tools", "craft_goods"}:
        tags.add("craft")
    if housing:
        tags.add("housing")
    if building_id in {"wall", "castle", "barracks", "prison", "lord_dungeon"}:
        tags.update({"defense", "fortification"})
    if building_id == "barracks":
        tags.update({"military", "training"})
    if int(building.get("cost", {}).get("gold", 0) or 0) <= 70:
        tags.add("low_cost")
    if "stone" in production:
        tags.add("stone")
    return sorted(tags)


def _action_id(action: dict[str, Any]) -> str:
    action_type = action["type"]
    payload = action.get("payload", {})
    if action_type == "build":
        return f"build:{payload['building_id']}:{payload['x']}:{payload['y']}"
    if action_type == "recruit":
        return f"recruit:{payload['unit_id']}:{payload['quantity']}"
    if action_type == "tax_policy":
        return f"tax_policy:{payload['policy_id']}"
    if action_type == "send_envoy":
        return f"send_envoy:{payload['faction_id']}:{payload['mission_type']}"
    return f"wait:{payload.get('reason', 'reserve')}"


def normalize_action(raw: dict[str, Any], *, actor: str | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Action 必须是对象")
    action_type = str(raw.get("type") or "").strip()
    if action_type not in ACTION_TYPES:
        raise ValueError(f"未知战略行动类型：{action_type}")
    payload = deepcopy(raw.get("payload") if isinstance(raw.get("payload"), dict) else {})
    action = {
        "type": action_type,
        "actor": str(actor or raw.get("actor") or "player"),
        "tags": sorted({str(item) for item in raw.get("tags", []) if str(item)}),
        "payload": payload,
        "estimated_cost": deepcopy(raw.get("estimated_cost") if isinstance(raw.get("estimated_cost"), dict) else {}),
        "explanation_key": str(raw.get("explanation_key") or action_type),
    }
    action["action_id"] = str(raw.get("action_id") or _action_id(action))
    return action


def _available_workforce(state: dict[str, Any]) -> int:
    workforce = state.get("workforce", {})
    return int(workforce.get("available", state.get("resources", {}).get("population", 0)) or 0) - int(workforce.get("assigned", 0) or 0)


def validate_action(
    state: dict[str, Any],
    raw_action: dict[str, Any],
    *,
    directive: dict[str, Any] | None = None,
    enforce_budget: bool = False,
) -> dict[str, Any]:
    try:
        action = normalize_action(raw_action)
        payload = action["payload"]
        action_type = action["type"]
        cost: dict[str, int] = {}
        if action_type == "build":
            building_id = str(payload.get("building_id") or "")
            building = BUILDINGS.get(building_id)
            if not building:
                raise ValueError(f"未知建筑：{building_id}")
            x, y = int(payload.get("x", 0)), int(payload.get("y", 0))
            tile = tile_at(state, x, y)
            if tile is None:
                raise ValueError("建设坐标不在领地地图范围内")
            if tile.get("owner"):
                raise ValueError("该地块不属于领主直辖")
            if tile.get("kind") not in building.get("requires", []):
                raise ValueError(f"{building['name']}不能建在{tile.get('label', tile.get('kind'))}")
            if any(int(item.get("x", 0)) == x and int(item.get("y", 0)) == y for item in state.get("construction_queue", [])):
                raise ValueError("该地块已有在建工程")
            if _available_workforce(state) < int(building.get("workforce", 0)):
                raise ValueError("可用劳力不足")
            cost = {key: int(value) for key, value in building.get("cost", {}).items()}
            if not can_pay(state.get("resources", {}), cost):
                raise ValueError("资源不足")
        elif action_type == "recruit":
            unit_id = str(payload.get("unit_id") or "")
            unit = UNITS.get(unit_id)
            if not unit:
                raise ValueError(f"未知兵种：{unit_id}")
            quantity = int(payload.get("quantity", 0))
            if not 1 <= quantity <= 50:
                raise ValueError("征兵数量必须在 1..50")
            if not state.get("buildings", {}).get(unit.get("requires_building"), 0):
                raise ValueError(f"需要先建成{unit.get('requires_building')}")
            cost = {key: int(value) * quantity for key, value in unit.get("cost", {}).items()}
            if not can_pay(state.get("resources", {}), unit.get("cost", {}), quantity):
                raise ValueError("资源或人口不足")
        elif action_type == "tax_policy":
            policy_id = str(payload.get("policy_id") or "")
            rule = load_council_policies()["action_rules"]["tax_policies"].get(policy_id)
            if not rule:
                raise ValueError(f"未知税政：{policy_id}")
        elif action_type == "send_envoy":
            faction_id = str(payload.get("faction_id") or "")
            mission_type = str(payload.get("mission_type") or "")
            relation = state.get("diplomacy", {}).get(faction_id)
            info = state.get("factions", {}).get(faction_id, {})
            if relation is None or faction_id == state.get("realm_name") or (isinstance(info, dict) and info.get("is_player")):
                raise ValueError("非法外交目标")
            rule = load_council_policies()["action_rules"]["envoy_missions"].get(mission_type)
            if not rule:
                raise ValueError(f"未知使团任务：{mission_type}")
            relation_value = int(relation.get("relation", 0) if isinstance(relation, dict) else 0)
            if relation_value < int(rule.get("minimum_relation", -100)):
                raise ValueError("当前关系不足以执行该使团任务")
            if isinstance(relation, dict) and relation.get("at_war") and mission_type != "appease":
                raise ValueError("交战期间只能派遣缓和使团")
            cost = {key: int(value) for key, value in rule.get("cost", {}).items()}
            if not can_pay(state.get("resources", {}), cost):
                raise ValueError("使团费用不足")
        if enforce_budget and directive and cost.get("gold", 0):
            budget = directive.get("budget_limits", {})
            current_gold = int(state.get("resources", {}).get("gold", 0) or 0)
            minimum = int(budget.get("minimum_gold_reserve", 0) or 0)
            ratio = float(budget.get("gold_spend_ratio", 1.0) or 0)
            if cost["gold"] > current_gold * ratio or current_gold - cost["gold"] < minimum:
                raise ValueError("行动超出战略方针预算或最低金库储备")
        action["estimated_cost"] = cost
        return {"legal": True, "action": action, "errors": []}
    except HTTPException as error:
        return {"legal": False, "action": raw_action, "errors": [str(error.detail)]}
    except (KeyError, TypeError, ValueError) as error:
        return {"legal": False, "action": raw_action, "errors": [str(error)]}


def _best_build_tiles(state: dict[str, Any], building: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    center = (int(state.get("map_size", 10) or 10) + 1) / 2
    occupied = {(int(item.get("x", 0)), int(item.get("y", 0))) for item in state.get("construction_queue", [])}
    candidates = [
        tile
        for tile in state.get("map", [])
        if not tile.get("owner")
        and tile.get("kind") in building.get("requires", [])
        and (int(tile.get("x", 0)), int(tile.get("y", 0))) not in occupied
    ]
    candidates.sort(key=lambda tile: (abs(float(tile["x"]) - center) + abs(float(tile["y"]) - center), int(tile["y"]), int(tile["x"])))
    return candidates[:limit]


def _affordable_quantity(state: dict[str, Any], unit: dict[str, Any]) -> int:
    maximum = 50
    for resource, amount in unit.get("cost", {}).items():
        amount = int(amount)
        if amount > 0:
            maximum = min(maximum, int(state.get("resources", {}).get(resource, 0) or 0) // amount)
    return max(0, maximum)


def legal_actions(
    state: dict[str, Any],
    *,
    directive: dict[str, Any] | None = None,
    actor: str = "player",
) -> list[dict[str, Any]]:
    config = load_council_policies()
    planner = config["planner"]
    candidates: list[dict[str, Any]] = []
    for building_id, building in BUILDINGS.items():
        tags = _building_tags(building_id, building)
        for tile in _best_build_tiles(state, building, int(planner["max_build_coordinates"])):
            candidates.append(normalize_action({
                "type": "build",
                "actor": actor,
                "tags": tags,
                "payload": {"building_id": building_id, "x": tile["x"], "y": tile["y"]},
                "estimated_cost": building.get("cost", {}),
                "explanation_key": "build_capacity",
            }))
    for unit_id, unit in UNITS.items():
        maximum = _affordable_quantity(state, unit)
        quantities = sorted({*map(int, planner.get("recruit_quantities", [])), maximum})
        for quantity in quantities:
            if quantity <= 0:
                continue
            candidates.append(normalize_action({
                "type": "recruit",
                "actor": actor,
                "tags": ["military", "recruitment", "defense"],
                "payload": {"unit_id": unit_id, "quantity": quantity},
                "estimated_cost": {key: int(value) * quantity for key, value in unit.get("cost", {}).items()},
                "explanation_key": "recruit_force",
            }))
    for policy_id, rule in config["action_rules"]["tax_policies"].items():
        candidates.append(normalize_action({
            "type": "tax_policy",
            "actor": actor,
            "tags": rule.get("tags", []),
            "payload": {"policy_id": policy_id},
            "explanation_key": "raise_revenue",
        }))
    for faction_id, relation in state.get("diplomacy", {}).items():
        info = state.get("factions", {}).get(faction_id, {})
        if faction_id == state.get("realm_name") or (isinstance(info, dict) and info.get("is_player")):
            continue
        for mission_type, rule in config["action_rules"]["envoy_missions"].items():
            candidates.append(normalize_action({
                "type": "send_envoy",
                "actor": actor,
                "tags": rule.get("tags", []),
                "payload": {"faction_id": faction_id, "mission_type": mission_type},
                "estimated_cost": rule.get("cost", {}),
                "explanation_key": "send_envoy",
            }))
    allowed_tags = set(directive.get("allowed_action_tags", [])) if directive else set()
    legal: list[dict[str, Any]] = []
    for action in candidates:
        if allowed_tags and not (allowed_tags & set(action["tags"])):
            continue
        validation = validate_action(state, action, directive=directive, enforce_budget=actor == "management_ai")
        if validation["legal"]:
            legal.append(validation["action"])
    legal.sort(key=lambda item: (int(item.get("estimated_cost", {}).get("gold", 0)), item["action_id"]))
    wait = normalize_action({
        "type": "wait",
        "actor": actor,
        "tags": ["wait", "low_cost", "stability"],
        "payload": {"reason": "preserve_reserves"},
        "explanation_key": "wait_for_reserves",
    })
    maximum = max(1, int(planner["max_legal_actions"]))
    return legal[: max(0, maximum - 1)] + [wait]


def _claim_action_slot(state: dict[str, Any], action: dict[str, Any], actor: str) -> None:
    management = state.setdefault("management_ai", {})
    turn = int(state.get("turn", 1) or 1)
    current = management.get("action_slot")
    if isinstance(current, dict) and int(current.get("turn", -1)) == turn:
        raise ValueError(f"第 {turn} 轮的战略行动已经由 {current.get('actor', '未知来源')} 使用")
    management["action_slot"] = {"turn": turn, "action_id": action["action_id"], "actor": actor}


def execute_action(
    state: dict[str, Any],
    raw_action: dict[str, Any],
    context: TurnContext,
    *,
    directive: dict[str, Any] | None = None,
    enforce_slot: bool = True,
    enforce_budget: bool = False,
) -> list[TurnEvent]:
    validation = validate_action(state, raw_action, directive=directive, enforce_budget=enforce_budget)
    if not validation["legal"]:
        raise ValueError("；".join(validation["errors"]))
    action = validation["action"]
    actor = str(action.get("actor") or context.actor)
    before_count = len(context.events)
    if enforce_slot:
        _claim_action_slot(state, action, actor)
    payload = action["payload"]
    if action["type"] == "build":
        construction.start_project(state, payload["building_id"], int(payload["x"]), int(payload["y"]), context)
    elif action["type"] == "recruit":
        military.start_training(state, payload["unit_id"], int(payload["quantity"]), context)
    elif action["type"] == "tax_policy":
        rule = load_council_policies()["action_rules"]["tax_policies"][payload["policy_id"]]
        law_name = str(payload.get("decree_text") or rule["name"])[:120]
        change_resource(state["resources"], state["changes"], "gold", int(rule.get("gold", 0)))
        change_resource(state["resources"], state["changes"], "morale", int(rule.get("morale", 0)))
        state.setdefault("laws", []).append(law_name)
        context.events.append(TurnEvent(
            phase="player_action",
            kind="law_enacted",
            severity="warning",
            message=f"领主发布法令：{law_name}。",
            data={
                "law": law_name,
                "policy_id": payload["policy_id"],
                "gold": rule.get("gold", 0),
                "morale": rule.get("morale", 0),
            },
        ))
        context.events.append(TurnEvent(
            phase="player_action",
            kind="tax_income",
            message="新税令已经入账，市集上的交谈声随之低了下去。",
            data={"gold": rule.get("gold", 0), "morale": rule.get("morale", 0), "policy_id": payload["policy_id"]},
        ))
    elif action["type"] == "send_envoy":
        rule = load_council_policies()["action_rules"]["envoy_missions"][payload["mission_type"]]
        pay(state["resources"], state["changes"], rule.get("cost", {}))
        for resource, amount in rule.get("gain", {}).items():
            change_resource(state["resources"], state["changes"], resource, int(amount))
        diplomacy.change_relation(state, payload["faction_id"], int(rule.get("relation_delta", 0)), rule["name"], context)
        if rule.get("treaty"):
            diplomacy.add_treaty(
                state,
                payload["faction_id"],
                str(rule["treaty"]),
                int(rule.get("treaty_duration_turns", 1)),
                context,
            )
        context.events.append(TurnEvent(
            phase="player_action",
            kind="envoy_sent",
            message=f"使团已向{payload['faction_id']}出发，使命是{rule['name']}。",
            data={"faction_id": payload["faction_id"], "mission_type": payload["mission_type"]},
        ))
    else:
        context.events.append(TurnEvent(
            phase="player_action",
            kind="wait",
            message="本轮不另起高成本差事，账房保留了现有储备。",
            data={"reason": payload.get("reason", "preserve_reserves")},
        ))
    context.events.append(TurnEvent(
        phase="management_action",
        kind="structured_action_executed",
        message=f"战略行动已经执行：{action['action_id']}",
        data={"action": action, "actor": actor},
    ))
    return context.events[before_count:]


def parse_command_action(state: dict[str, Any], command: str, *, actor: str = "player") -> dict[str, Any] | None:
    text = command.strip()
    building = next((entry for name, entry in BUILDINGS_BY_NAME.items() if name in text), None)
    unit = next((entry for name, entry in UNITS_BY_NAME.items() if name in text), None)
    if building and any(word in text for word in ("建造", "修建", "建设")):
        match = re.search(r"\b([A-Xa-x])\s*(2[0-4]|1\d|[1-9])\b", text)
        if not match:
            raise ValueError("请指定建设坐标，例如：在 E4 建造农田")
        x = ord(match.group(1).upper()) - 64
        return normalize_action({
            "type": "build",
            "actor": actor,
            "tags": _building_tags(building["id"], building),
            "payload": {"building_id": building["id"], "x": x, "y": int(match.group(2))},
        })
    if unit and any(word in text for word in ("招募", "训练", "征召")):
        quantity_match = re.search(r"(\d+)\s*(?:名|个|队)?", text)
        quantity = int(quantity_match.group(1)) if quantity_match else 1
        return normalize_action({
            "type": "recruit",
            "actor": actor,
            "tags": ["military", "recruitment", "defense"],
            "payload": {"unit_id": unit["id"], "quantity": quantity},
        })
    if any(word in text for word in ("征税", "税令", "加税")):
        return normalize_action({
            "type": "tax_policy",
            "actor": actor,
            "tags": ["finance", "treasury", "tax"],
            "payload": {"policy_id": "standard_levy", "decree_text": text},
        })
    if "等待" in text or "维持现状" in text:
        return normalize_action({
            "type": "wait",
            "actor": actor,
            "tags": ["wait", "low_cost", "stability"],
            "payload": {"reason": "player_order"},
        })
    for faction in state.get("diplomacy", {}):
        if faction not in text:
            continue
        mission = "alliance" if "联盟" in text or "结盟" in text else "appease" if any(word in text for word in ("缓和", "赠礼", "停战")) else "trade"
        if any(word in text for word in ("外交", "使者", "使团", "贸易", "联盟", "结盟", "赠礼", "停战")):
            return normalize_action({
                "type": "send_envoy",
                "actor": actor,
                "tags": ["diplomacy", mission],
                "payload": {"faction_id": faction, "mission_type": mission},
            })
    return None
