# BTCU Harness 四层认知能力

**文档版本：v1.0**
**关联代码：`mapping/projector.py`, `memory/ecology.py`, `memory/climate.py`, `decision/third_choice.py`, `agent.py`**

---

## 1. 概述

BTCU 的认知能力分为四层，每层对应一种与世界交互的方式：

```
第四层：创造世界 —— 主动进入未知，生成新事物
         ^
         |
第三层：解释世界 —— 从大量状态中涌现规律
         ^
         |
第二层：理解世界 —— 从卦象中提取语义
         ^
         |
第一层：映射世界 —— 从原始输入得到九维三态
```

| 层次 | 能力 | 输入 | 输出 | 代码模块 |
|------|------|------|------|----------|
| 映射世界 | 投影 | 自然语言 | CognitiveState | `InputProjector`, `PatternLearner` |
| 理解世界 | 解读 | CognitiveState | 语义描述 | `MemoryEcology.recall()`, `CognitiveSpace.describe_state()` |
| 解释世界 | 发现 | 大量状态历史 | CognitiveSeason, ClimateReport | `MemoryEcology.sense_making()`, `CognitiveClimate` |
| 创造世界 | 探索 | 冲突/未知 | ThirdChoice, 新状态 | `ThirdChoiceGenerator`, `DecisionPathfinder` |

---

## 2. 第一层：映射世界

### 2.1 核心问题

如何将任意自然语言输入映射到九维三元向量（CognitiveState）？

### 2.2 映射算法

```
输入文本
    |
    v
[特征提取] PatternLearner.extract_features(text)
    |  关键词、长度、情感、疑问类型
    v
[模式匹配] PatternLearner.match(text) -> (Pattern, similarity)?
    |
    +-- 匹配成功 (sim >= 0.7) --> 使用 pattern.state_values
    |                              source = "pattern"
    |
    +-- 匹配失败 --> [LLM 投影] InputProjector._project_with_llm(text, llm_cb)
                        |
                        v
                    LLM 返回 JSON {"assessments": [{"value": -1|0|1, "reason": "..."}]}
                        |
                        v
                    解析 + clamp --> CognitiveState
                        |           source = "llm"
                        v
                    [模式学习] PatternLearner.learn(text, state)
                        |  存储供未来匹配
                        v
                    CognitiveState (0-19682)
```

### 2.3 示例

输入："Should BTCU prioritize deep algorithmic innovation?"

LLM 评估（投资评估九维）：

| 维度 | 值 | 原因 |
|------|----|------|
| 技术深度 | +1 | "algorithmic" 指向技术深度 |
| 用户体验 | 0 | 未提及 |
| 创新性 | +1 | "innovation" 明确指向 |
| 可维护性 | 0 | 未提及 |
| 社区影响 | +1 | 深度创新影响社区 |
| 商业价值 | 0 | 未直接提及 |
| 学习成长 | +1 | "deep" 意味着学习 |
| 风险评估 | -1 | 深度方向风险高 |
| 长期愿景 | +1 | 长期投入 |

结果状态：`[1, 0, 1, 0, 1, 0, 1, -1, 1]` -> 索引 #10610

### 2.4 映射质量指标

| 指标 | 计算 | 目标 |
|------|------|------|
| 投影置信度 | `ProjectionResult.confidence` | > 0.7 |
| 模式覆盖率 | `PatternLearner.reuse_rate` | 趋近 1.0 |
| 空态比例 | `state.void_count / 9` | < 0.5（空态过多=维度不适配） |

---

## 3. 第二层：理解世界

### 3.1 核心问题

给定一个 CognitiveState，如何从中提取语义——这个状态意味着什么？

### 3.2 理解算法

```python
def understand_state(state: CognitiveState, agent: BTCUAgent) -> Dict[str, Any]:
    # 1. 结构理解：维度的阴阳空分布
    structure = {
        "polarity": state.polarity,       # +5 = 阳多阴少
        "yang_count": state.yang_count,   # 5
        "yin_count": state.yin_count,     # 1
        "void_count": state.void_count,   # 3
        "intensity": state.intensity,     # 6 = |polarity|
    }

    # 2. 记忆理解：该状态的历史经验
    memory = agent.ecology.recall(state)
    experience = {
        "visit_count": memory["state_memory"].visit_count,
        "success_rate": memory["state_memory"].success_rate,
        "insights": memory["state_memory"].insights,
        "suppressed": memory["state_memory"].suppressed_decisions,
    }

    # 3. 关系理解：与其他状态的关联
    relations = {
        "resonant_states": memory["resonant_states"],
        "incoming_transitions": len(memory["incoming_transitions"]),
        "outgoing_transitions": len(memory["outgoing_transitions"]),
    }

    # 4. 自我理解：与吸引子的关系
    self_context = {
        "alignment": agent.self_layer.alignment_score(state),
        "distance_to_attractor": agent.self_layer.distance_to_attractor(state),
    }

    # 5. 自然语言描述
    description = agent.space.describe_state(state)

    return {
        "structure": structure,
        "experience": experience,
        "relations": relations,
        "self_context": self_context,
        "description": description,
    }
```

### 3.3 示例

状态 #10610 `[1, 0, 1, 0, 1, 0, 1, -1, 1]`：

```json
{
  "structure": {
    "polarity": 5,
    "yang_count": 5,
    "yin_count": 1,
    "void_count": 3,
    "intensity": 6,
    "interpretation": "阳主导，有明确方向但保留开放性（3维空），有1维风险否定"
  },
  "experience": {
    "visit_count": 3,
    "success_rate": 0.67,
    "insights": ["技术深度与创新性正相关"],
    "suppressed": []
  },
  "relations": {
    "resonant_states": [10611, 10609, 10612],
    "incoming_transitions": 2,
    "outgoing_transitions": 4
  },
  "self_context": {
    "alignment": 0.778,
    "distance_to_attractor": 4
  },
  "description": "技术深度:阳, 用户体验:空, 创新性:阳, ..."
}
```

---

## 4. 第三层：解释世界

### 4.1 核心问题

从大量状态访问历史中，涌现出什么规律？

### 4.2 解释算法

```python
def explain_world(agent: BTCUAgent) -> Dict[str, Any]:
    # 1. 静态节气：从记忆生态中涌现的模式
    seasons = agent.ecology.sense_making()
    # attractor: 反复回归的状态
    # virtue: 反复成功的路径
    # trap: 反复失败的路径
    # blind_spot: 未探索的区域
    # resonance: 频繁共激活的状态对

    # 2. 动态气候：长期趋势分析
    climate = agent.climate.report(
        ecology=agent.ecology,
        trajectory=agent.trajectory,
    )
    # polarity_trend: 趋阳还是趋阴
    # exploration_phase: 扩大/巩固/停滞
    # climate_zones: 活跃区域
    # drift: 认知漂移
    # dominant_period: 主导周期

    # 3. 轨迹分析：认知路径的模式
    clusters = agent.trajectory.detect_clusters()
    cycles = agent.trajectory.detect_cycles()
    # clusters: 反复访问的区域
    # cycles: 重复的状态序列

    # 4. 综合解释
    return {
        "seasons": seasons,
        "climate": climate,
        "clusters": clusters,
        "cycles": cycles,
        "summary": f"Agent处于{climate.exploration_phase}阶段，"
                   f"极性趋势{climate.polarity_trend:+.2f}，"
                   f"已发现{len(seasons)}个认知节气"
    }
```

### 4.3 示例输出

```
=== 认知世界解释 ===

[节气]
- attractor: 状态#9841（全空态）被访问7次——Agent 反复回归创造潜能
- virtue: 转化 9841->10610 成功率 100%——从空态到创新方向的路径是美德
- blind_spot: 19677个状态(100%)未被探索——大量未知

[气候]
- 探索阶段: expanding（86%探索率）
- 极性趋势: -0.821（趋向阴——Agent 在反思阶段）
- 气候区域: 4个活跃区域
  - Zone #10610: 温度 0.43, 极性 +5.5 (创新方向)
  - Zone #14279: 温度 0.14, 极性 +2.0
  - Zone #1083: 温度 0.14, 极性 -4.0 (反思方向)
- 漂移: 5.0（轻微认知漂移）

[轨迹]
- 聚类: 1个（以#9841为中心）
- 周期: 检测到周期1的循环（9841->9841），规律性 100%
- 探索率: 86%
```

---

## 5. 第四层：创造世界

### 5.1 核心问题

如何主动进入未知状态并生成新事物？

### 5.2 创造的三种路径

#### 路径 A：第三选择（从冲突中创造）

```python
# 当两个方向冲突时，生成超越的第三选择
candidates = agent.third_choice_gen.generate_all(state_a, state_b)
# 策略: void, fusion, dominance_a, dominance_b, emergent
# emergent 策略专门探索未访问的邻近状态
```

#### 路径 B：盲区探索（从未知中创造）

```python
# 发现盲区并主动探索
seasons = agent.ecology.sense_making()
blind_spots = [s for s in seasons if s.season_type == "blind_spot"]

# 选择最近的盲区
current = agent._prev_state
nearest_blind = min(
    blind_spots[0].state_indices,
    key=lambda idx: current.distance(CognitiveState.from_index(idx))
)

# 生成路径到盲区
path = agent.pathfinder.find_path(current, CognitiveState.from_index(nearest_blind))
```

#### 路径 C：空态回归（从潜能中创造）

```python
# 回到全空态，释放所有确定立场
void_path = agent.pathfinder.find_void_path(current)
# 从空态出发，以全新视角重新投影
new_state = agent.projector.project("完全不同的新问题", llm_cb)
```

### 5.3 创造力评估

| 指标 | 计算 | 含义 |
|------|------|------|
| void_ratio | `candidate.void_ratio` | 第三选择中空维比例，越高越有创造潜力 |
| emergent_rate | emergent策略数 / 总候选数 | 涌现策略占比 |
| blind_spot_coverage | 1 - coverage | 未探索空间比例 |
| novelty_score | 新状态在最近N步中未出现 | 状态新颖度 |

### 5.4 创造与自我的平衡

创造力不等于无原则。`ThirdChoiceGenerator` 的评分包含 `self_alignment_score`（权重 0.20）——创造的第三选择不应该完全偏离 Agent 的身份。

```
创造力 = void_ratio * 0.30 (开放) + equidistance * 0.25 (平衡)
         + memory_score * 0.25 (经验) + self_alignment * 0.20 (认同)
```

---

## 6. 四层认知的协同

### 6.1 认知循环

```
[映射] 输入 -> 状态
   |
   v
[理解] 状态 -> 语义（记忆+关系+自我）
   |
   v
[解释] 历史 -> 规律（节气+气候+轨迹）
   |
   v
[创造] 冲突/未知 -> 新状态（第三选择+盲区探索）
   |
   v
[映射] 新状态作为输入回到循环...
```

### 6.2 在 agent.py 中的实现

`BTCUAgent.process()` 方法的 11 步对应四层认知：

| 步骤 | 认知层 | 代码 |
|------|--------|------|
| 1. 模式匹配 | 映射 | `pattern_learner.match()` |
| 2. LLM 投影 | 映射 | `projector.project()` |
| 3. 记忆回溯 | 理解 | `ecology.recall()` |
| 4. 自我对齐 | 理解 | `self_layer.alignment_score()` |
| 5. 决策路径 | 创造 | `pathfinder.find_path()` |
| 6. 第三选择 | 创造 | `third_choice_gen.generate_all()` |
| 7. LLM 建议 | 创造 | `llm_bridge.advise()` |
| 8. 模式学习 | 映射 | `pattern_learner.learn()` |
| 9. 轨迹记录 | 理解 | `trajectory.record()` |
| 10. 记忆记录 | 理解 | `ecology.remember()` |
| 11. 气候快照 | 解释 | `climate.snapshot()` |

### 6.3 成长阶段与四层认知

| 成长阶段 | 映射 | 理解 | 解释 | 创造 |
|----------|------|------|------|------|
| school | LLM 主导 | 基础记忆 | 无足够数据 | 依赖 LLM 建议 |
| internalize | 模式优先 | 记忆积累 | 节气开始涌现 | 第三选择主动生成 |
| graduate | 自主投影 | 深度理解 | 气候+轨迹分析 | 主动盲区探索 |

---

## 参考文献

1. Piaget, J. (1970). *The Science of Education and the Psychology of the Child*. 认知发展四阶段.
2. Vygotsky, L. S. (1978). *Mind in Society*. 最近发展区理论.
3. Bloom, B. S. (1956). *Taxonomy of Educational Objectives*. 认知层次分类.
4. Argyris, C. (1991). Teaching Smart People How to Learn. *Harvard Business Review*. 双环学习.
