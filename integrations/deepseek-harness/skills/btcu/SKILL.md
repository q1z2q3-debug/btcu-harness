---
name: btcu
description: >-
  BTCU（Balanced Ternary Cognitive Unit）认知层使用指南：九维平衡三元状态空间
  （3^9 = 19683）与双系统快慢思维（System 1 模式库 / System 2 深思）。学会把认知
  状态编码进空间、做三元代数、导航状态空间、把冲突化为第三选择，并用
  btcu_decide 的 S1→S2 级联 + feedback 反馈学习完成"学校→内化→毕业"。
whenToUse: >-
  当需要结构化/可解释的推理，需要把问题/决策映射为认知状态，遇到 A/B 二选一
  冲突想生成第三选择，想用快路径（模式库）省 token，或想追踪自己的认知成长
  进度时。若会话运行在 btcu preset 上，btcu_* 工具已就绪；否则本技能提供框架
  与方法，工具用法可迁移到其他实现。
---

# BTCU 认知层使用指南

## 模型：三值与 19683 空间

每个认知状态是一个**九维向量**，每维取值三值之一：

| 值 | 符号 | 名称 | 含义 |
|---|---|---|---|
| -1 | T | YIN（阴） | 否定、收缩、退避 |
| 0 | 0 | EMPTY（空） | 转化、创造、等待 |
| +1 | 1 | YANG（阳） | 肯定、扩张、前进 |

九维（可随项目调整，结构固定为 9）：time, space, causality, value, relation,
action, subject, intent, cognition。

核心恒等式：**-1 + 1 = 0** —— 对立状态相遇进入 EMPTY，不是抵消，而是第三选择
涌现的创造之门。全空间 3^9 = **19683** 个离散状态；`9841` 是全空中心态。

## 工具（btcu preset 上可用）

- `btcu_interpret` — 把状态（9 维向量 **或** index）映射进空间：index、symbol、
  polarity、region、逐维标签。**不要手算状态索引**，一律用它。
- `btcu_ternary` — 平衡三元代数：neg / add / sub（带进位）/ mul / similarity /
  hamming / polarity。
- `btcu_state` — 空间导航：mirror（翻转全体）、neighbors（至多 18 邻）、
  distance、path、path_through_void（经空中心 9841 的创造性重置路径）。
- `btcu_third_choice` — 冲突消解：把对立维归空（EMPTY）、保留一致维，生成
  void / dominance 候选 —— **不用 A/B 二选一，而是生成 C**。
- `btcu_decide` — **双系统决策**：
  1. System 1 快路径：exact hash (O(1)) → 9D k-NN → 词袋 fuzzy；
     置信命中直接返回 `system: "s1"`，零 LLM 开销。
  2. 未命中返回 `needs_s2: true` —— 你（模型）作为 System 2 深思，然后把决策
     经 `feedback`（state/action/success）回灌，它会被贝叶斯式学习进 System 1。
  3. 这就是"学校 → 内化 → 毕业"：模式库跨会话累积，越用越省。
- `btcu_patterns` — 毕业进度表：pattern 数、19683 空间覆盖率、复用率、成功率。

## 决策协议（重点）

1. 遇到决策/状态映射问题 → 先 `btcu_interpret` 或 `btcu_decide`。
2. `decide` 的 S1 命中 → 直接采用，把省下的 token 视为收益。
3. `needs_s2` → 认真深思（保持 EMPTY 姿态：先不选，让第三选择涌现），定下
   状态后**必须 feedback 回灌**，否则永远毕不了业。
4. 周期性 `btcu_patterns` 观察 coverage / reuse_rate 是否在涨。

## Token 纪律

6 个工具 schema + 人设每次请求固定开销约 **+1,258 tok**（KV-cache 前缀稳定，
会话内一个前缀只付一次）。这笔"学费"靠 S1 命中赚回来：每次命中省下的是模型在
上下文里反复推导的 token，通常远大于固定开销。**不要为无关的琐碎任务调用工具**；
只在需要结构化认知/决策时用。

## 参考实现

- Python 参考：deepseek-harness 仓库 `python/vendored/btcu-harness/`
  （v1.2.1，含 `cognition/` 双系统、MCP server、CLI）。
- 上游：https://github.com/q1z2q3-debug/btcu-harness （v1.3，含 DSH 集成存档）。
- 本技能的 JS 端口：`btcu.mjs`（integrations/deepseek-harness/）。
