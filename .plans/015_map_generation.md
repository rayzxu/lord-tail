# Plan 015: 自动生成领地地图与外交地图

## 目标

建立可重复、可配置的地图自动生成系统，把“领地经营地图”和“外交大地图”彻底分开生成。

本 plan 的硬性规则：

1. 领地地图上，领主堡垒必须位于地图正中央。
2. 只有外交地图上可以出现山丘、湖泊、河流等大地理地形。
3. 领地地图不得出现其他外交势力所属的地产、聚落或 `owner`。
4. 外交地图不得出现农田、伐木场、铁匠铺、采石场、酒馆、作坊等领地经营建筑。

## 当前问题

- `state.map` 和 `state.diplomacy_map` 已经拆分，但生成逻辑仍在 `backend/app/engine/state.py` 里以硬编码方式混杂实现。
- 领地地图需要自动生成更多可经营地块，但不能混入外交势力。
- 外交地图需要自动生成大地理、势力位置和边境格局，但不能混入领地经营建筑。
- 旧存档或前端旧 state 可能仍把外交势力地块显示在领地地图上，需要后端 normalize 和前端渲染双重防线。

## 输入

```text
backend/app/data/catalog.json
backend/app/catalog.py
backend/app/engine/state.py
backend/app/engine/mutations.py
backend/app/systems/diplomacy.py
frontend/src/App.tsx
frontend/src/api.ts
backend/tests/test_diplomacy_map.py
```

## 输出

新增：

```text
backend/app/engine/mapgen.py
backend/tests/test_map_generation.py
```

修改：

```text
backend/app/data/catalog.json
backend/app/catalog.py
backend/app/engine/state.py
frontend/src/App.tsx
.plans/README.md
```

## 数据配置

在 `catalog.json` 中新增：

```json
"map_generation": {
  "realm": {
    "default_size": 10,
    "center_building": {
      "kind": "castle",
      "label": "领主堡垒"
    },
    "starting_neighbors": [
      { "dx": 0, "dy": 1, "kind": "homes", "label": "村舍" }
    ],
    "allowed_initial_kinds": ["grass", "forest", "castle", "homes"],
    "forest_patches": [
      { "anchor": "north_west", "width": 2, "height": 3 }
    ]
  },
  "diplomacy": {
    "default_size": 10,
    "allowed_initial_kinds": ["grass", "forest", "hill", "lake", "river", "town", "castle", "village", "slum"],
    "terrain_patches": [
      { "kind": "forest", "anchor": "north_west", "width": 2, "height": 3 },
      { "kind": "hill", "anchor": "north_east", "width": 2, "height": 2 },
      { "kind": "lake", "anchor": "south_west", "width": 2, "height": 2 },
      { "kind": "river", "shape": "south_edge" }
    ],
    "faction_placement": {
      "strategy": "perimeter_even",
      "settlement_cycle": ["village", "castle", "town", "slum"]
    }
  }
}
```

说明：

- `map.default_size/min_size/max_size` 仍保留作为全局尺寸约束。
- `map_generation.realm.allowed_initial_kinds` 不允许包含 `hill/lake/river/town/village/slum`。
- `map_generation.diplomacy.allowed_initial_kinds` 不允许包含 Plan 005/005A 的经营建筑 kind，例如 `farm/lumberyard/blacksmith/quarry/tavern/shop`。

## 后端设计

新增 `backend/app/engine/mapgen.py`：

```python
def generate_realm_map(size: int, seed: str | None = None) -> list[dict[str, Any]]
def generate_diplomacy_map(size: int, factions: dict[str, Any], seed: str | None = None) -> list[dict[str, Any]]
def sanitize_realm_map(tiles: list[dict[str, Any]]) -> list[dict[str, Any]]
def validate_generated_maps(realm_map: list[dict[str, Any]], diplomacy_map: list[dict[str, Any]], size: int) -> None
```

### `generate_realm_map`

规则：

1. 生成 `size × size` 的领地经营地图。
2. 全部地块默认 `grass / 草地 / owner: None`。
3. 中央坐标：
   - 使用 `center = (size + 1) // 2`。
   - `x=center, y=center` 必须是 `castle / 领主堡垒 / owner: None`。
   - 默认 10×10 时中心仍使用 E5 或项目当前坐标规则中最接近中央的格子；如未来要支持偶数地图的双中心，必须单独立项。
4. 中央相邻格放初始房屋：
   - 默认 `x=center, y=center+1` 为 `homes / 村舍`。
   - 若越界则选择最近的合法邻格。
5. 可以出现 `forest`，用于伐木场/狩猎小屋等经营建筑前置条件。
6. 不允许出现：
   - `owner != None`
   - `town`
   - `village`
   - `slum`
   - `hill`
   - `lake`
   - `river`
   - 外交势力名称拼接出来的 label，例如 `血鸦农村`、`金鳞城镇`

### `generate_diplomacy_map`

规则：

1. 生成 `size × size` 的外交大地图。
2. 全部地块默认 `grass / 草地 / owner: None`。
3. 可以出现：
   - `forest`
   - `hill`
   - `lake`
   - `river`
   - `town`
   - `castle`
   - `village`
   - `slum`
4. 为 `catalog.factions` 中每个势力放置至少一个聚落地块：
   - 聚落必须位于地图边缘或接近边缘。
   - `owner` 必须等于势力 key。
   - label 形如 `{势力名}{聚落类型中文名}`。
5. 不允许出现 Plan 005/005A 的经营建筑 kind：
   - `farm`
   - `lumberyard`
   - `quarry`
   - `blacksmith`
   - `hunting_lodge`
   - `ranch`
   - `handicraft_workshop`
   - `shop`
   - `tavern`
   - `monastery`
   - `prison`
   - `barracks`
   - `wall`
   - `hut_yard`
   - `townhouses`
   - `manor`

### `sanitize_realm_map`

用于兼容旧存档。

必须把下列地块清理成 `grass / 草地 / owner: None`：

- `owner` 非空的地块。
- `kind in {"town", "village", "slum", "hill", "lake", "river"}` 的地块。
- label 中包含已知外交势力名且不是领主堡垒的地块。

注意：

- `castle` 不能直接清理，因为领主堡垒也是 `castle`。
- `castle + owner != None` 必须清理。

## `state.py` 改造

- `initial_map(size)` 改为调用 `mapgen.generate_realm_map(size)`。
- `initial_diplomacy_map(size)` 改为调用 `mapgen.generate_diplomacy_map(size, FACTIONS)`。
- `normalize_map(state)` 改为调用 `mapgen.sanitize_realm_map(state["map"])`。
- `make_state()` 写入：

```python
state["map"] = generate_realm_map(map_size)
state["diplomacy_map"] = generate_diplomacy_map(map_size, FACTIONS)
```

## 前端要求

- 领地地图只读取 `state.map`。
- 外交地图只读取 `state.diplomacy_map`。
- 领地地图渲染前保留只读防线：
  - 如果 tile 有 `owner`，显示为普通草地。
  - 如果 tile.kind 是 `town/village/slum/hill/lake/river`，显示为普通草地。
- 外交地图渲染前不得 fallback 到 `state.map`。
- 如果后端返回的 `diplomacy_map` 缺失，前端可以基于 `state.diplomacy` 生成临时 fallback，但这个 fallback 只能用于外交地图。

## 测试

新增 `backend/tests/test_map_generation.py`，覆盖：

1. `generate_realm_map(10)`：
   - `len(map) == 100`
   - 中央格为 `castle / 领主堡垒`
   - 没有任何 `owner`
   - 不包含 `town/village/slum/hill/lake/river`
2. `generate_diplomacy_map(10, FACTIONS)`：
   - `len(map) == 100`
   - 包含 `hill/lake/river`
   - 每个势力至少有一个 `owner == faction` 的地块
   - 不包含经营建筑 kind
3. `sanitize_realm_map()`：
   - 能清理 `owner` 非空地块。
   - 能清理 `town/village/slum/hill/lake/river`。
   - 不清理无 owner 的 `castle / 领主堡垒`。
4. `POST /api/game/start`：
   - `state.map` 满足领地地图约束。
   - `state.diplomacy_map` 满足外交地图约束。

## 验证命令

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/test_map_generation.py backend/tests/test_diplomacy_map.py -q
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
cd frontend && npm run build
```

## 完成判定

- 领地地图中心始终是领主堡垒。
- 领地地图不会显示其他势力地产。
- 领地地图不会出现山丘、湖泊、河流。
- 外交地图可以显示山丘、湖泊、河流和势力聚落。
- 前端两个地图的数据源和显示语义保持隔离。
