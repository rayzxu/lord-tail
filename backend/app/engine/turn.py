from __future__ import annotations

import random
import re
from copy import deepcopy
from typing import Any

from ..catalog import UNITS_BY_NAME, BUILDINGS_BY_NAME
from ..systems import construction, demographics, diplomacy, economy, events, military
from .commands import command_coordinate, first_mentioned
from .mutations import change_resource
from .narrative import events_to_report, serialize_events, suggest_next_actions
from .time import advance_strategic_clock
from .types import TurnContext, TurnEvent

WEATHER_CHOICES = ["薄雾", "阴云", "细雨", "晴朗"]
DEFAULT_SUGGESTIONS = ["在 E4 建造农田", "在 B2 建造伐木场", "在 F4 建造训练场"]


def run_start_turn(state: dict[str, Any], context: TurnContext) -> None:
    state["changes"] = {key: 0 for key in state["resources"]}
    workforce = state.setdefault("workforce", {"available": 0, "assigned": 0})
    workforce["available"] = state["resources"].get("population", 0)
    military.normalize_army_status(state)
    diplomacy.normalize_diplomacy_state(state)
    demographics.normalize_demographics(state)
    context.events.append(TurnEvent(phase="start_turn", kind="prepared", message=f"第 {state['turn']} 轮的结算开始。"))


def run_income(state: dict[str, Any], context: TurnContext) -> None:
    economy.produce_resources(state, context)


def run_player_action(state: dict[str, Any], context: TurnContext) -> None:
    command = context.command
    resources, changes = state["resources"], state["changes"]
    building = first_mentioned(BUILDINGS_BY_NAME, command)
    unit = first_mentioned(UNITS_BY_NAME, command)
    if building and any(word in command for word in ["建造", "修建", "建设"]):
        coordinate = command_coordinate(command)
        if coordinate is None:
            raise ValueError("请指定建设坐标，例如：在 E4 建造农田")
        construction.start_project(state, building["id"], coordinate[0], coordinate[1], context)
        return
    if unit and any(word in command for word in ["招募", "训练", "征召"]):
        quantity_match = re.search(r"(\d+)\s*(?:名|个|队)?", command)
        quantity = int(quantity_match.group(1)) if quantity_match else 1
        military.start_training(state, unit["id"], quantity, context)
        return
    if any(word in command for word in ["贸易", "外交", "使者"]):
        change_resource(resources, changes, "gold", 30)
        change_resource(resources, changes, "food", -20)
        message = "使者带回一纸谨慎的贸易意向，以及一袋足以安抚账房的硬币。"
        context.events.append(TurnEvent(phase="player_action", kind="trade", message=message, data={"gold": 30, "food": -20}))
        return
    if any(word in command for word in ["税", "法令", "律"]):
        economy.apply_tax_income(state, context)
        state["laws"].append(command[:42])
        return
    context.events.append(TurnEvent(phase="player_action", kind="noop", message="领地的书记官记录下了这项命令。"))


def run_construction(state: dict[str, Any], context: TurnContext) -> None:
    construction.advance_projects(state, context)


def run_weather(state: dict[str, Any], context: TurnContext) -> None:
    state["weather"] = random.choice(WEATHER_CHOICES)
    context.events.append(TurnEvent(
        phase="weather",
        kind="changed",
        message=f"天气转为{state['weather']}。",
        data={"weather": state["weather"]},
    ))


def run_military(state: dict[str, Any], context: TurnContext) -> None:
    military.advance_training(state, context)
    military.apply_upkeep(state, context)


def run_diplomacy(state: dict[str, Any], context: TurnContext) -> None:
    diplomacy.run_diplomacy_phase(state, context)


def run_demographics(state: dict[str, Any], context: TurnContext) -> None:
    demographics.run_demographics_phase(state, context)


def run_expenditure(state: dict[str, Any], context: TurnContext) -> None:
    economy.consume_population_food(state, context)
    economy.apply_building_maintenance(state, context)


def run_events(state: dict[str, Any], context: TurnContext) -> None:
    events.run_random_events(state, context)
    events.check_threshold_events(state, context)


def run_end_turn(state: dict[str, Any], context: TurnContext) -> None:
    advance_strategic_clock(state, context, days=context.advance_calendar_days)


# 结算顺序：收入 -> 执行动作 -> 建筑 -> 军事 -> 外交 -> 人口/阶级经济 -> 天气 -> 支出 -> 事件。
TURN_PHASES = [
    run_start_turn,
    run_income,
    run_player_action,
    run_construction,
    run_military,
    run_diplomacy,
    run_demographics,
    run_weather,
    run_expenditure,
    run_events,
    run_end_turn,
]


def build_narrative(context: TurnContext) -> str:
    return events_to_report(context.events)


def run_strategic_turn(
    state: dict[str, Any],
    command: str,
    *,
    actor: str = "player",
    advance_calendar_days: int = 9,
) -> tuple[str, list[str], list[dict[str, Any]]]:
    working = deepcopy(state)
    context = TurnContext(command=command, actor=actor, advance_calendar_days=advance_calendar_days)
    for phase in TURN_PHASES:
        phase(working, context)
    narrative = build_narrative(context)
    context.suggestions = suggest_next_actions(working, context.events) or list(DEFAULT_SUGGESTIONS)
    state.clear()
    state.update(working)
    return narrative, context.suggestions, serialize_events(context.events)


def local_turn(state: dict[str, Any], command: str) -> tuple[str, list[str], list[dict[str, Any]]]:
    return run_strategic_turn(state, command)
