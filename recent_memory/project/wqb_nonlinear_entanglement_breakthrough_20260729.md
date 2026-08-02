# WQB 6个非线性纠缠因子回测项目（2026-07-29）
## 项目背景
将alpha_021反转信号（高Sharpe）与volume_delta变化信号（低SC）正交组合，实现6种非线性纠缠结构，目标是达成Sharpe>1.6且SC<0.3的发布标准。
## 交付物
- 主脚本：wqb_entanglement_breakthrough.py（6因子回测+提交检查+报告生成，带429重试、状态库去重功能）
- 重检脚本：wqb_entanglement_recheck.py（对已有alpha_id执行提交检查重检，跳过模拟阶段）
- 结果报告：wqb_entanglement_breakthrough.md
- 状态库：wqb_state.db（alphas表按表达式+设置哈希去重，submit_checks表按alpha_id去重）
## 回测结果
| 因子 | Alpha ID | Sharpe | Fitness | 换手率 |  LOW_SHARPE | HIGH_TURNOVER | SC状态 |
|------|----------|--------|---------|--------|------------|---------------|--------|
| E1_门控反转 | Vk3m5RL8 | 0.95 | 0.18 | 0.69 | FAIL | PASS | PENDING |
| E2_调制反转 | 78nvMeK5 | 0.95 | 0.25 | 1.48 | FAIL | FAIL | PENDING |
| E3_方向调制 | 78nvlE1Z | 0.52 | 0.08 | 1.46 | FAIL | FAIL | PENDING |
| E4_加权组合 | WjVoJmzQ | 1.31 | 0.36 | 1.34 | PASS | FAIL | PENDING |
| E5_非对称门控 | np8erzA8 | 0.83 | 0.19 | 1.48 | FAIL | FAIL | PENDING |
| E6_双变化量乘积 | omgJZKJb | -0.52 | -0.05 | 1.37 | FAIL | FAIL | PENDING |
## 关键结论
1. E4_加权组合是唯一通过LOW_SHARPE(>1.25)的因子，E1_门控反转是唯一通过HIGH_TURNOVER(<0.7)的因子
2. 所有因子的SELF_CORRELATION字段在免费账号下平台持续PENDING，不会自动计算
3. 未达成核心目标，换手率过高(1.3-1.5)是当前主要瓶颈
