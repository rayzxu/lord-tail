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


def start_game(client: TestClient) -> dict:
    response = client.post("/api/game/start", json={
        "lord_name": "Ray",
        "lord_gender": "未说明",
        "realm_name": "北境",
        "appearance": "",
        "personality": "",
        "talents": [{"id": "harvest_hand"}, {"id": "charismatic_lord"}],
    })
    assert response.status_code == 200, response.text
    return response.json()["state"]
