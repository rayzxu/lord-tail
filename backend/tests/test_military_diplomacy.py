from __future__ import annotations

from conftest import start_game


def test_training_pipeline_and_upkeep_events(client):
    start_game(client)
    response = client.post("/api/state/buildings", json={"building": "训练场", "action": "build", "count": 1})
    assert response.status_code == 200, response.text

    response = client.post("/api/game/turn", json={"command": "训练 3 名步兵"})
    assert response.status_code == 200, response.text
    state = response.json()["state"]
    assert state["training_queue"]

    response = client.post("/api/game/turn", json={"command": "巡视训练场"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["state"]["army"]["infantry"] >= 3
    assert any(event["kind"] == "training_completed" for event in data["events"])
    assert any(event["kind"] == "unit_upkeep" for event in data["events"])


def test_diplomacy_state_shape_and_war_warning_event(client):
    start_game(client)
    response = client.post("/api/state/diplomacy", json={"faction": "金鳞", "status": "敌对"})
    assert response.status_code == 200, response.text
    entry = response.json()["state"]["diplomacy"]["金鳞"]
    assert set(entry) == {"stance", "relation", "treaties", "at_war"}

    client.post("/api/state/diplomacy", json={"faction": "金鳞", "status": "战争"})
    response = client.post("/api/game/turn", json={"command": "派书记官整理外交文书"})
    assert response.status_code == 200, response.text
    entry = response.json()["state"]["diplomacy"]["金鳞"]
    assert entry["at_war"] is True
