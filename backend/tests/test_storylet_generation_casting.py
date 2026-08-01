from copy import deepcopy

from app.engine.state import require_state
from app.storylets.generation import materialization_capacity
from app.storylets.service import instantiate_storylet, normalize_storylet_state
from conftest import start_game


def test_normalize_and_preview_have_no_side_effects(client):
    state = start_game(client)
    before = deepcopy(state)
    normalize_storylet_state(state)
    normalize_storylet_state(state)
    assert state == before

    preview = instantiate_storylet(state, "petition_building_credit", seed=120, commit=False)
    assert preview["commit"] is False
    assert state == before


def test_materializing_existing_population_does_not_increase_population(client):
    state = start_game(client)
    before_population = state["resources"]["population"]
    before_class_population = sum(item["population"] for item in state["demographics"]["classes"].values())
    instance = instantiate_storylet(state, "petition_building_credit", seed=121, commit=True)
    character_id = instance["cast"]["petitioner"]
    character = next(item for item in state["characters"]["entries"] if item["id"] == character_id)
    origin = character["components"]["provenance"]["population_origin"]
    assert origin["cohort_member"] is True
    assert state["resources"]["population"] == before_population
    assert sum(item["population"] for item in state["demographics"]["classes"].values()) == before_class_population
    assert materialization_capacity(state, origin["class_id"]) >= 0
