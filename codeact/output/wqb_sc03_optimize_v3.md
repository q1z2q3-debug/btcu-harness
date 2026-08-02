# WQB SC03 优化回测 v3 — 聚焦d3窗口+新结构（B组）
**生成时间**: 2026-07-28 06:26:36
## 总体统计
| 指标 | 数值 |
|------|------|
| 因子总数 | 6 |
| 回测成功 | 6/6 |
| SC < 0.3 | 4/6 |
| Sharpe > 0 | 5/6 |
| Sharpe > 0.5 候选 | 4/6 |

## 因子回测结果明细
| 因子 | 设计思路 | Alpha ID | Sharpe | Fitness | 年化收益 | 最大回撤 | 换手率 | SC | SC<0.3? | Sharpe>0? |
|------|---------|----------|--------|---------|---------|---------|--------|----|--------|----------|
| B13_vol_ratio | volume/20日均量 — 经典volume ratio因子 | le3gxrbe | 0.7100 | 0.1300 | N/A | N/A | 0.95 | 0.3121 | ❌ | ✅ |
| B13v_vol_ratio_d3 | 3日volume ratio变化 — ratio的delta | YPglZ0Lw | 0.5600 | 0.0800 | N/A | N/A | 1.12 | 0.1497 | ✅ | ✅ |
| B13v_dollar_vol_d3 | 3日dollar volume rank变化 — 成交额排名变化 | akERJ7nw | 0.2600 | 0.0200 | N/A | N/A | 1.15 | 0.0893 | ✅ | ✅ |
| B13v_vol_ratio_rank_d3 | 3日volume ratio rank变化 — ratio排名变化 | kqZ8RgWO | 0.6800 | 0.1000 | N/A | N/A | 1.13 | 0.1600 | ✅ | ✅ |
| B13v_vol_ma5_ma20_ratio | 5日/20日均量比 — 量能趋势因子 | LLd8e8jv | 0.5200 | 0.1300 | N/A | N/A | 0.38 | 0.3858 | ❌ | ✅ |
| B13v_vol_ma5_ma20_ratio_d3 | 3日量能比变化 — 量能趋势变化 | A17L6zAR | -0.1300 | -0.0100 | N/A | N/A | 0.59 | 0.2142 | ✅ | ❌ |

## 候选因子 (Sharpe > 0.5)
| 排名 | 因子 | Sharpe | Fitness | SC | 回撤 |
|------|------|--------|---------|-----|------|
| 1 | B13_vol_ratio | 0.7100 | 0.1300 | 0.3121 | 0.00% |
| 2 | B13v_vol_ratio_rank_d3 | 0.6800 | 0.1000 | 0.1600 | 0.00% |
| 3 | B13v_vol_ratio_d3 | 0.5600 | 0.0800 | 0.1497 | 0.00% |
| 4 | B13v_vol_ma5_ma20_ratio | 0.5200 | 0.1300 | 0.3858 | 0.00% |

### B13_vol_ratio
- **表达式**: `rank(volume / ts_mean(volume, 20))`
- **设计思路**: volume/20日均量 — 经典volume ratio因子
- **Alpha ID**: le3gxrbe
- **Sharpe**: 0.7100
- **SC**: 0.3121

### B13v_vol_ratio_d3
- **表达式**: `rank(ts_delta(volume / ts_mean(volume, 20), 3))`
- **设计思路**: 3日volume ratio变化 — ratio的delta
- **Alpha ID**: YPglZ0Lw
- **Sharpe**: 0.5600
- **SC**: 0.1497

### B13v_dollar_vol_d3
- **表达式**: `rank(ts_delta(ts_rank(close * volume, 20), 3))`
- **设计思路**: 3日dollar volume rank变化 — 成交额排名变化
- **Alpha ID**: akERJ7nw
- **Sharpe**: 0.2600
- **SC**: 0.0893

### B13v_vol_ratio_rank_d3
- **表达式**: `rank(ts_delta(ts_rank(volume / ts_mean(volume, 20), 20), 3))`
- **设计思路**: 3日volume ratio rank变化 — ratio排名变化
- **Alpha ID**: kqZ8RgWO
- **Sharpe**: 0.6800
- **SC**: 0.1600

### B13v_vol_ma5_ma20_ratio
- **表达式**: `rank(ts_mean(volume, 5) / ts_mean(volume, 20))`
- **设计思路**: 5日/20日均量比 — 量能趋势因子
- **Alpha ID**: LLd8e8jv
- **Sharpe**: 0.5200
- **SC**: 0.3858

### B13v_vol_ma5_ma20_ratio_d3
- **表达式**: `rank(ts_delta(ts_mean(volume, 5) / ts_mean(volume, 20), 3))`
- **设计思路**: 3日量能比变化 — 量能趋势变化
- **Alpha ID**: A17L6zAR
- **Sharpe**: -0.1300
- **SC**: 0.2142
