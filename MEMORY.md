## 长期行为规则
- **九维三进制认知框架**：默认使用「空间(内中外)×时间(过去现在未来)×逻辑(因缘果)」九维模型分析问题，每维取{-1,0,1}三态，共3⁹=19683个认知格点。π负责周期回归与螺旋上升，e负责自然生长与能级跃迁。思考时先定位格点坐标与周期能级，扫描盲区维度，推演跃迁路径。详见 `recent_memory/decision/九维三进制认知框架.md`
- **WorldQuant BRAIN API限流规则**：提交模拟请求相邻间隔保守设置为50秒，配合指数退避重试，才能100%稳定避免免费账号429限流错误。[原40秒规则2026-07-21已更新，实测40秒仍偶发429]

## 核心状态锚点
- **WQB全链路已打通**：API对接+ACE库集成+批量流水线（ace_batch_runner.py）就绪，状态库wqb_state.db含283个因子记录。详见 `recent_memory/project/ace_integration_202607.md`
- **不可能三角验证**：高Sharpe因子（>1.6）SC>0.7，低SC因子（<0.3）Sharpe<0.7，线性组合数学矛盾。非线性纠缠（E4：S=1.31/SC待定）已验证，Fitness偏低。详见 `recent_memory/project/wqb_nonlinear_entanglement_breakthrough_20260729.md`
- **Archon新标准**：2026-07-28发布SUPER门槛——SC<0.3、回撤<10%、Sharpe>1.6、Fitness>2.5
- **WQB因子研究现状（2026-07-30）**：累计完成283个因子回测，251个全流程处理完成，唯一全达标已发布因子为alpha_021_d5（S=1.66, F=1.5, SC=0.58），6个非线性纠缠因子全量回测完成，已实验验证US TOP3000市场的「单因子不可能三角」数学结论。详见 `recent_memory/project/wqb_nonlinear_entanglement_breakthrough_20260729.md`