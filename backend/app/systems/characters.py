from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from ..catalog import ITEMS, RESOURCES
from ..engine.time import add_to_time_point, normalize_time_point, time_key, time_point_from_state

DEFAULT_CHARACTER_STATUS = "active"
RESERVED_CHARACTER_IDS = {"user", "player", "lord", "current_lord"}
SPECIAL_CHARACTER_SOURCE_IDS = {"player_lord", "external_unknown", "unknown"}
LORD_ITEM_CHARACTER_IDS = {"player_lord", "lord", "current_lord"}
ATTRIBUTE_IDS: dict[str, dict[str, str]] = {
    "STR": {"name": "Strength", "label": "力量", "influence": "近战伤害、负重、推拉、破坏物体"},
    "DEX": {"name": "Dexterity", "label": "敏捷", "influence": "命中、闪避、潜行、反应速度、精细操作"},
    "CON": {"name": "Constitution", "label": "体质", "influence": "生命值、耐力、抗病、抗毒、身体恢复"},
    "INT": {"name": "Intelligence", "label": "智力", "influence": "学习、知识、分析、法术、技能点"},
    "WIS": {"name": "Wisdom", "label": "感知／智慧", "influence": "察觉、直觉、意志、判断、精神抗性"},
    "CHA": {"name": "Charisma", "label": "魅力", "influence": "说服、威吓、领导、欺骗、人际影响"},
}
DEFAULT_ATTRIBUTES = {key: 10 for key in ATTRIBUTE_IDS}
PUBLIC_EQUIPMENT_SLOTS = (
    "head",
    "neck",
    "torso",
    "back",
    "left_arm",
    "right_arm",
    "left_hand",
    "right_hand",
    "waist",
    "left_leg",
    "right_leg",
    "left_foot",
    "right_foot",
)
PRIVATE_EQUIPMENT_SLOTS = (
    "left_nipple",
    "right_nipple",
    "nipple_chain",
    "penis",
    "vagina",
    "anus",
)
ACCESSORY_EQUIPMENT_SLOTS = ("accessory_1", "accessory_2")
BODY_EQUIPMENT_SLOTS = (*PUBLIC_EQUIPMENT_SLOTS, *PRIVATE_EQUIPMENT_SLOTS, *ACCESSORY_EQUIPMENT_SLOTS)
EQUIPMENT_SLOT_REGISTRY: dict[str, dict[str, Any]] = {
    "head": {"label": "头部", "adult_only": False, "examples": ["帽子", "头盔", "王冠"]},
    "neck": {"label": "颈部", "adult_only": False, "examples": ["项链", "护喉", "披风扣"]},
    "torso": {"label": "躯干", "adult_only": False, "examples": ["衣服", "锁甲", "胸甲", "长袍"]},
    "back": {"label": "背部", "adult_only": False, "examples": ["披风", "背包", "箭袋"]},
    "left_arm": {"label": "左臂", "adult_only": False, "examples": ["护臂", "臂甲"]},
    "right_arm": {"label": "右臂", "adult_only": False, "examples": ["护臂", "臂甲"]},
    "left_hand": {"label": "左手", "adult_only": False, "examples": ["武器", "盾牌", "工具"]},
    "right_hand": {"label": "右手", "adult_only": False, "examples": ["武器", "盾牌", "工具"]},
    "waist": {"label": "腰部", "adult_only": False, "examples": ["腰带", "钱袋", "剑鞘"]},
    "left_leg": {"label": "左腿", "adult_only": False, "examples": ["护腿", "腿甲"]},
    "right_leg": {"label": "右腿", "adult_only": False, "examples": ["护腿", "腿甲"]},
    "left_foot": {"label": "左脚", "adult_only": False, "examples": ["鞋", "靴子", "马刺"]},
    "right_foot": {"label": "右脚", "adult_only": False, "examples": ["鞋", "靴子", "马刺"]},
    "left_nipple": {"label": "左乳头", "adult_only": True, "examples": ["穿环", "夹具"]},
    "right_nipple": {"label": "右乳头", "adult_only": True, "examples": ["穿环", "夹具"]},
    "nipple_chain": {"label": "乳链", "adult_only": True, "examples": ["连接饰物"]},
    "penis": {"label": "阴茎", "adult_only": True, "examples": ["穿环", "封闭装置"]},
    "vagina": {"label": "阴道", "adult_only": True, "examples": ["穿环", "封闭装置"]},
    "anus": {"label": "肛门", "adult_only": True, "examples": ["封闭装置"]},
    "accessory_1": {"label": "饰品 1", "adult_only": False, "examples": ["戒指", "护符", "印章"]},
    "accessory_2": {"label": "饰品 2", "adult_only": False, "examples": ["戒指", "护符", "印章"]},
}
EQUIPMENT_SLOT_ALIASES = {
    "body": "torso",
    "cloak": "back",
    "main_hand": "right_hand",
    "off_hand": "left_hand",
    "hand": "right_hand",
    "ring": "accessory_1",
    "trinket": "accessory_1",
}
DEFAULT_AVAILABLE_EQUIPMENT_SLOTS = (*PUBLIC_EQUIPMENT_SLOTS, *ACCESSORY_EQUIPMENT_SLOTS)
BODY_SLOT_PRESETS: dict[str, dict[str, Any]] = {
    "common": {
        "label": "通用身体槽位",
        "slots": list(DEFAULT_AVAILABLE_EQUIPMENT_SLOTS),
    },
    "male": {
        "label": "男性全槽位",
        "slots": [
            *PUBLIC_EQUIPMENT_SLOTS,
            "left_nipple",
            "right_nipple",
            "nipple_chain",
            "penis",
            "anus",
            *ACCESSORY_EQUIPMENT_SLOTS,
        ],
    },
    "female": {
        "label": "女性全槽位",
        "slots": [
            *PUBLIC_EQUIPMENT_SLOTS,
            "left_nipple",
            "right_nipple",
            "nipple_chain",
            "vagina",
            "anus",
            *ACCESSORY_EQUIPMENT_SLOTS,
        ],
    },
}
BASE_CHARACTER_COMPONENTS = (
    "attributes", "body_profile", "inventory", "equipment",
    "social_identity", "personality_axes", "household", "narrative", "wardrobe", "provenance",
)

CHARACTER_KINDS: dict[str, dict[str, Any]] = {
    "commoner": {"label": "普通领民", "components": ["health"]},
    "steward": {"label": "管家", "components": ["court_official", "economy_agent", "health"]},
    "merchant": {"label": "商人", "components": ["merchant", "economy_agent", "health"]},
    "envoy": {"label": "使者", "components": ["envoy", "diplomacy_agent", "health"]},
    "knight": {"label": "骑士", "components": ["noble", "combatant", "health"]},
    "soldier": {"label": "士兵", "components": ["combatant", "health"]},
    "craftsman": {"label": "工匠", "components": ["craftsman", "economy_agent", "health"]},
    "prisoner": {"label": "俘虏", "components": ["prisoner", "health"]},
    "spy": {"label": "间谍", "components": ["spy", "health"]},
}

ROLE_KIND_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("管家", "账房", "总管"), "steward"),
    (("商人", "商队"), "merchant"),
    (("使者", "外交"), "envoy"),
    (("骑士", "贵族"), "knight"),
    (("士兵", "护卫", "雇佣兵"), "soldier"),
    (("工匠", "铁匠", "木匠"), "craftsman"),
    (("俘虏", "囚犯"), "prisoner"),
    (("间谍", "密探", "线人"), "spy"),
)

SEX_POSITION_IDS: dict[str, str] = {
    "missionary": "正面",
    "standing": "站立",
    "rear": "背后",
    "oral": "口交",
    "anal": "肛交",
}

BODY_CONTENT_TYPES: dict[str, str] = {
    "semen": "精液",
    "urine": "尿液",
    "food": "食物",
    "water": "水",
    "wine": "酒",
    "medicine": "药物",
    "poison": "毒物",
    "blood": "血液",
    "bile": "胆汁",
    "parasite": "寄生物",
    "unknown": "未知内容物",
}

REPRODUCTIVE_CONTENT_TARGETS: dict[str, str] = {
    "stomach": "stomach_contents",
    "intestine": "intestinal_contents",
    "uterus": "uterine_contents",
}

DEFAULT_CONTENT_EXPIRY: dict[str, dict[str, int]] = {
    "stomach": {"hours": 12},
    "intestine": {"days": 2},
    "uterus": {"days": 3},
}

COMPONENT_DEFAULTS: dict[str, dict[str, Any]] = {
    "attributes": {
        "base": DEFAULT_ATTRIBUTES,
        "modifiers": {},
        "equipment_modifiers": {},
        "effective": DEFAULT_ATTRIBUTES,
    },
    "body_profile": {"available_slots": list(DEFAULT_AVAILABLE_EQUIPMENT_SLOTS), "notes": ""},
    "inventory": {"items": []},
    "equipment": {"slots": {}, "attribute_effects": {}, "realm_effects": {}, "sources": []},
    "health": {"condition": "healthy", "wounds": [], "stress": 0, "disease": ""},
    "court_official": {"rank": "", "access_level": 1, "manages": []},
    "economy_agent": {"wealth": 0, "income": 0, "debts": []},
    "merchant": {"goods": [], "credit": 50, "route": "", "next_visit_hint": ""},
    "envoy": {"home_faction": "", "authority": 0, "message": "", "negotiation_stance": "neutral"},
    "diplomacy_agent": {"faction": "", "influence": 0, "grievances": [], "promises": []},
    "noble": {"rank": "", "house": "", "honor": 0},
    "combatant": {"unit_type": "", "skill": 20, "morale": 50, "equipment": []},
    "craftsman": {"craft": "", "skill": 20, "workshop": "", "orders": []},
    "prisoner": {"captor": "", "reason": "", "security_level": 1, "ransom": 0},
    "spy": {"cover": "", "loyalty_to": "", "secrecy": 50, "known_secrets": []},
    "sexual_history": {
        "enabled": True,
        "adult_only": True,
        "total_partner_count": 0,
        "total_encounter_count": 0,
        "partners": {},
        "position_totals": {},
        "last_encounter_time": None,
    },
    "reproductive_contents": {
        "stomach_contents": [],
        "intestinal_contents": [],
        "uterine_contents": [],
    },
    "social_identity": {"class_id": "", "legal_status": "", "occupation_id": "", "reputation": 0},
    "personality_axes": {
        "ambition": 50, "greed": 50, "boldness": 50, "loyalty": 50,
        "compassion": 50, "piety": 50, "deceit": 50,
    },
    "household": {"household_id": "", "home_tile": "", "member_ids": [], "dependent_ids": []},
    "narrative": {"goals": [], "hooks": [], "secrets": [], "recent_event_ids": [], "active_chain_ids": []},
    "wardrobe": {"template_id": "", "wealth_band": "poor", "season": "spring", "description_md": ""},
    "provenance": {
        "generator_version": 0, "seed": None, "archetype_id": "",
        "created_by_story_event_id": "", "population_origin": {},
    },
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clean_string(value: Any, default: str = "") -> str:
    return str(value if value is not None else default).strip()


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _clean_int_map(value: Any, allowed_keys: set[str], *, default_zero: bool = False) -> dict[str, int]:
    raw = value if isinstance(value, dict) else {}
    result = {key: 0 for key in allowed_keys} if default_zero else {}
    for key, raw_value in raw.items():
        normalized_key = str(key).strip()
        if normalized_key not in allowed_keys:
            continue
        try:
            result[normalized_key] = int(raw_value or 0)
        except (TypeError, ValueError):
            result[normalized_key] = 0
    return result


def _item_catalog_entry(item_id: str) -> dict[str, Any]:
    item = ITEMS.get(item_id)
    if not isinstance(item, dict):
        raise HTTPException(422, f"未知物品 id：{item_id}")
    return item


def _item_effects(item_id: str) -> dict[str, Any]:
    item = _item_catalog_entry(item_id)
    return item.get("effects") if isinstance(item.get("effects"), dict) else {}


def _normalize_equipment_slot(slot: Any) -> str:
    slot_id = _clean_string(slot)
    slot_id = EQUIPMENT_SLOT_ALIASES.get(slot_id, slot_id)
    return slot_id if slot_id in EQUIPMENT_SLOT_REGISTRY else ""


def _normalize_equipment_slot_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        slot = _normalize_equipment_slot(raw)
        if slot and slot not in seen:
            normalized.append(slot)
            seen.add(slot)
    return normalized


def _item_slot(item_id: str) -> str:
    item = _item_catalog_entry(item_id)
    allowed = _normalize_equipment_slot_list(item.get("allowed_slots"))
    if allowed:
        return allowed[0]
    return _normalize_equipment_slot(item.get("slot")) or "accessory_1"


def _item_allowed_slots(item_id: str) -> list[str]:
    item = _item_catalog_entry(item_id)
    allowed = _normalize_equipment_slot_list(item.get("allowed_slots"))
    if allowed:
        return allowed
    legacy_slot = _normalize_equipment_slot(item.get("slot"))
    return [legacy_slot] if legacy_slot else []


def _item_occupied_slots(item_id: str, selected_slot: str) -> list[str]:
    item = _item_catalog_entry(item_id)
    occupied = _normalize_equipment_slot_list(item.get("occupied_slots"))
    return occupied if occupied else [selected_slot]


def _item_tags(item_id: str) -> set[str]:
    item = _item_catalog_entry(item_id)
    raw = item.get("tags")
    if not isinstance(raw, list):
        return set()
    return {_clean_string(tag) for tag in raw if _clean_string(tag)}


def _private_slots(slots: list[str] | set[str]) -> set[str]:
    return set(slots) & set(PRIVATE_EQUIPMENT_SLOTS)


def _normalize_body_profile_component(character: dict[str, Any]) -> dict[str, Any]:
    components = character.setdefault("components", {})
    raw_profile = components.get("body_profile") if isinstance(components.get("body_profile"), dict) else {}
    raw_available = raw_profile.get("available_slots")
    if raw_available is None:
        available = list(DEFAULT_AVAILABLE_EQUIPMENT_SLOTS)
    else:
        available = _normalize_equipment_slot_list(raw_available)
        if not available:
            available = list(DEFAULT_AVAILABLE_EQUIPMENT_SLOTS)
    if not _is_adult(character):
        available = [slot for slot in available if slot not in PRIVATE_EQUIPMENT_SLOTS]
    profile = {
        **deepcopy(raw_profile),
        "available_slots": available,
        "private_slots_enabled": bool(_private_slots(set(available))),
    }
    components["body_profile"] = profile
    return profile


def _equipment_requirement_satisfied(slots: dict[str, str], item_id: str) -> tuple[bool, str]:
    item = _item_catalog_entry(item_id)
    requirements = item.get("requirements") if isinstance(item.get("requirements"), dict) else {}
    for raw_slot, requirement in requirements.items():
        slot = _normalize_equipment_slot(raw_slot)
        if not slot:
            return False, f"装备需求包含未知槽位：{raw_slot}"
        equipped_item_id = slots.get(slot)
        if not equipped_item_id:
            return False, f"{item.get('name', item_id)} 需要 {EQUIPMENT_SLOT_REGISTRY[slot]['label']} 已装备指定物品"
        if isinstance(requirement, dict):
            required_tag = _clean_string(requirement.get("tag"))
            if required_tag and required_tag not in _item_tags(equipped_item_id):
                return False, f"{EQUIPMENT_SLOT_REGISTRY[slot]['label']} 已装备物品缺少标签：{required_tag}"
    return True, ""


def _validate_item_equip_target(character: dict[str, Any], item_id: str, selected_slot: str, target_slots: list[str], slots: dict[str, str]) -> None:
    allowed_slots = _item_allowed_slots(item_id)
    if not allowed_slots:
        raise HTTPException(422, f"物品没有 allowed_slots：{item_id}")
    if selected_slot not in allowed_slots:
        raise HTTPException(422, f"{ITEMS[item_id].get('name', item_id)} 不能装备到槽位：{selected_slot}")
    unknown_slots = [slot for slot in target_slots if slot not in EQUIPMENT_SLOT_REGISTRY]
    if unknown_slots:
        raise HTTPException(422, f"未知装备槽位：{unknown_slots}")
    private = _private_slots(set(target_slots) | {selected_slot})
    if private and not _is_adult(character):
        raise HTTPException(422, "私密部位装备只能用于已明确为成年的人物")
    body_profile = _normalize_body_profile_component(character)
    available = set(body_profile.get("available_slots", []))
    missing = [slot for slot in target_slots if slot not in available]
    if missing:
        labels = "、".join(EQUIPMENT_SLOT_REGISTRY[slot]["label"] for slot in missing)
        raise HTTPException(422, f"角色缺少装备所需身体槽位：{labels}")
    ok, reason = _equipment_requirement_satisfied(slots, item_id)
    if not ok:
        raise HTTPException(422, reason)
    for slot in target_slots:
        existing = slots.get(slot)
        if existing and existing != item_id:
            label = EQUIPMENT_SLOT_REGISTRY[slot]["label"]
            raise HTTPException(422, f"{label} 已被 {ITEMS.get(existing, {}).get('name', existing)} 占用")


def _equip_item_on_character_record(character: dict[str, Any], item_id: str, slot: str) -> None:
    selected_slot = _normalize_equipment_slot(slot) or _item_slot(item_id)
    if not selected_slot:
        raise HTTPException(422, "物品没有可装备槽位")
    target_slots = _item_occupied_slots(item_id, selected_slot)
    equipment = _ensure_component(character, "equipment")
    slots = equipment.setdefault("slots", {})
    if not isinstance(slots, dict):
        slots = {}
        equipment["slots"] = slots
    slots = {
        _normalize_equipment_slot(existing_slot): existing_item_id
        for existing_slot, existing_item_id in slots.items()
        if _normalize_equipment_slot(existing_slot) and _clean_string(existing_item_id) in ITEMS
    }
    _validate_item_equip_target(character, item_id, selected_slot, target_slots, slots)
    for occupied_slot in target_slots:
        slots[occupied_slot] = item_id
    equipment["slots"] = slots


def _normalize_inventory_items(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(value, list):
        for entry in value:
            if isinstance(entry, str):
                item_id = _clean_string(entry)
                quantity = 1
            elif isinstance(entry, dict):
                item_id = _clean_string(entry.get("item_id") or entry.get("id"))
                try:
                    quantity = int(entry.get("quantity", 1) or 1)
                except (TypeError, ValueError):
                    quantity = 1
            else:
                continue
            if item_id in ITEMS and quantity > 0:
                catalog_item = ITEMS[item_id]
                items.append({
                    "item_id": item_id,
                    "name": catalog_item.get("name", item_id),
                    "quantity": quantity,
                })
    return items


def _inventory_quantity(character: dict[str, Any], item_id: str) -> int:
    inventory = _ensure_component(character, "inventory")
    total = 0
    for entry in _normalize_inventory_items(inventory.get("items")):
        if entry["item_id"] == item_id:
            total += int(entry.get("quantity", 0) or 0)
    return total


def _set_inventory_items(character: dict[str, Any], items: list[dict[str, Any]]) -> None:
    inventory = _ensure_component(character, "inventory")
    normalized = _normalize_inventory_items(items)
    merged: dict[str, int] = {}
    for item in normalized:
        merged[item["item_id"]] = merged.get(item["item_id"], 0) + int(item["quantity"])
    inventory["items"] = [
        {"item_id": item_id, "name": ITEMS[item_id].get("name", item_id), "quantity": quantity}
        for item_id, quantity in sorted(merged.items())
        if quantity > 0
    ]


def _normalize_character_item_components(character: dict[str, Any]) -> None:
    components = character.setdefault("components", {})
    attributes = components.get("attributes") if isinstance(components.get("attributes"), dict) else {}
    base = _clean_int_map(attributes.get("base"), set(ATTRIBUTE_IDS), default_zero=False)
    for key, value in DEFAULT_ATTRIBUTES.items():
        base.setdefault(key, value)
    manual_modifiers = _clean_int_map(attributes.get("modifiers"), set(ATTRIBUTE_IDS))
    body_profile = _normalize_body_profile_component(character)
    available_slots = set(body_profile.get("available_slots", []))

    inventory = components.get("inventory") if isinstance(components.get("inventory"), dict) else {}
    inventory_items = _normalize_inventory_items(inventory.get("items"))
    components["inventory"] = {"items": inventory_items}

    equipment = components.get("equipment") if isinstance(components.get("equipment"), dict) else {}
    raw_slots = equipment.get("slots") if isinstance(equipment.get("slots"), dict) else {}
    slots: dict[str, str] = {}
    for raw_slot, raw_item_id in raw_slots.items():
        item_id = _clean_string(raw_item_id)
        if item_id not in ITEMS:
            continue
        slot = _normalize_equipment_slot(raw_slot) or _item_slot(item_id)
        if not slot or slot not in available_slots:
            continue
        slots[slot] = item_id

    equipment_modifiers = {key: 0 for key in ATTRIBUTE_IDS}
    realm_effects = {key: 0 for key in RESOURCES}
    sources: list[dict[str, Any]] = []
    seen_effect_sources: set[str] = set()
    for slot, item_id in slots.items():
        if item_id in seen_effect_sources:
            continue
        seen_effect_sources.add(item_id)
        effects = _item_effects(item_id)
        item_attribute_effects = _clean_int_map(effects.get("character_attributes"), set(ATTRIBUTE_IDS))
        item_realm_effects = _clean_int_map(effects.get("realm_resources"), set(RESOURCES))
        for key, delta in item_attribute_effects.items():
            equipment_modifiers[key] += delta
        for key, delta in item_realm_effects.items():
            realm_effects[key] += delta
        sources.append({
            "slot": slot,
            "occupied_slots": [occupied_slot for occupied_slot, occupied_item in slots.items() if occupied_item == item_id],
            "item_id": item_id,
            "name": ITEMS[item_id].get("name", item_id),
            "character_attributes": item_attribute_effects,
            "realm_resources": item_realm_effects,
            "armor": int(ITEMS[item_id].get("armor", 0) or 0),
            "damage": int(ITEMS[item_id].get("damage", 0) or 0),
            "weight": float(ITEMS[item_id].get("weight", 0) or 0),
            "durability": int(ITEMS[item_id].get("durability", 0) or 0),
        })

    effective = {
        key: int(base.get(key, 10)) + int(manual_modifiers.get(key, 0)) + int(equipment_modifiers.get(key, 0))
        for key in ATTRIBUTE_IDS
    }
    components["attributes"] = {
        "base": base,
        "modifiers": manual_modifiers,
        "equipment_modifiers": {key: value for key, value in equipment_modifiers.items() if value},
        "effective": effective,
    }
    components["equipment"] = {
        "slots": slots,
        "attribute_effects": {key: value for key, value in equipment_modifiers.items() if value},
        "realm_effects": {key: value for key, value in realm_effects.items() if value},
        "sources": sources,
    }


def _infer_kind(role: str, requested: str = "") -> tuple[str, str]:
    requested = _clean_string(requested)
    if requested in CHARACTER_KINDS:
        return requested, ""
    role = _clean_string(role)
    for needles, kind in ROLE_KIND_HINTS:
        if any(needle in role for needle in needles):
            return kind, requested if requested else ""
    return "commoner", requested if requested else ""


def _merge_component_defaults(kind: str, components: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(components)
    component_ids = [*BASE_CHARACTER_COMPONENTS, *CHARACTER_KINDS.get(kind, CHARACTER_KINDS["commoner"])["components"]]
    for component_id in component_ids:
        if not isinstance(merged.get(component_id), dict):
            merged[component_id] = deepcopy(COMPONENT_DEFAULTS[component_id])
        else:
            merged[component_id] = {**deepcopy(COMPONENT_DEFAULTS[component_id]), **deepcopy(merged[component_id])}
    return merged


def _structured_block(raw: Any) -> dict[str, Any]:
    return deepcopy(raw) if isinstance(raw, dict) else {}


def normalize_characters(state: dict[str, Any]) -> None:
    normalize_lord_components(state)
    raw = state.get("characters")
    if not isinstance(raw, dict):
        raw = {"entries": [], "next_id": 1}
        state["characters"] = raw
    entries = raw.setdefault("entries", [])
    if not isinstance(entries, list):
        entries = []
        raw["entries"] = entries
    next_id = int(raw.get("next_id", 1) or 1)
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            continue
        character = normalize_character_entry(item)
        if character["id"] in seen or character["id"] in RESERVED_CHARACTER_IDS:
            continue
        seen.add(character["id"])
        normalized.append(character)
        if character["id"].startswith("char_"):
            try:
                next_id = max(next_id, int(character["id"].removeprefix("char_")) + 1)
            except ValueError:
                pass
    raw["entries"] = normalized
    raw["next_id"] = max(next_id, 1)
    refresh_realm_item_effects(state)


def normalize_lord_components(state: dict[str, Any]) -> None:
    raw_components = state.get("lord_components")
    if not isinstance(raw_components, dict):
        raw_components = {}
    pseudo = normalize_character_entry({
        "id": "player_lord",
        "kind": "knight",
        "name": state.get("lord_name") or "领主",
        "role": "领主",
        "gender": state.get("lord_gender") or "未说明",
        "components": raw_components,
        "flags": {"adult": True},
    })
    state["lord_components"] = pseudo["components"]


def normalize_character_entry(item: dict[str, Any]) -> dict[str, Any]:
    character_id = _clean_string(item.get("id"))
    created_time = item.get("created_time") if isinstance(item.get("created_time"), dict) else {}
    raw_identity = _structured_block(item.get("identity"))
    raw_profile = _structured_block(item.get("profile"))
    raw_relationship = _structured_block(item.get("relationship"))
    raw_memory = _structured_block(item.get("memory"))
    flags = deepcopy(item.get("flags") if isinstance(item.get("flags"), dict) else {})
    role = _clean_string(item.get("role") or raw_identity.get("role"))
    kind, requested_kind = _infer_kind(role, item.get("kind"))
    if requested_kind:
        flags.setdefault("requested_kind", requested_kind)
    identity = {
        "role": role,
        "gender": _clean_string(item.get("gender") or raw_identity.get("gender"), "未说明"),
        "age": item.get("age") if item.get("age") is not None else raw_identity.get("age"),
        "faction": _clean_string(item.get("faction") or raw_identity.get("faction")),
        "location": _clean_string(item.get("location") or raw_identity.get("location")),
        "status": _clean_string(item.get("status") or raw_identity.get("status"), DEFAULT_CHARACTER_STATUS),
    }
    profile = {
        "appearance_md": _clean_string(item.get("appearance_md") or raw_profile.get("appearance_md")),
        "personality_md": _clean_string(item.get("personality_md") or raw_profile.get("personality_md")),
        "description_md": _clean_string(item.get("description_md") or raw_profile.get("description_md")),
        "traits": _clean_string_list(item.get("traits") if item.get("traits") is not None else raw_profile.get("traits")),
    }
    relationship = {
        "to_lord": _clean_string(item.get("relationship_to_lord") or raw_relationship.get("to_lord")),
        "disposition": int(item.get("disposition", raw_relationship.get("disposition", 0)) or 0),
        "loyalty": int(raw_relationship.get("loyalty", 0) or 0),
        "fear": int(raw_relationship.get("fear", 0) or 0),
        "trust": int(raw_relationship.get("trust", 0) or 0),
    }
    memory_entries = _clean_string_list(item.get("memories") if item.get("memories") is not None else raw_memory.get("entries"))
    memory = {**raw_memory, "entries": memory_entries}
    components = _merge_component_defaults(kind, deepcopy(item.get("components") if isinstance(item.get("components"), dict) else {}))
    normalized = {
        "id": character_id,
        "kind": kind,
        "name": _clean_string(item.get("name"), "无名人物"),
        "role": identity["role"],
        "gender": identity["gender"],
        "age": identity["age"],
        "faction": identity["faction"],
        "location": identity["location"],
        "status": identity["status"],
        "appearance_md": profile["appearance_md"],
        "personality_md": profile["personality_md"],
        "description_md": profile["description_md"],
        "relationship_to_lord": relationship["to_lord"],
        "disposition": relationship["disposition"],
        "traits": profile["traits"],
        "memories": memory_entries,
        "identity": identity,
        "profile": profile,
        "relationship": relationship,
        "memory": memory,
        "components": components,
        "flags": flags,
        "created_time": created_time,
        "created_at": _clean_string(item.get("created_at")),
        "updated_at": _clean_string(item.get("updated_at")),
    }
    _normalize_character_item_components(normalized)
    return normalized


def public_character_entry(character: dict[str, Any]) -> dict[str, Any]:
    return normalize_character_entry(character)


def public_lord_components(state: dict[str, Any]) -> dict[str, Any]:
    normalize_lord_components(state)
    return {
        "id": "player_lord",
        "name": state.get("lord_name") or "领主",
        "role": "领主",
        "gender": state.get("lord_gender") or "未说明",
        "components": deepcopy(state["lord_components"]),
        "flags": {"adult": True},
    }


def character_registry() -> dict[str, Any]:
    return {
        "kinds": deepcopy(CHARACTER_KINDS),
        "components": deepcopy(COMPONENT_DEFAULTS),
        "attribute_ids": deepcopy(ATTRIBUTE_IDS),
        "equipment_slots": deepcopy(EQUIPMENT_SLOT_REGISTRY),
        "public_equipment_slots": list(PUBLIC_EQUIPMENT_SLOTS),
        "private_equipment_slots": list(PRIVATE_EQUIPMENT_SLOTS),
        "accessory_equipment_slots": list(ACCESSORY_EQUIPMENT_SLOTS),
        "body_slot_presets": deepcopy(BODY_SLOT_PRESETS),
        "items": deepcopy(ITEMS),
        "sex_position_ids": deepcopy(SEX_POSITION_IDS),
        "body_content_types": deepcopy(BODY_CONTENT_TYPES),
        "reproductive_content_targets": deepcopy(REPRODUCTIVE_CONTENT_TARGETS),
        "default_content_expiry": deepcopy(DEFAULT_CONTENT_EXPIRY),
        "special_character_source_ids": sorted(SPECIAL_CHARACTER_SOURCE_IDS),
    }


def list_characters(
    state: dict[str, Any],
    *,
    status: str | None = None,
    faction: str | None = None,
    include_inactive: bool = True,
) -> list[dict[str, Any]]:
    normalize_characters(state)
    entries = [public_character_entry(item) for item in state["characters"]["entries"]]
    if not include_inactive:
        entries = [item for item in entries if item.get("status") not in {"dead", "removed", "inactive"}]
    if status:
        entries = [item for item in entries if item.get("status") == status]
    if faction:
        entries = [item for item in entries if item.get("faction") == faction]
    return entries


def get_character(state: dict[str, Any], character_id: str) -> dict[str, Any]:
    normalize_characters(state)
    for character in state["characters"]["entries"]:
        if character["id"] == character_id:
            return character
    raise KeyError(character_id)


def _is_adult(character: dict[str, Any]) -> bool:
    flags = character.get("flags") if isinstance(character.get("flags"), dict) else {}
    if flags.get("non_adult") or flags.get("minor") or flags.get("child"):
        return False
    if flags.get("adult") is True or character.get("id") == "player_lord":
        return True
    try:
        return int(character.get("age")) >= 18
    except (TypeError, ValueError):
        return False


def _require_adult_character(character: dict[str, Any]) -> None:
    if not _is_adult(character):
        raise HTTPException(422, "成人关系/内容物统计只能写入已明确为成年的人物")


def _source_character_snapshot(state: dict[str, Any], source_character_id: str, provided_name: str = "") -> str:
    source_character_id = _clean_string(source_character_id)
    if not source_character_id:
        raise HTTPException(422, "必须提供 source_character_id/partner_character_id")
    if source_character_id in SPECIAL_CHARACTER_SOURCE_IDS:
        return _clean_string(provided_name) or source_character_id
    try:
        source = get_character(state, source_character_id)
    except KeyError as error:
        raise HTTPException(422, "source_character_id/partner_character_id 必须引用人物账册中的人物，或使用允许的特殊来源 id") from error
    _require_adult_character(source)
    return _clean_string(provided_name) or source["name"]


def _ensure_component(character: dict[str, Any], component_id: str) -> dict[str, Any]:
    components = character.setdefault("components", {})
    component = components.get(component_id)
    if not isinstance(component, dict):
        component = deepcopy(COMPONENT_DEFAULTS[component_id])
        components[component_id] = component
    return component


def _normalize_count(value: Any, *, field_name: str, minimum: int = 1, maximum: int = 1000) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError) as error:
        raise HTTPException(422, f"{field_name} 必须是整数") from error
    if count < minimum or count > maximum:
        raise HTTPException(422, f"{field_name} 必须在 {minimum}-{maximum} 之间")
    return count


def append_sexual_encounter(state: dict[str, Any], character_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    partner_id = _clean_string(payload.get("partner_character_id"))
    if partner_id == _clean_string(character_id):
        raise HTTPException(422, "character_id 和 partner_character_id 不能相同")
    partner_name = _source_character_snapshot(state, partner_id, payload.get("partner_name_snapshot", ""))
    character = get_character(state, character_id)
    _require_adult_character(character)
    position_id = _clean_string(payload.get("position_id"), "unknown")
    if position_id not in SEX_POSITION_IDS:
        raise HTTPException(422, f"未知性爱姿势 id：{position_id}")
    count = _normalize_count(payload.get("count", 1), field_name="count")
    encounter_time = normalize_time_point(payload.get("time") if isinstance(payload.get("time"), dict) else None, state)
    notes = _clean_string_list(payload.get("notes"))

    history = _ensure_component(character, "sexual_history")
    history["enabled"] = True
    history["adult_only"] = True
    partners = history.setdefault("partners", {})
    if not isinstance(partners, dict):
        partners = {}
        history["partners"] = partners
    partner = partners.setdefault(partner_id, {
        "character_id": partner_id,
        "name_snapshot": partner_name,
        "encounter_count": 0,
        "position_counts": {},
        "first_time": encounter_time,
        "last_time": None,
        "notes": [],
    })
    partner["name_snapshot"] = partner_name
    partner["encounter_count"] = int(partner.get("encounter_count", 0) or 0) + count
    position_counts = partner.setdefault("position_counts", {})
    position_counts[position_id] = int(position_counts.get(position_id, 0) or 0) + count
    partner.setdefault("first_time", encounter_time)
    partner["last_time"] = encounter_time
    if notes:
        partner_notes = partner.setdefault("notes", [])
        if isinstance(partner_notes, list):
            partner_notes.extend(notes)
            partner["notes"] = partner_notes[-50:]

    position_totals = history.setdefault("position_totals", {})
    if not isinstance(position_totals, dict):
        position_totals = {}
        history["position_totals"] = position_totals
    position_totals[position_id] = int(position_totals.get(position_id, 0) or 0) + count
    history["total_encounter_count"] = int(history.get("total_encounter_count", 0) or 0) + count
    history["total_partner_count"] = len(partners)
    history["last_encounter_time"] = encounter_time
    character["updated_at"] = _now_iso()
    return character


def append_reproductive_content(state: dict[str, Any], character_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    target = _clean_string(payload.get("target"))
    field = REPRODUCTIVE_CONTENT_TARGETS.get(target)
    if not field:
        raise HTTPException(422, "target 必须是 stomach/intestine/uterus")
    content_type = _clean_string(payload.get("content_type"), "unknown")
    if content_type not in BODY_CONTENT_TYPES:
        raise HTTPException(422, f"未知内容物类型：{content_type}")
    source_id = _clean_string(payload.get("source_character_id"))
    source_name = _source_character_snapshot(state, source_id, payload.get("source_name_snapshot", ""))
    character = get_character(state, character_id)
    _require_adult_character(character)
    amount = _normalize_count(payload.get("amount", 1), field_name="amount")
    received_time = normalize_time_point(payload.get("received_time") if isinstance(payload.get("received_time"), dict) else None, state)
    raw_expires = payload.get("expires_time") if isinstance(payload.get("expires_time"), dict) else None
    expires_time = normalize_time_point(raw_expires, state) if raw_expires else add_to_time_point(received_time, **DEFAULT_CONTENT_EXPIRY[target])
    entry = {
        "content_type": content_type,
        "content_label": BODY_CONTENT_TYPES[content_type],
        "source_character_id": source_id,
        "source_name_snapshot": source_name,
        "amount": amount,
        "received_time": received_time,
        "expires_time": expires_time,
        "tags": _clean_string_list(payload.get("tags")),
    }
    if target == "uterus":
        fertility_context = payload.get("fertility_context") if isinstance(payload.get("fertility_context"), dict) else {}
        entry["fertility_context"] = deepcopy(fertility_context)
    contents = _ensure_component(character, "reproductive_contents")
    bucket = contents.setdefault(field, [])
    if not isinstance(bucket, list):
        bucket = []
        contents[field] = bucket
    bucket.append(entry)
    character["updated_at"] = _now_iso()
    return character


def clear_expired_reproductive_contents(state: dict[str, Any], character_id: str, now: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, int]]:
    character = get_character(state, character_id)
    _require_adult_character(character)
    contents = _ensure_component(character, "reproductive_contents")
    now_key = time_key(normalize_time_point(now, state))
    removed: dict[str, int] = {}
    for field in REPRODUCTIVE_CONTENT_TARGETS.values():
        bucket = contents.get(field)
        if not isinstance(bucket, list):
            contents[field] = []
            removed[field] = 0
            continue
        kept = []
        count = 0
        for entry in bucket:
            expires = entry.get("expires_time") if isinstance(entry, dict) else None
            if isinstance(expires, dict) and time_key(expires) <= now_key:
                count += 1
            else:
                kept.append(entry)
        contents[field] = kept
        removed[field] = count
    character["updated_at"] = _now_iso()
    return character, removed


def _next_character_id(state: dict[str, Any]) -> str:
    normalize_characters(state)
    next_id = int(state["characters"].get("next_id", 1) or 1)
    state["characters"]["next_id"] = next_id + 1
    return f"char_{next_id}"


def _reject_reserved_or_lord(state: dict[str, Any], character_id: str, name: str) -> None:
    if character_id in RESERVED_CHARACTER_IDS:
        raise HTTPException(422, "人物账册只记录非玩家人物，不能使用 user/player/lord 作为人物 id")
    lord_name = _clean_string(state.get("lord_name"))
    if lord_name and name == lord_name:
        raise HTTPException(422, "人物账册只记录非玩家人物，领主本人不应写入 NPC 人物账册")


def create_character(state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    normalize_characters(state)
    character_id = _clean_string(payload.get("id")) or _next_character_id(state)
    name = _clean_string(payload.get("name"))
    if not name:
        raise HTTPException(422, "创建人物必须提供 name")
    _reject_reserved_or_lord(state, character_id, name)
    try:
        get_character(state, character_id)
    except KeyError:
        pass
    else:
        raise HTTPException(409, "人物 id 已存在")
    now = _now_iso()
    character = normalize_character_entry({
        **payload,
        "id": character_id,
        "name": name,
        "created_time": time_point_from_state(state),
        "created_at": now,
        "updated_at": now,
    })
    state["characters"]["entries"].append(character)
    return character


def update_character(state: dict[str, Any], character_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    character = get_character(state, character_id)
    updated = {**character, **{key: value for key, value in patch.items() if value is not None}}
    updated["id"] = character_id
    updated["name"] = _clean_string(updated.get("name"), character.get("name"))
    _reject_reserved_or_lord(state, character_id, updated["name"])
    updated["updated_at"] = _now_iso()
    character.clear()
    character.update(normalize_character_entry(updated))
    return character


def append_memory(state: dict[str, Any], character_id: str, entries: list[str]) -> dict[str, Any]:
    character = get_character(state, character_id)
    current = _clean_string_list(character.get("memories"))
    current.extend(_clean_string_list(entries))
    character["memories"] = current[-200:]
    character["memory"] = {**_structured_block(character.get("memory")), "entries": character["memories"]}
    character["updated_at"] = _now_iso()
    character.update(normalize_character_entry(character))
    return character


def patch_component(state: dict[str, Any], character_id: str, component_id: str, values: dict[str, Any]) -> dict[str, Any]:
    if not component_id or "/" in component_id:
        raise HTTPException(422, "component_id 不合法")
    character = get_character(state, character_id)
    components = character.setdefault("components", {})
    current = components.get(component_id)
    if not isinstance(current, dict):
        current = deepcopy(COMPONENT_DEFAULTS.get(component_id, {}))
    current.update(deepcopy(values))
    components[component_id] = current
    character["updated_at"] = _now_iso()
    character.update(normalize_character_entry(character))
    refresh_realm_item_effects(state)
    return character


def upsert_character(state: dict[str, Any], payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    character_id = _clean_string(payload.get("id"))
    if character_id:
        try:
            return update_character(state, character_id, payload), False
        except KeyError:
            return create_character(state, payload), True
    return create_character(state, payload), True


def public_items_catalog() -> dict[str, Any]:
    return {
        "items": deepcopy(ITEMS),
        "attribute_ids": deepcopy(ATTRIBUTE_IDS),
        "equipment_slots": deepcopy(EQUIPMENT_SLOT_REGISTRY),
        "public_equipment_slots": list(PUBLIC_EQUIPMENT_SLOTS),
        "private_equipment_slots": list(PRIVATE_EQUIPMENT_SLOTS),
        "accessory_equipment_slots": list(ACCESSORY_EQUIPMENT_SLOTS),
        "body_slot_presets": deepcopy(BODY_SLOT_PRESETS),
    }


def armor_for_body_part(character: dict[str, Any], body_part: str) -> int:
    normalized = normalize_character_entry(character)
    slot = _normalize_equipment_slot(body_part)
    if not slot:
        return 0
    item_id = normalized.get("components", {}).get("equipment", {}).get("slots", {}).get(slot)
    if not item_id:
        return 0
    return int(ITEMS.get(item_id, {}).get("armor", 0) or 0)


def refresh_realm_item_effects(state: dict[str, Any]) -> dict[str, Any]:
    resources = state.setdefault("resources", {})
    realm_modifiers = {key: 0 for key in RESOURCES}
    sources: list[dict[str, Any]] = []
    normalize_lord_components(state)
    lord_equipment = state.get("lord_components", {}).get("equipment", {})
    if isinstance(lord_equipment, dict):
        effects = lord_equipment.get("realm_effects") if isinstance(lord_equipment.get("realm_effects"), dict) else {}
        for resource, delta in effects.items():
            if resource not in realm_modifiers:
                continue
            amount = int(delta or 0)
            realm_modifiers[resource] += amount
            if amount:
                sources.append({
                    "character_id": "player_lord",
                    "character_name": state.get("lord_name") or "领主",
                    "resource": resource,
                    "delta": amount,
                })
    entries = state.get("characters", {}).get("entries", [])
    if isinstance(entries, list):
        for character in entries:
            if not isinstance(character, dict):
                continue
            equipment = character.get("components", {}).get("equipment", {})
            if not isinstance(equipment, dict):
                continue
            effects = equipment.get("realm_effects") if isinstance(equipment.get("realm_effects"), dict) else {}
            for resource, delta in effects.items():
                if resource not in realm_modifiers:
                    continue
                amount = int(delta or 0)
                realm_modifiers[resource] += amount
                if amount:
                    sources.append({
                        "character_id": character.get("id"),
                        "character_name": character.get("name"),
                        "resource": resource,
                        "delta": amount,
                    })
    compact_modifiers = {key: value for key, value in realm_modifiers.items() if value}
    state["item_effects"] = {"realm_resource_modifiers": compact_modifiers, "sources": sources}
    state["effective_resources"] = {
        key: int(resources.get(key, 0) or 0) + int(compact_modifiers.get(key, 0) or 0)
        for key in RESOURCES
    }
    return state["item_effects"]


def _is_lord_item_target(character_id: str) -> bool:
    return _clean_string(character_id) in LORD_ITEM_CHARACTER_IDS


def _lord_item_target(state: dict[str, Any]) -> dict[str, Any]:
    normalize_lord_components(state)
    return {
        "id": "player_lord",
        "kind": "knight",
        "name": state.get("lord_name") or "领主",
        "role": "领主",
        "gender": state.get("lord_gender") or "未说明",
        "components": deepcopy(state["lord_components"]),
    }


def _commit_lord_item_target(state: dict[str, Any], character: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_character_entry(character)
    state["lord_components"] = normalized["components"]
    state["lord_equipment_updated_at"] = _now_iso()
    return public_lord_components(state)


def grant_item(state: dict[str, Any], character_id: str, item_id: str, quantity: int = 1) -> dict[str, Any]:
    item_id = _clean_string(item_id)
    _item_catalog_entry(item_id)
    quantity = _normalize_count(quantity, field_name="quantity", minimum=1, maximum=1000)
    if _is_lord_item_target(character_id):
        character = _lord_item_target(state)
        inventory = _ensure_component(character, "inventory")
        items = _normalize_inventory_items(inventory.get("items"))
        items.append({"item_id": item_id, "quantity": quantity})
        _set_inventory_items(character, items)
        committed = _commit_lord_item_target(state, character)
        refresh_realm_item_effects(state)
        return committed
    character = get_character(state, character_id)
    inventory = _ensure_component(character, "inventory")
    items = _normalize_inventory_items(inventory.get("items"))
    items.append({"item_id": item_id, "quantity": quantity})
    _set_inventory_items(character, items)
    character["updated_at"] = _now_iso()
    character.update(normalize_character_entry(character))
    refresh_realm_item_effects(state)
    return character


def equip_item(state: dict[str, Any], character_id: str, item_id: str, slot: str = "", auto_add: bool = True) -> dict[str, Any]:
    item_id = _clean_string(item_id)
    _item_catalog_entry(item_id)
    if _is_lord_item_target(character_id):
        character = _lord_item_target(state)
        if _inventory_quantity(character, item_id) <= 0:
            if not auto_add:
                raise HTTPException(422, f"领主背包中没有物品：{item_id}")
            inventory = _ensure_component(character, "inventory")
            items = _normalize_inventory_items(inventory.get("items"))
            items.append({"item_id": item_id, "quantity": 1})
            _set_inventory_items(character, items)
        _equip_item_on_character_record(character, item_id, slot)
        committed = _commit_lord_item_target(state, character)
        refresh_realm_item_effects(state)
        return committed
    character = get_character(state, character_id)
    if _inventory_quantity(character, item_id) <= 0:
        if not auto_add:
            raise HTTPException(422, f"人物背包中没有物品：{item_id}")
        grant_item(state, character_id, item_id, 1)
        character = get_character(state, character_id)
    _equip_item_on_character_record(character, item_id, slot)
    character["updated_at"] = _now_iso()
    character.update(normalize_character_entry(character))
    refresh_realm_item_effects(state)
    return character


def unequip_item(state: dict[str, Any], character_id: str, slot: str = "", item_id: str = "") -> dict[str, Any]:
    if _is_lord_item_target(character_id):
        character = _lord_item_target(state)
        equipment = _ensure_component(character, "equipment")
        slots = equipment.setdefault("slots", {})
        if not isinstance(slots, dict):
            slots = {}
            equipment["slots"] = slots
        slot = _normalize_equipment_slot(slot)
        item_id = _clean_string(item_id)
        if slot:
            equipped_item_id = slots.get(slot)
            if equipped_item_id:
                for existing_slot, existing_item_id in list(slots.items()):
                    if existing_item_id == equipped_item_id:
                        slots.pop(existing_slot, None)
        elif item_id:
            for existing_slot, equipped_item_id in list(slots.items()):
                if equipped_item_id == item_id:
                    slots.pop(existing_slot, None)
        else:
            raise HTTPException(422, "必须提供 slot 或 item_id")
        committed = _commit_lord_item_target(state, character)
        refresh_realm_item_effects(state)
        return committed
    character = get_character(state, character_id)
    equipment = _ensure_component(character, "equipment")
    slots = equipment.setdefault("slots", {})
    if not isinstance(slots, dict):
        slots = {}
        equipment["slots"] = slots
    slot = _normalize_equipment_slot(slot)
    item_id = _clean_string(item_id)
    if slot:
        equipped_item_id = slots.get(slot)
        if equipped_item_id:
            for existing_slot, existing_item_id in list(slots.items()):
                if existing_item_id == equipped_item_id:
                    slots.pop(existing_slot, None)
    elif item_id:
        for existing_slot, equipped_item_id in list(slots.items()):
            if equipped_item_id == item_id:
                slots.pop(existing_slot, None)
    else:
        raise HTTPException(422, "必须提供 slot 或 item_id")
    character["updated_at"] = _now_iso()
    character.update(normalize_character_entry(character))
    refresh_realm_item_effects(state)
    return character
