from __future__ import annotations

from typing import Any

from ..catalog import BUILDINGS


def legal_build_tiles(state: dict[str, Any], building_id: str) -> list[dict[str, Any]]:
    building = BUILDINGS.get(building_id, {})
    required = set(building.get("requires", []))
    active_coords = {(int(p.get("x", 0)), int(p.get("y", 0))) for p in state.get("construction_queue", []) if p.get("status", "active") == "active"}
    rows = [
        {"x": int(tile["x"]), "y": int(tile["y"]), "kind": tile.get("kind"), "label": tile.get("label", "")}
        for tile in state.get("map", [])
        if tile.get("kind") in required and not tile.get("owner") and (int(tile.get("x", 0)), int(tile.get("y", 0))) not in active_coords
    ]
    return sorted(rows, key=lambda tile: (tile["y"], tile["x"]))


def evaluate_triggers(state: dict[str, Any], definition: dict[str, Any], *, chain_facts: dict[str, Any] | None = None) -> tuple[bool, dict[str, Any], list[str]]:
    triggers = definition.get("triggers", {})
    facts: dict[str, Any] = {}
    reasons: list[str] = []
    resources = state.get("resources", {})
    for key, minimum in triggers.get("resource_minimum", {}).items():
        if int(resources.get(key, 0)) < int(minimum):
            reasons.append(f"资源 {key} 低于 {minimum}")
    for key, maximum in triggers.get("resource_maximum", {}).items():
        if int(resources.get(key, 0)) > int(maximum):
            reasons.append(f"资源 {key} 高于 {maximum}")
    class_ids = list(triggers.get("population_class_any", []))
    if class_ids:
        classes = state.get("demographics", {}).get("classes", {})
        minimum = int(triggers.get("minimum_class_population", 1))
        matches = [class_id for class_id in class_ids if int(classes.get(class_id, {}).get("population", 0)) >= minimum]
        if not matches:
            reasons.append("没有满足人口数量的阶级")
        facts["eligible_classes"] = matches
    if triggers.get("season_any") and state.get("season") not in triggers["season_any"]:
        reasons.append("季节不匹配")
    if triggers.get("weather_any") and state.get("weather") not in triggers["weather_any"]:
        reasons.append("天气不匹配")
    directive = state.get("strategic_directive") if isinstance(state.get("strategic_directive"), dict) else {}
    if triggers.get("directive_any") and directive.get("proposal_id") not in triggers["directive_any"]:
        reasons.append("战略方针不匹配")
    if triggers.get("directive_domain_any") and directive.get("domain") not in triggers["directive_domain_any"]:
        reasons.append("战略领域不匹配")
    for building, minimum in triggers.get("building_count_minimum", {}).items():
        catalog_name = BUILDINGS.get(building, {}).get("name", building)
        if int(state.get("buildings", {}).get(catalog_name, 0)) < int(minimum):
            reasons.append(f"建筑 {building} 数量不足")
    army_size = sum(int(value) for value in state.get("army", {}).values())
    if triggers.get("army_size_minimum") is not None and army_size < int(triggers["army_size_minimum"]):
        reasons.append("军队规模不足")
    if triggers.get("military_readiness_below") is not None and int(state.get("army_status", {}).get("organization", 100)) >= int(triggers["military_readiness_below"]):
        reasons.append("军队组织度未低于阈值")
    relation_below = triggers.get("diplomacy_relation_below", {})
    if isinstance(relation_below, dict):
        for faction, threshold in relation_below.items():
            entry = state.get("diplomacy", {}).get(faction, {})
            relation = int(entry.get("relation", 0)) if isinstance(entry, dict) else 0
            if relation >= int(threshold):
                reasons.append(f"与 {faction} 的关系未低于阈值")
    if triggers.get("at_war"):
        factions = triggers["at_war"] if isinstance(triggers["at_war"], list) else list(state.get("diplomacy", {}))
        if not any((entry.get("at_war") if isinstance(entry, dict) else entry == "战争") for faction, entry in state.get("diplomacy", {}).items() if faction in factions):
            reasons.append("当前没有满足条件的战争")
    hook_any = set(triggers.get("character_hook_any", []))
    if hook_any and not any(hook_any & set(character.get("components", {}).get("narrative", {}).get("hooks", [])) for character in state.get("characters", {}).get("entries", [])):
        reasons.append("没有人物拥有要求的 narrative hook")
    relationship_types = set(triggers.get("relationship_exists", [])) if isinstance(triggers.get("relationship_exists"), list) else ({str(triggers["relationship_exists"])} if triggers.get("relationship_exists") else set())
    if relationship_types and not any(edge.get("status", "active") == "active" and edge.get("type") in relationship_types for edge in state.get("character_relationships", {}).get("edges", [])):
        reasons.append("没有要求的人物关系")
    history_tags = {str(tag) for entry in state.get("history", {}).get("entries", []) for tag in entry.get("tags", [])}
    required_tags = set(triggers.get("history_tag_any", []))
    if required_tags and not required_tags & history_tags:
        reasons.append("编年史中没有要求的标签")
    forbidden_tags = set(triggers.get("history_tag_none", []))
    if forbidden_tags & history_tags:
        reasons.append("编年史中存在排除标签")
    legal_ids: list[str] = []
    for building_id in triggers.get("requires_legal_building_any", []):
        building = BUILDINGS.get(building_id, {})
        workforce = state.get("workforce", {})
        idle = int(workforce.get("available", resources.get("population", 0))) - int(workforce.get("assigned", 0))
        non_gold_affordable = all(int(resources.get(key, 0)) >= int(value) for key, value in building.get("cost", {}).items() if key != "gold")
        if legal_build_tiles(state, building_id) and idle >= int(building.get("workforce", 0)) and non_gold_affordable:
            legal_ids.append(building_id)
    if triggers.get("requires_legal_building_any") and not legal_ids:
        reasons.append("没有合法建筑与地块")
    facts["legal_buildings"] = legal_ids
    for key, expected in triggers.get("chain_fact_equals", {}).items():
        if (chain_facts or {}).get(key) != expected:
            reasons.append(f"事件链事实 {key} 不匹配")
    return not reasons, facts, reasons
