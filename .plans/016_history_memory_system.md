# Plan 016: 历史系统与领地记忆

## 目标

新增一个独立的历史系统，让“书记官”把值得记录的事情整理为结构化历史条目，作为领地长期记忆的一部分。

历史系统不是调试日志，也不是 Hermes trace。它的职责是：

1. 记录领地真正发生过的重要事情。
2. 支持前端“历史/编年史”页面查看。
3. 支持 Hermes agent 在叙事、描述、外交、战斗时读取相关历史，形成连续记忆。
4. 支持系统自动记录，也支持 Hermes 在故事推进过程中主动调用 API 记录。
5. 支持后续检索、摘要、按标签/人物/地点/势力关联。

## 当前问题

当前实现中：

- `history` 面板基本是静态/占位展示。
- Hermes run trace 只适合作为调试过程，不适合作为玩家可见编年史。
- turn events 是当轮结算结果，缺少长期保存、重要性、标签、关联对象。
- 后端没有统一的“领地记忆”读写接口。
- Hermes context 主要包含当前状态，缺少历史上下文。

这导致：

- 之前发生过的外交、战争、商队、法令、灾害、领主事件不会自然影响后续叙事。
- 玩家无法查看“这片领地到底经历过什么”。
- Hermes 容易重复设定、忘记承诺、忘记敌人或商队曾经发生的事件。

## 非目标

本 plan 不实现：

- 向量数据库。
- 复杂全文搜索引擎。
- 自动摘要压缩所有历史。
- 多存档历史合并。
- 删除真实发生过的历史。

MVP 只做结构化条目、基础筛选、Hermes context 注入和前端展示。

## 历史条目 schema

在后端 state 中新增：

```json
{
  "history": {
    "entries": [
      {
        "id": "hist_000001",
        "turn": 1,
        "calendar_day": 1,
        "clock_24": "06:00",
        "season": "春季",
        "weather": "细雨",
        "title": "亚历山大站上黑逼堡阳台",
        "summary_md": "领主在细雨中俯瞰泥泞领地，仆人与卫兵在恐惧中等待命令。",
        "details_md": "",
        "source": "scribe",
        "importance": 4,
        "visibility": "player",
        "tags": ["opening", "lord_event", "realm"],
        "related": {
          "people": ["亚历山大"],
          "factions": [],
          "tiles": ["5:5"],
          "buildings": ["lord_keep"],
          "resources": [],
          "scheduled_events": [],
          "turn_events": []
        },
        "created_by": "hermes|system|player|backend",
        "created_at": "2026-07-19T00:00:00Z",
        "updated_at": "2026-07-19T00:00:00Z"
      }
    ],
    "next_id": 2
  }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 稳定历史条目 id |
| `turn` | int | 发生时战略回合 |
| `calendar_day` | int | 发生时日历日 |
| `clock_24` | string | 24 小时时间 |
| `season` | string | 发生季节 |
| `weather` | string | 发生天气 |
| `title` | string | 玩家可见标题 |
| `summary_md` | string | 简短 Markdown 摘要 |
| `details_md` | string | 可选长 Markdown 记录 |
| `source` | string | `scribe` / `system` / `pipeline` / `scene` / `battle` / `diplomacy` |
| `importance` | int | 1-5，5 为必须注入长期记忆 |
| `visibility` | string | `player` / `secret` / `debug` |
| `tags` | list[string] | 检索标签 |
| `related` | object | 关联人物、势力、地块、建筑、资源、事件 |

## 记录策略

### 自动记录

后端可以从结构化 `TurnEvent` 自动生成历史条目。

自动记录条件：

- `severity == "critical"`：必记。
- `severity == "warning"` 且涉及外交、军事、灾害、人口大幅变化：必记。
- 建筑完工、法令发布、战争开始/结束、外交关系显著变化：必记。
- 资源小幅变化、普通收益、普通维护费：不记。

建议映射：

| TurnEvent kind | 历史策略 |
|---|---|
| `building_completed` | importance 3 |
| `law_enacted` | importance 4 |
| `battle_resolved` | importance 5 |
| `diplomacy_changed` | relation 变化绝对值 >= 20 时 importance 4 |
| `famine` / `plague` / `fire` | importance 5 |
| `caravan_arrived` | importance 3 |
| `caravan_cancelled` | importance 4 |
| `resource_changed` | 默认不记 |

### Hermes 主动记录

Hermes 在故事推进过程中，如果认为某件事会影响后续叙事，应调用历史记录接口。

典型场景：

- 领主羞辱了某个使者。
- 商队与领主达成承诺。
- 某个 NPC 被关入地牢。
- 玩家发布残酷法令。
- 某地块发生杀戮、火灾、神迹、瘟疫。
- 战斗中某支部队溃败或立功。

## 后端模块设计

新增：

```text
backend/app/engine/history.py
```

职责：

- normalize history state。
- 生成历史 id。
- 新增/更新历史条目。
- 从 TurnEvent 自动提取历史。
- 为 Hermes context 选择相关历史。
- 为前端提供过滤后的历史列表。

建议函数：

```python
def normalize_history(state: dict[str, Any]) -> None

def append_history_entry(
    state: dict[str, Any],
    *,
    title: str,
    summary_md: str,
    details_md: str = "",
    source: str = "system",
    importance: int = 3,
    visibility: str = "player",
    tags: list[str] | None = None,
    related: dict[str, Any] | None = None,
    created_by: str = "backend",
) -> dict[str, Any]

def update_history_entry(
    state: dict[str, Any],
    entry_id: str,
    patch: dict[str, Any],
) -> dict[str, Any]

def auto_record_turn_events(
    state: dict[str, Any],
    events: list[TurnEvent],
) -> list[dict[str, Any]]

def select_history_context(
    state: dict[str, Any],
    *,
    tags: list[str] | None = None,
    people: list[str] | None = None,
    factions: list[str] | None = None,
    tiles: list[str] | None = None,
    min_importance: int = 3,
    limit: int = 12,
) -> list[dict[str, Any]]
```

## API 设计

读接口：

```http
GET /api/history
```

Query：

```text
limit=50
offset=0
tag=diplomacy
source=battle
min_importance=3
visibility=player
```

返回：

```json
{
  "entries": [],
  "total": 0
}
```

详情接口：

```http
GET /api/history/{entry_id}
```

统一状态变更接口：

```http
POST /api/state/history
```

Payload：

```json
{
  "title": "商队首领被羞辱",
  "summary_md": "南方商队首领在黑逼堡大厅被迫跪在泥水里。",
  "details_md": "",
  "source": "scene",
  "importance": 4,
  "visibility": "player",
  "tags": ["caravan", "lord_event"],
  "related": {
    "people": ["亚历山大", "南方商队首领"],
    "factions": ["南方商队"],
    "tiles": ["5:5"],
    "scheduled_events": []
  },
  "created_by": "hermes"
}
```

可选更新接口：

```http
PATCH /api/state/history/{entry_id}
```

限制：

- 只能修正标题、摘要、标签、关联对象、重要性。
- 不提供物理删除接口。
- 如果需要隐藏，设置 `visibility = "debug"` 或 `visibility = "secret"`。

## Hermes tools / skill 设计

在 Hermes 场景 skill 中新增工具说明：

```text
record_history_entry
update_history_entry
query_history
```

其中：

- `record_history_entry` 调用 `POST /api/state/history`。
- `query_history` 调用 `GET /api/history`。
- Hermes 不应该把每一句对话都记录进历史，只记录“之后会影响领地、人物、外交、战争、经济的事情”。

### Hermes context 注入

在 `backend/app/engine/hermes_context.py` 中注入：

1. 最近 8 条 `importance >= 3` 的玩家可见历史。
2. 当前场景相关标签的历史。
3. 当前描述对象相关历史：
   - 描述领地：realm / law / disaster / battle / diplomacy。
   - 描述领主：lord_event / person。
   - 描述地块：该 tile 和周围 8 格相关历史。
   - 外交：对应 faction 相关历史。

注意：

- context 注入使用摘要，不传无限 details。
- 如果历史过多，优先 `importance` 高、时间近、相关性高。

## 前端设计

改造现有“历史”功能菜单。

### 历史面板

展示：

- 时间：第几轮 / 日历日 / 24 小时 / 季节。
- 标题。
- Markdown 摘要。
- 标签。
- 重要性。
- 来源。
- 关联对象。

交互：

- 按标签筛选。
- 按重要性筛选。
- 点击展开 `details_md`。
- 支持 Markdown table 渲染。

### 与事件系统的关系

历史面板展示“已经发生并被记录的事情”。

事件面板展示“正在发生/未来可能发生/已安排但未完成的事情”。

不要把两者混成一个列表。

## 与 turn pipeline 的集成

在战略回合结算完成后：

1. pipeline 产出 `events`。
2. `auto_record_turn_events(state, events)` 生成必要历史。
3. `events_to_report(events)` 继续生成本轮报告。
4. 返回 response 时附带 `history_entries_created`，方便测试和前端提示。

在场景结束时：

1. scene summary 可以被记录为历史。
2. 如果 Hermes 已主动记录关键事件，scene end 不重复记录。
3. 如果 scene 有 `outcome.importance >= 3`，自动生成一条 scene 历史。

## 文件修改范围

后端：

```text
backend/app/engine/history.py
backend/app/engine/state.py
backend/app/engine/turn.py
backend/app/engine/scenes.py
backend/app/engine/hermes_context.py
backend/app/api/state.py
backend/app/api/game.py
backend/app/api/schemas.py
backend/tests/test_history_system.py
```

前端：

```text
frontend/src/App.tsx
frontend/src/api.ts
frontend/src/styles.css
```

Hermes profile / skills：

```text
hermes/profiles 或当前项目中保存 profile/skill 的位置
```

如果当前项目没有本地保存 Hermes skill 文件，至少更新生成 profile/skill 的脚本和测试 fixture。

## 测试用例

### 后端 smoke

1. 开局后 `state.history.entries == []` 或只有 opening entry。
2. 调用 `POST /api/state/history` 新增一条。
3. `GET /api/history` 可以读到。
4. save/load 后历史仍存在。
5. `select_history_context` 能按 faction / tag / tile 取回相关历史。

### pipeline 自动记录

1. 发布法令后生成 `law_enacted` 历史。
2. 战斗结算后生成 `battle_resolved` 历史。
3. 普通粮食 +10 不生成历史。
4. 火灾/瘟疫/饥荒生成 importance 5 历史。

### Hermes 测试

1. 场景中玩家羞辱商队首领，Hermes 应调用 `record_history_entry`。
2. 后续再次接见同一商队，Hermes context 应包含这条历史。
3. 描述相关地块时，Hermes context 应包含该地块相关历史。

## 验证命令

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_history_system.py
cd frontend && npm run build
```

如涉及 Hermes 场景回归，额外运行：

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

- state 中存在稳定、可保存/读取的 `history.entries`。
- 前端历史面板展示真实后端历史，不再是占位内容。
- Hermes 可以调用 API 主动记录历史。
- turn pipeline 能把重要结构化事件自动写入历史。
- Hermes context 能注入最近且相关的重要历史。
- 所有新增测试通过。

## 不要做的事

- 不要把 Hermes trace 当历史。
- 不要把所有 TurnEvent 都无脑写入历史。
- 不要让历史条目只有中文自由文本，必须保留结构化标签和关联对象。
- 不要在 Python 里硬编码大量事件文案模板；可先生成朴素摘要，复杂叙事交给 Hermes。
