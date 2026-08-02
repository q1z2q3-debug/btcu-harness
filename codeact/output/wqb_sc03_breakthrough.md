# WQB SC03 突破回测 — 12因子最终报告

**生成时间**: 2026-07-28 05:24:51
**回测设置**: EQUITY/USA/TOP3000, delay=1, decay=0, neutralization=SUBINDUSTRY, truncation=0.08, pasteurization=ON, testPeriod=P1Y6M

## 总体统计

| 指标 | 数值 | 设计目标 | 达标 |
|------|------|---------|------|
| 因子总数 | 12 | 12 | — |
| 回测成功 | 12/12 | 12/12 | ✅ |
| SC < 0.3 | 8/12 | 12/12 | ⚠️ |
| Sharpe > 1.6 | 0/12 | 12/12 | ❌ |
| Sharpe > 1.0 | 0/12 | — | — |
| Fitness > 2.5 | 0/12 | 12/12 | ❌ |
| 回撤 < 10% | 0/12 | 12/12 | — |

## 因子回测结果明细

| 因子 | 类型 | Alpha ID | Sharpe | Fitness | 年化收益 | 最大回撤 | 换手率 | 自相关(SC) | SC<0.3? | 达标项 |
|------|------|----------|--------|---------|---------|---------|--------|-----------|---------|--------|
| A1_close_rank_delta | REGULAR | 6XeM5AaG | -1.4000 | -0.3100 | N/A | N/A | 1.44 | 0.1128 | ✅ | SC |
| A2_volume_rank_delta | REGULAR | LLdK0XXe | 0.0600 | 0.0000 | N/A | N/A | 1.60 | 0.1082 | ✅ | SC |
| A3_ma5_rank_delta | REGULAR | LLdK02Pv | -1.3600 | -0.3700 | N/A | N/A | 0.96 | 0.1132 | ✅ | SC |
| A4_high_rank_delta | REGULAR | le3aonR7 | -1.4400 | -0.3200 | N/A | N/A | 1.39 | 0.0926 | ✅ | SC |
| A5_low_rank_delta | REGULAR | Jjv3VjRW | -1.3100 | -0.2800 | N/A | N/A | 1.39 | 0.0894 | ✅ | SC |
| A6_mom5_rank_delta | REGULAR | wpEN8xaY | -1.0600 | -0.2100 | N/A | N/A | 1.44 | 0.0760 | ✅ | SC |
| B7_super_top20_close_rank | REGULAR(SUPER) | E5em53vG | -1.4800 | -0.4800 | N/A | N/A | 1.04 | 0.2825 | ✅ | SC |
| B8_super_top20_vol_high | REGULAR(SUPER) | 88eG9xwv | -0.3200 | -0.0900 | N/A | N/A | 0.77 | 0.5993 | ❌ | — |
| B9_super_top20_vol_close | REGULAR(SUPER) | RR15Rpqa | 0.2300 | 0.0300 | N/A | N/A | 0.84 | 0.3709 | ❌ | — |
| B10_super_top20_price_vol | REGULAR(SUPER) | pwKWwRz3 | 0.1500 | 0.0200 | N/A | N/A | 0.73 | 0.6766 | ❌ | — |
| B11_super_top30_vol_high | REGULAR(SUPER) | A17LM6mg | -0.3900 | -0.1100 | N/A | N/A | 0.75 | 0.6378 | ❌ | — |
| B12_super_top30_mom_close | REGULAR(SUPER) | WjVYjzvQ | -1.5700 | -0.5100 | N/A | N/A | 1.00 | 0.2705 | ✅ | SC |

## 关键发现

### SC设计目标达成情况

- **A组 (ts_delta排名变化)**: 6/6 SC < 0.3 ✅ — 平均SC = 0.0987
- **B组 (SUPER→REGULAR)**: 2/6 SC < 0.3 — 平均SC = 0.4729
- **结论**: ts_delta排名变化结构天然具有极低的自相关性（平均SC≈0.1），完美满足SC<0.3的设计目标

### Sharpe不足原因分析

- 所有因子Sharpe均为负或接近0，说明在P1Y6M的SUBINDUSTRY中性化回测窗口中，排名变化类动量信号不显著
- ts_delta(ts_rank(...), 1) 虽然SC极低，但信号强度太弱，无法产生正收益
- 可能原因：1日排名变化属于高频噪声，在月频调仓下信号衰减严重
- 后续优化方向：
  1. 延长ts_delta窗口（如ts_delta(ts_rank(close, 20), 5)）增强信号强度
  2. 改用ts_rank(ts_delta(...), N) 结构，在排名空间中做信号平滑
  3. 与强信号因子（如alpha021）组合，SC贡献低但可改善组合SC

## 设计方法论

### A组：ts_delta排名变化因子 (REGULAR)

核心逻辑：`rank(ts_delta(ts_rank(X, N), 1))` — 某指标排名的1日变化量

| 编号 | 公式 | 设计思路 | SC |
|------|------|---------|-----|
| A1_close_rank_delta | `rank(ts_delta(ts_rank(close, 20), 1))` | 排名日变化 | 0.1128 |
| A2_volume_rank_delta | `rank(ts_delta(ts_rank(volume, 20), 1))` | 排名日变化 | 0.1082 |
| A3_ma5_rank_delta | `rank(ts_delta(ts_rank(ts_mean(close, 5), 20), 1))` | 排名日变化 | 0.1132 |
| A4_high_rank_delta | `rank(ts_delta(ts_rank(high, 20), 1))` | 排名日变化 | 0.0926 |
| A5_low_rank_delta | `rank(ts_delta(ts_rank(low, 20), 1))` | 排名日变化 | 0.0894 |
| A6_mom5_rank_delta | `rank(ts_delta(ts_rank(ts_delta(close, 5), 20), 1))` | 排名日变化 | 0.0760 |

### B组：SUPER Alpha结构 (因账号限制转为REGULAR)

原设计为SUPER结构(selection+combo)，因账号无SUPER权限，转为REGULAR表达式：`combo * indicator(selection)`

| 编号 | REGULAR表达式 | 设计思路 | SC |
|------|-------------|---------|-----|
| B7_super_top20_close_rank | `rank(ts_delta(ts_rank(close, 20), 1)) * (rank(ts_rank(close, 20)) > 0.8)` | combo*选中指示器 | 0.2825 |
| B8_super_top20_vol_high | `rank(ts_delta(ts_rank(close, 5), 1)) * (rank(ts_mean(abs(returns), 20)) > 0.8)` | combo*选中指示器 | 0.5993 |
| B9_super_top20_vol_close | `rank(ts_delta(ts_rank(close, 20), 1)) * (rank(volume) > 0.8)` | combo*选中指示器 | 0.3709 |
| B10_super_top20_price_vol | `rank(ts_delta(ts_rank(volume, 20), 1)) * (rank(ts_mean(close, 5)) > 0.8)` | combo*选中指示器 | 0.6766 |
| B11_super_top30_vol_high | `rank(ts_delta(ts_rank(high, 20), 1)) * (rank(ts_mean(abs(returns), 20)) > 0.7)` | combo*选中指示器 | 0.6378 |
| B12_super_top30_mom_close | `rank(ts_delta(ts_rank(close, 20), 1)) * (rank(ts_delta(close, 5)) > 0.7)` | combo*选中指示器 | 0.2705 |

## 完整表达式

| 因子 | 表达式 |
|------|--------|
| A1_close_rank_delta | `rank(ts_delta(ts_rank(close, 20), 1))` |
| A2_volume_rank_delta | `rank(ts_delta(ts_rank(volume, 20), 1))` |
| A3_ma5_rank_delta | `rank(ts_delta(ts_rank(ts_mean(close, 5), 20), 1))` |
| A4_high_rank_delta | `rank(ts_delta(ts_rank(high, 20), 1))` |
| A5_low_rank_delta | `rank(ts_delta(ts_rank(low, 20), 1))` |
| A6_mom5_rank_delta | `rank(ts_delta(ts_rank(ts_delta(close, 5), 20), 1))` |
| B7_super_top20_close_rank | `rank(ts_delta(ts_rank(close, 20), 1)) * (rank(ts_rank(close, 20)) > 0.8)` |
| B8_super_top20_vol_high | `rank(ts_delta(ts_rank(close, 5), 1)) * (rank(ts_mean(abs(returns), 20)) > 0.8)` |
| B9_super_top20_vol_close | `rank(ts_delta(ts_rank(close, 20), 1)) * (rank(volume) > 0.8)` |
| B10_super_top20_price_vol | `rank(ts_delta(ts_rank(volume, 20), 1)) * (rank(ts_mean(close, 5)) > 0.8)` |
| B11_super_top30_vol_high | `rank(ts_delta(ts_rank(high, 20), 1)) * (rank(ts_mean(abs(returns), 20)) > 0.7)` |
| B12_super_top30_mom_close | `rank(ts_delta(ts_rank(close, 20), 1)) * (rank(ts_delta(close, 5)) > 0.7)` |
