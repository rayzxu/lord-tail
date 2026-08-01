from app.engine.time import set_time_point
from app.systems.scheduled_events import activate_due_events
from conftest import start_game


def test_spring_caravan_refusal_schedules_one_delayed_occurrence(client):
    state = start_game(client)
    entry = next(item for item in state["scheduled_events"]["entries"] if item["type"] == "caravan_arrival")
    assert entry["flags"]["story_arc_definition_id"] == "spring_caravan_visit"
    assert entry["schedule"]["repeat"] is None
    set_time_point(state, entry["schedule"]["due_time"])
    activate_due_events(state)
    arc = client.get("/api/story-arcs/current").json()["arc"]
    client.post(f"/api/storylets/{arc['current_instance']['id']}/choose", json={"choice_id": "deny_entry", "expected_transition_seq": 0})
    timed = next(item for item in state["scheduled_events"]["entries"] if item["type"] == "story_arc_node")
    set_time_point(state, timed["schedule"]["due_time"])
    activate_due_events(state)
    arc = client.get("/api/story-arcs/current").json()["arc"]
    completed = client.post(f"/api/storylets/{arc['current_instance']['id']}/choose", json={"choice_id": "send_away", "expected_transition_seq": arc["chain"]["transition_seq"]})
    assert completed.status_code == 200, completed.text
    future = [item for item in state["scheduled_events"]["entries"] if item.get("flags", {}).get("series_id") == "southern_caravan_route" and item["status"] == "scheduled"]
    assert len(future) == 1
    assert future[0]["schedule"]["due_time"]["calendar_day"] == state["time"]["calendar_day"] + 180
