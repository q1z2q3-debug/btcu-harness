# WQB因子自相关性优化项目进展（2026-07-22）
## 目标
优化因子降低SELF_CORRELATION自相关性至平台阈值≤0.7以下，同时保持Sharpe≥1.25、Fitness≥1.0，产出首个通过所有8项平台提交检查的正式发布因子。

## 核心诊断结论
通过对8个已有因子的提交检查测试，确认**vol120（120日长周期波动率）是高自相关性的唯一核心来源**：
- 含vol120权重≥20%的组合因子SelfCorr普遍在0.90~0.97区间，远超0.7阈值
- 基线最优因子combo_d10_vol120_w8020：Sharpe=2.24、Fitness=1.34，7/8项检查通过，仅SELF_CORRELATION=0.9687失败
- 次优因子combo_raw_vol120_w7030_decay10：Sharpe=1.99、Fitness=1.25，7/8项检查通过，仅SELF_CORRELATION=0.9183失败

## 已完成成果
1. 开发完成专用脚本 `wqb_submission_optimizer.py`，新增全链路提交检查接口支持，适配WQB API特殊行为：
   - POST /alphas/{id}/submit 返回201表示全量检查通过、403表示检查未通过，响应体中均携带完整checks结果
2. 第一批10个优先级最高的优化因子（vol20/vol60替换vol120、降低vol权重、波动率差分变体）已提交回测，7个完成验证，其中5个满足Sharpe≥1.25且Fitness≥1.0：
   - combo_d10_vol20_w8020：Sharpe=2.13, Fitness=1.35
   - combo_d10_vol20_w9010：Sharpe=2.01, Fitness=1.21
   - combo_d10_vol120_w9010：Sharpe=2.02, Fitness=1.23
   - combo_d10_vol60_w7525：Sharpe=1.96, Fitness=1.28
   - combo_d10_vol120_w9505：Sharpe=1.83, Fitness=1.08
3. 验证API限流规则：免费账号提交间隔必须≥50秒，40秒间隔仍会偶发429错误，配合指数退避重试可完全避免限流。

## 下一步计划
对上述5个候选因子执行提交检查，验证自相关性优化效果，预期可将SelfCorr降至0.75以下，接近达标阈值。
