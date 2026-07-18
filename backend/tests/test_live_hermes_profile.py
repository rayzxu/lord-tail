from __future__ import annotations

import json
import os
from typing import Any

import httpx
import pytest

from app.catalog import TALENTS


PROFILE_NAME = "lord-tail-ollama-gemma4-31b"
DEFAULT_HERMES_URL = "http://127.0.0.1:8643"
DEFAULT_HERMES_KEY = "lord-tail-local-test"


def _sse_json_events(text: str) -> list[dict[str, Any]]:
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line.removeprefix("data:").strip()))
    return events


def _require_live_hermes() -> tuple[str, str]:
    if os.getenv("LORD_TAIL_LIVE_HERMES") != "1":
        pytest.skip("set LORD_TAIL_LIVE_HERMES=1 to run against the real Hermes profile gateway")
    base_url = os.getenv("HERMES_RUNS_BASE_URL", DEFAULT_HERMES_URL).rstrip("/")
    api_key = os.getenv("HERMES_RUNS_API_KEY", DEFAULT_HERMES_KEY)
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        health = httpx.get(f"{base_url}/health", headers=headers, timeout=5)
        health.raise_for_status()
    except Exception as error:
        pytest.fail(f"real Hermes gateway is not reachable at {base_url}: {error}")
    return base_url, api_key


def test_real_hermes_profile_exposes_lord_tail_skill_and_api_server_toolsets():
    base_url, api_key = _require_live_hermes()
    headers = {"Authorization": f"Bearer {api_key}"}

    skills = httpx.get(f"{base_url}/v1/skills", headers=headers, timeout=10).json()
    toolsets = httpx.get(f"{base_url}/v1/toolsets", headers=headers, timeout=10).json()
    capabilities = httpx.get(f"{base_url}/v1/capabilities", headers=headers, timeout=10).json()

    assert capabilities["model"] == "deepseek-v4-flash"
    assert any(item["name"] == "lord-tail-game" for item in skills["data"])
    enabled_toolsets = {item["name"] for item in toolsets["data"] if item["enabled"]}
    assert {"terminal", "skills"}.issubset(enabled_toolsets)


def test_real_hermes_profile_describes_alexander_through_lord_tail_runs(client, monkeypatch):
    base_url, api_key = _require_live_hermes()
    monkeypatch.setenv("HERMES_RUNS_BASE_URL", base_url)
    monkeypatch.setenv("HERMES_RUNS_API_KEY", api_key)
    monkeypatch.setenv("HERMES_AGENT_PROFILE", PROFILE_NAME)

    talent_ids = list(TALENTS)[:2]
    start = client.post(
        "/api/game/start",
        json={
            "lord_name": "亚历山大",
            "lord_gender": "男",
            "realm_name": "黑逼堡",
            "appearance": "肥胖，矮小，龌蹉；小眼睛里全是贪婪",
            "personality": "媚上欺下",
            "talents": [{"id": talent_id} for talent_id in talent_ids],
        },
    )
    assert start.status_code == 200, start.text

    created = client.post(
        "/api/agent/runs",
        json={
            "mode": "describe_lord",
            "input": "用两句话描述领主亚历山大，不要修改状态。",
            "client_context": {"target_type": "lord"},
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["events_url"].endswith("/events")

    with client.stream("GET", f"/api/agent/runs/{created.json()['run_id']}/events") as response:
        assert response.status_code == 200, response.text
        events = _sse_json_events(response.read().decode())

    event_names = [event["event"] for event in events]
    assert "run.started" in event_names
    assert "message.delta" in event_names
    assert "run.completed" in event_names

    status = client.get(f"/api/agent/runs/{created.json()['run_id']}").json()
    final_text = status["final_text"]
    assert status["status"] == "completed"
    assert "亚历山大" in final_text
    assert any(word in final_text for word in ["肥胖", "矮小", "贪婪", "媚上欺下"])
