# WQB SC03 12因子自相关&lt;0.3突破回测项目
**生成时间**：2026-07-28
**设计目标**：以自相关SC&lt;0.3为首要目标，同时追求Sharpe&gt;1.6、Fitness&gt;2.5、回撤&lt;10%
**回测统一配置**：EQUITY/USA/TOP3000, delay=1, decay=0, neutralization=SUBINDUSTRY, truncation=0.08, pasteurization=ON, testPeriod=P1Y6M
**已完成内容**：
1. 完成12个因子设计，分A/B两组：A组6个ts_delta排名变化因子，B组6个原SUPER alpha转换的REGULAR因子
2. 交付wqb_sc03_breakthrough.py完整回测脚本，支持--group A/B/all拆分运行避免700秒沙箱超时，支持自定义提交间隔
3. A组6个因子首次全量回测成功，结果全部Sharpe为负，ts_delta排名变化类因子在P1Y6M周期表现不佳
4. 诊断出所有权限、限流、SC指标缺失问题并完成脚本适配，支持自动获取自相关指标

**当前待完成**：调整因子表达式解决2D输入shape错误问题，重新提交全部12个因子回测并收集SC&lt;0.3的达标因子
