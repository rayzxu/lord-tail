import pytest
from fastapi import HTTPException

from app.engine.state import require_state
from app.storylets.relationships import create_relationship, relationships_for
from app.systems.characters import create_character
from conftest import start_game


def test_relationship_edge_is_unique_and_visible_from_both_people(client):
    state = start_game(client)
    first = create_character(state, {"name": "奥托", "age": 40, "flags": {"adult": True}})
    second = create_character(state, {"name": "艾妲", "age": 37, "flags": {"adult": True}})
    edge = create_relationship(state, {"from_character_id": first["id"], "to_character_id": second["id"], "type": "spouse", "strength": 70})
    duplicate = create_relationship(state, {"from_character_id": second["id"], "to_character_id": first["id"], "type": "spouse", "strength": 10})
    assert edge["id"] == duplicate["id"]
    assert relationships_for(state, first["id"])[0]["id"] == edge["id"]


def test_minor_cannot_be_given_spouse_relationship(client):
    state = start_game(client)
    adult = create_character(state, {"name": "成人", "age": 30, "flags": {"adult": True}})
    minor = create_character(state, {"name": "孩子", "age": 14, "flags": {"minor": True}})
    with pytest.raises(HTTPException) as exc:
        create_relationship(state, {"from_character_id": adult["id"], "to_character_id": minor["id"], "type": "spouse"})
    assert exc.value.status_code == 422
