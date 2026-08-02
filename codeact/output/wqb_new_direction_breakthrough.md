# WQB 新方向突破因子探索报告

**生成时间**: 2026-07-28 03:13:39
**因子总数**: 11
**回测成功**: 10
**通过全部检查**: 0 个
**正式提交成功**: 0 个

## 汇总结果

| 因子名称 | 方向 | Alpha ID | Sharpe | Fitness | 自相关 | 检查状态 | 提交 |
|---------|------|----------|--------|---------|-------|----------|------|
| c1_mom_price_ma_corr | C₁=+1 动量延续 | N1RPJ1pp | -0.17 | -0.02 | None | ⏳ PENDING | — |
| c1_mom_price_ma30_corr | C₁=+1 动量延续 | 3qe0Jr1O | 0.01 | 0.0 | None | ⏳ PENDING | — |
| c1_mom_acceleration | C₁=+1 动量延续 | 0mMPN3mv | -0.46 | -0.09 | None | ⏳ PENDING | — |
| s2_vol_price_delta_sync | S₂ 量价协同 | xAdv2lng | -0.28 | -0.04 | None | ⏳ PENDING | — |
| s2_vol_on_price_regression | S₂ 量价协同 | MPL6eNKa | 0.69 | 0.14 | None | ⏳ PENDING | — |
| t3_return_acceleration | T₃ 加速度 | 58kJ50LM | -1.21 | -0.57 | None | ⏳ PENDING | — |
| t3_mom_short_mid_sync | T₃ 加速度 | wpEoAK8x | -0.16 | -0.02 | None | ⏳ PENDING | — |
| s3_high_low_corr | S₃ 多模态交叉 | qM67GRlE | 0.89 | 0.22 | None | ⏳ PENDING | — |
| s3_price_volatility_corr | S₃ 多模态交叉 | None | N/A | N/A | N/A | N/A | — |
| c2_price_trend_volume | C₂=+1 正交组合 | 1YzW8KLQ | -0.71 | -0.17 | None | ⏳ PENDING | — |
| c2_daily_price_change_sync | C₂=+1 正交组合 | akEa0Zv5 | -0.03 | -0.0 | None | ⏳ PENDING | — |

## 按方向分组

### C₁=+1 动量延续 (3个, 通过0个)

**c1_mom_price_ma_corr**: 价格与短期均线(10日)相关性
- 表达式: `rank(ts_corr(rank(close), rank(ts_mean(close, 10)), 5))`
- Alpha ID: N1RPJ1pp | Sharpe: -0.17 | Fitness: -0.02 | 自相关: None
- 状态: PENDING

**c1_mom_price_ma30_corr**: 价格与中期均线(30日)相关性
- 表达式: `rank(ts_corr(rank(close), rank(ts_mean(close, 30)), 10))`
- Alpha ID: 3qe0Jr1O | Sharpe: 0.01 | Fitness: 0.0 | 自相关: None
- 状态: PENDING

**c1_mom_acceleration**: 动量加速度
- 表达式: `rank(ts_corr(rank(ts_delta(close, 5)), rank(ts_delta(ts_mean(close, 20), 5)), 10))`
- Alpha ID: 0mMPN3mv | Sharpe: -0.46 | Fitness: -0.09 | 自相关: None
- 状态: PENDING

### S₂ 量价协同 (2个, 通过0个)

**s2_vol_price_delta_sync**: 量价短期变化同步
- 表达式: `rank(ts_corr(rank(ts_delta(close, 3)), rank(ts_delta(volume, 3)), 5))`
- Alpha ID: xAdv2lng | Sharpe: -0.28 | Fitness: -0.04 | 自相关: None
- 状态: PENDING

**s2_vol_on_price_regression**: 成交量对价格回归
- 表达式: `rank(ts_regression(rank(ts_mean(volume, 10)), rank(ts_mean(close, 20)), 5))`
- Alpha ID: MPL6eNKa | Sharpe: 0.69 | Fitness: 0.14 | 自相关: None
- 状态: PENDING

### T₃ 加速度 (2个, 通过0个)

**t3_return_acceleration**: 收益加速度
- 表达式: `rank(ts_delta(ts_sum(returns, 5), 5))`
- Alpha ID: 58kJ50LM | Sharpe: -1.21 | Fitness: -0.57 | 自相关: None
- 状态: PENDING

**t3_mom_short_mid_sync**: 短中期动量同步
- 表达式: `rank(ts_corr(rank(ts_delta(close, 3)), rank(ts_delta(close, 10)), 5))`
- Alpha ID: wpEoAK8x | Sharpe: -0.16 | Fitness: -0.02 | 自相关: None
- 状态: PENDING

### S₃ 多模态交叉 (2个, 通过0个)

**s3_high_low_corr**: 高低价相关性(5日)
- 表达式: `rank(ts_corr(rank(high), rank(low), 5))`
- Alpha ID: qM67GRlE | Sharpe: 0.89 | Fitness: 0.22 | 自相关: None
- 状态: PENDING

**s3_price_volatility_corr**: 价格与波动率关系
- 表达式: `rank(ts_corr(rank(close), rank(ts_stddev(returns, 20)), 10))`
- Alpha ID: None | Sharpe: N/A | Fitness: N/A | 自相关: N/A
- 状态: N/A

### C₂=+1 正交组合 (2个, 通过0个)

**c2_price_trend_volume**: 价格趋势与量能相关性
- 表达式: `rank(ts_corr(rank(ts_mean(close, 5)), rank(ts_mean(volume, 20)), 5))`
- Alpha ID: 1YzW8KLQ | Sharpe: -0.71 | Fitness: -0.17 | 自相关: None
- 状态: PENDING

**c2_daily_price_change_sync**: 日间价格变化同步
- 表达式: `rank(ts_corr(rank(ts_delta(close, 1)), rank(ts_delta(open, 1)), 5))`
- Alpha ID: akEa0Zv5 | Sharpe: -0.03 | Fitness: -0.0 | 自相关: None
- 状态: PENDING

## 正式提交结果

本次检查中没有因子通过全部8项检查，未执行正式提交。

## 因子设计说明

- 完全脱离alpha_021反转信号家族
- 不使用ts_rank(roc(...))等反转信号结构
- 不使用reverse()算子
- 不使用ts_stddev(returns, N)单独作为因子
- 所有因子使用ts_delay而非shift

### 五个方向

1. **C₁=+1 动量延续**: 趋势跟踪类因子
2. **S₂ 量价协同**: 成交量与价格的复合信号
3. **T₃ 加速度**: 价格变化率的变化
4. **S₃ 多模态交叉**: 多维度价格数据交叉分析
5. **C₂=+1 正交组合**: 多信号交叉组合
