# Hermes Scenario Matrix Report

- created_at: `2026-07-18T01:27:52`
- backend_url: `http://127.0.0.1:8000`
- hermes_url: `http://127.0.0.1:8643`
- total_cases: `2`
- correct_cases: `0`
- incorrect_cases: `2`

| Case | Category | API Correct | Run Completed | Missing APIs | Unexpected APIs | Error APIs |
|---|---|---:|---:|---|---|---|
| `daily_population` 人口：流民/人口变化 | `daily` | `False` | `False` | `POST /api/state/population, POST /api/state/morale, POST /api/agent/events` | `-` | `-` |
| `battle_cavalry_vs_infantry` 战斗：骑兵集群 vs 3 步兵 | `battle` | `False` | `False` | `POST /api/agent/events` | `-` | `-` |

Full prompts, Hermes events, backend audit logs, inputs and outputs are in the sibling JSON file.