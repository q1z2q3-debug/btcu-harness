# WQB 跃迁因子批量提交报告

**生成时间：** 2026-07-22 01:23:19

## 一、批次概览

- **计划提交：** 28 个因子
- **已完成回测：** 28 个
- **进行中：** 0 个
- **失败：** 0 个
- **达标 (Sharpe≥1.25 & Fitness≥1.0)：** 0 个
- **通过所有提交检查：** 0 个

## 二、分类表现

### breakthrough

- 数量：5 个
- 平均 Sharpe：-0.668
- 平均 Fitness：-0.288
- 最佳因子：vol_accel_5d3d (Sharpe=-0.13)

### conditional

- 数量：5 个
- 平均 Sharpe：0.462
- 平均 Fitness：0.228
- 最佳因子：extreme_day_reversal (Sharpe=1.33)

### hybrid

- 数量：3 个
- 平均 Sharpe：-0.377
- 平均 Fitness：-0.103
- 最佳因子：intraday_vol_change (Sharpe=0.25)

### nonlinear

- 数量：4 个
- 平均 Sharpe：-0.263
- 平均 Fitness：-0.175
- 最佳因子：vol_drop_mom (Sharpe=0.43)

### overnight_intraday

- 数量：5 个
- 平均 Sharpe：0.318
- 平均 Fitness：0.106
- 最佳因子：oi_divergence_change (Sharpe=1.31)

### rank_change

- 数量：4 个
- 平均 Sharpe：-0.880
- 平均 Fitness：-0.458
- 最佳因子：volume_rank_change (Sharpe=0.01)

### vpd

- 数量：2 个
- 平均 Sharpe：-0.335
- 平均 Fitness：-0.095
- 最佳因子：vpd_accel (Sharpe=0.24)

## 三、因子详细结果

| 因子名称 | 类别 | Sharpe | Fitness | 换手率 | 年化收益 | 最大回撤 | 状态 |
|---------|------|--------|---------|--------|----------|----------|------|
| extreme_day_reversal | conditional | 1.33 | 0.76 | 0.475 | 15.40% | 10.19% | COMPLETED |
| oi_divergence_change | overnight_intraday | 1.31 | 0.45 | 0.799 | 9.64% | 6.46% | COMPLETED |
| oi_combo_change | overnight_intraday | 1.31 | 0.45 | 0.799 | 9.64% | 6.46% | COMPLETED |
| volume_spike_reversal | conditional | 1.07 | 0.48 | 0.313 | 6.38% | 6.75% | COMPLETED |
| vol_breakout_reversal | conditional | 0.66 | 0.24 | 0.447 | 6.16% | 12.93% | COMPLETED |
| overnight_momentum | overnight_intraday | 0.60 | 0.20 | 0.412 | 4.35% | 11.13% | COMPLETED |
| vol_drop_mom | nonlinear | 0.43 | 0.13 | 0.274 | 2.39% | 14.03% | COMPLETED |
| intraday_vol_change | hybrid | 0.25 | 0.04 | 0.486 | 1.28% | 13.24% | COMPLETED |
| vpd_accel | vpd | 0.24 | 0.02 | 0.964 | 0.92% | 7.96% | COMPLETED |
| volume_rank_change | rank_change | 0.01 | 0.00 | 0.596 | 0.06% | 13.78% | COMPLETED |
| vol_accel_5d3d | breakthrough | -0.13 | -0.02 | 0.353 | -0.67% | 17.18% | COMPLETED |
| vol_decrease_rate | breakthrough | -0.13 | -0.03 | 0.216 | -0.82% | 16.79% | COMPLETED |
| gap_reversal_extreme | conditional | -0.15 | -0.03 | 0.317 | -1.45% | 23.70% | COMPLETED |
| overnight_change_rate | overnight_intraday | -0.23 | -0.03 | 0.777 | -1.78% | 20.90% | COMPLETED |
| long_mom_short_vol | nonlinear | -0.27 | -0.13 | 0.160 | -3.44% | 40.97% | COMPLETED |
| mom_accel_10d5d | breakthrough | -0.50 | -0.20 | 0.278 | -4.40% | 30.83% | COMPLETED |
| mom_x_volume_rank | nonlinear | -0.56 | -0.31 | 0.185 | -5.75% | 36.21% | COMPLETED |
| high_vol_reversal | conditional | -0.60 | -0.31 | 0.116 | -3.41% | 21.35% | COMPLETED |
| gap_with_volume | hybrid | -0.64 | -0.15 | 0.469 | -2.57% | 16.47% | COMPLETED |
| mom_div_vol | nonlinear | -0.65 | -0.39 | 0.162 | -5.79% | 32.08% | COMPLETED |
| rank_vol_sync | hybrid | -0.74 | -0.20 | 0.409 | -3.13% | 20.28% | COMPLETED |
| vpd_change_5d | vpd | -0.91 | -0.21 | 0.648 | -3.45% | 25.14% | COMPLETED |
| rank_momentum_5d | rank_change | -0.91 | -0.57 | 0.234 | -9.10% | 52.78% | COMPLETED |
| price_vol_accel | breakthrough | -1.05 | -0.38 | 0.426 | -5.53% | 28.54% | COMPLETED |
| rank_accel_5d3d | rank_change | -1.29 | -0.60 | 0.455 | -9.78% | 58.22% | COMPLETED |
| return_rank_momentum | rank_change | -1.33 | -0.66 | 0.452 | -11.06% | 65.00% | COMPLETED |
| intraday_change_rate | overnight_intraday | -1.40 | -0.54 | 0.802 | -12.05% | 61.76% | COMPLETED |
| mom_accel_5d2d | breakthrough | -1.53 | -0.81 | 0.519 | -14.53% | 80.43% | COMPLETED |

## 四、提交检查结果

暂无达标因子或检查未完成。

## 七、回测设置

| 参数 | 值 |
|------|----|
| instrumentType | EQUITY |
| region | USA |
| universe | TOP3000 |
| delay | 1 |
| decay | 15 |
| neutralization | SUBINDUSTRY |
| truncation | 0.08 |
| maxTrade | ON |
| pasteurization | ON |
| testPeriod | P1Y6M |
| unitHandling | VERIFY |
| nanHandling | OFF |
| language | FASTEXPR |
| visualization | False |

---
*报告生成时间：2026-07-22 01:23:19*