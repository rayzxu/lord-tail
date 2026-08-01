from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..catalog import RESOURCES
from ..engine.scenes import VALID_SCENE_TYPES
from ..storylets.config import EFFECT_OPS, PARAMETER_GENERATORS, TRIGGER_OPS
from ..storylets.graph import analyze_graph
from .character_config import load_anatomy, load_character_registry, load_equipment_slots
from .models import ValidationIssue
from .repository import get_document, list_documents, validate_content_identity


def _issue(code: str, message: str, path: str = "", *, severity: str = "error", suggestion: str = "") -> ValidationIssue:
    return ValidationIssue(code=code, message=message, path=path, severity=severity, suggestion=suggestion)


def _documents(content_type: str, candidate_id: str, candidate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {item["id"]: item["document"] for item in list_documents(content_type)}
    result[candidate_id] = candidate
    return result


def validate_document(content_type: str, content_id: str, document: dict[str, Any]) -> list[ValidationIssue]:
    validate_content_identity(content_type, content_id)
    issues: list[ValidationIssue] = []
    if not isinstance(document, dict):
        return [_issue("invalid_document", "内容根节点必须是对象")]
    if content_type in {"story_arc", "preset_character"} and str(document.get("id", "")) != content_id:
        issues.append(_issue("id_mismatch", "document.id 必须与内容 id 一致", "id"))
    if content_type == "storylet" and str(document.get("chain_id", "")) != content_id:
        issues.append(_issue("id_mismatch", "Storylet chain_id 必须与内容 id 一致", "chain_id"))

    if content_type == "story_arc":
        try:
            analyze_graph(document, effect_ops=EFFECT_OPS, valid_scene_types=VALID_SCENE_TYPES)
        except (ValueError, TypeError, KeyError) as exc:
            issues.append(_issue("invalid_story_arc", str(exc)))
    elif content_type == "storylet":
        issues.extend(_validate_storylet(document))
    elif content_type == "item":
        issues.extend(_validate_item(content_id, document))
    elif content_type == "preset_character":
        issues.extend(_validate_preset(document))
    elif content_type == "character_kind":
        components = _documents("character_component", "__candidate__", {}).keys()
        for index, component_id in enumerate(document.get("components", [])):
            if component_id not in components:
                issues.append(_issue("unknown_character_component", f"未知人物组件：{component_id}", f"components[{index}]"))
    elif content_type == "character_attribute":
        for field in ("name", "label", "influence"):
            if not str(document.get(field, "")):
                issues.append(_issue("missing_field", f"缺少 {field}", field))
    elif content_type == "body_part":
        issues.extend(_validate_body_part(content_id, document))
    elif content_type == "equipment_slot":
        issues.extend(_validate_equipment_slot(content_id, document))
    elif content_type == "body_slot_preset":
        slots = _documents("equipment_slot", "__candidate__", {}).keys()
        for index, slot_id in enumerate(document.get("slots", [])):
            if slot_id not in slots:
                issues.append(_issue("unknown_equipment_slot", f"未知装备槽位：{slot_id}", f"slots[{index}]"))
    elif content_type == "character_component" and not isinstance(document, dict):
        issues.append(_issue("invalid_component", "组件默认值必须是对象"))
    return issues


def _validate_storylet(document: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if int(document.get("schema_version", 0)) != 1:
        issues.append(_issue("invalid_schema_version", "Storylet schema_version 必须为 1", "schema_version"))
    nodes = document.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return issues + [_issue("missing_nodes", "Storylet nodes 必须是非空数组", "nodes")]
    keys: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            issues.append(_issue("invalid_node", "节点必须是对象", f"nodes[{index}]")); continue
        node_key = str(node.get("node_key", ""))
        if not node_key or node_key in keys:
            issues.append(_issue("duplicate_node_key", "node_key 必须非空且唯一", f"nodes[{index}].node_key"))
        keys.add(node_key)
        unknown_triggers = set(node.get("triggers", {})) - TRIGGER_OPS
        if unknown_triggers:
            issues.append(_issue("unknown_trigger", f"未知 trigger：{sorted(unknown_triggers)}", f"nodes[{index}].triggers"))
        for name, spec in node.get("parameters", {}).items():
            if not isinstance(spec, dict) or not (set(spec) & PARAMETER_GENERATORS):
                issues.append(_issue("invalid_parameter", f"参数 {name} 没有合法生成器", f"nodes[{index}].parameters.{name}"))
        for choice_index, choice in enumerate(node.get("choices", [])):
            if not isinstance(choice, dict) or not choice.get("id"):
                issues.append(_issue("invalid_choice", "choice id 不能为空", f"nodes[{index}].choices[{choice_index}]")); continue
            for effect_index, effect in enumerate(choice.get("effects", [])):
                if not isinstance(effect, dict) or effect.get("op") not in EFFECT_OPS:
                    issues.append(_issue("unknown_effect", f"未知 effect：{effect}", f"nodes[{index}].choices[{choice_index}].effects[{effect_index}]"))
                if isinstance(effect, dict) and effect.get("op") == "schedule_followup" and effect.get("node_key") not in {str(item.get("node_key")) for item in nodes if isinstance(item, dict)}:
                    issues.append(_issue("unknown_followup", f"后续节点不存在：{effect.get('node_key')}", f"nodes[{index}].choices[{choice_index}].effects[{effect_index}]"))
    return issues


def _validate_item(content_id: str, document: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    slots = set(_documents("equipment_slot", "__candidate__", {}))
    attributes = set(_documents("character_attribute", "__candidate__", {}))
    for field in ("allowed_slots", "occupied_slots"):
        values = document.get(field, [])
        if not isinstance(values, list):
            issues.append(_issue("invalid_slot_list", f"{field} 必须是数组", field)); continue
        for index, slot_id in enumerate(values):
            if slot_id not in slots:
                issues.append(_issue("unknown_equipment_slot", f"未知装备槽位：{slot_id}", f"{field}[{index}]"))
    for slot_id in document.get("requirements", {}):
        if slot_id not in slots:
            issues.append(_issue("unknown_requirement_slot", f"装备需求引用未知槽位：{slot_id}", f"requirements.{slot_id}"))
    effects = document.get("effects", {}) if isinstance(document.get("effects"), dict) else {}
    for attribute_id in effects.get("character_attributes", {}):
        if attribute_id not in attributes:
            issues.append(_issue("unknown_attribute", f"未知人物属性：{attribute_id}", f"effects.character_attributes.{attribute_id}"))
    for resource_id in effects.get("realm_resources", {}):
        if resource_id not in RESOURCES:
            issues.append(_issue("unknown_resource", f"未知领地资源：{resource_id}", f"effects.realm_resources.{resource_id}"))
    private = {key for key, value in load_equipment_slots().get("slots", {}).items() if value.get("adult_only")}
    if private & (set(document.get("allowed_slots", [])) | set(document.get("occupied_slots", []))) and document.get("adult_only") is not True:
        issues.append(_issue("adult_only_required", "使用成人槽位的装备必须设置 adult_only=true", "adult_only"))
    if not str(document.get("name", "")):
        issues.append(_issue("missing_name", "物品必须有 name", "name"))
    return issues


def _validate_preset(document: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    registry = load_character_registry()
    equipment = load_equipment_slots()
    if document.get("kind") not in registry.get("kinds", {}):
        issues.append(_issue("unknown_character_kind", f"未知人物 kind：{document.get('kind')}", "kind"))
    if document.get("body_preset_id") not in equipment.get("presets", {}):
        issues.append(_issue("unknown_body_preset", f"未知身体预设：{document.get('body_preset_id')}", "body_preset_id"))
    items = _documents("item", "__candidate__", {})
    item_ids = set(items)
    for index, item in enumerate(document.get("initial_inventory", [])):
        if not isinstance(item, dict) or item.get("item_id") not in item_ids:
            issues.append(_issue("unknown_item", f"未知初始物品：{item}", f"initial_inventory[{index}]"))
    for slot_id, item_id in document.get("initial_equipment", {}).items():
        if slot_id not in equipment.get("slots", {}):
            issues.append(_issue("unknown_equipment_slot", f"未知装备槽位：{slot_id}", f"initial_equipment.{slot_id}"))
        if item_id not in item_ids:
            issues.append(_issue("unknown_item", f"未知装备：{item_id}", f"initial_equipment.{slot_id}"))
    age = int(document.get("age", 0) or 0)
    preset_slots = set(equipment.get("presets", {}).get(document.get("body_preset_id"), {}).get("slots", []))
    private = {key for key, value in equipment.get("slots", {}).items() if value.get("adult_only")}
    if age < 18 and preset_slots & private:
        issues.append(_issue("adult_body_preset", "未成年预设人物不能使用成人身体槽位", "body_preset_id"))
    occupied_by: dict[str, str] = {}
    for entry_slot, item_id in document.get("initial_equipment", {}).items():
        item = items.get(item_id, {})
        if entry_slot not in preset_slots:
            issues.append(_issue("slot_not_available", f"身体预设不包含装备入口槽位：{entry_slot}", f"initial_equipment.{entry_slot}"))
        allowed = set(item.get("allowed_slots", []))
        if item and entry_slot not in allowed:
            issues.append(_issue("item_slot_not_allowed", f"{item_id} 不能从槽位 {entry_slot} 装备", f"initial_equipment.{entry_slot}"))
        occupied = set(item.get("occupied_slots", [])) or {entry_slot}
        if not occupied <= preset_slots:
            missing = sorted(occupied - preset_slots)
            issues.append(_issue("occupied_slot_not_available", f"{item_id} 需要身体预设不存在的槽位：{missing}", f"initial_equipment.{entry_slot}"))
        if age < 18 and (item.get("adult_only") or occupied & private):
            issues.append(_issue("adult_item_for_minor", f"未成年预设人物不能装备成人物品：{item_id}", f"initial_equipment.{entry_slot}"))
        for occupied_slot in occupied:
            previous = occupied_by.get(occupied_slot)
            if previous and previous != item_id:
                issues.append(_issue("equipment_slot_conflict", f"{previous} 与 {item_id} 同时占用 {occupied_slot}", f"initial_equipment.{entry_slot}"))
            occupied_by[occupied_slot] = item_id
    return issues


def _validate_body_part(content_id: str, document: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    parts = _documents("body_part", content_id, document)
    parent = document.get("parent_id")
    pair = document.get("pair_id")
    if parent is not None and parent not in parts:
        issues.append(_issue("unknown_parent_part", f"未知父身体部位：{parent}", "parent_id"))
    if pair is not None:
        if pair not in parts:
            issues.append(_issue("unknown_pair_part", f"未知配对身体部位：{pair}", "pair_id"))
        elif parts[pair].get("pair_id") != content_id:
            issues.append(_issue("asymmetric_pair", f"配对部位 {pair} 没有反向引用 {content_id}", "pair_id"))
    seen = {content_id}
    cursor = parent
    while cursor:
        if cursor in seen:
            issues.append(_issue("body_parent_cycle", "身体部位 parent_id 形成环", "parent_id")); break
        seen.add(cursor)
        cursor = parts.get(cursor, {}).get("parent_id")
    return issues


def _validate_equipment_slot(content_id: str, document: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    parts = set(_documents("body_part", "__candidate__", {}))
    if not document.get("virtual") and document.get("body_part_id") not in parts:
        issues.append(_issue("unknown_body_part", f"未知身体部位：{document.get('body_part_id')}", "body_part_id"))
    if document.get("group") not in {"public", "private", "accessory"}:
        issues.append(_issue("invalid_slot_group", "slot group 必须是 public/private/accessory", "group"))
    return issues


def validation_payload(content_type: str, content_id: str, document: dict[str, Any]) -> dict[str, Any]:
    issues = validate_document(content_type, content_id, deepcopy(document))
    return {
        "valid": not any(item.severity == "error" for item in issues),
        "errors": [item.model_dump() for item in issues if item.severity == "error"],
        "warnings": [item.model_dump() for item in issues if item.severity == "warning"],
        "info": [item.model_dump() for item in issues if item.severity == "info"],
    }
