# Plan 005: Medieval Demographics and Class Economy

## 目标

补强中世纪领地经济系统，把当前粗粒度的 `population / morale / gold / food` 扩展成可结算的人口结构与阶级经济。

本 plan 聚焦：

- 人口总量。
- 民心与统治力对人口流失/增长的影响。
- 领民阶级组成。
- 每个阶级的年龄组成、性别组成。
- 每个阶级的生产力、人均财富、税金、支出。
- 怀孕队列与出生率。
- 不同阶级的住房需求，以及对应住房空余对人口自然增长/迁入的影响。

## 输入

- `/Users/ray/raylab/lord-tail/backend/app/data/catalog.json`
- `/Users/ray/raylab/lord-tail/backend/app/systems/economy.py`
- `/Users/ray/raylab/lord-tail/backend/app/engine/state.py`
- `/Users/ray/raylab/lord-tail/backend/app/engine/turn.py`
- `/Users/ray/raylab/lord-tail/backend/app/engine/types.py`

如果 Plan 001、002、003、004 尚未执行，先执行它们。

## 输出文件

```text
/Users/ray/raylab/lord-tail/backend/app/systems/demographics.py
/Users/ray/raylab/lord-tail/backend/app/data/catalog.json
```

可选测试文件：

```text
/Users/ray/raylab/lord-tail/backend/tests/test_demographics_economy.py
```

如果项目暂时没有 pytest，使用本 plan 末尾的 inline smoke test。

## 设计约束

- `resources.population` 仍保留，作为 UI 和旧接口的总人口镜像。
- 真实人口结构以 `state["demographics"]` 为准。
- 每回合结束后必须把 `resources.population` 同步为 demographics 中所有阶级人口总和。
- 不要把阶级属性硬编码在 Python；阶级基础属性必须写入 `catalog.json`。
- 阶级 id 必须使用英文 snake_case，不要用中文名做逻辑 key。

## 状态 schema

在 state 中新增：

```json
{
  "demographics": {
    "classes": {
      "serfs": {
        "population": 58,
        "wealth_per_capita": 6.0,
        "morale": 48,
        "age": {
          "children": 16,
          "working": 36,
          "elder": 6
        },
        "sex": {
          "male": 29,
          "female": 29
        },
        "pregnancy": {
          "month_1": 0,
          "month_2": 0,
          "month_3": 0,
          "month_4": 0,
          "month_5": 0,
          "month_6": 0,
          "month_7": 0,
          "month_8": 0,
          "month_9": 0,
          "month_10": 0
        }
      }
    },
    "housing": {
      "by_type": {
        "hut": {
          "capacity": 70,
          "occupied": 58,
          "vacant": 12
        },
        "townhouse": {
          "capacity": 30,
          "occupied": 24,
          "vacant": 6
        },
        "workshop_home": {
          "capacity": 20,
          "occupied": 15,
          "vacant": 5
        },
        "manor": {
          "capacity": 6,
          "occupied": 3,
          "vacant": 3
        }
      },
      "capacity": 126,
      "occupied": 100,
      "vacant": 26
    }
  }
}
```

字段要求：

| 字段 | 说明 |
|---|---|
| `population` | 该阶级当前人口 |
| `wealth_per_capita` | 该阶级人均财富 |
| `morale` | 阶级局部民心；初期可等于全局民心 |
| `age.children` | 未成年人口 |
| `age.working` | 劳动年龄人口 |
| `age.elder` | 老年人口 |
| `sex.male` | 男性人口 |
| `sex.female` | 女性人口 |
| `pregnancy.month_1..month_10` | 1-10 月龄孕妇数量 |
| `housing.by_type` | 按住房类型统计容量、占用、空余 |
| `housing.capacity` | 所有住房类型总容量 |
| `housing.occupied` | 所有住房类型当前占用 |
| `housing.vacant` | 所有住房类型空余 |

## catalog 扩展

在 `/Users/ray/raylab/lord-tail/backend/app/data/catalog.json` 增加：

```json
{
  "population_classes": {
    "serfs": {
      "name": "农奴",
      "description": "依附土地的基础农业人口，产粮稳定但财富较低。",
      "initial_population": 58,
      "productivity": 1.0,
      "wealth_per_capita": 6.0,
      "tax": 0.8,
      "expense": 0.4,
      "class_requirement": 25,
      "housing_types": [
        "hut",
        "open_land_shelter"
      ],
      "can_self_build_shelter": true,
      "annual_birth_rate": 0.035,
      "age_ratio": {
        "children": 0.28,
        "working": 0.62,
        "elder": 0.10
      },
      "sex_ratio": {
        "male": 0.50,
        "female": 0.50
      }
    }
  }
}
```

## 推荐阶级设定

MVP 使用 5 个阶级：

| id | 中文名 | 初始人口 | 生产力 | 人均财富 | 税金 | 支出 | 阶级要求 | 年出生率 | 住房需求 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `serfs` | 农奴 | 58 | 1.0 | 6.0 | 0.8 | 0.4 | 25 | 0.035 | `hut`，不足时可用 `open_land_shelter` |
| `free_peasants` | 自由农 | 24 | 1.3 | 10.0 | 1.1 | 0.7 | 35 | 0.032 | `townhouse` |
| `artisans` | 工匠 | 10 | 1.8 | 18.0 | 1.8 | 1.2 | 45 | 0.026 | `workshop_home` |
| `merchants` | 商贾 | 5 | 2.4 | 35.0 | 3.0 | 2.2 | 55 | 0.020 | `workshop_home` 或 `shop_home` |
| `minor_nobles` | 骑士 | 3 | 0.6 | 80.0 | 4.0 | 5.0 | 70 | 0.014 | `manor` |

年龄和性别默认比例：

```json
{
  "age_ratio": {
    "children": 0.28,
    "working": 0.62,
    "elder": 0.10
  },
  "sex_ratio": {
    "male": 0.50,
    "female": 0.50
  }
}
```

可按阶级微调：

- `minor_nobles.children = 0.20`、`working = 0.65`、`elder = 0.15`
- `merchants.working = 0.70`
- 其他阶级使用默认比例即可。

## 经济公式

每个阶级每回合结算：

```text
new_wealth_per_capita = wealth_per_capita + productivity - tax - expense
class_tax_income = population * tax
class_expense_total = population * expense
class_production_value = working_population * productivity
```

要求：

- `wealth_per_capita` 不得低于 `0`。
- `class_tax_income` 进入 `resources.gold`。
- `class_production_value` 可以先作为抽象财富进入 `resources.gold`，也可以按阶级配置映射到资源；MVP 统一进入 `gold`。
- 阶级税金越高，短期财政越高，但会压低阶级财富和民心。

## 怀孕与出生

每个阶级维护 1-10 月龄孕妇数量：

```json
{
  "pregnancy": {
    "month_1": 0,
    "month_2": 0,
    "month_3": 0,
    "month_4": 0,
    "month_5": 0,
    "month_6": 0,
    "month_7": 0,
    "month_8": 0,
    "month_9": 0,
    "month_10": 0
  }
}
```

每回合按“一个月”推进：

1. `month_10` 的孕妇在本回合生产。
2. `month_9 -> month_10`，依次右移。
3. 计算新增 `month_1`。

新增怀孕数量：

```text
eligible_female = max(0, female_working_age - already_pregnant)
monthly_birth_rate = annual_birth_rate / 12
new_pregnancies = floor(eligible_female * monthly_birth_rate)
```

出生人口：

```text
births = month_10
children += births
population += births
sex.male += floor(births / 2)
sex.female += births - floor(births / 2)
```

MVP 不处理婴儿死亡率；后续可加入医疗、饥荒、战争影响。

## 民心、统治力与人口流动

全局规则：

- 当 `resources.morale < resources.authority` 时，开始人口流失。
- 高民心会增加人口迁入。
- 每个阶级有 `class_requirement`，表示该阶级愿意留在领地的最低生活/秩序要求。

用户给出的意图是：

```text
人口自然增长 = 现人口 + 出生人口 + 空余房屋影响 + 民心影响
```

原始表达中“`(空余房屋/4)/(民心-阶级要求)`”会导致民心越高，迁入越低，和“高民心会增加人口”的设计目标冲突。因此本 plan 采用可执行公式：

```text
morale_surplus = max(0, class_morale - class_requirement)
housing_pull = floor((vacant_housing / 4) * (morale_surplus / 100))
outflow = floor(population * max(0, authority - class_morale) / 1000)
new_population = current_population + births + housing_pull - outflow
```

说明：

- `vacant_housing` 必须只统计该阶级接受的住房类型。
- `vacant_housing / 4` 表示每回合可吸引 空余住房容量/4 个家庭/小户单位。
- `morale_surplus / 100` 让高民心增加迁入。
- 当民心低于统治力时，`outflow` 开始为正。
- `class_morale` 初期可以等于全局 `resources.morale`，后续可由阶级财富、税负和事件独立调整。
- 农奴的 `open_land_shelter` 是特殊住房类型：当普通窝棚不足时，农奴可以在空地自建临时窝棚；该类型提供低质量容量，但会降低该阶级局部民心或增加支出。

如果必须严格复现旧表达，必须额外加测试证明“高民心增加人口”仍成立；否则不得使用除法版本。

## 阶级住房需求

在 `catalog.json` 的建筑中增加可选字段：

```json
{
  "housing": {
    "type": "townhouse",
    "capacity": 20,
    "quality": 1.0
  }
}
```

住房类型：

| housing type | 中文 | 主要服务阶级 | 说明 |
|---|---|---|---|
| `open_land_shelter` | 空地窝棚 | 农奴 | 农奴可自建的临时低质量住房，不依赖正式建筑 |
| `hut` | 窝棚 | 农奴 | 基础住房，可由窝棚区或村舍提供 |
| `townhouse` | 镇屋 | 自由农 | 稳定家庭住房，支持更高财富积累 |
| `workshop_home` | 作坊住房 | 工匠 | 与作坊绑定，兼具居住和生产空间 |
| `shop_home` | 商铺住房 | 商贾 | 与商店绑定，兼具居住和交易空间 |
| `manor` | 宅邸 | 骑士 | 高阶住房，容量少但质量高 |

阶级住房匹配规则：

```text
class_vacant_housing = sum(vacant capacity of class.housing_types)
```

农奴特殊规则：

```text
if class_id == "serfs" and class_vacant_housing == 0 and can_self_build_shelter:
    open_land_shelter_capacity += floor(available_open_land / 2)
    serf_morale -= 1
```

MVP 可以不建真实 open land 地块系统，先用固定 `available_open_land = 20`，但必须把 TODO 写清楚。

MVP 建筑住房建议：

| 建筑 | housing.type | capacity |
|---|---|---:|
| 窝棚区 | `hut` | 40 |
| 村舍 | `hut` | 60 |
| 镇屋 | `townhouse` | 20 |
| 手工作坊 | `workshop_home` | 8 |
| 铁匠铺 | `workshop_home` | 4 |
| 商店 | `shop_home` | 6 |
| 酒馆 | `shop_home` | 4 |
| 宅邸 | `manor` | 6 |
| 领主堡垒 | `manor` | 4 |

如果 `starting_buildings` 中有这些建筑，开局 housing capacity 必须正确计算。

当前 catalog 中 `村舍` 和 `领主堡垒` 不在 `buildings` 目录里，Plan 执行时必须选择一种方式：

1. 把 `castle`、`homes` 加入 `buildings` catalog，带 `housing_capacity`。
2. 或新增 `starting_housing_capacity` 配置。

推荐第 1 种，因为它让建筑统计和住房容量走同一条数据路径。

## demographics 模块

新增 `/Users/ray/raylab/lord-tail/backend/app/systems/demographics.py`，实现：

- `initialize_demographics(state)`
- `normalize_demographics(state)`
- `recalculate_housing(state)`
- `advance_pregnancy(state, context)`
- `settle_class_wealth(state, context)`
- `apply_population_flow(state, context)`
- `sync_total_population(state)`
- `run_demographics_phase(state, context)`

函数要求：

- `initialize_demographics` 开局时按 catalog 的 `population_classes` 创建人口结构。
- `normalize_demographics` 读旧存档时补齐缺失字段。
- `recalculate_housing` 根据建筑重新计算分类型住房容量。
- `advance_pregnancy` 维护 1-10 月龄孕妇队列。
- `settle_class_wealth` 计算生产力、税金、支出、人均财富。
- `apply_population_flow` 处理民心、统治力、阶级要求和空余住房导致的人口迁入/流失。
- `sync_total_population` 把 `resources.population` 同步为阶级人口总和。

## pipeline 接入

在 `/Users/ray/raylab/lord-tail/backend/app/engine/turn.py` 中新增阶段：

```text
run_demographics
```

推荐顺序：

```text
start_turn
income
player_action
construction
military
diplomacy
demographics
weather
expenditure
end_turn
```

原因：

- 建筑完成后会影响住房容量。
- 军事和外交事件可能影响民心。
- 人口变动应在粮食消耗前同步，否则本回合消耗基数不准确。

## API

新增只读接口：

```text
GET /api/demographics
```

返回：

```json
{
  "demographics": {},
  "population": 100,
  "housing": {
    "by_type": {},
    "capacity": 120,
    "occupied": 100,
    "vacant": 20
  }
}
```

不要在本 plan 增加前端编辑人口结构的写接口。Hermes 如需修改人口，继续走统一 `/api/state/population` 或后续新增统一 `/api/state/demographics`。

## 步骤

1. 在 `catalog.json` 增加 `population_classes`，使用本 plan 的 5 个阶级初始值。
2. 在 `catalog.json` 增加 `castle`、`homes` 两个建筑条目，至少包含 `name`、`description`、`housing_capacity`、`production`、`maintenance`。
3. 新增 `systems/demographics.py`。
4. 在 `engine/state.py` 的 `make_state` 中调用 `initialize_demographics(state)`。
5. 在 `load_current_state` 中调用 `normalize_demographics(state)`，兼容旧存档。
6. 在 `engine/turn.py` 中接入 `run_demographics_phase`。
7. 修改 `economy.consume_population_food`，确保它读取同步后的 `resources.population`。
8. 新增 `api/demographics.py` 或在现有 game/state router 中加入 `GET /api/demographics`。
9. 前端可以暂时不显示阶级结构；如果要显示，只在领地详情里追加只读摘要。

## 不要做的事

- 不要把阶级属性硬编码在 Python。
- 不要让 `resources.population` 和 `demographics` 长期不一致。
- 不要在本 plan 引入疾病、饥荒、战争难民、阶级晋升/降级；这些留给后续 plan。
- 不要让怀孕数量超过适龄女性数量。
- 不要让 `wealth_per_capita` 变成负数。
- 不要在公式中使用可能除以 0 或产生反向激励的民心除法。

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
state = start.json()["state"]
assert "demographics" in state
assert sum(c["population"] for c in state["demographics"]["classes"].values()) == state["resources"]["population"]
assert state["demographics"]["housing"]["capacity"] >= state["resources"]["population"]
assert "by_type" in state["demographics"]["housing"]
assert "hut" in state["demographics"]["housing"]["by_type"]

before = state["demographics"]["classes"]["serfs"]["wealth_per_capita"]
turn = client.post("/api/game/turn", json={"command": "巡视村庄"})
assert turn.status_code == 200, turn.text
state = turn.json()["state"]
after = state["demographics"]["classes"]["serfs"]["wealth_per_capita"]
assert after >= 0
assert after != before
assert sum(c["population"] for c in state["demographics"]["classes"].values()) == state["resources"]["population"]

demo = client.get("/api/demographics")
assert demo.status_code == 200, demo.text
assert "housing" in demo.json()

print("OK")
PY
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
cd frontend && npm run build
```

## 额外公式测试

允许直接 import `systems.demographics`：

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python - <<'PY'
from app.systems.demographics import calculate_housing_pull, calculate_outflow, class_vacant_housing

low = calculate_housing_pull(vacant_housing=40, class_morale=50, class_requirement=40)
high = calculate_housing_pull(vacant_housing=40, class_morale=80, class_requirement=40)
assert high > low

assert calculate_outflow(population=100, authority=60, class_morale=50) > 0
assert calculate_outflow(population=100, authority=50, class_morale=60) == 0
housing = {"by_type": {"hut": {"vacant": 10}, "manor": {"vacant": 2}}}
assert class_vacant_housing(housing, ["hut"]) == 10
assert class_vacant_housing(housing, ["manor"]) == 2

print("OK")
PY
```

## 完成判定

- `catalog.json` 中有 `population_classes`。
- 开局 state 中有完整 `demographics`。
- 每个阶级有年龄组成、性别组成、1-10 月龄孕妇数量。
- 每个阶级有明确住房类型需求。
- 住房容量按 `housing.by_type` 统计，农奴/自由农/工匠/商贾/骑士不会共享同一个无差别空余池。
- 每回合会结算阶级人均财富：
  `新人均财富 = 人均财富 + 生产力 - 税金 - 支出`。
- 每回合会推进怀孕队列和出生。
- 民心低于统治力时会产生人口流失。
- 高民心和空余房屋会带来人口增长或迁入。
- `resources.population` 始终等于阶级人口总和。
- `GET /api/demographics` 可读取人口经济摘要。
- 验证命令输出 `OK`。
