# BTCU Harness 记忆系统规格说明

**文档版本：v1.0**
**关联代码：`memory/state_memory.py`, `memory/transition_memory.py`, `memory/ecology.py`, `memory/trajectory.py`, `memory/climate.py`, `storage/persistence.py`**

---

## 1. 记忆系统总体架构

BTCU 的记忆不是单一的存储结构，而是**四层生态**：

```
┌──────────────────────────────────────────────────────────┐
│                    MemoryEcology                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ StateMemory │  │ Transition   │  │  Resonance     │  │
│  │ Store       │  │ Store        │  │  Network       │  │
│  │ (19683间房) │  │ (走廊)       │  │  (共振网)      │  │
│  └─────────────┘  └──────────────┘  └────────────────┘  │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Trajectory  │  │ Climate      │  │ Sense Making   │  │
│  │ (认知轨迹)  │  │ (认知气候)   │  │ (节气涌现)    │  │
│  └─────────────┘  └──────────────┘  └────────────────┘  │
└──────────────────────────────────────────────────────────┘
         │
         v
┌──────────────────────────────────────────────────────────┐
│              PersistenceLayer (持久化)                    │
│         JSON / MongoDB (未来)                            │
└──────────────────────────────────────────────────────────┘
```

### 1.1 四层记忆分类

| 记忆类型 | 生物学类比 | 代码实现 | 索引号系统 | 生命周期 |
|----------|-----------|----------|-----------|----------|
| 经验记忆 | 情景记忆 | `StateMemory` + `VisitRecord` | EL-YYYYMMDD-NNN | 单次访问到衰减遗忘 |
| 转化记忆 | 程序记忆 | `TransitionMemory` + `TransitionRecord` | TR-FROMIDX-TOIDX | 路径走通到美德/陷阱涌现 |
| 能力记忆 | 语义记忆 | `PatternLearner` + `Pattern` | CAP-NNN | 模式积累到复用率稳定 |
| 生命历程记忆 | 自传体记忆 | `CognitiveTrajectory` + `TrajectoryPoint` | LE-NNN | 全生命周期持久 |

---

## 2. 经验记忆

### 2.1 数据模型

**`VisitRecord`**（`memory/state_memory.py:24`）：

```python
@dataclass
class VisitRecord:
    timestamp: str           # ISO 8601 UTC 时间戳
    context: Dict            # 上下文：{"input": "...", "source": "llm|pattern"}
    decision: Optional[str]  # 决策描述
    outcome: Optional[str]   # 结果描述
    outcome_positive: Optional[bool]  # 结果正负
    metadata: Dict           # 元数据：天气、日期、环境等
```

**`StateMemory`**（`memory/state_memory.py:48`）——一个"房间"的完整记忆：

```python
@dataclass
class StateMemory:
    state_index: int                    # 0-19682
    visits: List[VisitRecord]           # 访问记录列表 (MAX_VISITS_KEPT=1000)
    insights: List[str]                 # 提炼洞见 (去重)
    resonance_links: Dict[int, float]   # 共振链接 {other_index: strength}
    activation: float                   # 激活水平 [0.0, ...]
    last_visited: Optional[str]         # 最后访问时间
    first_visited: Optional[str]        # 首次访问时间
    suppressed_decisions: List[str]     # 被抑制的决策（失败记录）
```

### 2.2 索引号设计

**日志索引：`EL-YYYYMMDD-NNN`**

- `EL` = Experience Log
- `YYYYMMDD` = 日期
- `NNN` = 当日序号（001-999）

示例：`EL-20260815-001` 表示 2026 年 8 月 15 日的第一条经验日志。

**状态索引：`STATE-XXXXX`**

- `XXXXX` = 0-19682 的五位数编号
- 示例：`STATE-09841` = 全空态，`STATE-16928` = 某个阳多阴少状态

### 2.3 经验记忆的访问接口

```python
# 创建/获取状态记忆
mem = ecology.state_store.get(state_index)
mem = ecology.state_store.get_or_none(state_index)  # 不创建

# 访问状态
record = ecology.state_store.visit(
    state_index=16928,
    context={"input": "评估BTCU发展方向", "source": "llm"},
    decision="focus_on_pattern_learner",
    outcome="positive_feedback",
    outcome_positive=True,
    metadata={"weather": "sunny", "mood": "focused", "session": "v03_validation"}
)

# 查询
top_visited = ecology.state_store.most_visited(n=10)
top_activated = ecology.state_store.most_activated(n=10)
best_states = ecology.state_store.highest_success(n=10, min_visits=3)
```

### 2.4 经验记忆的衰减机制

```python
# memory/state_memory.py 中的 decay 方法
def decay(self, factor: float = 0.95) -> None:
    self.activation *= factor
    # 共振链接衰减更慢（平方根）
    for idx in list(self.resonance_links.keys()):
        self.resonance_links[idx] *= (factor ** 0.5)
        if self.resonance_links[idx] < 0.01:
            del self.resonance_links[idx]  # 低于阈值时修剪
```

衰减不是删除——记忆仍然存在，只是激活水平降低。如果再次访问，激活会立即跳升 +0.3（`visit()` 方法中的强化）。

**衰减时间线**（decay_factor=0.95）：

| 步数 | 激活水平 |
|------|----------|
| 0 | 1.00 (刚访问) |
| 10 | 0.60 |
| 20 | 0.36 (约 1/e) |
| 50 | 0.08 |
| 100 | 0.006 |

### 2.5 实验记录模板

```python
experiment_record = {
    "experiment_id": "EL-20260815-001",
    "timestamp": "2026-08-15T10:30:00Z",
    "state": "STATE-16928",
    "dimension_assessment": {
        "技术深度": 1, "用户体验": 1, "创新性": 1,
        "可维护性": 1, "社区影响": 0, "商业价值": 1,
        "学习成长": 1, "风险评估": -1, "长期愿景": 1
    },
    "input": "Should BTCU prioritize deep algorithmic innovation?",
    "decision": "focus_on_algorithmic_depth",
    "outcome": "positive_user_feedback",
    "outcome_positive": True,
    "metadata": {
        "session": "v03_validation",
        "growth_stage": "school",
        "self_alignment": 0.778,
        "climate": {"polarity": 5, "phase": "expanding"}
    }
}
```

---

## 3. 转化记忆

### 3.1 数据模型

**`TransitionRecord`**（`memory/transition_memory.py:28`）：

```python
@dataclass
class TransitionRecord:
    timestamp: str
    from_index: int
    to_index: int
    changed_dimensions: List[int]  # 哪些维度发生了变化
    trigger: Optional[str]         # 触发原因
    decision: Optional[str]
    outcome: Optional[str]
    outcome_positive: Optional[bool]
    metadata: Dict
```

**`TransitionMemory`**（`memory/transition_memory.py:54`）——一条"走廊"的完整记忆：

```python
@dataclass
class TransitionMemory:
    from_index: int
    to_index: int
    records: List[TransitionRecord]  # MAX_RECORDS=500
    activation: float
    last_traversed: Optional[str]
```

### 3.2 转化记忆的涌现属性

转化记忆有三个自动涌现的属性（`memory/transition_memory.py` 属性方法）：

| 属性 | 条件 | 代码 | 含义 |
|------|------|------|------|
| `is_pathway` | traverse_count >= 5 | 反复走过的路 | 已形成的认知习惯 |
| `is_virtue` | pathway AND success_rate >= 0.7 | 成功率高的路 | 认知美德 |
| `is_trap` | pathway AND success_rate <= 0.3 | 失败率高的路 | 认知陷阱 |

### 3.3 索引号设计

**转化索引：`TR-FROMIDX-TOIDX`**

- 示例：`TR-09841-16928` 表示从全空态到状态 #16928 的转化

### 3.4 转化记忆的操作接口

```python
# 记录转化
ecology.transition_store.record(
    from_index=9841,
    to_index=16928,
    changed_dimensions=[0, 1, 2, 3, 5, 8],
    trigger="user_query",
    decision="evaluate_direction",
    outcome="positive",
    outcome_positive=True
)

# 查询路径
outgoing = ecology.transition_store.pathways_from(9841)  # 从9841出发的路
incoming = ecology.transition_store.pathways_to(16928)   # 到达16928的路
virtues = ecology.transition_store.virtues()             # 所有美德
traps = ecology.transition_store.traps()                 # 所有陷阱
```

---

## 4. 能力记忆

### 4.1 数据模型

**`Pattern`**（`mapping/pattern_learner.py:22`）：

```python
@dataclass
class Pattern:
    features: Dict[str, float]        # 提取的文本特征
    state_values: Tuple[int, ...]     # 对应的九维状态值
    state_index: int                  # 状态编号 0-19682
    input_text: str                   # 原始输入文本
    source: str = "llm"               # 来源：llm/pattern/hybrid
    confidence: float = 1.0           # 置信度
    use_count: int = 0                # 被复用次数
    success_count: int = 0            # 成功次数
```

### 4.2 能力索引号设计

**能力索引：`CAP-NNN`**

- `NNN` = 能力序号（001-999）
- 示例：`CAP-001` = 第一个学会的模式

**工作流索引：`WF-NNN`**

- 示例：`WF-001` = 第一个工作流模板

### 4.3 特征提取算法

`PatternLearner.extract_features(text)` 提取以下特征：

| 特征类型 | 具体特征 | 提取方式 |
|----------|----------|----------|
| 关键词 | top-10 高频词 | 分词后按频率排序 |
| 长度 | short/medium/long | 按字符数分档 |
| 情感 | positive/negative/uncertainty | 词表匹配 |
| 疑问类型 | what/how/why/whether | 疑问词匹配 |

### 4.4 匹配与复用

```python
# 学习新模式
pattern = learner.learn(
    input_text="Should we focus on algorithmic innovation?",
    state=CognitiveState.from_values([1, 0, 1, 0, 0, 0, 1, -1, 1]),
    source="llm",
    confidence=0.8
)

# 匹配（internalize/graduate阶段）
match = learner.match("Should we focus on algorithmic innovation?")
if match:
    pattern, similarity = match
    # 直接使用 pattern.state_values，无需调用 LLM
    # 这就是 C ∝ N_unknown 的核心机制

# 强化（根据结果调整置信度）
learner.reinforce(state_index=16928, positive=True)
# 3次成功后 confidence += 0.1
```

### 4.5 Token 节省机制

| 成长阶段 | LLM 调用条件 | 能力记忆角色 | 成本模型 |
|----------|-------------|-------------|----------|
| school | 每次都调 | 不使用 | C proportional to N_call |
| internalize | 模式不匹配时调 | 优先匹配 | C proportional to N_pattern_miss |
| graduate | 仅未知输入调 | 主力 + LLM 兜底 | C proportional to N_unknown |

**能力记忆的复用率**（`PatternLearner.reuse_rate` 属性）：

$$\text{reuse\_rate} = \frac{\text{total\_reuses}}{\text{total\_lookups}}$$

当 reuse_rate 趋近 1.0 时，Agent 几乎不再需要 LLM——能力已完全内化。

---

## 5. 生命历程记忆

### 5.1 数据模型

**`TrajectoryPoint`**（`memory/trajectory.py:18`）：

```python
@dataclass
class TrajectoryPoint:
    timestamp: str
    state_index: int
    state_values: Tuple[int, ...]   # 九维快照
    context: str                     # 认知上下文
    trigger: str                     # 触发原因
    metadata: Dict                   # 附加元数据
```

### 5.2 成长事件类型

| 事件类型 | 代码触发点 | 记录内容 |
|----------|-----------|----------|
| 首次访问 | `StateMemory.visit()` when first_visited is None | 状态编号、时间、上下文 |
| 状态迁移 | `MemoryEcology.remember()` when prev_state exists | 源/目标状态、变化维度 |
| 成长阶段推进 | `BTCUAgent.advance_stage()` | 从 school->internalize->graduate |
| 模式学习 | `PatternLearner.learn()` | 输入文本、状态、来源 |
| 模式匹配 | `PatternLearner.match()` when matched | 匹配的模式、相似度 |
| 自我强化 | `NLPSelfLayer.reinforce()` | 正/负强化、力度、层名 |
| 认知节气发现 | `MemoryEcology.sense_making()` | 节气类型、描述、强度 |
| 第三选择生成 | `ThirdChoiceGenerator.generate_all()` | 候选策略、评分 |

### 5.3 生命历程索引号

**生命事件索引：`LE-NNN`**

- `NNN` = 生命事件序号（001-999+）
- 示例：`LE-001` = Agent 的第一次认知活动

### 5.4 轨迹分析接口

```python
# 基础查询
trajectory.length          # 总步数
trajectory.unique_states   # 访问过的不同状态数
trajectory.coverage        # 覆盖率 = unique / 19683

# 动态分析
velocity = trajectory.velocity(window=10)         # 认知速度
center = trajectory.cognitive_center(window=50)   # 认知重心
drift = trajectory.drift(window=50)               # 认知漂移
ratio = trajectory.explore_ratio()                # 探索率

# 模式发现
clusters = trajectory.detect_clusters(radius=3)   # 聚类
cycles = trajectory.detect_cycles(min_length=2, max_length=5)  # 周期
```

### 5.5 阶段划分

| 阶段 | 触发条件 | 代码位置 | 生命历程特征 |
|------|----------|----------|-------------|
| school | Agent 初始化 | `BTCUAgent.__init__(growth_stage="school")` | 高 LLM 依赖，低模式复用，探索率波动大 |
| internalize | `advance_stage()` 首次调用 | `agent.py` | 模式开始积累，reuse_rate 上升，LLM 调用下降 |
| graduate | `advance_stage()` 二次调用 | `agent.py` | 自主认知为主，仅在盲区调 LLM，轨迹形成稳定模式 |

---

## 6. 索引号系统总表

| 索引类型 | 格式 | 示例 | 用途 | 存储位置 |
|----------|------|------|------|----------|
| 经验日志 | EL-YYYYMMDD-NNN | EL-20260815-001 | 单次认知访问记录 | StateMemory.visits[].metadata |
| 生命事件 | LE-NNN | LE-042 | Agent 生命周期事件 | TrajectoryPoint.metadata |
| 能力索引 | CAP-NNN | CAP-007 | 已学会的投影模式 | Pattern.metadata |
| 工作流索引 | WF-NNN | WF-003 | 工作流模板 | 未来扩展 |
| 状态索引 | STATE-XXXXX | STATE-16928 | 19683 空间中的位置 | CognitiveState.index |
| 转化索引 | TR-XXXXX-XXXXX | TR-09841-16928 | 状态间转化路径 | TransitionMemory key |

---

## 7. 认知节气与气候

### 7.1 静态节气（`MemoryEcology.sense_making()`）

| 节气类型 | 发现条件 | 代码 | 应用 |
|----------|----------|------|------|
| attractor | visit_count >= 5 的状态 | `state_store.most_visited(n=10)` | 自我层参考、决策偏好 |
| virtue | pathway 且 success_rate >= 0.7 | `transition_store.virtues()` | 路径推荐 |
| trap | pathway 且 success_rate <= 0.3 | `transition_store.traps()` | 路径警告 |
| blind_spot | 从未访问的状态 | 全空间减去已访问 | 探索引导 |
| resonance | 共激活 >= 3 次的状态对 | `_resonance_discoveries` | 关联推荐 |

### 7.2 动态气候（`CognitiveClimate`）

| 气候指标 | 代码方法 | 值域 | 含义 |
|----------|----------|------|------|
| polarity_trend | `_compute_trend()` | 实数 | 正=趋向阳，负=趋向阴 |
| polarity_volatility | `_compute_volatility()` | [0, +inf) | 极性波动剧烈程度 |
| exploration_phase | recent_new_state_rate 判断 | expanding/consolidating/stagnant | 探索阶段 |
| climate_zones | `_identify_zones()` | List[ClimateZone] | 活跃区域 |
| drift_magnitude | 前后半段中心距离 | [0, 18] | 认知漂移幅度 |
| dominant_period | `trajectory.detect_cycles()` | 正整数 | 主导周期 |
| rhythm_regularity | 同周期占比 | [0, 1] | 节律稳定性 |

---

## 8. 记忆传承

### 8.1 导出

```python
# 导出完整记忆生态
legacy = ecology.export_legacy()
# 包含：所有 StateMemory、所有 TransitionMemory、共振网络、轨迹

# 导出为文件
agent.save()
# PersistenceLayer.save() 将 ecology + trajectory + patterns + self + climate 写入 JSON
```

### 8.2 导入

```python
# 从文件恢复
agent2 = BTCUAgent(storage_path="cognitive_legacy.json")
agent2.load()
# 完整恢复：ecology, trajectory, pattern_learner, self_layer, climate, growth_stage

# 从另一个 Agent 导入
legacy = agent1.export_memory()
agent2.import_memory(legacy)
```

### 8.3 记忆传承的应用场景

| 场景 | 方法 | 说明 |
|------|------|------|
| Agent 重启 | `save()` + `load()` | 跨会话保持认知连续性 |
| Agent 迁移 | `export_memory()` + `import_memory()` | 将认知经验转移到新 Agent |
| Agent 协作 | 共享 `export_legacy()` | 两个 Agent 共享认知空间（实验性） |
| 认知审计 | 读取 JSON 文件 | 人类检查 Agent 的认知历史和状态 |
| 认知重置 | 删除 JSON 文件 | 清除所有记忆，从零开始（谨慎） |

---

## 9. 记忆系统的数据一致性

### 9.1 当前实现（JSON 持久化）

- **原子性**：`PersistenceLayer.save()` 使用 `json.dump()` 一次性写入，要么完整写入要么不写入
- **一致性**：所有模块（ecology, trajectory, patterns, self, climate）在同一个 JSON 中，同时保存
- **隔离性**：单 Agent 单文件，无并发问题
- **持久性**：写入磁盘后即持久，但无 WAL（Write-Ahead Log）

### 9.2 未来 MongoDB 实现

```javascript
// 集合设计
db.state_memories      // 19683 个文档，索引 state_index
db.transition_memories // 转化记忆，复合索引 (from_index, to_index)
db.trajectories        // 轨迹点，索引 timestamp
db.patterns            // 模式，索引 state_index
db.self_levels         // NLP 自我层，索引 name
db.climate_snapshots   // 气候快照，索引 step
```

详见 `docs/storage_design.md`。

---

## 参考文献

1. Tulving, E. (1972). Episodic and semantic memory. *Organization of Memory*.
2. Squire, L. R. (1992). Declarative and nondeclarative memory. *Multiple Memory Systems*.
3. Dilts, R. (1996). *Visionary Leadership Skills*. 逻辑层级模型.
4. Baddeley, A. (1992). Working memory. *Science*.
5. McClelland, J. L., et al. (1995). Why there are complementary learning systems in the hippocampus and neocortex. *Neural Computation*.
