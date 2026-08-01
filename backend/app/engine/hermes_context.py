from __future__ import annotations

import json
import os
from typing import Any

from ..catalog import BUILDINGS, ITEMS, RESOURCES, UNITS
from ..ai.analysis import analyze_realm
from .history import select_history_context
from ..systems import characters, scheduled_events

DESCRIPTION_MODES = {"describe_realm", "describe_lord", "describe_tile", "describe_item"}
STORYLET_MODES = {"storylet_opening", "storylet_result"}
STRATEGIC_MODES = {"strategic_turn"}
SCENE_MODES = {"scene_step"}


def _compact_demographics(state: dict[str, Any]) -> dict[str, Any]:
    demographics = state.get("demographics", {})
    classes = demographics.get("classes", {})
    return {
        "classes": {
            class_id: {
                "name": item.get("name"),
                "population": item.get("population", 0),
                "wealth_per_capita": item.get("wealth_per_capita", 0),
                "morale": item.get("morale", 0),
                "last_births": item.get("last_births", 0),
                "last_migration": item.get("last_migration", 0),
                "last_outflow": item.get("last_outflow", 0),
            }
            for class_id, item in classes.items()
        },
        "housing": demographics.get("housing", {}),
    }


def _selected_tile(state: dict[str, Any], client_context: dict[str, Any] | None) -> dict[str, Any] | None:
    tile_info = (client_context or {}).get("selected_tile")
    if not isinstance(tile_info, dict):
        return None
    x, y = tile_info.get("x"), tile_info.get("y")
    map_source = tile_info.get("map_source") or (client_context or {}).get("map_source") or "realm"
    tiles = state.get("diplomacy_map", []) if map_source == "diplomacy" else state.get("map", [])
    return next((tile for tile in tiles if tile.get("x") == x and tile.get("y") == y), tile_info)


def compact_state_for_agent(state: dict[str, Any], client_context: dict[str, Any] | None = None) -> dict[str, Any]:
    selected_tile = _selected_tile(state, client_context)
    history_tiles = [f"{selected_tile.get('x')}:{selected_tile.get('y')}"] if selected_tile else None
    storylet_instances = state.get("storylets", {}).get("instances", [])
    return {
        "realm": {
            "name": state.get("realm_name"),
            "turn": state.get("turn"),
            "season": state.get("season"),
            "weather": state.get("weather"),
        },
        "time": state.get("time", {}),
        "game_mode": state.get("game_mode", "strategic"),
        "active_scene": state.get("active_scene"),
        "lord": {
            "name": state.get("lord_name"),
            "gender": state.get("lord_gender"),
            "appearance": state.get("appearance"),
            "personality": state.get("personality"),
            "talents": state.get("talents", []),
            "components": state.get("lord_components", {}),
        },
        "resources": state.get("resources", {}),
        "effective_resources": state.get("effective_resources", state.get("resources", {})),
        "item_effects": state.get("item_effects", {}),
        "changes": state.get("changes", {}),
        "buildings": state.get("buildings", {}),
        "army": state.get("army", {}),
        "army_status": state.get("army_status", {}),
        "diplomacy": state.get("diplomacy", {}),
        "faction_states": state.get("faction_states", {}),
        "characters": characters.list_characters(state, include_inactive=False)[:30],
        "demographics": _compact_demographics(state),
        "selected_tile": selected_tile,
        "realm_map": {
            "visible_tiles": state.get("map", [])[:100],
        },
        "diplomacy_map": {
            "visible_tiles": state.get("diplomacy_map", [])[:100],
        },
        "recent_events": state.get("recent_events", [])[-20:],
        "scheduled_event_context": scheduled_events.event_context(state),
        "council": state.get("council", {}),
        "strategic_directive": state.get("strategic_directive"),
        "management_ai": state.get("management_ai", {}),
        "management_analysis": analyze_realm(state),
        "storylets": {
            "current_instance_id": state.get("storylets", {}).get("current_instance_id"),
            "active_or_recent": [
                {key: value for key, value in item.items() if key not in {"result"}}
                for item in storylet_instances[-8:]
                if isinstance(item, dict)
            ],
        },
        "history_context": select_history_context(
            state,
            tiles=history_tiles,
            min_importance=3,
            limit=12,
        ),
        "allowed_actions": public_action_contract(),
    }


def public_action_contract() -> dict[str, Any]:
    return {
        "base_url": os.getenv("LORD_TAIL_AGENT_API_BASE_URL", "http://127.0.0.1:8000"),
        "global_rules": [
            "story_turn 中任何状态改变必须调用 Lord Tail HTTP API，最终回答不得输出 JSON actions/state_patch。",
            "每次成功调用 /api/state/* mutation 后，必须调用 /api/agent/events 记录事件。",
            "如果叙事产生会影响后续的承诺、羞辱、仇恨、战功、灾害、NPC 命运或外交后果，必须调用 /api/state/history 记入编年史。",
            "如果叙事中出现新的非玩家人物，或既有人物的外貌、性格、身份、关系、立场、所在地、状态、重要记忆发生变化，必须调用 /api/state/characters 或 PATCH /api/state/characters/{id} 更新人物账册。",
            "不存在的建筑、兵种、资源或系统 API 不得伪造；只调用 /api/agent/events 记录 catalog/api gap。",
            "description 模式只读，不得调用 mutation API。",
        ],
        "scene_skill_map": {
            "daily": "lord-tail-daily",
            "construction": "lord-tail-construction",
            "population": "lord-tail-population",
            "economy": "lord-tail-economy",
            "talent": "lord-tail-talent",
            "weather_season": "lord-tail-weather-season",
            "food_shortage": "lord-tail-food-shortage",
            "plague": "lord-tail-plague",
            "fire": "lord-tail-fire",
            "disaster": "lord-tail-disaster",
            "tax": "lord-tail-tax",
            "conscription": "lord-tail-conscription",
            "caravan": "lord-tail-caravan",
            "statue": "lord-tail-statue",
            "diplomacy_positive": "lord-tail-diplomacy-positive",
            "diplomacy_negative": "lord-tail-diplomacy-negative",
            "diplomacy": "lord-tail-diplomacy",
            "battle_archers": "lord-tail-battle-archers",
            "battle_infantry": "lord-tail-battle-infantry",
            "battle_cavalry": "lord-tail-battle-cavalry",
            "military": "lord-tail-military",
            "description": "lord-tail-description",
            "character": "lord-tail-character",
            "items": "lord-tail-items",
            "equipment": "lord-tail-items",
            "time": "lord-tail-time",
            "scene": "lord-tail-scene",
            "storylet": "lord-tail-storylet",
            "strategic_turn": "lord-tail-strategic-turn",
            "scene_dialogue": "lord-tail-scene-dialogue",
            "scene_battle": "lord-tail-scene-battle",
            "scene_diplomacy": "lord-tail-scene-diplomacy",
            "council": "lord-tail-council",
        },
        "ids": {
            "resources": list(RESOURCES.keys()),
            "buildings": list(BUILDINGS.keys()),
            "units": list(UNITS.keys()),
            "items": list(ITEMS.keys()),
            "character_attributes": list(characters.ATTRIBUTE_IDS.keys()),
            "equipment_slots": list(characters.EQUIPMENT_SLOT_REGISTRY.keys()),
            "diplomacy_statuses": ["友善", "中立", "敌对", "战争"],
            "event_severities": ["info", "warning", "critical"],
        },
        "resources": list(RESOURCES.keys()),
        "buildings": list(BUILDINGS.keys()),
        "units": list(UNITS.keys()),
        "apis": {
            "read_state": {"method": "GET", "path": "/api/state"},
            "read_time": {"method": "GET", "path": "/api/time"},
            "time_advance": {
                "method": "POST",
                "path": "/api/state/time/advance",
                "payload": {"days": 0, "hours": 2, "minutes": 0, "reason": "叙事中时间流逝两小时", "run_due_strategic_turns": True, "source": "hermes"},
            },
            "read_context": {"method": "GET", "path": "/api/agent/context"},
            "describe_context": {"method": "GET", "path": "/api/agent/describe-context"},
            "strategic_turn": {
                "method": "POST",
                "path": "/api/game/strategic-turn",
                "payload": {"command": "让领地按当前安排运转九天", "source": "hermes"},
            },
            "council_read": {"method": "GET", "path": "/api/council/current"},
            "council_resolve": {
                "method": "POST",
                "path": "/api/council/{meeting_id}/resolve",
                "payload": {"proposal_id": "finance_food_security", "management_mode": "delegated"},
            },
            "strategy_read": {"method": "GET", "path": "/api/strategy/current"},
            "strategy_analysis": {"method": "GET", "path": "/api/strategy/analysis"},
            "strategy_advice": {"method": "GET", "path": "/api/strategy/advice"},
            "legal_actions": {"method": "GET", "path": "/api/actions/legal"},
            "execute_action": {
                "method": "POST",
                "path": "/api/actions/execute",
                "payload": {"actor": "hermes", "action": {"type": "wait", "payload": {"reason": "player_order"}}},
            },
            "scene_start": {
                "method": "POST",
                "path": "/api/game/scenes",
                "payload": {"type": "dialogue", "title": "接见管家", "participants": []},
            },
            "scene_step": {
                "method": "POST",
                "path": "/api/game/scenes/current/step",
                "payload": {"input": "玩家命令", "narrative": "场景叙事", "events": []},
            },
            "scene_advance_time": {
                "method": "POST",
                "path": "/api/game/scenes/current/advance-time",
                "payload": {"hours": 0, "minutes": 0, "days": 1, "reason": "玩家说第二天", "run_due_strategic_turns": True},
            },
            "scene_end": {
                "method": "POST",
                "path": "/api/game/scenes/current/end",
                "payload": {"summary": "当前事件已经完成。", "outcome": {}},
            },
            "resources": {
                "method": "POST",
                "path": "/api/state/resources",
                "payload": {"changes": {"gold": 10}, "values": {"food": 300}},
            },
            "population": {"method": "POST", "path": "/api/state/population", "payload": {"delta": 5, "value": 120}},
            "morale": {"method": "POST", "path": "/api/state/morale", "payload": {"delta": -5, "value": 70}},
            "army": {"method": "POST", "path": "/api/state/army", "payload": {"unit": "infantry", "delta": 3}},
            "diplomacy": {"method": "POST", "path": "/api/state/diplomacy", "payload": {"faction": "金鳞", "status": "友善"}},
            "buildings": {
                "method": "POST",
                "path": "/api/state/buildings",
                "payload": {"building": "farm", "action": "build", "count": 1, "x": 5, "y": 4},
            },
            "battle_resolve": {
                "method": "POST",
                "path": "/api/state/battles/resolve",
                "payload": {
                    "player": {"cavalry": 1},
                    "enemy": {"infantry": 3},
                    "enemy_organization": 100,
                    "terrain": "grass",
                    "stance": "aggressive",
                    "source": "hermes",
                    "label": "骑兵冲击三名步兵",
                },
            },
            "events": {
                "method": "POST",
                "path": "/api/agent/events",
                "payload": {
                    "phase": "events",
                    "kind": "merchant_arrived",
                    "severity": "info",
                    "message": "...",
                    "data": {},
                },
            },
            "history_read": {"method": "GET", "path": "/api/history"},
            "characters_read": {"method": "GET", "path": "/api/characters"},
            "characters_registry": {"method": "GET", "path": "/api/characters/registry"},
            "character_kinds": {"method": "GET", "path": "/api/characters/kinds"},
            "items_read": {"method": "GET", "path": "/api/items"},
            "lord_components_read": {"method": "GET", "path": "/api/lord/components"},
            "lord_item_grant": {
                "method": "POST",
                "path": "/api/state/lord/items",
                "payload": {"item_id": "steward_ring", "quantity": 1, "created_by": "hermes"},
            },
            "lord_item_equip": {
                "method": "POST",
                "path": "/api/state/lord/equipment/equip",
                "payload": {"item_id": "grain_tithe_seal", "slot": "accessory_1", "auto_add": True, "created_by": "hermes"},
            },
            "lord_item_unequip": {
                "method": "POST",
                "path": "/api/state/lord/equipment/unequip",
                "payload": {"slot": "accessory_1", "created_by": "hermes"},
            },
            "character_detail": {"method": "GET", "path": "/api/characters/{character_id}"},
            "character_upsert": {
                "method": "POST",
                "path": "/api/state/characters",
                "payload": {
                    "id": "optional-stable-id",
                    "name": "玛尔塔",
                    "role": "管家",
                    "gender": "女",
                    "age": 42,
                    "faction": "黑泥堡",
                    "location": "领主堡垒",
                    "status": "active",
                    "appearance_md": "灰发，穿旧羊毛裙，腰间挂钥匙。",
                    "personality_md": "谨慎、记仇、擅长账目。",
                    "description_md": "可展示给玩家的人物描述。",
                    "relationship_to_lord": "惧怕但依赖领主权威",
                    "disposition": -10,
                    "traits": ["管家", "识字"],
                    "memories": ["第1日被领主当众斥责"],
                    "flags": {},
                },
            },
            "character_patch": {
                "method": "PATCH",
                "path": "/api/state/characters/{character_id}",
                "payload": {"location": "地牢门外", "disposition": -30, "memories": ["被迫为审讯作证"]},
            },
            "character_memory_append": {
                "method": "POST",
                "path": "/api/state/characters/{character_id}/memory",
                "payload": {"entry": "第1日被领主当众斥责。", "created_by": "hermes"},
            },
            "character_component_patch": {
                "method": "PATCH",
                "path": "/api/state/characters/{character_id}/components/{component_id}",
                "payload": {"values": {"stress": 10}, "created_by": "hermes"},
                "rules": ["普通组件可局部 PATCH；sexual_history/reproductive_contents 不要直接 PATCH，使用专用 API"],
            },
            "character_item_grant": {
                "method": "POST",
                "path": "/api/state/characters/{character_id}/items",
                "payload": {"item_id": "rusty_sword", "quantity": 1, "created_by": "hermes"},
                "rules": ["item_id 必须来自 /api/items 或 allowed_actions.ids.items"],
            },
            "character_item_equip": {
                "method": "POST",
                "path": "/api/state/characters/{character_id}/equipment/equip",
                "payload": {"item_id": "rusty_sword", "slot": "right_hand", "auto_add": True, "created_by": "hermes"},
                "rules": [
                    "装备后后端会重算 components.attributes.effective、components.equipment、state.item_effects 和 state.effective_resources",
                    "auto_add=true 可在叙事授予装备时同时入账；已有物品时也可用",
                ],
            },
            "character_item_unequip": {
                "method": "POST",
                "path": "/api/state/characters/{character_id}/equipment/unequip",
                "payload": {"slot": "right_hand", "item_id": "", "created_by": "hermes"},
                "rules": ["提供 slot 或 item_id 二选一"],
            },
            "character_sexual_encounter": {
                "method": "POST",
                "path": "/api/state/characters/{character_id}/sexual-encounters",
                "payload": {
                    "partner_character_id": "char_2",
                    "partner_name_snapshot": "奥托",
                    "position_id": "missionary",
                    "count": 1,
                    "notes": ["剧情后果标签"],
                    "created_by": "hermes",
                },
                "rules": [
                    "只能用于已明确成年的人物",
                    "position_id 从 /api/characters/registry.sex_position_ids 读取",
                    "不要直接 PATCH components.sexual_history",
                ],
            },
            "character_reproductive_content": {
                "method": "POST",
                "path": "/api/state/characters/{character_id}/reproductive-contents",
                "payload": {
                    "target": "uterus",
                    "content_type": "semen",
                    "source_character_id": "char_2",
                    "source_name_snapshot": "奥托",
                    "amount": 1,
                    "tags": ["剧情后果标签"],
                    "created_by": "hermes",
                },
                "rules": [
                    "target 只能是 stomach/intestine/uterus",
                    "content_type 从 /api/characters/registry.body_content_types 读取，包含 semen/urine/food/water/wine/medicine/poison/blood/bile/parasite/unknown",
                    "只能用于已明确成年的人物",
                    "不要直接 PATCH components.reproductive_contents",
                ],
            },
            "character_reproductive_contents_clear_expired": {
                "method": "POST",
                "path": "/api/state/characters/{character_id}/reproductive-contents/clear-expired",
                "payload": {},
            },
            "history_record": {
                "method": "POST",
                "path": "/api/state/history",
                "payload": {
                    "title": "商队首领被羞辱",
                    "summary_md": "南方商队首领在黑逼堡大厅被迫跪在泥水里。",
                    "details_md": "",
                    "source": "scene",
                    "importance": 4,
                    "visibility": "player",
                    "tags": ["caravan", "lord_event"],
                    "related": {"people": [], "factions": ["南方商队"], "tiles": []},
                    "created_by": "hermes",
                },
            },
            "events_read": {"method": "GET", "path": "/api/events"},
            "storylets_read": {"method": "GET", "path": "/api/storylets"},
            "storylet_current": {"method": "GET", "path": "/api/storylets/current"},
            "storylet_detail": {"method": "GET", "path": "/api/storylets/{story_event_id}"},
            "event_schedule": {
                "method": "POST",
                "path": "/api/state/events/schedule",
                "payload": {
                    "event_type": "enemy_arrival",
                    "title": "北方掠夺者逼近",
                    "description_md": "斥候报告，敌人将在二十七日后抵达。",
                    "in_days": 27,
                    "clock_24": "08:00",
                    "visibility": "player",
                    "importance": 5,
                    "related": {"factions": ["北方掠夺者"], "tiles": []},
                    "created_by": "hermes",
                },
            },
            "event_check_due": {"method": "POST", "path": "/api/state/events/check-due"},
            "event_cancel": {"method": "POST", "path": "/api/state/events/{event_id}/cancel", "payload": {"reason_md": "取消原因", "cancelled_by": "hermes"}},
            "event_reschedule": {"method": "POST", "path": "/api/state/events/{event_id}/reschedule", "payload": {"in_days": 9, "clock_24": "16:00", "reason_md": "改期原因"}},
            "event_resolve": {"method": "POST", "path": "/api/state/events/{event_id}/resolve", "payload": {"result_md": "事件结果", "outcome": {}, "resolved_by": "hermes"}},
        },
        "scene_playbooks": {
            "construction": ["POST /api/state/buildings", "POST /api/agent/events"],
            "population": ["POST /api/state/population", "POST /api/state/morale when social impact exists", "POST /api/agent/events"],
            "economy": ["POST /api/state/resources", "POST /api/agent/events"],
            "talent": ["POST matching /api/state/* if talent changes state", "POST /api/agent/events"],
            "disaster_food_shortage": ["POST /api/state/resources", "POST /api/state/morale", "POST /api/agent/events"],
            "disaster_plague": ["POST /api/state/population", "POST /api/state/morale", "POST /api/agent/events"],
            "disaster_fire": ["POST /api/state/resources", "POST /api/state/morale", "POST /api/agent/events"],
            "weather_season": ["天气和季节由后端战略推进自动结算；只在叙事备注时 POST /api/agent/events"],
            "tax": ["POST /api/state/resources", "POST /api/state/morale", "POST /api/agent/events"],
            "conscription": ["POST /api/state/army", "POST /api/state/population", "POST /api/state/resources for cost", "POST /api/agent/events"],
            "caravan": ["POST /api/state/resources", "POST /api/state/diplomacy if faction relation changes", "POST /api/agent/events", "POST /api/state/history when the visit creates a lasting promise, insult, debt, cancellation, or named NPC consequence"],
            "npc_or_dialogue": ["POST /api/state/characters when a named non-player character appears or changes", "POST /api/game/scenes/current/step", "POST /api/state/history for important NPC consequences", "POST /api/agent/events"],
            "character": ["GET /api/characters to check existing people", "POST /api/state/characters for new named non-player characters", "PATCH /api/state/characters/{character_id} for updates", "POST /api/state/history for lasting consequences", "POST /api/agent/events"],
            "items_equipment": ["GET /api/items", "POST /api/state/lord/items or /api/state/characters/{character_id}/items when item is gained", "POST /api/state/lord/equipment/equip or /api/state/characters/{character_id}/equipment/equip when item is worn or wielded", "POST /api/state/lord/equipment/unequip or /api/state/characters/{character_id}/equipment/unequip when removed", "POST /api/agent/events"],
            "diplomacy_positive": ["POST /api/state/resources if gift", "POST /api/state/diplomacy", "POST /api/agent/events"],
            "diplomacy_negative": ["POST /api/state/diplomacy", "POST /api/agent/events", "POST /api/state/history when the diplomatic slight, treaty, threat, or promise should affect later scenes"],
            "battle_archers": ["POST /api/state/battles/resolve", "POST /api/agent/events after successful battle resolution", "POST /api/state/history for notable valor, rout, named casualties, or strategic outcome"],
            "battle_infantry": ["POST /api/state/battles/resolve", "POST /api/agent/events after successful battle resolution", "POST /api/state/history for notable valor, rout, named casualties, or strategic outcome"],
            "battle_cavalry": ["POST /api/state/battles/resolve", "POST /api/agent/events after successful battle resolution", "POST /api/state/history for notable valor, rout, named casualties, or strategic outcome"],
            "statue": ["POST /api/agent/events only; no statue building id exists"],
            "strategic_turn": ["POST /api/game/strategic-turn"],
            "council": ["GET /api/council/current", "POST /api/council/{meeting_id}/resolve only after the player explicitly chooses a proposal", "GET /api/strategy/analysis"],
            "scene_step": ["POST /api/game/scenes if no active scene", "POST /api/game/scenes/current/step", "POST /api/game/scenes/current/advance-time only when time explicitly passes", "POST /api/game/scenes/current/end only when the event is complete"],
            "scene_battle": ["POST /api/game/scenes if no active battle scene", "POST /api/state/battles/resolve for decisive combat exchange", "POST /api/game/scenes/current/step", "POST /api/game/scenes/current/end when battle is resolved"],
        },
    }


def catalog_summary() -> dict[str, Any]:
    return {
        "resources": {key: {"name": value.get("name"), "description": value.get("description")} for key, value in RESOURCES.items()},
        "buildings": {
            key: {
                "name": value.get("name"),
                "description": value.get("description"),
                "cost": value.get("cost", {}),
                "production": value.get("production", {}),
                "maintenance": value.get("maintenance", {}),
                "construction_turns": value.get("construction_turns"),
                "workforce": value.get("workforce"),
                "housing": value.get("housing", {}),
            }
            for key, value in BUILDINGS.items()
        },
        "units": {
            key: {
                "name": value.get("name"),
                "description": value.get("description"),
                "cost": value.get("cost", {}),
                "upkeep": value.get("upkeep", {}),
                "combat": value.get("combat", {}),
            }
            for key, value in UNITS.items()
        },
        "items": {
            key: {
                "name": value.get("name"),
                "type": value.get("type"),
                "allowed_slots": value.get("allowed_slots", []),
                "occupied_slots": value.get("occupied_slots", []),
                "armor": value.get("armor", 0),
                "damage": value.get("damage", 0),
                "weight": value.get("weight", 0),
                "durability": value.get("durability", 0),
                "description": value.get("description"),
                "effects": value.get("effects", {}),
            }
            for key, value in ITEMS.items()
        },
        "character_attributes": characters.ATTRIBUTE_IDS,
        "equipment_slots": characters.EQUIPMENT_SLOT_REGISTRY,
    }


def due_event_prompt_prefix(state: dict[str, Any], *, read_only: bool = False) -> str:
    due = scheduled_events.due_events(state)
    if not due:
        return ""
    items = "\n".join(
        f"- {event['id']}｜{event['title']}｜到期：第 {event['schedule']['due_time']['calendar_day']} 日 {event['schedule']['due_time']['clock_24']}｜状态：{event['status']}｜提示：{event.get('on_due', {}).get('suggested_prompt', '')}"
        for event in due
    )
    if read_only:
        return (
            "【到期事件背景】\n"
            "以下事件的游戏内时间已经到达或超过。当前是只读描述模式，不得激活或修改事件，但描述时必须把这些事件作为环境背景。\n"
            f"{items}\n\n"
        )
    return (
        "【必须处理的到期事件】\n"
        "以下事件的游戏内时间已经到达或超过。推进剧情时必须优先承认这些事件已经发生/抵达/爆发，"
        "并调用 /api/state/events/check-due 或对应事件 API 激活/处理；不得继续假装它们尚未发生。\n"
        f"{items}\n\n"
    )


def resolve_effective_mode(mode: str, state: dict[str, Any], client_context: dict[str, Any] | None = None) -> str:
    if mode != "story_turn":
        return mode
    intent = (client_context or {}).get("intent")
    if intent in {"strategic_turn", "strategic"}:
        return "strategic_turn"
    if intent in {"scene_step", "scene"}:
        return "scene_step"
    if state.get("game_mode") == "scene" or state.get("active_scene") is not None:
        return "scene_step"
    return "scene_step"


def build_strategic_turn_context(state: dict[str, Any], command: str, client_context: dict[str, Any] | None = None) -> str:
    api_base_url = os.getenv("LORD_TAIL_AGENT_API_BASE_URL", "http://127.0.0.1:8000")
    payload = {
        "mode": "strategic_turn",
        "player_command": command,
        "api_base_url": api_base_url,
        "state": compact_state_for_agent(state, client_context),
        "catalog_summary": catalog_summary(),
    }
    return (
        due_event_prompt_prefix(state) +
        "你是 Lord Tail 的领地书记官，当前职责是 strategic_turn 战略回合誊写与执行。\n"
        "本模式代表一个 9 天战略回合，只处理领地经营尺度的命令。\n"
        "领主议会、领地指标、合法行动、Utility 评分和预测由后端确定性管理系统负责；你不得自行改写提案、评分、预测或方针数值。\n"
        "如果后端返回开放议会，只叙述大臣陈奏并等待玩家明确选择，不得替玩家采纳提案。\n"
        f"如果需要由后端执行完整九天结算，调用 {api_base_url}/api/game/strategic-turn。\n"
        "如需在结算前做状态修改，只能调用上下文 allowed_actions.apis 中列出的 Lord Tail HTTP API。\n"
        "最终回答只输出面向玩家的中文本轮报告和简短后续建议；不要输出 JSON actions/state_patch。\n\n"
        f"上下文 JSON：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_scene_step_context(state: dict[str, Any], command: str, client_context: dict[str, Any] | None = None) -> str:
    api_base_url = os.getenv("LORD_TAIL_AGENT_API_BASE_URL", "http://127.0.0.1:8000")
    payload = {
        "mode": "scene_step",
        "player_command": command,
        "api_base_url": api_base_url,
        "state": compact_state_for_agent(state, client_context),
        "catalog_summary": catalog_summary(),
    }
    return (
        due_event_prompt_prefix(state) +
        "你是 Lord Tail 的领地书记官，兼任故事讲述者、描述者与受控执行者。\n"
        "当前模式是 scene_step：推进局部故事、对话、商队、外交会谈或战斗场景。\n"
        "本模式默认不推进 9 天战略回合，也不得自行假设领地完成九天结算。\n"
        "必须先识别场景并使用对应 skill；场景 skill 名称在上下文 JSON 的 allowed_actions.scene_skill_map 中。\n"
        f"如需修改游戏状态，必须在推理/执行过程中通过工具调用 Lord Tail HTTP API：{api_base_url}/api/state/* 或 {api_base_url}/api/agent/events。\n"
        "每次成功调用 /api/state/* 后必须再调用 /api/agent/events 记录事件。\n"
        "如果本次互动产生会影响后续叙事的事实，例如承诺、羞辱、债务、仇恨、战功、NPC 命运或外交后果，必须调用 /api/state/history 写入编年史。\n"
        f"如果当前没有 active_scene 且玩家正在进入一个连续事件，先调用 {api_base_url}/api/game/scenes 创建场景。\n"
        f"每轮场景互动可以调用 {api_base_url}/api/game/scenes/current/step 记录场景进展。\n"
        "时间状态使用 24 小时制 clock_24（HH:MM，例如 06:00、18:30）；描述时间变化时优先引用具体 clock_24。\n"
        f"当叙事中时间实际流逝（第二天、两天后、晚上、早上、30 分钟后、18:00、等待数小时等）时，必须调用 {api_base_url}/api/state/time/advance 推进真实时间；该接口可在有无 active_scene 时使用。\n"
        f"如只想记录当前 active_scene 内的时间经过，也可调用 {api_base_url}/api/game/scenes/current/advance-time；累计达到 9 天时可由后端触发战略结算。\n"
        f"只有当前事件明确完成时，才调用 {api_base_url}/api/game/scenes/current/end 结束场景。\n"
        "不要把状态修改写成最终 JSON，不要在最终回答中返回 actions。最终回答只输出面向玩家的中文故事和简短后续建议。\n"
        "允许的 scene 包括 daily, dialogue, caravan, diplomacy, battle, court, council, lord_event, sexual。\n"
        "不要直接输出 state_patch；不要创造 catalog 外的资源、建筑、兵种 id；API 调用失败时要在故事中体现执行失败。\n\n"
        f"上下文 JSON：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_description_context(state: dict[str, Any], mode: str, input_text: str, client_context: dict[str, Any] | None = None) -> str:
    read_only_state = compact_state_for_agent(state, client_context)
    read_only_state.pop("allowed_actions", None)
    payload = {
        "mode": mode,
        "request": input_text,
        "state": read_only_state,
        "catalog_summary": catalog_summary(),
        "rules": {"allow_state_mutation": False, "output_language": "zh-CN"},
    }
    return (
        due_event_prompt_prefix(state, read_only=True) +
        "你是 Lord Tail 的领地书记官。描述人物、领地、地图格、建筑或界面物件。\n"
        "描述非玩家人物时，优先使用 state.characters 中的人物账册；如果 client_context 指定 character_id，要围绕该人物描述。\n"
        "本模式严禁修改状态，严禁返回 actions，只输出面向玩家的中文描述。\n\n"
        f"上下文 JSON：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_storylet_context(state: dict[str, Any], mode: str, input_text: str, client_context: dict[str, Any] | None = None) -> str:
    from ..storylets.instances import instance_by_id, public_instance
    from ..storylets.config import get_definition

    instance_id = str((client_context or {}).get("story_event_id") or state.get("storylets", {}).get("current_instance_id") or "")
    instance = instance_by_id(state, instance_id) if instance_id else None
    public = public_instance(instance, get_definition(instance["definition_id"], instance["node_key"])) if instance else None
    payload = {
        "mode": mode, "request": input_text, "storylet": public,
        "cast": public.get("cast_snapshots", {}) if public else {},
        "frozen_facts": public.get("facts", {}) if public else {},
        "rules": {"allow_state_mutation": False, "allow_choice": False, "facts_are_immutable": True, "output_language": "zh-CN"},
    }
    phase = "开场" if mode == "storylet_opening" else "裁断结果"
    return (
        f"你是 Lord Tail 的领地书记官，使用 lord-tail-storylet skill 润色剧情事件{phase}。\n"
        "只能依据冻结人物、事实、合法选择和后端结果叙述；不得新增金额、关系、建筑、伤亡或选择。\n"
        "本模式完全只读，不调用任何 mutation API，不替玩家选择，不输出 JSON。若信息不足，保留本地模板已经确定的事实。\n\n"
        f"上下文 JSON：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_run_payload(mode: str, input_text: str, state: dict[str, Any], client_context: dict[str, Any] | None = None) -> dict[str, Any]:
    effective_mode = resolve_effective_mode(mode, state, client_context)
    if effective_mode in STORYLET_MODES:
        instructions = build_storylet_context(state, effective_mode, input_text, client_context)
    elif effective_mode in DESCRIPTION_MODES:
        instructions = build_description_context(state, effective_mode, input_text, client_context)
    elif effective_mode in STRATEGIC_MODES:
        instructions = build_strategic_turn_context(state, input_text, client_context)
    else:
        instructions = build_scene_step_context(state, input_text, client_context)
    return {
        "input": input_text,
        "session_id": (
            client_context.get("hermes_session_id")
            if isinstance(client_context, dict) and client_context.get("hermes_session_id")
            else f"lord-tail:{state.get('realm_name', 'default')}"
        ),
        "model": os.getenv("HERMES_RUNS_MODEL", "deepseek-v4-flash"),
        "instructions": instructions,
        "conversation_history": [],
        "metadata": {
            "app": "lord-tail",
            "mode": effective_mode,
            "requested_mode": mode,
            "profile": os.getenv("HERMES_AGENT_PROFILE", "lord-tail-ollama-gemma4-31b"),
        },
    }


def build_story_turn_context(state: dict[str, Any], command: str, client_context: dict[str, Any] | None = None) -> str:
    return build_scene_step_context(state, command, client_context)
