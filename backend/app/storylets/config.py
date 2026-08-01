from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..catalog import BUILDINGS, POPULATION_CLASSES, RESOURCES
from ..engine.scenes import VALID_SCENE_TYPES
from .graph import analyze_graph

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "storylets"
RESERVED_FILES = {"director.json", "character_generation.json", "wardrobe_templates.json"}
TRIGGER_OPS = {
    "resource_minimum", "resource_maximum", "population_class_any", "minimum_class_population",
    "season_any", "weather_any", "directive_any", "directive_domain_any", "building_count_minimum",
    "army_size_minimum", "military_readiness_below", "diplomacy_relation_below", "at_war",
    "character_hook_any", "relationship_exists", "history_tag_any", "history_tag_none",
    "requires_legal_building_any", "chain_fact_equals",
}
PARAMETER_GENERATORS = {"constant", "range", "weighted_values", "state_path_readonly", "from_trigger_result", "from_service", "character_component_readonly", "chain_fact_readonly"}
EFFECT_OPS = {
    "change_resources", "change_resources_from_fact", "change_morale", "change_authority",
    "start_construction_from_facts", "patch_character_component", "append_character_memory",
    "create_relationship", "update_relationship", "create_obligation", "settle_obligation",
    "set_character_hook", "clear_character_hook", "schedule_followup", "append_history",
    "emit_turn_event", "confiscate_saved_gold",
    "set_arc_fact", "increment_arc_fact", "resolve_entry_event", "schedule_series_occurrence",
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Storylet 配置无法读取：{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Storylet 配置根节点必须是对象：{path}")
    return value


@lru_cache(maxsize=1)
def load_director_config() -> dict[str, Any]:
    return _read_json(DATA_DIR / "director.json")


@lru_cache(maxsize=1)
def load_generation_config() -> dict[str, Any]:
    return _read_json(DATA_DIR / "character_generation.json")


@lru_cache(maxsize=1)
def load_wardrobe_config() -> dict[str, Any]:
    return _read_json(DATA_DIR / "wardrobe_templates.json")


@lru_cache(maxsize=1)
def load_definitions() -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(DATA_DIR.glob("*.json")):
        if path.name in RESERVED_FILES:
            continue
        document = _read_json(path)
        raw_nodes = document.get("nodes", {})
        if int(document.get("schema_version", 1)) == 2:
            if not isinstance(raw_nodes, dict):
                raise ValueError(f"{path}: schema v2 nodes 必须是对象")
            iterable = list(raw_nodes.items())
        else:
            if not isinstance(raw_nodes, list):
                raise ValueError(f"{path}: schema v1 nodes 必须是数组")
            iterable = [(str(raw.get("node_key", "")) if isinstance(raw, dict) else str(index), raw) for index, raw in enumerate(raw_nodes)]
        for index, (authored_node_id, raw) in enumerate(iterable):
            if not isinstance(raw, dict):
                raise ValueError(f"{path}: nodes[{index}] 必须是对象")
            if int(document.get("schema_version", 1)) == 2:
                node = {
                    "id": document.get("id"), "node_key": authored_node_id,
                    "title": raw.get("title", document.get("title", authored_node_id)),
                    "category": raw.get("category", document.get("category", "daily")),
                    "source_kind": "scheduled", "priority": raw.get("priority", document.get("priority", "major")),
                    "blocking": raw.get("blocking", raw.get("kind") in {"choice", "timed"}),
                    "scene_type": raw.get("scene_type", document.get("scene_type", "daily")),
                    "roles": raw.get("roles", document.get("roles", {})),
                    "parameters": raw.get("parameters", document.get("parameters", {})),
                    "triggers": raw.get("triggers", document.get("triggers", {})), "narrative_template_md": raw.get("narrative_template_md", ""),
                    "choices": raw.get("choices", []), "kind": raw.get("kind"), "effects": raw.get("effects", []),
                    "transitions": raw.get("transitions", []), "transition": raw.get("transition"),
                    "after_hours": raw.get("after_hours", 0), "after_days": raw.get("after_days", 0),
                    "interaction_budget": raw.get("interaction_budget", document.get("interaction_budget", {})),
                    "schema_version": 2, "_arc_definition_id": document.get("id"), "_arc_version": document.get("version", 1),
                }
            else:
                node = dict(raw)
            node["_source_file"] = path.name
            key = (str(node.get("id", "")), str(node.get("node_key", "")))
            if key in result:
                raise ValueError(f"重复 Storylet 节点：{key[0]}:{key[1]}")
            result[key] = node
    return result


@lru_cache(maxsize=1)
def load_arc_definitions() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(DATA_DIR.glob("*.json")):
        if path.name in RESERVED_FILES:
            continue
        document = _read_json(path)
        if int(document.get("schema_version", 1)) != 2:
            continue
        definition = dict(document)
        definition["_source_file"] = path.name
        definition_id = str(definition.get("id", ""))
        if definition_id in result:
            raise ValueError(f"重复 Story Arc definition：{definition_id}")
        result[definition_id] = definition
    return result


def get_arc_definition(definition_id: str) -> dict[str, Any]:
    try:
        return load_arc_definitions()[definition_id]
    except KeyError as exc:
        raise KeyError(f"未知 Story Arc：{definition_id}") from exc


def get_definition(definition_id: str, node_key: str = "petition") -> dict[str, Any]:
    try:
        return load_definitions()[(definition_id, node_key)]
    except KeyError as exc:
        raise KeyError(f"未知 Storylet 节点：{definition_id}:{node_key}") from exc


def validate_storylet_catalog() -> None:
    configs = [load_director_config(), load_generation_config(), load_wardrobe_config()]
    if any(int(item.get("schema_version", 0)) != 1 for item in configs):
        raise ValueError("Storylet 基础配置 schema_version 必须为 1")
    definitions = load_definitions()
    if not definitions:
        raise ValueError("至少需要一个 Storylet 定义")
    allowed_classes = set(POPULATION_CLASSES)
    for definition in load_arc_definitions().values():
        analyze_graph(definition, effect_ops=EFFECT_OPS, valid_scene_types=VALID_SCENE_TYPES)
    for (definition_id, node_key), node in definitions.items():
        label = f"{node.get('_source_file')}:{definition_id}:{node_key}"
        if not definition_id or not node_key:
            raise ValueError(f"{label}: id 和 node_key 不能为空")
        if node.get("priority") not in {"major", "minor"}:
            raise ValueError(f"{label}: priority 必须是 major/minor")
        if node.get("scene_type") not in VALID_SCENE_TYPES:
            raise ValueError(f"{label}: 未知 scene_type")
        triggers = node.get("triggers", {})
        unknown_triggers = set(triggers) - TRIGGER_OPS
        if unknown_triggers:
            raise ValueError(f"{label}: 未知 trigger {sorted(unknown_triggers)}")
        for class_id in triggers.get("population_class_any", []):
            if class_id not in allowed_classes:
                raise ValueError(f"{label}: 未知人口阶级 {class_id}")
        for building_id in triggers.get("requires_legal_building_any", []):
            if building_id not in BUILDINGS:
                raise ValueError(f"{label}: 未知建筑 {building_id}")
        for resource_id in [*triggers.get("resource_minimum", {}), *triggers.get("resource_maximum", {})]:
            if resource_id not in RESOURCES:
                raise ValueError(f"{label}: 未知资源 {resource_id}")
        for name, spec in node.get("parameters", {}).items():
            if not isinstance(spec, dict) or not (set(spec) & PARAMETER_GENERATORS):
                raise ValueError(f"{label}: 参数 {name} 没有合法生成器")
        choices = node.get("choices", [])
        if int(node.get("schema_version", 1)) == 2:
            continue
        ids = [str(item.get("id", "")) for item in choices if isinstance(item, dict)]
        if not ids or len(ids) != len(set(ids)) or any(not value for value in ids):
            raise ValueError(f"{label}: choice id 必须非空且唯一")
        for choice in choices:
            if not str(choice.get("description_md", "")):
                raise ValueError(f"{label}:{choice.get('id')}: 缺少 fallback 描述")
            for effect in choice.get("effects", []):
                if not isinstance(effect, dict) or effect.get("op") not in EFFECT_OPS:
                    raise ValueError(f"{label}:{choice.get('id')}: 未知 effect {effect}")
                if effect.get("op") == "schedule_followup":
                    target = (definition_id, str(effect.get("node_key", "")))
                    if target not in definitions:
                        raise ValueError(f"{label}: followup 节点不存在 {target[1]}")
