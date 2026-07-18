# Battle Cavalry Hermes Battle API Test

- created_at: `2026-07-18T02:56:39`
- case: `battle_cavalry_vs_infantry_battle_api` 战斗：骑兵集群 vs 3 步兵（真实 battle API）
- run_id: `lt_run_e873ceab62464e6c83ecca0263e37871`
- hermes_run_id: `run_20ca012e3c0542d9abe2257e5ab2df43`
- run_completed: `True`
- api_correct: `True`
- duration_seconds: `347.723`

## Expected APIs

- `POST /api/state/battles/resolve`

## Actual APIs

- `POST /api/state/battles/resolve`
- `POST /api/agent/events`

## Missing APIs

- `-`

## Hermes final text

骑兵在草地上发起了猛烈的冲击，由于拥有极高的速度优势（1.8 vs 1.0），他们率先占据了主动权并率先发动攻击。

然而，虽然骑兵个体战力强大，但面对三名步兵的防线时，缺乏足够的数量支撑。尽管冲击瞬间造成了一名步兵阵亡，但由于步兵对骑兵存在一定的克制关系（乘数 1.25），在激烈的肉搏混战中，这名孤立的骑士被包围并迅速被击毙。

**战斗结算：**
- **速度与先手**：骑兵占据绝对优势 $\rightarrow$ 先手攻击。
- **克制关系**：步兵对骑兵有克制效果 $\rightarrow$ 防御端承受巨大压力。
- **伤害结果**：双方各损失 1 人（一名骑兵阵亡，一名步兵被践踏而死）。
- **士气与溃败**：由于唯一的精锐单位阵亡且损失率达 100%，军队组织度瞬间归零 $\rightarrow$ **全军溃散**。

这是一次惨痛的教训，过分依赖单兵冲击而忽视规模与克制导致了毁灭性的结果。

**建议：**
- 尽快扩充步兵规模以建立基本的防御阵线。
- 避免在缺乏掩护的情况下让少量骑兵直接冲撞步兵簇集群。

Full event stream and backend audit are in the sibling JSON file.