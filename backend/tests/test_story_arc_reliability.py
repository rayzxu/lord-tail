from copy import deepcopy

from app.engine import scenes
from app.engine.time import set_time_point
from app.storylets.config import get_arc_definition
from app.storylets.graph import condition_matches
from app.storylets.runtime import audit_arc_consistency
from app.storylets.runtime import try_activate_arc_entry
from app.storylets.runs import canonical_definition, definition_hash
from app.storylets.service import normalize_storylet_state
from app.systems.scheduled_events import activate_due_events
from app.systems.scheduled_events import schedule_event
from conftest import start_game


def _due_entry(state):
    entry = next(item for item in state["scheduled_events"]["entries"] if item["type"] == "caravan_arrival")
    set_time_point(state, entry["schedule"]["due_time"])
    return entry


def _choose(client, arc, choice_id):
    return client.post(
        f"/api/storylets/{arc['current_instance']['id']}/choose",
        json={"choice_id": choice_id, "expected_transition_seq": arc["run"]["transition_seq"]},
    )


def test_busy_scene_queues_entry_without_creating_run_then_activates(client):
    state = start_game(client); entry = _due_entry(state)
    scenes.start_scene(state, "daily", "其他接见")
    activate_due_events(state, source="test")
    queued = next(item for item in state["scheduled_events"]["entries"] if item["id"] == entry["id"])
    assert queued["status"] == "due"
    assert queued["flags"]["queued_for_scene"] is True
    assert state["storylets"]["arc_runs"] == {}
    scenes.end_scene(state, "接见结束")
    activated = next(item for item in state["scheduled_events"]["entries"] if item["id"] == entry["id"])
    assert activated["status"] == "active"
    assert len(state["storylets"]["arc_runs"]) == 1
    run_id = activated["flags"]["story_arc_run_id"]
    assert audit_arc_consistency(state, run_id) == []


def test_entry_activation_failure_leaves_authoritative_state_unchanged(client, monkeypatch):
    state = start_game(client); entry = _due_entry(state)
    before = deepcopy(state)

    def fail_scene(*args, **kwargs):
        raise RuntimeError("injected scene failure")

    monkeypatch.setattr("app.storylets.runtime.scenes.start_scene", fail_scene)
    try:
        try_activate_arc_entry(state, entry["id"], seed=2001)
    except RuntimeError:
        pass
    else:
        raise AssertionError("failure injection did not fail")
    assert state == before


def test_definition_snapshot_and_hash_ignore_editor_layout(client):
    state = start_game(client); _due_entry(state); activate_due_events(state, source="test")
    arc = client.get("/api/story-arcs/current").json()["arc"]
    run = state["storylets"]["arc_runs"][arc["run"]["id"]]
    original_target = run["definition_snapshot"]["nodes"]["arrival_gate"]["choices"][0]["transition"]["to"]
    live = get_arc_definition("spring_caravan_visit")
    live["nodes"]["arrival_gate"]["choices"][0]["transition"]["to"] = "visit_resolved"
    try:
        response = _choose(client, arc, "admit_under_guard")
        assert response.status_code == 200
        assert response.json()["arc"]["run"]["current_node_id"] == original_target.replace("registration", "trade_hearing")
    finally:
        live["nodes"]["arrival_gate"]["choices"][0]["transition"]["to"] = original_target
    with_layout = {**deepcopy(run["definition_snapshot"]), "editor_layout": {"nodes": {"x": {"x": 1, "y": 2}}}}
    assert definition_hash(with_layout) == definition_hash(run["definition_snapshot"])


def test_terminal_choice_can_be_replayed_and_conflicting_choice_is_rejected(client):
    state = start_game(client); _due_entry(state); activate_due_events(state, source="test")
    first = client.get("/api/story-arcs/current").json()["arc"]
    second = _choose(client, first, "admit_under_guard").json()["arc"]
    visit_id = second["current_visit"]["visit_id"]
    completed = _choose(client, second, "approve_trade")
    assert completed.status_code == 200 and completed.json()["terminal"] is True
    run_id = completed.json()["run_id"]
    replay = client.post(f"/api/story-arcs/{run_id}/visits/{visit_id}/choose", json={"choice_id": "approve_trade", "expected_transition_seq": 0})
    assert replay.status_code == 200 and replay.json()["idempotent"] is True
    conflict = client.post(f"/api/story-arcs/{run_id}/visits/{visit_id}/choose", json={"choice_id": "heavy_tax"})
    assert conflict.status_code == 409
    assert "choice_conflict" in conflict.text


def test_empty_scene_step_does_not_consume_budget(client):
    state = start_game(client); _due_entry(state); activate_due_events(state, source="test")
    response = client.post("/api/game/scenes/current/step", json={})
    assert response.status_code == 422
    arc = client.get("/api/story-arcs/current").json()["arc"]
    assert arc["interaction_budget"]["used"] == 0


def test_any_is_and_with_sibling_conditions():
    state = {"resources": {"gold": 10}, "season": "春季"}
    run = {"facts": {"trust": 5, "route": "south"}, "node_visits": []}
    condition = {
        "any": [{"fact_equals": {"route": "south"}}, {"fact_equals": {"route": "north"}}],
        "resource_minimum": {"gold": 20},
    }
    assert condition_matches(condition, state, run) is False


def test_automatic_narratives_are_returned_in_order(client):
    state = start_game(client); _due_entry(state); activate_due_events(state, source="test")
    first = client.get("/api/story-arcs/current").json()["arc"]
    response = _choose(client, first, "admit_under_guard")
    assert [row["node_id"] for row in response.json()["transition_log"]] == ["registration"]
    assert "墨水、泥浆与货单" in response.json()["narrative"]
    second = response.json()["arc"]
    terminal = _choose(client, second, "approve_trade")
    assert [row["node_id"] for row in terminal.json()["transition_log"]] == ["market_day", "visit_resolved"]


def test_active_scene_run_wins_focus_over_older_timed_run(client):
    state = start_game(client); _due_entry(state); activate_due_events(state, source="test")
    first = client.get("/api/story-arcs/current").json()["arc"]
    waiting = _choose(client, first, "deny_entry").json()["arc"]
    older_run_id = waiting["run"]["id"]
    assert state["active_scene"] is None
    second_event = schedule_event(
        state, event_type="caravan_arrival", title="另一支商队", in_days=0,
        flags={"story_arc_definition_id": "spring_caravan_visit", "story_arc_seed": 3001},
        created_by="test",
    )
    activate_due_events(state, source="test")
    second_event = next(item for item in state["scheduled_events"]["entries"] if item["id"] == second_event["id"])
    response = client.get("/api/story-arcs/current").json()
    assert response["focused_arc_id"] == state["active_scene"]["flags"]["story_arc_run_id"]
    assert response["focused_arc_id"] != older_run_id
    assert {arc["run"]["id"] for arc in response["active_arcs"]} == {older_run_id, second_event["flags"]["story_arc_run_id"]}


def test_v2_chain_migration_is_idempotent_and_keeps_v1_instances(client):
    state = start_game(client)
    legacy_v1 = {"id": "story_evt_000001", "definition_id": "petition_building_credit", "node_key": "petition", "status": "ready"}
    legacy_v2 = {
        "id": "story_evt_000002", "definition_id": "spring_caravan_visit", "node_key": "arrival_gate",
        "chain_id": "story_chain_000001", "status": "awaiting_choice", "arc_node_kind": "choice",
        "selected_choice_id": None, "result": None, "cast": {}, "cast_snapshots": {}, "facts": {},
        "narrative_md": "旧开场", "freeform_steps_used": 1,
    }
    state["storylets"].update({
        "instances": [legacy_v1, legacy_v2],
        "chains": {"story_chain_000001": {
            "id": "story_chain_000001", "runtime_version": 2, "definition_id": "spring_caravan_visit",
            "definition_version": 1, "status": "active", "entry_scheduled_event_id": "evt_000001",
            "current_node_id": "arrival_gate", "current_instance_id": "story_evt_000002",
            "cast": {}, "cast_snapshots": {}, "facts": {}, "transition_seq": 0,
            "node_results": {}, "visited_nodes": [],
        }},
    })
    normalize_storylet_state(state)
    first = deepcopy(state["storylets"]["arc_runs"])
    normalize_storylet_state(state)
    assert state["storylets"]["arc_runs"] == first
    assert [item["id"] for item in state["storylets"]["instances"]] == ["story_evt_000001"]
    run = state["storylets"]["arc_runs"]["story_chain_000001"]
    assert run["runtime_version"] == 3
    assert run["node_visits"][0]["legacy_instance_id"] == "story_evt_000002"
    assert not ({"cast", "cast_snapshots", "facts"} & set(run["node_visits"][0]))
