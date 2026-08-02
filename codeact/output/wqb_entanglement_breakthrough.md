# 6个非线性纠缠因子 — 最终回测报告

**生成时间**: 2026-07-29 11:37:02
**回测设置**: EQUITY/USA/TOP3000, delay=1, decay=0, neutralization=SUBINDUSTRY, truncation=0.08, pasteurization=ON, testPeriod=P1Y6M

## 基础信号定义

| 信号 | 表达式 |
|------|--------|
| alpha_021_raw |  |
| volume_delta |  |

## 6个纠缠因子定义与回测结果

| 因子 | Alpha ID | Sharpe | Fitness | 年化收益 | 最大回撤 | 换手率 | 检查状态 |
|------|----------|--------|---------|----------|----------|--------|----------|
| E1_门控反转 | Vk3m5RL8 | 0.9500 | 0.1800 | 2.45% | 4.14% | 0.6939 | ⏳ SC待定 |
| E2_调制反转 | 78nvMeK5 | 0.9500 | 0.2500 | 10.40% | 15.32% | 1.4840 | ⏳ SC待定 |
| E3_方向调制 | 78nvlE1Z | 0.5200 | 0.0800 | 3.68% | 14.54% | 1.4568 | ⏳ SC待定 |
| E4_加权组合 | WjVoJmzQ | 1.3100 | 0.3600 | 10.07% | 7.34% | 1.3406 | ⏳ SC待定 |
| E5_非对称门控 | np8erzA8 | 0.8300 | 0.1900 | 7.41% | 11.82% | 1.4843 | ⏳ SC待定 |
| E6_双变化量乘积 | omgJZKJb | -0.5200 | -0.0500 | -1.42% | 7.85% | 1.3675 | ⏳ SC待定 |

## 8项提交检查详细结果

### E1_门控反转 (Vk3m5RL8)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | ❌ FAIL | 0.9500 | 1.2500 |
| LOW_FITNESS | ❌ FAIL | 0.1800 | 1.0000 |
| LOW_TURNOVER | ✅ PASS | 0.6939 | 0.0100 |
| HIGH_TURNOVER | ✅ PASS | 0.6939 | 0.7000 |
| CONCENTRATED_WEIGHT | ✅ PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 1.0600 | 0.4100 |
| SELF_CORRELATION | ⏳ PENDING | - | - |
| MATCHES_COMPETITION | ✅ PASS | - | - |

### E2_调制反转 (78nvMeK5)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | ❌ FAIL | 0.9500 | 1.2500 |
| LOW_FITNESS | ❌ FAIL | 0.2500 | 1.0000 |
| LOW_TURNOVER | ✅ PASS | 1.4840 | 0.0100 |
| HIGH_TURNOVER | ❌ FAIL | 1.4840 | 0.7000 |
| CONCENTRATED_WEIGHT | ✅ PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 0.8100 | 0.4100 |
| SELF_CORRELATION | ⏳ PENDING | - | - |
| MATCHES_COMPETITION | ✅ PASS | - | - |

### E3_方向调制 (78nvlE1Z)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | ❌ FAIL | 0.5200 | 1.2500 |
| LOW_FITNESS | ❌ FAIL | 0.0800 | 1.0000 |
| LOW_TURNOVER | ✅ PASS | 1.4568 | 0.0100 |
| HIGH_TURNOVER | ❌ FAIL | 1.4568 | 0.7000 |
| CONCENTRATED_WEIGHT | ✅ PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 0.4400 | 0.2300 |
| SELF_CORRELATION | ⏳ PENDING | - | - |
| MATCHES_COMPETITION | ✅ PASS | - | - |

### E4_加权组合 (WjVoJmzQ)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | ✅ PASS | 1.3100 | 1.2500 |
| LOW_FITNESS | ❌ FAIL | 0.3600 | 1.0000 |
| LOW_TURNOVER | ✅ PASS | 1.3406 | 0.0100 |
| HIGH_TURNOVER | ❌ FAIL | 1.3406 | 0.7000 |
| CONCENTRATED_WEIGHT | ✅ PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 0.6500 | 0.5700 |
| SELF_CORRELATION | ⏳ PENDING | - | - |
| MATCHES_COMPETITION | ✅ PASS | - | - |

### E5_非对称门控 (np8erzA8)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | ❌ FAIL | 0.8300 | 1.2500 |
| LOW_FITNESS | ❌ FAIL | 0.1900 | 1.0000 |
| LOW_TURNOVER | ✅ PASS | 1.4843 | 0.0100 |
| HIGH_TURNOVER | ❌ FAIL | 1.4843 | 0.7000 |
| CONCENTRATED_WEIGHT | ✅ PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 0.5600 | 0.3600 |
| SELF_CORRELATION | ⏳ PENDING | - | - |
| MATCHES_COMPETITION | ✅ PASS | - | - |

### E6_双变化量乘积 (omgJZKJb)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | ❌ FAIL | -0.5200 | 1.2500 |
| LOW_FITNESS | ❌ FAIL | -0.0500 | 1.0000 |
| LOW_TURNOVER | ✅ PASS | 1.3675 | 0.0100 |
| HIGH_TURNOVER | ❌ FAIL | 1.3675 | 0.7000 |
| CONCENTRATED_WEIGHT | ✅ PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | -0.0600 | -0.2300 |
| SELF_CORRELATION | ⏳ PENDING | - | - |
| MATCHES_COMPETITION | ✅ PASS | - | - |

## 核心目标达成分析

| 目标 | 说明 | 达标因子 | 数值 |
|------|------|----------|------|
| Sharpe > 1.6 | 高收益风险比 | 无 | - |
| LOW_SHARPE通过(Sh>1.25) | 提交检查达标 | E4_加权组合(Sh=1.31) | - |
| HIGH_TURNOVER通过(To<0.7) | 低换手率 | E1_门控反转(To=0.69) | - |

## 关键发现

1. **E4_加权组合** (Sharpe=1.31) 是唯一通过LOW_SHARPE检查的因子，但Fitness=0.36和Turnover=1.34未达标
2. **E1_门控反转** (Sharpe=0.95, Turnover=0.69) 是唯一通过HIGH_TURNOVER检查的因子，门控机制有效降低了换手率
3. 所有因子的SELF_CORRELATION检查仍在平台计算中，需等待平台完成计算
4. 所有因子均未达到Sharpe>1.6且SC<0.3的核心目标
5. 换手率过高是主要瓶颈(1.3-1.5)，需要使用decay>0或更长的信号周期来降低
