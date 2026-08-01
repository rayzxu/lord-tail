from __future__ import annotations

from dataclasses import dataclass
from typing import Any


NODE_KINDS = {"choice", "automatic", "timed", "terminal"}
CONDITION_OPS = {
    "fact_equals", "fact_gte", "fact_lte", "choice_was", "resource_minimum",
    "relationship_minimum", "character_trait_minimum", "season_any", "any",
}


@dataclass(frozen=True)
class GraphAnalysis:
    reachable_nodes: frozenset[str]
    terminal_nodes: frozenset[str]
    paths: tuple[tuple[str, ...], ...]
    max_blocking_decisions: int


def _transitions(node: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(node.get("transition"), dict):
        rows.append(node["transition"])
    rows.extend(item for item in node.get("transitions", []) if isinstance(item, dict))
    for choice in node.get("choices", []):
        if isinstance(choice, dict) and isinstance(choice.get("transition"), dict):
            rows.append(choice["transition"])
    return rows


def _validate_condition(condition: Any, label: str) -> None:
    if condition in (None, {}):
        return
    if not isinstance(condition, dict):
        raise ValueError(f"{label}: transition.when 必须是对象")
    unknown = set(condition) - CONDITION_OPS
    if unknown:
        raise ValueError(f"{label}: 未知剧情图条件 {sorted(unknown)}")
    if "any" in condition:
        rows = condition["any"]
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"{label}: any 必须是非空数组")
        for index, item in enumerate(rows):
            _validate_condition(item, f"{label}.any[{index}]")


def analyze_graph(
    definition: dict[str, Any], *, effect_ops: set[str], valid_scene_types: set[str]
) -> GraphAnalysis:
    definition_id = str(definition.get("id", ""))
    label = str(definition.get("_source_file") or definition_id or "story arc")
    if int(definition.get("schema_version", 0)) != 2:
        raise ValueError(f"{label}: story arc schema_version 必须为 2")
    if not definition_id:
        raise ValueError(f"{label}: id 不能为空")
    if int(definition.get("version", 0)) < 1:
        raise ValueError(f"{label}: version 必须是正整数")
    nodes = definition.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        raise ValueError(f"{label}: nodes 必须是非空对象")
    entry = str(definition.get("entry_node", ""))
    if entry not in nodes:
        raise ValueError(f"{label}: entry_node 不存在：{entry}")

    edges: dict[str, list[str]] = {}
    terminals: set[str] = set()
    for node_id, raw_node in nodes.items():
        node_label = f"{label}:{node_id}"
        if not node_id or not isinstance(raw_node, dict):
            raise ValueError(f"{node_label}: node id 和内容必须有效")
        kind = str(raw_node.get("kind", ""))
        if kind not in NODE_KINDS:
            raise ValueError(f"{node_label}: 未知 node kind {kind}")
        scene_type = str(raw_node.get("scene_type") or definition.get("scene_type") or "daily")
        if scene_type not in valid_scene_types:
            raise ValueError(f"{node_label}: 未知 scene_type {scene_type}")
        if not str(raw_node.get("narrative_template_md", "")):
            raise ValueError(f"{node_label}: 缺少 narrative_template_md fallback")
        choices = raw_node.get("choices", [])
        if not isinstance(choices, list):
            raise ValueError(f"{node_label}: choices 必须是数组")
        choice_ids = [str(item.get("id", "")) for item in choices if isinstance(item, dict)]
        if kind in {"choice", "timed"} and not choice_ids:
            raise ValueError(f"{node_label}: {kind} 节点至少需要一个 choice")
        if len(choice_ids) != len(set(choice_ids)) or any(not item for item in choice_ids):
            raise ValueError(f"{node_label}: choice id 必须非空且唯一")
        for choice in choices:
            choice_label = f"{node_label}:{choice.get('id')}"
            if not str(choice.get("label", "")) or not str(choice.get("description_md", "")):
                raise ValueError(f"{choice_label}: choice 缺少 label 或 description_md")
            if not isinstance(choice.get("transition"), dict):
                raise ValueError(f"{choice_label}: choice 必须有且只有一个 transition")
            for effect in choice.get("effects", []):
                if not isinstance(effect, dict) or effect.get("op") not in effect_ops:
                    raise ValueError(f"{choice_label}: 未知 effect {effect}")
                if effect.get("op") in {"schedule_followup", "transition_to"}:
                    raise ValueError(f"{choice_label}: schema v2 禁止 {effect.get('op')}")
        for effect in raw_node.get("effects", []):
            if not isinstance(effect, dict) or effect.get("op") not in effect_ops:
                raise ValueError(f"{node_label}: 未知 effect {effect}")
        transitions = _transitions(raw_node)
        if kind == "terminal":
            terminals.add(str(node_id))
            if transitions:
                raise ValueError(f"{node_label}: terminal 不允许 transition")
            if not any(effect.get("op") == "resolve_entry_event" for effect in raw_node.get("effects", []) if isinstance(effect, dict)):
                raise ValueError(f"{node_label}: terminal 必须包含 resolve_entry_event")
        elif not transitions:
            raise ValueError(f"{node_label}: 非 terminal 节点必须有 transition")
        if kind == "automatic":
            fallbacks = [row for row in transitions if not row.get("when")]
            if len(fallbacks) != 1:
                raise ValueError(f"{node_label}: automatic 必须有且只有一个 fallback transition")
        if kind == "timed":
            delay_hours = int(raw_node.get("after_hours", 0) or 0)
            delay_days = int(raw_node.get("after_days", 0) or 0)
            if delay_hours <= 0 and delay_days <= 0:
                raise ValueError(f"{node_label}: timed 必须提供 after_hours 或 after_days")
        targets: list[str] = []
        for index, transition in enumerate(transitions):
            target = str(transition.get("to", ""))
            if target not in nodes:
                raise ValueError(f"{node_label}: transition[{index}] 指向不存在节点 {target}")
            _validate_condition(transition.get("when"), f"{node_label}.transition[{index}]")
            targets.append(target)
        edges[str(node_id)] = targets

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise ValueError(f"{label}: 第一版剧情图禁止环，检测到 {node_id}")
        if node_id in visited:
            return
        visiting.add(node_id)
        for target in edges[node_id]:
            visit(target)
        visiting.remove(node_id)
        visited.add(node_id)

    visit(entry)
    unreachable = set(nodes) - visited
    if unreachable:
        raise ValueError(f"{label}: 存在不可达节点 {sorted(unreachable)}")

    paths: list[tuple[str, ...]] = []

    def enumerate_paths(node_id: str, path: tuple[str, ...]) -> None:
        current = path + (node_id,)
        if node_id in terminals:
            paths.append(current)
            return
        for target in edges[node_id]:
            enumerate_paths(target, current)

    enumerate_paths(entry, ())
    if not paths:
        raise ValueError(f"{label}: 没有任何路径到达 terminal")
    max_blocking = max(
        sum(1 for node_id in path if nodes[node_id].get("blocking", nodes[node_id].get("kind") in {"choice", "timed"}))
        for path in paths
    )
    configured_max = int(definition.get("max_blocking_decisions", 0) or 0)
    if configured_max and max_blocking > configured_max:
        raise ValueError(f"{label}: blocking decision 最大深度 {max_blocking} 超过限制 {configured_max}")
    return GraphAnalysis(frozenset(visited), frozenset(terminals), tuple(paths), max_blocking)


def condition_matches(condition: dict[str, Any] | None, state: dict[str, Any], chain: dict[str, Any]) -> bool:
    if not condition:
        return True
    facts = chain.get("facts", {})
    if "any" in condition:
        return any(condition_matches(item, state, chain) for item in condition["any"])
    for key, spec in condition.items():
        if key == "fact_equals" and any(facts.get(name) != value for name, value in spec.items()):
            return False
        if key == "fact_gte" and any(float(facts.get(name, 0)) < float(value) for name, value in spec.items()):
            return False
        if key == "fact_lte" and any(float(facts.get(name, 0)) > float(value) for name, value in spec.items()):
            return False
        if key == "choice_was":
            values = {item.get("choice_id") for item in chain.get("node_results", {}).values() if isinstance(item, dict)}
            if str(spec) not in values:
                return False
        if key == "resource_minimum" and any(float(state.get("resources", {}).get(name, 0)) < float(value) for name, value in spec.items()):
            return False
        if key == "season_any" and state.get("season") not in spec:
            return False
        if key == "relationship_minimum":
            if float(chain.get("facts", {}).get("merchant_attitude", 0)) < float(spec):
                return False
        if key == "character_trait_minimum":
            return False
    return True
