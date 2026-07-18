# Plan 012: 外交地图界面（Diplomacy Map UI）

## 目标

把当前"战术地图"旁边新增/拆分出一张**可配置尺寸（n×n）的外交地图**。外交地图是大地理与势力范围地图，不是领主直辖地产经营地图：

1. 地图尺寸可配置（默认 10×10，允许 6×6 到 24×24），不再硬编码 `range(1, 11)`。
2. 外交地图地块类型只包括：城镇、城堡、农村、流民窝棚、森林、草地、湖泊、河流、山丘，并由 `diplomacy_tile_kinds` 管理图标/颜色/说明。
3. 领地经营地图地块类型来自 Plan 005/005A 的 `buildings[*].tile_kind` 和基础地形，由 `map_tile_kinds` 管理；农田、伐木场、铁匠铺、采石场、作坊、酒馆等设施不属于外交地图地块类型。
4. 外交地图地块新增 `owner` 字段，可归属某个外交势力，让地图体现"谁的地盘在哪里"。领地地图为领主直辖经营地图，正常情况下不出现外交势力 owner。
5. 前端点击外交地图地块弹出**结构化**外交地块详情面板；点击外交势力弹出**结构化**势力详情面板（关系、姿态、条约、领地统计）。领地地图地块点击遵循 Plan 013 的描述缓存/邻接上下文要求。

## 重要修订：两张地图不可混用

本 plan 原始版本错误地把外交地图与领地经营地图合并为同一个 `state.map`，并把经营建筑类型也纳入外交地图目录。修订后必须满足：

- `state.map`：领地经营地图。只显示领主可直接操控的地形、建筑、地产设施；建筑来源为 Plan 005/005A 与 `catalog.buildings`。
- `state.diplomacy_map`：外交地图。只显示大地理和外交势力聚落，不显示农田、伐木场、铁匠铺、采石场、酒馆等领地设施。
- `map_tile_kinds`：领地经营地图 tile catalog。
- `diplomacy_tile_kinds`：外交地图 tile catalog。
- 势力领地统计必须扫描 `state.diplomacy_map`，不能扫描 `state.map`。

## 当前实现（背景）

- `backend/app/engine/state.py:27` 的 `initial_map()` 硬编码 `range(1, 11)`，只生成 `grass`、`castle`、`homes`、`forest` 四种 kind。
- `backend/app/engine/mutations.py:79` 的 `tile_at`、`update_tile_for_building` 已经支持任意地块查找和建筑覆盖，但没有尺寸或归属校验。
- `backend/app/systems/diplomacy.py` 的 `diplomacy` 是一个**扁平字典**（`{"金鳞": {...}, "血鸦": {...}}`），和地图完全没有关联，没有"势力控制哪些地块"的概念。
- `backend/app/catalog.py` / `backend/app/data/catalog.json` 里 `buildings[*].tile_kind` 已经提供了建筑驱动的领地经营地块类型（`homes`、`farm`、`lumberyard`、`quarry`……），这些必须留在领地地图目录，不应进入外交地图目录。
- 前端 `frontend/src/App.tsx`：
  - `icon` 表（第 5 行）和图例里的三元表达式（第 213 行）硬编码了地块图标和中文标签，只覆盖了部分 kind。
  - 地图渲染硬编码 `Array.from({ length: 100 })`、10 列、`['A'..'J']` 字母表头（第 213 行）。
  - 点击地块只会触发 `describeTile()`（第 164 行），走 Hermes SSE 生成一段叙事文本，没有任何结构化字段展示。
  - 外交信息只在头部显示一个写死的 `state.diplomacy['血鸦']`（第 210 行），以及 `DetailPanel` 里的一行纯文本拼接（第 226 行），没有可点击的势力详情。

## 输入

- `/Users/ray/raylab/lord-tail/backend/app/data/catalog.json`
- `/Users/ray/raylab/lord-tail/backend/app/catalog.py`
- `/Users/ray/raylab/lord-tail/backend/app/engine/state.py`
- `/Users/ray/raylab/lord-tail/backend/app/engine/mutations.py`
- `/Users/ray/raylab/lord-tail/backend/app/systems/diplomacy.py`
- `/Users/ray/raylab/lord-tail/backend/app/systems/construction.py`
- `/Users/ray/raylab/lord-tail/backend/app/api/state.py`
- `/Users/ray/raylab/lord-tail/backend/app/api/schemas.py`
- `/Users/ray/raylab/lord-tail/frontend/src/App.tsx`
- `/Users/ray/raylab/lord-tail/frontend/src/api.ts`
- `/Users/ray/raylab/lord-tail/frontend/src/styles.css`

如果 Plan 001-004、011 尚未执行，先确认对应模块（`systems/diplomacy.py`、`engine/time.py`、`engine/scenes.py`）已存在，本 plan 直接在其基础上扩展。

## 输出文件

新增：

```text
backend/tests/test_diplomacy_map.py
```

修改（不新增模块文件，直接扩展现有模块）：

```text
backend/app/data/catalog.json
backend/app/catalog.py
backend/app/engine/state.py
backend/app/engine/mutations.py
backend/app/systems/diplomacy.py
backend/app/systems/construction.py
backend/app/api/state.py
backend/app/api/schemas.py
backend/app/main.py
frontend/src/api.ts
frontend/src/App.tsx
frontend/src/styles.css
```

## catalog 扩展

### 1. `map` 配置

```json
"map": {
  "default_size": 10,
  "min_size": 6,
  "max_size": 24
}
```

### 2. `map_tile_kinds`：领地经营地图地块目录

新增/维护顶层 key，只覆盖**领地经营地图**可能出现在 `state.map[*].kind` 里的值——包括基础地形和 Plan 005/005A 的建筑驱动地块。不要把外交地图专属的 `town`、`village`、`slum` 放入这里：

```json
"map_tile_kinds": {
  "grass":   { "label": "草地",     "category": "terrain",    "icon": "·", "color": "#7fae5c", "description": "适宜耕作与建设的开阔地。" },
  "forest":  { "label": "森林",     "category": "terrain",    "icon": "♣", "color": "#3f6b3f", "description": "林木资源丰富，可伐木、狩猎。" },
  "hill":    { "label": "山丘",     "category": "terrain",    "icon": "▲", "color": "#a08a5c", "description": "地势较高，利于防御与采石。" },
  "lake":    { "label": "湖泊",     "category": "terrain",    "icon": "≈", "color": "#3b6e9e", "description": "不可建设的水域，提供渔获。" },
  "river":   { "label": "河流",     "category": "terrain",    "icon": "~", "color": "#4f86b5", "description": "灌溉水源，沿岸利于农业。" },
  "castle":     { "label": "城堡",   "category": "settlement", "icon": "♜", "color": "#9a7d3a", "description": "领主或势力的军事政治中心。" },
  "homes":      { "label": "村舍",   "category": "structure", "icon": "⌂", "color": "#8fae6c", "description": "" },
  "farm":       { "label": "农田",   "category": "structure", "icon": "≋", "color": "#c2b280", "description": "" },
  "lumberyard": { "label": "伐木场", "category": "structure", "icon": "♧", "color": "#3f6b3f", "description": "" },
  "quarry":     { "label": "采石场", "category": "structure", "icon": "◆", "color": "#a08a5c", "description": "" },
  "blacksmith":         { "label": "铁匠铺", "category": "structure", "icon": "⚒", "color": "#7a7a7a", "description": "" },
  "hunting_lodge":      { "label": "狩猎小屋", "category": "structure", "icon": "🏹", "color": "#3f6b3f", "description": "" },
  "ranch":              { "label": "养殖场", "category": "structure", "icon": "◐", "color": "#8fae6c", "description": "" },
  "handicraft_workshop":{ "label": "手工作坊", "category": "structure", "icon": "✦", "color": "#c9a227", "description": "" },
  "shop":               { "label": "商店", "category": "structure", "icon": "$", "color": "#c9a227", "description": "" },
  "tavern":             { "label": "酒馆", "category": "structure", "icon": "☕", "color": "#c9a227", "description": "" },
  "monastery":          { "label": "修道院", "category": "structure", "icon": "✝", "color": "#9a7d3a", "description": "" },
  "prison":             { "label": "监狱", "category": "structure", "icon": "⛓", "color": "#7a7a7a", "description": "" },
  "barracks":           { "label": "训练场", "category": "structure", "icon": "⚔", "color": "#7a7a7a", "description": "" },
  "wall":               { "label": "城墙", "category": "structure", "icon": "▤", "color": "#7a7a7a", "description": "" },
  "hut_yard":           { "label": "窝棚区", "category": "structure", "icon": "⌢", "color": "#7a6a58", "description": "" },
  "townhouses":         { "label": "镇屋", "category": "structure", "icon": "⌘", "color": "#c9a227", "description": "" },
  "manor":              { "label": "宅邸", "category": "structure", "icon": "⌂", "color": "#9a7d3a", "description": "" }
}
```

说明：`icon`/`color` 具体取值可以调整，但**每一个** `buildings[*].tile_kind` 和领地地图生成器可能写入的 kind 都必须在这里有对应条目——这是校验的硬性要求。`description` 允许留空字符串。

### 3. `diplomacy_tile_kinds`：外交地图地块目录

新增顶层 key，只覆盖外交大地图地块：

```json
"diplomacy_tile_kinds": {
  "grass":   { "label": "草地",     "category": "terrain",    "icon": "·", "color": "#7fae5c", "description": "开阔、低价值但便于通行的边境地带。" },
  "forest":  { "label": "森林",     "category": "terrain",    "icon": "♣", "color": "#3f6b3f", "description": "可阻隔军队行军，也可能藏匿猎户、盗匪或斥候。" },
  "hill":    { "label": "山丘",     "category": "terrain",    "icon": "▲", "color": "#a08a5c", "description": "高地会影响行军、视野与防御。" },
  "lake":    { "label": "湖泊",     "category": "terrain",    "icon": "≈", "color": "#3b6e9e", "description": "大型水域，通常限制通行并影响贸易路线。" },
  "river":   { "label": "河流",     "category": "terrain",    "icon": "~", "color": "#4f86b5", "description": "天然边界、交通线与补给线。" },
  "town":    { "label": "城镇",     "category": "settlement", "icon": "⌘", "color": "#c9a227", "description": "地区级商贸与行政中心。" },
  "castle":  { "label": "城堡",     "category": "settlement", "icon": "♜", "color": "#9a7d3a", "description": "地区级军事政治据点。" },
  "village": { "label": "农村",     "category": "settlement", "icon": "⌂", "color": "#8fae6c", "description": "地区级乡村聚落。" },
  "slum":    { "label": "流民窝棚", "category": "settlement", "icon": "⌢", "color": "#7a6a58", "description": "大地图上的流民聚集区。" }
}
```

外交地图中的 `town/village/slum/castle` 是地区级聚落概念，不等同于领地经营地图中的商店、农田、窝棚区、领主堡垒等建筑。

### 4. `factions`：势力静态资料

新增顶层 key，与现有 `diplomacy`（决定初始 stance）分离——`diplomacy` 管**动态**外交状态默认值，`factions` 管**静态**展示资料，两者用同样的 key（势力名）关联：

```json
"factions": {
  "金鳞": { "color": "#d4af37", "banner": "🐉", "description": "盘踞东境的古老王朝，重商而好和。" },
  "血鸦": { "color": "#8b1e2f", "banner": "🐦", "description": "以劫掠边境闻名的军阀势力。" }
}
```

约束：`factions` 的 key 必须和 `diplomacy`（`CATALOG["diplomacy"]`）的 key 完全一致；启动时校验，缺一个都要报错。

## 状态字段

`make_state()`（`backend/app/engine/state.py`）新增：

```json
{
  "map_size": 10,
  "diplomacy_map_size": 10
}
```

`Tile` schema 新增字段：

```json
{
  "x": 1,
  "y": 1,
  "kind": "forest",
  "label": "森林",
  "owner": null
}
```

- `owner` 取值：`null`（玩家直辖/无主）或某个 `factions` key（如 `"血鸦"`）。
- 领地地图 `state.map` 正常情况下全部 `owner: null`；外交地图 `state.diplomacy_map` 可出现外交势力 owner。
- 旧存档地块没有 `owner` 字段时，`normalize_state` 必须补 `owner: null`。
- 旧存档如果把外交 owner 地块混在 `state.map`，normalize 时必须把它迁移/重建到 `state.diplomacy_map`，并把 `state.map` 对应地块清理为普通领地地形。
- 旧存档没有 `map_size` 时，用 `int(len(state["map"]) ** 0.5)` 推出尺寸并写回。

## 后端实现

### 1. `engine/state.py`

```python
def initial_map(size: int = 10) -> list[dict[str, Any]]
def initial_diplomacy_map(size: int = 10) -> list[dict[str, Any]]
```

- `initial_map` 生成领地经营地图，`initial_diplomacy_map` 生成外交大地图。二者可以暂时共用尺寸配置，但不能共用 tile list。
- 生成规则（确定性布局，不做随机/噪声生成）：
  - 默认全部 `grass` / `owner: null`。
  - 地图中心 `(size // 2, size // 2)` 保留为 `castle` / `领主堡垒`（玩家堡垒），中心右侧一格 `homes` / `村舍`——沿用现有行为，坐标按 `size` 等比例换算，不再写死 `(5,5)/(5,6)`。
  - 左上角一小块区域铺 `forest`（沿用现有比例逻辑）。
  - 新增：在地图另外几个角落/边缘各放 1-2 块 `hill`、`lake`、`river`，保证默认地图上四种新地形都至少出现一次。地图尺寸过小（`size < 8`）时可以跳过部分地形，但至少保留 `forest` 和 `hill`。
  - `initial_diplomacy_map` 为 `CATALOG["factions"]` 里的每个势力，在地图边缘各放置 1 块外交聚落地块并设置 `owner`：例如靠右上角放一块 `owner: "金鳞", kind: "village"`，靠左下角放一块 `owner: "血鸦", kind: "castle"`。这是本 plan 的 MVP 播种规则，不追求地缘合理性。
- `make_state()` 写入 `state["map_size"] = size`，`state["map"] = initial_map(size)`，`state["diplomacy_map_size"] = size`，`state["diplomacy_map"] = initial_diplomacy_map(size)`。
- `StartRequest` 新增 `map_size: int | None`，传入时做 `min_size <= map_size <= max_size` 校验（`backend/app/api/schemas.py`），否则用 catalog 默认值。

### 2. `engine/mutations.py`

- `tile_at`、`update_tile_for_building` 保持坐标查找逻辑，但新增边界校验：坐标超出 `1..state["map_size"]` 时抛 `HTTPException(422, "坐标超出地图范围")`（当前依赖 pydantic 的 `ge=1,le=10` 静态上限，必须去掉写死的 `le=10`，改为运行时按 `state["map_size"]` 校验）。
- 新增校验：建筑不能建在 `tile.get("owner")` 不是 `None`（即属于其他势力）的地块上，`update_tile_for_building` 或 `construction.py` 里报 `ValueError("该地块归属外交势力，无法建设")`。

### 3. `systems/construction.py`

- 在现有 `tile["kind"] not in building["requires"]` 校验旁边，加入 owner 校验（见上）。

### 4. `systems/diplomacy.py`

新增函数：

```python
def faction_static_info(faction: str) -> dict[str, Any]
def territory_for_faction(state: dict[str, Any], faction: str) -> list[dict[str, Any]]
def faction_detail(state: dict[str, Any]) -> dict[str, dict[str, Any]]
```

- `faction_static_info`：从 `CATALOG["factions"]` 读取 `color/banner/description`，缺失时给出中性默认值（不报错，因为玩家可能通过 `/api/state/diplomacy` 动态新增一个 catalog 里没有的势力名）。
- `territory_for_faction`：扫描 `state["diplomacy_map"]`，返回 `owner == faction` 的地块列表（`x/y/kind/label`）。严禁扫描 `state["map"]`。
- `faction_detail`：对 `normalize_diplomacy_state(state)` 里的每个势力，合并动态状态 + 静态资料 + `owned_tiles`/`owned_tile_count`，返回：

```json
{
  "金鳞": {
    "stance": "中立", "relation": 0, "treaties": [], "at_war": false,
    "color": "#d4af37", "banner": "🐉", "description": "...",
    "owned_tiles": [{"x": 9, "y": 1, "kind": "village", "label": "..."}],
    "owned_tile_count": 1
  }
}
```

### 5. `api/state.py`

新增只读接口：

```http
GET /api/state/diplomacy
GET /api/hermes/diplomacy   (兼容别名，风格同其余 /api/hermes/*)
```

返回 `{"factions": diplomacy.faction_detail(state)}`。

### 6. `main.py`

- 新增 `validate_map_tile_kinds_catalog()`（放在 `catalog.py` 或新的小函数里均可，但必须在 app 启动时和 `validate_unit_combat_catalog()` 一起调用）：
  - 校验每个 `buildings[*].tile_kind` 都在 `map_tile_kinds` 里。
  - 校验 `factions` 的 key 集合和 `diplomacy` 的 key 集合完全相同。
  - 缺失时启动即报错，不能静默。

## 前端实现

### `frontend/src/api.ts`

- `Tile` 增加 `owner: string | null`。
- `GameState` 增加 `map_size: number`、`diplomacy_map_size: number`、`diplomacy_map: Tile[]`。
- 新增类型：

```ts
export type MapTileKind = { label: string; category: 'terrain' | 'settlement' | 'structure'; icon: string; color: string; description: string }
export type FactionStatic = { color: string; banner: string; description: string }
export type Catalog = {
  map: { default_size: number; min_size: number; max_size: number }
  map_tile_kinds: Record<string, MapTileKind>
  diplomacy_tile_kinds: Record<string, MapTileKind>
  factions: Record<string, FactionStatic>
  [key: string]: unknown
}
export type FactionDetail = DiplomacyState & FactionStatic & { owned_tiles: Tile[]; owned_tile_count: number }
```

- 新增客户端方法：

```ts
catalog: () => request<Catalog>('/catalog'),
state: {
  ...
  diplomacy: (mutation: DiplomacyMutation) => ...,        // 已存在，POST
  diplomacyRead: () => request<{ factions: Record<string, FactionDetail> }>('/state/diplomacy'), // 新增 GET
}
```

### `frontend/src/App.tsx`

1. 启动时（`useEffect`，和现有 `api.talents()` 并列）拉取 `api.catalog()`，存入 `catalog` state，供地图/图例/详情面板使用。领地地图遍历 `catalog.map_tile_kinds`；外交地图遍历/读取 `catalog.diplomacy_tile_kinds`。
2. 领地地图按 `state.map_size` + `state.map` 渲染；外交地图按 `state.diplomacy_map_size` + `state.diplomacy_map` 渲染：
   - 列头字母：`Array.from({ length: size }, (_, i) => columnLabel(i))`，`columnLabel` 对 `i < 26` 用 `A-Z`，否则退化为 `A1/A2...`（简单处理，避免硬编码超过 26 列崩溃）。
   - `map-grid` 的 CSS 改为 `grid-template-columns: repeat(var(--map-size), ...)`，`--map-size` 通过内联 style 传入 `state.map_size`。
3. 新增/维护 `TileDetailPanel` 组件（结构化，非 LLM）：点击地块时不再直接调用 `describeTile()`，而是打开该面板，展示：
   - 领地地图地块：坐标、`kind` 图标与中文标签来自 `map_tile_kinds`，归属显示"领地直辖"，描述入口遵循 Plan 013。
   - 外交地图地块：坐标、`kind` 图标与中文标签来自 `diplomacy_tile_kinds`；若 `tile.owner` 非空，展示所属势力并提供"查看外交详情"跳转到 `FactionDetailPanel`；若为空，显示"未被明确控制"。
4. 新增 `FactionDetailPanel` 组件（结构化）：展示势力旗帜/主色调/描述、`stance`、`relation`（数值 + 简单进度条，正负用不同颜色，参考现有 `Meter` 组件风格）、`at_war`、`treaties` 列表（名称+剩余回合）、`owned_tile_count` 和 `owned_tiles` 坐标列表（每个坐标可点击，点击后关闭当前面板并高亮/滚动到对应地块——MVP 可以只做"关闭面板 + 打开该地块的 TileDetailPanel"，不用做真正的地图滚动定位）。
5. 触发 `FactionDetailPanel` 的入口：
   - 从 `TileDetailPanel` 的"查看外交详情"按钮。
   - 地图旁新增一个"外交"小节（可以是图例下方的一行势力 chip 列表），遍历 `state.diplomacy` 的 key，每个势力显示旗帜+名称+姿态色点，点击打开 `FactionDetailPanel`。这取代当前头部写死的 `diplomacy-dot`（`血鸦`）和 `DetailPanel` 里纯文本拼接的外交行。
6. 数据获取：`FactionDetailPanel` 需要的 `relation/treaties/owned_tiles` 来自新接口 `api.state.diplomacyRead()`；面板打开时懒加载（若已有缓存则直接用，避免每次点击都发请求可以按需决定，MVP 允许每次打开都重新请求）。

### `frontend/src/styles.css`

- 新增地块 `owner` 的视觉标记（例如地块下边框用势力主色调渲染，宽度/透明度自定，不覆盖原有 kind 底色）。
- 新增 `TileDetailPanel`、`FactionDetailPanel` 样式，可以直接复用现有 `.modal-shade` / `.detail-modal` 类名结构，避免引入新的弹层机制。
- `.map-grid` 改为按 CSS 变量 `--map-size` 生成列数，替换当前写死的 10 列（如果当前用的是显式声明 10 个 `1fr`，改成 `repeat(var(--map-size, 10), 1fr)`）。

## 兼容策略

- 保留 `GameState.map`、`Tile.x/y/kind/label` 现有字段和语义，但 `GameState.map` 仅表示领地经营地图；新增 `GameState.diplomacy_map` 表示外交地图。
- 保留 `describe_tile` Hermes 模式和相关 SSE 流程，只是从"点击地块唯一行为"降级为"详情面板内的次要按钮"。
- `POST /api/state/diplomacy`（写）保持不变；新增的 `GET /api/state/diplomacy`（读）是独立路由，不冲突。
- 旧存档：
  - 无 `map_size` → 按 `sqrt(len(map))` 推导并写回。
  - 地块无 `owner` → normalize 时补 `null`。
  - 旧存档中 `state.map` 已混入外交 owner 地块 → normalize 时清理出领地地图，并重建/迁移到 `state.diplomacy_map`。
  - 无 `factions` catalog 条目的历史势力名（例如玩家通过 `/api/state/diplomacy` 手动加过一个 catalog 里没有的势力）→ `faction_static_info` 返回中性默认值（灰色、无旗帜），不报错。

## 步骤

1. 扩展 `catalog.json`：加 `map`、`map_tile_kinds`、`diplomacy_tile_kinds`、`factions`。
2. `catalog.py` 导出 `MAP_CONFIG`、`MAP_TILE_KINDS`、`DIPLOMACY_TILE_KINDS`、`FACTIONS`，并实现 `validate_map_tile_kinds_catalog()`。
3. `main.py` 启动时调用新增校验函数。
4. `engine/state.py`：
   - `initial_map(size)` 支持任意尺寸，只生成领地经营地图。
   - 新增 `initial_diplomacy_map(size)`，只生成外交大地图和势力聚落。
   - `make_state()` 写入 `map_size` / `map` / `diplomacy_map_size` / `diplomacy_map`，`StartRequest` 支持可选 `map_size`。
   - `normalize_state()`（或新增 `normalize_map(state)`）补齐旧存档字段，并迁移/清理混入 `state.map` 的外交 owner 地块。
5. `engine/mutations.py`：坐标越界校验改为运行时按 `state["map_size"]`；`update_tile_for_building` 增加 owner 校验。
6. `api/schemas.py`：`BuildingMutationRequest.x/y` 去掉写死的 `le=10`；`StartRequest` 加 `map_size`。
7. `systems/construction.py`：建设校验里加入"地块不能属于其他势力"。
8. `systems/diplomacy.py`：新增 `faction_static_info` / `territory_for_faction` / `faction_detail`。
9. `api/state.py`：新增 `GET /api/state/diplomacy`。
10. 前端 `api.ts`：新增类型和 `api.catalog()` / `api.state.diplomacyRead()`。
11. 前端 `App.tsx`：两张地图分别渲染、`TileDetailPanel`、`FactionDetailPanel`、势力 chip 列表、图例数据化。
12. 前端 `styles.css`：新增样式，网格改为变量驱动列数。
13. 新增 `backend/tests/test_diplomacy_map.py`。
14. 跑验证命令。

## 后端测试（`backend/tests/test_diplomacy_map.py`）

必须覆盖：

1. 默认开局：`state["map_size"] == 10`，`len(state["map"]) == 100`，坐标覆盖 `1..10`。
2. 自定义尺寸开局：`POST /api/game/start` 传 `map_size: 8` → `state["map_size"] == 8`，`len(state["map"]) == 64`，所有坐标在 `1..8`。
3. 默认地图上 `{"forest", "hill", "lake", "river"}` 四种新地形至少各出现一次。
4. 默认 `diplomacy_map` 上 `factions` catalog 里每个势力至少拥有一块 `owner` 等于自己的地块；默认 `map` 上所有地块 `owner is None`。
5. `GET /api/state/diplomacy` 返回的每个势力包含 `color`/`banner`/`owned_tile_count`，且 `owned_tile_count == len(owned_tiles)`。
6. `/api/state/buildings` 建设只修改 `state.map`，不得修改 `state.diplomacy_map`。
7. `map_tile_kinds` 覆盖所有 `buildings[*].tile_kind`（直接读 `public_catalog()` 断言）。
8. `factions` key 集合和 `diplomacy` key 集合一致（直接读 `public_catalog()` 断言）。
9. 旧格式存档（手工构造：无 `map_size`、地块无 `owner`，或 `state.map` 混入 owner 地块）经 `normalize_state` 后能推出 `map_size == 10`，`state.map` 全部 `owner is None`，且存在 `state.diplomacy_map`。

## 不要做的事

- 不做真正的随机/噪声地图生成，本 plan 只要求确定性、可复现的布局规则。
- 不实现基于地形的战术移动/寻路（`passable`、`defense_bonus` 这类字段留作未来 plan 的元数据占位，本 plan 不接入 `military.py` 战斗结算）。
- 不修改现有建筑的 `requires` 地形限制（建筑仍然只能建在 `grass` 上，除非未来单独立项）。
- 不做势力 AI 扩张/攻城掠地机制，`owner` 在本 plan 中是静态播种 + 手工/未来接口可改，不做自动演化。
- 不要求前端做真正的地图平移/缩放；n×n 超过默认视口大小时允许出现横向/纵向滚动，不必做视口裁剪优化。
- 不要移除或替换现有 `describe_tile` Hermes 叙事功能，只是把它从主行为降级为详情面板内的次要按钮。
- 不要把 `map_tile_kinds` 的图标/颜色写死进前端组件；前端必须从 `/api/catalog` 读取。

## 验证命令

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/test_diplomacy_map.py -q
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
cd frontend && npm run build
```

补充 smoke test（自定义地图尺寸 + 势力领地读取）：

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
start = client.post("/api/game/start", json={
    "lord_name": "Ray",
    "lord_gender": "未说明",
    "realm_name": "北境",
    "appearance": "",
    "personality": "",
    "talents": [{"id": "harvest_hand"}, {"id": "charismatic_lord"}],
    "map_size": 8,
})
assert start.status_code == 200, start.text
state = start.json()["state"]
assert state["map_size"] == 8
assert len(state["map"]) == 64
assert all(1 <= t["x"] <= 8 and 1 <= t["y"] <= 8 for t in state["map"])

kinds = {t["kind"] for t in state["map"]}
assert {"forest", "hill", "lake", "river"} <= kinds, kinds

dip = client.get("/api/state/diplomacy")
assert dip.status_code == 200, dip.text
factions = dip.json()["factions"]
for name, detail in factions.items():
    assert "color" in detail and "owned_tile_count" in detail
    assert detail["owned_tile_count"] == len(detail["owned_tiles"])

print("OK")
PY
```

## 完成判定

- `catalog.json` 新增 `map` / `map_tile_kinds` / `factions`，且启动时的校验函数会在缺项时报错。
- 地图尺寸可通过开局参数配置为 n×n（默认 10×10），旧存档自动 normalize 出 `map_size`。
- 地块新增 `owner` 字段；城镇/农村/流民窝棚/森林/草地/湖泊/河流/山丘等新地形和聚落类型能出现在默认地图上。
- `GET /api/state/diplomacy` 返回结构化的势力详情（静态资料 + 动态外交状态 + 领地统计）。
- 前端地图按 `map_size` 动态渲染列数/坐标表头，不再硬编码 10。
- 点击地块弹出结构化 `TileDetailPanel`；点击势力弹出结构化 `FactionDetailPanel`；二者可互相跳转。
- 现有 Hermes `describe_tile` 叙事功能仍可用，作为详情面板内的次要操作。
- 建筑无法建在其他势力领地的地块上。
- 后端测试、`compileall`、前端 `npm run build` 全部通过。
