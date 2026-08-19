# BTCU Harness 开放性与自创机制

**文档版本：v1.0**
**关联代码：`mapping/dimension_adapter.py`（DimensionSet.lock）, `agent.py`（init_project）**

---

## 1. 设计原则："仅封闭三元，其余开放"

BTCU 的核心哲学是**最小约束、最大涌现**。系统唯一定义的是：

- 三态基元 $\{-1, 0, +1\}$（不可改变）
- 九维结构（维度数固定，维度含义可适配）
- 编码规则 0-19682（数学性质，不可改变）

除此之外的一切——维度标签、状态语义、运算方式、模块组合——都是开放的，可以由 Agent 自己定义和扩展。

---

## 2. 维度自创机制

### 2.1 当前的维度适配流程

```
项目启动
    |
    v
DimensionAdapter.adapt_with_llm(project_description, llm_callback)
    |
    | LLM 分析项目领域，建议 9 个维度
    v
DimensionSet(labels=[...], domain="custom", locked=False)
    |
    v
DimensionSet.lock()  # 锁定，不可再改
    |
    v
项目期间固定使用这 9 个维度
```

### 2.2 维度自创的触发条件（未来扩展）

Agent 在运行过程中可以发现当前九维不足以表达某些认知输入，触发维度自创：

| 触发条件 | 检测方法 | 示例 |
|----------|----------|------|
| 持续空态 | 连续 N 次投影有 >6 维为空 | 输入始终无法被当前维度有效评估 |
| 低置信度 | LLM 投影置信度持续 < 0.3 | LLM 无法将输入映射到现有维度 |
| 盲区聚集 | 某类输入始终映射到同一状态 | 不同输入被"压缩"到同一状态 |
| 人类反馈 | 用户指出维度不足 | "你漏考虑了安全维度" |

### 2.3 维度自创流程（设计）

```python
class DimensionCreator:
    """Agent 自主创建新维度的机制。"""

    def check_need_for_new_dimension(self, recent_projections: List[ProjectionResult]) -> bool:
        """检测是否需要新维度。"""
        # 条件1: 连续 10 次投影中 >7 次有 >=6 维为空
        void_heavy = sum(1 for p in recent_projections[-10:]
                        if p.state.void_count >= 6)
        if void_heavy >= 7:
            return True

        # 条件2: 最近 20 次投影的平均置信度 < 0.3
        avg_conf = sum(p.confidence for p in recent_projections[-20:]) / 20
        if avg_conf < 0.3:
            return True

        return False

    def propose_new_dimension(self, recent_inputs: List[str],
                               llm_callback) -> Optional[str]:
        """让 LLM 分析最近输入，提议新维度。"""
        prompt = f"""
        The following inputs could not be well-captured by the current
        9 dimensions. Analyze them and propose ONE new dimension that
        would better capture their cognitive content.

        Recent inputs:
        {chr(10).join(f'- {inp[:100]}' for inp in recent_inputs[-20:])}

        Current dimensions: {self.dim_set.labels}

        Propose a new dimension name (2-4 Chinese characters or 1-3 English words):
        """
        response = llm_callback(prompt)
        return response.strip()

    def validate_dimension(self, new_label: str, test_inputs: List[str],
                           llm_callback) -> bool:
        """验证新维度的有效性。"""
        # 用新维度重新投影测试输入
        # 如果区分度提升 > 20%，则接受
        old_states = set()
        for inp in test_inputs:
            result = self.projector.project(inp, llm_callback)
            old_states.add(result.state.index)

        # 加入新维度后（替换最不活跃的维度）
        # 重新投影
        new_states = set()
        # ... (实现省略)

        improvement = len(new_states - old_states) / len(test_inputs)
        return improvement > 0.2
```

### 2.4 维度替换规则

新增维度不是变成十维（会破坏 3^9=19683 结构），而是**替换最不活跃的维度**：

```python
def find_least_active_dimension(self, recent_projections: List[ProjectionResult]) -> int:
    """找到最近使用率最低的维度。"""
    activity = [0] * 9
    for proj in recent_projections[-100:]:
        for i in range(9):
            if proj.state[i].value != 0:  # 非空 = 活跃
                activity[i] += 1
    return activity.index(min(activity))  # 最不活跃的维度索引
```

### 2.5 维度替换的影响

替换维度后：
- 旧维度的 `StateMemory` 语义全部失效（因为编码改变）
- 必须重新初始化记忆生态，或做维度迁移
- 这是一个**高风险操作**，需要人类确认

---

## 3. 运算自创机制

### 3.1 当前的固定运算

BTCU 当前定义的运算（`core/trit.py`）：

| 运算 | 代码 | 含义 |
|------|------|------|
| negate | `Trit.negate()` | 取反：YIN<->YANG, VOID不变 |
| add | `Trit.add()` | 加法：-1+1=0（公理） |
| multiply | `Trit.multiply()` | 乘法：VOID是零因子 |

### 3.2 运算自创的设计

Agent 可以在实践中发现新的复合运算模式，将其提炼为"认知运算"：

```python
class CognitiveOperation:
    """Agent 自创的认知运算。"""
    name: str                    # 运算名称
    input_dims: List[int]        # 涉及的输入维度
    operation: Callable          # 运算函数
    output_interpretation: str   # 输出含义
    validation_count: int        # 验证次数
    success_rate: float          # 成功率

# 示例：Agent 发现"极性翻转"运算
def polarity_flip(state: CognitiveState, dims: List[int]) -> CognitiveState:
    """对指定维度做极性翻转（阴->阳, 阳->阴, 空不变）。"""
    values = list(state.values)
    for d in dims:
        values[d] = -values[d]
    return CognitiveState.from_values(values)

# 示例：Agent 发现"空态注入"运算
def void_injection(state: CognitiveState, dims: List[int]) -> CognitiveState:
    """将指定维度置空。"""
    values = list(state.values)
    for d in dims:
        values[d] = 0
    return CognitiveState.from_values(values)
```

### 3.3 运算发现的机制

```python
class OperationDiscovery:
    """从轨迹中自动发现运算模式。"""

    def discover_from_trajectory(self, trajectory: CognitiveTrajectory) -> List[CognitiveOperation]:
        """分析轨迹中的重复转化模式。"""
        operations = []

        # 检测周期性转化
        cycles = trajectory.detect_cycles()
        for cycle in cycles:
            if cycle.period == 2:
                # A -> B -> A 模式：可能是"翻转"运算
                state_a = CognitiveState.from_index(cycle.pattern[0])
                state_b = CognitiveState.from_index(cycle.pattern[1])
                diff_dims = state_a.diff_dimensions(state_b)

                # 检查是否是极性翻转
                is_flip = all(
                    state_a[d].value + state_b[d].value == 0
                    for d in diff_dims
                )
                if is_flip:
                    operations.append(CognitiveOperation(
                        name="polarity_flip",
                        input_dims=diff_dims,
                        operation=polarity_flip,
                        validation_count=cycle.occurrences,
                    ))

        return operations
```

---

## 4. 模块自创机制

### 4.1 自涌现模块的生命周期

```
检测到重复模式
    |
    v
提议新模块（从模式中提取规则）
    |
    v
验证模块有效性（在测试集上运行）
    |
    v
[通过] -> 纳入正式模块 / [未通过] -> 丢弃
    |
    v
运行监控（跟踪模块的表现）
    |
    v
[表现好] -> 保持 / [表现差] -> 降级或移除
```

### 4.2 模块合法性验证标准

| 标准 | 检查方法 | 阈值 |
|------|----------|------|
| 语义不冲突 | 新模块的输出不与现有模块矛盾 | 冲突率 < 10% |
| 增量价值 | 新模块覆盖的输入之前无法处理 | 覆盖率 > 5% |
| 稳定性 | 多次运行同一输入产生相同输出 | 一致性 > 90% |
| 安全性 | 不破坏系统核心约束（三元、九维、编码） | 零违规 |
| 成本效益 | 新模块节省的 LLM 调用 > 维护成本 | ROI > 2.0 |

### 4.3 模块注册表

```python
class ModuleRegistry:
    """自创模块的注册表。"""

    def __init__(self):
        self.modules: Dict[str, RegisteredModule] = {}
        self.performance_history: Dict[str, List[float]] = {}

    def register(self, module: CognitiveOperation, validation_results: Dict) -> bool:
        """注册新模块。"""
        # 检查合法性
        if not self._validate(module, validation_results):
            return False

        self.modules[module.name] = RegisteredModule(
            module=module,
            registered_at=_now_iso(),
            status="active",
            validation=validation_results,
        )
        return True

    def evaluate(self, module_name: str) -> str:
        """评估模块表现，决定保持/降级/移除。"""
        history = self.performance_history.get(module_name, [])
        if len(history) < 10:
            return "warming_up"

        recent_avg = sum(history[-10:]) / 10
        if recent_avg > 0.7:
            return "keep"
        elif recent_avg > 0.3:
            return "degraded"
        else:
            return "remove"
```

---

## 5. 开放性的安全边界

### 5.1 不可变的核心约束

以下约束**任何自创机制都不可触碰**：

1. **三元基元**：$\{-1, 0, +1\}$ 不可扩展为四元或更多
2. **九维结构**：维度数固定为 9，不可增减
3. **编码规则**：0-19682 的整数编码不可改变
4. **公理**：$-1 + 1 = 0$ 不可修改
5. **空态不变性**：全空态 #9841 的取反对合性质不可破坏

### 5.2 可变的内容

1. **维度标签**：通过 `DimensionAdapter` 适配（但锁定后不可改）
2. **状态语义**：完全由 `StateMemory` 经验涌现
3. **运算组合**：Agent 可发现新的复合运算
4. **记忆策略**：衰减因子、共振半径等参数可调
5. **决策策略**：第三选择的策略和权重可扩展

### 5.3 人类控制权保留

所有自创机制都需要人类确认才能生效：

| 操作 | 自动程度 | 人类确认 |
|------|----------|----------|
| 学习新模式 | 全自动 | 不需要 |
| 发现认知节气 | 全自动 | 不需要 |
| 提议新维度 | 半自动 | 需要确认 |
| 替换维度 | 不自动 | 必须人类触发 |
| 注册新运算 | 半自动 | 需要确认 |
| 修改核心参数 | 不自动 | 必须人类触发 |

---

## 6. 自创机制与成长阶段的对应

| 成长阶段 | 自创能力 | 说明 |
|----------|----------|------|
| school | 无 | 一切依赖 LLM，无自主性 |
| internalize | 模式学习 | 自动积累投影模式，但不能改变结构 |
| graduate | 模式 + 运算发现 | 可从轨迹中发现新运算，需人类确认后注册 |
| 未来: master | 全部 | 可提议新维度、新模块，人类确认后生效 |

---

## 参考文献

1. Minsky, M. (1986). *The Society of Mind*. 自组织与涌现.
2. Hofstadter, D. (1979). *Godel, Escher, Bach*. 自指与涌现.
3. Wolfram, S. (2002). *A New Kind of Science*. 元胞自动机与涌现.
4. Kauffman, S. (1993). *The Origins of Order*. 自组织与进化.
