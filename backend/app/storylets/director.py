from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..engine.time import time_point_from_state
from .config import load_definitions, load_director_config
from .service import instantiate_storylet, normalize_storylet_state
from .triggers import evaluate_triggers


def select_storylet(state: dict[str, Any], *, source_kind: str = "realm", focus_character_id: str | None = None, seed: int) -> dict[str, Any]:
    normalize_storylet_state(state)
    current_day = int(state.get("time", {}).get("calendar_day", 1))
    rejected: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for (definition_id, node_key), definition in load_definitions().items():
        if definition.get("source_kind") != source_kind or node_key != "petition":
            continue
        reasons: list[str] = []
        cooldown_until = int(state["storylets"]["cooldowns"].get(definition_id, 0) or 0)
        if cooldown_until > current_day:
            reasons.append(f"冷却至第 {cooldown_until} 日")
        ok, facts, trigger_reasons = evaluate_triggers(state, definition)
        reasons.extend(trigger_reasons)
        if reasons or not ok:
            rejected.append({"definition_id": definition_id, "node_key": node_key, "reasons": reasons})
            continue
        score = int(definition.get("base_weight", 0))
        if definition_id not in state["storylets"].get("recent_template_ids", []):
            score += int(load_director_config().get("weights", {}).get("novelty", 10))
        candidates.append({"definition_id": definition_id, "node_key": node_key, "score": score, "trigger_facts": facts})
    candidates.sort(key=lambda item: (-item["score"], item["definition_id"], item["node_key"]))
    return {"selected": candidates[0] if candidates else None, "candidates": candidates, "rejected": rejected, "seed": seed, "focus_character_id": focus_character_id}


def run_director(state: dict[str, Any], *, source_kind: str = "realm", focus_character_id: str | None = None, seed: int | None = None, commit: bool = True) -> dict[str, Any]:
    normalize_storylet_state(state)
    director = state["storylets"]["director"]
    if not director.get("enabled", True):
        return {"selected": None, "rejected": [{"reason": "director_disabled"}]}
    if state.get("active_scene") or state.get("council", {}).get("current_meeting") or state["storylets"].get("current_instance_id"):
        return {"selected": None, "rejected": [{"reason": "blocking_state"}]}
    if any(item.get("blocking") and item.get("status") in {"ready", "active", "awaiting_choice"} for item in state["storylets"]["instances"]):
        return {"selected": None, "rejected": [{"reason": "blocking_storylet_exists"}]}
    resolved_seed = int(seed if seed is not None else director.get("seed", 2001)) + int(state.get("turn", 1))
    decision = select_storylet(state, source_kind=source_kind, focus_character_id=focus_character_id, seed=resolved_seed)
    director["last_run_time"] = time_point_from_state(state)
    director["last_decision"] = deepcopy(decision)
    if decision["selected"] and commit:
        selected = decision["selected"]
        instance = instantiate_storylet(state, selected["definition_id"], node_key=selected["node_key"], seed=resolved_seed, focus_character_id=focus_character_id, commit=True)
        decision["instance"] = instance
        state["storylets"]["director"]["last_decision"] = deepcopy(decision)
    return decision
