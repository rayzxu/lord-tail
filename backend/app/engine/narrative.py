from __future__ import annotations

from typing import Any

from .types import TurnEvent


def serialize_events(events: list[TurnEvent]) -> list[dict[str, Any]]:
    return [event.model_dump() if hasattr(event, "model_dump") else event.dict() for event in events]


def events_to_report(events: list[TurnEvent]) -> str:
    meaningful = [
        event
        for event in events
        if not event.kind.endswith("_noop") and event.kind != "noop"
    ]
    if not meaningful:
        return "本轮领地平稳运转，没有需要特别记录的事项。"

    critical = [event for event in meaningful if event.severity == "critical"]
    warnings = [event for event in meaningful if event.severity == "warning"]
    normal = [event for event in meaningful if event.severity == "info"]
    ordered = critical + warnings + normal
    selected = ordered[:6]
    report = " ".join(event.message for event in selected)
    if len(ordered) > len(selected):
        report += f" 另有 {len(ordered) - len(selected)} 项事务已入档。"
    return report


def suggest_next_actions(state: dict[str, Any], events: list[TurnEvent]) -> list[str]:
    resources = state.get("resources", {})
    event_kinds = {event.kind for event in events}
    suggestions: list[str] = []

    if "food_depleted" in event_kinds or resources.get("food", 0) < 80:
        suggestions.append("在 E4 建造农田")
    if resources.get("gold", 0) < 100:
        suggestions.append("调整税令以补充金库")
    if resources.get("morale", 0) < 35:
        suggestions.append("降低征敛并安抚领民")
    if any(event.kind == "war_warning" for event in events):
        suggestions.append("派遣使者缓和外交关系")
    if state.get("buildings", {}).get("训练场", 0) and sum(state.get("army", {}).values()) < 10:
        suggestions.append("训练 5 名步兵")
    if state.get("demographics", {}).get("housing", {}).get("total_vacant", 0) < 10:
        suggestions.append("建造镇屋或窝棚区")

    defaults = ["在 B2 建造伐木场", "修建手工作坊扩大产业", "巡视粮仓与市场"]
    for item in defaults:
        if len(suggestions) >= 3:
            break
        if item not in suggestions:
            suggestions.append(item)
    return suggestions[:3]
