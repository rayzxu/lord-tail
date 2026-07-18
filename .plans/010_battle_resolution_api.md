# Plan 010: Battle Resolution API

## 目标

补齐公开的战斗结算 API，让 Hermes agent 和前端不再只能记录 `battle_api_gap`，而是可以通过后端真实结算战斗。

当前状态：

- `backend/app/systems/military.py` 已有内部 `resolve_battle(state, battle_request, context)`。
- 兵种 `combat.power / defense / range / speed / counters` 已由 catalog 管理。
- 组织度、伤亡、溃逃已经有内部规则。
- 但没有公开 API，所以 Hermes 战斗 skill 只能调用 `/api/agent/events` 记录缺口。

本 plan 的核心是把内部战斗结算暴露为受控状态 mutation API，并让 Hermes battle skills 改为调用该 API。

## 输入

- `/Users/ray/raylab/lord-tail/backend/app/systems/military.py`
- `/Users/ray/raylab/lord-tail/backend/app/api/state.py`
- `/Users/ray/raylab/lord-tail/backend/app/api/schemas.py`
- `/Users/ray/raylab/lord-tail/backend/app/engine/types.py`
- `/Users/ray/raylab/lord-tail/backend/app/engine/hermes_context.py`
- `/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-battle-archers/SKILL.md`
- `/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-battle-infantry/SKILL.md`
- `/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-battle-cavalry/SKILL.md`
- `/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-game/references/api_contract.md`
- `/Users/ray/raylab/lord-tail/frontend/src/api.ts`

## 输出文件

主要修改：

```text
/Users/ray/raylab/lord-tail/backend/app/api/schemas.py
/Users/ray/raylab/lord-tail/backend/app/api/state.py
/Users/ray/raylab/lord-tail/backend/app/systems/military.py
/Users/ray/raylab/lord-tail/backend/app/engine/hermes_context.py
/Users/ray/raylab/lord-tail/backend/tests/test_battle_resolution_api.py
/Users/ray/raylab/lord-tail/frontend/src/api.ts
/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-battle-archers/SKILL.md
/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-battle-infantry/SKILL.md
/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-battle-cavalry/SKILL.md
/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-game/references/api_contract.md
```

可选新增：

```text
/Users/ray/raylab/lord-tail/backend/app/api/battles.py
```

如果新增 `api/battles.py`，需要在 `backend/app/main.py` include router。若只在 `api/state.py` 中添加 endpoint，不需要新增 router。

## API 设计

新增统一状态 mutation API：

```http
POST /api/state/battles/resolve
POST /api/hermes/battles/resolve
```

说明：

- `/api/state/battles/resolve` 是正式统一接口。
- `/api/hermes/battles/resolve` 是 Hermes 兼容别名，内部必须走同一套 handler。
- 这是状态变更接口，不是纯模拟接口；默认会修改 `state.army`、`state.army_status`、`state.battles`，并返回结构化事件。

### Request schema

在 `backend/app/api/schemas.py` 增加：

```python
class BattleResolveRequest(BaseModel):
    player: dict[str, int] | None = None
    enemy: dict[str, int] = Field(min_length=1)
    enemy_organization: int = Field(default=100, ge=0, le=100)
    terrain: str = Field(default="grass", max_length=40)
    stance: str = Field(default="balanced", pattern="^(cautious|balanced|aggressive)$")
    apply_to_state: bool = True
    source: str = Field(default="api", max_length=40)
    label: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=1000)
```

字段规则：

| 字段 | 说明 |
|---|---|
| `player` | 可选。缺省时使用 `state.army` 全军参战；传入时表示抽调这些兵参战。 |
| `enemy` | 必填。敌方兵力，key 必须是 unit id。 |
| `enemy_organization` | 敌方组织度，默认 `100`。 |
| `terrain` | MVP 仅记录到结果；暂不做复杂地形修正。 |
| `stance` | 我方战斗姿态。MVP 影响伤亡比。 |
| `apply_to_state` | 默认 `true`。`true` 时修改当前 state；`false` 只做 dry-run，用于前端预览或测试。 |
| `source` | `api` / `hermes` / `debug` / `frontend` 等来源标记。 |
| `label` | 战斗标题，例如“骑兵冲击三名步兵”。 |
| `notes` | Hermes 或前端传入的战斗背景。 |

### Response schema

返回保持 `mutation_result` 风格，但必须额外包含 `battle_result`：

```json
{
  "state": {},
  "narrative": "战斗已经结算。",
  "suggestions": [],
  "events": [],
  "battle_result": {
    "id": "battle_1",
    "winner": "player",
    "terrain": "grass",
    "stance": "balanced",
    "player": {
      "before": {"cavalry": 1},
      "after": {"cavalry": 0},
      "casualties": 1,
      "casualties_by_unit": {"cavalry": 1},
      "organization_before": 100,
      "organization_after": 0,
      "routed": true
    },
    "enemy": {
      "before": {"infantry": 3},
      "after": {"infantry": 1},
      "casualties": 2,
      "casualties_by_unit": {"infantry": 2},
      "organization": 100
    },
    "modifiers": {
      "player_range_multiplier": 1.0,
      "enemy_range_multiplier": 1.0,
      "player_average_range": 1.0,
      "enemy_average_range": 1.0,
      "player_average_speed": 2.0,
      "enemy_average_speed": 1.0,
      "speed_casualty_modifier": 1.05,
      "initiative": "player",
      "counter_breakdown": []
    },
    "scores": {
      "player_attack": 0.0,
      "player_defense": 0.0,
      "enemy_attack": 0.0,
      "enemy_defense": 0.0,
      "player_score": 0.0,
      "enemy_score": 0.0
    }
  }
}
```

具体数字由实现计算，不要照抄示例。

## military.py 需要补强的内部能力

当前 `resolve_battle()` 已可用，但 result 太粗，无法支撑前端和 Hermes 描述。需要补强为 API 级结果。

### 新增/调整函数

```python
def validate_force(force: dict[str, int], *, field: str) -> dict[str, int]:
    ...

def select_player_force(state: dict[str, Any], requested: dict[str, int] | None) -> dict[str, int]:
    ...

def resolve_battle(state: dict[str, Any], battle_request: dict[str, Any], context: TurnContext) -> dict[str, Any]:
    ...
```

要求：

- `validate_force`：
  - unit id 必须存在于 `UNITS`。
  - 数量必须是正整数。
  - 空 force 报错。
- `select_player_force`：
  - `player is None` 时使用当前 `state.army` 中所有 `count > 0` 的部队。
  - `player` 非空时，不能超过 `state.army` 中可用数量。
  - 错误必须返回 422，而不是静默改小数量。
- `resolve_battle`：
  - 支持 `apply_to_state=false` dry-run。
  - 支持只抽调部分我方部队参战，而不是永远全军参战。
  - result 必须包含 before/after、casualties_by_unit、scores、modifiers、organization before/after、routed。
  - `state.battles` 中记录完整 battle_result。

### 姿态规则

`stance` 先做 MVP：

| stance | 我方攻击 | 我方防御 | 我方伤亡 | 敌方伤亡 |
|---|---:|---:|---:|---:|
| `cautious` | `0.90` | `1.10` | `0.90` | `0.90` |
| `balanced` | `1.00` | `1.00` | `1.00` | `1.00` |
| `aggressive` | `1.15` | `0.90` | `1.15` | `1.10` |

这些数值可以先放在 `military.py` 常量中，但要有 TODO：后续迁移到 catalog/rules json。不要散落硬编码在多处。

### casualties_by_unit

当前 `_apply_casualties()` 只返回 remaining。需要改为返回：

```python
{
  "remaining": {"infantry": 7},
  "casualties_by_unit": {"infantry": 3}
}
```

或者新增 `_distribute_casualties()`，避免破坏现有测试。

### battle id

新增：

```python
state["battle_seq"] = state.get("battle_seq", 0) + 1
battle_id = f"battle_{state['battle_seq']}"
```

旧存档缺少 `battle_seq` 时自动补。

## API handler 行为

在 `state.py` 或 `battles.py` 中添加：

```python
@router.post("/state/battles/resolve")
@router.post("/hermes/battles/resolve")
def state_battle_resolve(request: BattleResolveRequest) -> dict[str, Any]:
    ...
```

要求：

1. `state = require_state()`。
2. 创建 `TurnContext(command=request.label or "battle_resolve", actor=request.source)`。
3. 调用 `military.resolve_battle(...)`。
4. 捕获 `ValueError` 并转为 `HTTPException(422, message)`。
5. 使用 `mutation_result(state, "战斗已经结算。", events=context.events)` 返回。
6. 在返回 body 顶层追加 `battle_result`。

注意：

- `apply_to_state=false` 时不能修改 `state.army`、`state.army_status`、`state.battles`。
- dry-run 可以返回 `battle_result` 和临时 events，但不能污染当前 state。
- `apply_to_state=true` 时必须写入 `state.battles`。

## Hermes skill 更新

三个 battle skills 必须从“记录缺口”改成“调用战斗结算 API”。

### `lord-tail-battle-cavalry`

将说明改为：

- 骑兵冲击、速度、克制、士气和溃败必须调用：

```bash
curl -s -X POST "$LORD_TAIL_API_BASE_URL/api/state/battles/resolve" \
  -H 'Content-Type: application/json' \
  -d '{"player":{"cavalry":1},"enemy":{"infantry":3},"enemy_organization":100,"terrain":"grass","stance":"aggressive","source":"hermes","label":"骑兵冲击三名步兵"}'
```

### `lord-tail-battle-archers`

示例：

```bash
curl -s -X POST "$LORD_TAIL_API_BASE_URL/api/state/battles/resolve" \
  -H 'Content-Type: application/json' \
  -d '{"player":{"archers":1},"enemy":{"infantry":3},"enemy_organization":100,"terrain":"grass","stance":"balanced","source":"hermes","label":"弓兵对三名步兵射击"}'
```

### `lord-tail-battle-infantry`

示例：

```bash
curl -s -X POST "$LORD_TAIL_API_BASE_URL/api/state/battles/resolve" \
  -H 'Content-Type: application/json' \
  -d '{"player":{"infantry":1},"enemy":{"infantry":3},"enemy_organization":100,"terrain":"grass","stance":"balanced","source":"hermes","label":"步兵对三名步兵近战"}'
```

Hermes 输出规则：

- 最终回答只能基于 API 返回的 `battle_result` 写故事。
- 不允许在 API 返回之外自行编造伤亡、克制倍率、溃逃结果。
- 如果 API 返回 422，必须向玩家说明无法结算的具体原因，并可调用 `/api/agent/events` 记录错误。

## Hermes context / API contract 更新

更新 `backend/app/engine/hermes_context.py`：

- `allowed_actions.scene_playbooks` 中 battle 场景从 `POST /api/agent/events only` 改为 `POST /api/state/battles/resolve`。
- `allowed_actions.api_contract` 或相关描述中加入 battle resolve endpoint。

更新：

```text
/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-game/references/api_contract.md
```

加入：

```text
POST /api/state/battles/resolve
Purpose: resolve a real battle and mutate army/army_status/battles.
Use for: archers, infantry, cavalry, counter, range, speed, morale, rout checks.
Do not use /api/agent/events for battle_api_gap once this endpoint exists.
```

## 前端契约

更新 `frontend/src/api.ts`：

```ts
export type BattleResolveRequest = {
  player?: Record<string, number>
  enemy: Record<string, number>
  enemy_organization?: number
  terrain?: string
  stance?: 'cautious' | 'balanced' | 'aggressive'
  apply_to_state?: boolean
  source?: string
  label?: string
  notes?: string
}

export type BattleResult = {
  id: string
  winner: 'player' | 'enemy'
  player: Record<string, unknown>
  enemy: Record<string, unknown>
  modifiers: Record<string, unknown>
  scores: Record<string, number>
}
```

并增加：

```ts
battles: {
  resolve: (request: BattleResolveRequest) =>
    request<TurnResult & { battle_result: BattleResult }>('/state/battles/resolve', {
      method: 'POST',
      body: JSON.stringify(request),
    })
}
```

本 plan 不要求前端做完整战斗 UI，但 API client 必须先补。

## 自动 approval 白名单

当前后端 approval 自动批准 Lord Tail 本地白名单 API。实现本 plan 时必须把新 endpoint 加入：

```python
SAFE_LORD_TAIL_APPROVAL_PATHS
```

新增：

```text
/api/state/battles/resolve
/api/hermes/battles/resolve
```

否则 Hermes 会再次被 approval 拦截。

## 测试

新增：

```text
/Users/ray/raylab/lord-tail/backend/tests/test_battle_resolution_api.py
```

### 测试 1：骑兵 vs 三步兵 API 正常结算

要求：

1. start game。
2. 通过 `/api/state/army` 设置 `cavalry = 1`。
3. 调用：

```json
{
  "player": {"cavalry": 1},
  "enemy": {"infantry": 3},
  "stance": "aggressive",
  "source": "test",
  "label": "骑兵冲击三名步兵"
}
```

断言：

- status 200。
- response 顶层有 `battle_result`。
- `battle_result.modifiers.player_average_speed > battle_result.modifiers.enemy_average_speed`。
- `battle_result.player.before.cavalry == 1`。
- `battle_result.enemy.before.infantry == 3`。
- events 中有 `battle_resolved`。
- state.battles 最后一项 id 等于返回 id。

### 测试 2：兵力不足返回 422

调用 `player: {"cavalry": 2}`，但 state 只有 1 名骑兵。

断言：

- status 422。
- response detail 包含“兵力不足”或等价中文错误。
- state.army 没有被修改。

### 测试 3：dry-run 不污染 state

调用：

```json
{
  "player": {"archers": 1},
  "enemy": {"infantry": 3},
  "apply_to_state": false
}
```

断言：

- status 200。
- 返回 `battle_result`。
- state.army 不变。
- state.battles 长度不变。

### 测试 4：未知兵种返回 422

调用 `enemy: {"dragon": 1}`。

断言：

- status 422。
- 不产生 battles 记录。

### 测试 5：溃逃事件机器可读

构造低组织度：

```json
army_status.organization = 20
```

发起一场高损失战斗。

断言：

- 若 `loss_ratio >= 0.15`，`state.army_status.routed == true`。
- events 中有 `army_routed`。
- `battle_result.player.routed == true`。

### 测试 6：Hermes approval 白名单

在 `backend/tests/test_hermes_runs_backend.py` 或新测试中补：

- approval command 为 `curl -s -X POST http://127.0.0.1:8000/api/state/battles/resolve ...`
- 默认 `auto-safe-local` 应返回 `choice=once`。

## 真实 Hermes 复测

完成实现后，必须用真实 Hermes profile 复测原失败战争 case：

输入：

```text
用一队骑兵冲击三名步兵，判断速度、克制、伤害、士气打击和溃败。若没有战斗结算 API，不要捏造，只记录缺口。
```

新的期望：

- Hermes 不再调用 `POST /api/agent/events` 的 `battle_api_gap`。
- Hermes 必须调用 `POST /api/state/battles/resolve`。
- 后端 audit 必须记录：

```text
POST /api/state/battles/resolve
```

- final text 必须基于 `battle_result` 描述战斗。

报告保存到：

```text
/Users/ray/raylab/lord-tail/.reports/hermes_matrix/
```

建议命名：

```text
battle_cavalry_battle_api_<timestamp>.json
battle_cavalry_battle_api_<timestamp>.md
```

## 不要做的事

- 不要在 Hermes 最终输出 JSON。
- 不要让 Hermes 自行计算伤亡、克制倍率、士气或溃逃；必须以后端返回为准。
- 不要继续把 battle 场景作为 `battle_api_gap` 处理，除非 API 返回错误。
- 不要把新的战斗规则数值散落硬编码到多个文件。
- 不要在本 plan 做完整战术地图寻路、阵型、格子距离、多回合移动。
- 不要让 `apply_to_state=false` 修改真实 state。
- 不要允许 API 传入超过当前 state.army 的我方兵力并静默成功。

## 验证命令

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python -m pytest \
  backend/tests/test_battle_resolution_api.py \
  backend/tests/test_hermes_runs_backend.py -q

PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend

cd frontend
npm run build
```

API smoke test：

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
client.post("/api/game/start", json={
    "lord_name": "亚历山大",
    "lord_gender": "男",
    "realm_name": "黑逼堡",
    "appearance": "肥胖，矮小，龌蹉；小眼睛里全是贪婪",
    "personality": "媚上欺下",
    "talents": [{"id": "harvest_hand"}, {"id": "charismatic_lord"}],
})
client.post("/api/state/army", json={"unit": "cavalry", "value": 1})
response = client.post("/api/state/battles/resolve", json={
    "player": {"cavalry": 1},
    "enemy": {"infantry": 3},
    "stance": "aggressive",
    "source": "smoke",
    "label": "骑兵冲击三名步兵",
})
assert response.status_code == 200, response.text
body = response.json()
assert "battle_result" in body
assert body["battle_result"]["player"]["before"]["cavalry"] == 1
assert body["battle_result"]["enemy"]["before"]["infantry"] == 3
assert any(event["kind"] == "battle_resolved" for event in body["events"])
print("OK")
PY
```

## 完成判定

- 存在公开 API：`POST /api/state/battles/resolve`。
- Hermes 兼容别名存在：`POST /api/hermes/battles/resolve`。
- API 能真实修改 `state.army`、`state.army_status` 和 `state.battles`。
- API 支持 `apply_to_state=false` dry-run，且不会污染 state。
- API 返回完整 `battle_result`，包含：
  - before/after
  - casualties
  - casualties_by_unit
  - organization before/after
  - routed
  - range/speed/counter/initiative modifiers
  - attack/defense/scores
- Hermes battle skills 调用 `POST /api/state/battles/resolve`。
- `battle_api_gap` 不再是 battle skills 的默认路径。
- approval 白名单包含新 battle endpoint。
- 后端 pytest、compileall、前端 build 通过。
- 真实 Hermes 战争 case 报告显示：
  - expected API: `POST /api/state/battles/resolve`
  - actual API: `POST /api/state/battles/resolve`
  - missing APIs: none
  - unexpected APIs: none
