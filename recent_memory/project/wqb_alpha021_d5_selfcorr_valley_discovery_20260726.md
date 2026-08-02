# alpha_021_d5自相关低谷重大发现
## 核心发现
2026-07-26 验证完成，alpha_021_d5自相关值仅为0.5838，远低于平台0.7的发布阈值，形成以d5为中心的尖锐自相关低谷：
| 因子名称 | 自相关值 | 状态 |
|---------|---------|------|
| alpha_021_d5 | 0.5838 | ✅ 达标 |
| alpha_021_d4 | 0.7021 | ❌ 刚超标 |
| alpha_021_d6 | 0.7284 | ❌ 超标 |
| alpha_021_d7 | 0.7668 | ❌ 超标 |
| alpha_021_d1_raw | 0.9534 | ❌ 严重超标 |
| alpha_021_d3 | 0.9901 | ❌ 严重超标 |

## 测试结果
共完成11个d5周边变体因子回测：
1. combo_d5_vol20_w9703: Sharpe=1.93, Fitness=1.21，7/8项提交检查通过，仅高换手和自相关超标
2. combo_d5_vol20_w9802: Sharpe=1.98, Fitness=1.17，6/8项提交检查通过
3. combo_d5_vol20_w9901: Sharpe=1.85, Fitness=1.02，6/8项提交检查通过

## 产出物
- 最终报告路径：/app/data/所有对话/主对话/codeact/output/wqb_d5_selfcorr_breakthrough_report.md
- 3阶段处理脚本：wqb_d5_selfcorr_breakthrough.py、wqb_d5_phase2_analysis.py、wqb_d5_phase3_variants.py
- 状态库：wqb_state.db，存储全量回测数据、自相关数据、提交检查结果
