from __future__ import annotations

from typing import Any

from ..catalog import BUILDINGS
from ..engine.mutations import can_pay, pay, tile_at
from ..engine.talents import talent_bonus
from ..engine.types import TurnContext, TurnEvent


def _resolve_building(building_id: str) -> dict[str, Any]:
    building = BUILDINGS.get(building_id)
    if building is None:
        raise ValueError(f"未知建筑：{building_id}")
    return building


def _next_project_id(state: dict[str, Any]) -> str:
    state["construction_seq"] = state.get("construction_seq", 0) + 1
    return f"project_{state['construction_seq']}"


def _workforce(state: dict[str, Any]) -> dict[str, int]:
    return state.setdefault("workforce", {"available": state["resources"].get("population", 0), "assigned": 0})


def start_project(state: dict[str, Any], building_id: str, x: int, y: int, context: TurnContext) -> dict[str, Any]:
    building = _resolve_building(building_id)
    tile = tile_at(state, x, y)
    if tile is None:
        raise ValueError("建设坐标不在地图范围内")
    if tile.get("owner"):
        raise ValueError("该地块不属于领主直辖，无法建设")
    if tile["kind"] not in building["requires"]:
        raise ValueError(f"{building['name']}必须建在：{'、'.join(building['requires'])}")
    resources = state["resources"]
    if not can_pay(resources, building["cost"]):
        raise ValueError(f"资源不足，无法建造{building['name']}")
    workforce = _workforce(state)
    idle = workforce["available"] - workforce["assigned"]
    if idle < building["workforce"]:
        raise ValueError(f"可用劳力不足，无法建造{building['name']}")
    pay(resources, state["changes"], building["cost"])
    workforce["assigned"] += building["workforce"]
    reduction = talent_bonus(state, "construction_turn_reduction")
    turns = max(1, building["construction_turns"] - reduction)
    project = {
        "id": _next_project_id(state),
        "building_id": building_id,
        "x": x,
        "y": y,
        "remaining_turns": turns,
        "total_turns": turns,
        "workforce": building["workforce"],
        "status": "active",
    }
    state["construction_queue"].append(project)
    context.events.append(TurnEvent(
        phase="player_action",
        kind="project_started",
        message=f"{building['workforce']} 名劳工在 {chr(64 + x)}{y} 开始修建{building['name']}，预计还需 {turns} 轮。",
        data={"project_id": project["id"], "building": building["name"], "turns": turns},
    ))
    return project


def complete_project(state: dict[str, Any], project: dict[str, Any], context: TurnContext) -> None:
    building = _resolve_building(project["building_id"])
    state["buildings"][building["name"]] = state["buildings"].get(building["name"], 0) + 1
    tile = tile_at(state, project["x"], project["y"])
    if tile:
        tile.update(kind=building["tile_kind"], label=building["name"])
    workforce = _workforce(state)
    workforce["assigned"] = max(0, workforce["assigned"] - project["workforce"])
    project["status"] = "completed"
    context.events.append(TurnEvent(
        phase="construction",
        kind="project_completed",
        message=f"{building['name']}竣工",
        data={"project_id": project["id"], "building": building["name"], "x": project["x"], "y": project["y"]},
    ))


def advance_projects(state: dict[str, Any], context: TurnContext) -> None:
    queue = state["construction_queue"]
    active = [project for project in queue if project.get("status", "active") == "active"]
    if not active:
        context.events.append(TurnEvent(phase="construction", kind="noop", message="没有在建的工程。"))
        return
    completed_ids = set()
    for project in active:
        project["remaining_turns"] -= 1
        if project["remaining_turns"] <= 0:
            complete_project(state, project, context)
            completed_ids.add(project["id"])
    if completed_ids:
        state["construction_queue"] = [project for project in queue if project["id"] not in completed_ids]
    else:
        context.events.append(TurnEvent(phase="construction", kind="in_progress", message="工程仍在推进中。"))


def cancel_project(state: dict[str, Any], project_id: str, context: TurnContext) -> None:
    queue = state["construction_queue"]
    project = next((item for item in queue if item["id"] == project_id), None)
    if project is None:
        raise ValueError(f"未找到工程：{project_id}")
    workforce = _workforce(state)
    workforce["assigned"] = max(0, workforce["assigned"] - project["workforce"])
    state["construction_queue"] = [item for item in queue if item["id"] != project_id]
    building = _resolve_building(project["building_id"])
    context.events.append(TurnEvent(
        phase="construction",
        kind="project_cancelled",
        message=f"{building['name']}的工程被取消，劳力已释放。",
        data={"project_id": project_id, "building": building["name"]},
    ))


def destroy_building(state: dict[str, Any], building_id_or_name: str, x: int, y: int, context: TurnContext) -> None:
    building = BUILDINGS.get(building_id_or_name)
    if building is None:
        building = next((value for value in BUILDINGS.values() if value["name"] == building_id_or_name), None)
    if building is None:
        raise ValueError(f"未知建筑：{building_id_or_name}")
    name = building["name"]
    if state["buildings"].get(name, 0) <= 0:
        raise ValueError(f"没有可摧毁的{name}")
    tile = tile_at(state, x, y)
    if tile is None or tile.get("kind") != building["tile_kind"]:
        raise ValueError(f"坐标上没有可摧毁的{name}")
    state["buildings"][name] = max(0, state["buildings"][name] - 1)
    tile.update(kind="grass", label="草地")
    context.events.append(TurnEvent(
        phase="construction",
        kind="building_destroyed",
        message=f"{name}被拆除。",
        data={"building": name, "x": x, "y": y},
    ))
