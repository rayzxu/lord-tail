from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "characters"


def _read(name: str) -> dict[str, Any]:
    path = DATA_DIR / name
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"人物配置根节点必须是对象：{path}")
    return value


@lru_cache(maxsize=1)
def _character_registry_cached() -> dict[str, Any]:
    return _read("registry.json")


@lru_cache(maxsize=1)
def _anatomy_cached() -> dict[str, Any]:
    return _read("anatomy.json")


@lru_cache(maxsize=1)
def _equipment_slots_cached() -> dict[str, Any]:
    return _read("equipment_slots.json")


def load_character_registry() -> dict[str, Any]:
    return deepcopy(_character_registry_cached())


def load_anatomy() -> dict[str, Any]:
    return deepcopy(_anatomy_cached())


def load_equipment_slots() -> dict[str, Any]:
    return deepcopy(_equipment_slots_cached())


def clear_character_config_cache() -> None:
    _character_registry_cached.cache_clear()
    _anatomy_cached.cache_clear()
    _equipment_slots_cached.cache_clear()


def validate_character_configs() -> None:
    registry = load_character_registry()
    anatomy = load_anatomy().get("body_parts", {})
    equipment = load_equipment_slots()
    slots = equipment.get("slots", {})
    if int(registry.get("schema_version", 0)) != 1:
        raise ValueError("characters/registry.json schema_version 必须为 1")
    if not registry.get("attributes") or not registry.get("kinds") or not registry.get("components"):
        raise ValueError("人物 registry 必须包含 attributes/kinds/components")
    for kind_id, kind in registry["kinds"].items():
        unknown = set(kind.get("components", [])) - set(registry["components"])
        if unknown:
            raise ValueError(f"人物 kind {kind_id} 引用未知 component：{sorted(unknown)}")
    aliases = equipment.get("aliases", {})
    if set(aliases) & set(slots):
        raise ValueError("装备槽位 alias 不能遮蔽正式 slot id")
    if len(set(aliases)) != len(aliases):
        raise ValueError("装备槽位 alias 必须唯一")
    for slot_id, slot in slots.items():
        body_part_id = slot.get("body_part_id")
        if not slot.get("virtual") and body_part_id not in anatomy:
            raise ValueError(f"装备槽位 {slot_id} 引用未知身体部位 {body_part_id}")
    for preset_id, preset in equipment.get("presets", {}).items():
        unknown = set(preset.get("slots", [])) - set(slots)
        if unknown:
            raise ValueError(f"身体槽位 preset {preset_id} 引用未知槽位：{sorted(unknown)}")
