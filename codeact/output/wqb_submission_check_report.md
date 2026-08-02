# WQB 因子提交检查报告

**检查时间**: 2026-07-24 18:05:28
**检查因子数**: 5
**通过全部检查**: 0 个
**正式提交成功**: 0 个

## 汇总结果

| 因子名称 | Alpha ID | Sharpe | Fitness | 自相关性 | 检查状态 | 正式提交 |
|---------|----------|--------|---------|----------|----------|----------|
| combo_d10_vol20_w8020 | omg2jwZv | 2.13 | 1.35 | 0.9632 | ❌ FAIL | - |
| combo_d10_vol20_w9010 | d5RqJXYY | 2.01 | 1.21 | 0.8557 | ❌ FAIL | - |
| combo_d10_vol120_w9010 | mLVOnal6 | 2.02 | 1.23 | 0.8769 | ❌ FAIL | - |
| combo_d10_vol60_w7525 | P0OeLMaM | 1.96 | 1.28 | 0.9472 | ❌ FAIL | - |
| combo_d10_vol120_w9505 | pwK0bGx3 | 1.83 | 1.08 | 0.7697 | ❌ FAIL | - |

## 8项检查详细结果

### combo_d10_vol20_w8020 (omg2jwZv)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | ✅ PASS | 2.13 | 1.25 |
| LOW_FITNESS | ✅ PASS | 1.35 | 1.0 |
| LOW_TURNOVER | ✅ PASS | 0.4234 | 0.01 |
| HIGH_TURNOVER | ✅ PASS | 0.4234 | 0.7 |
| CONCENTRATED_WEIGHT | ✅ PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 1.22 | 0.92 |
| SELF_CORRELATION | ❌ FAIL | 0.9632 | 0.7 |
| MATCHES_COMPETITION | ✅ PASS | - | - |

### combo_d10_vol20_w9010 (d5RqJXYY)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | ✅ PASS | 2.01 | 1.25 |
| LOW_FITNESS | ✅ PASS | 1.21 | 1.0 |
| LOW_TURNOVER | ✅ PASS | 0.4473 | 0.01 |
| HIGH_TURNOVER | ✅ PASS | 0.4473 | 0.7 |
| CONCENTRATED_WEIGHT | ✅ PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 1.22 | 0.87 |
| SELF_CORRELATION | ❌ FAIL | 0.8557 | 0.7 |
| MATCHES_COMPETITION | ✅ PASS | - | - |

### combo_d10_vol120_w9010 (mLVOnal6)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | ✅ PASS | 2.02 | 1.25 |
| LOW_FITNESS | ✅ PASS | 1.23 | 1.0 |
| LOW_TURNOVER | ✅ PASS | 0.447 | 0.01 |
| HIGH_TURNOVER | ✅ PASS | 0.447 | 0.7 |
| CONCENTRATED_WEIGHT | ✅ PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 1.23 | 0.87 |
| SELF_CORRELATION | ❌ FAIL | 0.8769 | 0.7 |
| MATCHES_COMPETITION | ✅ PASS | - | - |

### combo_d10_vol60_w7525 (P0OeLMaM)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | ✅ PASS | 1.96 | 1.25 |
| LOW_FITNESS | ✅ PASS | 1.28 | 1.0 |
| LOW_TURNOVER | ✅ PASS | 0.3981 | 0.01 |
| HIGH_TURNOVER | ✅ PASS | 0.3981 | 0.7 |
| CONCENTRATED_WEIGHT | ✅ PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 1.15 | 0.85 |
| SELF_CORRELATION | ❌ FAIL | 0.9472 | 0.7 |
| MATCHES_COMPETITION | ✅ PASS | - | - |

### combo_d10_vol120_w9505 (pwK0bGx3)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | ✅ PASS | 1.83 | 1.25 |
| LOW_FITNESS | ✅ PASS | 1.08 | 1.0 |
| LOW_TURNOVER | ✅ PASS | 0.4513 | 0.01 |
| HIGH_TURNOVER | ✅ PASS | 0.4513 | 0.7 |
| CONCENTRATED_WEIGHT | ✅ PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 1.15 | 0.79 |
| SELF_CORRELATION | ❌ FAIL | 0.7697 | 0.7 |
| MATCHES_COMPETITION | ✅ PASS | - | - |

## 正式提交结果

本次检查中没有因子通过全部 8 项检查，未执行正式提交。

## 说明

- 提交检查通过标准：8 项检查全部为 PASS
- SELF_CORRELATION 阈值：≤ 0.7
- Sharpe 阈值：≥ 1.25
- Fitness 阈值：≥ 1.0
- 检查接口：POST /alphas/{id}/submit
