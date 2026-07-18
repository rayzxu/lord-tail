# Hermes Scenario Matrix Report

- created_at: `2026-07-18T01:03:51`
- backend_url: `http://127.0.0.1:8000`
- hermes_url: `http://127.0.0.1:8643`
- total_cases: `17`
- correct_cases: `0`
- incorrect_cases: `17`

| Case | Category | API Correct | Run Completed | Missing APIs | Unexpected APIs | Error APIs |
|---|---|---:|---:|---|---|---|
| `daily_build_farm` 建造：开垦农田 | `daily` | `False` | `True` | `POST /api/agent/events` | `-` | `-` |
| `daily_population` 人口：流民/人口变化 | `daily` | `False` | `False` | `POST /api/state/population, POST /api/state/morale, POST /api/agent/events` | `-` | `-` |
| `daily_economy` 经济：资源变化 | `daily` | `False` | `False` | `POST /api/state/resources, POST /api/agent/events` | `-` | `-` |
| `daily_talent` 角色天赋：利用既有天赋 | `daily` | `False` | `False` | `POST /api/agent/events` | `-` | `-` |
| `daily_weather_season` 天气季节 | `daily` | `False` | `False` | `POST /api/agent/events` | `-` | `-` |
| `daily_food_shortage` 缺粮 | `daily` | `False` | `False` | `POST /api/state/resources, POST /api/state/morale, POST /api/agent/events` | `-` | `-` |
| `daily_plague` 瘟疫 | `daily` | `False` | `False` | `POST /api/state/population, POST /api/state/morale, POST /api/agent/events` | `-` | `-` |
| `daily_fire` 火灾 | `daily` | `False` | `False` | `POST /api/state/resources, POST /api/state/morale, POST /api/agent/events` | `-` | `-` |
| `daily_tax` 征税 | `daily` | `False` | `False` | `POST /api/state/resources, POST /api/state/morale, POST /api/agent/events` | `-` | `-` |
| `daily_conscription` 征兵 | `daily` | `False` | `False` | `POST /api/state/army, POST /api/state/population, POST /api/agent/events` | `-` | `-` |
| `daily_caravan` 商队 | `daily` | `False` | `False` | `POST /api/state/resources, POST /api/state/diplomacy, POST /api/agent/events` | `-` | `-` |
| `daily_statue` 建造雕像 | `daily` | `False` | `False` | `POST /api/agent/events` | `-` | `-` |
| `diplomacy_positive` 外交关系：正向 | `diplomacy` | `False` | `False` | `POST /api/state/diplomacy, POST /api/agent/events` | `-` | `-` |
| `diplomacy_negative` 外交关系：逆向 | `diplomacy` | `False` | `False` | `POST /api/state/diplomacy, POST /api/agent/events` | `-` | `-` |
| `battle_archers_vs_infantry` 战斗：弓兵集群 vs 3 步兵 | `battle` | `False` | `False` | `POST /api/agent/events` | `-` | `-` |
| `battle_infantry_vs_infantry` 战斗：步兵集群 vs 3 步兵 | `battle` | `False` | `False` | `POST /api/agent/events` | `-` | `-` |
| `battle_cavalry_vs_infantry` 战斗：骑兵集群 vs 3 步兵 | `battle` | `False` | `False` | `POST /api/agent/events` | `-` | `-` |

Full prompts, Hermes events, backend audit logs, inputs and outputs are in the sibling JSON file.