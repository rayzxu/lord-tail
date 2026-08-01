from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.engine.run_store import reset_runs_for_tests


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_agent_runs():
    reset_runs_for_tests()
    yield
    reset_runs_for_tests()


def start_game(client: TestClient, *, resolve_council: bool = True) -> dict:
    response = client.post("/api/game/start", json={
        "lord_name": "Ray",
        "lord_gender": "未说明",
        "realm_name": "北境",
        "appearance": "",
        "personality": "",
        "talents": [{"id": "harvest_hand"}, {"id": "charismatic_lord"}],
    })
    assert response.status_code == 200, response.text
    if resolve_council:
        # Existing subsystem tests begin after the mandatory opening council.
        # Council-specific tests pass resolve_council=False and exercise the
        # actual 06:00 -> 09:00 interruption through the public API.
        from app.engine.state import require_state
        from app.systems.council import open_meeting_from_event, resolve_meeting

        state = require_state()
        event = next(item for item in state["scheduled_events"]["entries"] if item["type"] == "council_session")
        meeting = open_meeting_from_event(state, event)
        resolve_meeting(state, meeting["id"], meeting["proposals"][0]["id"], "manual")
        # Legacy subsystem tests opt out of the production Storylet director so
        # an unrelated character petition cannot interrupt their second turn.
        # Storylet-specific tests explicitly re-enable it.
        state["storylets"]["director"]["enabled"] = False
        return state
    return response.json()["state"]
