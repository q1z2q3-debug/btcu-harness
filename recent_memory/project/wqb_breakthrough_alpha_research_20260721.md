# WQB跃迁Alpha因子研究进展（2026-07-21）
## 已完成工作
- 累计完成59个全新Alpha因子回测，分11个逻辑方向，完全避开传统现有因子加权微调，从底层逻辑创新
- 有效方向验证：隔夜日内分化（oi_divergence）系列表现最优，Sharpe普遍处于1.3~1.5区间
- 组合优化验证：5因子加权分散化可将Fitness最高提升至0.93（combo_5f_weighted，Sharpe=1.43，换手率0.58，均满足WQB提交门槛），距离Fitness≥1.0要求仅差0.07
- Top因子完整指标：combo_5f_weighted Train Sharpe=1.55, Test Sharpe=1.19，自相关系数0.65已满足≤0.7要求，子样本表现稳定
## 已验证有效结论
1. 纯动量加速度类因子在美股USA/TOP3000池表现差，普遍Sharpe为负，无实用价值
2. 极端反转叠加放量加权是稳定获取正收益的低换手方向
3. 多周期隔夜日内分化因子等权组合可得到Sharpe≥1.6的高收益表现
## 后续待完成项
- 微调combo_5f_weighted的权重分布，进一步提升Fitness突破1.0阈值
- 生成codeact/output/wqb_breakthrough_report.md完整跃迁因子研究报告
- 完成符合所有WQB平台检查要求的合格因子正式提交