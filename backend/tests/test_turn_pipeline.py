from __future__ import annotations

from conftest import start_game


def test_turn_response_contains_threshold_events(client):
    start_game(client)
    client.post("/api/state/resources", json={"values": {"food": 0}})

    response = client.post("/api/game/turn", json={"command": "巡视粮仓"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["events"]
    assert any(event["kind"] == "food_depleted" for event in data["events"])
    assert data["state"]["resources"]["food"] >= 0
    assert data["source"] == "rules"


def test_turn_pipeline_completes_one_turn_building_and_reports_event(client):
    start_game(client)

    response = client.post("/api/game/turn", json={"command": "在 E4 建造窝棚区"})
    assert response.status_code == 200, response.text
    data = response.json()
    kinds = [event["kind"] for event in data["events"]]
    assert "project_started" in kinds
    assert "project_completed" in kinds
    assert "building_completed_effect" in kinds
    assert data["state"]["buildings"]["窝棚区"] == 1
