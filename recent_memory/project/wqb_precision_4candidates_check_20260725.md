# WQB精准突破4个候选因子提交检查结果（2026-07-25）

## 项目背景
已筛选出4个同时满足Sharpe≥1.25且Fitness≥1.0的达标候选因子，执行WQB平台标准8项提交检查，验证SELF_CORRELATION≤0.7要求，对全部通过的因子自动正式提交发布。

## 4个候选因子基础信息
| 因子名称 | Alpha ID | Sharpe | Fitness | Turnover |
|---------|----------|--------|---------|----------|
| alpha_021_d1_raw | E5eE3Zp1 | 1.73 | 1.22 | 0.4034 |
| alpha_021_d3 | E5eEALEL | 1.69 | 1.42 | 0.2719 |
| alpha_021_d5 | O0xZv69J | 1.66 | 1.50 | 0.2261 |
| combo_d5_vol20_w9505 | pwKl0XoX | 1.58 | 1.23 | 0.1791 |

## 最终检查结果
全部4个因子均未通过8项全量检查，无因子正式提交发布：
1. alpha_021_d1_raw：7项检查通过，SELF_CORRELATION=0.9534>0.7 未达标
2. alpha_021_d3：7项检查通过，SELF_CORRELATION=0.9901>0.7 未达标
3. alpha_021_d5：返回ALREADY_SUBMITTED状态，因子此前已在平台提交过
4. combo_d5_vol20_w9505：7项检查通过，SELF_CORRELATION=0.8295>0.7 未达标

所有因子除自相关性外的其余7项检查（LOW_SHARPE、LOW_FITNESS、LOW_TURNOVER、HIGH_TURNOVER、CONCENTRATED_WEIGHT、LOW_SUB_UNIVERSE_SHARPE、MATCHES_COMPETITION）全部通过。

## 交付物
- 新脚本路径：`./codeact/scripts/wqb_4candidates_submit.py`，已注册到index.json
- 结果报告路径：`./codeact/output/wqb_4candidates_submit_report.md`
- 状态库：`./codeact/output/wqb_state.db` submit_checks表已保存全部检查结果
