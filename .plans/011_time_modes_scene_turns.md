# Plan 011: 时间系统与双推进模式

## 目标

把当前单一 `story_turn / describe_*` 分流，升级为明确的双推进模式：

1. **战略回合模式**：一个战略 turn = 9 天，执行完整领地结算 pipeline。
2. **场景故事模式**：领主与 NPC、商队、外交会谈、战斗等多轮交互默认不推进战略 turn；只有用户或 Hermes 明确推进时间时，才累计场景内时间，并在累计达到 9 天时触发战略结算。

完成后，前端、后端、Hermes agent 对“时间是否流动”和“是否结算领地”有统一语义，不再把所有故事输入都混成一个 turn。

## 当前问题

当前实现中：

- 前端主输入框调用 `/api/agent/runs`，mode 固定为 `story_turn`。
- `story_turn` 允许 Hermes 调用 `/api/state/*` mutation，但不会自动推进 `state["turn"]`。
- `/api/game/turn` 是旧兼容接口，每调用一次本地 pipeline 并 `turn += 1`。
- `describe_*` 是只读描述模式，不推进时间。
- 没有字段说明 `turn` 代表几天。
- 没有 `calendar_day`、`active_scene`、`scene_time_elapsed` 等状态。
- Hermes instructions 没有明确区分：
  - 战略命令：执行 9 天结算。
  - 场景命令：局部叙事与交互，不默认结算。

## 目标行为

### 战略回合模式

适用于玩家明确做 9 天尺度的领地经营命令，例如：

- “接下来安排春耕，推进一轮”
- “本旬重点修建农田”
- “让领地按当前安排运转 9 天”
- “结束本轮”

行为：

1. 执行玩家战略命令。
2. 调用统一 turn pipeline：
   `start_turn -> income -> player_action -> construction -> military -> diplomacy -> demographics -> weather -> expenditure -> events -> end_turn`
3. 推进 `calendar_day += 9`。
4. 推进 `turn += 1`。
5. 根据天数更新季节、天气。
6. 输出本轮报告。

### 场景故事模式

适用于局部连续事件，例如：

- 领主与管家/NPC 对话。
- 接见商队。
- 宴会、审判、领主私人事件。
- 外交谈判。
- 战争中的多轮战术命令。

行为：

1. 默认不执行战略结算。
2. 默认不推进 `turn`。
3. 可以调用 `/api/state/*` 修改局部状态，例如资源、民心、外交、部队、战斗结果。
4. 如果用户 prompt 明确时间流动：
   - “早上 / 中午 / 傍晚 / 晚上”：推进场景内小时。
   - “第二天 / 两天后 / 三日后”：推进场景内天数。
   - “等到雨停 / 围城数日”：由 Hermes 判断合理时间，但必须调用时间 API。
5. 场景内累计时间达到 9 天时，触发一次战略结算。
6. 当前事件完成后，调用 scene end，回到战略模式。

### 描述模式

`describe_realm / describe_lord / describe_tile / describe_item` 继续只读：

- 不修改状态。
- 不推进时间。
- 不打开或结束场景。

## 新状态字段

在 `backend/app/engine/state.py` 的 `make_state()` 中增加：

```json
{
  "time": {
    "calendar_day": 1,
    "turn_days": 9,
    "day_in_turn": 1,
    "time_of_day": "morning",
    "season": "春季",
    "weather": "细雨"
  },
  "game_mode": "strategic",
  "active_scene": null,
  "scene_seq": 0
}
```

兼容要求：

- 保留顶层 `turn`、`season`、`weather`，避免前端大改。
- 顶层 `season/weather` 从 `state["time"]` 同步。
- 旧存档没有 `time/game_mode/active_scene` 时，读取时自动 normalize。

### `active_scene` schema

```json
{
  "id": "scene_1",
  "type": "dialogue|caravan|diplomacy|battle|court|lord_event|daily",
  "title": "接见南方商队",
  "status": "active",
  "started_turn": 1,
  "started_calendar_day": 1,
  "elapsed_hours": 0,
  "elapsed_days": 0,
  "time_locked": true,
  "participants": [
    {
      "id": "lord",
      "name": "亚历山大",
      "role": "lord"
    }
  ],
  "flags": {},
  "summary": "",
  "recent_messages": []
}
```

## 后端模块拆分

新增模块：

```text
backend/app/engine/time.py
backend/app/engine/scenes.py
```

### `time.py`

职责：

- normalize time state。
- 将旧顶层 `season/weather` 同步到 `state["time"]`。
- 推进小时/天数。
- 判断是否达到战略 turn 结算阈值。
- 将 `calendar_day` 转为季节。

建议函数：

```python
def normalize_time(state: dict[str, Any]) -> None
def sync_legacy_time_fields(state: dict[str, Any]) -> None
def advance_scene_time(state: dict[str, Any], *, hours: int = 0, days: int = 0, reason: str = "") -> list[TurnEvent]
def consume_due_strategic_turns(state: dict[str, Any], context: TurnContext) -> int
def current_time_summary(state: dict[str, Any]) -> dict[str, Any]
```

### `scenes.py`

职责：

- 创建/读取/结束 active scene。
- 记录场景消息。
- 控制 `game_mode`。
- 限制同一时间只能有一个 active scene。

建议函数：

```python
def normalize_scene_state(state: dict[str, Any]) -> None
def start_scene(state: dict[str, Any], scene_type: str, title: str, participants: list[dict[str, Any]] | None = None) -> dict[str, Any]
def append_scene_message(state: dict[str, Any], role: str, content: str, metadata: dict[str, Any] | None = None) -> None
def end_scene(state: dict[str, Any], summary: str = "", outcome: dict[str, Any] | None = None) -> dict[str, Any]
def require_active_scene(state: dict[str, Any]) -> dict[str, Any]
```

## API 设计

新增公开 API。前端和 Hermes 统一使用这些接口。

### 读时间状态

```http
GET /api/time
```

返回：

```json
{
  "turn": 1,
  "time": {},
  "game_mode": "strategic",
  "active_scene": null
}
```

### 战略回合推进

```http
POST /api/game/strategic-turn
```

Payload：

```json
{
  "command": "接下来九天安排春耕并继续修建农田",
  "source": "player|hermes|system"
}
```

行为：

- 执行完整 pipeline。
- 推进 9 天。
- `turn += 1`。
- 如果有 active_scene，默认拒绝，除非 payload 明确 `force_end_scene: true`。

### 开始场景

```http
POST /api/game/scenes
```

Payload：

```json
{
  "type": "caravan",
  "title": "接见南方商队",
  "participants": [],
  "flags": {}
}
```

行为：

- 设置 `game_mode = "scene"`。
- 创建 `active_scene`。
- 不推进时间。

### 场景内推进

```http
POST /api/game/scenes/current/step
```

Payload：

```json
{
  "input": "我命令卫兵把商队头领带到火盆前问话",
  "narrative": "可选，Hermes 最终描述",
  "events": []
}
```

行为：

- 记录场景消息和事件。
- 不推进战略 turn。
- 不自动结算。

### 场景内时间推进

```http
POST /api/game/scenes/current/advance-time
```

Payload：

```json
{
  "hours": 0,
  "days": 2,
  "reason": "玩家说两天后再审问俘虏",
  "run_due_strategic_turns": true
}
```

行为：

- 更新 active scene 的 `elapsed_hours / elapsed_days`。
- 更新 `state["time"]["calendar_day"]` 和 `day_in_turn`。
- 如果累计跨过 9 天，并且 `run_due_strategic_turns = true`，执行相应次数的战略结算。

### 结束场景

```http
POST /api/game/scenes/current/end
```

Payload：

```json
{
  "summary": "商队接受重税，留下少量货物后离开。",
  "outcome": {}
}
```

行为：

- 归档 scene 到 `recent_events`。
- `active_scene = null`。
- `game_mode = "strategic"`。
- 不自动推进战略 turn，除非场景内时间累计触发。

## Hermes mode 调整

当前：

```ts
type AgentRunMode =
  | 'story_turn'
  | 'describe_realm'
  | 'describe_lord'
  | 'describe_tile'
  | 'describe_item'
```

改为：

```ts
type AgentRunMode =
  | 'strategic_turn'
  | 'scene_step'
  | 'story_turn'        // 兼容别名，后端按上下文路由
  | 'describe_realm'
  | 'describe_lord'
  | 'describe_tile'
  | 'describe_item'
```

后端兼容规则：

- `story_turn` 如果 `state["game_mode"] == "scene"`，按 `scene_step` 处理。
- `story_turn` 如果 `state["game_mode"] == "strategic"`，默认按 `scene_step` 还是 `strategic_turn` 需要前端显式传 `client_context.intent`。
- 前端最终应该显式传：
  - “推进 9 天 / 结束本轮”按钮：`strategic_turn`
  - 普通对话/战斗/互动输入：`scene_step`

## Hermes instructions 更新

修改 `backend/app/engine/hermes_context.py`：

### strategic_turn instructions

必须写入：

- 本模式代表 9 天。
- Hermes 可以在战略命令中调用 `/api/state/*`，但战略结算由后端 `/api/game/strategic-turn` 或 pipeline 完成。
- 最终输出本轮报告，不输出 JSON。

### scene_step instructions

必须写入：

- 本模式默认不推进战略 turn。
- 若需要状态改变，调用 `/api/state/*`。
- 若用户明确提到时间经过，必须调用 `/api/game/scenes/current/advance-time`。
- 若事件结束，必须调用 `/api/game/scenes/current/end`。
- 若还在事件中，不得结束 scene。
- 战斗场景应使用 `/api/state/battles/resolve` 处理关键攻击/伤害/组织度/溃败。

### description instructions

保留：

- 只读。
- 不调用 mutation。
- 不推进时间。

## Hermes skill 更新

在 profile skills 中新增或更新：

```text
lord-tail-time
lord-tail-scene
lord-tail-strategic-turn
lord-tail-scene-dialogue
lord-tail-scene-diplomacy
lord-tail-scene-battle
```

每个 skill 必须列清楚可用 API：

### lord-tail-time

- `GET /api/time`
- `POST /api/game/scenes/current/advance-time`
- 时间表达解析规则：
  - “早上/上午” -> hours 0 或设置 time_of_day。
  - “中午” -> hours 4。
  - “晚上/夜里” -> hours 8~12。
  - “第二天” -> days 1。
  - “两天后” -> days 2。
  - “九天后/一旬后” -> days 9，可能触发战略结算。

### lord-tail-scene

- `POST /api/game/scenes`
- `POST /api/game/scenes/current/step`
- `POST /api/game/scenes/current/end`
- `POST /api/agent/events`

### lord-tail-strategic-turn

- `POST /api/game/strategic-turn`
- `GET /api/state`
- `POST /api/agent/events`

### lord-tail-scene-battle

- `POST /api/state/battles/resolve`
- `POST /api/game/scenes/current/step`
- `POST /api/game/scenes/current/advance-time`
- `POST /api/game/scenes/current/end`

## 前端调整

### 顶部状态栏

显示：

- `第 N 轮`
- `第 X 日`
- `本轮第 Y/9 日`
- `春季`
- `细雨`
- 当前模式：
  - `战略`
  - `场景：接见南方商队`

### 输入区

增加模式感知：

- 如果 `game_mode == strategic`：
  - 主输入框默认是“故事/场景互动”还是“战略命令”需要 UI 区分。
  - 增加按钮：`推进九天`
  - 增加按钮：`开始场景`
- 如果 `game_mode == scene`：
  - 主输入框发送 `scene_step`。
  - 显示 `结束场景` 按钮。
  - 显示场景已过时间。

### API 类型

修改 `frontend/src/api.ts`：

- `AgentRunMode` 增加 `strategic_turn`、`scene_step`。
- 增加 `api.time.read()`。
- 增加 `api.game.strategicTurn()`。
- 增加 `api.scenes.start/step/advanceTime/end()`。

## 后端测试

新增：

```text
backend/tests/test_time_modes.py
backend/tests/test_scene_api.py
backend/tests/test_hermes_time_context.py
```

必须覆盖：

1. 初始状态：
   - `turn == 1`
   - `time.calendar_day == 1`
   - `time.turn_days == 9`
   - `game_mode == "strategic"`
   - `active_scene is None`

2. strategic turn：
   - 调用 `/api/game/strategic-turn`
   - `turn += 1`
   - `calendar_day += 9`
   - 建筑/训练/人口/经济 pipeline 正常执行

3. scene start：
   - 调用 `/api/game/scenes`
   - `game_mode == "scene"`
   - `active_scene.status == "active"`
   - `turn` 不变

4. scene step：
   - 调用 `/api/game/scenes/current/step`
   - `turn` 不变
   - `calendar_day` 不变
   - scene recent messages 增加

5. scene advance 2 days：
   - `turn` 不变
   - `calendar_day += 2`
   - active_scene elapsed_days += 2

6. scene advance 9 days：
   - 如果 `run_due_strategic_turns=true`
   - `turn += 1`
   - pipeline 被执行

7. scene end：
   - `active_scene is None`
   - `game_mode == "strategic"`
   - recent_events 有 scene summary

8. describe mode：
   - 不允许调用 mutation。
   - 不推进时间。

9. Hermes context：
   - `strategic_turn` instructions 明确 9 天。
   - `scene_step` instructions 明确默认不推进战略 turn。
   - `scene_step` instructions 包含 advance-time/end API。

## Hermes 全量测试场景

扩展 `tools/run_hermes_scenario_matrix.py`：

### 新增 case

1. `scene_dialogue_no_time_advance`
   - 输入：`我让管家进来，询问粮仓亏空是谁造成的。`
   - 期望：
     - 不调用 `/api/game/strategic-turn`
     - 不调用 `/api/game/scenes/current/advance-time`
     - 可调用 `/api/game/scenes/current/step`
     - `turn` 不变

2. `scene_dialogue_next_day`
   - 输入：`第二天早上，我再次召见管家。`
   - 期望：
     - 调用 `/api/game/scenes/current/advance-time`
     - payload days = 1
     - `turn` 不变，除非累计达到 9 天

3. `scene_battle_multi_round`
   - 输入三轮：
     - `弓箭手先射击。`
     - `步兵顶上去。`
     - `骑兵从侧翼冲锋。`
   - 期望：
     - 多次 `scene_step`
     - 至少一次 `/api/state/battles/resolve`
     - 默认不调用 `/api/game/strategic-turn`

4. `strategic_advance_9_days`
   - 输入：`结束本轮，让领地按当前安排运转九天。`
   - 期望：
     - 调用或触发 `/api/game/strategic-turn`
     - `turn += 1`
     - `calendar_day += 9`

5. `scene_ends_back_to_strategic`
   - 输入：`这场审问结束了，把结果记入书记官卷宗。`
   - 期望：
     - 调用 `/api/game/scenes/current/end`
     - `game_mode == strategic`

## 兼容策略

- 保留 `/api/game/turn`，但标记为 legacy。
- `/api/game/turn` 内部可以直接调用新的 `strategic_turn` pipeline。
- 保留 `story_turn` mode，避免前端旧代码或测试直接失效。
- 新前端逐步切换到 `strategic_turn` / `scene_step`。
- 旧存档读取时自动 normalize：
  - 无 `time` 则补默认。
  - 无 `game_mode` 则设为 `strategic`。
  - 无 `active_scene` 则设为 `None`。

## 实施步骤

1. 新增 `engine/time.py` 和 `engine/scenes.py`。
2. 修改 `engine/state.py`：
   - `make_state()` 加新字段。
   - `require_state/load_current_state/set_current_state` 前后调用 normalize。
3. 修改 `engine/turn.py`：
   - 将 `run_end_turn` 从单纯 `turn += 1` 改成通过 time 模块推进 9 天。
   - 暴露 `run_strategic_turn(state, command)`。
4. 新增/修改 FastAPI schemas。
5. 新增 `/api/time`。
6. 新增 `/api/game/strategic-turn`。
7. 新增 scene API。
8. 修改 `hermes_context.py`：
   - 支持 `strategic_turn` 和 `scene_step`。
   - context 中加入 `time`、`game_mode`、`active_scene`。
9. 修改 `api/runs.py`：
   - AgentRunMode 增加新 mode。
   - approval whitelist 加入新的 scene/time API。
10. 更新 Hermes profile skills。
11. 修改前端类型和 UI。
12. 补测试。
13. 更新 Hermes scenario matrix。

## 验证命令

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/test_time_modes.py backend/tests/test_scene_api.py backend/tests/test_hermes_time_context.py -q
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
cd frontend && npm run build
```

Hermes live 验证：

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python tools/run_hermes_scenario_matrix.py \
  --backend-url http://127.0.0.1:8000 \
  --hermes-url http://127.0.0.1:8643 \
  --hermes-key lord-tail-local-test \
  --model deepseek-v4-flash \
  --case scene_dialogue_no_time_advance \
  --case scene_dialogue_next_day \
  --case scene_battle_multi_round \
  --case strategic_advance_9_days \
  --case scene_ends_back_to_strategic \
  --case-timeout-seconds 600
```

## 完成判定

- 后端状态明确包含 `time/game_mode/active_scene`。
- 一个战略 turn 固定代表 9 天。
- 场景 step 默认不推进 `turn`。
- 明确时间表达会通过 API 推进场景时间。
- 场景累计达到 9 天时可以触发战略结算。
- 描述模式仍然只读。
- Hermes instructions 和 skills 明确区分战略回合与场景故事。
- 前端能显示当前模式和时间。
- 测试和构建全部通过。
