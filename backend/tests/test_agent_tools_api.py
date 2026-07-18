from __future__ import annotations

from conftest import start_game


def test_agent_context_exposes_state_catalog_and_unified_mutation_api(client):
    start_game(client)

    response = client.get("/api/agent/context")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["state"]["realm"]["name"] == "北境"
    assert "resources" in data["catalog_summary"]
    assert data["mutation_api"]["resources"] == "POST /api/state/resources"
    assert "buildings" in data["allowed_actions"]


def test_describe_context_is_read_only_for_tile(client):
    start_game(client)

    response = client.get("/api/agent/describe-context", params={"target_type": "tile", "x": 5, "y": 5})

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["target"]["label"] == "领主堡垒"
    assert data["description_rules"]["allow_state_mutation"] is False


def test_agent_events_records_recent_event_without_custom_mutation_api(client):
    state = start_game(client)
    gold_before = state["resources"]["gold"]

    response = client.post(
        "/api/agent/events",
        json={"kind": "merchant_arrived", "message": "一支商队抵达南门。", "severity": "info", "data": {"scene": "caravan"}},
    )

    assert response.status_code == 200, response.text
    state_after = response.json()["state"]
    assert state_after["resources"]["gold"] == gold_before
    assert state_after["recent_events"][-1]["kind"] == "merchant_arrived"
