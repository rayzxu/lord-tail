from __future__ import annotations

import json
import os
from typing import Any

import httpx


async def call_hermes(state: dict[str, Any], command: str) -> dict[str, Any] | None:
    url = os.getenv("HERMES_AGENT_URL")
    if not url:
        return None
    headers = {"Authorization": f"Bearer {os.getenv('HERMES_AGENT_TOKEN', '')}"} if os.getenv("HERMES_AGENT_TOKEN") else {}
    payload = {
        "state": state,
        "command": command,
        "system_context": (
            "你是中世纪领地管理游戏的叙事书记官。输出中文叙事。"
            "如需修改状态，优先返回 actions 数组，type 支持 resources/population/morale/army/diplomacy/buildings，payload 必须匹配 /api/state/* 接口。"
            "state_patch 仅为 legacy 兼容格式，不作为主路径。"
        ),
    }
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, json.JSONDecodeError):
        return None
