from __future__ import annotations

from conftest import start_game


def test_first_council_interrupts_at_day_one_nine_oclock(client):
    state = start_game(client, resolve_council=False)
    council_events = [item for item in state["scheduled_events"]["entries"] if item["type"] == "council_session"]
    assert len(council_events) == 1
    assert council_events[0]["schedule"]["due_time"]["calendar_day"] == 1
    assert council_events[0]["schedule"]["due_time"]["clock_24"] == "09:00"

    response = client.post("/api/game/strategic-turn", json={"command": "推进九天"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["state"]["turn"] == 1
    assert data["state"]["time"]["clock_24"] == "09:00"
    assert data["state"]["active_scene"]["type"] == "council"
    assert any(item["kind"] == "council_opened" for item in data["events"])

    meeting = data["state"]["council"]["current_meeting"]
    assert meeting["status"] == "open"
    assert [item["domain"] for item in meeting["proposals"]] == ["finance", "military", "diplomacy", "reserve"]


def test_resolving_council_creates_timed_directive_and_is_idempotent(client):
    start_game(client, resolve_council=False)
    interrupted = client.post("/api/game/strategic-turn", json={"command": "推进九天"}).json()
    meeting = interrupted["state"]["council"]["current_meeting"]
    proposal = meeting["proposals"][0]
    response = client.post(
        f"/api/council/{meeting['id']}/resolve",
        json={"proposal_id": proposal["id"], "management_mode": "delegated"},
    )
    assert response.status_code == 200, response.text
    directive = response.json()["directive"]
    assert directive["proposal_id"] == proposal["id"]
    assert directive["expires_time"]["calendar_day"] - directive["started_time"]["calendar_day"] == 90
    assert response.json()["state"]["active_scene"] is None

    repeated = client.post(
        f"/api/council/{meeting['id']}/resolve",
        json={"proposal_id": proposal["id"], "management_mode": "delegated"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
