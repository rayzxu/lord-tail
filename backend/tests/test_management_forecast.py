from __future__ import annotations

from copy import deepcopy

from app.ai.actions import legal_actions
from app.ai.forecast import forecast
from app.engine.state import require_state
from conftest import start_game


def test_forecast_is_reproducible_and_does_not_mutate_state(client):
    start_game(client)
    state = require_state()
    before = deepcopy(state)
    action = next(item for item in legal_actions(state) if item["type"] == "wait")
    first = forecast(state, [action], horizon=2, seed=1901)
    second = forecast(state, [action], horizon=2, seed=1901)
    assert state == before
    assert first == second
    assert len(first["turns"]) == 2
    assert first["final"]["turn"] == state["turn"] + 2
