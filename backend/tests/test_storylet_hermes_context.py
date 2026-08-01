from app.engine.hermes_context import build_run_payload
from app.storylets.service import instantiate_storylet
from app.systems.scheduled_events import activate_due_events
from app.engine.time import set_time_point
from conftest import start_game


def test_storylet_hermes_modes_are_read_only_and_receive_frozen_instance(client):
    state = start_game(client)
    instance = instantiate_storylet(state, "petition_building_credit", seed=610, commit=True)
    activate_due_events(state, source="test")
    payload = build_run_payload("storylet_opening", "润色开场", state, {"story_event_id": instance["id"]})
    assert payload["metadata"]["mode"] == "storylet_opening"
    assert "完全只读" in payload["instructions"]
    assert "不替玩家选择" in payload["instructions"]
    assert instance["id"] in payload["instructions"]
    assert instance["facts"]["building_name"] in payload["instructions"]


def test_story_arc_hermes_context_exposes_only_current_locked_node(client):
    state = start_game(client)
    entry = next(item for item in state["scheduled_events"]["entries"] if item["type"] == "caravan_arrival")
    set_time_point(state, entry["schedule"]["due_time"])
    activate_due_events(state, source="test")
    instance_id = state["storylets"]["current_instance_id"]
    payload = build_run_payload("storylet_opening", "润色商队开场", state, {"story_event_id": instance_id})
    assert "lord-tail-story-arc" in payload["instructions"]
    assert '"current_node_id": "arrival_gate"' in payload["instructions"]
    assert "只演出当前节点" in payload["instructions"]
    assert "不替玩家选择" in payload["instructions"]
