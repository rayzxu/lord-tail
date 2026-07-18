# Hermes Scenario Matrix Report

- created_at: `2026-07-18T04:27:15`
- backend_url: `http://127.0.0.1:8000`
- hermes_url: `http://127.0.0.1:8643`
- total_cases: `17`
- correct_cases: `10`
- incorrect_cases: `7`

| Case | Category | API Correct | Run Completed | Missing APIs | Unexpected APIs | Error APIs |
|---|---|---:|---:|---|---|---|
| `daily_build_farm` 建造：开垦农田 | `daily` | `True` | `True` | `-` | `-` | `-` |
| `daily_population` 人口：流民/人口变化 | `daily` | `False` | `True` | `-` | `POST /api/state/resources` | `-` |
| `daily_economy` 经济：资源变化 | `daily` | `True` | `True` | `-` | `-` | `-` |
| `daily_talent` 角色天赋：利用既有天赋 | `daily` | `False` | `True` | `-` | `POST /api/state/buildings` | `-` |
| `daily_weather_season` 天气季节 | `daily` | `True` | `True` | `-` | `-` | `-` |
| `daily_food_shortage` 缺粮 | `daily` | `True` | `True` | `-` | `-` | `-` |
| `daily_plague` 瘟疫 | `daily` | `True` | `True` | `-` | `-` | `-` |
| `daily_fire` 火灾 | `daily` | `True` | `True` | `-` | `-` | `-` |
| `daily_tax` 征税 | `daily` | `True` | `True` | `-` | `-` | `-` |
| `daily_conscription` 征兵 | `daily` | `False` | `True` | `-` | `POST /api/state/resources` | `-` |
| `daily_caravan` 商队 | `daily` | `True` | `True` | `-` | `-` | `-` |
| `daily_statue` 建造雕像 | `daily` | `True` | `True` | `-` | `-` | `-` |
| `diplomacy_positive` 外交关系：正向 | `diplomacy` | `False` | `True` | `-` | `POST /api/state/resources` | `-` |
| `diplomacy_negative` 外交关系：逆向 | `diplomacy` | `True` | `True` | `-` | `-` | `-` |
| `battle_archers_vs_infantry` 战斗：弓兵集群 vs 3 步兵 | `battle` | `False` | `True` | `POST /api/agent/events` | `-` | `-` |
| `battle_infantry_vs_infantry` 战斗：步兵集群 vs 3 步兵 | `battle` | `False` | `True` | `POST /api/agent/events` | `-` | `-` |
| `battle_cavalry_vs_infantry` 战斗：骑兵集群 vs 3 步兵 | `battle` | `False` | `True` | `POST /api/agent/events` | `-` | `-` |

Full prompts, Hermes events, backend audit logs, inputs and outputs are in the sibling JSON file.