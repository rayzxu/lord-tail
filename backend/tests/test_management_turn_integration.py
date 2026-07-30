from __future__ import annotations

from app.engine.state import require_state
from app.systems.council import set_management_mode
from conftest import start_game


def test_delegated_ai_uses_exactly_one_action(client):
    start_game(client)
    state = require_state()
    set_management_mode(state, "delegated")
    response = client.post("/api/game/strategic-turn", json={"command": "让领地按当前方针运转九天"})
    assert response.status_code == 200, response.text
    events = response.json()["events"]
    assert sum(item["kind"] == "structured_action_executed" for item in events) == 1
    assert sum(item["kind"] == "management_ai_decision" for item in events) == 1


def test_manual_order_overrides_delegated_ai(client):
    start_game(client)
    state = require_state()
    set_management_mode(state, "delegated")
    response = client.post("/api/game/strategic-turn", json={"command": "等待并维持现状"})
    assert response.status_code == 200, response.text
    events = response.json()["events"]
    assert sum(item["kind"] == "structured_action_executed" for item in events) == 1
    assert any(item["kind"] == "manual_action_override" for item in events)
    assert not any(item["kind"] == "management_ai_decision" for item in events)


def test_advisory_mode_blocks_until_candidate_is_accepted(client):
    start_game(client)
    state = require_state()
    set_management_mode(state, "advisory")
    blocked = client.post("/api/game/strategic-turn", json={"command": "按当前方针推进九天"})
    assert blocked.status_code == 200
    assert blocked.json()["state"]["turn"] == 1
    assert any(item["kind"] == "management_advice_required" for item in blocked.json()["events"])
    decision = blocked.json()["state"]["management_ai"]["pending_advice"]

    accepted = client.post(
        f"/api/strategy/advice/{decision['id']}/accept",
        json={"action_id": decision["selected_action"]["action_id"]},
    )
    assert accepted.status_code == 200, accepted.text
    advanced = client.post("/api/game/strategic-turn", json={"command": "按已盖印的顾问方案推进九天"})
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()["state"]["turn"] == 2
    assert any(item["kind"] == "management_ai_decision" for item in advanced.json()["events"])


def test_public_action_api_consumes_slot_without_granting_ai_second_action(client):
    start_game(client)
    executed = client.post(
        "/api/actions/execute",
        json={
            "actor": "hermes",
            "action": {"type": "wait", "payload": {"reason": "player_order"}},
        },
    )
    assert executed.status_code == 200, executed.text

    advanced = client.post("/api/game/strategic-turn", json={"command": "按当前方针推进九天"})
    assert advanced.status_code == 200, advanced.text
    events = advanced.json()["events"]
    assert any(item["kind"] == "action_slot_already_used" for item in events)
    assert not any(item["kind"] == "management_ai_decision" for item in events)
    assert sum(item["kind"] == "structured_action_executed" for item in events) == 0
