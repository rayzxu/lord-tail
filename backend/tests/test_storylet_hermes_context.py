from app.engine.hermes_context import build_run_payload
from app.storylets.service import instantiate_storylet
from app.systems.scheduled_events import activate_due_events
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
