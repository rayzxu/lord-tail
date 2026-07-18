from __future__ import annotations

from conftest import start_game


def test_state_api_resources_population_and_buildings(client):
    start_game(client)

    response = client.post("/api/state/resources", json={"changes": {"gold": 25, "population": 5}})
    assert response.status_code == 200, response.text
    state = response.json()["state"]
    assert state["resources"]["gold"] >= 525
    assert state["resources"]["population"] == sum(
        item["population"] for item in state["demographics"]["classes"].values()
    )

    response = client.post("/api/state/morale", json={"delta": -10})
    assert response.status_code == 200, response.text
    assert response.json()["state"]["resources"]["morale"] == 60

    response = client.post("/api/state/buildings", json={"building": "窝棚区", "action": "build", "count": 1})
    assert response.status_code == 200, response.text
    housing = response.json()["state"]["demographics"]["housing"]["by_type"]
    assert housing["hut"]["capacity"] >= 112


def test_state_api_army_and_diplomacy(client):
    start_game(client)

    response = client.post("/api/state/army", json={"unit": "步兵", "value": 12})
    assert response.status_code == 200, response.text
    assert response.json()["state"]["army"]["infantry"] == 12

    response = client.post("/api/state/diplomacy", json={"faction": "金鳞", "status": "友善"})
    assert response.status_code == 200, response.text
    entry = response.json()["state"]["diplomacy"]["金鳞"]
    assert entry["stance"] == "友善"
    assert entry["relation"] == 70
