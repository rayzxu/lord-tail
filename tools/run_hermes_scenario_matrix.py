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
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.catalog import TALENTS  # noqa: E402


SCENARIO_SETTINGS = {
    "lord_name": "亚历山大",
    "lord_gender": "男",
    "realm_name": "黑逼堡",
    "appearance": "肥胖，矮小，龌蹉；小眼睛里全是贪婪",
    "personality": "媚上欺下",
}

TRACEABLE_GAME_API_PREFIXES = (
    "GET /api/agent/context",
    "GET /api/agent/describe-context",
    "POST /api/agent/events",
    "GET /api/state",
    "GET /api/time",
    "POST /api/game/strategic-turn",
    "POST /api/game/scenes",
    "POST /api/game/scenes/current/step",
    "POST /api/game/scenes/current/advance-time",
    "POST /api/game/scenes/current/end",
    "POST /api/state/resources",
    "POST /api/state/population",
    "POST /api/state/morale",
    "POST /api/state/army",
    "POST /api/state/diplomacy",
    "POST /api/state/buildings",
    "POST /api/state/battles/resolve",
)


@dataclass
class MatrixCase:
    id: str
    category: str
    title: str
    prompt: str
    expected_apis: list[str]
    notes: str = ""
    run_mode: str = "story_turn"


@dataclass
class MatrixResult:
    id: str
    category: str
    title: str
    expected_apis: list[str]
    actual_apis: list[str] = field(default_factory=list)
    missing_apis: list[str] = field(default_factory=list)
    unexpected_apis: list[str] = field(default_factory=list)
    error_apis: list[dict[str, Any]] = field(default_factory=list)
    api_correct: bool = False
    input: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    duration_seconds: float = 0.0
    error: str | None = None
    run_completed: bool = False


class MatrixRunner:
    def __init__(self, backend_url: str, hermes_url: str, hermes_key: str, model: str):
        self.backend_url = backend_url.rstrip("/")
        self.hermes_url = hermes_url.rstrip("/")
        self.model = model
        self.client = httpx.Client(timeout=httpx.Timeout(420.0, connect=10.0))
        self.hermes_headers = {"Authorization": f"Bearer {hermes_key}"} if hermes_key else {}

    def close(self) -> None:
        self.client.close()

    def backend(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        return self.client.request(method, f"{self.backend_url}{path}", **kwargs)

    def hermes(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = dict(self.hermes_headers)
        headers.update(kwargs.pop("headers", {}) or {})
        return self.client.request(method, f"{self.hermes_url}{path}", headers=headers, **kwargs)

    def scenario_talents(self) -> list[dict[str, str]]:
        stable_pool = [
            talent_id
            for talent_id, talent in TALENTS.items()
            if "initial_resources" not in talent.get("effects", {})
        ]
        return [{"id": talent_id} for talent_id in random.Random(1707).sample(stable_pool, 2)]

    def initialize_game(self) -> dict[str, Any]:
        start = self.backend("POST", "/api/game/start", json={**SCENARIO_SETTINGS, "talents": self.scenario_talents()})
        start.raise_for_status()
        budget = self.backend("POST", "/api/state/resources", json={
            "values": {
                "gold": 10000,
                "food": 10000,
                "wood": 10000,
                "stone": 10000,
                "iron": 10000,
                "tools": 10000,
                "population": 1000,
                "morale": 60,
                "authority": 80,
                "security": 70,
            }
        })
        budget.raise_for_status()
        barracks = self.backend("POST", "/api/state/buildings", json={"building": "训练场", "action": "build", "count": 1})
        barracks.raise_for_status()
        army = []
        for unit in ("infantry", "archers", "cavalry"):
            response = self.backend("POST", "/api/state/army", json={"unit": unit, "value": 10})
            response.raise_for_status()
            army.append(response.json())
        return {"start": start.json(), "budget": budget.json(), "barracks": barracks.json(), "army": army}

    def clear_audit(self) -> None:
        self.backend("DELETE", "/api/debug/request-log").raise_for_status()

    def read_audit(self) -> list[dict[str, Any]]:
        response = self.backend("GET", "/api/debug/request-log")
        response.raise_for_status()
        return response.json()["events"]

    def stream_run(self, run_id: str, max_seconds: float) -> tuple[list[dict[str, Any]], bool]:
        events: list[dict[str, Any]] = []
        completed = False
        started = time.monotonic()
        seen = set()
        stream_timeout = httpx.Timeout(max_seconds + 90.0, connect=10.0, read=max_seconds, write=20.0, pool=10.0)
        try:
            with httpx.Client(timeout=stream_timeout, trust_env=False) as stream_client:
                with stream_client.stream("GET", f"{self.backend_url}/api/agent/runs/{run_id}/events") as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if time.monotonic() - started >= max_seconds:
                            break
                        if not line.startswith("data:"):
                            continue
                        event = json.loads(line.removeprefix("data:").strip())
                        event_key = json.dumps(event, ensure_ascii=False, sort_keys=True)
                        if event_key not in seen:
                            seen.add(event_key)
                            events.append(event)
                        if event.get("event") in {"run.completed", "run.failed", "run.cancelled"}:
                            completed = event.get("event") == "run.completed"
                            break
        except httpx.ReadTimeout:
            pass
        return events, completed

    def build_instructions(self, case: MatrixCase) -> str:
        expected = "\n".join(f"- {api}" for api in case.expected_apis)
        return (
            "你是 Lord Tail 的 Hermes Agent，必须使用 lord-tail-game skill 的行为规范。\n"
            "本次测试的目标不是让你输出 JSON，而是让你在执行故事时真实调用 Lord Tail 后端 API。\n"
            f"Lord Tail API Base URL: {self.backend_url}\n\n"
            "执行规则：\n"
            "1. 先调用 GET /api/agent/context 读取当前状态和 catalog。\n"
            "2. 只调用存在于 Lord Tail API contract 中的接口；不要发明不存在的 API。\n"
            "3. 如果场景需要的系统 API 不存在，例如 battle resolve 或 statue building 不在 catalog，调用 POST /api/agent/events 记录缺口，不要捏造状态。\n"
            "4. 若需要改资源、人口、民心、军队、外交、建筑，只能调用 /api/state/*。\n"
            "5. scene_step 默认不推进九天战略回合；只有明确时间经过时才调用 /api/game/scenes/current/advance-time。\n"
            "6. strategic_turn 代表九天战略回合，应调用 /api/game/strategic-turn。\n"
            "7. 最终回答只输出中文故事与简短建议，不要输出 JSON，不要输出 actions，不要输出 state_patch。\n\n"
            f"本 case 期望你调用的 API：\n{expected}\n"
        )

    def run_case(self, case: MatrixCase, case_timeout_seconds: float) -> MatrixResult:
        started = time.monotonic()
        result = MatrixResult(
            id=case.id,
            category=case.category,
            title=case.title,
            expected_apis=case.expected_apis,
            input={"prompt": case.prompt, "notes": case.notes},
            notes=case.notes,
        )
        try:
            self.clear_audit()
            hermes_session_id = f"lord-tail-matrix:{case.id}:{int(time.time())}"
            create_payload = {
                "mode": case.run_mode,
                "input": case.prompt,
                "client_context": {
                    "hermes_session_id": hermes_session_id,
                    "test_case": {
                        "id": case.id,
                        "title": case.title,
                        "expected_apis": case.expected_apis,
                        "notes": case.notes,
                    },
                },
            }
            created = self.backend("POST", "/api/agent/runs", json=create_payload)
            created.raise_for_status()
            created_body = created.json()
            local_run_id = created_body.get("run_id")
            if not local_run_id:
                raise RuntimeError(f"Hermes run response missing id: {created_body}")
            events, completed = self.stream_run(str(local_run_id), case_timeout_seconds)
            status = self.backend("GET", f"/api/agent/runs/{local_run_id}")
            status_body = status.json() if status.content else {}
            completed = completed or status_body.get("status") == "completed"
            if not completed:
                try:
                    self.backend("POST", f"/api/agent/runs/{local_run_id}/cancel")
                except Exception:
                    pass
            audit = self.read_audit()
            game_events = [
                event
                for event in audit
                if any(event["api"].startswith(prefix) for prefix in TRACEABLE_GAME_API_PREFIXES)
            ]
            actual_apis = [event["api"] for event in game_events]
            actual_api_set = set(actual_apis)
            expected_set = set(case.expected_apis)
            missing = [api for api in case.expected_apis if api not in actual_api_set]
            unexpected = [api for api in actual_apis if api not in expected_set]
            error_apis = [event for event in game_events if int(event.get("status_code", 0)) >= 400]
            result.actual_apis = actual_apis
            result.missing_apis = missing
            result.unexpected_apis = unexpected
            result.error_apis = error_apis
            result.output = {
                "hermes_create": created_body,
                "hermes_status": status_body,
                "hermes_events": events,
                "backend_audit": game_events,
                "final_text": status_body.get("final_text") or status_body.get("output") or "",
            }
            result.run_completed = completed
            if not completed:
                result.error = f"case timeout or run not completed within {case_timeout_seconds:g}s"
            result.api_correct = not missing and not unexpected and not error_apis
        except Exception as error:
            result.error = str(error)
            try:
                result.output["backend_audit"] = self.read_audit()
            except Exception:
                pass
        finally:
            result.duration_seconds = round(time.monotonic() - started, 3)
        return result


def scenario_cases() -> list[MatrixCase]:
    event = "POST /api/agent/events"
    scene_start = "POST /api/game/scenes"
    scene_step = "POST /api/game/scenes/current/step"
    scene_time = "POST /api/game/scenes/current/advance-time"
    scene_end = "POST /api/game/scenes/current/end"
    strategic = "POST /api/game/strategic-turn"
    return [
        MatrixCase("scene_dialogue_no_time_advance", "time_scene", "场景：对话不推进时间", "我让管家进来，询问粮仓亏空是谁造成的。", [scene_start, scene_step], "默认不应调用 advance-time 或 strategic-turn。", "scene_step"),
        MatrixCase("scene_dialogue_next_day", "time_scene", "场景：第二天推进场景时间", "第二天早上，我再次召见管家，让他交出粮仓账册。", [scene_start, scene_time, scene_step], "必须调用 advance-time，days 应为 1。", "scene_step"),
        MatrixCase("scene_battle_multi_round", "time_scene", "战斗场景：多轮不推进战略回合", "开始一场边境战斗：弓箭手先射击，步兵随后顶上，骑兵最后从侧翼冲锋。", [scene_start, "POST /api/state/battles/resolve", scene_step, event], "战斗结算必须使用 battle resolve。", "scene_step"),
        MatrixCase("strategic_advance_9_days", "time_scene", "战略：推进九天", "结束本轮，让领地按当前安排运转九天。", [strategic], "战略回合必须调用 strategic-turn。", "strategic_turn"),
        MatrixCase("scene_ends_back_to_strategic", "time_scene", "场景：结束回战略", "这场审问结束了，把结果记入书记官卷宗。", [scene_start, scene_end], "没有 active scene 时应先创建或记录一个审问场景，再结束。", "scene_step"),
        MatrixCase("daily_build_farm", "daily", "建造：开垦农田", "在 E4 建造一片农田，并描述劳工如何在细雨中被驱赶开垦。", ["POST /api/state/buildings", event]),
        MatrixCase("daily_population", "daily", "人口：流民/人口变化", "一批饥饿流民来到城门，请决定是否接纳，并实际调整人口与民心。", ["POST /api/state/population", "POST /api/state/morale", event]),
        MatrixCase("daily_economy", "daily", "经济：资源变化", "命令管家清点仓库并没收一批私藏粮食，请实际修改金币或粮食。", ["POST /api/state/resources", event]),
        MatrixCase("daily_talent", "daily", "角色天赋：利用既有天赋", "根据亚历山大的天赋安排一次相关行动，若影响状态请通过 API 执行。", [event]),
        MatrixCase("daily_weather_season", "daily", "天气季节", "细雨变重影响春季劳作。若没有天气/季节修改 API，请只记录事件。", [event], "当前没有公开 weather/season mutation API。"),
        MatrixCase("daily_food_shortage", "daily", "缺粮", "制造一次粮仓告急事件：将粮食降到极低并记录民怨。", ["POST /api/state/resources", "POST /api/state/morale", event]),
        MatrixCase("daily_plague", "daily", "瘟疫", "村舍中爆发瘟疫，请扣减人口与民心，并记录事件。", ["POST /api/state/population", "POST /api/state/morale", event]),
        MatrixCase("daily_fire", "daily", "火灾", "木棚区失火，烧毁部分木材并降低民心，记录火灾事件。", ["POST /api/state/resources", "POST /api/state/morale", event]),
        MatrixCase("daily_tax", "daily", "征税", "发布临时泥税，增加金币并降低民心，记录事件。", ["POST /api/state/resources", "POST /api/state/morale", event]),
        MatrixCase("daily_conscription", "daily", "征兵", "强征三名步兵入伍，并从人口中扣除相应人数，记录事件。", ["POST /api/state/army", "POST /api/state/population", event]),
        MatrixCase("daily_caravan", "daily", "商队", "南方商队抵达，带来金币和手工品，也改善一个外交对象的印象。", ["POST /api/state/resources", "POST /api/state/diplomacy", event]),
        MatrixCase("daily_statue", "daily", "建造雕像", "领主要求建造自己的雕像。若 catalog 没有雕像建筑，不要发明建筑，只记录缺口事件。", [event], "当前 catalog 没有 statue/sculpture 建筑。"),
        MatrixCase("diplomacy_positive", "diplomacy", "外交关系：正向", "向金鳞派出使者和礼物，改善外交关系。", ["POST /api/state/diplomacy", event]),
        MatrixCase("diplomacy_negative", "diplomacy", "外交关系：逆向", "羞辱血鸦使者，使外交关系恶化到战争或敌对。", ["POST /api/state/diplomacy", event]),
        MatrixCase("battle_archers_vs_infantry", "battle", "战斗：弓兵集群 vs 3 步兵", "用一队弓兵对阵三名步兵，判断射程、攻击、伤害、士气打击和是否溃败。若没有战斗结算 API，不要捏造，只记录缺口。", [event], "当前没有公开 battle resolve API。"),
        MatrixCase("battle_infantry_vs_infantry", "battle", "战斗：步兵集群 vs 3 步兵", "用一队步兵对阵三名步兵，判断攻击、防御、伤害、士气和溃败。若没有战斗结算 API，不要捏造，只记录缺口。", [event], "当前没有公开 battle resolve API。"),
        MatrixCase("battle_cavalry_vs_infantry", "battle", "战斗：骑兵集群 vs 3 步兵", "用一队骑兵冲击三名步兵，判断速度、克制、伤害、士气打击和溃败。若没有战斗结算 API，不要捏造，只记录缺口。", [event], "当前没有公开 battle resolve API。"),
    ]


def write_report(report: dict[str, Any], output_dir: Path, name: str | None = None) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = name or f"hermes_scenario_matrix_{stamp}"
    json_path = output_dir / f"{base_name}.json"
    md_path = output_dir / f"{base_name}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Hermes Scenario Matrix Report",
        "",
        f"- created_at: `{report['created_at']}`",
        f"- backend_url: `{report['backend_url']}`",
        f"- hermes_url: `{report['hermes_url']}`",
        f"- total_cases: `{report['summary']['total_cases']}`",
        f"- correct_cases: `{report['summary']['correct_cases']}`",
        f"- incorrect_cases: `{report['summary']['incorrect_cases']}`",
        "",
        "| Case | Category | API Correct | Run Completed | Missing APIs | Unexpected APIs | Error APIs |",
        "|---|---|---:|---:|---|---|---|",
    ]
    for item in report["cases"]:
        errors = [f"{event['api']}({event['status_code']})" for event in item["error_apis"]]
        lines.append(
            f"| `{item['id']}` {item['title']} | `{item['category']}` | `{item['api_correct']}` | "
            f"`{item.get('run_completed', False)}` | "
            f"`{', '.join(item['missing_apis']) or '-'}` | "
            f"`{', '.join(item['unexpected_apis']) or '-'}` | "
            f"`{', '.join(errors) or '-'}` |"
        )
    lines.append("\nFull prompts, Hermes events, backend audit logs, inputs and outputs are in the sibling JSON file.")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Lord Tail Hermes scenario API-call matrix.")
    parser.add_argument("--backend-url", default=os.getenv("LORD_TAIL_BACKEND_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--hermes-url", default=os.getenv("HERMES_RUNS_BASE_URL", "http://127.0.0.1:8643"))
    parser.add_argument("--hermes-key", default=os.getenv("HERMES_RUNS_API_KEY", "lord-tail-local-test"))
    parser.add_argument("--model", default=os.getenv("HERMES_RUNS_MODEL", "deepseek-v4-flash"))
    parser.add_argument("--case", action="append", help="Run only selected case id. Can be repeated.")
    parser.add_argument("--case-timeout-seconds", type=float, default=240.0)
    parser.add_argument("--output-dir", default=str(REPO_ROOT / ".reports" / "hermes_matrix"))
    args = parser.parse_args()

    runner = MatrixRunner(args.backend_url, args.hermes_url, args.hermes_key, args.model)
    try:
        init = runner.initialize_game()
        cases = scenario_cases()
        if args.case:
            selected = set(args.case)
            cases = [case for case in cases if case.id in selected]
        results: list[MatrixResult] = []
        output_dir = Path(args.output_dir)
        for case in cases:
            result = runner.run_case(case, args.case_timeout_seconds)
            results.append(result)
            partial_report = {
                "object": "lord_tail.hermes_scenario_matrix",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "backend_url": args.backend_url,
                "hermes_url": args.hermes_url,
                "initialization": init,
                "summary": {
                    "total_cases": len(results),
                    "planned_cases": len(cases),
                    "correct_cases": sum(1 for item in results if item.api_correct),
                    "incorrect_cases": sum(1 for item in results if not item.api_correct),
                },
                "cases": [item.__dict__ for item in results],
            }
            write_report(partial_report, output_dir, "hermes_scenario_matrix_live")
    finally:
        runner.close()

    report = {
        "object": "lord_tail.hermes_scenario_matrix",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "backend_url": args.backend_url,
        "hermes_url": args.hermes_url,
        "initialization": init,
        "summary": {
            "total_cases": len(results),
            "planned_cases": len(cases),
            "correct_cases": sum(1 for result in results if result.api_correct),
            "incorrect_cases": sum(1 for result in results if not result.api_correct),
        },
        "cases": [result.__dict__ for result in results],
    }
    json_path, md_path = write_report(report, Path(args.output_dir))
    print(json.dumps({
        "summary": report["summary"],
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
