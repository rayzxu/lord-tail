from __future__ import annotations

from conftest import start_game
from app.engine.hermes_context import build_scene_step_context
from app.engine.state import require_state


def test_start_game_has_default_caravan_with_canonical_due_time(client):
    state = start_game(client)
    events = state["scheduled_events"]["entries"]
    assert events
    caravan = events[0]
    assert caravan["type"] == "caravan_arrival"
    assert "created_time" in caravan
    assert "due_time" in caravan["schedule"]
    assert "due_turn" not in caravan["schedule"]
    assert "in_turns" not in caravan["schedule"]
    assert caravan["schedule"]["due_time"]["calendar_day"] == 90
    assert caravan["schedule"]["due_time"]["clock_24"] == "16:00"
    assert caravan["flags"]["story_arc_definition_id"] == "spring_caravan_visit"
    assert caravan["schedule"]["repeat"] is None


def test_schedule_event_api_uses_time_not_turns(client):
    start_game(client)
    response = client.post("/api/state/events/schedule", json={
        "event_type": "enemy_arrival",
        "title": "北方掠夺者逼近",
        "description_md": "敌军将在一日后抵达。",
        "in_days": 1,
        "clock_24": "08:00",
        "importance": 5,
        "related": {"factions": ["北方掠夺者"]},
    })
    assert response.status_code == 200, response.text
    event = response.json()["scheduled_event"]
    assert event["schedule"]["due_time"] == {"calendar_day": 2, "clock_24": "08:00", "season": "春季", "weather": "细雨"}
    assert "due_turn" not in event["schedule"]

    listing = client.get("/api/events?status=scheduled")
    assert listing.status_code == 200, listing.text
    assert any(item["title"] == "北方掠夺者逼近" for item in listing.json()["events"])


def test_strategic_turn_activates_due_event(client):
    start_game(client)
    response = client.post("/api/state/events/schedule", json={
        "event_type": "enemy_arrival",
        "title": "明日敌军抵达",
        "in_days": 1,
        "clock_24": "06:00",
        "importance": 5,
    })
    event_id = response.json()["scheduled_event"]["id"]

    turn = client.post("/api/game/strategic-turn", json={"command": "让领地运转九天", "source": "player"})
    assert turn.status_code == 200, turn.text
    data = turn.json()
    assert any(event["kind"] == "enemy_arrived" for event in data["events"])
    assert any(event["kind"] == "strategic_advance_interrupted" for event in data["events"])
    assert data["state"]["time"]["calendar_day"] == 2
    assert data["state"]["time"]["clock_24"] == "06:00"
    assert data["state"]["game_mode"] == "scene"
    assert data["state"]["active_scene"]["type"] == "battle"
    active = next(event for event in data["state"]["scheduled_events"]["entries"] if event["id"] == event_id)
    assert active["status"] == "active"


def test_scene_time_activates_due_event(client):
    start_game(client)
    client.post("/api/game/scenes", json={"type": "daily", "title": "等待消息"})
    scheduled = client.post("/api/state/events/schedule", json={
        "event_type": "diplomatic_response",
        "title": "使者回信",
        "in_days": 1,
        "clock_24": "06:00",
    }).json()["scheduled_event"]

    advanced = client.post("/api/game/scenes/current/advance-time", json={"days": 1, "reason": "第二天清晨"})
    assert advanced.status_code == 200, advanced.text
    data = advanced.json()
    assert any(event["kind"] == "diplomatic_response_arrived" for event in data["events"])
    event = next(item for item in data["state"]["scheduled_events"]["entries"] if item["id"] == scheduled["id"])
    assert event["status"] == "active"


def test_hermes_prompt_emphasizes_due_events(client):
    start_game(client)
    client.post("/api/state/events/schedule", json={
        "event_type": "caravan_arrival",
        "title": "立刻抵达的商队",
        "due_time": {"calendar_day": 1, "clock_24": "06:00"},
    })
    prompt = build_scene_step_context(require_state(), "我继续审问管家")
    assert "【必须处理的到期事件】" in prompt
    assert "立刻抵达的商队" in prompt
    assert "urgent_due_events" in prompt


def test_resolve_event_records_history_and_schedules_next_recurring(client):
    start_game(client)
    due = client.post("/api/state/events/schedule", json={
        "event_type": "caravan_arrival",
        "title": "今日商队",
        "due_time": {"calendar_day": 1, "clock_24": "06:00"},
    }).json()["scheduled_event"]
    client.post("/api/state/events/check-due")

    resolved = client.post(f"/api/state/events/{due['id']}/resolve", json={
        "result_md": "商队缴纳重税后离开。",
        "resolved_by": "hermes",
    })
    assert resolved.status_code == 200, resolved.text
    state = resolved.json()["state"]
    assert any(entry["source"] == "scheduled_event" and "今日商队" in entry["title"] for entry in state["history"]["entries"])
    next_events = [event for event in state["scheduled_events"]["entries"] if event.get("flags", {}).get("repeated_from") == due["id"]]
    assert next_events
    assert next_events[0]["schedule"]["due_time"]["calendar_day"] == 91
