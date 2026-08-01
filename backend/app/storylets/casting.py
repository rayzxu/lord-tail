from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..systems.characters import list_characters
from .generation import character_draft_from_cohort, materialization_capacity


def _class_id(character: dict[str, Any]) -> str:
    return str(character.get("components", {}).get("social_identity", {}).get("class_id", ""))


def _candidate_ok(character: dict[str, Any], spec: dict[str, Any], used: set[str]) -> bool:
    if character.get("status") in {"dead", "removed", "inactive", "left"}:
        return False
    if spec.get("distinct", True) and character.get("id") in used:
        return False
    if spec.get("adult") and int(character.get("age") or 0) < 18:
        return False
    if spec.get("class_any") and _class_id(character) not in spec["class_any"]:
        return False
    if spec.get("kind_any") and character.get("kind") not in spec["kind_any"]:
        return False
    return True


def cast_storylet(state: dict[str, Any], definition: dict[str, Any], generated_facts: dict[str, Any], *, seed: int, focus_character_id: str | None = None) -> dict[str, Any]:
    existing = list_characters(state, include_inactive=False)
    recent_cast = state.get("storylets", {}).get("recent_cast", {})
    cast: dict[str, str] = {}
    generated: dict[str, dict[str, Any]] = {}
    snapshots: dict[str, dict[str, Any]] = {}
    used: set[str] = set()
    relationship_drafts: list[dict[str, Any]] = []
    generated_per_class: dict[str, int] = {}
    eligible_classes = generated_facts.get("eligible_classes", []) or ["serfs"]
    for index, (role, spec) in enumerate(definition.get("roles", {}).items()):
        candidates = [item for item in existing if _candidate_ok(item, spec, used)]
        if role == "petitioner":
            cooled = [item for item in candidates if int(recent_cast.get(item.get("id"), 0)) < 2]
            candidates = cooled
        relation_role = str(spec.get("relation_to", ""))
        if relation_role and cast.get(relation_role):
            anchor_id = cast[relation_role]
            allowed_relations = set(spec.get("relation_any", []))
            edges = state.get("character_relationships", {}).get("edges", [])
            related_ids: set[str] = set()
            for edge in edges:
                if edge.get("status", "active") != "active":
                    continue
                if edge.get("from_character_id") == anchor_id and (edge.get("inverse_type") in allowed_relations or edge.get("type") in allowed_relations):
                    related_ids.add(str(edge.get("to_character_id")))
                if edge.get("to_character_id") == anchor_id and (edge.get("type") in allowed_relations or edge.get("inverse_type") in allowed_relations):
                    related_ids.add(str(edge.get("from_character_id")))
            candidates = [item for item in candidates if item.get("id") in related_ids]
        if focus_character_id:
            candidates.sort(key=lambda item: (item.get("id") != focus_character_id, int(recent_cast.get(item.get("id"), 0)), str(item.get("id"))))
        else:
            candidates.sort(key=lambda item: (int(recent_cast.get(item.get("id"), 0)), str(item.get("id"))))
        if candidates and spec.get("reuse_existing", True):
            selected = candidates[0]
            cast[role] = selected["id"]
            used.add(selected["id"])
            snapshots[role] = {"id": selected["id"], "name": selected["name"], "role": selected.get("role", ""), "class_id": _class_id(selected)}
            continue
        if spec.get("generate_if_missing") or (relation_role and spec.get("generate_relation_if_missing")):
            anchor_snapshot = snapshots.get(relation_role, {})
            preferred_classes = spec.get("class_any") or ([anchor_snapshot.get("class_id")] if anchor_snapshot.get("class_id") else eligible_classes)
            allowed = [value for value in preferred_classes if value in eligible_classes] or eligible_classes
            class_id = sorted(allowed)[(seed + index) % len(allowed)]
            if generated_per_class.get(class_id, 0) >= materialization_capacity(state, class_id):
                if spec.get("required"):
                    raise ValueError(f"{class_id} 阶级没有足够的未具名人口用于角色 {role}")
                continue
            draft = character_draft_from_cohort(state, class_id, seed=seed + 101 * (index + 1))
            generated_per_class[class_id] = generated_per_class.get(class_id, 0) + 1
            token = f"@generated:{role}"
            cast[role] = token
            generated[role] = draft
            snapshots[role] = {"id": token, "name": draft["name"], "role": draft.get("role", ""), "class_id": class_id}
            if relation_role:
                relationship_drafts.append({"from_role": relation_role, "to_role": role, "type": str((spec.get("relation_any") or ["family"])[0]), "strength": 70})
            continue
        if spec.get("required"):
            raise ValueError(f"必需角色 {role} 无可用人物")
    household = {"member_roles": list(cast), "head_role": next(iter(cast), ""), "class_id": snapshots.get(next(iter(cast), ""), {}).get("class_id", "")} if len(cast) > 1 and relationship_drafts else None
    return {"cast": cast, "generated_characters": generated, "cast_snapshots": snapshots, "relationship_drafts": relationship_drafts, "household_draft": household}
