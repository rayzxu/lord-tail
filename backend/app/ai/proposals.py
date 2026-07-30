from __future__ import annotations

from copy import deepcopy
from typing import Any

from .config import load_council_policies

DOMAIN_ORDER = ("finance", "military", "diplomacy")


def _metric(analysis: dict[str, Any], key: str) -> float | None:
    value = analysis.get("metrics", {}).get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _selection_score(proposal: dict[str, Any], analysis: dict[str, Any]) -> tuple[float, list[str]]:
    score = 1.0
    reasons: list[str] = []
    for key, threshold in proposal.get("selection", {}).items():
        suffix = "_below" if key.endswith("_below") else "_above" if key.endswith("_above") else ""
        if not suffix:
            continue
        metric_key = key[: -len(suffix)]
        value = _metric(analysis, metric_key)
        if value is None:
            continue
        matched = value < float(threshold) if suffix == "_below" else value > float(threshold)
        if matched:
            score += 10.0 + min(10.0, abs(float(threshold) - value))
            direction = "低于" if suffix == "_below" else "高于"
            reasons.append(f"{metric_key}={value:g}，{direction}警戒值 {threshold}")
    return score, reasons


def _risk_lines(analysis: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    food_runway = _metric(analysis, "food_runway_days")
    gold_runway = _metric(analysis, "gold_runway_days")
    readiness = _metric(analysis, "military_readiness")
    if food_runway is not None and food_runway < 27:
        risks.append("粮食储备不足三个战略回合，任何高成本扩张都可能放大饥荒风险。")
    if gold_runway is not None and gold_runway < 27:
        risks.append("金库正在收缩，工程与军队维护可能互相挤压。")
    if readiness is not None and readiness < 1:
        risks.append("当前战备低于外部威胁，经济投入需要保留防务余量。")
    return risks or ["主要风险来自天气、计划事件和预测期外的外交变化。"]


def _proposal_view(proposal_id: str, proposal: dict[str, Any], analysis: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    metrics = analysis.get("metrics", {})
    evidence = reasons or [
        f"粮食净变化 {metrics.get('food_net_turn', 0):g}/轮",
        f"金币净变化 {metrics.get('gold_net_turn', 0):g}/轮",
        f"战备值 {metrics.get('military_readiness', 0):g}",
        f"平均外交关系 {metrics.get('average_relation', 0):g}",
    ]
    return {
        "id": proposal_id,
        "domain": proposal["domain"],
        "title": proposal["title"],
        "minister": proposal["minister"],
        "summary": proposal["summary"],
        "speech_md": (
            f"### {proposal['minister']}的陈奏\n\n"
            f"> {proposal['summary']}\n\n"
            + "\n".join(f"- {line}" for line in evidence)
        ),
        "evidence": evidence,
        "targets": deepcopy(proposal.get("targets", {})),
        "budget_limits": deepcopy(proposal.get("budget_limits", {})),
        "allowed_action_tags": list(proposal.get("allowed_action_tags", [])),
        "action_tag_weights": deepcopy(proposal.get("action_tag_weights", {})),
        "weights": deepcopy(proposal.get("weights", {})),
        "risks": _risk_lines(analysis),
        "forecast": {
            "horizon_turns": 3,
            "status": "available_after_planning",
            "summary": "解决会议后，管理 AI 将以当前方针生成可执行的三回合滚动预测。",
        },
    }


def generate_proposals(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    configured = load_council_policies()["proposals"]
    selected: list[dict[str, Any]] = []
    for domain in DOMAIN_ORDER:
        ranked: list[tuple[float, str, dict[str, Any], list[str]]] = []
        for proposal_id, proposal in configured.items():
            if proposal.get("domain") == domain:
                score, reasons = _selection_score(proposal, analysis)
                ranked.append((score, proposal_id, proposal, reasons))
        ranked.sort(key=lambda row: (-row[0], row[1]))
        _, proposal_id, proposal, reasons = ranked[0]
        selected.append(_proposal_view(proposal_id, proposal, analysis, reasons))
    reserve = configured["status_quo_reserve"]
    selected.append(_proposal_view("status_quo_reserve", reserve, analysis, ["保留储备，避免在局势不明时启动昂贵计划。"]))
    return selected


def directive_from_proposal(
    proposal: dict[str, Any],
    *,
    directive_id: str,
    meeting_id: str,
    started_time: dict[str, Any],
    expires_time: dict[str, Any],
    duration_turns: int,
) -> dict[str, Any]:
    return {
        "id": directive_id,
        "source_meeting_id": meeting_id,
        "proposal_id": proposal["id"],
        "domain": proposal["domain"],
        "title": proposal["title"],
        "status": "active",
        "started_time": deepcopy(started_time),
        "expires_time": deepcopy(expires_time),
        "duration_strategic_turns": int(duration_turns),
        "executed_strategic_turns": 0,
        "targets": deepcopy(proposal.get("targets", {})),
        "budget_limits": deepcopy(proposal.get("budget_limits", {})),
        "allowed_action_tags": list(proposal.get("allowed_action_tags", [])),
        "action_tag_weights": deepcopy(proposal.get("action_tag_weights", {})),
        "weights": deepcopy(proposal.get("weights", {})),
        "progress": {},
        "completed_targets": [],
        "suspension_reason": None,
    }
