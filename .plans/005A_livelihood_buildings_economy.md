# Plan 005A: Livelihood Buildings and Local Production Economy

## 目标

补充与民生相关的建筑、资源产出和地方经济链条，为 Plan 005 的阶级人口经济提供更真实的产业基础。

本 plan 聚焦：

- 民生建筑目录。
- 建筑成本、工期、劳力、维护费。
- 建筑产出资源。
- 建筑对住房、阶级就业、民心、治安、训练的影响。
- 新资源类型，如铁、肉、皮革、手工品、服务收入等。

## 输入

- `/Users/ray/raylab/lord-tail/backend/app/data/catalog.json`
- `/Users/ray/raylab/lord-tail/backend/app/systems/economy.py`
- `/Users/ray/raylab/lord-tail/backend/app/systems/construction.py`
- `/Users/ray/raylab/lord-tail/backend/app/systems/demographics.py`

如果 Plan 005 尚未执行，先执行 Plan 005。

## 输出

主要修改：

```text
/Users/ray/raylab/lord-tail/backend/app/data/catalog.json
/Users/ray/raylab/lord-tail/backend/app/systems/economy.py
```

可选新增：

```text
/Users/ray/raylab/lord-tail/backend/app/systems/production.py
```

如果新增 `production.py`，`economy.py` 只做阶段编排，具体产出由 `production.py` 计算。

## 新资源

在 `catalog.json.resources` 中补充：

| id | 中文名 | 初始值 | 用途 |
|---|---|---:|---|
| `iron` | 铁 | 0 | 武器、工具、铁匠铺 |
| `meat` | 肉 | 0 | 食物、酒馆、军粮 |
| `leather` | 皮革 | 0 | 轻甲、鞍具、贸易 |
| `craft_goods` | 手工品 | 0 | 贸易、商店、财富 |
| `tools` | 工具 | 0 | 提高生产力、建筑效率 |
| `piety` | 虔敬 | 0 | 修道院、民心、事件 |
| `security` | 治安 | 50 | 监狱、训练场、犯罪事件 |
| `service_income` | 服务收入 | 0 | 商店、酒馆等服务业收入 |

`security` 可设置 `minimum=0`、`maximum=100`；其他资源 `minimum=0`。

## 建筑目录

在 `catalog.json.buildings` 中补充或完善：

| id | 中文名 | 主要产出 | 住房 | 备注 |
|---|---|---|---|---|
| `blacksmith` | 铁匠铺 | `iron`、`tools` | `workshop_home: 4` | 支持军备和工具 |
| `quarry` | 采石场 | `stone` | 无 | 已有，补经济字段 |
| `lumberyard` | 伐木场 | `wood` | 无 | 已有，补经济字段 |
| `hunting_lodge` | 狩猎小屋 | `meat`、`leather` | 无 | 依赖 forest |
| `ranch` | 养殖场 | `meat`、`leather` | `hut: 4` | 依赖 grass |
| `handicraft_workshop` | 手工作坊 | `craft_goods` | `workshop_home: 8` | 工匠核心建筑 |
| `shop` | 商店 | `gold`、`service_income` | `shop_home: 6` | 商贾核心建筑 |
| `tavern` | 酒馆 | `gold`、`service_income`、民心 | `shop_home: 4` | 消耗 `food/meat` |
| `monastery` | 修道院 | `piety`、民心 | 无 | 降低动荡 |
| `prison` | 监狱 | `security` | 无 | 降低民心或增加支出 |
| `barracks` | 训练场 | `security`、训练能力 | 无 | 已有，补经济字段 |
| `hut_yard` | 窝棚区 | 无 | `hut: 40` | 农奴基础住房 |
| `townhouses` | 镇屋 | 无 | `townhouse: 20` | 自由农住房 |
| `manor` | 宅邸 | 少量 `gold` 或影响力 | `manor: 6` | 骑士住房 |

## building schema 扩展

每个建筑允许增加：

```json
{
  "production": {
    "wood": 28
  },
  "consumption": {
    "meat": 2
  },
  "maintenance": {
    "gold": 1
  },
  "housing": {
    "type": "workshop_home",
    "capacity": 4,
    "quality": 1.0
  },
  "employment": {
    "class_id": "artisans",
    "slots": 6,
    "productivity_bonus": 0.1
  },
  "morale_effect": 1,
  "security_effect": 0,
  "requires": [
    "grass"
  ]
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `production` | 每回合产出资源 |
| `consumption` | 每回合消耗资源 |
| `maintenance` | 每回合维护支出 |
| `housing` | 住房类型、容量、质量 |
| `employment` | 对特定阶级提供就业槽和生产力加成 |
| `morale_effect` | 对全局或地方民心影响 |
| `security_effect` | 对治安影响 |

## 推荐初始数值

```json
{
  "blacksmith": {
    "name": "铁匠铺",
    "cost": { "gold": 140, "wood": 30, "stone": 20 },
    "construction_turns": 3,
    "workforce": 10,
    "production": { "iron": 8, "tools": 2 },
    "consumption": { "wood": 4 },
    "maintenance": { "gold": 2 },
    "housing": { "type": "workshop_home", "capacity": 4, "quality": 1.0 },
    "employment": { "class_id": "artisans", "slots": 4, "productivity_bonus": 0.15 },
    "requires": ["grass"]
  }
}
```

建议完整数值：

| id | cost | 工期 | 劳力 | production | consumption | maintenance |
|---|---|---:|---:|---|---|---|
| `blacksmith` | gold 140, wood 30, stone 20 | 3 | 10 | iron 8, tools 2 | wood 4 | gold 2 |
| `quarry` | gold 90, wood 20 | 3 | 12 | stone 22 | food 2 | gold 1 |
| `lumberyard` | gold 65, wood 10 | 2 | 10 | wood 28 | food 1 | gold 1 |
| `hunting_lodge` | gold 80, wood 25 | 2 | 8 | meat 12, leather 4 | arrows/tools 可后续补 | gold 1 |
| `ranch` | gold 130, wood 45 | 4 | 12 | meat 16, leather 5 | food 5 | gold 2 |
| `handicraft_workshop` | gold 110, wood 35, stone 10 | 3 | 8 | craft_goods 10 | wood 3 | gold 1 |
| `shop` | gold 160, wood 35, stone 20 | 3 | 6 | gold 18, service_income 8 | craft_goods 3 | gold 2 |
| `tavern` | gold 150, wood 45, stone 15 | 3 | 8 | gold 15, service_income 10, morale +1 | food 4, meat 2 | gold 2 |
| `monastery` | gold 220, stone 80, wood 30 | 5 | 14 | piety 8, morale +2 | food 3 | gold 3 |
| `prison` | gold 180, stone 90, wood 20 | 4 | 10 | security +3 | food 2 | gold 3, morale -1 |
| `barracks` | gold 120, wood 35, stone 20 | 3 | 12 | security +2 | food 2 | gold 2 |
| `hut_yard` | gold 40, wood 20 | 1 | 6 | 无 | 无 | gold 0 |
| `townhouses` | gold 120, wood 45, stone 20 | 3 | 10 | 无 | 无 | gold 1 |
| `manor` | gold 300, wood 80, stone 100 | 6 | 18 | gold 5 | food 4 | gold 5 |

## 经济结算规则

`economy.py` 或 `production.py` 必须：

1. 先检查 `consumption` 是否足够。
2. 如果消耗不足：
   - 建筑本轮产出减半。
   - 追加 `TurnEvent(kind="production_shortage")`。
3. 扣除 `consumption`。
4. 增加 `production`。
5. 扣除 `maintenance`。
6. 应用 `morale_effect` 和 `security_effect`。

不要让建筑在资源不足时凭空满额生产。

## 与阶级经济的关系

建筑的 `employment` 影响 Plan 005：

- `employment.class_id` 指定受益阶级。
- `slots` 表示可提供工作岗位。
- `productivity_bonus` 加到该阶级生产力。

MVP 公式：

```text
employed = min(class.working_population, sum(slots))
effective_productivity = base_productivity + weighted_productivity_bonus
```

如果暂时不实现就业分配，至少要把 `employment` 字段写入 catalog，并在 `demographics.py` 留 TODO。

## 建筑前置与地形

MVP 地形要求：

| 建筑 | requires |
|---|---|
| 伐木场 | `forest` |
| 狩猎小屋 | `forest` |
| 采石场 | `grass`，后续改 `hills/stone` |
| 养殖场 | `grass` |
| 其他民生建筑 | `grass` |

后续如果增加山地、河流、矿脉地形，再细化 requires。

## 步骤

1. 在 `catalog.json.resources` 增加新资源。
2. 在 `catalog.json.buildings` 增加本 plan 的民生建筑。
3. 给已有 `quarry/lumberyard/barracks` 补齐 `consumption`、`maintenance`、`employment`、`security_effect`。
4. 修改 `economy.produce_resources` 或新增 `production.py`，支持 `production + consumption + maintenance`。
5. 修改 `demographics.recalculate_housing`，读取 `building.housing`。
6. 修改 `demographics.settle_class_wealth`，读取 `building.employment` 对阶级生产力的影响。
7. 为每个新建筑添加至少一个 smoke test：
   - 可建造。
   - 能产出或影响对应资源。
   - 住房型建筑会增加对应 `housing.by_type` 容量。

## 不要做的事

- 不要把民生建筑产出写死在 `economy.py`。
- 不要引入尚不存在的复杂供应链，如煤矿、马匹血统、工具耐久。
- 不要让生产在消耗不足时满额发生。
- 不要让所有住房都进入同一个无差别容量池；必须按 `housing.type` 统计。

## 验证命令

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
})
assert start.status_code == 200, start.text

catalog = client.get("/api/catalog").json()
for resource in ["iron", "meat", "leather", "craft_goods", "tools", "piety", "security", "service_income"]:
    assert resource in catalog["resources"]
for building in ["blacksmith", "hunting_lodge", "ranch", "handicraft_workshop", "shop", "tavern", "monastery", "prison", "hut_yard", "townhouses", "manor"]:
    assert building in catalog["buildings"]

client.post("/api/state/buildings", json={"building": "铁匠铺", "action": "build", "count": 1})
turn = client.post("/api/game/turn", json={"command": "巡视铁匠铺"})
assert turn.status_code == 200, turn.text
state = turn.json()["state"]
assert state["resources"]["iron"] > 0 or state["resources"]["tools"] > 0

print("OK")
PY
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
cd frontend && npm run build
```

## 完成判定

- 新资源全部存在于 `catalog.json.resources`。
- 民生建筑全部存在于 `catalog.json.buildings`。
- 建筑生产会读取 `production/consumption/maintenance`。
- 消耗不足会降低或阻断产出，并产生结构化事件。
- 建筑住房通过 `housing.type` 进入 Plan 005 的住房系统。
- 建筑就业通过 `employment` 影响对应阶级生产力，或至少以 TODO 形式保留明确接入点。
- 验证命令输出 `OK`。
