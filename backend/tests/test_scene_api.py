from __future__ import annotations

from conftest import start_game


def test_scene_start_step_and_end_do_not_advance_turn(client):
    start_game(client)

    started = client.post("/api/game/scenes", json={"type": "dialogue", "title": "接见管家"})
    assert started.status_code == 200, started.text
    state = started.json()["state"]
    assert state["game_mode"] == "scene"
    assert state["active_scene"]["title"] == "接见管家"
    assert state["turn"] == 1
    assert state["time"]["calendar_day"] == 1

    stepped = client.post("/api/game/scenes/current/step", json={"input": "询问粮仓亏空。", "narrative": "管家跪下答话。"})
    assert stepped.status_code == 200, stepped.text
    state = stepped.json()["state"]
    assert state["turn"] == 1
    assert state["time"]["calendar_day"] == 1
    assert len(state["active_scene"]["recent_messages"]) == 2

    ended = client.post("/api/game/scenes/current/end", json={"summary": "审问结束。"})
    assert ended.status_code == 200, ended.text
    state = ended.json()["state"]
    assert state["game_mode"] == "strategic"
    assert state["active_scene"] is None
    assert state["turn"] == 1


def test_sexual_scene_type_is_allowed_and_preserves_flags(client):
    start_game(client)

    response = client.post("/api/game/scenes", json={
        "type": "sexual",
        "title": "领主与艾琳的成人场景",
        "participants": [
            {"type": "lord", "name": "Ray"},
            {"type": "character", "id": "char_1", "name": "艾琳", "age": 24},
        ],
        "flags": {"adult_scene": True, "sexual_scene": True, "requires_adult_participants": True, "character_id": "char_1"},
    })
    assert response.status_code == 200, response.text
    scene = response.json()["state"]["active_scene"]
    assert scene["type"] == "sexual"
    assert scene["flags"]["adult_scene"] is True
    assert scene["flags"]["sexual_scene"] is True
    assert scene["participants"][1]["id"] == "char_1"


def test_scene_advance_two_days_does_not_advance_turn(client):
    start_game(client)
    client.post("/api/game/scenes", json={"type": "dialogue", "title": "审问管家"})

    response = client.post(
        "/api/game/scenes/current/advance-time",
        json={"days": 2, "reason": "玩家说两天后继续审问", "run_due_strategic_turns": True},
    )
    assert response.status_code == 200, response.text
    state = response.json()["state"]

    assert state["turn"] == 1
    assert state["time"]["calendar_day"] == 3
    assert state["time"]["day_in_turn"] == 3
    assert state["active_scene"]["elapsed_days"] == 2


def test_scene_advance_nine_days_runs_due_strategic_turn_without_double_counting_days(client):
    start_game(client)
    client.post("/api/game/scenes", json={"type": "battle", "title": "边境冲突"})

    response = client.post(
        "/api/game/scenes/current/advance-time",
        json={"days": 9, "reason": "围城九日后", "run_due_strategic_turns": True},
    )
    assert response.status_code == 200, response.text
    state = response.json()["state"]

    assert state["turn"] == 2
    assert state["time"]["calendar_day"] == 10
    assert state["time"]["day_in_turn"] == 1
    assert state["active_scene"]["elapsed_days"] == 9
    assert any(event["phase"] == "end_turn" for event in response.json()["events"])
