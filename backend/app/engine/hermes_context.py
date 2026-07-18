from __future__ import annotations

import json
import os
from typing import Any

from ..catalog import BUILDINGS, RESOURCES, UNITS

DESCRIPTION_MODES = {"describe_realm", "describe_lord", "describe_tile", "describe_item"}
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
        },
        "resources": state.get("resources", {}),
        "changes": state.get("changes", {}),
        "buildings": state.get("buildings", {}),
        "army": state.get("army", {}),
        "army_status": state.get("army_status", {}),
        "diplomacy": state.get("diplomacy", {}),
        "demographics": _compact_demographics(state),
        "selected_tile": selected_tile,
        "realm_map": {
            "visible_tiles": state.get("map", [])[:100],
        },
        "diplomacy_map": {
            "visible_tiles": state.get("diplomacy_map", [])[:100],
        },
        "recent_events": state.get("recent_events", [])[-20:],
        "allowed_actions": public_action_contract(),
    }


def public_action_contract() -> dict[str, Any]:
    return {
        "base_url": os.getenv("LORD_TAIL_AGENT_API_BASE_URL", "http://127.0.0.1:8000"),
        "global_rules": [
            "story_turn 中任何状态改变必须调用 Lord Tail HTTP API，最终回答不得输出 JSON actions/state_patch。",
            "每次成功调用 /api/state/* mutation 后，必须调用 /api/agent/events 记录事件。",
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
            "time": "lord-tail-time",
            "scene": "lord-tail-scene",
            "strategic_turn": "lord-tail-strategic-turn",
            "scene_dialogue": "lord-tail-scene-dialogue",
            "scene_battle": "lord-tail-scene-battle",
            "scene_diplomacy": "lord-tail-scene-diplomacy",
        },
        "ids": {
            "resources": list(RESOURCES.keys()),
            "buildings": list(BUILDINGS.keys()),
            "units": list(UNITS.keys()),
            "diplomacy_statuses": ["友善", "中立", "敌对", "战争"],
            "event_severities": ["info", "warning", "critical"],
        },
        "resources": list(RESOURCES.keys()),
        "buildings": list(BUILDINGS.keys()),
        "units": list(UNITS.keys()),
        "apis": {
            "read_state": {"method": "GET", "path": "/api/state"},
            "read_time": {"method": "GET", "path": "/api/time"},
            "read_context": {"method": "GET", "path": "/api/agent/context"},
            "describe_context": {"method": "GET", "path": "/api/agent/describe-context"},
            "strategic_turn": {
                "method": "POST",
                "path": "/api/game/strategic-turn",
                "payload": {"command": "让领地按当前安排运转九天", "source": "hermes"},
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
        },
        "scene_playbooks": {
            "construction": ["POST /api/state/buildings", "POST /api/agent/events"],
            "population": ["POST /api/state/population", "POST /api/state/morale when social impact exists", "POST /api/agent/events"],
            "economy": ["POST /api/state/resources", "POST /api/agent/events"],
            "talent": ["POST matching /api/state/* if talent changes state", "POST /api/agent/events"],
            "disaster_food_shortage": ["POST /api/state/resources", "POST /api/state/morale", "POST /api/agent/events"],
            "disaster_plague": ["POST /api/state/population", "POST /api/state/morale", "POST /api/agent/events"],
            "disaster_fire": ["POST /api/state/resources", "POST /api/state/morale", "POST /api/agent/events"],
            "weather_season": ["POST /api/agent/events only; no weather/season mutation API exists"],
            "tax": ["POST /api/state/resources", "POST /api/state/morale", "POST /api/agent/events"],
            "conscription": ["POST /api/state/army", "POST /api/state/population", "POST /api/state/resources for cost", "POST /api/agent/events"],
            "caravan": ["POST /api/state/resources", "POST /api/state/diplomacy if faction relation changes", "POST /api/agent/events"],
            "diplomacy_positive": ["POST /api/state/resources if gift", "POST /api/state/diplomacy", "POST /api/agent/events"],
            "diplomacy_negative": ["POST /api/state/diplomacy", "POST /api/agent/events"],
            "battle_archers": ["POST /api/state/battles/resolve", "POST /api/agent/events after successful battle resolution"],
            "battle_infantry": ["POST /api/state/battles/resolve", "POST /api/agent/events after successful battle resolution"],
            "battle_cavalry": ["POST /api/state/battles/resolve", "POST /api/agent/events after successful battle resolution"],
            "statue": ["POST /api/agent/events only; no statue building id exists"],
            "strategic_turn": ["POST /api/game/strategic-turn"],
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
    }


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
        "你是 Lord Tail 的 Hermes Agent，当前模式是 strategic_turn。\n"
        "本模式代表一个 9 天战略回合，只处理领地经营尺度的命令。\n"
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
        "你是 Lord Tail 的 Hermes Agent，角色是故事讲述者与执行者。\n"
        "当前模式是 scene_step：推进局部故事、对话、商队、外交会谈或战斗场景。\n"
        "本模式默认不推进 9 天战略回合，也不得自行假设领地完成九天结算。\n"
        "必须先识别场景并使用对应 Hermes skill；场景 skill 名称在上下文 JSON 的 allowed_actions.scene_skill_map 中。\n"
        f"如需修改游戏状态，必须在推理/执行过程中通过工具调用 Lord Tail HTTP API：{api_base_url}/api/state/* 或 {api_base_url}/api/agent/events。\n"
        "每次成功调用 /api/state/* 后必须再调用 /api/agent/events 记录事件。\n"
        f"如果当前没有 active_scene 且玩家正在进入一个连续事件，先调用 {api_base_url}/api/game/scenes 创建场景。\n"
        f"每轮场景互动可以调用 {api_base_url}/api/game/scenes/current/step 记录场景进展。\n"
        "时间状态使用 24 小时制 clock_24（HH:MM，例如 06:00、18:30）；描述时间变化时优先引用具体 clock_24。\n"
        f"只有当玩家明确说“第二天、两天后、晚上、早上、30 分钟后、18:00”等时间经过时，才调用 {api_base_url}/api/game/scenes/current/advance-time；累计达到 9 天时可由后端触发战略结算。\n"
        f"只有当前事件明确完成时，才调用 {api_base_url}/api/game/scenes/current/end 结束场景。\n"
        "不要把状态修改写成最终 JSON，不要在最终回答中返回 actions。最终回答只输出面向玩家的中文故事和简短后续建议。\n"
        "允许的 scene 包括 daily, caravan, diplomacy, military, lord_event。\n"
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
        "你是 Lord Tail 的描述者。描述人物、领地、地图格、建筑或 UI item。\n"
        "本模式严禁修改状态，严禁返回 actions，只输出面向玩家的中文描述。\n\n"
        f"上下文 JSON：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_run_payload(mode: str, input_text: str, state: dict[str, Any], client_context: dict[str, Any] | None = None) -> dict[str, Any]:
    effective_mode = resolve_effective_mode(mode, state, client_context)
    if effective_mode in DESCRIPTION_MODES:
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
