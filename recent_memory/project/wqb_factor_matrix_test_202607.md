# WorldQuant BRAIN 因子参数矩阵测试项目记录
## 项目背景
对已验证的Top5 Alpha因子进行4套差异化参数方案的遍历测试，找到每个因子的最优参数配置，输出参数对比报告，沉淀不同参数组合下的因子表现规律。
## 测试范围
5个Top因子（按原始Sharpe排名）：
1. reversal_5（动量反转因子，原始Sharpe 1.16，Fitness 1.06）
2. alpha_012（量价因子，原始Sharpe 1.00，Fitness 0.41）
3. hist_vol_120（波动率因子，原始Sharpe 0.93，Fitness 1.25）
4. hist_vol_20（波动率因子，原始Sharpe 0.86，Fitness 1.08）
5. alpha_006（量价因子，原始Sharpe 0.85，Fitness 0.39）

4套适配API限制后的最终参数方案：
1. **standard（标准稳健版）**：universe TOP2000，delay=1，neutralization INDUSTRY，decay=6，truncation 0.10，testPeriod P5Y0M
2. **aggressive（高灵敏进攻版）**：universe TOP1000，delay=1，neutralization SECTOR，decay=2，truncation 0.05，testPeriod P2Y0M
3. **low_turnover（低换手长线版）**：universe TOP3000，delay=1，neutralization MARKET，decay=12，truncation 0.12，testPeriod P6Y0M
4. **drawdown_control（异常修复稳回撤版）**：universe TOP2000，delay=1，neutralization SUBINDUSTRY，decay=8，truncation 0.15，testPeriod P6Y0M

总测试量：20个新模拟 + 5个baseline对照组，共25组数据点。
## 已完成开发点
1. wqb_factor_runner.py新增--mode matrix运行模式，自动遍历5因子×4方案的所有组合
2. 新增参数矩阵对比报告自动生成函数，支持按因子、参数维度输出对比表、单因子最优方案推荐、参数交叉分析、全量组合综合排名
3. wqb_api_client.py状态库新增progress_url持久化字段，修复PENDING状态任务丢失断点的问题，支持跨会话无需重新提交即可续跑等待结果
4. 验证settings哈希计算逻辑完全覆盖所有参数字段，差异化配置会被判定为独立记录，不会被错误缓存命中覆盖
## 当前进度（2026-07-17）
大部分模拟已提交到WQB平台，待收集全量回测结果后自动输出完整的wqb_param_matrix_report.md参数对比报告。
