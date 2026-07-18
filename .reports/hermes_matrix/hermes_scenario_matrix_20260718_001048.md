# Hermes Scenario Matrix Report

- created_at: `2026-07-18T00:10:48`
- backend_url: `http://127.0.0.1:8000`
- hermes_url: `http://127.0.0.1:8643`
- total_cases: `1`
- correct_cases: `0`
- incorrect_cases: `1`

| Case | Category | Correct | Missing APIs | Unexpected APIs | Error APIs |
|---|---|---:|---|---|---|
| `daily_weather_season` 天气季节 | `daily` | `False` | `-` | `-` | `POST /api/agent/events(422)` |

Full prompts, Hermes events, backend audit logs, inputs and outputs are in the sibling JSON file.