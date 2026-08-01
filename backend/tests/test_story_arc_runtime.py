from app.engine.state import require_state
from app.engine.time import set_time_point
from app.storylets.runtime import audit_arc_consistency
from app.systems.scheduled_events import activate_due_events
from conftest import start_game


def activate_caravan(client):
    state = start_game(client)
    entry = next(item for item in state["scheduled_events"]["entries"] if item["type"] == "caravan_arrival")
    set_time_point(state, entry["schedule"]["due_time"])
    activate_due_events(state, source="test")
    arc = client.get("/api/story-arcs/current").json()["arc"]
    return state, entry, arc


def choose(client, arc, choice_id, seq=None):
    return client.post(
        f"/api/storylets/{arc['current_instance']['id']}/choose",
        json={"choice_id": choice_id, "expected_transition_seq": arc["chain"]["transition_seq"] if seq is None else seq},
    )


def test_arc_lifecycle_cannot_be_bypassed_and_completes_atomically(client):
    state, entry, arc = activate_caravan(client)
    chain_id = arc["chain"]["id"]
    assert audit_arc_consistency(state, chain_id) == []
    assert client.post("/api/game/scenes/current/end", json={"summary": "跳过"}).status_code == 409
    assert client.post(f"/api/state/events/{entry['id']}/resolve", json={"result_md": "跳过", "resolved_by": "hermes"}).status_code == 409

    first = choose(client, arc, "admit_under_guard")
    assert first.status_code == 200, first.text
    next_arc = first.json()["arc"]
    assert next_arc["chain"]["current_node_id"] == "trade_hearing"
    assert audit_arc_consistency(state, chain_id) == []

    stale = choose(client, next_arc, "approve_trade", seq=0)
    assert stale.status_code == 409
    completed = choose(client, next_arc, "approve_trade")
    assert completed.status_code == 200, completed.text
    payload = completed.json()
    assert payload["terminal"] is True
    assert payload["arc"]["chain"]["status"] == "completed"
    assert state["active_scene"] is None
    resolved_entry = next(item for item in state["scheduled_events"]["entries"] if item["id"] == entry["id"])
    assert resolved_entry["status"] == "resolved"
    assert audit_arc_consistency(state, chain_id) == []


def test_choice_is_idempotent_and_freeform_budget_does_not_move_node(client):
    state, _, arc = activate_caravan(client)
    instance_id = arc["current_instance"]["id"]
    for index in range(2):
        stepped = client.post("/api/game/scenes/current/step", json={"input": f"追问 {index}"})
        assert stepped.status_code == 200
    messages_before = len(state["active_scene"]["recent_messages"])
    events_before = len(state["recent_events"])
    rejected = client.post("/api/game/scenes/current/step", json={"input": "第三次追问"})
    assert rejected.status_code == 409
    assert len(state["active_scene"]["recent_messages"]) == messages_before
    assert len(state["recent_events"]) == events_before
    current = client.get("/api/story-arcs/current").json()["arc"]
    assert current["chain"]["current_node_id"] == "arrival_gate"
    assert current["interaction_budget"] == {"used": 2, "maximum": 2, "freeform_allowed": False}

    chosen = choose(client, current, "inspect_outside")
    assert chosen.status_code == 200
    repeated = client.post(f"/api/storylets/{instance_id}/choose", json={"choice_id": "inspect_outside", "expected_transition_seq": 0})
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True


def test_timed_node_activates_once_after_six_hours(client):
    state, _, arc = activate_caravan(client)
    denied = choose(client, arc, "deny_entry")
    assert denied.status_code == 200
    waiting = denied.json()["arc"]
    assert waiting["chain"]["current_node_id"] == "camp_outside"
    assert state["active_scene"] is None
    timed = next(item for item in state["scheduled_events"]["entries"] if item["type"] == "story_arc_node" and item["status"] == "scheduled")
    set_time_point(state, timed["schedule"]["due_time"])
    assert len(activate_due_events(state, source="test")) == 1
    assert state["active_scene"]["flags"]["story_arc_node_id"] == "camp_outside"
    assert activate_due_events(state, source="test") == []
