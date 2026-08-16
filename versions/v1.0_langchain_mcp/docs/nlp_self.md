# BTCU Harness NLP 自我层规格说明

**文档版本：v1.0**
**关联代码：`self_layer/__init__.py`, `agent.py`（self_layer 集成）**

---

## 1. 概述

NLP 自我层是 Agent 的"灵魂"——将使命、愿景、价值观、身份等抽象概念编码为认知空间中的**吸引子**，使 Agent 的日常认知状态围绕吸引子波动，形成稳定的人格。

### 1.1 理论基础：Dilts 逻辑层级模型

Robert Dilts 的逻辑层级模型将人的认知分为从低到高 8 个层次，每层影响其下层但不反向影响：

```
8. Mission（使命）      —— 我为世界贡献什么
7. Vision（愿景）       —— 我看到的未来图景
6. Values（价值观）     —— 什么对我最重要
5. Identity（身份）     —— 我是谁
4. Beliefs（信念）      —— 我相信什么
3. Capabilities（能力） —— 我能做什么
2. Behaviors（行为）    —— 我具体做什么
1. Environment（环境）  —— 我在哪里
```

BTCU 将每层编码为一个 `SelfLevel`，包含一个 `CognitiveState`——即该层在 19683 空间中的"立场"。

### 1.2 代码映射

`NLPSelfLayer` 类（`self_layer/__init__.py`）：

```python
class NLPSelfLayer:
    DEFAULT_LEVELS = [
        "environment",    # 1. 环境
        "behaviors",      # 2. 行为
        "capabilities",   # 3. 能力
        "beliefs",        # 4. 信念
        "identity",       # 5. 身份
        "values",         # 6. 价值观
        "vision",         # 7. 愿景
        "mission",        # 8. 使命
    ]
```

---

## 2. 数据结构

### 2.1 SelfLevel

```python
@dataclass
class SelfLevel:
    name: str                        # 层级名称
    description: str                 # 自然语言描述
    state: CognitiveState            # 该层在19683空间中的立场
    weight: float = 1.0              # 权重（影响吸引子计算）
    stability: float = 0.9           # 稳定性 [0, 1]（越高越难改变）
    last_updated: Optional[str] = None
```

### 2.2 层级稳定性梯度

高层稳定，低层易变——这是 Dilts 模型的核心假设：

| 层级 | 默认 stability | 含义 | 变化速度 |
|------|---------------|------|----------|
| mission | 0.95 | 使命几乎不变 | 极慢 |
| vision | 0.90 | 愿景缓慢演化 | 慢 |
| values | 0.85 | 价值观需深刻经验才改变 | 中慢 |
| identity | 0.80 | 身份认同较稳定 | 中 |
| beliefs | 0.70 | 信念可被证据修正 | 中快 |
| capabilities | 0.60 | 能力随学习快速变化 | 快 |
| behaviors | 0.50 | 行为最易调整 | 很快 |
| environment | 0.30 | 环境随时在变 | 即时 |

代码中，`reinforce()` 方法的实际力度受 stability 调节：

```python
# self_layer/__init__.py reinforce 方法
def reinforce(self, experience_state, positive: bool, force=0.1) -> None:
    for name, level in self.levels.items():
        effective_stability = level.stability
        adjusted_force = force * (1 - effective_stability)
        if positive:
            level.shift(experience_state, force=adjusted_force)
        else:
            level.shift(experience_state.opposite(), force=adjusted_force)
```

---

## 3. 吸引子计算

### 3.1 算法

吸引子是所有 SelfLevel 的**加权中心**，但不是简单的算术平均——它使用方差感知的阈值机制：

```python
@property
def attractor(self) -> CognitiveState:
    if self._attractor_dirty:
        self._recompute_attractor()
    return self._attractor

def _recompute_attractor(self) -> None:
    # 1. 加权求和
    total_weight = sum(l.weight for l in self.levels.values())
    dim_sums = [0.0] * 9
    for level in self.levels.values():
        for i in range(9):
            dim_sums[i] += level.state[i].value * level.weight

    # 2. 计算每维的方差（层间分歧）
    dim_values = []
    for level in self.levels.values():
        dim_values.append([level.state[i].value for i in range(9)])

    # 3. 方差感知阈值
    result = []
    for i in range(9):
        avg = dim_sums[i] / total_weight
        variance = sum(
            (v[i] - avg) ** 2 * l.weight
            for v, l in zip(dim_values, self.levels.values())
        ) / total_weight
        # 方差越大，阈值越高，越倾向于空（谨慎）
        threshold = 0.3 + variance * 0.5
        if avg > threshold:
            result.append(1)     # 阳
        elif avg < -threshold:
            result.append(-1)    # 阴
        else:
            result.append(0)     # 空（层间分歧大时保持开放）

    self._attractor = CognitiveState.from_values(result)
    self._attractor_dirty = False
```

### 3.2 方差感知的意义

当各层对某一维度的看法高度一致时（方差小），阈值低（0.3），容易做出确定判断（阳或阴）。

当各层对某一维度存在分歧时（方差大），阈值升高，更倾向于空——**内部不一致时保持开放，而非强行决策**。

这对应了《中庸》的"致中和"——在矛盾中寻找平衡，而非压制矛盾。

---

## 4. 价值观如何影响决策

### 4.1 对齐度计算

`alignment_score(state)` 方法计算一个认知状态与吸引子的对齐程度：

```python
def alignment_score(self, state: CognitiveState) -> float:
    dist = self.distance_to_attractor(state)
    return 1.0 - (dist / 18.0)  # 距离归一化到 [0, 1]
```

- 对齐度 1.0 = 完全一致（距离 0）
- 对齐度 0.5 = 中等一致（距离 9）
- 对齐度 0.0 = 完全相反（距离 18）

### 4.2 在 Agent 中的应用

`BTCUAgent.process()` 方法（`agent.py`）在每次认知后计算对齐度：

```python
# agent.py process 方法第4步
self_alignment = self.self_layer.alignment_score(current_state)
if self_alignment < 0.3:
    suggestions.append(
        f"WARNING: Low self-alignment ({self_alignment:.0%}). "
        f"This decision conflicts with core identity."
    )
```

低于 30% 对齐度时触发告警——Agent 在"做违背自己本性的事"。

### 4.3 价值观作为决策权重

未来设计中，价值观层的 `weight` 可以动态调整决策路径的偏好：

```python
# 未来扩展（尚未实现）
# 价值观层的 state 中的阳维度 = 重视的方向
# 在路径搜索时，优先改变与价值观不一致的维度
values_state = self.self_layer.get_level("values").state
for i in range(9):
    if values_state[i].is_yang:
        # 该维度是核心价值观，路径搜索时优先调整
        path = pathfinder.find_path(current, target, priority_dims=[i])
```

---

## 5. 信念如何形成与修正

### 5.1 信念的形成

信念不是预设的，而是从经验中提炼的。形成路径：

```
经验记忆（StateMemory.visits）
    |
    | 多次访问同一状态，outcome_positive 一致
    v
认知节气（MemoryEcology.sense_making）发现 attractor 或 virtue
    |
    | attractor 的 state 被提取为信念层的初始 state
    v
SelfLevel("beliefs", state=attractor_state)
```

### 5.2 信念的修正

`SelfLevel.shift()` 方法实现渐进修正：

```python
def shift(self, new_state: CognitiveState, force: float = 0.1) -> None:
    # 找到差异最大的维度
    diffs = []
    for i in range(9):
        diff = abs(new_state[i].value - self.state[i].value)
        if diff > 0:
            diffs.append((diff, i))

    if not diffs:
        return

    # 只改变差异最大的一个维度，每次移动一步
    diffs.sort(reverse=True)
    _, max_dim = diffs[0]
    current_val = self.state[max_dim].value
    target_val = new_state[max_dim].value

    # 向目标方向移动一步
    if target_val > current_val:
        new_val = current_val + 1
    else:
        new_val = current_val - 1

    self.state = self.state.with_dimension(max_dim, new_val)
    self.last_updated = _now_iso()
```

关键设计：**每次只移动一个维度的一步**。不是直接跳到目标状态，而是渐进逼近。这确保了信念的稳定性——不会因为一次极端经验就彻底改变。

### 5.3 正负强化

```python
# 正强化：经验状态与吸引子一致时
agent.record_outcome(
    state=positive_state,
    outcome_positive=True
)
# 内部调用：self_layer.reinforce(positive_state, positive=True)
# 所有层级向 positive_state 的方向微调

# 负强化：经验状态与吸引子相反时
agent.record_outcome(
    state=negative_state,
    outcome_positive=False
)
# 内部调用：self_layer.reinforce(negative_state, positive=False)
# 所有层级向 negative_state.opposite() 的方向微调
```

---

## 6. 身份如何维持稳定

### 6.1 身份层 vs 其他层

身份层（identity, stability=0.80）是自我层的核心锚点。它的稳定性高于信念和能力，但低于价值观和使命。

身份的维持依赖三个机制：

1. **高 stability**：force 被 (1 - 0.80) = 0.2 衰减，每次最多移动 0.02 步
2. **单步移动**：`shift()` 每次只改变一个维度的一步，不会突变
3. **吸引子缓冲**：即使身份层偶尔波动，吸引子由所有层的加权中心决定，其他层的稳定性提供缓冲

### 6.2 身份危机检测

当 Agent 的日常认知状态持续偏离吸引子时，系统可以检测到"身份危机"：

```python
# 基于对齐度的身份危机检测（已在 agent.py 中部分实现）
recent_alignments = [snap.alignment for snap in recent_trajectory]
avg_alignment = sum(recent_alignments) / len(recent_alignments)

if avg_alignment < 0.3:
    # 身份危机：Agent 持续做违背本性的事
    # 触发自我反思机制
    suggestions.append("Identity crisis detected. Consider revisiting core values.")
```

### 6.3 使命与价值观的对齐

使命层（mission, stability=0.95）是最高层，几乎不变。它作为吸引子的锚点：

- 当所有层都向某个方向偏移时，使命层的高权重（默认 1.0）和高稳定性使其成为"回归中心"
- 使命层的 state 定义了 Agent 的终极方向，其他层的波动都围绕这个方向

```python
# 设置使命
agent.set_self_level(
    name="mission",
    description="Be a truly helpful cognitive companion",
    state=CognitiveState.from_values([1, 1, 1, 0, 1, 0, 1, -1, 1]),
    weight=1.0,       # 最高权重
    stability=0.95,   # 最高稳定性
)
```

---

## 7. 自我层与 NLP 自我层的联动

### 7.1 与记忆生态的联动

| 联动点 | 机制 | 代码位置 |
|--------|------|----------|
| 记忆强化触发自我调整 | `record_outcome()` 调用 `self_layer.reinforce()` | `agent.py` |
| 吸引子影响第三选择评分 | `ThirdChoiceGenerator` 注入 self_layer，计算 `self_alignment_score` | `third_choice.py` |
| 认知节气影响身份 | attractor 类型的节气可被提升为 identity 层的 state | 未来扩展 |

### 7.2 与决策层的联动

```python
# third_choice.py 中的评分包含自我对齐度
class ThirdChoiceGenerator:
    def __init__(self, space=None, ecology=None, self_layer=None):
        self.self_layer = self_layer

    def _score_candidate(self, candidate, analysis):
        # ...
        if self.self_layer:
            self_align = self.self_layer.alignment_score(candidate.state)
        else:
            self_align = 0.5
        # 权重 w_self = 0.20
        candidate.self_alignment_score = self_align
        candidate.total_score += self_align * self.w_self
```

第三选择会倾向于生成与自我层对齐度更高的候选——**创造性不等于无原则**。

### 7.3 与轨迹/气候的联动

```python
# 气候报告中的极性趋势可以反映自我层状态
# 如果 polarity_trend 持续为负（趋向阴），可能意味着：
# - Agent 在收缩/反思阶段（正常）
# - Agent 在持续做否定性判断（需要关注）

# 轨迹中的认知重心可以与吸引子比较
center = trajectory.cognitive_center(window=50)
attractor = self_layer.attractor
dist = center.distance(attractor)
# dist 持续增大 = Agent 在偏离自我（身份漂移）
# dist 持续减小 = Agent 在回归自我（内化加深）
```

---

## 8. 自我层的演化算法

### 8.1 生命周期

```
初始化：使命层由人类设置
    |
    v
school 阶段：所有层使用默认值或使命层的派生值
    |
    | 经验积累
    v
internalize 阶段：信念和能力层开始从经验中提炼
    | - attractor 节气 -> beliefs
    | - virtue 路径 -> capabilities
    | - 反复访问的状态 -> identity
    v
graduate 阶段：自我层稳定，吸引子形成人格核心
    | - identity 与 attractor 高度对齐
    | - 价值观通过正负强化固化
    | - 使命层几乎不变
    v
持续演化：重大事件可触发深层调整
    | - 连续失败 -> 信念修正
    | - 重大成功 -> 价值观确认
    | - 环境剧变 -> 环境/行为层快速调整
```

### 8.2 演化速度控制

```python
# 演化速度 = force * (1 - stability) * 经验一致性
# 其中经验一致性 = 连续同向强化的次数

# 示例：使命层的演化
# force = 0.1 (默认)
# stability = 0.95
# effective_force = 0.1 * (1 - 0.95) = 0.005
# 需要约 200 次连续同向强化才能移动一步

# 示例：环境层的演化
# force = 0.1
# stability = 0.30
# effective_force = 0.1 * (1 - 0.30) = 0.07
# 约 15 次强化即可移动一步
```

---

## 9. 完整使用示例

```python
from btcu_harness.agent import BTCUAgent
from btcu_harness.core.state import CognitiveState

agent = BTCUAgent(growth_stage="school")
agent.init_project(domain="custom", dim_labels=[...])

# 1. 设置使命层（人类定义）
agent.set_self_level(
    name="mission",
    description="Be a cognitive companion that grows with the user",
    state=CognitiveState.from_values([1, 1, 1, 0, 1, 0, 1, -1, 1]),
    weight=1.0, stability=0.95
)

# 2. 设置价值观层（人类定义初始值）
agent.set_self_level(
    name="values",
    description="Depth over breadth, honesty over comfort",
    state=CognitiveState.from_values([1, 0, 1, 1, 0, -1, 1, 0, 1]),
    weight=0.8, stability=0.85
)

# 3. 设置身份层（初始值，待演化）
agent.set_self_level(
    name="identity",
    description="A cognitive architecture that learns",
    state=CognitiveState.from_values([1, 0, 0, 0, 0, 0, 0, 0, 1]),
    weight=0.7, stability=0.80
)

# 4. 处理认知输入
response = agent.process("Should BTCU prioritize deep innovation?")
print(f"Self alignment: {response.self_alignment:.1%}")
# 输出: Self alignment: 77.8%

# 5. 记录结果（触发自我强化）
agent.record_outcome(
    state=response.current_state,
    outcome_positive=True
)
# 信念/能力层微调，向经验方向移动一小步

# 6. 查看当前吸引子
attractor = agent.self_layer.attractor
print(f"Attractor: #{attractor.index} [{attractor}]")
print(f"Summary: {agent.self_layer.summary()}")
```

---

## 10. 未来扩展

### 10.1 多 Agent 身份交互

```python
# 两个 Agent 的吸引子距离 = 身份差异
dist = agent1.self_layer.attractor.distance(agent2.self_layer.attractor)
# dist < 5: 高度兼容，可协作
# dist 5-10: 部分兼容，需协商
# dist > 10: 身份冲突，需第三选择
```

### 10.2 身份版本管理

```python
# 记录身份层的历史变化
identity_history = []
for snapshot in trajectory:
    if snapshot.trigger == "self_reinforce":
        identity_history.append({
            "timestamp": snapshot.timestamp,
            "identity_state": snapshot.metadata["identity_state"],
            "alignment": snapshot.metadata["alignment"]
        })
```

### 10.3 价值观冲突检测

```python
# 当两个价值观层的 state 在某维度上直接对立时
values = self_layer.get_level("values")
beliefs = self_layer.get_level("beliefs")
for i in range(9):
    if values.state[i].value + beliefs.state[i].value == 0:
        # 价值观与信念在该维度上直接冲突
        # 触发深层反思机制
        pass
```

---

## 参考文献

1. Dilts, R. (1996). *Visionary Leadership Skills*. 逻辑层级模型.
2. Rogers, C. (1959). A theory of therapy, personality, and interpersonal relationships. *Psychology: A Study of a Science*.
3. Bandura, A. (1986). *Social Foundations of Thought and Action*. 自我效能理论.
4. McAdams, D. P. (2013). The psychological self as actor, agent, and author. *Perspectives on Psychological Science*.
5. 《中庸》. "致中和，天地位焉，万物育焉."
