from __future__ import annotations

import json
import os
import shlex
from collections.abc import AsyncIterator
from pathlib import PurePosixPath
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..engine import run_store
from ..engine.hermes_actions import action_event, apply_hermes_actions
from ..engine.hermes_context import DESCRIPTION_MODES, build_run_payload
from ..engine.state import require_state
from ..integrations import hermes_runs

router = APIRouter()

SAFE_LORD_TAIL_APPROVAL_PATHS = {
    "/api/agent/context",
    "/api/agent/describe-context",
    "/api/agent/events",
    "/api/state",
    "/api/characters",
    "/api/items",
    "/api/lord/components",
    "/api/time",
    "/api/state/time/advance",
    "/api/hermes/time/advance",
    "/api/game/strategic-turn",
    "/api/game/scenes",
    "/api/game/scenes/current/step",
    "/api/game/scenes/current/advance-time",
    "/api/game/scenes/current/end",
    "/api/state/resources",
    "/api/state/population",
    "/api/state/morale",
    "/api/state/army",
    "/api/state/diplomacy",
    "/api/state/buildings",
    "/api/state/battles/resolve",
    "/api/state/characters",
    "/api/state/lord/items",
    "/api/state/lord/components/body_profile",
    "/api/state/lord/components/attributes",
    "/api/state/lord/equipment/equip",
    "/api/state/lord/equipment/unequip",
    "/api/hermes/characters",
    "/api/hermes/items",
    "/api/hermes/lord/components",
    "/api/hermes/lord/items",
    "/api/hermes/lord/equipment/equip",
    "/api/hermes/lord/equipment/unequip",
    "/api/hermes/battles/resolve",
}
SAFE_LORD_TAIL_APPROVAL_PATH_PREFIXES = (
    "/api/characters/",
    "/api/state/characters/",
    "/api/hermes/characters/",
)

UNSAFE_SHELL_MARKERS = (";", "&&", "||", "|", "`", "$(", ">", "<")
CURL_FLAGS_WITH_VALUES = {"-X", "--request", "-H", "--header", "-d", "--data", "--data-raw", "--data-binary"}
CURL_FLAGS_WITH_OPTIONAL_VALUES = {"-s", "-S", "-f", "-L", "--silent", "--show-error", "--fail", "--location"}

AgentRunMode = Literal["strategic_turn", "scene_step", "story_turn", "describe_realm", "describe_lord", "describe_tile", "describe_item"]


class AgentRunRequest(BaseModel):
    mode: AgentRunMode = "story_turn"
    input: str = Field(min_length=1, max_length=4000)
    client_context: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    choice: str = Field(min_length=1, max_length=30)


class ClarifyRequest(BaseModel):
    response: str = Field(min_length=1, max_length=4000)


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _run_public(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "object": "lord_tail.agent_run",
        "run_id": run["run_id"],
        "hermes_run_id": run.get("hermes_run_id"),
        "mode": run.get("mode"),
        "status": run.get("status"),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "final_text": run.get("final_text", ""),
        "last_event": run.get("events", [])[-1] if run.get("events") else None,
    }


def _hermes_http_error_detail(action: str, error: httpx.HTTPError) -> str:
    base_url = hermes_runs.runs_base_url() or "未配置"
    if isinstance(error, httpx.ConnectError):
        return f"{action}失败：无法连接书记官传信服务 {base_url}，请确认 Hermes gateway 已启动且端口配置正确。原始错误：{error}"
    if isinstance(error, httpx.TimeoutException):
        return f"{action}失败：连接书记官传信服务 {base_url} 超时。原始错误：{error}"
    if isinstance(error, httpx.HTTPStatusError):
        response = error.response
        body = response.text.strip().replace("\n", " ")
        if len(body) > 500:
            body = body[:500] + "..."
        suffix = f"，响应：{body}" if body else ""
        return f"{action}失败：书记官传信服务 {base_url} 返回 HTTP {response.status_code}{suffix}"
    return f"{action}失败：{error}"


def _extract_actions(event: dict[str, Any]) -> list[Any]:
    actions = event.get("actions")
    if isinstance(actions, list):
        return actions
    output = event.get("output")
    if not isinstance(output, str):
        return []
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict) and isinstance(parsed.get("actions"), list):
        return parsed["actions"]
    return []


def _normalize_hermes_event(local_run: dict[str, Any], hermes_event: dict[str, Any]) -> dict[str, Any]:
    event = dict(hermes_event)
    event.setdefault("event", "message.delta" if "delta" in event else "run.event")
    event["run_id"] = local_run["run_id"]
    if local_run.get("hermes_run_id"):
        event["hermes_run_id"] = local_run["hermes_run_id"]
    return event


async def _apply_actions_from_event(local_run: dict[str, Any], event: dict[str, Any]) -> list[dict[str, Any]]:
    actions = _extract_actions(event)
    if not actions:
        return []
    state = require_state()
    allow_mutation = local_run.get("mode") not in DESCRIPTION_MODES
    results = apply_hermes_actions(state, actions, allow_mutation=allow_mutation)
    return [
        run_store.append_event(
            local_run["run_id"],
            action_event(result, run_id=local_run["run_id"], hermes_run_id=local_run.get("hermes_run_id")),
        )
        for result in results
    ]


def _is_safe_lord_tail_api_url(raw_url: str) -> bool:
    parsed = urlparse(raw_url)
    if parsed.scheme != "http":
        return False
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        return False
    if parsed.port != 8000:
        return False
    normalized_path = str(PurePosixPath(parsed.path))
    return normalized_path in SAFE_LORD_TAIL_APPROVAL_PATHS or normalized_path.startswith(SAFE_LORD_TAIL_APPROVAL_PATH_PREFIXES)


def _is_safe_lord_tail_api_command(command: Any) -> bool:
    if not isinstance(command, str):
        return False
    command = command.strip()
    if not command:
        return False
    if any(marker in command for marker in UNSAFE_SHELL_MARKERS):
        return False

    command = command.replace("\\\r\n", " ").replace("\\\n", " ")
    quote: str | None = None
    escaped = False
    for char in command:
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote != "'":
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
            continue
        if char in {"\n", "\r"} and quote is None:
            return False

    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens or tokens[0] != "curl":
        return False

    saw_url = False
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token.startswith(("http://", "https://")):
            if not _is_safe_lord_tail_api_url(token):
                return False
            saw_url = True
            index += 1
            continue
        if token in CURL_FLAGS_WITH_OPTIONAL_VALUES:
            index += 1
            continue
        if token.startswith("--request="):
            method = token.split("=", 1)[1].upper()
            if method not in {"GET", "POST", "PATCH"}:
                return False
            index += 1
            continue
        if token.startswith(("--data=", "--data-raw=", "--data-binary=", "--header=")):
            index += 1
            continue
        if token in CURL_FLAGS_WITH_VALUES:
            if index + 1 >= len(tokens):
                return False
            if token in {"-X", "--request"} and tokens[index + 1].upper() not in {"GET", "POST", "PATCH"}:
                return False
            index += 2
            continue
        return False
    return saw_url


async def _auto_respond_approval_if_needed(local_run: dict[str, Any], event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("event") != "approval.request":
        return None
    policy = os.getenv("HERMES_APPROVAL_POLICY", "auto-safe-local").strip().lower()
    if policy in {"manual", "off", "none"}:
        return None
    hermes_run_id = local_run.get("hermes_run_id")
    if not hermes_run_id:
        return None

    command = event.get("command") or event.get("preview")
    if policy == "auto-deny":
        choice = "deny"
        message = "令状已按当前策略自动驳回。"
    elif policy == "auto-approve":
        choice = "once"
        message = "令状已按当前策略准行一次。"
    elif policy == "auto-safe-local":
        if _is_safe_lord_tail_api_command(command):
            choice = "once"
            message = "领地账册内的安全差事已准行一次。"
        else:
            choice = "deny"
            message = "令状不在领地账册准许范围内，已自动驳回。"
    else:
        return None

    try:
        await hermes_runs.send_approval(hermes_run_id, choice)
    except Exception:
        pass
    return run_store.append_event(local_run["run_id"], {
        "event": "approval.responded",
        "run_id": local_run["run_id"],
        "hermes_run_id": hermes_run_id,
        "choice": choice,
        "resolved": 1,
        "message": message,
    })


@router.post("/agent/runs")
async def create_agent_run(request: AgentRunRequest) -> dict[str, Any]:
    state = require_state()
    if hermes_runs.runs_base_url() is None:
        raise HTTPException(503, "书记官传信未配置：请在后端环境变量中设置传信地址")
    payload = build_run_payload(request.mode, request.input, state, request.client_context)
    try:
        hermes_run = await hermes_runs.create_run(payload)
    except httpx.HTTPError as error:
        raise HTTPException(502, _hermes_http_error_detail("书记官传信创建", error)) from error
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error

    hermes_run_id = str(hermes_run.get("run_id") or hermes_run.get("id") or "")
    if not hermes_run_id:
        raise HTTPException(502, "书记官传信返回缺少文书编号")
    local_run = run_store.create_run(
        mode=request.mode,
        input_text=request.input,
        hermes_run_id=hermes_run_id,
        metadata={"client_context": request.client_context, "hermes": hermes_run},
    )
    run_store.append_event(local_run["run_id"], {
        "event": "run.started",
        "hermes_run_id": hermes_run_id,
        "status": hermes_run.get("status", "started"),
        "message": "书记官已经开卷。",
    })
    return {
        "run_id": local_run["run_id"],
        "hermes_run_id": hermes_run_id,
        "status": "started",
        "events_url": f"/api/agent/runs/{local_run['run_id']}/events",
    }


@router.get("/agent/runs/{run_id}")
async def agent_run_status(run_id: str) -> dict[str, Any]:
    try:
        return _run_public(run_store.require_run(run_id))
    except KeyError as error:
        raise HTTPException(404, "未找到书记官文书") from error


@router.get("/agent/runs/{run_id}/events")
async def agent_run_events(run_id: str, since_seq: int = Query(default=0, ge=0)) -> StreamingResponse:
    try:
        local_run = run_store.require_run(run_id)
    except KeyError as error:
        raise HTTPException(404, "未找到书记官文书") from error

    async def generate() -> AsyncIterator[str]:
        for event in run_store.events_after(run_id, since_seq):
            yield _sse(event)

        latest = run_store.require_run(run_id)
        if latest.get("status") in run_store.TERMINAL_STATUSES:
            return

        hermes_run_id = latest.get("hermes_run_id")
        if not hermes_run_id:
            failed = run_store.append_event(run_id, {"event": "run.failed", "error": "缺少书记官文书编号"})
            yield _sse(failed)
            return

        try:
            async for hermes_event in hermes_runs.stream_run_events(hermes_run_id):
                local_run_snapshot = run_store.require_run(run_id)
                normalized = _normalize_hermes_event(local_run_snapshot, hermes_event)
                stored = run_store.append_event(run_id, normalized)
                yield _sse(stored)

                approval_response = await _auto_respond_approval_if_needed(local_run_snapshot, stored)
                if approval_response is not None:
                    yield _sse(approval_response)

                for action_item in await _apply_actions_from_event(local_run_snapshot, stored):
                    yield _sse(action_item)

                if stored.get("event") in {"run.completed", "run.failed", "run.cancelled"}:
                    break
        except Exception as error:
            failed = run_store.append_event(run_id, {"event": "run.failed", "error": str(error)})
            yield _sse(failed)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/agent/runs/{run_id}/approval")
async def agent_run_approval(run_id: str, request: ApprovalRequest) -> dict[str, Any]:
    try:
        local_run = run_store.require_run(run_id)
    except KeyError as error:
        raise HTTPException(404, "未找到书记官文书") from error
    hermes_run_id = local_run.get("hermes_run_id")
    if not hermes_run_id:
        raise HTTPException(409, "该文书没有关联书记官传信")
    response = await hermes_runs.send_approval(hermes_run_id, request.choice)
    event = run_store.append_event(run_id, {
        "event": "approval.responded",
        "choice": request.choice,
        "resolved": 1,
        "message": "令状批复已提交。",
    })
    return {"status": "ok", "hermes": response, "event": event}


@router.post("/agent/runs/{run_id}/clarify")
async def agent_run_clarify(run_id: str, request: ClarifyRequest) -> dict[str, Any]:
    try:
        local_run = run_store.require_run(run_id)
    except KeyError as error:
        raise HTTPException(404, "未找到书记官文书") from error
    hermes_run_id = local_run.get("hermes_run_id")
    if not hermes_run_id:
        raise HTTPException(409, "该文书没有关联书记官传信")
    response = await hermes_runs.send_clarify(hermes_run_id, request.response)
    event = run_store.append_event(run_id, {
        "event": "clarify.responded",
        "response": request.response,
        "message": "补充信息已提交。",
    })
    return {"status": "ok", "hermes": response, "event": event}


@router.post("/agent/runs/{run_id}/cancel")
async def agent_run_cancel(run_id: str) -> dict[str, Any]:
    try:
        local_run = run_store.require_run(run_id)
    except KeyError as error:
        raise HTTPException(404, "未找到书记官文书") from error
    hermes_run_id = local_run.get("hermes_run_id")
    hermes_response: dict[str, Any] = {}
    if hermes_run_id:
        hermes_response = await hermes_runs.cancel_run(hermes_run_id)
    event = run_store.append_event(run_id, {"event": "run.cancelled", "message": "书记官已经停笔。"})
    return {"status": "cancelled", "hermes": hermes_response, "event": event}
