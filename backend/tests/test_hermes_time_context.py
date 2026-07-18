from __future__ import annotations

from conftest import start_game


def test_strategic_turn_context_mentions_nine_days(client, monkeypatch):
    from app.engine.hermes_context import build_run_payload

    state = start_game(client)
    payload = build_run_payload("strategic_turn", "结束本轮", state, {})

    assert payload["metadata"]["mode"] == "strategic_turn"
    assert "9 天战略回合" in payload["instructions"]
    assert "/api/game/strategic-turn" in payload["instructions"]


def test_scene_step_context_mentions_no_default_strategic_advance_and_time_api(client):
    from app.engine.hermes_context import build_run_payload

    state = start_game(client)
    payload = build_run_payload("scene_step", "第二天早上继续审问", state, {})

    assert payload["metadata"]["mode"] == "scene_step"
    assert "默认不推进 9 天战略回合" in payload["instructions"]
    assert "/api/game/scenes/current/advance-time" in payload["instructions"]
    assert "/api/game/scenes/current/end" in payload["instructions"]


def test_description_context_remains_read_only(client):
    from app.engine.hermes_context import build_run_payload

    state = start_game(client)
    payload = build_run_payload("describe_realm", "描述领地", state, {})

    assert payload["metadata"]["mode"] == "describe_realm"
    assert "严禁修改状态" in payload["instructions"]
    assert "advance-time" not in payload["instructions"]
