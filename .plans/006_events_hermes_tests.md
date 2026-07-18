# Plan 006: Events, Hermes Integration, and Tests

## 目标

落地 `events` 模块，把 economy / construction / military / diplomacy 的结果统一成结构化事件，再由 narrative 层和 Hermes 使用。

同时收敛 Hermes 接入方式：Hermes 不再直接修改任意 `state_patch` 作为主路径，而是优先调用统一 `/api/state/*` 或返回结构化 action。

## 输入

- `/Users/ray/raylab/lord-tail/backend/app/engine/types.py`
- `/Users/ray/raylab/lord-tail/backend/app/engine/turn.py`
- `/Users/ray/raylab/lord-tail/backend/app/integrations/hermes.py`
- `/Users/ray/raylab/lord-tail/backend/app/api/state.py`
- `/Users/ray/raylab/lord-tail/README.md`

如果 Plan 001、002、003、004、005 尚未执行，先执行它们。

## 输出文件

```text
/Users/ray/raylab/lord-tail/backend/app/systems/events.py
/Users/ray/raylab/lord-tail/backend/app/engine/narrative.py
/Users/ray/raylab/lord-tail/backend/tests/test_turn_pipeline.py
/Users/ray/raylab/lord-tail/backend/tests/test_state_api.py
/Users/ray/raylab/lord-tail/backend/tests/test_military_diplomacy.py
```

如果项目当前没有 pytest 结构，可以先使用 `backend/tests/` 新增 pytest，并把依赖写入 `backend/requirements.txt`。

## 事件 schema

统一 `TurnEvent` 字段：

```json
{
  "phase": "economy",
  "kind": "resource_changed",
  "message": "农田产出粮食 30。",
  "severity": "info",
  "data": {
    "resource": "food",
    "amount": 30
  }
}
```

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `phase` | string | `action` / `construction` / `economy` / `military` / `diplomacy` / `events` |
| `kind` | string | 机器可读事件类型 |
| `message` | string | 后端短文本，可给 UI/Hermes 使用 |
| `severity` | string | `info` / `warning` / `critical` |
| `data` | object | 结构化载荷 |

## events MVP

`systems/events.py` 实现：

- `run_random_events(state, context)`
- `apply_event_effect(state, event, context)`
- `check_threshold_events(state, context)`

MVP 事件：

- 粮食为 0：民心下降。
- 金币为 0：军队维持风险。
- 民心低于 25：叛乱风险事件。
- 外交关系低于 -60：战争警告事件。
- 建筑完工：生成正面事件。

事件触发先保持确定性阈值，随机事件可以留一个 `random.Random(seed)` 入口，但不要让测试不可重复。

## narrative MVP

`engine/narrative.py` 实现：

- `events_to_report(events: list[TurnEvent]) -> str`
- `suggest_next_actions(state, events) -> list[str]`

要求：

- 本地 narrative 从结构化事件生成。
- 不要在每个系统模块里拼长段叙事。
- Hermes 仍可返回自己的 narrative，但状态变更走统一接口或结构化 action。

## Hermes 接口收敛

Hermes 调用建议支持两种返回：

### 1. 叙事-only

```json
{
  "narrative": "本轮叙事",
  "suggestions": ["..."]
}
```

### 2. 结构化 actions

```json
{
  "narrative": "本轮叙事",
  "actions": [
    {
      "type": "resources",
      "payload": {
        "changes": {
          "gold": 10
        }
      }
    },
    {
      "type": "diplomacy",
      "payload": {
        "faction": "金鳞",
        "status": "友善"
      }
    }
  ]
}
```

`state_patch` 保留兼容，但 README 明确标为 legacy。

## 步骤

1. 扩展 `TurnEvent`，加入 `severity`。
2. 新增 `systems/events.py`，实现阈值事件。
3. 在 pipeline 的 `run_events` 阶段调用 `events.run_random_events` 和 `events.check_threshold_events`。
4. 新增 `engine/narrative.py`，把 pipeline 返回 narrative 的逻辑集中到这里。
5. 修改 Hermes 适配：
   - Hermes response 如果有 `actions`，逐条调用内部 mutation helper。
   - `state_patch` 仍可用，但注释和 README 标记 legacy。
6. 给 `/api/game/turn` response 增加可选字段 `events`。
   - 如果担心前端类型，先保持前端忽略额外字段即可。
   - TypeScript 类型可以补 `events?: TurnEvent[]`。
7. 新增 pytest：
   - `test_state_api.py` 覆盖 `/api/state/*`。
   - `test_turn_pipeline.py` 覆盖建造、经济、事件顺序。
   - `test_military_diplomacy.py` 覆盖训练、维持费、外交对象格式。
8. 更新 README，写明：
   - `/api/state/*` 是统一状态修改接口。
   - Hermes action type 与 payload 映射。
   - `state_patch` 是 legacy。

## 不要做的事

- 不要让 Hermes 返回的自由文本直接决定状态。
- 不要把事件写成只有中文 message 的字符串数组；必须有机器可读 `kind` 和 `data`。
- 不要让随机事件导致测试不稳定。
- 不要删除 legacy `state_patch`，除非已有迁移确认。

## 验证命令

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
client.post("/api/game/start", json={
    "lord_name": "Ray",
    "lord_gender": "未说明",
    "realm_name": "北境",
    "appearance": "",
    "personality": "",
    "talents": [{"id": "harvest_hand"}, {"id": "charismatic_lord"}],
})

client.post("/api/state/resources", json={"values": {"food": 0}})
turn = client.post("/api/game/turn", json={"command": "巡视粮仓"})
assert turn.status_code == 200, turn.text
data = turn.json()
assert "events" in data
assert any(event["kind"] for event in data["events"])
assert data["state"]["resources"]["food"] >= 0

print("OK")
PY
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
cd frontend && npm run build
```

如果 pytest 已建立，额外运行：

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests
```

## 完成判定

- `/api/game/turn` 的本地规则路径由事件驱动生成报告。
- economy / construction / military / diplomacy 都只追加结构化事件，不直接拼长叙事。
- Hermes 支持结构化 `actions`。
- README 写清楚统一状态接口和 legacy `state_patch`。
- 验证命令输出 `OK`。
