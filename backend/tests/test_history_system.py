from __future__ import annotations

from conftest import start_game
from app.engine.hermes_context import compact_state_for_agent
from app.engine.state import require_state


def test_history_initialized_and_manual_record_api(client):
    state = start_game(client)
    assert state["history"]["entries"]
    assert state["history"]["entries"][0]["title"].endswith("开局")

    response = client.post("/api/state/history", json={
        "title": "商队首领被羞辱",
        "summary_md": "|对象|结果|\n|---|---|\n|南方商队|记下怨恨|",
        "details_md": "领主命令卫兵将商队首领按在泥水里。",
        "source": "scene",
        "importance": 4,
        "tags": ["caravan", "lord_event"],
        "related": {"factions": ["南方商队"], "people": ["商队首领"]},
        "created_by": "hermes",
    })
    assert response.status_code == 200, response.text
    entry = response.json()["history_entry"]
    assert entry["id"].startswith("hist_")
    assert entry["importance"] == 4

    listing = client.get("/api/history?tag=caravan&min_importance=4")
    assert listing.status_code == 200, listing.text
    data = listing.json()
    assert data["total"] == 1
    assert data["entries"][0]["summary_md"].startswith("|对象|结果|")

    detail = client.get(f"/api/history/{entry['id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["entry"]["title"] == "商队首领被羞辱"


def test_turn_pipeline_records_law_and_building_history(client):
    start_game(client)

    law_response = client.post("/api/game/strategic-turn", json={"command": "发布税令：每户多缴一枚铜币", "source": "player"})
    assert law_response.status_code == 200, law_response.text
    law_state = law_response.json()["state"]
    assert any(entry["title"] == "领主发布法令" for entry in law_state["history"]["entries"])
    assert law_response.json()["history_entries_created"]

    build_response = client.post("/api/game/strategic-turn", json={"command": "在 E4 建造窝棚区", "source": "player"})
    assert build_response.status_code == 200, build_response.text
    history = build_response.json()["state"]["history"]["entries"]
    assert any("窝棚区" in entry["title"] for entry in history)
    assert any("construction" in entry["tags"] for entry in history)


def test_battle_and_diplomacy_api_create_history(client):
    start_game(client)
    client.post("/api/state/army", json={"unit": "步兵", "value": 10})

    battle = client.post("/api/state/battles/resolve", json={
        "enemy": {"infantry": 3},
        "label": "黑逼堡外的试探战",
        "source": "api",
    })
    assert battle.status_code == 200, battle.text
    assert any(entry["title"] == "黑逼堡外的试探战" for entry in battle.json()["state"]["history"]["entries"])

    diplomacy = client.post("/api/state/diplomacy", json={"faction": "金鳞", "status": "战争"})
    assert diplomacy.status_code == 200, diplomacy.text
    assert any("金鳞" in entry["title"] and "diplomacy" in entry["tags"] for entry in diplomacy.json()["state"]["history"]["entries"])


def test_history_context_is_exposed_to_hermes_context(client):
    start_game(client)
    response = client.post("/api/state/history", json={
        "title": "E5 阳台上的威吓",
        "summary_md": "领主在堡垒阳台上威吓仆人与卫兵。",
        "source": "scene",
        "importance": 4,
        "tags": ["realm", "lord_event"],
        "related": {"tiles": ["5:5"], "people": ["Ray"]},
        "created_by": "hermes",
    })
    assert response.status_code == 200, response.text

    context = compact_state_for_agent(require_state(), {"selected_tile": {"x": 5, "y": 5, "map_source": "realm"}})
    titles = {entry["title"] for entry in context["history_context"]}
    assert "E5 阳台上的威吓" in titles
