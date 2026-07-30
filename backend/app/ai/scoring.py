from __future__ import annotations

from typing import Any

from .analysis import analyze_realm


def _value(metrics: dict[str, Any], key: str, default: float = 0.0) -> float:
    raw = metrics.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def score_transition(
    before_state: dict[str, Any],
    after_state: dict[str, Any],
    action: dict[str, Any],
    directive: dict[str, Any],
) -> dict[str, Any]:
    before = analyze_realm(before_state)
    after = analyze_realm(after_state)
    bm, am = before["metrics"], after["metrics"]
    weights = directive.get("weights", {})

    food_before = _value(bm, "food_net_turn")
    food_after = _value(am, "food_net_turn")
    gold_before = _value(bm, "gold_net_turn")
    gold_after = _value(am, "gold_net_turn")
    morale_delta = _value(am, "morale") - _value(bm, "morale")
    defense_delta = _value(am, "defensive_power") - _value(bm, "defensive_power")
    relation_delta = _value(am, "average_relation") - _value(bm, "average_relation")
    housing_delta = _value(am, "housing_vacant") - _value(bm, "housing_vacant")
    employment_delta = _value(am, "employment_rate") - _value(bm, "employment_rate")

    survival = 0.0
    if _value(am, "food_net_turn") < 0:
        runway = am.get("food_runway_days")
        survival -= 25.0 if runway is not None and float(runway) < 18 else 4.0
    if _value(am, "gold_net_turn") < 0:
        runway = am.get("gold_runway_days")
        survival -= 18.0 if runway is not None and float(runway) < 18 else 2.0
    if _value(am, "morale") < 25:
        survival -= 15.0
    survival += max(-5.0, min(8.0, food_after - food_before))

    food_security = (food_after - food_before) * 0.7 + max(-2.0, min(4.0, housing_delta * 0.1))
    treasury = (gold_after - gold_before) * 0.6 + employment_delta * 8
    stability = morale_delta * 0.5 + housing_delta * 0.08
    defense = defense_delta * 0.5 + (_value(am, "military_readiness") - _value(bm, "military_readiness")) * 4
    diplomatic = relation_delta * 0.4 + (_value(bm, "war_risk") - _value(am, "war_risk")) * 8
    tag_weights = directive.get("action_tag_weights", {})
    tag_bonus = sum(float(tag_weights.get(tag, 0.0)) for tag in set(action.get("tags", [])))
    gold_cost = float(action.get("estimated_cost", {}).get("gold", 0) or 0)
    cost = -gold_cost / max(100.0, _value(before.get("resources", {}), "gold", 0) + 1) * 3
    wait_penalty = -0.5 if action.get("type") == "wait" and directive.get("domain") != "reserve" else 0.0

    breakdown = {
        "survival": survival * float(weights.get("survival", 1.0)),
        "food_security": food_security * float(weights.get("food_security", 1.0)),
        "treasury": treasury * float(weights.get("treasury", 1.0)),
        "stability": stability * float(weights.get("stability", 1.0)),
        "defense": defense * float(weights.get("defense", 1.0)),
        "diplomacy": diplomatic * float(weights.get("diplomacy", 1.0)),
        "directive_tags": tag_bonus,
        "cost": cost,
        "wait": wait_penalty,
    }
    failures: list[str] = []
    if int(after_state.get("resources", {}).get("food", 0) or 0) <= 0:
        failures.append("预测后粮食耗尽")
    if int(after_state.get("resources", {}).get("gold", 0) or 0) <= 0 and gold_after < 0:
        failures.append("预测后金库耗尽且仍在亏损")
    if _value(am, "at_war_count") > 0 and _value(am, "military_readiness") < 0.4:
        failures.append("战争状态下防务跌破最低安全线")
    total = sum(breakdown.values()) - len(failures) * 100
    return {
        "score": round(total, 4),
        "score_breakdown": {key: round(value, 4) for key, value in breakdown.items()},
        "hard_constraint_failures": failures,
        "legal": not failures,
        "before_metrics": bm,
        "after_metrics": am,
    }
