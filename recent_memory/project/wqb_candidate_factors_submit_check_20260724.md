# WQB 5个候选因子提交检查项目（2026-07-24）

## 任务背景
对状态库中预先筛选出的5个同时满足Sharpe≥1.25、Fitness≥1.0的组合候选因子执行WQB平台全量8项提交检查，验证SELF_CORRELATION≤0.7阈值要求，找到可正式公开发布的Alpha因子。

## 候选因子清单
| 因子名称 | alpha_id | Sharpe | Fitness |
|---------|----------|--------|---------|
| combo_d10_vol20_w8020 | omg2jwZv | 2.13 | 1.35 |
| combo_d10_vol20_w9010 | d5RqJXYY | 2.01 | 1.21 |
| combo_d10_vol120_w9010 | mLVOnal6 | 2.02 | 1.23 |
| combo_d10_vol60_w7525 | P0OeLMaM | 1.96 | 1.28 |
| combo_d10_vol120_w9505 | pwK0bGx3 | 1.83 | 1.08 |

## 最终检查结果
所有5个因子均通过剩余7项检查：LOW_SHARPE、LOW_FITNESS、LOW_TURNOVER、HIGH_TURNOVER、CONCENTRATED_WEIGHT、LOW_SUB_UNIVERSE_SHARPE、MATCHES_COMPETITION，全部因子唯一失败项均为SELF_CORRELATION大于0.7阈值：
- combo_d10_vol20_w8020：自相关值0.9632
- combo_d10_vol20_w9010：自相关值0.8557
- combo_d10_vol120_w9010：自相关值0.8769
- combo_d10_vol60_w7525：自相关值0.9472
- combo_d10_vol120_w9505：自相关值0.7697（为所有因子中最接近阈值的，仅超出要求9.96%）

## 产出物
1. 独立自动化脚本：codeact/scripts/wqb_submission_check.py，完整实现从状态库读因子→触发8项检查→解析结果→自动提交通过因子→生成报告全流程
2. 完整检查报告：codeact/output/wqb_submission_check_report.md，包含所有8项检查的明细数值
3. 所有结果已同步写入状态库submit_checks表持久化存储
