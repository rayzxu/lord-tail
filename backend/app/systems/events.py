from __future__ import annotations

import random
from typing import Any

from ..engine.mutations import change_resource
from ..engine.types import TurnContext, TurnEvent
from . import diplomacy, military


def apply_event_effect(state: dict[str, Any], event: TurnEvent, context: TurnContext) -> None:
    effect = event.data.get("effect", {})
    resources = state["resources"]
    changes = state["changes"]
    for resource, amount in effect.get("resources", {}).items():
        change_resource(resources, changes, resource, int(amount))
    if effect.get("organization"):
        military.change_organization(state, int(effect["organization"]), event.kind, context)


def run_random_events(state: dict[str, Any], context: TurnContext, seed: int | None = None) -> None:
    if seed is None:
        return
    rng = random.Random(seed)
    if rng.random() < 0.05:
        event = TurnEvent(
            phase="events",
            kind="minor_market_windfall",
            message="流动商队带来一笔小额市税。",
            data={"effect": {"resources": {"gold": 10}}},
        )
        apply_event_effect(state, event, context)
        context.events.append(event)


def check_threshold_events(state: dict[str, Any], context: TurnContext) -> None:
    resources = state["resources"]

    if resources.get("food", 0) <= 0:
        event = TurnEvent(
            phase="events",
            kind="food_depleted",
            severity="critical",
            message="粮仓见底，领民的不安开始蔓延。",
            data={"resource": "food", "amount": 0, "effect": {"resources": {"morale": -5}}},
        )
        apply_event_effect(state, event, context)
        context.events.append(event)

    if resources.get("gold", 0) <= 0:
        event = TurnEvent(
            phase="events",
            kind="treasury_empty",
            severity="warning",
            message="金库空虚，军饷与维护支出面临风险。",
            data={"resource": "gold", "amount": 0, "effect": {"organization": -5}},
        )
        apply_event_effect(state, event, context)
        context.events.append(event)

    if resources.get("morale", 0) < 25:
        context.events.append(TurnEvent(
            phase="events",
            kind="rebellion_risk",
            severity="critical",
            message="民心已经跌入危险区，叛乱风险正在上升。",
            data={"morale": resources.get("morale", 0), "threshold": 25},
        ))

    for faction, relation in diplomacy.normalize_diplomacy_state(state).items():
        if relation.get("relation", 0) < -60 and not relation.get("at_war", False):
            context.events.append(TurnEvent(
                phase="events",
                kind="war_warning",
                severity="warning",
                message=f"{faction} 的敌意接近战争边缘。",
                data={"faction": faction, "relation": relation.get("relation"), "threshold": -60},
            ))

    completed = [
        event.data
        for event in context.events
        if event.phase == "construction" and event.kind == "project_completed"
    ]
    for item in completed:
        context.events.append(TurnEvent(
            phase="events",
            kind="building_completed_effect",
            message=f"{item.get('building', '新建筑')}完工带动了领地秩序。",
            data={"building": item.get("building"), "project_id": item.get("project_id")},
        ))
