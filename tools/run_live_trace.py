from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_APP = REPO_ROOT / "backend" / "app"
if str(BACKEND_APP.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_APP.parent))

from app.catalog import BUILDINGS, TALENTS, UNITS  # noqa: E402


SCENARIO_SETTINGS = {
    "lord_name": "亚历山大",
    "lord_gender": "男",
    "realm_name": "黑逼堡",
    "appearance": "肥胖，矮小，龌蹉；小眼睛里全是贪婪",
    "personality": "媚上欺下",
}


@dataclass
class TraceStep:
    name: str
    expected_api: list[str]
    actual_api: list[str] = field(default_factory=list)
    api_correct: bool = False
    input: Any = None
    output: Any = None
    checks: dict[str, Any] = field(default_factory=dict)
    hermes_events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    duration_seconds: float = 0.0


class ApiRecorder:
    def __init__(self, backend_url: str, hermes_url: str, hermes_key: str):
        self.backend_url = backend_url.rstrip("/")
        self.hermes_url = hermes_url.rstrip("/")
        self.hermes_headers = {"Authorization": f"Bearer {hermes_key}"} if hermes_key else {}
        self.client = httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0))

    def close(self) -> None:
        self.client.close()

    def backend(self, method: str, path: str, **kwargs: Any) -> tuple[str, httpx.Response]:
        api = f"{method.upper()} {path}"
        response = self.client.request(method, f"{self.backend_url}{path}", **kwargs)
        return api, response

    def hermes(self, method: str, path: str, **kwargs: Any) -> tuple[str, httpx.Response]:
        api = f"{method.upper()} {path}"
        headers = dict(self.hermes_headers)
        headers.update(kwargs.pop("headers", {}) or {})
        response = self.client.request(method, f"{self.hermes_url}{path}", headers=headers, **kwargs)
        return api, response

    def backend_sse(self, path: str) -> tuple[str, list[dict[str, Any]], str]:
        api = f"GET {path}"
        raw_chunks: list[str] = []
        events: list[dict[str, Any]] = []
        with self.client.stream("GET", f"{self.backend_url}{path}") as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    raw_chunks.append(line)
                if line.startswith("data:"):
                    payload = line.removeprefix("data:").strip()
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        event = {"event": "parse_error", "raw": payload}
                    events.append(event)
                    if event.get("event") in {"run.completed", "run.failed", "run.cancelled"}:
                        break
        return api, events, "\n".join(raw_chunks)


def scenario_talents() -> list[dict[str, str]]:
    stable_pool = [
        talent_id
        for talent_id, talent in TALENTS.items()
        if "initial_resources" not in talent.get("effects", {})
    ]
    return [{"id": talent_id} for talent_id in random.Random(1707).sample(stable_pool, 2)]


def json_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text


def call_step(
    recorder: ApiRecorder,
    *,
    name: str,
    expected_api: list[str],
    calls: list[tuple[str, str, dict[str, Any]]],
    check,
    step_input: Any = None,
) -> TraceStep:
    started = time.monotonic()
    step = TraceStep(name=name, expected_api=expected_api, input=step_input)
    outputs: list[Any] = []
    try:
        for method, path, kwargs in calls:
            actual_api, response = recorder.backend(method, path, **kwargs)
            step.actual_api.append(actual_api)
            outputs.append({
                "api": actual_api,
                "status_code": response.status_code,
                "body": json_body(response),
            })
            response.raise_for_status()
        step.output = outputs[-1]["body"] if len(outputs) == 1 else outputs
        check_result = check(step.output, outputs)
        step.checks = check_result if isinstance(check_result, dict) else {"passed": bool(check_result)}
        step.api_correct = step.expected_api == step.actual_api and bool(step.checks.get("passed", False))
    except Exception as error:
        step.output = outputs
        step.error = str(error)
        step.checks = {"passed": False}
        step.api_correct = False
    finally:
        step.duration_seconds = round(time.monotonic() - started, 3)
    return step


def hermes_run_step(
    recorder: ApiRecorder,
    *,
    name: str,
    mode: str,
    input_text: str,
    client_context: dict[str, Any],
    expected_hermes_events: list[str],
    expected_state_action_types: set[str] | None = None,
    expect_tool_api_calls: bool = False,
    expect_non_json_final: bool = False,
) -> TraceStep:
    started = time.monotonic()
    request_body = {"mode": mode, "input": input_text, "client_context": client_context}
    step = TraceStep(
        name=name,
        expected_api=[
            *(["GET /api/state"] if expect_tool_api_calls else []),
            "POST /api/agent/runs",
            "GET /api/agent/runs/{run_id}/events",
            "GET /api/agent/runs/{run_id}",
            *(["GET /api/state"] if expect_tool_api_calls else []),
        ],
        input=request_body,
        checks={"expected_hermes_events": expected_hermes_events},
    )
    try:
        state_before = None
        if expect_tool_api_calls:
            api, before_response = recorder.backend("GET", "/api/state")
            step.actual_api.append(api)
            state_before = json_body(before_response)["state"]
            before_response.raise_for_status()
        api, create_response = recorder.backend("POST", "/api/agent/runs", json=request_body)
        step.actual_api.append(api)
        create_body = json_body(create_response)
        create_response.raise_for_status()
        run_id = create_body["run_id"]
        events_path = f"/api/agent/runs/{run_id}/events"
        status_path = f"/api/agent/runs/{run_id}"
        api, events, raw_sse = recorder.backend_sse(events_path)
        step.actual_api.append("GET /api/agent/runs/{run_id}/events")
        api, status_response = recorder.backend("GET", status_path)
        step.actual_api.append("GET /api/agent/runs/{run_id}")
        status_body = json_body(status_response)
        status_response.raise_for_status()
        state_after = None
        if expect_tool_api_calls:
            api, after_response = recorder.backend("GET", "/api/state")
            step.actual_api.append(api)
            state_after = json_body(after_response)["state"]
            after_response.raise_for_status()
        event_names = [str(event.get("event", "")) for event in events]
        action_types = {
            str(event.get("data", {}).get("type"))
            for event in events
            if event.get("event") == "state.action_applied"
        }
        expected_state_action_types = expected_state_action_types or set()
        expected_events_present = all(name in event_names for name in expected_hermes_events)
        expected_actions_present = expected_state_action_types.issubset(action_types)
        tool_events_present = any(name.startswith("tool.") for name in event_names)
        final_text = str(status_body.get("final_text", ""))
        non_json_final = not final_text.strip().startswith(("```json", "{"))
        step.hermes_events = events
        step.output = {
            "create": create_body,
            "events": events,
            "raw_sse": raw_sse,
            "status": status_body,
            "state_before": state_before,
            "state_after": state_after,
        }
        step.checks.update({
            "passed": expected_events_present
            and expected_actions_present
            and (tool_events_present if expect_tool_api_calls else True)
            and (non_json_final if expect_non_json_final else True)
            and status_body.get("status") == "completed",
            "status": status_body.get("status"),
            "event_names": event_names,
            "tool_events_present": tool_events_present,
            "expected_events_present": expected_events_present,
            "expected_state_action_types": sorted(expected_state_action_types),
            "actual_state_action_types": sorted(action_types),
            "expected_actions_present": expected_actions_present,
            "non_json_final": non_json_final,
            "final_text": final_text,
        })
        step.api_correct = step.actual_api == step.expected_api and bool(step.checks["passed"])
    except Exception as error:
        step.error = str(error)
        step.checks["passed"] = False
        step.api_correct = False
    finally:
        step.duration_seconds = round(time.monotonic() - started, 3)
    return step


def run_trace(backend_url: str, hermes_url: str, hermes_key: str) -> dict[str, Any]:
    recorder = ApiRecorder(backend_url, hermes_url, hermes_key)
    steps: list[TraceStep] = []
    try:
        # Health and profile checks.
        started = time.monotonic()
        health_step = TraceStep(
            name="health_and_profile",
            expected_api=["GET /api/health", "GET /health", "GET /v1/skills", "GET /v1/toolsets", "GET /v1/capabilities"],
        )
        try:
            api, backend_health = recorder.backend("GET", "/api/health")
            health_step.actual_api.append(api)
            api, hermes_health = recorder.hermes("GET", "/health")
            health_step.actual_api.append(api)
            api, skills = recorder.hermes("GET", "/v1/skills")
            health_step.actual_api.append(api)
            api, toolsets = recorder.hermes("GET", "/v1/toolsets")
            health_step.actual_api.append(api)
            api, capabilities = recorder.hermes("GET", "/v1/capabilities")
            health_step.actual_api.append(api)
            bodies = {
                "backend_health": json_body(backend_health),
                "hermes_health": json_body(hermes_health),
                "skills": json_body(skills),
                "toolsets": json_body(toolsets),
                "capabilities": json_body(capabilities),
            }
            enabled_toolsets = {item["name"] for item in bodies["toolsets"].get("data", []) if item.get("enabled")}
            has_skill = any(item.get("name") == "lord-tail-game" for item in bodies["skills"].get("data", []))
            health_step.output = bodies
            health_step.checks = {
                "passed": bodies["backend_health"].get("status") == "ok"
                and bodies["hermes_health"].get("status") == "ok"
                and bodies["capabilities"].get("model") == "deepseek-v4-flash"
                and has_skill
                and {"terminal", "skills"}.issubset(enabled_toolsets),
                "has_lord_tail_skill": has_skill,
                "enabled_toolsets": sorted(enabled_toolsets),
                "model": bodies["capabilities"].get("model"),
            }
            health_step.api_correct = health_step.expected_api == health_step.actual_api and health_step.checks["passed"]
        except Exception as error:
            health_step.error = str(error)
            health_step.checks = {"passed": False}
        health_step.duration_seconds = round(time.monotonic() - started, 3)
        steps.append(health_step)

        start_body = {**SCENARIO_SETTINGS, "talents": scenario_talents()}
        steps.append(call_step(
            recorder,
            name="start_alexander_scenario",
            expected_api=["POST /api/game/start"],
            calls=[("POST", "/api/game/start", {"json": start_body})],
            step_input=start_body,
            check=lambda body, _: {
                "passed": body["state"]["turn"] == 1
                and body["state"]["season"] == "春季"
                and body["state"]["weather"] == "细雨"
                and body["state"]["resources"]["morale"] == 50
                and body["state"]["resources"]["authority"] == 50
                and body["state"]["resources"]["population"] == 100
                and body["state"]["resources"]["gold"] == 500
                and body["state"]["resources"]["food"] == 500
                and "泥泞的城堡阳台" in body["narrative"],
                "narrative_excerpt": body.get("narrative", "")[:240],
            },
        ))

        budget_body = {
            "values": {
                "gold": 10000,
                "food": 10000,
                "wood": 10000,
                "stone": 10000,
                "iron": 10000,
                "tools": 10000,
                "population": 1000,
            }
        }
        steps.append(call_step(
            recorder,
            name="give_large_test_budget",
            expected_api=["POST /api/state/resources"],
            calls=[("POST", "/api/state/resources", {"json": budget_body})],
            step_input=budget_body,
            check=lambda body, _: {"passed": body["state"]["resources"]["gold"] == 10000 and body["state"]["resources"]["population"] == 1000},
        ))

        coordinates = [
            (x, y)
            for y in range(1, 11)
            for x in range(1, 11)
            if (x, y) not in {(5, 5), (5, 6)}
        ]
        for index, (building_id, building) in enumerate(BUILDINGS.items()):
            x, y = coordinates[index]
            body = {"building": building_id, "action": "build", "count": 1, "x": x, "y": y}
            steps.append(call_step(
                recorder,
                name=f"build_{building_id}",
                expected_api=["POST /api/state/buildings"],
                calls=[("POST", "/api/state/buildings", {"json": body})],
                step_input=body,
                check=lambda response_body, _, building_name=building["name"], tx=x, ty=y: {
                    "passed": response_body["state"]["buildings"].get(building_name, 0) >= 1
                    and next(tile for tile in response_body["state"]["map"] if tile["x"] == tx and tile["y"] == ty)["label"] == building_name,
                    "building": building_name,
                },
            ))

        for unit_id, unit in UNITS.items():
            train_command = {"command": f"训练 2 名{unit['name']}"}
            advance_calls = [
                ("POST", "/api/game/turn", {"json": {"command": "巡视训练场"}})
                for _ in range(int(unit.get("training_turns", 1)) + 1)
            ]
            steps.append(call_step(
                recorder,
                name=f"train_{unit_id}",
                expected_api=["POST /api/game/turn", *["POST /api/game/turn" for _ in advance_calls]],
                calls=[("POST", "/api/game/turn", {"json": train_command}), *advance_calls],
                step_input={"start_training": train_command, "advance_turns": len(advance_calls)},
                check=lambda body, _, uid=unit_id: {
                    "passed": body[-1]["body"]["state"]["army"].get(uid, 0) >= 2 if isinstance(body, list) else body["state"]["army"].get(uid, 0) >= 2,
                    "army": body[-1]["body"]["state"]["army"] if isinstance(body, list) else body["state"]["army"],
                },
            ))

        decree_body = {"command": "发布严苛加税法令，要求所有村舍缴纳春季泥税"}
        steps.append(call_step(
            recorder,
            name="decree_tax_law_and_turn_pipeline",
            expected_api=["POST /api/game/turn"],
            calls=[("POST", "/api/game/turn", {"json": decree_body})],
            step_input=decree_body,
            check=lambda body, _: {
                "passed": {"production", "tax_income", "population_consumption", "maintenance"}.issubset({event["kind"] for event in body["events"]})
                and any("泥税" in law for law in body["state"].get("laws", [])),
                "event_kinds": [event["kind"] for event in body["events"]],
                "laws": body["state"].get("laws", []),
                "changes": body["state"].get("changes", {}),
            },
        ))

        diplomacy_body = {"faction": "金鳞", "status": "战争"}
        steps.append(call_step(
            recorder,
            name="diplomacy_set_war",
            expected_api=["POST /api/state/diplomacy"],
            calls=[("POST", "/api/state/diplomacy", {"json": diplomacy_body})],
            step_input=diplomacy_body,
            check=lambda body, _: {
                "passed": body["state"]["diplomacy"]["金鳞"]["stance"] == "战争"
                and body["state"]["diplomacy"]["金鳞"]["at_war"] is True,
                "diplomacy": body["state"]["diplomacy"]["金鳞"],
            },
        ))

        army_body = {"unit": "infantry", "value": 20}
        steps.append(call_step(
            recorder,
            name="army_set_infantry",
            expected_api=["POST /api/state/army"],
            calls=[("POST", "/api/state/army", {"json": army_body})],
            step_input=army_body,
            check=lambda body, _: {"passed": body["state"]["army"]["infantry"] == 20, "army": body["state"]["army"]},
        ))

        steps.append(hermes_run_step(
            recorder,
            name="real_hermes_describe_lord",
            mode="describe_lord",
            input_text="用两句话描述领主亚历山大，不要修改状态。",
            client_context={"target_type": "lord"},
            expected_hermes_events=["run.started", "message.delta", "run.completed"],
        ))

        steps.append(hermes_run_step(
            recorder,
            name="real_hermes_story_turn_with_api_calls",
            mode="story_turn",
            input_text=(
                "发布小额泥税并命令卫兵弹压骚动。请作为故事讲述者和执行者推进剧情。"
                "如果你决定改变状态，必须使用工具调用 Lord Tail HTTP API，"
                "例如 POST /api/state/resources、POST /api/state/morale、POST /api/agent/events。"
                "最终回答只能输出中文故事和简短建议，不要输出 JSON 或 actions。"
            ),
            client_context={"scene": "daily", "test": "live_trace_expected_api_calls"},
            expected_hermes_events=["run.started", "run.completed"],
            expect_tool_api_calls=True,
            expect_non_json_final=True,
        ))

        gap = TraceStep(
            name="battle_public_api_gap",
            expected_api=["POST /api/state/battle or POST /api/game/battle"],
            actual_api=[],
            api_correct=False,
            input={"reason": "当前战斗只有 app.systems.military.resolve_battle 系统函数，没有公开 HTTP API。"},
            output={"gap": "battle has no public API endpoint; existing tests cover direct backend function only"},
            checks={"passed": False, "needs_backend_api": True},
        )
        steps.append(gap)
    finally:
        recorder.close()

    report = {
        "object": "lord_tail.live_trace_report",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "backend_url": backend_url,
        "hermes_url": hermes_url,
        "hermes_profile": "lord-tail-ollama-gemma4-31b",
        "summary": {
            "total_steps": len(steps),
            "passed_steps": sum(1 for step in steps if step.api_correct),
            "failed_steps": sum(1 for step in steps if not step.api_correct),
        },
        "steps": [step.__dict__ for step in steps],
    }
    return report


def write_report(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"alexander_live_trace_{stamp}.json"
    md_path = output_dir / f"alexander_live_trace_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Alexander Live Trace Report",
        "",
        f"- created_at: `{report['created_at']}`",
        f"- backend_url: `{report['backend_url']}`",
        f"- hermes_url: `{report['hermes_url']}`",
        f"- hermes_profile: `{report['hermes_profile']}`",
        f"- total_steps: `{report['summary']['total_steps']}`",
        f"- passed_steps: `{report['summary']['passed_steps']}`",
        f"- failed_steps: `{report['summary']['failed_steps']}`",
        "",
        "| Step | API Correct | Expected API | Actual API | Checks |",
        "|---|---:|---|---|---|",
    ]
    for step in report["steps"]:
        checks = step.get("checks", {})
        check_text = json.dumps(checks, ensure_ascii=False)
        if len(check_text) > 360:
            check_text = check_text[:357] + "..."
        lines.append(
            f"| `{step['name']}` | `{step['api_correct']}` | "
            f"`{', '.join(step['expected_api'])}` | `{', '.join(step['actual_api'])}` | "
            f"`{check_text}` |"
        )
    lines.extend([
        "",
        "Full request/response bodies are stored in the sibling JSON file.",
    ])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live Lord Tail + Hermes trace and save all inputs/outputs.")
    parser.add_argument("--backend-url", default=os.getenv("LORD_TAIL_BACKEND_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--hermes-url", default=os.getenv("HERMES_RUNS_BASE_URL", "http://127.0.0.1:8643"))
    parser.add_argument("--hermes-key", default=os.getenv("HERMES_RUNS_API_KEY", "lord-tail-local-test"))
    parser.add_argument("--output-dir", default=str(REPO_ROOT / ".reports" / "live_trace"))
    args = parser.parse_args()

    os.environ["HERMES_RUNS_BASE_URL"] = args.hermes_url
    os.environ["HERMES_RUNS_API_KEY"] = args.hermes_key
    os.environ["HERMES_AGENT_PROFILE"] = "lord-tail-ollama-gemma4-31b"

    report = run_trace(args.backend_url, args.hermes_url, args.hermes_key)
    json_path, md_path = write_report(report, Path(args.output_dir))
    print(json.dumps({
        "summary": report["summary"],
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
