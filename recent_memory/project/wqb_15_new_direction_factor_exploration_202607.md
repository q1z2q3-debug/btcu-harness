# WQB 15个九维新方向因子探索 2026-07-29
## 完成进度
1. 脚本开发完成：采用两阶段策略（先逐个提交因子入队列，间隔30秒避免限流，全部提交后集中并行轮询回测进度），已适配免费账号限流规则
2. 实测结果：15个因子全部尝试提交，11个成功进入队列，10个完成回测，成功率10/15
3. 回测结果：
   - 最佳因子：s3_high_low_corr，Sharpe=0.89，Fitness=0.22（高低价相关性信号）
   - 次佳因子：s2_vol_on_price_regression，Sharpe=0.69，Fitness=0.14（成交量对价格回归信号）
   - 其余8个因子表现未达预期，全部因子当前提交检查状态为PENDING，为免费账号平台后台检查异步计算特性导致，非脚本错误
4. 交付产物：
   - 脚本路径：./codeact/scripts/wqb_new_direction_breakthrough.py
   - 结果报告路径：./codeact/output/wqb_new_direction_breakthrough.md
   - 脚本已注册到codeact/index.json，所有开发任务全部完成
## 后续待处理
等待平台后台完成异步检查计算后，二次读取检查结果即可筛选达标因子。
