from __future__ import annotations

import random
from copy import deepcopy
from typing import Any

from fastapi import HTTPException

from ..systems.characters import create_character, list_characters
from .config import load_generation_config, load_wardrobe_config


def active_materialized_count(state: dict[str, Any], class_id: str) -> int:
    count = 0
    for character in list_characters(state, include_inactive=False):
        origin = character.get("components", {}).get("provenance", {}).get("population_origin", {})
        if origin.get("cohort_member") and origin.get("class_id") == class_id:
            count += 1
    return count


def materialization_capacity(state: dict[str, Any], class_id: str) -> int:
    population = int(state.get("demographics", {}).get("classes", {}).get(class_id, {}).get("population", 0))
    return max(0, population - active_materialized_count(state, class_id))


def character_draft_from_cohort(state: dict[str, Any], class_id: str, *, seed: int, story_event_id: str = "pending") -> dict[str, Any]:
    if materialization_capacity(state, class_id) <= 0:
        raise HTTPException(422, f"{class_id} 阶级没有可具名化人口")
    config = load_generation_config()
    profile = config.get("class_profiles", {}).get(class_id)
    if not isinstance(profile, dict):
        raise HTTPException(422, f"没有 {class_id} 的人物生成配置")
    rng = random.Random(seed)
    gender_id = "female" if rng.randrange(100) < 50 else "male"
    gender = "女" if gender_id == "female" else "男"
    names = config.get("names", {}).get(gender_id, [])
    name = str(names[rng.randrange(len(names))])
    age = rng.randint(18, 62)
    wealth_bands = profile.get("wealth_bands", ["poor"])
    wealth_band = str(wealth_bands[rng.randrange(len(wealth_bands))])
    axes = {key: rng.randint(20, 80) for key in ("ambition", "greed", "boldness", "loyalty", "compassion", "piety", "deceit")}
    archetypes = config.get("archetypes", ["commoner"])
    archetype = str(archetypes[rng.randrange(len(archetypes))])
    wardrobe_key = f"{class_id}_{wealth_band}"
    wardrobe_text = str(load_wardrobe_config().get("templates", {}).get(wardrobe_key, "朴素而经年磨损的衣物显示着此人的身份。"))
    class_state = state.get("demographics", {}).get("classes", {}).get(class_id, {})
    base_wealth = max(0, int(class_state.get("wealth_per_capita", 0)))
    return {
        "kind": profile.get("kind", "commoner"), "name": name, "role": profile.get("role", "领民"),
        "gender": gender, "age": age, "faction": state.get("realm_name", ""), "location": "领主直辖地",
        "status": "active", "appearance_md": wardrobe_text,
        "personality_md": f"{archetype}；野心 {axes['ambition']}，忠诚 {axes['loyalty']}。",
        "description_md": wardrobe_text, "traits": [archetype], "flags": {"adult": True, "storylet_generated": True},
        "components": {
            "social_identity": {"class_id": class_id, "legal_status": profile.get("legal_status", ""), "occupation_id": profile.get("occupation_id", ""), "reputation": rng.randint(0, 20)},
            "personality_axes": axes,
            "economy_agent": {"wealth": max(1, base_wealth * rng.randint(1, 4)), "income": 0, "debts": []},
            "narrative": {"goals": ["secure_household_future"], "hooks": [], "secrets": [], "recent_event_ids": [], "active_chain_ids": []},
            "wardrobe": {"template_id": wardrobe_key, "wealth_band": wealth_band, "season": "spring", "description_md": wardrobe_text},
            "provenance": {"generator_version": int(config.get("generator_version", 1)), "seed": seed, "archetype_id": archetype, "created_by_story_event_id": story_event_id, "population_origin": {"class_id": class_id, "cohort_member": True, "materialized_by_event": story_event_id}},
        },
    }


def materialize_character_from_cohort(state: dict[str, Any], class_id: str, *, seed: int, story_event_id: str) -> dict[str, Any]:
    return create_character(state, deepcopy(character_draft_from_cohort(state, class_id, seed=seed, story_event_id=story_event_id)))
