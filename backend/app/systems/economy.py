from __future__ import annotations

from typing import Any

from ..catalog import BUILDINGS
from ..engine.mutations import change_resource
from ..engine.talents import talent_effect, talent_multiplier
from ..engine.types import TurnContext, TurnEvent


def produce_resources(state: dict[str, Any], context: TurnContext) -> None:
    resources, changes = state["resources"], state["changes"]
    produced: dict[str, int] = {}
    consumed: dict[str, int] = {}
    shortages: dict[str, int] = {}
    for building_id, building in BUILDINGS.items():
        count = state["buildings"].get(building["name"], 0)
        if not count:
            continue
        production_multiplier = 1.0
        for resource, amount in building.get("consumption", {}).items():
            required = int(amount) * count
            available = resources.get(resource, 0)
            paid = min(available, required)
            if paid:
                change_resource(resources, changes, resource, -paid)
                consumed[resource] = consumed.get(resource, 0) + paid
            if paid < required:
                shortages[resource] = shortages.get(resource, 0) + required - paid
                production_multiplier = min(production_multiplier, 0.5)
        for resource, amount in building["production"].items():
            value = int(amount * count * production_multiplier * talent_effect(state, "production_multiplier", building_id))
            if value:
                change_resource(resources, changes, resource, value)
                produced[resource] = produced.get(resource, 0) + value
    if produced or consumed:
        context.events.append(TurnEvent(
            phase="income",
            kind="production",
            message="领地各处的产业完成了本轮投入与产出。",
            data={"produced": produced, "consumed": consumed, "shortages": shortages},
        ))
    elif shortages:
        context.events.append(TurnEvent(phase="income", kind="production_shortage", message="部分产业因原料短缺停摆。", data=shortages))
    else:
        context.events.append(TurnEvent(phase="income", kind="production_noop", message="本轮没有可结算的产出。"))


def consume_population_food(state: dict[str, Any], context: TurnContext) -> None:
    resources, changes = state["resources"], state["changes"]
    consumption = max(1, resources["population"] // 10)
    change_resource(resources, changes, "food", -consumption)
    context.events.append(TurnEvent(
        phase="expenditure",
        kind="population_consumption",
        message=f"领民消耗了 {consumption} 粮食。",
        data={"food": -consumption},
    ))


def apply_building_maintenance(state: dict[str, Any], context: TurnContext) -> None:
    resources, changes = state["resources"], state["changes"]
    totals: dict[str, int] = {}
    morale_delta = 0
    security_delta = 0
    for building_id, building in BUILDINGS.items():
        count = state["buildings"].get(building["name"], 0)
        if not count:
            continue
        for resource, amount in building.get("maintenance", {}).items():
            cost = amount * count
            if cost:
                change_resource(resources, changes, resource, -cost)
                totals[resource] = totals.get(resource, 0) - cost
        morale_delta += int(building.get("morale_effect", 0)) * count
        security_delta += int(building.get("security_effect", 0)) * count
    if morale_delta:
        change_resource(resources, changes, "morale", morale_delta)
        totals["morale"] = totals.get("morale", 0) + morale_delta
    if security_delta:
        change_resource(resources, changes, "security", security_delta)
        totals["security"] = totals.get("security", 0) + security_delta
    if totals:
        context.events.append(TurnEvent(phase="expenditure", kind="maintenance", message="建筑维护费用已经结算。", data=totals))
    else:
        context.events.append(TurnEvent(phase="expenditure", kind="maintenance_noop", message="本轮没有额外的建筑维护支出。"))


def apply_tax_income(state: dict[str, Any], context: TurnContext) -> None:
    resources, changes = state["resources"], state["changes"]
    multiplier = talent_multiplier(state, "tax_multiplier")
    gold = int(55 * multiplier)
    morale_penalty = -5
    change_resource(resources, changes, "gold", gold)
    change_resource(resources, changes, "morale", morale_penalty)
    context.events.append(TurnEvent(
        phase="player_action",
        kind="tax_income",
        message="新法令被钉上公告栏，市场的交谈声随之低了下去。",
        data={"gold": gold, "morale": morale_penalty},
    ))


def run_economy_phase(state: dict[str, Any], context: TurnContext) -> None:
    # 便于未来复用的聚合入口；当前 pipeline 按用户要求拆成 income/expenditure 两段，
    # 分别直接调用下面的细粒度函数，不经过这个聚合函数。
    produce_resources(state, context)
    consume_population_food(state, context)
    apply_building_maintenance(state, context)
