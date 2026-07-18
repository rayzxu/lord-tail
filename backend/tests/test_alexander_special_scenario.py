from __future__ import annotations

import json
import random
from typing import Any

from app.catalog import BUILDINGS, TALENTS, UNITS
from app.engine.types import TurnContext
from app.systems import diplomacy, military


SCENARIO_SETTINGS = {
    "lord_name": "亚历山大",
    "lord_gender": "男",
    "realm_name": "黑逼堡",
    "appearance": "肥胖，矮小，龌蹉；小眼睛里全是贪婪",
    "personality": "媚上欺下",
}


def _scenario_talents() -> list[dict[str, str]]:
    stable_pool = [
        talent_id
        for talent_id, talent in TALENTS.items()
        if "initial_resources" not in talent.get("effects", {})
    ]
    return [{"id": talent_id} for talent_id in random.Random(1707).sample(stable_pool, 2)]


def _start_alexander(client) -> dict[str, Any]:
    response = client.post("/api/game/start", json={**SCENARIO_SETTINGS, "talents": _scenario_talents()})
    assert response.status_code == 200, response.text
    return response.json()


def _sse_json_events(text: str) -> list[dict[str, Any]]:
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line.removeprefix("data:").strip()))
    return events


def _give_large_test_budget(client) -> dict[str, Any]:
    response = client.post(
        "/api/state/resources",
        json={
            "values": {
                "gold": 10000,
                "food": 10000,
                "wood": 10000,
                "stone": 10000,
                "iron": 10000,
                "tools": 10000,
                "population": 1000,
            }
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["state"]


def test_alexander_opening_state_map_and_pressure_narrative(client):
    data = _start_alexander(client)
    state = data["state"]
    narrative = data["narrative"]

    assert state["turn"] == 1
    assert state["season"] == "春季"
    assert state["weather"] == "细雨"
    assert state["resources"]["morale"] == 50
    assert state["resources"]["authority"] == 50
    assert state["resources"]["population"] == 100
    assert state["resources"]["gold"] == 500
    assert state["resources"]["food"] == 500
    assert state["realm_name"] == "黑逼堡"
    assert state["lord_name"] == "亚历山大"
    assert state["lord_gender"] == "男"
    assert len(state["map"]) == 100
    assert next(tile for tile in state["map"] if tile["x"] == 5 and tile["y"] == 5)["label"] == "领主堡垒"
    assert next(tile for tile in state["map"] if tile["x"] == 5 and tile["y"] == 6)["label"] == "村舍"
    assert state["buildings"] == {"领主堡垒": 1, "村舍": 1}
    assert narrative.startswith("第1轮｜春季｜细雨")
    for expected in ["泥泞的城堡阳台", "俯瞰", "肥胖，矮小，龌蹉", "媚上欺下", "仆人", "卫兵", "敬畏", "恐惧", "税", "劳役"]:
        assert expected in narrative


def test_all_catalog_buildings_can_be_established_through_unified_state_api(client):
    _start_alexander(client)
    _give_large_test_budget(client)
    coordinates = [
        (x, y)
        for y in range(1, 11)
        for x in range(1, 11)
        if (x, y) not in {(5, 5), (5, 6)}
    ]

    for index, (building_id, building) in enumerate(BUILDINGS.items()):
        x, y = coordinates[index]
        before = client.get("/api/state").json()["state"]["buildings"].get(building["name"], 0)
        response = client.post("/api/state/buildings", json={"building": building_id, "action": "build", "count": 1, "x": x, "y": y})
        assert response.status_code == 200, f"{building_id}: {response.text}"
        state = response.json()["state"]
        assert state["buildings"][building["name"]] == before + 1
        assert next(tile for tile in state["map"] if tile["x"] == x and tile["y"] == y)["label"] == building["name"]


def test_training_every_unit_advances_from_command_to_completed_army(client):
    _start_alexander(client)
    _give_large_test_budget(client)
    response = client.post("/api/state/buildings", json={"building": "训练场", "action": "build", "count": 1})
    assert response.status_code == 200, response.text

    for unit_id, unit in UNITS.items():
        before = client.get("/api/state").json()["state"]["army"].get(unit_id, 0)
        response = client.post("/api/game/turn", json={"command": f"训练 2 名{unit['name']}"})
        assert response.status_code == 200, f"{unit_id}: {response.text}"
        assert any(event["kind"] == "training_started" for event in response.json()["events"])
        for _ in range(int(unit.get("training_turns", 1)) + 1):
            response = client.post("/api/game/turn", json={"command": "巡视训练场"})
            assert response.status_code == 200, response.text
        state = response.json()["state"]
        assert state["army"][unit_id] >= before + 2


def test_decree_tax_law_and_end_turn_income_pipeline(client):
    _start_alexander(client)
    _give_large_test_budget(client)
    client.post("/api/state/buildings", json={"building": "农田", "action": "build", "count": 1})
    before = client.get("/api/state").json()["state"]

    response = client.post("/api/game/turn", json={"command": "发布严苛加税法令，要求所有村舍缴纳春季泥税"})

    assert response.status_code == 200, response.text
    data = response.json()
    state = data["state"]
    kinds = {event["kind"] for event in data["events"]}
    assert "production" in kinds
    assert "tax_income" in kinds
    assert "population_consumption" in kinds
    assert "maintenance" in kinds
    assert state["turn"] == before["turn"] + 1
    assert state["laws"]
    assert any("泥税" in law for law in state["laws"])
    assert state["resources"]["morale"] < before["resources"]["morale"]
    assert state["changes"]["gold"] != 0
    assert state["changes"]["food"] != 0


def test_diplomacy_state_api_and_treaty_phase(client):
    _start_alexander(client)

    response = client.post("/api/state/diplomacy", json={"faction": "金鳞", "status": "战争"})
    assert response.status_code == 200, response.text
    entry = response.json()["state"]["diplomacy"]["金鳞"]
    assert entry["stance"] == "战争"
    assert entry["relation"] == -100
    assert entry["at_war"] is True

    state = response.json()["state"]
    context = TurnContext(command="签订短期停战")
    diplomacy.add_treaty(state, "金鳞", "停战", 1, context)
    assert state["diplomacy"]["金鳞"]["treaties"][0]["name"] == "停战"
    diplomacy.advance_treaties(state, context)
    assert not state["diplomacy"]["金鳞"]["treaties"]
    assert any(event.kind == "treaties_expired" for event in context.events)


def test_battle_resolution_uses_organization_counters_range_speed_and_rout(client):
    data = _start_alexander(client)
    state = data["state"]
    state["army"] = {"infantry": 12, "archers": 6, "cavalry": 2}
    state["army_status"] = {"organization": 20, "routed": False, "last_loss_ratio": 0.0}
    context = TurnContext(command="血鸦袭击边境")

    assert military.unit_counter_multiplier("infantry", "cavalry") > 1
    assert military.unit_counter_multiplier("cavalry", "archers") > 1
    high_attack, high_defense = military.apply_organization_modifiers(100, 100, 80)
    low_attack, low_defense = military.apply_organization_modifiers(100, 100, 20)
    assert low_attack < high_attack
    assert low_defense < high_defense
    assert military.average_range({"archers": 10}) > military.average_range({"infantry": 10})
    assert military.average_speed({"cavalry": 10}) > military.average_speed({"archers": 10})

    result = military.resolve_battle(
        state,
        {"enemy": {"infantry": 35, "archers": 20, "cavalry": 10}, "enemy_organization": 100},
        context,
    )

    assert result["winner"] in {"player", "enemy"}
    assert result["casualties"] >= 0
    assert state["battles"][-1] == result
    assert any(event.kind == "battle_resolved" for event in context.events)
    assert state["army_status"]["last_loss_ratio"] == result["casualties"] / result["pre_battle_total_units"]
    if result["casualties"] / result["pre_battle_total_units"] >= 0.15:
        assert state["army_status"]["routed"] is True


def test_hermes_story_turn_receives_scenario_context_and_applies_every_action_type(client, monkeypatch):
    from app.integrations import hermes_runs

    _start_alexander(client)
    _give_large_test_budget(client)
    monkeypatch.setenv("HERMES_RUNS_BASE_URL", "http://hermes.test")
    captured_payloads: list[dict[str, Any]] = []

    async def fake_create_run(payload):
        captured_payloads.append(payload)
        instructions = payload["instructions"]
        for expected in ["黑逼堡", "亚历山大", "肥胖，矮小，龌蹉", "媚上欺下", "allowed_actions"]:
            assert expected in instructions
        return {"run_id": "run_alexander_special", "status": "started"}

    async def fake_stream_run_events(hermes_run_id):
        assert hermes_run_id == "run_alexander_special"
        yield {"event": "reasoning.available", "text": "识别为压迫式开局与税役命令。"}
        yield {"event": "tool.started", "name": "lord_tail_get_state"}
        yield {"event": "tool.completed", "name": "lord_tail_get_state"}
        yield {
            "event": "run.completed",
            "output": json.dumps(
                {
                    "narrative": "亚历山大把泥税钉上公告栏，卫兵押着农奴散开。",
                    "suggestions": ["继续征税", "派兵巡逻"],
                    "actions": [
                        {"type": "resources", "payload": {"changes": {"gold": 12}}},
                        {"type": "population", "payload": {"delta": -1}},
                        {"type": "morale", "payload": {"delta": -4}},
                        {"type": "army", "payload": {"unit": "infantry", "delta": 3}},
                        {"type": "diplomacy", "payload": {"faction": "血鸦", "status": "战争"}},
                        {"type": "buildings", "payload": {"building": "farm", "action": "build", "count": 1, "x": 4, "y": 4}},
                        {
                            "type": "turn_event",
                            "payload": {
                                "phase": "events",
                                "kind": "oppressive_opening",
                                "severity": "warning",
                                "message": "泥税公告引发低声怨恨。",
                                "data": {"scene": "daily"},
                            },
                        },
                    ],
                },
                ensure_ascii=False,
            ),
        }

    monkeypatch.setattr(hermes_runs, "create_run", fake_create_run)
    monkeypatch.setattr(hermes_runs, "stream_run_events", fake_stream_run_events)

    created = client.post("/api/agent/runs", json={"mode": "story_turn", "input": "发布泥税并命令卫兵弹压"})
    assert created.status_code == 200, created.text
    assert created.json()["events_url"].endswith("/events")
    with client.stream("GET", f"/api/agent/runs/{created.json()['run_id']}/events") as response:
        assert response.status_code == 200, response.text
        events = _sse_json_events(response.read().decode())

    assert captured_payloads
    assert "tool.started" in [event["event"] for event in events]
    action_results = [event["data"] for event in events if event["event"] == "state.action_applied"]
    assert {result["type"] for result in action_results} == {"resources", "population", "morale", "army", "diplomacy", "buildings", "turn_event"}
    state = client.get("/api/state").json()["state"]
    assert state["army"]["infantry"] >= 3
    assert state["diplomacy"]["血鸦"]["stance"] == "战争"
    assert state["buildings"]["农田"] >= 1
    assert state["recent_events"][-1]["kind"] == "oppressive_opening"
