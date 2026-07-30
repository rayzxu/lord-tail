from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..catalog import BUILDINGS, UNITS

POLICY_PATH = Path(__file__).parent.parent / "data" / "council_policies.json"
VALID_DOMAINS = {"finance", "military", "diplomacy", "reserve"}


@lru_cache(maxsize=1)
def load_council_policies() -> dict[str, Any]:
    data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    validate_council_policies(data)
    return data


def validate_council_policies(data: dict[str, Any]) -> None:
    if int(data.get("schema_version", 0)) != 1:
        raise ValueError("council_policies.json.schema_version 必须为 1")
    planner = data.get("planner")
    if not isinstance(planner, dict):
        raise ValueError("council_policies.json.planner 必须是对象")
    bounded = {
        "depth": (1, 6),
        "beam_width": (1, 20),
        "max_legal_actions": (1, 100),
        "max_build_coordinates": (1, 10),
        "max_expansions_per_node": (1, 50),
        "advice_count": (1, 10),
    }
    for key, (minimum, maximum) in bounded.items():
        value = int(planner.get(key, 0))
        if not minimum <= value <= maximum:
            raise ValueError(f"council_policies.json.planner.{key} 必须在 {minimum}..{maximum} 之间")
    proposals = data.get("proposals")
    if not isinstance(proposals, dict) or not proposals:
        raise ValueError("council_policies.json.proposals 必须是非空对象")
    for proposal_id, proposal in proposals.items():
        if proposal.get("domain") not in VALID_DOMAINS:
            raise ValueError(f"council_policies.json.proposals.{proposal_id}.domain 非法")
        for key, value in proposal.get("weights", {}).items():
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"council_policies.json.proposals.{proposal_id}.weights.{key} 必须是有限数")
        for tag, value in proposal.get("action_tag_weights", {}).items():
            if tag not in proposal.get("allowed_action_tags", []):
                raise ValueError(f"council_policies.json.proposals.{proposal_id}.action_tag_weights.{tag} 不在允许标签中")
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"council_policies.json.proposals.{proposal_id}.action_tag_weights.{tag} 必须是有限数")
        budget = proposal.get("budget_limits", {})
        ratio = float(budget.get("gold_spend_ratio", 0))
        if not 0 <= ratio <= 1:
            raise ValueError(f"council_policies.json.proposals.{proposal_id}.budget_limits.gold_spend_ratio 必须在 0..1")
    action_rules = data.get("action_rules", {})
    for group in ("tax_policies", "envoy_missions"):
        if not isinstance(action_rules.get(group), dict):
            raise ValueError(f"council_policies.json.action_rules.{group} 必须是对象")
    referenced = data.get("references", {})
    for building_id in referenced.get("buildings", []):
        if building_id not in BUILDINGS:
            raise ValueError(f"council_policies.json 引用了未知建筑：{building_id}")
    for unit_id in referenced.get("units", []):
        if unit_id not in UNITS:
            raise ValueError(f"council_policies.json 引用了未知兵种：{unit_id}")
