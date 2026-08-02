# WQB SC03 优化回测 — 12因子优化设计与回测报告（B组）

**生成时间**: 2026-07-28 05:44:45
**回测设置**: EQUITY/USA/TOP3000, delay=1, decay=0, neutralization=SUBINDUSTRY, truncation=0.08, pasteurization=ON, testPeriod=P1Y6M

**优化目标**: 保持SC<0.3为首要目标，同时追求Sharpe>0

## 总体统计

| 指标 | 数值 | 设计目标 | 达标 |
|------|------|---------|------|
| 因子总数 | 6 | — | — |
| 回测成功 | 2/6 | 6/6 | ⚠️ |
| SC < 0.3 | 2/6 | 6/6 | ⚠️ |
| Sharpe > 0 | 1/6 | 越多越好 | — |
| Sharpe > 1.6 | 0/6 | — | — |
| Sharpe > 0.5 候选 | 0/6 | — | — |
| Fitness > 2.5 | 0/6 | — | — |
| 回撤 < 10% | 0/6 | — | — |

## 因子回测结果明细

| 因子 | 设计思路 | Alpha ID | Sharpe | Fitness | 年化收益 | 最大回撤 | 换手率 | 自相关(SC) | SC<0.3? | Sharpe>0? |
|------|---------|----------|--------|---------|---------|---------|--------|-----------|---------|----------|
| B7_argmax_pos | 20日最高价位置 — 值越大越接近新高(0=今天,19=20天前) | FAILED | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| B8_argmin_pos | 20日最低价位置 — 值越大越接近新低 | FAILED | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| B9_argmax_delta | 5日argmax位置变化 — 最近高点位置的变化趋势 | FAILED | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| B10_pv_corr_short | 5日量价相关性 — 短期量价配合程度 | gJ9rp3Jl | -0.7200 | -0.1300 | N/A | N/A | 0.74 | 0.1574 | ✅ | ❌ |
| B11_corr_delta | 5日量价相关性变化 — 量价关系趋势变化 | KPEVaEGx | 0.0500 | 0.0000 | N/A | N/A | 0.58 | 0.0889 | ✅ | ✅ |
| B12_range_delta | 1日波动区间变化 — 波动率日变化 | FAILED | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |

## SC vs Sharpe 分析

| 因子 | SC | Sharpe | 象限 |
|------|----|--------|------|
| B7_argmax_pos | N/A | N/A | 数据不足 |
| B8_argmin_pos | N/A | N/A | 数据不足 |
| B9_argmax_delta | N/A | N/A | 数据不足 |
| B10_pv_corr_short | 0.1574 | -0.7200 | 📊 SC<0.3但Sharpe≤0 (需改进信号) |
| B11_corr_delta | 0.0889 | 0.0500 | 🎯 SC<0.3 & Sharpe>0 (理想) |
| B12_range_delta | N/A | N/A | 数据不足 |

## 候选因子 (Sharpe > 0.5)

无符合条件的候选因子。

## 各因子详细检查结果

### B10_pv_corr_short

- **设计思路**: 5日量价相关性 — 短期量价配合程度
- **表达式**: `rank(ts_corr(rank(close), rank(volume), 5))`
- **Alpha ID**: gJ9rp3Jl
- **Sharpe**: -0.7200
- **Fitness**: -0.1300
- **SC**: 0.1574

| 检查项 | 结果 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | FAIL | -0.7200 | 1.2500 |
| LOW_FITNESS | FAIL | -0.1300 | 1.0000 |
| LOW_TURNOVER | PASS | 0.7353 | 0.0100 |
| HIGH_TURNOVER | FAIL | 0.7353 | 0.7000 |
| CONCENTRATED_WEIGHT | PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | FAIL | -0.4800 | -0.3100 |
| SELF_CORRELATION | PENDING | - | - |
| MATCHES_COMPETITION | PASS | - | - |
| SELF_CORRELATION | PASS | 0.1574 | 0.7000 |

### B11_corr_delta

- **设计思路**: 5日量价相关性变化 — 量价关系趋势变化
- **表达式**: `rank(ts_delta(ts_corr(rank(close), rank(volume), 10), 5))`
- **Alpha ID**: KPEVaEGx
- **Sharpe**: 0.0500
- **Fitness**: 0.0000
- **SC**: 0.0889

| 检查项 | 结果 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | FAIL | 0.0500 | 1.2500 |
| LOW_FITNESS | FAIL | 0.0000 | 1.0000 |
| LOW_TURNOVER | PASS | 0.5817 | 0.0100 |
| HIGH_TURNOVER | PASS | 0.5817 | 0.7000 |
| CONCENTRATED_WEIGHT | PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | PASS | 0.1400 | 0.0200 |
| SELF_CORRELATION | PENDING | - | - |
| MATCHES_COMPETITION | PASS | - | - |
| SELF_CORRELATION | PASS | 0.0889 | 0.7000 |

## 优化设计方法论

### 首次回测发现的问题

原版A组`rank(ts_delta(ts_rank(X, 20), 1))`结构：
- ✅ SC极低（平均0.0987），全部<0.3
- ❌ 所有Sharpe为负或接近0（最高0.06）
- 原因：1日排名变化属于高频噪声，在月频调仓下信号衰减严重

### 优化方向

**A组：延长ts_delta窗口**

| 编号 | 公式 | 设计思路 |
|------|------|---------|
| A1_close_rank_d5 | `rank(ts_delta(ts_rank(close, 20), 5))` | 5日收盘价排名变化 — 比1日版本信号更强 |
| A2_close_rank_d10 | `rank(ts_delta(ts_rank(close, 20), 10))` | 10日收盘价排名变化 — 捕捉中期趋势 |
| A3_volume_rank_d5 | `rank(ts_delta(ts_rank(volume, 20), 5))` | 5日成交量排名变化 — 量能变化信号 |
| A4_ma5_rank_d5 | `rank(ts_delta(ts_rank(ts_mean(close, 5), 20), 5))` | 5日MA5排名变化 — 平滑后的趋势变化 |
| A5_mom5_rank_d5 | `rank(ts_delta(ts_rank(ts_delta(close, 5), 20), 5))` | 5日动量排名变化 — 动量加速度 |
| A6_rank_acc_d10 | `rank(ts_sum(ts_delta(ts_rank(close, 20), 1), 10))` | 10日累计排名变化 — 累积方向信号 |

**B组：替代低SC结构**

| 编号 | 公式 | 设计思路 |
|------|------|---------|
| B7_argmax_pos | `rank(ts_argmax(close, 20))` | 20日最高价位置 — 值越大越接近新高(0=今天,19=20天前) |
| B8_argmin_pos | `rank(ts_argmin(close, 20))` | 20日最低价位置 — 值越大越接近新低 |
| B9_argmax_delta | `rank(ts_delta(ts_argmax(close, 20), 5))` | 5日argmax位置变化 — 最近高点位置的变化趋势 |
| B10_pv_corr_short | `rank(ts_corr(rank(close), rank(volume), 5))` | 5日量价相关性 — 短期量价配合程度 |
| B11_corr_delta | `rank(ts_delta(ts_corr(rank(close), rank(volume), 10), 5))` | 5日量价相关性变化 — 量价关系趋势变化 |
| B12_range_delta | `rank(ts_delta(ts_max(high, 5) - ts_min(low, 5), 1))` | 1日波动区间变化 — 波动率日变化 |
