from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from fastapi import HTTPException

from .config import get_arc_definition


RUNTIME_DEFINITION_KEYS = {
    "schema_version", "id", "version", "title", "description_md", "category",
    "priority", "importance", "scene_type", "entry_node", "max_blocking_decisions",
    "interaction_budget", "triggers", "roles", "parameters", "series", "nodes",
}


def canonical_definition(definition: dict[str, Any]) -> dict[str, Any]:
    """Return the immutable, author-semantic portion of an arc definition."""
    return deepcopy({key: definition[key] for key in RUNTIME_DEFINITION_KEYS if key in definition})


def definition_hash(definition: dict[str, Any]) -> str:
    encoded = json.dumps(canonical_definition(definition), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def definition_for_run(run: dict[str, Any]) -> dict[str, Any]:
    snapshot = run.get("definition_snapshot")
    if not isinstance(snapshot, dict) or not snapshot:
        snapshot = canonical_definition(get_arc_definition(str(run["definition_id"])))
        run["definition_snapshot"] = snapshot
        run["definition_hash"] = definition_hash(snapshot)
        run["definition_version"] = int(snapshot.get("version", 1))
        run["definition_snapshot_origin"] = "migrated_current_definition"
        run.setdefault("migration_warnings", []).append(
            "旧存档没有 Definition 快照；已按迁移时的当前发布版本冻结。"
        )
    return snapshot


def run_by_id(state: dict[str, Any], run_id: str) -> dict[str, Any]:
    run = state.get("storylets", {}).get("arc_runs", {}).get(run_id)
    if not isinstance(run, dict):
        raise HTTPException(404, "未找到 Story Arc")
    return run


def visit_by_id(run: dict[str, Any], visit_or_legacy_id: str) -> dict[str, Any]:
    for visit in run.get("node_visits", []):
        if visit.get("visit_id") == visit_or_legacy_id or visit.get("legacy_instance_id") == visit_or_legacy_id:
            return visit
    raise HTTPException(404, "未找到剧情节点访问记录")


def find_visit(state: dict[str, Any], visit_or_legacy_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    for run in state.get("storylets", {}).get("arc_runs", {}).values():
        if not isinstance(run, dict):
            continue
        for visit in run.get("node_visits", []):
            if visit.get("visit_id") == visit_or_legacy_id or visit.get("legacy_instance_id") == visit_or_legacy_id:
                return run, visit
    return None


def next_run_id(state: dict[str, Any]) -> str:
    storylets = state["storylets"]
    value = int(storylets.get("next_run_id", 1))
    storylets["next_run_id"] = value + 1
    return f"story_run_{value:06d}"


def next_visit_id(state: dict[str, Any]) -> str:
    storylets = state["storylets"]
    value = int(storylets.get("next_visit_id", 1))
    storylets["next_visit_id"] = value + 1
    return f"visit_{value:06d}"


def next_legacy_instance_id(state: dict[str, Any]) -> str:
    storylets = state["storylets"]
    value = int(storylets.get("next_instance_id", 1))
    storylets["next_instance_id"] = value + 1
    return f"story_evt_{value:06d}"


def execution_context(run: dict[str, Any], visit: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    """Ephemeral adapter for the shared effect executor; never persisted."""
    return {
        "id": visit["visit_id"],
        "legacy_instance_id": visit.get("legacy_instance_id"),
        "definition_id": run["definition_id"],
        "node_key": visit["node_id"],
        "title": node.get("title", visit["node_id"]),
        "category": run.get("category", "daily"),
        "priority": node.get("priority", run.get("priority", "major")),
        "chain_id": run["id"],
        "arc_run_id": run["id"],
        "scheduled_event_id": visit.get("scheduled_event_id") or run.get("entry_scheduled_event_id"),
        "cast": run.get("cast", {}),
        "cast_snapshots": run.get("cast_snapshots", {}),
        "facts": run.setdefault("facts", {}),
        "obligations": run.setdefault("obligations", []),
    }


def public_visit(run: dict[str, Any], visit: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    choices = [
        {key: deepcopy(value) for key, value in choice.items() if key not in {"effects", "transition"}}
        for choice in node.get("choices", [])
    ] if visit.get("status") == "awaiting_choice" else []
    # Compatibility projection. cast/facts live only on the Run, not the persisted Visit.
    return {
        "id": visit.get("legacy_instance_id") or visit["visit_id"],
        "visit_id": visit["visit_id"],
        "definition_id": run["definition_id"],
        "node_key": visit["node_id"],
        "title": node.get("title", visit["node_id"]),
        "category": run.get("category", "daily"),
        "chain_id": run["id"],
        "status": "resolved" if visit.get("status") == "completed" else visit.get("status"),
        "priority": node.get("priority", run.get("priority", "major")),
        "blocking": bool(node.get("blocking", node.get("kind") in {"choice", "timed"})),
        "scene_type": node.get("scene_type", run.get("scene_type", "daily")),
        "created_time": visit.get("created_time"),
        "activated_time": visit.get("activated_time"),
        "resolved_time": visit.get("resolved_time"),
        "scheduled_event_id": visit.get("scheduled_event_id"),
        "scene_id": visit.get("scene_id"),
        "cast": deepcopy(run.get("cast", {})),
        "cast_snapshots": deepcopy(run.get("cast_snapshots", {})),
        "facts": deepcopy(run.get("facts", {})),
        "choice_ids": [str(choice.get("id")) for choice in node.get("choices", [])],
        "choices": choices,
        "narrative_md": visit.get("narrative_md", ""),
        "narrative_source": "frozen_definition",
        "selected_choice_id": visit.get("choice_id"),
        "result": deepcopy(visit.get("effects_result")),
        "freeform_steps_used": int(visit.get("freeform_steps_used", 0)),
    }


def migrate_v2_runs(state: dict[str, Any]) -> None:
    """Idempotently collapse schema-v2 chains and instances into runtime-v3 runs."""
    storylets = state["storylets"]
    chains = storylets.get("chains", {})
    instances = storylets.get("instances", [])
    migrated_instance_ids: set[str] = set()
    for chain_id, chain in list(chains.items()):
        if not isinstance(chain, dict) or chain.get("runtime_version") != 2:
            continue
        if chain_id in storylets["arc_runs"]:
            continue
        graph = canonical_definition(get_arc_definition(str(chain["definition_id"])))
        visits: list[dict[str, Any]] = []
        for instance in instances:
            if not isinstance(instance, dict) or instance.get("chain_id") != chain_id:
                continue
            migrated_instance_ids.add(str(instance.get("id")))
            status = "completed" if instance.get("status") == "resolved" else instance.get("status", "ready")
            visits.append({
                "visit_id": next_visit_id(state), "legacy_instance_id": instance.get("id"),
                "node_id": instance.get("node_key"), "node_kind": instance.get("arc_node_kind") or graph.get("nodes", {}).get(instance.get("node_key"), {}).get("kind"),
                "status": status, "choice_id": instance.get("selected_choice_id"),
                "scene_id": instance.get("scene_id"), "scheduled_event_id": instance.get("scheduled_event_id"),
                "freeform_steps_used": int(instance.get("freeform_steps_used", 0)),
                "narrative_md": instance.get("narrative_md", ""), "effects_result": deepcopy(instance.get("result")),
                "transition_to": chain.get("node_results", {}).get(instance.get("node_key"), {}).get("transition_to"),
                "transition_seq": chain.get("node_results", {}).get(instance.get("node_key"), {}).get("transition_seq", 0),
                "created_time": instance.get("created_time"), "activated_time": instance.get("activated_time"),
                "resolved_time": instance.get("resolved_time"),
            })
        current = next((v for v in visits if v.get("legacy_instance_id") == chain.get("current_instance_id")), None)
        run = {
            **deepcopy(chain), "id": chain_id, "runtime_version": 3,
            "definition_snapshot": graph, "definition_hash": definition_hash(graph),
            "definition_snapshot_origin": "migrated_current_definition",
            "node_visits": visits, "current_visit_id": current.get("visit_id") if current else None,
        }
        run.pop("instance_ids", None); run.pop("current_instance_id", None); run.pop("node_results", None)
        storylets["arc_runs"][chain_id] = run
        del chains[chain_id]
        for event in state.get("scheduled_events", {}).get("entries", []):
            flags = event.get("flags", {})
            if flags.get("story_arc_chain_id") == chain_id:
                flags["story_arc_run_id"] = chain_id
        scene = state.get("active_scene")
        if isinstance(scene, dict) and scene.get("flags", {}).get("story_arc_chain_id") == chain_id:
            scene["flags"]["story_arc_run_id"] = chain_id
            if current:
                scene["flags"]["story_arc_visit_id"] = current["visit_id"]
    if migrated_instance_ids:
        storylets["instances"] = [item for item in instances if str(item.get("id")) not in migrated_instance_ids]

