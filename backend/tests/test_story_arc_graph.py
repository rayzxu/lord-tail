from copy import deepcopy

import pytest

from app.engine.scenes import VALID_SCENE_TYPES
from app.storylets.config import EFFECT_OPS, get_arc_definition, validate_storylet_catalog
from app.storylets.graph import analyze_graph


def analysis(definition):
    return analyze_graph(definition, effect_ops=EFFECT_OPS, valid_scene_types=VALID_SCENE_TYPES)


def test_spring_caravan_graph_is_valid_dag_with_bounded_decisions():
    validate_storylet_catalog()
    result = analysis(get_arc_definition("spring_caravan_visit"))
    assert len(result.reachable_nodes) == 7
    assert result.terminal_nodes == {"visit_resolved"}
    assert result.max_blocking_decisions <= 3
    assert len(result.paths) >= 6


@pytest.mark.parametrize("mutation, message", [
    (lambda graph: graph.update(entry_node="missing"), "entry_node"),
    (lambda graph: graph["nodes"]["arrival_gate"]["choices"][0]["transition"].update(to="missing"), "不存在节点"),
    (lambda graph: graph["nodes"]["registration"]["transition"].update(to="arrival_gate"), "禁止环"),
])
def test_invalid_graphs_fail_static_validation(mutation, message):
    graph = deepcopy(get_arc_definition("spring_caravan_visit"))
    mutation(graph)
    with pytest.raises(ValueError, match=message):
        analysis(graph)
