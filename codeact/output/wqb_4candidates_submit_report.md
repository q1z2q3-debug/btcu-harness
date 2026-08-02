# WQB 候选因子提交检查与发布报告

**检查时间**: 2026-07-25 00:35:53
**检查因子数**: 4
**通过全部检查**: 0 个
**正式提交成功**: 0 个

## 汇总结果

| # | 因子名称 | Alpha ID | Sharpe | Fitness | 换手率 | 自相关性 | 检查状态 | 正式提交 |
|---|---------|----------|--------|---------|--------|----------|----------|----------|
| 1 | alpha_021_d1_raw | `E5eE3Zp1` | 1.73 | 1.22 | 0.4034 | 0.9534 | ❌ FAIL | - |
| 2 | alpha_021_d3 | `E5eEALEL` | 1.69 | 1.42 | 0.2719 | 0.9901 | ❌ FAIL | - |
| 3 | alpha_021_d5 | `O0xZv69J` | 1.66 | 1.50 | 0.2261 | N/A | ❌ FAIL | - |
| 4 | combo_d5_vol20_w9505 | `pwKl0XoX` | 1.58 | 1.23 | 0.1791 | 0.8295 | ❌ FAIL | - |

## 8项检查详细结果

### 1. alpha_021_d1_raw (`E5eE3Zp1`)

| 检查项 | 状态 | 数值 | 阈值 | 说明 |
|--------|------|------|------|------|
| LOW_SHARPE | ✅ PASS | 1.73 | 1.25 | Sharpe ≥ 1.25 |
| LOW_FITNESS | ✅ PASS | 1.22 | 1.0 | Fitness ≥ 1.0 |
| LOW_TURNOVER | ✅ PASS | 0.4034 | 0.01 | 换手率 ≥ 0.01 |
| HIGH_TURNOVER | ✅ PASS | 0.4034 | 0.7 | 换手率 ≤ 0.7 |
| CONCENTRATED_WEIGHT | ✅ PASS | - | - | 权重集中度检查 |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 1.18 | 0.75 | 子宇宙Sharpe检查 |
| SELF_CORRELATION | ❌ FAIL | 0.9534 | 0.7 | 自相关性 ≤ 0.7 |
| MATCHES_COMPETITION | ✅ PASS | - | - | 竞赛重复检查 |

- **检查时间**: 2026-07-25T00:31:57
- **数据来源**: 实时API检查

### 2. alpha_021_d3 (`E5eEALEL`)

| 检查项 | 状态 | 数值 | 阈值 | 说明 |
|--------|------|------|------|------|
| LOW_SHARPE | ✅ PASS | 1.69 | 1.25 | Sharpe ≥ 1.25 |
| LOW_FITNESS | ✅ PASS | 1.42 | 1.0 | Fitness ≥ 1.0 |
| LOW_TURNOVER | ✅ PASS | 0.2719 | 0.01 | 换手率 ≥ 0.01 |
| HIGH_TURNOVER | ✅ PASS | 0.2719 | 0.7 | 换手率 ≤ 0.7 |
| CONCENTRATED_WEIGHT | ✅ PASS | - | - | 权重集中度检查 |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 1.13 | 0.73 | 子宇宙Sharpe检查 |
| SELF_CORRELATION | ❌ FAIL | 0.9901 | 0.7 | 自相关性 ≤ 0.7 |
| MATCHES_COMPETITION | ✅ PASS | - | - | 竞赛重复检查 |

- **检查时间**: 2026-07-25T00:32:49
- **数据来源**: 实时API检查

### 3. alpha_021_d5 (`O0xZv69J`)

| 检查项 | 状态 | 数值 | 阈值 | 说明 |
|--------|------|------|------|------|
| LOW_SHARPE | N/A | - | - | Sharpe ≥ 1.25 |
| LOW_FITNESS | N/A | - | - | Fitness ≥ 1.0 |
| LOW_TURNOVER | N/A | - | - | 换手率 ≥ 0.01 |
| HIGH_TURNOVER | N/A | - | - | 换手率 ≤ 0.7 |
| CONCENTRATED_WEIGHT | N/A | - | - | 权重集中度检查 |
| LOW_SUB_UNIVERSE_SHARPE | N/A | - | - | 子宇宙Sharpe检查 |
| SELF_CORRELATION | N/A | - | - | 自相关性 ≤ 0.7 |
| MATCHES_COMPETITION | N/A | - | - | 竞赛重复检查 |

- **检查时间**: 2026-07-25T00:35:01
- **数据来源**: 实时API检查

### 4. combo_d5_vol20_w9505 (`pwKl0XoX`)

| 检查项 | 状态 | 数值 | 阈值 | 说明 |
|--------|------|------|------|------|
| LOW_SHARPE | ✅ PASS | 1.58 | 1.25 | Sharpe ≥ 1.25 |
| LOW_FITNESS | ✅ PASS | 1.23 | 1.0 | Fitness ≥ 1.0 |
| LOW_TURNOVER | ✅ PASS | 0.1791 | 0.01 | 换手率 ≥ 0.01 |
| HIGH_TURNOVER | ✅ PASS | 0.1791 | 0.7 | 换手率 ≤ 0.7 |
| CONCENTRATED_WEIGHT | ✅ PASS | - | - | 权重集中度检查 |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 0.86 | 0.68 | 子宇宙Sharpe检查 |
| SELF_CORRELATION | ❌ FAIL | 0.8295 | 0.7 | 自相关性 ≤ 0.7 |
| MATCHES_COMPETITION | ✅ PASS | - | - | 竞赛重复检查 |

- **检查时间**: 2026-07-25T00:35:52
- **数据来源**: 实时API检查

## 正式提交结果

本次检查中没有因子通过全部 8 项检查，未执行正式提交。

## 未通过检查的因子分析

### alpha_021_d1_raw (`E5eE3Zp1`)

**未通过的检查项**: SELF_CORRELATION

- **SELF_CORRELATION**: 数值=0.9534, 阈值=0.7

### alpha_021_d3 (`E5eEALEL`)

**未通过的检查项**: SELF_CORRELATION

- **SELF_CORRELATION**: 数值=0.9901, 阈值=0.7

### alpha_021_d5 (`O0xZv69J`)

**未通过的检查项**: ALREADY_SUBMITTED

- **ALREADY_SUBMITTED**: 数值=None, 阈值=None

### combo_d5_vol20_w9505 (`pwKl0XoX`)

**未通过的检查项**: SELF_CORRELATION

- **SELF_CORRELATION**: 数值=0.8295, 阈值=0.7

## 说明

- **提交检查通过标准**：8 项检查全部为 PASS
- **SELF_CORRELATION 阈值**：≤ 0.7
- **Sharpe 阈值**：≥ 1.25
- **Fitness 阈值**：≥ 1.0
- **检查接口**：POST /alphas/{id}/submit
- **正式提交接口**：PUT /alphas/{id}/submit
- **提交间隔**：≥ 50 秒，避免 429 限流
- **状态库去重**：同一 alpha_id 已有检查记录时直接从数据库读取，不重复调用 API
