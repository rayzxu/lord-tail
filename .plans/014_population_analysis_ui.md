# Plan 014: 领地居民分析页面

## 目标

在前端新增一个只读的“居民分析”页面/面板，用于展示后端已经存在的人口阶级结构和阶级经济数据。

本 plan 不修改人口结算公式，不新增人口编辑能力；只把已有数据清晰展示出来。

## 当前状态

后端已有：

- `GET /api/demographics`
  - 返回当前人口动态状态。
- `GET /api/catalog`
  - `population_classes` 中有阶级固有属性。

前端当前没有专门居民分析入口。只能看到人口总数，无法查看：

- 阶级组成。
- 每阶级男女比例。
- 年龄结构。
- 1-10 月龄孕妇。
- 生产力、税金、支出、出生率等阶级固有属性。
- 住房需求与空置情况。
- 上轮出生、迁入、流失、财富变化。

## 页面入口

在顶部功能菜单新增：

```text
居民分析
```

建议顺序：

```text
领地详情 | 居民分析 | 领主详情 | 历史 | 保存 | 读取 | 退出
```

点击后打开 modal 或 side panel。MVP 使用现有 `DetailPanel` 风格 modal 即可。

## 数据来源

### 当前人口状态

```http
GET /api/demographics
```

结构示例：

```json
{
  "demographics": {
    "classes": {
      "serfs": {
        "name": "农奴",
        "population": 58,
        "wealth_per_capita": 3,
        "morale": 70,
        "age": {
          "child": 15,
          "working": 35,
          "elder": 8
        },
        "sex": {
          "female": 30,
          "male": 28
        },
        "pregnancy": {
          "1": 0,
          "2": 0,
          "...": 0,
          "10": 0
        },
        "last_births": 0,
        "last_migration": 0,
        "last_outflow": 0,
        "last_wealth_delta": 0
      }
    },
    "housing": {
      "by_type": {},
      "total_capacity": 134,
      "total_occupied": 100,
      "total_vacant": 34
    }
  }
}
```

### 阶级固有属性

```http
GET /api/catalog
```

读取：

```json
{
  "population_classes": {
    "serfs": {
      "name": "农奴",
      "productivity": 2,
      "tax": 1,
      "expense": 1,
      "annual_birth_rate": 0.045,
      "housing_types": ["hut", "open_land_shelter"]
    }
  }
}
```

## 前端类型

修改 `frontend/src/api.ts`，新增类型：

```ts
export type PopulationClassState = {
  name: string
  population: number
  wealth_per_capita: number
  morale: number
  age: Record<'child' | 'working' | 'elder', number>
  sex: Record<'female' | 'male', number>
  pregnancy: Record<string, number>
  last_births: number
  last_migration: number
  last_outflow: number
  last_wealth_delta: number
}

export type HousingState = {
  by_type: Record<string, {
    capacity: number
    occupied: number
    vacant: number
    quality: number
  }>
  total_capacity: number
  total_occupied: number
  total_vacant: number
}

export type DemographicsResponse = {
  demographics: {
    classes: Record<string, PopulationClassState>
    housing: HousingState
    last_births: number
    last_migration: number
    last_outflow: number
    last_wealth_delta: number
  }
}

export type PopulationClassCatalog = {
  name: string
  description?: string
  productivity: number
  tax: number
  expense: number
  annual_birth_rate: number
  housing_types: string[]
  class_requirement?: number
}
```

API：

```ts
demographics: () => request<DemographicsResponse>('/demographics')
```

`api.catalog()` 当前如果已有类型不完整，需要扩展 `Catalog` 类型，至少包含：

```ts
population_classes?: Record<string, PopulationClassCatalog>
```

## UI 结构

### 总览卡片

显示：

- 总人口。
- 阶级数。
- 总住房容量。
- 已占用住房。
- 空余住房。
- 上轮出生。
- 上轮迁入。
- 上轮流失。
- 上轮财富变化。

### 阶级分析表

每行一个阶级：

| 阶级 | 人口 | 男/女 | 年龄结构 | 孕妇 | 生产力 | 人均财富 | 税金 | 支出 | 出生率 | 民心 | 住房 |
|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|

字段：

- 阶级名：`class_state.name`
- 人口：`population`
- 男/女：`sex.male / sex.female`
- 年龄结构：`child / working / elder`
- 孕妇：`sum(pregnancy values)`，并可展开显示 1-10 月龄
- 生产力：catalog `productivity`
- 人均财富：state `wealth_per_capita`
- 税金：catalog `tax`
- 支出：catalog `expense`
- 出生率：catalog `annual_birth_rate`
- 民心：state `morale`
- 住房：catalog `housing_types`

### 孕妇月龄条

MVP 可以每阶级显示：

```text
孕妇 1-10 月：0 / 0 / 1 / 0 / ...
```

后续可换成小型条形图。

### 住房分析区

按住房类型展示：

| 住房类型 | 容量 | 已住 | 空余 | 质量 |
|---|---:|---:|---:|---:|

数据来自：

```ts
demographics.housing.by_type
```

需要把 housing type 映射成人类可读中文：

```ts
const housingLabels = {
  hut: '窝棚',
  open_land_shelter: '空地自建窝棚',
  townhouse: '镇屋',
  workshop_home: '作坊住房',
  shop_home: '商铺住房',
  manor: '宅邸',
}
```

如果 catalog 后续提供 housing_types 字典，则改为读取 catalog。

## 交互

MVP：

- 打开居民分析时，前端请求：
  - `GET /api/demographics`
  - `GET /api/catalog` 如果 catalog 尚未加载
- 显示 loading。
- 请求失败时显示错误。
- 不提供编辑按钮。

可选：

- 点击阶级行展开详情。
- 点击“请 Hermes 描述此阶级”调用 `describe_item`，client_context：

```json
{
  "target_type": "population_class",
  "class_id": "serfs",
  "class_state": {},
  "class_catalog": {}
}
```

此可选项不作为 MVP 完成条件。

## 后端补充建议

当前 `GET /api/demographics` 只返回动态状态，catalog 固有属性需要前端再查 `/api/catalog`。

MVP 可以接受双请求。

如果要减少前端拼装，可以新增：

```http
GET /api/demographics/analysis
```

返回已经 merge 好的：

```json
{
  "classes": {
    "serfs": {
      "state": {},
      "catalog": {},
      "derived": {
        "pregnant_total": 0,
        "male_ratio": 0.48,
        "female_ratio": 0.52,
        "working_ratio": 0.60,
        "expected_wealth_next": 4
      }
    }
  },
  "housing": {}
}
```

但本 plan 建议先不新增后端接口，避免扩大范围。

## 派生计算

前端可以做轻量派生：

```ts
pregnantTotal = sum(Object.values(classState.pregnancy))
expectedWealthNext = wealth_per_capita + productivity - tax - expense
maleRatio = male / population
femaleRatio = female / population
workingRatio = working / population
```

注意：

- 如果 population 为 0，比例显示 `-`。
- `expectedWealthNext` 只是按当前固有属性估算，不代替后端结算。

## 文件修改

预期修改：

```text
frontend/src/api.ts
frontend/src/App.tsx
frontend/src/styles.css
```

可选新增：

```text
frontend/src/components/PopulationAnalysisPanel.tsx
```

当前项目组件都在 `App.tsx`，MVP 可以继续放在 `App.tsx`，但如果文件继续膨胀，建议拆组件。

## 测试

前端目前没有组件测试框架。本 plan 至少要求：

```bash
cd /Users/ray/raylab/lord-tail/frontend
npm run build
```

后端 smoke：

```bash
cd /Users/ray/raylab/lord-tail
curl -s http://127.0.0.1:8000/api/demographics | python -m json.tool
curl -s http://127.0.0.1:8000/api/catalog | python -m json.tool
```

如果新增 `/api/demographics/analysis`，必须补：

```text
backend/tests/test_demographics_analysis_api.py
```

## 完成判定

- 顶部菜单出现“居民分析”。
- 点击后能打开居民分析面板。
- 面板显示总人口、住房总览和阶级列表。
- 每个阶级显示：
  - 人口
  - 男/女
  - 年龄结构
  - 1-10 月龄孕妇合计或明细
  - 生产力
  - 人均财富
  - 税金
  - 支出
  - 出生率
  - 住房需求
- 页面只读，不会修改后端状态。
- `npm run build` 通过。
