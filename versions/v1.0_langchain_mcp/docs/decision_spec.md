# BTCU Harness 决策与行动规格说明

**文档版本：v1.0**
**关联代码：`decision/pathfinder.py`, `decision/third_choice.py`, `core/space.py`**

---

## 1. 决策的本质：卦变路径

BTCU 的决策不是"从选项集中选择最优"，而是**生成从当前状态到目标状态的认知迁移路径**。

在《易经》中，决策对应"卦变"——从一个卦象变到另一个卦象，每一步改变一个爻。BTCU 中，每一步改变一个维度的 Trit 值（-1 -> 0 -> +1 或反向），这对应认知的一次微调。

### 1.1 核心类

| 类 | 文件 | 职责 |
|----|------|------|
| `DecisionPathfinder` | `decision/pathfinder.py` | 生成状态迁移路径，标注记忆 |
| `DecisionPath` | `decision/pathfinder.py` | 路径数据结构 |
| `ThirdChoiceGenerator` | `decision/third_choice.py` | 二元冲突时生成第三选择 |
| `ThirdChoiceCandidate` | `decision/third_choice.py` | 候选方案数据结构 |
| `ConflictAnalysis` | `decision/third_choice.py` | 冲突分析结果 |

---

## 2. 路径搜索算法

### 2.1 贪心路径（`CognitiveSpace.path()`）

```python
def path(source: CognitiveState, target: CognitiveState) -> List[CognitiveState]:
    """贪心算法：每步改变一个维度，减少到目标的距离。"""
    path = [source]
    current = source
    while current != target:
        # 找到第一个与 target 不同的维度
        for i in range(9):
            if current[i] != target[i]:
                # 向 target 方向移动一步
                current = current.with_dimension(i, target[i].value)
                path.append(current)
                break
    return path
```

**路径长度** = 认知距离 `dist(source, target)` = 两个状态间不同维度的 Trit 差值之和。

### 2.2 穿越空态路径（`CognitiveSpace.path_through_void()`）

```python
def path_through_void(source: CognitiveState, target: CognitiveState) -> List[CognitiveState]:
    """从 source 到 void 再到 target——必经创造潜能。"""
    void = CognitiveState.all_void()  # #9841
    return path(source, void) + path(void, target)[1:]
```

**哲学意义**：从极端否定到极端肯定没有直通路径——必须经过空态（创造潜能）。这是 BTCU 的核心定理之一。

### 2.3 记忆标注（`_annotate_with_memory()`）

路径生成后，`DecisionPathfinder` 会用记忆生态标注路径上的每个状态：

```python
def _annotate_with_memory(self, path: DecisionPath) -> None:
    for state in path.states:
        mem = self.ecology.state_store.get_or_none(state.index)
        if mem:
            # 警告：该状态有失败记录
            if mem.failure_count > mem.success_count:
                path.memory_warnings.append(
                    f"State #{state.index} has {mem.failure_count} failures"
                )
            # 引导：该状态有完美记录
            if mem.visit_count >= 3 and mem.success_rate == 1.0:
                path.memory_guidance.append(
                    f"State #{state.index} has perfect record"
                )
            # 警告：被抑制的决策
            if mem.suppressed_decisions:
                path.memory_warnings.append(
                    f"Suppressed: {mem.suppressed_decisions}"
                )

    # 标注转化记忆中的陷阱
    for i in range(len(path.states) - 1):
        tm = self.ecology.transition_store.get_or_none(
            path.states[i].index, path.states[i+1].index
        )
        if tm and tm.is_trap:
            path.memory_warnings.append(
                f"Trap: {tm.from_index}->{tm.to_index} "
                f"(failure rate: {1-tm.success_rate:.0%})"
            )
        if tm and tm.is_virtue:
            path.memory_guidance.append(
                f"Virtue: {tm.from_index}->{tm.to_index} "
                f"(success rate: {tm.success_rate:.0%})"
            )
```

### 2.4 路径选择策略

`DecisionPathfinder.find_path()` 根据距离选择路径类型：

```python
def find_path(self, source, target, prefer_void=False) -> DecisionPath:
    dist = source.distance(target)
    # 距离 >= 10 时自动选择穿越空态路径
    if prefer_void or dist >= 10:
        raw_path = self.space.path_through_void(source, target)
        through_void = True
    else:
        raw_path = self.space.path(source, target)
        through_void = False

    path = DecisionPath(
        states=raw_path,
        through_void=through_void,
        estimated_length=len(raw_path) - 1,
        ...
    )
    self._annotate_with_memory(path)
    return path
```

---

## 3. 卦变路径的合法规则

### 3.1 单步变化规则

每一步只能改变一个维度，且变化幅度为 1：

| 当前值 | 可达值 | 不可达值 |
|--------|--------|----------|
| -1 (阴) | 0 (空) | +1 (阳)——需两步 |
| 0 (空) | -1 (阴) 或 +1 (阳) | — |
| +1 (阳) | 0 (空) | -1 (阴)——需两步 |

### 3.2 阴 -> 空 -> 阳的必经性

从阴到阳的任何路径都必须经过空：

$$\text{dist}(-1, +1) = 2 \quad \text{但中间必经} \quad 0$$

这不是人为限制，而是 Trit 值域 $\{-1, 0, +1\}$ 的数学性质——不存在从 -1 直接跳到 +1 的单步操作。

在状态空间层面，这意味着**从全阴到全阳的路径长度恰好是 18**（每维 2 步 x 9 维），且路径必然穿越空态区域。

### 3.3 合法路径的验证

```python
def is_legal_path(path: List[CognitiveState]) -> bool:
    """验证路径是否合法：每步只改变一个维度，且幅度为1。"""
    for i in range(len(path) - 1):
        diff = path[i].distance(path[i + 1])
        if diff != 1:
            return False
        # 检查是否只有一个维度变化
        diff_dims = path[i].diff_dimensions(path[i + 1])
        if len(diff_dims) != 1:
            return False
        # 检查变化幅度
        dim = diff_dims[0]
        val_diff = abs(path[i][dim].value - path[i + 1][dim].value)
        if val_diff != 1:
            return False
    return True
```

---

## 4. 第三选择生成器

### 4.1 冲突分析

`ThirdChoiceGenerator.analyze_conflict(state_a, state_b)` 分析两个状态的冲突结构：

```python
@dataclass
class ConflictAnalysis:
    state_a: CognitiveState
    state_b: CognitiveState
    agreeing_dims: List[int]    # A和B一致的维度
    disagreeing_dims: List[int] # A和B不一致的维度
    opposite_dims: List[int]    # 完全对立的维度 (-1 vs +1)
    adjacent_dims: List[int]    # 相邻冲突 (-1 vs 0 或 0 vs +1)

    @property
    def has_conflict(self) -> bool:
        return len(self.disagreeing_dims) > 0

    @property
    def is_extreme_conflict(self) -> bool:
        return len(self.opposite_dims) == 9

    @property
    def conflict_intensity(self) -> float:
        return len(self.disagreeing_dims) / 9

    @property
    def opposition_ratio(self) -> float:
        if not self.disagreeing_dims:
            return 0.0
        return len(self.opposite_dims) / len(self.disagreeing_dims)
```

### 4.2 五种策略

#### 策略 1: void（置空）

```python
def _strategy_void(self, analysis: ConflictAnalysis) -> ThirdChoiceCandidate:
    """一致维度保持，冲突维度置空。"""
    result = [0] * 9
    for i in analysis.agreeing_dims:
        result[i] = analysis.state_a[i].value
    # 冲突维度全部为 0（空）
    return ThirdChoiceCandidate(
        state=CognitiveState.from_values(result),
        strategy="void",
        rationale="Void conflicts, preserve agreements",
        preserved_dims=analysis.agreeing_dims,
        voided_dims=analysis.disagreeing_dims,
    )
```

#### 策略 2: fusion（融合）

```python
def _strategy_fusion(self, analysis: ConflictAnalysis) -> ThirdChoiceCandidate:
    """相邻冲突取非零值，对立冲突置空。"""
    result = [0] * 9
    for i in analysis.agreeing_dims:
        result[i] = analysis.state_a[i].value
    for i in analysis.disagreeing_dims:
        val_a = analysis.state_a[i].value
        val_b = analysis.state_b[i].value
        if val_a != 0:
            result[i] = val_a  # 取非零值
        elif val_b != 0:
            result[i] = val_b
        # 如果都是非零且对立（-1 vs +1），保持空
    return ThirdChoiceCandidate(
        state=CognitiveState.from_values(result),
        strategy="fusion",
        rationale="Fuse adjacent conflicts, void opposites",
    )
```

#### 策略 3: dominance_a（A 方主导）

```python
def _strategy_dominance(self, analysis, dominant="a") -> ThirdChoiceCandidate:
    """前半冲突由主导方决定，后半置空。"""
    result = [0] * 9
    for i in analysis.agreeing_dims:
        result[i] = analysis.state_a[i].value
    # 排序冲突维度，前半取主导方
    sorted_disagree = sorted(analysis.disagreeing_dims)
    half = len(sorted_disagree) // 2
    for idx, i in enumerate(sorted_disagree):
        if idx < half:
            source = analysis.state_a if dominant == "a" else analysis.state_b
            result[i] = source[i].value
        # 后半保持空
    return ThirdChoiceCandidate(
        state=CognitiveState.from_values(result),
        strategy=f"dominance_{dominant}",
    )
```

#### 策略 4: dominance_b（B 方主导）

与 dominance_a 对称，B 方主导前半冲突。

#### 策略 5: emergent（涌现）

```python
def _strategy_emergent(self, analysis: ConflictAnalysis) -> ThirdChoiceCandidate:
    """在void策略基础上，探索未访问的邻近状态。"""
    base = self._strategy_void(analysis)
    # 在 base.state 的邻域中寻找未访问的状态
    neighbors = base.state.neighbors()
    unvisited = [
        n for n in neighbors
        if self.ecology and
           self.ecology.state_store.get_or_none(n.index) is None
    ]
    # 选择与A和B距离最接近的未访问状态
    best = None
    best_diff = float('inf')
    for n in unvisited:
        dist_a = n.distance(analysis.state_a)
        dist_b = n.distance(analysis.state_b)
        diff = abs(dist_a - dist_b)
        if diff < best_diff:
            best_diff = diff
            best = n
    if best and best_diff <= 3:
        return ThirdChoiceCandidate(
            state=best,
            strategy="emergent",
            rationale="Explore unvisited equidistant state",
        )
    return base  # 退回void
```

### 4.3 候选评分

```python
def _score_candidate(self, candidate, analysis) -> None:
    # 1. 等距性 (w=0.25): 与A和B的距离是否平衡
    dist_a = candidate.state.distance(analysis.state_a)
    dist_b = candidate.state.distance(analysis.state_b)
    candidate.equidistance_score = 1.0 - abs(dist_a - dist_b) / 18

    # 2. 记忆 (w=0.25): 该状态的历史成功率
    mem = self.ecology.state_store.get_or_none(candidate.state.index)
    if mem and mem.visit_count > 0:
        candidate.memory_score = mem.success_rate
    else:
        candidate.memory_score = 0.5  # 未访问=中性

    # 3. 自我对齐 (w=0.20): 与吸引子的对齐度
    if self.self_layer:
        candidate.self_alignment_score = self.self_layer.alignment_score(candidate.state)
    else:
        candidate.self_alignment_score = 0.5

    # 4. 空度 (w=0.30): 冲突维度的置空比例
    candidate.void_ratio = len(candidate.voided_dims) / max(1, len(analysis.disagreeing_dims))

    # 加权总分
    candidate.total_score = (
        candidate.equidistance_score * 0.25 +
        candidate.memory_score * 0.25 +
        candidate.self_alignment_score * 0.20 +
        candidate.void_ratio * 0.30
    )
```

### 4.4 完整生成流程

```
输入: state_a, state_b
    |
    v
analyze_conflict(a, b) -> ConflictAnalysis
    |
    | 如果无冲突: 返回 state_a (无需第三选择)
    v
生成 5 个策略候选:
    - _strategy_void
    - _strategy_fusion
    - _strategy_dominance_a
    - _strategy_dominance_b
    - _strategy_emergent
    |
    v
对每个候选用 _score_candidate 评分
    |
    v
按 total_score 降序排序
    |
    v
去重（相同 index 的候选保留高分者）
    |
    v
返回 Top-N (max_candidates=8)
```

---

## 5. 认知节律如何影响决策

### 5.1 节律来源

`CognitiveClimate` 和 `CognitiveTrajectory` 提供节律信息：

| 节律指标 | 来源 | 对决策的影响 |
|----------|------|-------------|
| exploration_phase | `CognitiveClimate` | expanding时鼓励探索新路径；stagnant时建议回归空态 |
| polarity_trend | `CognitiveClimate` | 趋向阳时路径偏向阳性目标；趋向阴时偏向反思 |
| dominant_period | `CognitiveTrajectory` | 已知周期可预测下一步认知方向 |
| drift | `CognitiveClimate` | 高漂移时决策应更谨慎，低漂移时可更果断 |

### 5.2 节律感知的路径选择（未来扩展）

```python
def find_path_with_rhythm(self, source, target) -> DecisionPath:
    climate = self.climate.report(ecology=self.ecology, trajectory=self.trajectory)

    # 停滞期：建议先回空态
    if climate.exploration_phase == "stagnant":
        void_path = self.find_void_path(source)
        return void_path  # "先归空再出发"

    # 扩展期：选择经过未访问状态的路径
    elif climate.exploration_phase == "expanding":
        # 在路径上加入未访问的邻近状态
        raw_path = self.space.path(source, target)
        detour = self._find_unvisited_detour(raw_path)
        if detour:
            return detour

    # 默认：贪心路径 + 记忆标注
    return self.find_path(source, target)
```

---

## 6. 完整决策流程示例

```python
from btcu_harness.agent import BTCUAgent
from btcu_harness.core.state import CognitiveState

agent = BTCUAgent()
agent.init_project(domain="decision", dim_labels=[
    "紧迫性", "重要性", "资源可用", "风险水平", "团队支持",
    "技术可行", "战略对齐", "时间约束", "长期影响"
])

# 场景：在"快速上线"和"完美打磨"之间冲突
state_a = CognitiveState.from_values([1, 1, 0, -1, 1, 0, 1, 1, 1])  # 快速上线
state_b = CognitiveState.from_values([-1, 1, 0, 1, -1, 1, 1, -1, 1])  # 完美打磨

# 生成第三选择
gen = agent.third_choice_gen
analysis = gen.analyze_conflict(state_a, state_b)
print(f"冲突维度: {analysis.disagreeing_dims}")  # [0, 3, 4, 7]
print(f"对立维度: {analysis.opposite_dims}")     # [0, 3, 4, 7]

candidates = gen.generate_all(state_a, state_b)
for c in candidates[:3]:
    print(f"[{c.strategy}] #{c.state.index} "
          f"score={c.total_score:.2f} void={c.void_ratio:.0%}")

# 生成从当前到第三选择的路径
best = candidates[0]
path = agent.pathfinder.find_path(agent._prev_state, best.state)
print(f"路径长度: {path.estimated_length}")
print(f"穿越空态: {path.through_void}")
print(f"记忆警告: {path.memory_warnings}")
print(f"记忆引导: {path.memory_guidance}")
```

---

## 参考文献

1. Howard, R. A. (1966). Decision Analysis: Applied Decision Theory. *Proceedings of the 4th IFORS Conference*.
2. Kahneman, D. (2011). *Thinking, Fast and Slow*. 双系统决策理论.
3. Schelling, T. C. (1960). *The Strategy of Conflict*. 第三选择理论.
4. 周文王. 《周易》. 卦变体系.
5. Hegel, G. W. F. (1807). *Phenomenology of Spirit*. 正-反-合辩证法.
