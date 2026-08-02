# ACE 批量因子回测与提交检查报告

**生成时间**: 2026-07-25 00:34:54
**因子总数**: 4
**回测成功**: 4
**通过全部检查**: 0 个
**正式提交成功**: 0 个

## 汇总结果

| 因子名称 | Alpha ID | Sharpe | Fitness | 自相关性 | 检查状态 | 生产相关性 | 正式提交 |
|---------|----------|--------|---------|----------|----------|------------|----------|
| alpha_021_d1_raw | E5eE3Zp1 | 1.73 | 1.22 | 0.9534 | ❌ FAIL | — | — |
| alpha_021_d3 | E5eEALEL | 1.69 | 1.42 | 0.9901 | ❌ FAIL | — | — |
| alpha_021_d5 | O0xZv69J | None | None | None | ❌ FAIL | — | — |
| combo_d5_vol20_w9505 | pwKl0XoX | 1.58 | 1.23 | 0.8295 | ❌ FAIL | — | — |

## 8项检查详细结果

### alpha_021_d1_raw (E5eE3Zp1)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | ✅ PASS | 1.7300 | 1.2500 |
| LOW_FITNESS | ✅ PASS | 1.2200 | 1.0000 |
| LOW_TURNOVER | ✅ PASS | 0.4034 | 0.0100 |
| HIGH_TURNOVER | ✅ PASS | 0.4034 | 0.7000 |
| CONCENTRATED_WEIGHT | ✅ PASS | None | None |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 1.1800 | 0.7500 |
| SELF_CORRELATION | ❌ FAIL | 0.9534 | 0.7000 |
| MATCHES_COMPETITION | ✅ PASS | None | None |

### alpha_021_d3 (E5eEALEL)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | ✅ PASS | 1.6900 | 1.2500 |
| LOW_FITNESS | ✅ PASS | 1.4200 | 1.0000 |
| LOW_TURNOVER | ✅ PASS | 0.2719 | 0.0100 |
| HIGH_TURNOVER | ✅ PASS | 0.2719 | 0.7000 |
| CONCENTRATED_WEIGHT | ✅ PASS | None | None |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 1.1300 | 0.7300 |
| SELF_CORRELATION | ❌ FAIL | 0.9901 | 0.7000 |
| MATCHES_COMPETITION | ✅ PASS | None | None |

### alpha_021_d5 (O0xZv69J)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | N/A | - | - |
| LOW_FITNESS | N/A | - | - |
| LOW_TURNOVER | N/A | - | - |
| HIGH_TURNOVER | N/A | - | - |
| CONCENTRATED_WEIGHT | N/A | - | - |
| LOW_SUB_UNIVERSE_SHARPE | N/A | - | - |
| SELF_CORRELATION | N/A | - | - |
| MATCHES_COMPETITION | N/A | - | - |

### combo_d5_vol20_w9505 (pwKl0XoX)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | ✅ PASS | 1.5800 | 1.2500 |
| LOW_FITNESS | ✅ PASS | 1.2300 | 1.0000 |
| LOW_TURNOVER | ✅ PASS | 0.1791 | 0.0100 |
| HIGH_TURNOVER | ✅ PASS | 0.1791 | 0.7000 |
| CONCENTRATED_WEIGHT | ✅ PASS | None | None |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 0.8600 | 0.6800 |
| SELF_CORRELATION | ❌ FAIL | 0.8295 | 0.7000 |
| MATCHES_COMPETITION | ✅ PASS | None | None |

## 正式提交结果

本次检查中没有因子通过全部 8 项检查，未执行正式提交。
