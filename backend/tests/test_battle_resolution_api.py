from __future__ import annotations

from conftest import start_game

from app.engine.state import require_state


def test_cavalry_vs_three_infantry_resolves_via_api(client):
    start_game(client)
    army_response = client.post("/api/state/army", json={"unit": "cavalry", "value": 1})
    assert army_response.status_code == 200, army_response.text

    response = client.post("/api/state/battles/resolve", json={
        "player": {"cavalry": 1},
        "enemy": {"infantry": 3},
        "stance": "aggressive",
        "source": "test",
        "label": "骑兵冲击三名步兵",
    })

    assert response.status_code == 200, response.text
    body = response.json()
    battle = body["battle_result"]
    assert battle["id"].startswith("battle_")
    assert battle["player"]["before"]["cavalry"] == 1
    assert battle["enemy"]["before"]["infantry"] == 3
    assert battle["modifiers"]["player_average_speed"] > battle["modifiers"]["enemy_average_speed"]
    assert any(event["kind"] == "battle_resolved" for event in body["events"])
    assert body["state"]["battles"][-1]["id"] == battle["id"]


def test_battle_resolve_rejects_unavailable_player_force_without_mutation(client):
    start_game(client)
    client.post("/api/state/army", json={"unit": "cavalry", "value": 1})
    before = client.get("/api/state").json()["state"]["army"]["cavalry"]

    response = client.post("/api/state/battles/resolve", json={
        "player": {"cavalry": 2},
        "enemy": {"infantry": 3},
    })

    assert response.status_code == 422
    assert "兵力不足" in response.json()["detail"]
    after_state = client.get("/api/state").json()["state"]
    assert after_state["army"]["cavalry"] == before
    assert after_state["battles"] == []


def test_battle_resolve_dry_run_does_not_mutate_state(client):
    start_game(client)
    client.post("/api/state/army", json={"unit": "archers", "value": 1})
    before_state = client.get("/api/state").json()["state"]
    before_army = dict(before_state["army"])
    before_battles = list(before_state["battles"])

    response = client.post("/api/state/battles/resolve", json={
        "player": {"archers": 1},
        "enemy": {"infantry": 3},
        "apply_to_state": False,
        "source": "test",
    })

    assert response.status_code == 200, response.text
    assert "battle_result" in response.json()
    after_state = client.get("/api/state").json()["state"]
    assert after_state["army"] == before_army
    assert after_state["battles"] == before_battles


def test_battle_resolve_rejects_unknown_unit(client):
    start_game(client)
    client.post("/api/state/army", json={"unit": "infantry", "value": 1})

    response = client.post("/api/state/battles/resolve", json={
        "player": {"infantry": 1},
        "enemy": {"dragon": 1},
    })

    assert response.status_code == 422
    assert "未知兵种" in response.json()["detail"]
    assert client.get("/api/state").json()["state"]["battles"] == []


def test_battle_resolve_rout_event_is_machine_readable(client):
    start_game(client)
    state = require_state()
    state["army"] = {"infantry": 10, "archers": 0, "cavalry": 0}
    state["army_status"] = {"organization": 20, "routed": False, "last_loss_ratio": 0.0}

    response = client.post("/api/state/battles/resolve", json={
        "player": {"infantry": 10},
        "enemy": {"cavalry": 80},
        "enemy_organization": 100,
        "stance": "aggressive",
        "source": "test",
        "label": "低组织度步兵遭遇骑兵重击",
    })

    assert response.status_code == 200, response.text
    body = response.json()
    battle = body["battle_result"]
    loss_ratio = battle["player"]["casualties"] / max(1, sum(battle["player"]["before"].values()))
    if loss_ratio >= 0.15:
        assert body["state"]["army_status"]["routed"] is True
        assert battle["player"]["routed"] is True
        assert any(event["kind"] == "army_routed" for event in body["events"])
