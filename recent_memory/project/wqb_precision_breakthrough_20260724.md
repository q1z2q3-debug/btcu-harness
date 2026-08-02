# WQB精准突破因子回测项目（2026-07-24）
## 项目目标
设计并回测12个因子，精准卡在SELF_CORRELATION≤0.7且Fitness≥1.0的阈值交集区域，通过WQB平台全部8项提交检查后正式发布。
## 核心策略
用更快的衰减参数(d5/d3)降低自相关性，同时混入少量短周期波动率权重补充Fitness，平衡两个指标。
## 因子分组
1. 组1：短衰减纯alpha_021基线，共3个因子（d5/d3/d1无衰减）
2. 组2：d5基础 + 不同权重vol20组合，共4个因子
3. 组3：d3基础 + 不同权重vol20组合，共3个因子
4. 组4：条件过滤类创新因子，共2个
## 已完成结果
11个因子回测完成，4个初步达标：
- alpha_021_d5: Sharpe=1.66, Fitness=1.5, Turnover=0.2261
- alpha_021_d3: Sharpe=1.69, Fitness=1.42, Turnover=0.2719
- alpha_021_d1_raw: Sharpe=1.73, Fitness=1.22, Turnover=0.4034
- combo_d5_vol20_w9505: Sharpe=1.58, Fitness=1.23, Turnover=0.1791
剩余2个因子待回测完成后，自动执行8项提交检查，通过后正式发布。
## 产出物
- 已开发脚本路径：./codeact/scripts/wqb_precision_breakthrough.py
- 状态库路径：./codeact/output/wqb_state.db
- 结果报告路径：./codeact/output/wqb_precision_breakthrough_report.md
