# Alexander Live Trace Report

- created_at: `2026-07-17T23:26:16`
- backend_url: `http://127.0.0.1:8000`
- hermes_url: `http://127.0.0.1:8643`
- hermes_profile: `lord-tail-ollama-gemma4-31b`
- total_steps: `30`
- passed_steps: `24`
- failed_steps: `6`

| Step | API Correct | Expected API | Actual API | Checks |
|---|---:|---|---|---|
| `health_and_profile` | `True` | `GET /api/health, GET /health, GET /v1/skills, GET /v1/toolsets, GET /v1/capabilities` | `GET /api/health, GET /health, GET /v1/skills, GET /v1/toolsets, GET /v1/capabilities` | `{"passed": true, "has_lord_tail_skill": true, "enabled_toolsets": ["skills", "terminal"], "model": "gemma4:31b"}` |
| `start_alexander_scenario` | `True` | `POST /api/game/start` | `POST /api/game/start` | `{"passed": true, "narrative_excerpt": "第1轮｜春季｜细雨。春雨像灰色的麻布压在 黑逼堡 上，亚历山大 领主站在泥泞的城堡阳台，俯瞰正中央的领主堡垒与 E6 旁几间破旧房屋。他是男，外表肥胖，矮小，龌蹉；小眼睛里全是贪婪，性格媚上欺下；命运赐福在他身后低声作响：斯巴达血统、建筑巧匠。仆人垂着头不敢直视，卫兵把铁手套贴在胸前，敬畏与恐惧像潮气一样贴住他们的喉咙。领主的小小领地在泥水中展开，而他心里盘算的不是怜悯，是税、劳役、惩戒与如何让每一粒粮食都服从自己的印章。"}` |
| `give_large_test_budget` | `True` | `POST /api/state/resources` | `POST /api/state/resources` | `{"passed": true}` |
| `build_castle` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "领主堡垒"}` |
| `build_homes` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "村舍"}` |
| `build_farm` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "农田"}` |
| `build_lumberyard` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "伐木场"}` |
| `build_quarry` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "采石场"}` |
| `build_blacksmith` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "铁匠铺"}` |
| `build_hunting_lodge` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "狩猎小屋"}` |
| `build_ranch` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "养殖场"}` |
| `build_handicraft_workshop` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "手工作坊"}` |
| `build_shop` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "商店"}` |
| `build_tavern` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "酒馆"}` |
| `build_monastery` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "修道院"}` |
| `build_prison` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "监狱"}` |
| `build_barracks` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "训练场"}` |
| `build_wall` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "城墙"}` |
| `build_hut_yard` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "窝棚区"}` |
| `build_townhouses` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "镇屋"}` |
| `build_manor` | `True` | `POST /api/state/buildings` | `POST /api/state/buildings` | `{"passed": true, "building": "宅邸"}` |
| `train_infantry` | `False` | `POST /api/game/turn, POST /api/game/turn, POST /api/game/turn` | `POST /api/game/turn, POST /api/game/turn, POST /api/game/turn` | `{"passed": false}` |
| `train_archers` | `False` | `POST /api/game/turn, POST /api/game/turn, POST /api/game/turn, POST /api/game/turn` | `POST /api/game/turn, POST /api/game/turn, POST /api/game/turn, POST /api/game/turn` | `{"passed": false}` |
| `train_cavalry` | `False` | `POST /api/game/turn, POST /api/game/turn, POST /api/game/turn, POST /api/game/turn, POST /api/game/turn` | `POST /api/game/turn, POST /api/game/turn, POST /api/game/turn, POST /api/game/turn, POST /api/game/turn` | `{"passed": false}` |
| `decree_tax_law_and_turn_pipeline` | `True` | `POST /api/game/turn` | `POST /api/game/turn` | `{"passed": true, "event_kinds": ["prepared", "production", "tax_income", "noop", "training_noop", "unit_upkeep", "treaties_noop", "class_wealth", "births", "population_flow", "changed", "population_consumption", "maintenance", "advanced"], "laws": ["发布严苛加税法令，要求所有村舍缴纳春季泥税"], "changes": {"gold": 1353, "food": -36, "wood": 20, "stone": 22, "population": 0, "...` |
| `diplomacy_set_war` | `True` | `POST /api/state/diplomacy` | `POST /api/state/diplomacy` | `{"passed": true, "diplomacy": {"stance": "战争", "relation": -100, "treaties": [], "at_war": true}}` |
| `army_set_infantry` | `True` | `POST /api/state/army` | `POST /api/state/army` | `{"passed": true, "army": {"infantry": 20, "archers": 2, "cavalry": 2}}` |
| `real_hermes_describe_lord` | `False` | `POST /api/agent/runs, GET /api/agent/runs/{run_id}/events, GET /api/agent/runs/{run_id}` | `POST /api/agent/runs` | `{"expected_hermes_events": ["run.started", "message.delta", "run.completed"], "passed": false}` |
| `real_hermes_story_turn_with_expected_actions` | `False` | `POST /api/agent/runs, GET /api/agent/runs/{run_id}/events, GET /api/agent/runs/{run_id}` | `POST /api/agent/runs` | `{"expected_hermes_events": ["run.started", "run.completed"], "passed": false}` |
| `battle_public_api_gap` | `False` | `POST /api/state/battle or POST /api/game/battle` | `` | `{"passed": false, "needs_backend_api": true}` |

Full request/response bodies are stored in the sibling JSON file.