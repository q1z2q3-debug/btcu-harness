# WQB v3 因子扩展项目（2026-07-19）
## 项目目标
新增22个FASTEXPR因子，包含4个组合验证因子、8个情绪类因子、10个Alpha101经典因子，扩展因子库覆盖范围。
## 完成结果
- 总提交因子数：22
- 成功回测：20个，2个语法错误因子（alpha_009、high_break_20）已修复kth_element命名参数问题，重新提交后验证通过。
- Top新因子排名：
  1. alpha_021（Alpha101类）：Sharpe=1.62，Fitness=1.19
  2. amihud_illiq（情绪类）：Sharpe=1.08，Fitness=0.72
  3. volume_price_diverge（情绪类）：Sharpe=1.0，Fitness=0.69
- 生成交付报告：wqb_backtest_report.md（全因子总排名）、wqb_combination_test_report.md（组合因子对比验证）
## 脚本改动
- wqb_factor_runner.py新增"v3"和"combos"两个运行模式
- 新增generate_combination_report函数生成组合对比报告
- 提交间隔调整为40秒适配平台严格限流
