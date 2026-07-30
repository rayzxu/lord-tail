from __future__ import annotations

import random
from copy import deepcopy
from typing import Any, Iterable

from ..engine.time import advance_strategic_clock
from ..engine.types import TurnContext
from ..systems import construction, demographics, diplomacy, economy, events, military, weather
from .actions import execute_action, normalize_action
from .analysis import analyze_realm


def simulate_one_turn(state: dict[str, Any], action: dict[str, Any], *, seed: int = 0) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run official deterministic phase functions on a detached state copy."""
    working = deepcopy(state)
    working["changes"] = {key: 0 for key in working.get("resources", {})}
    workforce = working.setdefault("workforce", {"available": 0, "assigned": 0})
    workforce["available"] = int(working.get("resources", {}).get("population", 0) or 0)
    context = TurnContext(command="", actor="simulation", advance_calendar_days=int(working.get("time", {}).get("turn_days", 9) or 9))
    economy.produce_resources(working, context)
    simulated_action = normalize_action(action, actor="simulation")
    execute_action(working, simulated_action, context, enforce_slot=False, enforce_budget=False)
    construction.advance_projects(working, context)
    military.advance_training(working, context)
    military.apply_upkeep(working, context)
    diplomacy.run_diplomacy_phase(working, context)
    demographics.run_demographics_phase(working, context)
    weather.advance_weather(working, context, rng=random.Random(seed))
    economy.consume_population_food(working, context)
    economy.apply_building_maintenance(working, context)
    events.run_random_events(working, context, seed=seed)
    events.check_threshold_events(working, context)
    advance_strategic_clock(working, context)
    return working, [event.model_dump() for event in context.events]


def _state_summary(state: dict[str, Any]) -> dict[str, Any]:
    analysis = analyze_realm(state)
    return {
        "turn": state.get("turn", 1),
        "time": deepcopy(state.get("time", {})),
        "resources": deepcopy(state.get("resources", {})),
        "metrics": analysis["metrics"],
        "buildings": deepcopy(state.get("buildings", {})),
        "army": deepcopy(state.get("army", {})),
    }


def forecast(
    state: dict[str, Any],
    action_sequence: Iterable[dict[str, Any]],
    *,
    horizon: int = 3,
    seed: int = 0,
    scenarios: tuple[str, ...] = ("baseline",),
) -> dict[str, Any]:
    if scenarios != ("baseline",):
        raise ValueError("第一版预测器只支持 baseline 情景")
    working = deepcopy(state)
    actions = [normalize_action(item, actor="simulation") for item in action_sequence]
    turns: list[dict[str, Any]] = []
    for index in range(max(0, int(horizon))):
        action = actions[index] if index < len(actions) else {
            "type": "wait",
            "actor": "simulation",
            "tags": ["wait"],
            "payload": {"reason": "forecast_padding"},
        }
        working, turn_events = simulate_one_turn(working, action, seed=seed + index)
        turns.append({
            "offset": index + 1,
            "action": normalize_action(action, actor="simulation"),
            "summary": _state_summary(working),
            "risks": [
                event
                for event in turn_events
                if event.get("severity") in {"warning", "critical"} or event.get("kind") in {"food_depleted", "treasury_empty", "rebellion_risk"}
            ],
        })
    return {
        "horizon": max(0, int(horizon)),
        "seed": int(seed),
        "scenarios": list(scenarios),
        "initial": _state_summary(state),
        "turns": turns,
        "final": _state_summary(working),
    }
