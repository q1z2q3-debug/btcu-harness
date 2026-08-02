# WQB SC03 突破回测 — 最终综合报告

**生成时间**: 2026-07-28
**回测设置**: EQUITY/USA/TOP3000, delay=1, decay=0, neutralization=SUBINDUSTRY, truncation=0.08, pasteurization=ON, testPeriod=P1Y6M

---

## 核心发现

经过三轮迭代优化（v1→v2→v3），共测试**36个因子**，成功发现**5个SC<0.3且Sharpe>0.5的双达标因子**，以及**10个SC<0.3且Sharpe>0的达标因子**。

### 关键突破

| 阶段 | 最佳因子 | Sharpe | SC | 突破 |
|------|---------|--------|-----|------|
| 原始 (12因子) | A2_volume_rank_delta | 0.06 | 0.1082 | 首次验证SC<0.3可实现 |
| v1 (扩展窗口) | A3_volume_rank_d5 | 0.25 | 0.1629 | 延长delta窗口→Sharpe转正 |
| v2 (参数扫描) | A3v_vol_rank_d3 | **0.64** | 0.1611 | 发现d3窗口为最优参数 |
| v3 (新结构) | A3v2_vol_rank10_d3 | **0.70** | 0.1558 | 10日rank窗口进一步优化 |
| v3 (新结构) | B13_vol_ratio | **0.71** | 0.3121 | volume ratio结构Sharpe最高 |

### 最终结论

**volume相关因子是以SC<0.3为首要目标时的最优选择**。volume rank的短期变化(d3窗口)既能保持低SC（~0.16），又能产生正向Sharpe（~0.70）。

---

## Top 5 双达标因子 (SC<0.3 + Sharpe>0.5)

| 排名 | 因子 | 表达式 | Sharpe | Fitness | SC | 年化收益 | 最大回撤 | 换手率 |
|------|------|--------|--------|---------|-----|---------|---------|--------|
| 1 | **B13_vol_ratio** | `rank(volume / ts_mean(volume, 20))` | **0.71** | 0.13 | 0.3121 ⚠️ | N/A | N/A | 1.91 |
| 2 | **A3v2_vol_rank10_d3** | `rank(ts_delta(ts_rank(volume, 10), 3))` | **0.70** | 0.10 | **0.1558** ✅ | N/A | N/A | 1.64 |
| 3 | **B13v_vol_ratio_rank_d3** | `rank(ts_delta(ts_rank(volume/ts_mean(volume,20), 20), 3))` | **0.68** | 0.10 | **0.1600** ✅ | N/A | N/A | 1.62 |
| 4 | **A3v_vol_rank_d3** | `rank(ts_delta(ts_rank(volume, 20), 3))` | **0.64** | 0.09 | **0.1611** ✅ | N/A | N/A | 1.59 |
| 5 | **A3v2_vol_rank30_d3** | `rank(ts_delta(ts_rank(volume, 30), 3))` | **0.57** | 0.07 | **0.1563** ✅ | N/A | N/A | 1.64 |

> ⚠️ B13_vol_ratio的SC=0.3121略高于0.3阈值，但Sharpe最高。若严格SC<0.3，则A3v2_vol_rank10_d3为最优选择。

---

## 全部达标因子 (SC<0.3 + Sharpe>0)

| 因子 | 表达式 | Sharpe | SC | 达标 |
|------|--------|--------|-----|------|
| A3v2_vol_rank10_d3 | `rank(ts_delta(ts_rank(volume,10),3))` | 0.70 | 0.1558 | ✅✅ |
| B13v_vol_ratio_rank_d3 | `rank(ts_delta(ts_rank(volume/ts_mean(volume,20),20),3))` | 0.68 | 0.1600 | ✅✅ |
| A3v_vol_rank_d3 | `rank(ts_delta(ts_rank(volume,20),3))` | 0.64 | 0.1611 | ✅✅ |
| A3v2_vol_rank30_d3 | `rank(ts_delta(ts_rank(volume,30),3))` | 0.57 | 0.1563 | ✅✅ |
| B13v_vol_ratio_d3 | `rank(ts_delta(volume/ts_mean(volume,20),3))` | 0.56 | 0.1497 | ✅✅ |
| A3_volume_rank_d5 | `rank(ts_delta(ts_rank(volume,20),5))` | 0.25 | 0.1629 | ✅ |
| B13v_dollar_vol_d3 | `rank(ts_delta(ts_rank(close*volume,20),3))` | 0.26 | 0.0893 | ✅ |
| A3v_vol_rank_d10 | `rank(ts_delta(ts_rank(volume,20),10))` | 0.26 | 0.2181 | ✅ |
| A3v_vol_rank20_d15 | `rank(ts_delta(ts_rank(volume,20),15))` | 0.11 | 0.2392 | ✅ |
| B11_corr_delta | `rank(ts_delta(ts_corr(rank(close),rank(volume),10),5))` | 0.05 | 0.0889 | ✅ |

---

## 设计方法论总结

### 核心发现

1. **volume是唯一有效的低SC信号源**：price类字段(close/open/high/low)的ts_delta结构无论窗口如何，Sharpe均为负值；只有volume的ts_delta结构能产生正Sharpe
2. **d3窗口是最优参数**：3日volume rank变化在所有窗口测试中表现最佳（Sharpe=0.64-0.70）
3. **volume ratio结构具有天然优势**：`rank(volume / ts_mean(volume, 20))` 结构Sharpe最高（0.71），但SC略超阈值（0.3121）
4. **SC与Sharpe的权衡**：volume因子在SC<0.3的约束下，Sharpe上限约为0.70；若放宽SC至0.5，可达到Sharpe>1.5（如alpha_021系）

### 验证的无效结构

| 结构 | 原因 |
|------|------|
| `ts_argmax/ts_argmin` | WQB平台不支持该算子 |
| `ts_max(high,5)-ts_min(low,5)` | WQB平台不支持ts_max/ts_min |
| price类字段ts_delta | 所有price字段(close/open/high/low)的排名变化Sharpe均≤-1.2 |
| ts_corr类(未delta) | 纯corr结构SC较高（>0.3） |
| SUPER结构(combo*indicator) | 免费账号无SUPER权限，转为REGULAR后SC大多>0.3 |

### 设计原则

1. **使用ts_delta结构降低SC**：一阶差分天然破坏时间序列自相关
2. **选择volume而非price**：volume信号在低SC约束下是唯一有效的预测变量
3. **优化delta窗口**：3日窗口优於1日（噪声）和5日以上（信号衰减）
4. **rank变换是必需的**：所有有效因子都包含rank()变换，消除量纲和极端值影响

---

## 脚本索引

| 脚本 | 用途 | 路径 |
|------|------|------|
| wqb_sc03_breakthrough.py | 原始12因子回测（A组ts_delta+SUPER转REGULAR） | `./codeact/scripts/wqb_sc03_breakthrough.py` |
| wqb_sc03_optimize.py | v1优化：扩展delta窗口+新结构（12因子） | `./codeact/scripts/wqb_sc03_optimize.py` |
| wqb_sc03_optimize_v2.py | v2优化：参数扫描（12因子） | `./codeact/scripts/wqb_sc03_optimize_v2.py` |
| wqb_sc03_optimize_v3.py | v3优化：聚焦d3+volume ratio（12因子） | `./codeact/scripts/wqb_sc03_optimize_v3.py` |

**状态库**: `wqb_state.db` — 共245个alpha记录，40个提交检查记录