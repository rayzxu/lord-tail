from __future__ import annotations

import json

import pytest

from conftest import start_game


def _sse_json_events(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line.removeprefix("data:").strip()))
    return events


def test_create_run_and_stream_events(client, monkeypatch):
    from app.integrations import hermes_runs

    start_game(client)
    monkeypatch.setenv("HERMES_RUNS_BASE_URL", "http://hermes.test")

    async def fake_create_run(payload):
        assert payload["metadata"]["mode"] == "scene_step"
        assert payload["metadata"]["requested_mode"] == "story_turn"
        assert payload["model"] == "deepseek-v4-flash"
        assert "上下文 JSON" in payload["instructions"]
        assert "默认不推进 9 天战略回合" in payload["instructions"]
        return {"run_id": "run_123", "status": "started"}

    async def fake_stream_run_events(hermes_run_id):
        assert hermes_run_id == "run_123"
        yield {"event": "reasoning.available", "text": "判断商队意图。"}
        yield {"event": "message.delta", "delta": "一支商队抵达边境。"}
        yield {"event": "run.completed", "output": "一支商队抵达边境。"}

    monkeypatch.setattr(hermes_runs, "create_run", fake_create_run)
    monkeypatch.setattr(hermes_runs, "stream_run_events", fake_stream_run_events)

    created = client.post("/api/agent/runs", json={"mode": "story_turn", "input": "接待商队"})
    assert created.status_code == 200, created.text
    run_id = created.json()["run_id"]
    assert created.json()["hermes_run_id"] == "run_123"

    with client.stream("GET", f"/api/agent/runs/{run_id}/events") as response:
        assert response.status_code == 200, response.text
        events = _sse_json_events(response.read().decode())

    assert [event["event"] for event in events] == [
        "run.started",
        "reasoning.available",
        "message.delta",
        "run.completed",
    ]
    assert all("seq" in event for event in events)
    status = client.get(f"/api/agent/runs/{run_id}")
    assert status.json()["status"] == "completed"
    assert status.json()["final_text"] == "一支商队抵达边境。"


def test_approval_request_auto_denies(client, monkeypatch):
    from app.integrations import hermes_runs

    start_game(client)
    monkeypatch.setenv("HERMES_RUNS_BASE_URL", "http://hermes.test")
    monkeypatch.setenv("HERMES_APPROVAL_POLICY", "auto-deny")
    approvals: list[tuple[str, str]] = []

    async def fake_create_run(payload):
        return {"run_id": "run_approval", "status": "started"}

    async def fake_stream_run_events(hermes_run_id):
        yield {
            "event": "approval.request",
            "choices": ["once", "session", "deny"],
            "command": "curl http://127.0.0.1:8000/api/state/resources",
            "description": "修改资源",
        }
        yield {"event": "run.completed", "output": "审批已处理。"}

    async def fake_send_approval(hermes_run_id, choice):
        approvals.append((hermes_run_id, choice))
        return {"status": "ok"}

    monkeypatch.setattr(hermes_runs, "create_run", fake_create_run)
    monkeypatch.setattr(hermes_runs, "stream_run_events", fake_stream_run_events)
    monkeypatch.setattr(hermes_runs, "send_approval", fake_send_approval)

    run_id = client.post("/api/agent/runs", json={"mode": "story_turn", "input": "尝试危险操作"}).json()["run_id"]
    with client.stream("GET", f"/api/agent/runs/{run_id}/events") as response:
        events = _sse_json_events(response.read().decode())

    assert approvals == [("run_approval", "deny")]
    assert any(event["event"] == "approval.request" for event in events)
    assert any(event["event"] == "approval.responded" and event["choice"] == "deny" for event in events)


def test_approval_request_auto_approves_safe_lord_tail_api(client, monkeypatch):
    from app.integrations import hermes_runs

    start_game(client)
    monkeypatch.setenv("HERMES_RUNS_BASE_URL", "http://hermes.test")
    monkeypatch.delenv("HERMES_APPROVAL_POLICY", raising=False)
    approvals: list[tuple[str, str]] = []

    async def fake_create_run(payload):
        return {"run_id": "run_approval_safe", "status": "started"}

    async def fake_stream_run_events(hermes_run_id):
        yield {
            "event": "approval.request",
            "choices": ["once", "session", "deny"],
            "command": (
                'curl -s -X POST "http://127.0.0.1:8000/api/agent/events" '
                "-H 'Content-Type: application/json' "
                """-d '{"kind":"battle_api_gap","severity":"warning"}'"""
            ),
            "description": "记录战斗结算 API 缺口",
        }
        yield {"event": "run.completed", "output": "审批已处理。"}

    async def fake_send_approval(hermes_run_id, choice):
        approvals.append((hermes_run_id, choice))
        return {"status": "ok"}

    monkeypatch.setattr(hermes_runs, "create_run", fake_create_run)
    monkeypatch.setattr(hermes_runs, "stream_run_events", fake_stream_run_events)
    monkeypatch.setattr(hermes_runs, "send_approval", fake_send_approval)

    run_id = client.post("/api/agent/runs", json={"mode": "story_turn", "input": "记录战斗缺口"}).json()["run_id"]
    with client.stream("GET", f"/api/agent/runs/{run_id}/events") as response:
        events = _sse_json_events(response.read().decode())

    assert approvals == [("run_approval_safe", "once")]
    assert any(event["event"] == "approval.responded" and event["choice"] == "once" for event in events)


def test_approval_request_auto_approves_multiline_safe_lord_tail_api(client, monkeypatch):
    from app.integrations import hermes_runs

    start_game(client)
    monkeypatch.setenv("HERMES_RUNS_BASE_URL", "http://hermes.test")
    monkeypatch.delenv("HERMES_APPROVAL_POLICY", raising=False)
    approvals: list[tuple[str, str]] = []

    async def fake_create_run(payload):
        return {"run_id": "run_approval_multiline", "status": "started"}

    async def fake_stream_run_events(hermes_run_id):
        yield {
            "event": "approval.request",
            "choices": ["once", "session", "deny"],
            "command": """curl -s -X POST "http://127.0.0.1:8000/api/agent/events" \\
-H 'Content-Type: application/json' \\
-d '{
  "kind": "battle_api_gap",
  "severity": "warning",
  "message": "当前后端没有 battle resolve API"
}'""",
            "description": "记录战斗结算 API 缺口",
        }
        yield {"event": "run.completed", "output": "审批已处理。"}

    async def fake_send_approval(hermes_run_id, choice):
        approvals.append((hermes_run_id, choice))
        return {"status": "ok"}

    monkeypatch.setattr(hermes_runs, "create_run", fake_create_run)
    monkeypatch.setattr(hermes_runs, "stream_run_events", fake_stream_run_events)
    monkeypatch.setattr(hermes_runs, "send_approval", fake_send_approval)

    run_id = client.post("/api/agent/runs", json={"mode": "story_turn", "input": "记录战斗缺口"}).json()["run_id"]
    with client.stream("GET", f"/api/agent/runs/{run_id}/events") as response:
        events = _sse_json_events(response.read().decode())

    assert approvals == [("run_approval_multiline", "once")]
    assert any(event["event"] == "approval.responded" and event["choice"] == "once" for event in events)


def test_approval_request_auto_approves_battle_resolve_api(client, monkeypatch):
    from app.integrations import hermes_runs

    start_game(client)
    monkeypatch.setenv("HERMES_RUNS_BASE_URL", "http://hermes.test")
    monkeypatch.delenv("HERMES_APPROVAL_POLICY", raising=False)
    approvals: list[tuple[str, str]] = []

    async def fake_create_run(payload):
        return {"run_id": "run_approval_battle", "status": "started"}

    async def fake_stream_run_events(hermes_run_id):
        yield {
            "event": "approval.request",
            "choices": ["once", "session", "deny"],
            "command": (
                "curl -s -X POST http://127.0.0.1:8000/api/state/battles/resolve "
                "-H 'Content-Type: application/json' "
                """-d '{"player":{"cavalry":1},"enemy":{"infantry":3}}'"""
            ),
            "description": "结算战斗",
        }
        yield {"event": "run.completed", "output": "审批已处理。"}

    async def fake_send_approval(hermes_run_id, choice):
        approvals.append((hermes_run_id, choice))
        return {"status": "ok"}

    monkeypatch.setattr(hermes_runs, "create_run", fake_create_run)
    monkeypatch.setattr(hermes_runs, "stream_run_events", fake_stream_run_events)
    monkeypatch.setattr(hermes_runs, "send_approval", fake_send_approval)

    run_id = client.post("/api/agent/runs", json={"mode": "story_turn", "input": "结算骑兵冲击"}).json()["run_id"]
    with client.stream("GET", f"/api/agent/runs/{run_id}/events") as response:
        events = _sse_json_events(response.read().decode())

    assert approvals == [("run_approval_battle", "once")]
    assert any(event["event"] == "approval.responded" and event["choice"] == "once" for event in events)


def test_approval_request_auto_approves_character_api(client, monkeypatch):
    from app.integrations import hermes_runs

    start_game(client)
    monkeypatch.setenv("HERMES_RUNS_BASE_URL", "http://hermes.test")
    monkeypatch.delenv("HERMES_APPROVAL_POLICY", raising=False)
    approvals: list[tuple[str, str]] = []

    async def fake_create_run(payload):
        return {"run_id": "run_approval_character", "status": "started"}

    async def fake_stream_run_events(hermes_run_id):
        yield {
            "event": "approval.request",
            "choices": ["once", "session", "deny"],
            "command": (
                "curl -s -X PATCH http://127.0.0.1:8000/api/state/characters/char_1 "
                "-H 'Content-Type: application/json' "
                """-d '{"location":"地牢门外","disposition":-30}'"""
            ),
            "description": "更新人物账册",
        }
        yield {"event": "run.completed", "output": "审批已处理。"}

    async def fake_send_approval(hermes_run_id, choice):
        approvals.append((hermes_run_id, choice))
        return {"status": "ok"}

    monkeypatch.setattr(hermes_runs, "create_run", fake_create_run)
    monkeypatch.setattr(hermes_runs, "stream_run_events", fake_stream_run_events)
    monkeypatch.setattr(hermes_runs, "send_approval", fake_send_approval)

    run_id = client.post("/api/agent/runs", json={"mode": "story_turn", "input": "更新玛尔塔的位置"}).json()["run_id"]
    with client.stream("GET", f"/api/agent/runs/{run_id}/events") as response:
        events = _sse_json_events(response.read().decode())

    assert approvals == [("run_approval_character", "once")]
    assert any(event["event"] == "approval.responded" and event["choice"] == "once" for event in events)


def test_approval_request_auto_approves_character_adult_stat_api(client, monkeypatch):
    from app.integrations import hermes_runs

    start_game(client)
    monkeypatch.setenv("HERMES_RUNS_BASE_URL", "http://hermes.test")
    monkeypatch.delenv("HERMES_APPROVAL_POLICY", raising=False)
    approvals: list[tuple[str, str]] = []

    async def fake_create_run(payload):
        return {"run_id": "run_approval_character_adult_stats", "status": "started"}

    async def fake_stream_run_events(hermes_run_id):
        yield {
            "event": "approval.request",
            "choices": ["once", "session", "deny"],
            "command": (
                "curl -s -X POST http://127.0.0.1:8000/api/state/characters/char_1/reproductive-contents "
                "-H 'Content-Type: application/json' "
                """-d '{"target":"stomach","content_type":"water","source_character_id":"external_unknown"}'"""
            ),
            "description": "更新人物内容物状态",
        }
        yield {"event": "run.completed", "output": "审批已处理。"}

    async def fake_send_approval(hermes_run_id, choice):
        approvals.append((hermes_run_id, choice))
        return {"status": "ok"}

    monkeypatch.setattr(hermes_runs, "create_run", fake_create_run)
    monkeypatch.setattr(hermes_runs, "stream_run_events", fake_stream_run_events)
    monkeypatch.setattr(hermes_runs, "send_approval", fake_send_approval)

    run_id = client.post("/api/agent/runs", json={"mode": "story_turn", "input": "更新人物状态"}).json()["run_id"]
    with client.stream("GET", f"/api/agent/runs/{run_id}/events") as response:
        events = _sse_json_events(response.read().decode())

    assert approvals == [("run_approval_character_adult_stats", "once")]
    assert any(event["event"] == "approval.responded" and event["choice"] == "once" for event in events)


def test_approval_request_auto_approves_scribe_time_advance_api(client, monkeypatch):
    from app.integrations import hermes_runs

    start_game(client)
    monkeypatch.setenv("HERMES_RUNS_BASE_URL", "http://hermes.test")
    monkeypatch.delenv("HERMES_APPROVAL_POLICY", raising=False)
    approvals: list[tuple[str, str]] = []

    async def fake_create_run(payload):
        return {"run_id": "run_approval_time_advance", "status": "started"}

    async def fake_stream_run_events(hermes_run_id):
        yield {
            "event": "approval.request",
            "choices": ["once", "session", "deny"],
            "command": (
                "curl -s -X POST http://127.0.0.1:8000/api/state/time/advance "
                "-H 'Content-Type: application/json' "
                """-d '{"hours":2,"reason":"等待两个小时","source":"hermes"}'"""
            ),
            "description": "推进领地时间",
        }
        yield {"event": "run.completed", "output": "审批已处理。"}

    async def fake_send_approval(hermes_run_id, choice):
        approvals.append((hermes_run_id, choice))
        return {"status": "ok"}

    monkeypatch.setattr(hermes_runs, "create_run", fake_create_run)
    monkeypatch.setattr(hermes_runs, "stream_run_events", fake_stream_run_events)
    monkeypatch.setattr(hermes_runs, "send_approval", fake_send_approval)

    run_id = client.post("/api/agent/runs", json={"mode": "story_turn", "input": "等待两个小时"}).json()["run_id"]
    with client.stream("GET", f"/api/agent/runs/{run_id}/events") as response:
        events = _sse_json_events(response.read().decode())

    assert approvals == [("run_approval_time_advance", "once")]
    assert any(event["event"] == "approval.responded" and event["choice"] == "once" for event in events)


def test_approval_request_auto_denies_non_whitelisted_command(client, monkeypatch):
    from app.integrations import hermes_runs

    start_game(client)
    monkeypatch.setenv("HERMES_RUNS_BASE_URL", "http://hermes.test")
    monkeypatch.delenv("HERMES_APPROVAL_POLICY", raising=False)
    approvals: list[tuple[str, str]] = []

    async def fake_create_run(payload):
        return {"run_id": "run_approval_unsafe", "status": "started"}

    async def fake_stream_run_events(hermes_run_id):
        yield {
            "event": "approval.request",
            "choices": ["once", "session", "deny"],
            "command": "curl http://127.0.0.1:8000/api/agent/events; rm -rf /tmp/lord-tail-test",
            "description": "不安全命令",
        }
        yield {"event": "run.completed", "output": "审批已处理。"}

    async def fake_send_approval(hermes_run_id, choice):
        approvals.append((hermes_run_id, choice))
        return {"status": "ok"}

    monkeypatch.setattr(hermes_runs, "create_run", fake_create_run)
    monkeypatch.setattr(hermes_runs, "stream_run_events", fake_stream_run_events)
    monkeypatch.setattr(hermes_runs, "send_approval", fake_send_approval)

    run_id = client.post("/api/agent/runs", json={"mode": "story_turn", "input": "尝试不安全命令"}).json()["run_id"]
    with client.stream("GET", f"/api/agent/runs/{run_id}/events") as response:
        events = _sse_json_events(response.read().decode())

    assert approvals == [("run_approval_unsafe", "deny")]
    assert any(event["event"] == "approval.responded" and event["choice"] == "deny" for event in events)


def test_story_turn_applies_actions_from_sse(client, monkeypatch):
    from app.integrations import hermes_runs

    state = start_game(client)
    gold_before = state["resources"]["gold"]
    monkeypatch.setenv("HERMES_RUNS_BASE_URL", "http://hermes.test")

    async def fake_create_run(payload):
        return {"run_id": "run_actions", "status": "started"}

    async def fake_stream_run_events(hermes_run_id):
        yield {
            "event": "run.completed",
            "output": "商队缴纳了过路税。",
            "actions": [{"type": "resources", "payload": {"changes": {"gold": 10}}}],
        }

    monkeypatch.setattr(hermes_runs, "create_run", fake_create_run)
    monkeypatch.setattr(hermes_runs, "stream_run_events", fake_stream_run_events)

    run_id = client.post("/api/agent/runs", json={"mode": "story_turn", "input": "向商队征收过路税"}).json()["run_id"]
    with client.stream("GET", f"/api/agent/runs/{run_id}/events") as response:
        events = _sse_json_events(response.read().decode())

    state = client.get("/api/state").json()["state"]
    assert state["resources"]["gold"] == gold_before + 10
    assert any(event["event"] == "state.action_applied" for event in events)


def test_description_mode_rejects_state_mutation_actions(client, monkeypatch):
    from app.integrations import hermes_runs

    state = start_game(client)
    gold_before = state["resources"]["gold"]
    monkeypatch.setenv("HERMES_RUNS_BASE_URL", "http://hermes.test")

    async def fake_create_run(payload):
        assert payload["metadata"]["mode"] == "describe_tile"
        assert "严禁修改状态" in payload["instructions"]
        return {"run_id": "run_describe", "status": "started"}

    async def fake_stream_run_events(hermes_run_id):
        yield {
            "event": "run.completed",
            "output": "这是一片雨后的农田。",
            "actions": [{"type": "resources", "payload": {"changes": {"gold": 10}}}],
        }

    monkeypatch.setattr(hermes_runs, "create_run", fake_create_run)
    monkeypatch.setattr(hermes_runs, "stream_run_events", fake_stream_run_events)

    run_id = client.post(
        "/api/agent/runs",
        json={"mode": "describe_tile", "input": "描述 E4", "client_context": {"selected_tile": {"x": 5, "y": 4}}},
    ).json()["run_id"]
    with client.stream("GET", f"/api/agent/runs/{run_id}/events") as response:
        events = _sse_json_events(response.read().decode())

    state = client.get("/api/state").json()["state"]
    assert state["resources"]["gold"] == gold_before
    assert any(event["event"] == "state.action_rejected" for event in events)


def test_agent_runs_requires_configuration(client, monkeypatch):
    start_game(client)
    monkeypatch.delenv("HERMES_RUNS_BASE_URL", raising=False)
    response = client.post("/api/agent/runs", json={"mode": "story_turn", "input": "巡视领地"})
    assert response.status_code == 503


@pytest.mark.anyio
async def test_hermes_runs_client_ignores_proxy_env_by_default(monkeypatch):
    from app.integrations import hermes_runs

    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7897")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7899")
    monkeypatch.delenv("HERMES_RUNS_TRUST_ENV", raising=False)

    async with hermes_runs.runs_client() as client:
        assert client._trust_env is False


@pytest.mark.anyio
async def test_hermes_runs_client_can_explicitly_trust_env(monkeypatch):
    from app.integrations import hermes_runs

    monkeypatch.setenv("HERMES_RUNS_TRUST_ENV", "true")

    async with hermes_runs.runs_client() as client:
        assert client._trust_env is True
