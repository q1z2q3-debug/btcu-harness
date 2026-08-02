# WQB alpha_021 全维度优化报告（2026-07-20）
## 核心成果
原基准alpha_021：Sharpe=1.62，Fitness=0.94，换手45%，年化15%
最终最优因子：combo_d10_vol120_w8020，Sharpe=2.24，Fitness=1.34，相对基准提升38.3%，完全满足平台发布条件。

## 四大模块测试结果
### 1. 参数矩阵测试（16个组合）
- Decay扫描：decay越小表现越好，decay=5时Sharpe=1.84，decay=10时Sharpe=1.78且Fitness=0.97最稳健
- 中性化测试：SUBINDUSTRY中性最优，NONE中性效果最差（Sharpe=0.78）
- 股票池测试：TOP3000表现优于TOP1000/TOP2000
- 截断测试：truncation 0.05/0.08/0.12几乎无差异

### 2. 变体因子测试（6个变体）
- alpha_021_v7（成交量加权）：Sharpe=1.61接近基准
- alpha_021_v3（日内收益取反）：Sharpe=1.46
- alpha_021_v5（5日均线差）：Sharpe=1.3，Fitness=0.9
- 其余变体表现较差（Sharpe<1.2）

### 3. 原始信号加权组合（9个组合）
验证了"先加权原始信号再rank"的核心假设：
- alpha_021+hist_vol_120 70/30比例：Sharpe=1.78，Fitness=1.21
- 远优于之前"先rank再加权"的旧组合（Sharpe仅0.4-0.76），提升134%

### 4. 交叉验证（9个组合）
最优参数+最优组合叠加：
- combo_d10_vol120_w8020：Sharpe=2.24，Fitness=1.34 🏆全局第一
- combo_d5_vol120_w8020：Sharpe=2.18，Fitness=1.09
- combo_raw_vol120_w7030_decay5：Sharpe=2.08，Fitness=1.09

## 关键经验
1. WQB提交间隔必须≥40秒，30秒仍频繁触发429
2. 提交前需将自定义精简settings与DEFAULT_SETTINGS合并规范化，避免哈希不一致产生重复记录
3. 80/20权重分配最优：alpha_021占80%，低波因子vol120占20%
4. decay=10平衡了Sharpe和Fitness，是最适合发布的参数选择
