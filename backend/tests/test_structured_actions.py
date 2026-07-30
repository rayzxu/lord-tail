from __future__ import annotations

from conftest import start_game


def test_legal_actions_validate_and_share_one_turn_slot(client):
    start_game(client)
    listing = client.get("/api/actions/legal")
    assert listing.status_code == 200, listing.text
    actions = listing.json()["actions"]
    assert actions
    assert any(item["type"] == "wait" for item in actions)
    action = next(item for item in actions if item["type"] == "wait")

    validation = client.post("/api/actions/validate", json={"action": action, "actor": "player"})
    assert validation.status_code == 200
    assert validation.json()["legal"] is True

    executed = client.post("/api/actions/execute", json={"action": action, "actor": "player"})
    assert executed.status_code == 200, executed.text
    repeated = client.post("/api/actions/execute", json={"action": action, "actor": "player"})
    assert repeated.status_code == 422
    assert "战略行动已经" in repeated.json()["detail"]


def test_invalid_build_coordinate_is_rejected_by_shared_validator(client):
    start_game(client)
    action = {"type": "build", "payload": {"building_id": "farm", "x": 999, "y": 999}}
    response = client.post("/api/actions/validate", json={"action": action, "actor": "hermes"})
    assert response.status_code == 200
    assert response.json()["legal"] is False
    assert "地图范围" in response.json()["errors"][0]
