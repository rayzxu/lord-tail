from __future__ import annotations

from app.ai.actions import validate_action
from app.ai.planner import plan_management_action
from app.engine.state import require_state
from conftest import start_game


def test_planner_is_deterministic_and_returns_legal_ranked_candidates(client):
    start_game(client)
    state = require_state()
    directive = state["strategic_directive"]
    first = plan_management_action(state, directive, seed=7)
    second = plan_management_action(state, directive, seed=7)
    assert first["selected_action"] == second["selected_action"]
    assert first["planned_sequence_labels"]
    assert 1 <= len(first["candidates"]) <= 3
    validation = validate_action(state, first["selected_action"], directive=directive, enforce_budget=True)
    assert validation["legal"] is True
