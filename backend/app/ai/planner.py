from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..catalog import BUILDINGS, UNITS
from .actions import legal_actions
from .config import load_council_policies
from .forecast import forecast, simulate_one_turn
from .scoring import score_transition


def _action_label(action: dict[str, Any]) -> str:
    payload = action.get("payload", {})
    if action.get("type") == "build":
        building = BUILDINGS.get(payload.get("building_id"), {})
        return f"在 {chr(64 + int(payload.get('x', 1)))}{payload.get('y')} 修建{building.get('name', payload.get('building_id'))}"
    if action.get("type") == "recruit":
        unit = UNITS.get(payload.get("unit_id"), {})
        return f"征募 {payload.get('quantity')} 名{unit.get('name', payload.get('unit_id'))}"
    if action.get("type") == "tax_policy":
        return "征收常例税"
    if action.get("type") == "send_envoy":
        return f"向{payload.get('faction_id')}派出{payload.get('mission_type')}使团"
    return "维持现状并积累储备"


def _candidate_view(action: dict[str, Any], score: dict[str, Any], sequence: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "action": deepcopy(action),
        "label": _action_label(action),
        "legal": score.get("legal", True),
        "score": score["score"],
        "score_breakdown": score["score_breakdown"],
        "hard_constraint_failures": score.get("hard_constraint_failures", []),
        "reason": _reason(action, score),
        "planned_sequence": [_action_label(item) for item in sequence],
    }


def _reason(action: dict[str, Any], score: dict[str, Any]) -> str:
    positive = sorted(
        ((key, value) for key, value in score.get("score_breakdown", {}).items() if value > 0),
        key=lambda row: -row[1],
    )
    factors = "、".join(key for key, _ in positive[:3]) or "保存储备"
    return f"{_action_label(action)}；主要依据：{factors}。"


def plan_management_action(
    state: dict[str, Any],
    directive: dict[str, Any],
    *,
    mode: str = "delegated",
    seed: int = 0,
) -> dict[str, Any]:
    config = load_council_policies()["planner"]
    depth = int(config["depth"])
    beam_width = int(config["beam_width"])
    expansion_limit = int(config["max_expansions_per_node"])
    root = deepcopy(state)
    beam: list[dict[str, Any]] = [{"state": root, "sequence": [], "score": 0.0, "first_score": None}]
    first_candidates: dict[str, dict[str, Any]] = {}

    for level in range(depth):
        expanded: list[dict[str, Any]] = []
        for node_index, node in enumerate(beam):
            actions = legal_actions(node["state"], directive=directive, actor="management_ai")[:expansion_limit]
            for action_index, action in enumerate(actions):
                try:
                    next_state, _ = simulate_one_turn(
                        node["state"],
                        action,
                        seed=seed + level * 1000 + node_index * 100 + action_index,
                    )
                except (TypeError, ValueError):
                    continue
                scored = score_transition(node["state"], next_state, action, directive)
                if not scored["legal"]:
                    continue
                sequence = node["sequence"] + [action]
                first_score = node["first_score"] or scored
                total = float(node["score"]) + float(scored["score"]) * (0.82 ** level)
                expanded.append({"state": next_state, "sequence": sequence, "score": total, "first_score": first_score})
                if level == 0:
                    first_candidates[action["action_id"]] = _candidate_view(action, scored, sequence)
        if not expanded:
            break
        expanded.sort(key=lambda item: (-item["score"], [action["action_id"] for action in item["sequence"]]))
        beam = expanded[:beam_width]

    if not beam or not beam[0]["sequence"]:
        fallback = legal_actions(root, directive=directive, actor="management_ai")[-1]
        next_state, _ = simulate_one_turn(root, fallback, seed=seed)
        scored = score_transition(root, next_state, fallback, directive)
        beam = [{"state": next_state, "sequence": [fallback], "score": scored["score"], "first_score": scored}]
        first_candidates[fallback["action_id"]] = _candidate_view(fallback, scored, [fallback])

    best = beam[0]
    best_action = best["sequence"][0]
    ordered_candidates = sorted(first_candidates.values(), key=lambda item: (-item["score"], item["action"]["action_id"]))
    advice_count = int(config["advice_count"])
    best_forecast = forecast(root, best["sequence"], horizon=depth, seed=seed)
    return {
        "id": f"decision:{directive.get('id', 'none')}:{state.get('turn', 1)}:{seed}",
        "mode": mode,
        "directive_id": directive.get("id"),
        "turn": int(state.get("turn", 1) or 1),
        "selected_action": deepcopy(best_action),
        "selected_label": _action_label(best_action),
        "reason": _reason(best_action, best["first_score"]),
        "score": round(float(best["score"]), 4),
        "score_breakdown": deepcopy(best["first_score"]["score_breakdown"]),
        "candidates": ordered_candidates[:advice_count],
        "planned_sequence": deepcopy(best["sequence"]),
        "planned_sequence_labels": [_action_label(item) for item in best["sequence"]],
        "forecast": best_forecast,
    }
