from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..catalog import UNITS
from ..engine.mutations import can_pay, change_resource, pay, resolve_unit
from ..engine.types import TurnContext, TurnEvent

DEFAULT_ARMY_STATUS = {"organization": 100, "routed": False, "last_loss_ratio": 0.0}
STANCE_MODIFIERS = {
    # TODO: move stance modifiers to catalog/rules json when battle rules are data-driven.
    "cautious": {"attack": 0.90, "defense": 1.10, "player_casualties": 0.90, "enemy_casualties": 0.90},
    "balanced": {"attack": 1.00, "defense": 1.00, "player_casualties": 1.00, "enemy_casualties": 1.00},
    "aggressive": {"attack": 1.15, "defense": 0.90, "player_casualties": 1.15, "enemy_casualties": 1.10},
}


def _combat(unit_id: str) -> dict[str, Any]:
    unit = UNITS[unit_id]
    combat = unit.get("combat", {})
    power = float(combat.get("power", 1.0))
    return {
        "power": power,
        "defense": float(combat.get("defense", power)),
        "morale": float(combat.get("morale", 1.0)),
        "organization_damage": float(combat.get("organization_damage", 1.0)),
        "range": int(combat.get("range", 1)),
        "speed": float(combat.get("speed", 1.0)),
        "counters": dict(combat.get("counters", {})),
    }


def validate_unit_combat_catalog() -> None:
    for unit_id, unit in UNITS.items():
        combat = unit.get("combat", {})
        attack_range = int(combat.get("range", 1))
        speed = float(combat.get("speed", 1.0))
        counters = combat.get("counters", {})
        if attack_range < 1:
            raise ValueError(f"{unit_id}.combat.range 必须 >= 1")
        if speed <= 0:
            raise ValueError(f"{unit_id}.combat.speed 必须 > 0")
        if not isinstance(counters, dict):
            raise ValueError(f"{unit_id}.combat.counters 必须是对象")
        for target_id, multiplier in counters.items():
            if target_id not in UNITS:
                raise ValueError(f"{unit_id}.combat.counters 引用了未知兵种：{target_id}")
            if float(multiplier) <= 0:
                raise ValueError(f"{unit_id}.combat.counters.{target_id} 必须为正数")


def normalize_army_status(state: dict[str, Any]) -> dict[str, Any]:
    status = state.setdefault("army_status", dict(DEFAULT_ARMY_STATUS))
    status["organization"] = max(0, min(100, int(status.get("organization", 100))))
    status["routed"] = bool(status.get("routed", False))
    status["last_loss_ratio"] = float(status.get("last_loss_ratio", 0.0))
    state.setdefault("training_queue", [])
    state.setdefault("training_seq", 0)
    state.setdefault("battles", [])
    state.setdefault("battle_seq", 0)
    for unit_id in UNITS:
        state.setdefault("army", {}).setdefault(unit_id, 0)
    return status


def _next_battle_id(state: dict[str, Any]) -> str:
    state["battle_seq"] = int(state.get("battle_seq", 0)) + 1
    return f"battle_{state['battle_seq']}"


def _next_training_id(state: dict[str, Any]) -> str:
    state["training_seq"] = state.get("training_seq", 0) + 1
    return f"training_{state['training_seq']}"


def set_unit_count(state: dict[str, Any], unit_key_or_name: str, value: int) -> tuple[str, dict[str, Any]]:
    unit_id, unit = resolve_unit(unit_key_or_name)
    normalize_army_status(state)
    state["army"][unit_id] = max(0, int(value))
    return unit_id, unit


def start_training(state: dict[str, Any], unit_id: str, quantity: int, context: TurnContext) -> dict[str, Any]:
    unit = UNITS.get(unit_id)
    if unit is None:
        raise ValueError(f"未知兵种：{unit_id}")
    if not state["buildings"].get(unit["requires_building"], 0):
        raise ValueError(f"招募{unit['name']}需要先建成{unit['requires_building']}")
    quantity = max(1, min(int(quantity), 50))
    resources = state["resources"]
    if not can_pay(resources, unit["cost"], quantity):
        raise ValueError(f"资源或人口不足，无法招募 {quantity} 名{unit['name']}")
    pay(resources, state["changes"], unit["cost"], quantity)
    turns = max(1, int(unit.get("training_turns", 1)))
    project = {
        "id": _next_training_id(state),
        "unit_id": unit_id,
        "quantity": quantity,
        "remaining_turns": turns,
        "total_turns": turns,
        "started_turn": state["turn"],
    }
    state.setdefault("training_queue", []).append(project)
    context.events.append(TurnEvent(
        phase="player_action",
        kind="training_started",
        message=f"训练场接收了 {quantity} 名{unit['name']}，预计还需 {turns} 轮。",
        data={"training_id": project["id"], "unit_id": unit_id, "quantity": quantity, "turns": turns},
    ))
    return project


def advance_training(state: dict[str, Any], context: TurnContext) -> None:
    normalize_army_status(state)
    queue = state["training_queue"]
    if not queue:
        context.events.append(TurnEvent(phase="military", kind="training_noop", message="本轮没有正在训练的部队。"))
        return
    completed_ids: set[str] = set()
    for project in queue:
        if project.get("started_turn") == state["turn"]:
            continue
        project["remaining_turns"] -= 1
        if project["remaining_turns"] <= 0:
            unit_id = project["unit_id"]
            unit = UNITS[unit_id]
            state["army"][unit_id] = state["army"].get(unit_id, 0) + project["quantity"]
            completed_ids.add(project["id"])
            context.events.append(TurnEvent(
                phase="military",
                kind="training_completed",
                message=f"{project['quantity']} 名{unit['name']}完成训练，已编入军册。",
                data={"training_id": project["id"], "unit_id": unit_id, "quantity": project["quantity"]},
            ))
    if completed_ids:
        state["training_queue"] = [project for project in queue if project["id"] not in completed_ids]
    elif queue:
        context.events.append(TurnEvent(phase="military", kind="training_in_progress", message="训练仍在推进中。"))


def apply_upkeep(state: dict[str, Any], context: TurnContext) -> None:
    resources, changes = state["resources"], state["changes"]
    upkeep: dict[str, int] = {}
    for unit_id, unit in UNITS.items():
        count = state["army"].get(unit_id, 0)
        if not count:
            continue
        for resource, amount in unit["upkeep"].items():
            upkeep[resource] = upkeep.get(resource, 0) + amount * count
    shortage = any(resources.get(resource, 0) < amount for resource, amount in upkeep.items())
    for resource, amount in upkeep.items():
        change_resource(resources, changes, resource, -amount)
    if upkeep:
        context.events.append(TurnEvent(phase="military", kind="unit_upkeep", message="部队军饷已经结算。", data=upkeep))
        if shortage:
            change_organization(state, -10, "upkeep_shortage", context)
    else:
        context.events.append(TurnEvent(phase="military", kind="unit_upkeep_noop", message="本轮没有部队维持费。"))


def change_organization(state: dict[str, Any], delta: int, reason: str, context: Any) -> None:
    status = normalize_army_status(state)
    before = status["organization"]
    status["organization"] = max(0, min(100, before + int(delta)))
    if status["organization"] != before:
        context.events.append(TurnEvent(
            phase="military",
            kind="organization_changed",
            message=f"军队组织度变化 {status['organization'] - before:+d}。",
            data={"before": before, "after": status["organization"], "reason": reason},
        ))


def apply_organization_modifiers(base_attack: float, base_defense: float, organization: int) -> tuple[float, float]:
    if organization >= 60:
        return base_attack, base_defense
    if organization >= 30:
        return base_attack * 0.75, base_defense * 0.80
    if organization >= 1:
        return base_attack * 0.40, base_defense * 0.50
    return base_attack * 0.20, base_defense * 0.25


def unit_counter_multiplier(attacker_unit_id: str, defender_unit_id: str) -> float:
    if attacker_unit_id not in UNITS or defender_unit_id not in UNITS:
        return 1.0
    return float(_combat(attacker_unit_id)["counters"].get(defender_unit_id, 1.0))


def _weighted_average(units: dict[str, int], key: str, default: float) -> float:
    total = sum(max(0, int(count)) for count in units.values())
    if total <= 0:
        return default
    weighted = 0.0
    for unit_id, count in units.items():
        if unit_id not in UNITS or count <= 0:
            continue
        weighted += _combat(unit_id)[key] * count
    return weighted / total


def average_range(units: dict[str, int]) -> float:
    return _weighted_average(units, "range", 1.0)


def average_speed(units: dict[str, int]) -> float:
    return _weighted_average(units, "speed", 1.0)


def range_advantage_multiplier(attacker: dict[str, int], defender: dict[str, int]) -> float:
    if average_range(attacker) <= average_range(defender):
        return 1.0
    if average_speed(defender) >= average_speed(attacker) + 0.75:
        return 1.0
    return 1.10


def speed_casualty_modifier(winner: dict[str, int], loser: dict[str, int]) -> float:
    winner_speed = average_speed(winner)
    loser_speed = average_speed(loser)
    if winner_speed > loser_speed + 0.5:
        return 1.05
    if loser_speed > winner_speed + 0.5:
        return 0.95
    return 1.0


def validate_force(force: dict[str, int], *, field: str) -> dict[str, int]:
    if not isinstance(force, dict):
        raise ValueError(f"{field} 必须是兵种数量对象")
    normalized: dict[str, int] = {}
    for unit_id, raw_count in force.items():
        if unit_id not in UNITS:
            raise ValueError(f"{field} 包含未知兵种：{unit_id}")
        count = int(raw_count)
        if count <= 0:
            raise ValueError(f"{field}.{unit_id} 必须是正整数")
        normalized[unit_id] = count
    if not normalized:
        raise ValueError(f"{field} 不能为空")
    return normalized


def select_player_force(state: dict[str, Any], requested: dict[str, int] | None) -> dict[str, int]:
    normalize_army_status(state)
    available = {unit_id: int(count) for unit_id, count in state.get("army", {}).items() if int(count) > 0}
    if requested is None:
        return validate_force(available, field="player")
    selected = validate_force(requested, field="player")
    for unit_id, count in selected.items():
        if int(state.get("army", {}).get(unit_id, 0)) < count:
            raise ValueError(f"兵力不足：{unit_id} 可用 {state.get('army', {}).get(unit_id, 0)}，请求 {count}")
    return selected


def _countered_attack_power(attacker: dict[str, int], defender: dict[str, int]) -> float:
    total_defenders = sum(max(0, int(count)) for count in defender.values())
    power = 0.0
    for attacker_id, attacker_count in attacker.items():
        if attacker_id not in UNITS or attacker_count <= 0:
            continue
        if total_defenders:
            weighted_counter = sum(
                unit_counter_multiplier(attacker_id, defender_id) * defender_count
                for defender_id, defender_count in defender.items()
                if defender_count > 0
            ) / total_defenders
        else:
            weighted_counter = 1.0
        power += attacker_count * _combat(attacker_id)["power"] * weighted_counter
    return power


def _counter_breakdown(attacker: dict[str, int], defender: dict[str, int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for attacker_id, attacker_count in attacker.items():
        if attacker_id not in UNITS or attacker_count <= 0:
            continue
        for defender_id, defender_count in defender.items():
            if defender_id not in UNITS or defender_count <= 0:
                continue
            rows.append({
                "attacker_unit_id": attacker_id,
                "defender_unit_id": defender_id,
                "attacker_count": attacker_count,
                "defender_count": defender_count,
                "multiplier": unit_counter_multiplier(attacker_id, defender_id),
            })
    return rows


def _defense_power(units: dict[str, int]) -> float:
    return sum(count * _combat(unit_id)["defense"] for unit_id, count in units.items() if unit_id in UNITS and count > 0)


def _total_units(units: dict[str, int]) -> int:
    return sum(max(0, int(count)) for count in units.values())


def _casualty_count(total: int, ratio: float) -> int:
    if total <= 0 or ratio <= 0:
        return 0
    return min(total, max(1, round(total * ratio)))


def _apply_casualties(units: dict[str, int], casualties: int) -> dict[str, int]:
    remaining = dict(units)
    total = _total_units(remaining)
    if total <= 0 or casualties <= 0:
        return remaining
    assigned = 0
    unit_items = [(unit_id, count) for unit_id, count in remaining.items() if count > 0]
    for index, (unit_id, count) in enumerate(unit_items):
        if index == len(unit_items) - 1:
            loss = min(count, casualties - assigned)
        else:
            loss = min(count, round(casualties * (count / total)))
        remaining[unit_id] = max(0, count - loss)
        assigned += loss
    return remaining


def _distribute_casualties(units: dict[str, int], casualties: int) -> dict[str, dict[str, int]]:
    before = dict(units)
    remaining = _apply_casualties(before, casualties)
    losses = {unit_id: max(0, before.get(unit_id, 0) - remaining.get(unit_id, 0)) for unit_id in before}
    return {"remaining": remaining, "casualties_by_unit": losses}


def check_rout(state: dict[str, Any], battle_result: dict[str, Any], context: Any) -> None:
    status = normalize_army_status(state)
    casualties = int(battle_result.get("casualties", 0))
    total = max(1, int(battle_result.get("pre_battle_total_units", 0)))
    loss_ratio = casualties / total
    status["last_loss_ratio"] = loss_ratio
    if (status["organization"] < 25 and loss_ratio >= 0.15) or loss_ratio >= 0.35:
        status["routed"] = True
        status["organization"] = min(status["organization"], 10)
        context.events.append(TurnEvent(
            phase="military",
            kind="army_routed",
            severity="critical",
            message="军队承受不住损失，阵线溃散。",
            data={"loss_ratio": loss_ratio, "organization": status["organization"]},
        ))


def resolve_battle(state: dict[str, Any], battle_request: dict[str, Any], context: TurnContext) -> dict[str, Any]:
    apply_to_state = bool(battle_request.get("apply_to_state", True))
    if not apply_to_state:
        working = deepcopy(state)
        return _resolve_battle_in_place(working, battle_request, context, apply_to_state=False)
    return _resolve_battle_in_place(state, battle_request, context, apply_to_state=True)


def _resolve_battle_in_place(
    state: dict[str, Any],
    battle_request: dict[str, Any],
    context: TurnContext,
    *,
    apply_to_state: bool,
) -> dict[str, Any]:
    validate_unit_combat_catalog()
    status = normalize_army_status(state)
    player_units = select_player_force(state, battle_request.get("player"))
    enemy_units = validate_force(battle_request.get("enemy", {}), field="enemy")
    player_total = _total_units(player_units)
    enemy_total = _total_units(enemy_units)
    if player_total <= 0 or enemy_total <= 0:
        raise ValueError("战斗双方都必须有兵力")
    battle_id = _next_battle_id(state)
    terrain = str(battle_request.get("terrain") or "grass")
    stance = str(battle_request.get("stance") or "balanced")
    if stance not in STANCE_MODIFIERS:
        raise ValueError(f"未知战斗姿态：{stance}")
    stance_modifier = STANCE_MODIFIERS[stance]
    organization_before = int(status["organization"])
    routed_before = bool(status.get("routed", False))
    player_org = 0 if status.get("routed") else int(status["organization"])
    enemy_org = int(battle_request.get("enemy_organization", 100))
    player_attack, player_defense = apply_organization_modifiers(
        _countered_attack_power(player_units, enemy_units),
        _defense_power(player_units),
        player_org,
    )
    enemy_attack, enemy_defense = apply_organization_modifiers(
        _countered_attack_power(enemy_units, player_units),
        _defense_power(enemy_units),
        enemy_org,
    )
    player_range_multiplier = range_advantage_multiplier(player_units, enemy_units)
    enemy_range_multiplier = range_advantage_multiplier(enemy_units, player_units)
    player_attack *= player_range_multiplier * stance_modifier["attack"]
    player_defense *= stance_modifier["defense"]
    enemy_attack *= enemy_range_multiplier
    player_score = player_attack + player_defense
    enemy_score = enemy_attack + enemy_defense
    player_won = player_score >= enemy_score
    ratio = min(player_score, enemy_score) / max(player_score, enemy_score)
    loser_loss_ratio = min(0.65, 0.15 + (1 - ratio) * 0.35)
    winner_loss_ratio = min(0.35, 0.05 + ratio * 0.12)
    speed_modifier = speed_casualty_modifier(player_units, enemy_units) if player_won else speed_casualty_modifier(enemy_units, player_units)
    if player_won:
        player_casualties = _casualty_count(player_total, winner_loss_ratio * stance_modifier["player_casualties"])
        enemy_casualties = _casualty_count(enemy_total, loser_loss_ratio * speed_modifier * stance_modifier["enemy_casualties"])
    else:
        player_casualties = _casualty_count(player_total, loser_loss_ratio * speed_modifier * stance_modifier["player_casualties"])
        enemy_casualties = _casualty_count(enemy_total, winner_loss_ratio * stance_modifier["enemy_casualties"])
    player_casualties = min(player_total, max(0, player_casualties))
    enemy_casualties = min(enemy_total, max(0, enemy_casualties))
    player_distribution = _distribute_casualties(player_units, player_casualties)
    enemy_distribution = _distribute_casualties(enemy_units, enemy_casualties)
    if apply_to_state:
        state["army"].update(player_distribution["remaining"])
    result = {
        "id": battle_id,
        "winner": "player" if player_won else "enemy",
        "terrain": terrain,
        "stance": stance,
        "label": battle_request.get("label", ""),
        "notes": battle_request.get("notes", ""),
        "source": battle_request.get("source", "api"),
        "player_score": player_score,
        "enemy_score": enemy_score,
        "casualties": player_casualties,
        "enemy_casualties": enemy_casualties,
        "pre_battle_total_units": player_total,
        "player": {
            "before": dict(player_units),
            "after": dict(player_distribution["remaining"]),
            "casualties": player_casualties,
            "casualties_by_unit": dict(player_distribution["casualties_by_unit"]),
            "organization_before": organization_before,
            "organization_after": organization_before,
            "routed_before": routed_before,
            "routed": routed_before,
        },
        "enemy": {
            "before": dict(enemy_units),
            "after": dict(enemy_distribution["remaining"]),
            "casualties": enemy_casualties,
            "casualties_by_unit": dict(enemy_distribution["casualties_by_unit"]),
            "organization": enemy_org,
        },
        "modifiers": {
            "player_range_multiplier": player_range_multiplier,
            "enemy_range_multiplier": enemy_range_multiplier,
            "player_average_range": average_range(player_units),
            "enemy_average_range": average_range(enemy_units),
            "player_average_speed": average_speed(player_units),
            "enemy_average_speed": average_speed(enemy_units),
            "speed_casualty_modifier": speed_modifier,
            "initiative": "player" if average_speed(player_units) >= average_speed(enemy_units) else "enemy",
            "stance": stance_modifier,
            "counter_breakdown": _counter_breakdown(player_units, enemy_units),
            "enemy_counter_breakdown": _counter_breakdown(enemy_units, player_units),
        },
        "scores": {
            "player_attack": player_attack,
            "player_defense": player_defense,
            "enemy_attack": enemy_attack,
            "enemy_defense": enemy_defense,
            "player_score": player_score,
            "enemy_score": enemy_score,
        },
    }
    change_organization(state, -round((player_casualties / max(1, player_total)) * 100), "battle_losses", context)
    check_rout(state, result, context)
    result["player"]["organization_after"] = int(state["army_status"]["organization"])
    result["player"]["routed"] = bool(state["army_status"].get("routed", False))
    if apply_to_state:
        state.setdefault("battles", []).append(result)
    context.events.append(TurnEvent(
        phase="military",
        kind="battle_resolved",
        message="战斗已经结算。",
        data=result,
    ))
    return result
