from copy import deepcopy

from app.engine.state import require_state
from app.storylets.service import instantiate_storylet
from app.systems.scheduled_events import activate_due_events
from conftest import start_game


def _active_petition(client, seed=300):
    state = start_game(client)
    instance = instantiate_storylet(state, "petition_building_credit", seed=seed, commit=True)
    activate_due_events(state, source="test")
    return state, instance


def test_choice_is_atomic_and_idempotent(client):
    state, instance = _active_petition(client)
    response = client.post(f"/api/storylets/{instance['id']}/choose", json={"choice_id": "refuse_petition", "actor": "player"})
    assert response.status_code == 200, response.text
    assert response.json()["instance"]["status"] == "resolved"
    repeat = client.post(f"/api/storylets/{instance['id']}/choose", json={"choice_id": "refuse_petition", "actor": "player"})
    assert repeat.status_code == 200
    assert repeat.json()["idempotent"] is True
    conflict = client.post(f"/api/storylets/{instance['id']}/choose", json={"choice_id": "confiscate_savings", "actor": "player"})
    assert conflict.status_code == 409


def test_failed_construction_choice_leaves_no_partial_state(client):
    state, instance = _active_petition(client, seed=301)
    state["resources"]["gold"] = 0
    petitioner = next(item for item in state["characters"]["entries"] if item["id"] == instance["cast"]["petitioner"])
    petitioner["components"]["economy_agent"]["wealth"] = 0
    before = deepcopy(state)
    response = client.post(f"/api/storylets/{instance['id']}/choose", json={"choice_id": "grant_subsidy", "actor": "player"})
    assert response.status_code == 422
    after = require_state()
    assert after["resources"] == before["resources"]
    assert after["construction_queue"] == before["construction_queue"]
    assert after["storylets"]["instances"] == before["storylets"]["instances"]
    after_petitioner = next(item for item in after["characters"]["entries"] if item["id"] == instance["cast"]["petitioner"])
    assert after_petitioner["components"]["economy_agent"] == petitioner["components"]["economy_agent"]


def test_loan_starts_real_project_and_schedules_repayment(client):
    state, instance = _active_petition(client, seed=302)
    response = client.post(f"/api/storylets/{instance['id']}/choose", json={"choice_id": "offer_loan", "actor": "player"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["result"]["project_id"]
    assert any(item["id"] == body["result"]["project_id"] for item in body["state"]["construction_queue"])
    followups = [item for item in body["state"]["storylets"]["instances"] if item["node_key"] == "loan_repayment_due"]
    assert len(followups) == 1
    scheduled = next(item for item in body["state"]["scheduled_events"]["entries"] if item["id"] == followups[0]["scheduled_event_id"])
    assert scheduled["schedule"]["due_time"]["calendar_day"] == body["state"]["time"]["calendar_day"] + 90
