# WQB SC03 优化回测 v2 — 参数扫描（B组）
**生成时间**: 2026-07-28 06:06:55
**回测设置**: EQUITY/USA/TOP3000, delay=1, decay=0, neutralization=SUBINDUSTRY, truncation=0.08, pasteurization=ON, testPeriod=P1Y6M

## 总体统计
| 指标 | 数值 |
|------|------|
| 因子总数 | 6 |
| 回测成功 | 6/6 |
| SC < 0.3 | 6/6 |
| Sharpe > 0 | 0/6 |
| Sharpe > 0.5 候选 | 0/6 |

## 因子回测结果明细
| 因子 | 设计思路 | Alpha ID | Sharpe | Fitness | 年化收益 | 最大回撤 | 换手率 | SC | SC<0.3? | Sharpe>0? |
|------|---------|----------|--------|---------|---------|---------|--------|----|--------|----------|
| B11v_corr5_d5 | 5日量价corr的5日变化 — 短corr窗口 | WjVYmdxx | -0.7800 | -0.1200 | N/A | N/A | 0.77 | 0.1172 | ✅ | ❌ |
| B11v_corr15_d5 | 15日量价corr的5日变化 — 中corr窗口 | 3qeGWzoQ | -0.6200 | -0.1100 | N/A | N/A | 0.51 | 0.1153 | ✅ | ❌ |
| B11v_corr20_d5 | 20日量价corr的5日变化 — 长corr窗口 | kqZ85ZgK | -0.5200 | -0.0900 | N/A | N/A | 0.47 | 0.0664 | ✅ | ❌ |
| B11v_corr10_d10 | 10日量价corr的10日变化 — 长delta窗口 | zqRAz8aR | -0.0100 | -0.0000 | N/A | N/A | 0.48 | 0.1355 | ✅ | ❌ |
| B11v_corr10_d3 | 10日量价corr的3日变化 — 短delta窗口 | qM65ZLbv | -0.1200 | -0.0100 | N/A | N/A | 0.72 | 0.0851 | ✅ | ❌ |
| B12v_vol_delta_x_close_delta | volume rank变化 × 价格变化 — 量价双因子组合 | d5R9wY1x | -0.2100 | -0.0200 | N/A | N/A | 1.07 | 0.1154 | ✅ | ❌ |

## 各因子详细结果
### B11v_corr5_d5
- **表达式**: `rank(ts_delta(ts_corr(rank(close), rank(volume), 5), 5))`
- **设计思路**: 5日量价corr的5日变化 — 短corr窗口
- **Alpha ID**: WjVYmdxx
- **Sharpe**: -0.7800
- **SC**: 0.1172

### B11v_corr15_d5
- **表达式**: `rank(ts_delta(ts_corr(rank(close), rank(volume), 15), 5))`
- **设计思路**: 15日量价corr的5日变化 — 中corr窗口
- **Alpha ID**: 3qeGWzoQ
- **Sharpe**: -0.6200
- **SC**: 0.1153

### B11v_corr20_d5
- **表达式**: `rank(ts_delta(ts_corr(rank(close), rank(volume), 20), 5))`
- **设计思路**: 20日量价corr的5日变化 — 长corr窗口
- **Alpha ID**: kqZ85ZgK
- **Sharpe**: -0.5200
- **SC**: 0.0664

### B11v_corr10_d10
- **表达式**: `rank(ts_delta(ts_corr(rank(close), rank(volume), 10), 10))`
- **设计思路**: 10日量价corr的10日变化 — 长delta窗口
- **Alpha ID**: zqRAz8aR
- **Sharpe**: -0.0100
- **SC**: 0.1355

### B11v_corr10_d3
- **表达式**: `rank(ts_delta(ts_corr(rank(close), rank(volume), 10), 3))`
- **设计思路**: 10日量价corr的3日变化 — 短delta窗口
- **Alpha ID**: qM65ZLbv
- **Sharpe**: -0.1200
- **SC**: 0.0851

### B12v_vol_delta_x_close_delta
- **表达式**: `rank(ts_delta(ts_rank(volume, 20), 5) * rank(ts_delta(close, 5)))`
- **设计思路**: volume rank变化 × 价格变化 — 量价双因子组合
- **Alpha ID**: d5R9wY1x
- **Sharpe**: -0.2100
- **SC**: 0.1154
