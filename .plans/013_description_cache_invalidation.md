# Plan 013: 描述缓存、过期策略与邻域上下文

## 目标

把当前“每次点击描述领地/领主/地块都即时重新生成”的策略，升级为可控的描述生命周期系统：

1. **短期内不重新描述**：描述生成后在同一短期时间窗口内复用缓存。
2. **长期/季节变化后标记需要更新**：战略时间推进、季节变化、长期经过后，不立即生成，但标记为 stale。
3. **周围环境变化后标记需要更新**：
   - 当前地块发生变化时，该地块描述 stale。
   - 当前地块周围 8 格发生变化时，该地块描述 stale。
   - 领地整体描述在关键地图变化后 stale。
4. **生成地块描述时给 Hermes agent 周围地块信息和已有描述**：
   - 当前格。
   - 周围 8 格。
   - 这些格子的结构化信息。
   - 如果已有描述，也传给 Hermes，供其延续或改写。

本 plan 只解决描述缓存与过期，不改变战斗、经济或外交结算规则。

## 当前问题

当前实现：

- 前端点击 `描述领地` / `描述领主` / 地图格，直接创建 Hermes `describe_*` run。
- 描述结果只存于前端 drawer state。
- 不写回后端。
- 不进 save/load。
- 不知道描述是否过期。
- `describe_tile` 只传选中 tile，没有传周围 8 格。
- 地图变化不会影响描述状态。

这导致：

- 同一状态下重复点击会重复烧模型。
- 地块环境变了，旧描述无法判断是否失效。
- Hermes 描述单格时缺少周围上下文，容易写得孤立。

## 描述对象范围

首批支持：

```text
realm
lord
tile:{x}:{y}
item:{target_type}:{key}
```

其中本 plan 重点实现：

- `realm`
- `lord`
- `tile`

`item` 可以先走现有即时描述，后续再缓存。

## 状态 schema

在后端 state 中增加：

```json
{
  "descriptions": {
    "realm": {
      "markdown": "",
      "status": "missing|fresh|stale",
      "stale_reasons": [],
      "generated_turn": null,
      "generated_calendar_day": null,
      "generated_season": null,
      "source_state_hash": "",
      "updated_at": ""
    },
    "lord": {
      "markdown": "",
      "status": "missing|fresh|stale",
      "stale_reasons": [],
      "generated_turn": null,
      "generated_calendar_day": null,
      "generated_season": null,
      "source_state_hash": "",
      "updated_at": ""
    },
    "tiles": {
      "5:5": {
        "markdown": "",
        "status": "missing|fresh|stale",
        "stale_reasons": [],
        "generated_turn": null,
        "generated_calendar_day": null,
        "generated_season": null,
        "source_state_hash": "",
        "updated_at": ""
      }
    }
  }
}
```

### status 含义

| status | 含义 |
|---|---|
| `missing` | 从未生成过 |
| `fresh` | 可直接复用 |
| `stale` | 有缓存，但需要更新；前端可显示“可能已过时” |

### stale_reasons 示例

```text
season_changed
long_time_elapsed
realm_resources_changed
realm_buildings_changed
lord_profile_changed
tile_changed
neighbor_tile_changed
nearby_building_changed
scene_event_nearby
```

## 短期/长期更新策略

### 短期内不重新描述

短期定义：

- `calendar_day - generated_calendar_day < 9`
- 且没有显式 stale reason
- 且 source hash 一致或只发生了轻微非相关变化

行为：

- 前端点击描述时，优先读缓存。
- 如果 `status == fresh`，直接展示，不创建 Hermes run。

### 长期标记 stale

长期定义：

- `calendar_day - generated_calendar_day >= 27`，即 3 个战略回合。

行为：

- 不自动重新生成。
- 标记：

```text
long_time_elapsed
```

### 季节变化标记 stale

当 `state.time.season != generated_season`：

- `realm` stale。
- 所有已缓存 tile stale。
- `lord` 不因季节变化自动 stale，除非发生领主事件。

### 地图变化标记 stale

当某个地块 `(x, y)` 发生变化，例如：

- kind 变化。
- label 变化。
- owner/faction 变化。
- building_id 变化。
- event marker 变化。

则：

- `tile:x:y` stale，reason=`tile_changed`。
- 周围 8 格 stale，reason=`neighbor_tile_changed`。
- `realm` stale，reason=`realm_buildings_changed` 或 `map_changed`。

周围 8 格：

```text
(x-1,y-1) (x,y-1) (x+1,y-1)
(x-1,y)   (x,y)   (x+1,y)
(x-1,y+1) (x,y+1) (x+1,y+1)
```

边界外忽略。

## 后端模块设计

新增：

```text
backend/app/engine/descriptions.py
```

职责：

- normalize descriptions state。
- 计算描述对象 key。
- 标记 stale。
- 保存 Hermes 生成结果。
- 读取描述缓存。
- 构造 describe context，包括 tile 周围 8 格。

建议函数：

```python
def normalize_descriptions(state: dict[str, Any]) -> None
def description_key(target_type: str, *, x: int | None = None, y: int | None = None, key: str | None = None) -> str
def get_description(state: dict[str, Any], target_type: str, **kwargs) -> dict[str, Any]
def save_description(state: dict[str, Any], target_type: str, markdown: str, **kwargs) -> dict[str, Any]
def mark_description_stale(state: dict[str, Any], target_type: str, reason: str, **kwargs) -> None
def mark_tile_and_neighbors_stale(state: dict[str, Any], x: int, y: int, reason: str = "tile_changed") -> None
def mark_due_descriptions_stale(state: dict[str, Any]) -> None
def tile_neighborhood(state: dict[str, Any], x: int, y: int) -> dict[str, Any]
```

## source_state_hash

描述缓存需要 hash 判断是否仍适用。

### realm hash 包含

- `turn`
- `time.calendar_day`
- `season`
- `weather`
- `resources`
- `buildings`
- `diplomacy`
- `army`
- `active_scene` 简要状态
- map 中建筑/地貌统计

### lord hash 包含

- `lord_name`
- `lord_gender`
- `appearance`
- `personality`
- `talents`
- 领主相关 recent_events

### tile hash 包含

- 当前 tile。
- 周围 8 格 tile。
- 当前 tile 已有事件 marker。
- 当前/周围建筑信息。
- 当前时间：season/weather/time_of_day。

## API 设计

新增 API：

### 读取描述缓存

```http
GET /api/descriptions/{target_type}
```

Query：

```text
x=5&y=5&key=...
```

返回：

```json
{
  "target_type": "tile",
  "key": "tile:5:5",
  "description": {
    "markdown": "...",
    "status": "fresh",
    "stale_reasons": [],
    "generated_turn": 1,
    "generated_calendar_day": 1,
    "generated_season": "春季",
    "updated_at": "..."
  },
  "context": {
    "target": {},
    "neighbors": []
  }
}
```

### 保存描述结果

```http
POST /api/descriptions/{target_type}
```

Payload：

```json
{
  "markdown": "...",
  "x": 5,
  "y": 5,
  "key": null,
  "source": "hermes"
}
```

行为：

- 保存 markdown。
- status=`fresh`。
- stale_reasons 清空。
- 记录 generated_turn/calendar_day/season/source_state_hash/updated_at。

### 标记描述过期

```http
POST /api/descriptions/{target_type}/stale
```

Payload：

```json
{
  "reason": "tile_changed",
  "x": 5,
  "y": 5,
  "key": null
}
```

主要供内部测试/调试，正式业务优先由后端事件自动标记。

## describe-context 更新

修改：

```text
GET /api/agent/describe-context
```

### realm context 增加

```json
{
  "cached_description": {},
  "description_status": "fresh|stale|missing",
  "stale_reasons": [],
  "map_summary": {},
  "changed_tiles_recently": []
}
```

### lord context 增加

```json
{
  "cached_description": {},
  "description_status": "fresh|stale|missing",
  "stale_reasons": [],
  "lord_recent_events": []
}
```

### tile context 增加

```json
{
  "target": {
    "x": 5,
    "y": 5,
    "kind": "castle",
    "label": "领主堡垒"
  },
  "neighbors": [
    {
      "direction": "N",
      "x": 5,
      "y": 4,
      "kind": "grass",
      "label": "草地",
      "cached_description": {}
    }
  ],
  "cached_description": {},
  "description_status": "stale",
  "stale_reasons": ["neighbor_tile_changed"]
}
```

Hermes 生成 tile 描述时，必须收到：

- 当前地块结构。
- 周围 8 格结构。
- 当前地块旧描述。
- 周围地块旧描述，如果存在。
- 当前季节/天气/time_of_day。

## Hermes 描述 run 写回策略

当前前端直接展示 Hermes output。需要改为：

1. 前端点击描述。
2. 前端先调用 `GET /api/descriptions/{target_type}`。
3. 如果 `status == fresh` 且用户没有点击“重新生成”：
   - 直接展示缓存 markdown。
   - 不调用 Hermes。
4. 如果 `missing/stale`：
   - 调用 Hermes describe run。
   - run completed 后，前端调用 `POST /api/descriptions/{target_type}` 保存 markdown。
   - 再展示保存后的 markdown。

说明：

- 短期内不会重新描述。
- stale 不代表自动生成，只是 UI 提示。
- 用户可以手动点击“重新生成”绕过缓存。

## 后端自动 stale 标记点

### 时间推进

在 `engine/time.py` 中：

- `advance_strategic_clock`
- `advance_calendar`

调用：

```python
mark_due_descriptions_stale(state)
```

规则：

- season changed：realm + all cached tiles stale。
- long_time_elapsed：realm + all cached tiles stale。

### 地图变化

所有会修改 tile 的地方必须调用：

- `engine/mutations.update_tile_for_building`
- `systems/construction.complete_project`
- `systems/construction.destroy_building`
- 未来 diplomacy map owner 修改 API。

调用：

```python
mark_tile_and_neighbors_stale(state, x, y)
mark_description_stale(state, "realm", "map_changed")
```

### 领主变化

未来如果新增领主事件 API：

- 外貌变化。
- 性格/声望变化。
- 称号/伤病/诅咒/祝福变化。

调用：

```python
mark_description_stale(state, "lord", "lord_profile_changed")
```

当前 plan 先不新增领主属性 mutation API，只预留函数和测试。

## 前端调整

### DescriptionState 扩展

```ts
type DescriptionState = {
  open: boolean
  title: string
  text: string
  trace: AgentTraceEvent[]
  loading: boolean
  status?: 'missing' | 'fresh' | 'stale'
  stale_reasons?: string[]
  generated_turn?: number | null
  generated_calendar_day?: number | null
}
```

### Drawer UI

显示：

- `fresh`：`描述生成于第 N 轮 / 第 X 日`
- `stale`：`描述可能已过时：季节变化 / 周围地块变化`
- `missing`：`尚未生成描述`

按钮：

- `重新生成`
- `使用缓存`

### 点击描述流程

修改 `describe()`：

```text
read cache -> fresh 则展示 -> missing/stale 则允许生成 -> run completed -> save cache
```

对于 tile：

- 传 `x/y`。
- 保存时也传 `x/y`。

## Hermes skill 更新

更新：

```text
lord-tail-description
lord-tail-game/references/api_contract.md
```

新增描述规则：

- 描述模式仍只读，不得 mutation。
- 可以读取 `/api/agent/describe-context`。
- 生成 tile 描述时必须利用 `neighbors`。
- 如果有 cached_description：
  - fresh：通常不应该重新生成。
  - stale：以旧描述为基础，结合 stale reason 更新。

新增 API contract：

- `GET /api/descriptions/{target_type}`
- `POST /api/descriptions/{target_type}`
- `POST /api/descriptions/{target_type}/stale`

## 测试

新增：

```text
backend/tests/test_description_cache.py
backend/tests/test_description_invalidation.py
backend/tests/test_describe_context_neighbors.py
```

### 必测 case

1. 初始状态 descriptions 存在：
   - realm missing
   - lord missing
   - tiles empty

2. 保存 realm 描述：
   - status=fresh
   - generated_turn 当前 turn
   - generated_calendar_day 当前 calendar_day

3. 短期读取不 stale：
   - 生成后推进 1 天 scene time
   - cache 仍 fresh

4. 长期 stale：
   - 生成后推进 27 天
   - realm stale reason 包含 `long_time_elapsed`

5. 季节变化 stale：
   - 生成 realm/tile 后推进到下季
   - realm/tile stale reason 包含 `season_changed`

6. 当前 tile 变化：
   - 保存 tile 5:5 描述
   - 修改 5:5 kind/label
   - tile 5:5 stale reason 包含 `tile_changed`

7. 周围 8 格变化：
   - 保存 tile 5:5 描述
   - 修改 5:4
   - tile 5:5 stale reason 包含 `neighbor_tile_changed`

8. 非邻居变化不影响：
   - 保存 tile 5:5
   - 修改 1:1
   - tile 5:5 仍 fresh

9. describe-context tile：
   - target 是当前格。
   - neighbors 长度最多 8。
   - 包含周围格 cached_description。

10. description mode 不暴露 mutation API。

## 实施步骤

1. 新增 `engine/descriptions.py`。
2. `engine/state.py` normalize 中接入 descriptions。
3. 新增 API schemas：
   - `DescriptionSaveRequest`
   - `DescriptionStaleRequest`
4. 新增 API router 或扩展 `agent_tools.py`：
   - `GET /api/descriptions/{target_type}`
   - `POST /api/descriptions/{target_type}`
   - `POST /api/descriptions/{target_type}/stale`
5. 修改 `describe-context`，为 realm/lord/tile 加 cache metadata。
6. 在地图变化点调用 stale 标记：
   - `update_tile_for_building`
   - `complete_project`
   - `destroy_building`
7. 在时间推进点调用长期/季节 stale 标记。
8. 修改前端 `api.ts`。
9. 修改前端 `describe()` 流程和 drawer UI。
10. 更新 Hermes description skill 和 API contract。
11. 补测试。
12. 跑验证。

## 验证命令

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python -m pytest \
  backend/tests/test_description_cache.py \
  backend/tests/test_description_invalidation.py \
  backend/tests/test_describe_context_neighbors.py -q
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
cd frontend && npm run build
```

## 完成判定

- 描述结果持久化到后端 state，并能 save/load。
- fresh 缓存不会短期重复生成。
- stale 状态只标记，不自动烧模型。
- 长期、季节变化、当前地块变化、周围 8 格变化能正确标记 stale。
- tile 描述 context 包含当前格和周围 8 格结构与缓存描述。
- 前端能显示描述状态，并支持重新生成。
- Hermes description skill 明确要求使用邻域上下文。
- 全量测试与前端 build 通过。
