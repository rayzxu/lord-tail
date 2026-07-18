from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from .mutations import apply_structured_action

VALID_EVENT_SEVERITIES = {"info", "warning", "critical"}


def _normalize_turn_event(payload: dict[str, Any]) -> dict[str, Any]:
    severity = str(payload.get("severity", "info"))
    if severity not in VALID_EVENT_SEVERITIES:
        raise HTTPException(422, "turn_event.severity 必须是 info/warning/critical")
    kind = str(payload.get("kind", "")).strip()
    message = str(payload.get("message", "")).strip()
    if not kind or not message:
        raise HTTPException(422, "turn_event 必须提供 kind 和 message")
    data = payload.get("data", {})
    if not isinstance(data, dict):
        raise HTTPException(422, "turn_event.data 必须是对象")
    return {
        "phase": str(payload.get("phase", "events")),
        "kind": kind,
        "message": message,
        "severity": severity,
        "data": data,
    }


def apply_hermes_action(state: dict[str, Any], action: dict[str, Any], allow_mutation: bool = True) -> dict[str, Any]:
    action_type = str(action.get("type", ""))
    payload = action.get("payload", {})
    if not isinstance(payload, dict):
        raise HTTPException(422, "Hermes action payload 必须是对象")

    if action_type == "turn_event":
        event = _normalize_turn_event(payload)
        state.setdefault("recent_events", []).append(event)
        state["recent_events"] = state["recent_events"][-50:]
        return {"type": action_type, "status": "applied", "event": event}

    if not allow_mutation:
        raise HTTPException(422, f"{action_type} 在描述模式中不允许修改状态")

    return apply_structured_action(state, action)


def apply_hermes_actions(state: dict[str, Any], actions: list[Any], allow_mutation: bool = True) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            results.append({"type": "unknown", "status": "rejected", "error": "action 必须是对象"})
            continue
        try:
            results.append(apply_hermes_action(state, action, allow_mutation=allow_mutation))
        except (HTTPException, TypeError, ValueError) as error:
            results.append({
                "type": str(action.get("type", "unknown")),
                "status": "rejected",
                "error": getattr(error, "detail", str(error)),
                "action": action,
            })
    return results


def action_event(result: dict[str, Any], run_id: str | None = None, hermes_run_id: str | None = None) -> dict[str, Any]:
    status = result.get("status")
    event_name = "state.action_applied" if status == "applied" else "state.action_rejected"
    message = f"Hermes action 已应用：{result.get('type')}" if status == "applied" else f"Hermes action 被拒绝：{result.get('type')}"
    event = {
        "event": event_name,
        "message": message,
        "severity": "info" if status == "applied" else "warning",
        "data": result,
    }
    if run_id:
        event["run_id"] = run_id
    if hermes_run_id:
        event["hermes_run_id"] = hermes_run_id
    return event

