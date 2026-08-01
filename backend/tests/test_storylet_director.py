from app.storylets.director import run_director
from conftest import start_game


def test_director_creates_one_ready_major_and_next_advance_activates_it(client):
    state = start_game(client)
    state["storylets"]["director"]["enabled"] = True
    decision = run_director(state, seed=500, commit=True)
    assert decision["instance"]["status"] == "ready"
    second = run_director(state, seed=501, commit=True)
    assert second["selected"] is None
    response = client.post("/api/game/strategic-turn", json={"command": "推进九天", "source": "player"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"]["storylets"]["current_instance_id"] == decision["instance"]["id"]
    assert body["state"]["active_scene"]["flags"]["source"] == "storylet"
    assert any(event["kind"] == "strategic_advance_blocked_by_due_event" for event in body["events"])
    end = client.post("/api/game/scenes/current/end", json={"summary": "试图绕过裁断", "outcome": {}})
    assert end.status_code == 409
