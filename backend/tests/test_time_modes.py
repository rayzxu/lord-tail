from __future__ import annotations

from conftest import start_game


def test_initial_state_has_time_and_strategic_mode(client):
    state = start_game(client)

    assert state["turn"] == 1
    assert state["time"]["calendar_day"] == 1
    assert state["time"]["turn_days"] == 9
    assert state["time"]["day_in_turn"] == 1
    assert state["time"]["hour"] == 6
    assert state["time"]["hour_24"] == 6
    assert state["time"]["minute"] == 0
    assert state["time"]["clock_24"] == "06:00"
    assert state["game_mode"] == "strategic"
    assert state["active_scene"] is None

    time_response = client.get("/api/time")
    assert time_response.status_code == 200
    assert time_response.json()["game_mode"] == "strategic"
    assert time_response.json()["time"]["clock_24"] == "06:00"


def test_strategic_turn_advances_nine_days_and_turn(client):
    start_game(client)

    response = client.post("/api/game/strategic-turn", json={"command": "让领地按当前安排运转九天"})
    assert response.status_code == 200, response.text
    state = response.json()["state"]

    assert state["turn"] == 2
    assert state["time"]["calendar_day"] == 10
    assert state["time"]["day_in_turn"] == 1
    assert any(event["kind"] == "advanced" for event in response.json()["events"])


def test_strategic_turn_weather_updates_state_and_time(client):
    initial = start_game(client)
    assert initial["weather"] == "细雨"

    response = client.post("/api/game/strategic-turn", json={"command": "让领地按当前安排运转九天"})
    assert response.status_code == 200, response.text
    state = response.json()["state"]

    weather_events = [event for event in response.json()["events"] if event["phase"] == "weather" and event["kind"] == "changed"]
    assert weather_events
    assert state["weather"] == weather_events[-1]["data"]["weather"]
    assert state["time"]["weather"] == state["weather"]
    assert state["weather"] != "细雨"


def test_legacy_game_turn_uses_nine_day_strategic_clock(client):
    start_game(client)

    response = client.post("/api/game/turn", json={"command": "巡视村庄"})
    assert response.status_code == 200, response.text
    state = response.json()["state"]

    assert state["turn"] == 2
    assert state["time"]["calendar_day"] == 10


def test_strategic_turn_rejects_active_scene_without_force(client):
    start_game(client)
    client.post("/api/game/scenes", json={"type": "dialogue", "title": "接见管家"})

    response = client.post("/api/game/strategic-turn", json={"command": "推进九天"})
    assert response.status_code == 409


def test_scene_advance_time_uses_24_hour_clock(client):
    start_game(client)
    client.post("/api/game/scenes", json={"type": "dialogue", "title": "长夜审问"})

    response = client.post(
        "/api/game/scenes/current/advance-time",
        json={"hours": 13, "minutes": 30, "reason": "到十九点半继续", "run_due_strategic_turns": False},
    )
    assert response.status_code == 200, response.text
    state = response.json()["state"]

    assert state["time"]["calendar_day"] == 1
    assert state["time"]["hour_24"] == 19
    assert state["time"]["minute"] == 30
    assert state["time"]["clock_24"] == "19:30"
    assert state["active_scene"]["elapsed_hours"] == 13
    assert state["active_scene"]["elapsed_minutes"] == 30
    event = next(event for event in response.json()["events"] if event["phase"] == "scene_time")
    assert event["data"]["clock_24"] == "19:30"


def test_scribe_time_advance_works_without_active_scene(client):
    start_game(client)

    response = client.post(
        "/api/state/time/advance",
        json={"hours": 2, "minutes": 45, "reason": "书记官让庭审延后两个小时四十五分", "run_due_strategic_turns": False},
    )
    assert response.status_code == 200, response.text
    state = response.json()["state"]

    assert state["game_mode"] == "strategic"
    assert state["active_scene"] is None
    assert state["time"]["calendar_day"] == 1
    assert state["time"]["clock_24"] == "08:45"
    assert any(event["phase"] == "time" and event["kind"] == "scribe_time_advanced" for event in response.json()["events"])


def test_scribe_time_advance_updates_active_scene_elapsed(client):
    start_game(client)
    client.post("/api/game/scenes", json={"type": "dialogue", "title": "长谈"})

    response = client.post(
        "/api/state/time/advance",
        json={"hours": 3, "minutes": 15, "reason": "长谈持续到上午", "run_due_strategic_turns": False},
    )
    assert response.status_code == 200, response.text
    state = response.json()["state"]

    assert state["time"]["clock_24"] == "09:15"
    assert state["active_scene"]["elapsed_hours"] == 3
    assert state["active_scene"]["elapsed_minutes"] == 15


def test_scribe_time_advance_can_trigger_due_strategic_turn(client):
    start_game(client)

    response = client.post(
        "/api/state/time/advance",
        json={"days": 9, "reason": "九天过去", "run_due_strategic_turns": True},
    )
    assert response.status_code == 200, response.text
    state = response.json()["state"]

    assert state["turn"] == 2
    assert state["time"]["calendar_day"] == 10
    assert any(event["phase"] == "end_turn" for event in response.json()["events"])


def test_scene_advance_time_wraps_24_hour_clock_to_next_day(client):
    start_game(client)
    client.post("/api/game/scenes", json={"type": "dialogue", "title": "守夜"})

    response = client.post(
        "/api/game/scenes/current/advance-time",
        json={"hours": 20, "minutes": 15, "reason": "次日凌晨两点一刻", "run_due_strategic_turns": False},
    )
    assert response.status_code == 200, response.text
    state = response.json()["state"]

    assert state["time"]["calendar_day"] == 2
    assert state["time"]["day_in_turn"] == 2
    assert state["time"]["clock_24"] == "02:15"
    assert state["active_scene"]["elapsed_days"] == 0
    assert state["active_scene"]["elapsed_hours"] == 20
    assert state["active_scene"]["elapsed_minutes"] == 15
