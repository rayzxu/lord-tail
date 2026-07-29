# Plan 017: 长期事件与计划事件系统

## 目标

新增一个长期事件/计划事件系统，用于管理跨场景、跨多个战略回合、指定日期或条件触发的事件。

典型需求：

- 商队每个季节末到访领地。
- 商队因为被羞辱、抢劫、战争、瘟疫等原因，下次不会来，或改期到某个日期。
- 敌军将在几个回合后抵达。
- 某个外交使者三天后回信。
- 瘟疫、火灾、流民潮、叛乱等事件持续多个回合。
- 某个事件进入 active 状态后，需要玩家在场景模式中处理，处理完后再 resolve。

事件系统解决“未来将发生什么/正在持续什么”；历史系统解决“已经发生过什么并被记录下来”。

## 当前问题

当前 `systems/events.py` 更偏向当轮阈值事件和随机事件：

- 缺少可持久化的未来事件队列。
- 缺少准确日期/几回合后触发。
- 缺少 recurring 规则，例如每季末商队。
- 缺少 cancel/reschedule。
- 缺少 active/resolved 状态。
- Hermes 没有专门工具去安排、取消、改期长期事件。
- 前端没有事件面板展示“将来会发生/正在发生”的事。

## 非目标

本 plan 不实现：

- 大型任务调度器。
- 真实世界时间定时器。
- 后台异步任务。
- 复杂概率模拟。
- 全量剧情编辑器。

所有事件调度时间统一基于游戏内绝对时间 `GameTimePoint`。

“几回合后”等回合表达只能作为用户输入时的自然语言换算来源，不进入事件存储 schema。换算规则：

```text
1 战略回合 = state.time.turn_days 天，当前默认 9 天。
“三回合后” => current calendar_day + 3 * turn_days。
```

事件系统内部只比较：

```text
calendar_day + clock_24
```

这样可以避免“回合数”和“日期”同时存在导致到期判断冲突。

## 核心概念

### scheduled event

尚未到期的计划事件。

例：

```text
第 27 日 16:00，南方商队抵达黑逼堡。
```

### active event

已经触发，但尚未完成，需要玩家或系统处理。

例：

```text
南方商队已抵达城门外，正在等待接见。
```

### resolved event

已经处理完，保留结果摘要，可被历史系统记录。

例：

```text
商队被领主征收重税后离开，下季拒绝来访。
```

### cancelled / missed event

由于状态变化不再发生，或错过窗口。

例：

```text
商队因道路战乱取消本季行程。
```

## 状态 schema

在后端 state 中新增：

```json
{
  "scheduled_events": {
    "entries": [
      {
        "id": "evt_000001",
        "type": "caravan_arrival",
        "title": "南方商队到访",
        "description_md": "南方商队预计在春季末抵达黑逼堡。",
        "status": "scheduled",
        "visibility": "player",
        "importance": 3,
        "created_time": {
          "calendar_day": 1,
          "clock_24": "06:00",
          "season": "春季",
          "weather": "细雨"
        },
        "schedule": {
          "due_time": {
            "calendar_day": 27,
            "clock_24": "16:00",
            "season": "春季"
          },
          "window_days": 1,
          "repeat": {
            "kind": "seasonly",
            "interval": 1,
            "until_time": null,
            "max_occurrences": null
          }
        },
        "conditions": {
          "requires_not_at_war_with": [],
          "requires_relation_min": {},
          "requires_resources_min": {},
          "blocked_by_flags": []
        },
        "on_due": {
          "mode": "activate",
          "scene_type": "caravan",
          "turn_event_kind": "caravan_arrived",
          "suggested_prompt": "南方商队抵达城门，要求拜见领主。"
        },
        "on_resolve": {
          "record_history": true,
          "schedule_next": true
        },
        "related": {
          "people": [],
          "factions": ["南方商队"],
          "tiles": [],
          "buildings": [],
          "history_entries": []
        },
        "flags": {},
        "result_md": "",
        "created_by": "system",
        "updated_at": "2026-07-19T00:00:00Z"
      }
    ],
    "next_id": 2
  }
}
```

### GameTimePoint schema

所有长期事件统一使用：

```json
{
  "calendar_day": 27,
  "clock_24": "16:00",
  "season": "春季",
  "weather": "细雨"
}
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `calendar_day` | int | 游戏内绝对日，第 1 日开始 |
| `clock_24` | string | 24 小时制，`HH:MM` |
| `season` | string | 可缓存显示；normalize 时可按 calendar_day 重算 |
| `weather` | string | 创建/触发时天气快照，可为空 |

不存储：

- `due_turn`
- `in_turns`
- `created_turn`

如果前端需要展示“第几轮”，按公式从 `calendar_day` 计算：

```text
turn = floor((calendar_day - 1) / state.time.turn_days) + 1
day_in_turn = ((calendar_day - 1) % state.time.turn_days) + 1
```

### status 枚举

| status | 含义 |
|---|---|
| `scheduled` | 已安排，未到期 |
| `due` | 到期但尚未激活，通常只作为瞬时中间态 |
| `active` | 已触发，正在发生 |
| `resolved` | 已完成 |
| `cancelled` | 被取消 |
| `missed` | 因窗口过期或条件不满足而错过 |

### visibility

| visibility | 含义 |
|---|---|
| `player` | 玩家知道，可在事件面板显示 |
| `hint` | 只显示模糊提示 |
| `secret` | 玩家不可见，仅后端/Hermes 可见 |
| `debug` | 仅测试/调试显示 |

## 事件模板配置

不要把事件类型和基础参数硬编码在 Python 逻辑里。

在 `backend/app/data/catalog.json` 中新增：

```json
{
  "event_templates": {
    "caravan_arrival": {
      "label": "商队到访",
      "default_importance": 3,
      "default_visibility": "player",
      "default_scene_type": "caravan",
      "default_due_clock_24": "16:00",
      "default_repeat": {
        "kind": "seasonly",
        "interval": 1
      },
      "tags": ["caravan", "economy", "diplomacy"],
      "prompt_hint": "商队抵达领地边界，等待领主许可入城。"
    },
    "enemy_arrival": {
      "label": "敌军抵达",
      "default_importance": 5,
      "default_visibility": "player",
      "default_scene_type": "battle",
      "tags": ["war", "military"],
      "prompt_hint": "敌军旗帜出现在远处道路上。"
    }
  }
}
```

Python 负责：

- 读取模板。
- 校验事件 type 是否存在。
- 按模板填默认值。
- 执行通用 due/cancel/reschedule/resolve 流程。

具体事件影响尽量通过已有 mutation API、battle API、diplomacy API 执行。

## 后端模块设计

新增：

```text
backend/app/systems/scheduled_events.py
```

职责：

- normalize scheduled event state。
- 创建计划事件。
- 取消/改期计划事件。
- 查询到期事件。
- 到期后激活事件或直接执行效果。
- resolve active event。
- recurring 事件生成下一次计划。
- 把重要结果交给历史系统记录。

建议函数：

```python
def normalize_scheduled_events(state: dict[str, Any]) -> None

def schedule_event(
    state: dict[str, Any],
    *,
    event_type: str,
    title: str | None = None,
    description_md: str = "",
    due_time: dict[str, Any] | None = None,
    in_days: int | None = None,
    in_hours: int | None = None,
    in_minutes: int | None = None,
    clock_24: str | None = None,
    visibility: str | None = None,
    importance: int | None = None,
    related: dict[str, Any] | None = None,
    conditions: dict[str, Any] | None = None,
    flags: dict[str, Any] | None = None,
    created_by: str = "backend",
) -> dict[str, Any]

def cancel_event(
    state: dict[str, Any],
    event_id: str,
    *,
    reason_md: str,
    cancelled_by: str = "backend",
) -> dict[str, Any]

def reschedule_event(
    state: dict[str, Any],
    event_id: str,
    *,
    due_time: dict[str, Any] | None = None,
    in_days: int | None = None,
    in_hours: int | None = None,
    in_minutes: int | None = None,
    clock_24: str | None = None,
    reason_md: str = "",
) -> dict[str, Any]

def due_events(state: dict[str, Any]) -> list[dict[str, Any]]

def activate_due_events(
    state: dict[str, Any],
    *,
    source: str = "pipeline",
) -> list[TurnEvent]

def resolve_event(
    state: dict[str, Any],
    event_id: str,
    *,
    result_md: str,
    outcome: dict[str, Any] | None = None,
    resolved_by: str = "backend",
) -> dict[str, Any]

def schedule_next_occurrence(
    state: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any] | None
```

## 时间集成

事件到期判断基于 `schedule.due_time.calendar_day` 和 `schedule.due_time.clock_24`。

比较规则：

```python
def time_key(time_point):
    hour, minute = parse_clock_24(time_point["clock_24"])
    return time_point["calendar_day"] * 24 * 60 + hour * 60 + minute

event_is_due = time_key(event["schedule"]["due_time"]) <= time_key(state["time"])
```

不要用 `turn` 判断事件是否到期。

### 战略回合推进

战略回合一次推进 9 天。MVP 可采用：

1. 战略回合开始前检查已到期事件。
2. 时间推进到回合结束后检查 `schedule.due_time <= current state.time` 的事件。
3. 对于中途到期事件，在本轮报告中说明其实际到期日。

后续增强可以逐日模拟。

### 场景时间推进

如果场景模式中用户说：

- “两天后”
- “第二天傍晚”
- “等到商队抵达”

则 Hermes 应调用时间 API 推进时间。每次时间推进后，后端检查到期事件。

如果事件 due：

- 可以激活为 active event。
- 可以把 active event 挂到 `state.active_scene`。
- 可以返回提示让前端展示。

## API 设计

读接口：

```http
GET /api/events
```

Query：

```text
status=scheduled|active|resolved|cancelled|missed
visibility=player
limit=50
include_secret=false
```

返回：

```json
{
  "events": [],
  "total": 0
}
```

统一状态变更接口：

```http
POST /api/state/events/schedule
POST /api/state/events/{event_id}/cancel
POST /api/state/events/{event_id}/reschedule
POST /api/state/events/{event_id}/resolve
POST /api/state/events/check-due
```

### schedule payload

```json
{
  "event_type": "enemy_arrival",
  "title": "北方掠夺者逼近",
  "description_md": "斥候报告，敌人将在二十七日后抵达。",
  "in_days": 27,
  "clock_24": "08:00",
  "visibility": "player",
  "importance": 5,
  "related": {
    "factions": ["北方掠夺者"],
    "tiles": []
  },
  "created_by": "hermes"
}
```

如果用户或 Hermes 使用“几回合后”的表达，调用 API 前必须先换算成 `in_days`：

```text
in_days = 回合数 * state.time.turn_days
```

### cancel payload

```json
{
  "reason_md": "商队听闻道路战乱，取消本季行程。",
  "cancelled_by": "hermes"
}
```

### resolve payload

```json
{
  "result_md": "商队缴纳重税后离开，留下少量铁器和怨恨。",
  "outcome": {
    "record_history": true,
    "schedule_next": true,
    "resource_changes": {
      "gold": 80
    },
    "diplomacy_changes": {
      "南方商队": -15
    }
  },
  "resolved_by": "hermes"
}
```

## Hermes tools / skill 设计

每类场景 skill 中加入对应事件工具，但不要把所有工具塞成一个模糊大工具。

## Hermes prompt 到期强调

每次构造 Hermes prompt 前，后端必须检查长期事件：

```python
urgent_due_events = scheduled_events.due_events(state)
active_events = scheduled_events.active_events(state)
```

在 `backend/app/engine/hermes_context.py` 的 `compact_state_for_agent()` 中加入：

```json
{
  "scheduled_event_context": {
    "urgent_due_events": [],
    "active_events": [],
    "upcoming_events": []
  }
}
```

选择规则：

| 列表 | 条件 | 用途 |
|---|---|---|
| `urgent_due_events` | `schedule.due_time <= state.time` 且 status 为 `scheduled/due` | 必须在 prompt 顶部强调 |
| `active_events` | status 为 `active` | 场景推进时必须持续提醒 |
| `upcoming_events` | 未来 9 天内 importance >= 3 | 给 Hermes 预告，不强制触发 |

prompt 文案必须在普通上下文之前插入：

```text
【必须处理的到期事件】
以下事件的游戏内时间已经到达或超过。推进剧情时必须优先承认这些事件已经发生/抵达/爆发，并调用对应事件 API 激活或处理；不得继续假装它们尚未发生。
```

如果 `urgent_due_events` 非空：

1. strategic_turn 模式：
   - 本轮报告必须提到这些事件。
   - 如果事件 `on_due.mode == "activate"`，必须调用 `POST /api/state/events/check-due` 或对应 activate API。
2. scene_step 模式：
   - 如果当前场景与 due event 相关，直接把事件带入当前场景。
   - 如果不相关，也必须在叙事中插入打断/通报，例如“传令兵闯入大厅”。
3. description 模式：
   - 只读，不激活事件。
   - 但描述时可以把 active/due 事件作为环境背景。

不允许：

- prompt 中已经给出 due event，Hermes 仍输出“商队将在未来某日抵达”。
- due event 未被 API 激活，仅在文本里轻描淡写。

### 商队 skill

```text
schedule_caravan_arrival
cancel_caravan_arrival
reschedule_caravan_arrival
resolve_caravan_visit
```

### 外交 skill

```text
schedule_diplomatic_response
schedule_envoy_arrival
cancel_diplomatic_event
resolve_diplomatic_event
```

### 战争 skill

```text
schedule_enemy_arrival
schedule_reinforcements
activate_battle_event
resolve_war_event
```

### 日常/灾害 skill

```text
schedule_plague_wave
schedule_fire_spread
schedule_refugee_arrival
resolve_disaster_event
```

Hermes 使用规则：

- 如果叙事中承诺“几天后/几回合后/某日会发生”，必须调用 schedule API。
- 如果叙事中说“商队下次不会来”，必须 cancel 或 reschedule 对应 recurring event。
- 如果敌人已经被击退，必须 resolve/cancel 未来敌军事件。
- 不允许只在文本里承诺未来事件而不落入 state。

## 前端设计

新增“事件”入口，和“历史”分开。

### 事件面板

展示：

- 计划事件：标题、到期日期、剩余天数、可见性、重要性。
- 进行中事件：状态、相关势力/地点、处理入口。
- 已解决/取消事件：结果摘要。

交互：

- 按 status 筛选。
- 点击事件查看 Markdown 描述和结果。
- 对 active event 提供“进入场景/继续处理”按钮。
- 如果事件 `visibility == hint`，只显示模糊提示。

### 状态栏提示

可选：

- 在顶部状态栏显示最近将到期的重要事件数量。
- `importance >= 4` 且剩余 `<= 9` 天时提示。

## 与历史系统的关系

事件 resolve/cancel/missed 时，如果：

- `importance >= 3`
- 或 `on_resolve.record_history == true`
- 或事件类型是战争、外交、灾害、商队

则调用历史系统写入一条历史。

关联：

```json
{
  "related": {
    "scheduled_events": ["evt_000001"],
    "history_entries": ["hist_000010"]
  }
}
```

## 与现有 events 模块的关系

保留：

```text
backend/app/systems/events.py
```

作为“即时事件/阈值事件/随机事件”模块。

新增：

```text
backend/app/systems/scheduled_events.py
```

作为“长期计划事件”模块。

turn pipeline 的 events phase 顺序建议：

```text
check_due_scheduled_events
run_threshold_events
run_random_events
activate_due_scheduled_events
auto_record_history
```

如果 due event 激活为场景，pipeline 不应自动替玩家解决它，只应把它放入 active events，并在本轮报告中提示。

## 文件修改范围

后端：

```text
backend/app/systems/scheduled_events.py
backend/app/systems/events.py
backend/app/engine/state.py
backend/app/engine/time.py
backend/app/engine/turn.py
backend/app/engine/scenes.py
backend/app/engine/history.py
backend/app/engine/hermes_context.py
backend/app/api/state.py
backend/app/api/game.py
backend/app/api/schemas.py
backend/app/data/catalog.json
backend/tests/test_scheduled_events.py
```

前端：

```text
frontend/src/App.tsx
frontend/src/api.ts
frontend/src/styles.css
```

Hermes profile / skills：

```text
Hermes 场景 skills：caravan / diplomacy / war / daily disaster
Hermes profile tools：schedule/cancel/reschedule/resolve event API
```

## 测试用例

### 商队季末到访

1. 开局时自动安排春季末商队。
2. 推进到 due day 前，事件保持 `scheduled`。
3. 推进到 due day 后，事件变为 `active`。
4. 本轮报告提示商队抵达。
5. resolve 后生成历史。
6. 如果 repeat 为 seasonly，生成下一季到访事件。

### 商队取消下次到访

1. 当前商队事件 resolve，结果为被羞辱/抢劫。
2. Hermes 调用 cancel 或 reschedule 下一次商队事件。
3. 后续推进到原 due day，不应出现商队抵达。
4. 历史记录包含取消原因。

### 敌军几回合后抵达

1. Hermes 将“三回合后”换算为 `in_days = 3 * state.time.turn_days`，再调用 `schedule_enemy_arrival(in_days=27)`。
2. 推进 2 回合，不触发。
3. 推进第 3 回合，事件 active。
4. 前端事件面板显示战争事件。
5. 如果玩家提前外交解决，事件可 cancel。

### 场景中精确时间

1. 玩家在场景中说“两天后等使者回来”。
2. Hermes 调用时间推进 API。
3. scheduled event due 后自动 active。
4. 当前场景上下文中包含 active event。

### Hermes prompt 到期强调

1. 安排一个 `due_time` 已经早于当前 `state.time` 的商队事件。
2. 调用 `build_scene_step_context()`。
3. prompt 中必须出现 `【必须处理的到期事件】`。
4. prompt JSON 中必须包含该事件的 `urgent_due_events`。
5. 如果事件尚未 active，Hermes 的期望 API 调用必须包含 `POST /api/state/events/check-due` 或对应 activate API。
6. description 模式只允许读取该上下文，不允许激活事件。

### 条件阻塞

1. 商队事件要求 `requires_not_at_war_with=["南方商队"]`。
2. due 时如果正在战争，事件变为 `missed` 或 `cancelled`。
3. 本轮报告说明原因。
4. 历史按 importance 决定是否记录。

## 验证命令

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_scheduled_events.py
cd frontend && npm run build
```

Hermes 全量回归：

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python tools/run_hermes_scenario_matrix.py \
  --backend-url http://127.0.0.1:8000 \
  --hermes-url http://127.0.0.1:8643 \
  --hermes-key lord-tail-local-test \
  --model deepseek-v4-flash \
  --case-timeout-seconds 600
```

## 完成判定

- state 中存在稳定、可保存/读取的 `scheduled_events.entries`。
- 可以 schedule / cancel / reschedule / resolve 事件。
- 战略回合推进和场景时间推进都会检查 due events。
- 商队季末到访和敌军几回合后抵达两个核心 case 通过。
- Hermes skill 明确要求：承诺未来事件时必须调用 schedule API。
- 前端有独立事件面板，不与历史面板混淆。
- 事件 resolve/cancel 后能按规则写入历史系统。

## 不要做的事

- 不要用真实系统时间。
- 不要把计划事件只写进叙事文本。
- 不要把历史和事件合并成一个无状态列表。
- 不要让 due event 自动替玩家完成关键选择。
- 不要在 Python 中硬编码具体商队、敌军、灾害模板；模板放进 `catalog.json`。
