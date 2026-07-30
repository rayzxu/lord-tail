from __future__ import annotations

from copy import deepcopy

from app.ai.analysis import analyze_realm
from app.engine.state import require_state
from conftest import start_game


def test_analysis_is_pure_and_contains_all_domains(client):
    start_game(client)
    state = require_state()
    before = deepcopy(state)
    first = analyze_realm(state)
    second = analyze_realm(state)
    assert state == before
    assert first == second
    assert {"finance", "military", "diplomacy", "stability", "metrics"} <= first.keys()
    assert "food_net_turn" in first["metrics"]
    assert "military_readiness" in first["metrics"]
    assert "war_risk" in first["metrics"]
