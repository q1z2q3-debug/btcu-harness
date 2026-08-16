# BTCU Harness 认知投影器实现方案

**文档版本：v1.0**
**关联代码：`mapping/projector.py`, `mapping/dimension_adapter.py`, `mapping/pattern_learner.py`**

---

## 1. 概述

认知投影器是 Agent 的"眼睛"——将自然语言输入投影到九维三元认知空间，获得一个 0-19682 的状态编号。

```
输入文本 -> [投影器] -> CognitiveState (9维, 每维 {-1,0,+1})
                        |
                        v
                    状态编号 0-19682
```

### 1.1 投影器类型

| 类型 | 成长阶段 | 代码实现 | LLM 依赖 |
|------|----------|----------|----------|
| LLM 投影器 | school | `InputProjector._project_with_llm()` | 每次调用 |
| 模式投影器 | internalize/graduate | `InputProjector._project_with_patterns()` | 不调用 |
| 混合投影器 | internalize | 模式优先，LLM 兜底 | 仅新模式 |
| 规则投影器 | 未来扩展 | 自定义规则映射 | 不调用 |
| 人机协同投影器 | 未来扩展 | LLM + 人工反馈 | 可配置 |

---

## 2. LLM 投影器

### 2.1 工作流程

```python
# mapping/projector.py _project_with_llm 方法
def _project_with_llm(self, input_text, llm_callback) -> ProjectionResult:
    # 1. 构造提示词
    dim_list = "\n".join(f"  {i+1}. {label}" for i, label in enumerate(self.dim_set.labels))
    prompt = PROJECTION_PROMPT_TEMPLATE.format(
        input_text=input_text,
        dimension_list=dim_list,
        dim1=self.dim_set.labels[0],
    )

    # 2. 调用 LLM
    response = llm_callback(prompt)

    # 3. 解析 JSON 响应
    parsed = json.loads(response)
    assessments = parsed.get("assessments", [])

    # 4. 提取每维值并 clamp 到 [-1, 1]
    values = []
    dim_assessments = {}
    for i, label in enumerate(self.dim_set.labels):
        if i < len(assessments):
            val = int(assessments[i].get("value", 0))
            values.append(max(-1, min(1, val)))  # clamp
            dim_assessments[label] = assessments[i].get("reason", "")
        else:
            values.append(0)
            dim_assessments[label] = "no assessment"

    # 5. 构造 CognitiveState
    state = CognitiveState.from_values(values)
    return ProjectionResult(
        state=state,
        dimension_assessments=dim_assessments,
        confidence=0.8,
        source="llm",
    )
```

### 2.2 提示词模板

```
PROJECTION_PROMPT_TEMPLATE = """
You are a cognitive projection engine for the BTCU Harness.

Given an input, evaluate it across 9 dimensions. Each dimension must be
assigned a value of -1 (negative/yin), 0 (neutral/void), or +1 (positive/yang).

Dimensions:
{dimension_list}

Input: <input>{input_text}</input>

Respond as JSON:
{{
  "assessments": [
    {{"value": -1|0|1, "reason": "brief explanation"}},
    ... (9 items, one per dimension)
  ]
}}

The first dimension ({dim1}) is the most important. Consider the input
carefully from multiple angles before responding.
"""
```

### 2.3 降级处理

```python
# 如果 LLM 返回非 JSON：
except (json.JSONDecodeError, ValueError, KeyError):
    return ProjectionResult(
        state=CognitiveState.all_void(),  # 全空态
        dimension_assessments={l: "parse_error" for l in self.dim_set.labels},
        confidence=0.0,
        source="llm_parse_error",
    )
```

---

## 3. 模式投影器

### 3.1 PatternLearner 特征提取

`PatternLearner.extract_features(text)` 提取以下特征：

```python
def extract_features(self, text: str) -> Dict[str, float]:
    features = {}

    # 1. 关键词特征 (top-10)
    words = self._tokenize(text)
    word_counts = Counter(words)
    top_words = word_counts.most_common(10)
    for word, count in top_words:
        features[f"kw_{word}"] = count / len(words)

    # 2. 长度特征
    text_len = len(text)
    if text_len < 50:
        features["len_short"] = 1.0
    elif text_len < 200:
        features["len_medium"] = 1.0
    else:
        features["len_long"] = 1.0

    # 3. 情感特征
    features["sent_positive"] = sum(1 for w in words if w in self.POSITIVE_WORDS) / max(1, len(words))
    features["sent_negative"] = sum(1 for w in words if w in self.NEGATIVE_WORDS) / max(1, len(words))
    features["sent_uncertain"] = sum(1 for w in words if w in self.UNCERTAINTY_WORDS) / max(1, len(words))

    # 4. 疑问类型
    for marker, name in self.QUESTION_MARKERS:
        if marker in text.lower():
            features[f"q_{name}"] = 1.0

    return features
```

### 3.2 相似度计算

```python
def similarity(self, features_a: Dict[str, float], features_b: Dict[str, float]) -> float:
    """余弦相似度"""
    all_keys = set(features_a.keys()) | set(features_b.keys())
    dot = sum(features_a.get(k, 0) * features_b.get(k, 0) for k in all_keys)
    norm_a = sum(v ** 2 for v in features_a.values()) ** 0.5
    norm_b = sum(v ** 2 for v in features_b.values()) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
```

### 3.3 匹配流程

```python
def match(self, input_text: str) -> Optional[Tuple[Pattern, float]]:
    features = self.extract_features(input_text)

    best_pattern = None
    best_sim = 0.0

    for pattern in self.patterns:
        sim = self.similarity(features, pattern.features)
        if sim > best_sim:
            best_sim = sim
            best_pattern = pattern

    if best_pattern and best_sim >= self.similarity_threshold:
        best_pattern.use_count += 1
        return best_pattern, best_sim

    return None  # 无匹配——需要 LLM
```

---

## 4. 成长阶段与投影策略

### 4.1 school 阶段

```python
if self.growth_stage == "school":
    return self._project_with_llm(input_text, llm_callback)
```

每次都调用 LLM，同时将结果存入 PatternLearner 供未来匹配。

### 4.2 internalize 阶段

```python
elif self.growth_stage == "internalize":
    # 先尝试模式匹配
    pattern_result = self._project_with_patterns(input_text)
    if pattern_result is not None:
        return pattern_result  # 模式命中，不调 LLM
    # 模式未命中，调 LLM
    return self._project_with_llm(input_text, llm_callback)
```

### 4.3 graduate 阶段

```python
else:  # graduate
    pattern_result = self._project_with_patterns(input_text)
    if pattern_result is not None:
        return pattern_result
    # 模式未命中——仅在有 LLM 时调用
    if llm_callback:
        return self._project_with_llm(input_text, llm_callback)
    # 无 LLM——返回空态（自主兜底）
    return ProjectionResult(
        state=CognitiveState.all_void(),
        dimension_assessments={l: "unknown" for l in self.dim_set.labels},
        confidence=0.0,
        source="void_fallback",
    )
```

---

## 5. 规则投影器（未来扩展）

### 5.1 设计

```python
class RuleProjector:
    """基于人工定义的特征映射规则进行投影。"""

    def __init__(self, dim_set: DimensionSet):
        self.dim_set = dim_set
        self.rules: List[ProjectionRule] = []

    def add_rule(self, dimension_index: int, keywords: List[str],
                 value: int, reason: str) -> None:
        """添加规则：如果输入包含关键词，则该维度取 value。"""
        self.rules.append(ProjectionRule(
            dimension_index=dimension_index,
            keywords=keywords,
            value=value,
            reason=reason,
        ))

    def project(self, input_text: str) -> ProjectionResult:
        values = [0] * 9  # 默认全空
        assessments = {}

        for i, label in enumerate(self.dim_set.labels):
            assessments[label] = "no rule matched"
            for rule in self.rules:
                if rule.dimension_index == i:
                    if any(kw in input_text.lower() for kw in rule.keywords):
                        values[i] = rule.value
                        assessments[label] = rule.reason
                        break

        return ProjectionResult(
            state=CognitiveState.from_values(values),
            dimension_assessments=assessments,
            confidence=0.6,  # 规则投影置信度低于 LLM
            source="rule",
        )
```

### 5.2 使用示例

```python
rule_proj = RuleProjector(dim_set)
rule_proj.add_rule(0, ["创新", "突破", "novel", "innovation"], 1, "创新信号")
rule_proj.add_rule(0, ["保守", "传统", "conservative"], -1, "保守信号")
rule_proj.add_rule(1, ["用户体验", "UX", "易用"], 1, "用户导向")
rule_proj.add_rule(7, ["风险", "danger", "risk"], -1, "风险信号")
```

---

## 6. 人机协同投影器（未来扩展）

### 6.1 设计

```python
class HumanInTheLoopProjector:
    """LLM 投影 + 人工反馈修正。"""

    def __init__(self, llm_projector, feedback_store):
        self.llm_projector = llm_projector
        self.feedback_store = feedback_store  # 存储人工修正

    def project(self, input_text: str, llm_callback) -> ProjectionResult:
        # 1. LLM 投影
        result = self.llm_projector.project(input_text, llm_callback)

        # 2. 检查是否有历史人工反馈
        feedback = self.feedback_store.get(input_text)
        if feedback:
            # 应用人工修正
            corrected_values = list(result.state.values)
            for dim, val in feedback.corrections.items():
                corrected_values[dim] = val
            result = ProjectionResult(
                state=CognitiveState.from_values(corrected_values),
                dimension_assessments=result.dimension_assessments,
                confidence=0.95,  # 人工修正后高置信度
                source="hybrid",
            )

        return result

    def record_feedback(self, input_text: str, corrections: Dict[int, int]):
        """记录人工修正，供未来使用。"""
        self.feedback_store.save(input_text, corrections)
```

---

## 7. 训练方法：三值量化

### 7.1 Straight-Through Estimator (STE)

如果使用神经网络做投影，连续输出需要量化为三值。STE 的方法：

```python
import torch

class TritQuantizer(torch.autograd.Function):
    """三值量化器：前向量化为 {-1, 0, 1}，反向传播用连续值梯度。"""

    @staticmethod
    def forward(ctx, x):
        # 量化规则：
        # x > 0.5 -> 1
        # x < -0.5 -> -1
        # else -> 0
        return torch.where(x > 0.5, torch.ones_like(x),
                          torch.where(x < -0.5, torch.ones_like(x) * -1,
                                     torch.zeros_like(x)))

    @staticmethod
    def backward(ctx, grad_output):
        # 直通梯度：量化操作的梯度 = 恒等梯度
        return grad_output
```

### 7.2 温度退火

训练初期使用"软"量化（温度高，接近连续），逐步降低温度使输出趋近三值：

```python
def soft_trit(x, temperature=1.0):
    """软三值化：温度越高越接近连续，温度越低越接近三值。"""
    # 使用可微分近似
    soft_yang = torch.sigmoid((x - 0.5) / temperature)
    soft_yin = torch.sigmoid((-x - 0.5) / temperature)
    return soft_yang - soft_yin  # [-1, 1] 连续，趋近 {-1, 0, 1}
```

---

## 8. 投影质量评估

### 8.1 置信度

| 来源 | 置信度 | 含义 |
|------|--------|------|
| LLM 成功解析 | 0.8 | LLM 正常返回有效 JSON |
| 模式匹配 | sim * 0.8 | 相似度越高置信度越高 |
| 规则匹配 | 0.6 | 规则覆盖时中等置信 |
| 人工修正 | 0.95 | 人工确认后最高 |
| LLM 解析失败 | 0.0 | 返回全空态 |
| 无 LLM 兜底 | 0.0 | graduate 阶段无 LLM 时 |

### 8.2 投影一致性

同一输入多次投影应产生相同状态。LLM 投影的不一致性来自 temperature > 0：

```python
# 测试投影一致性
results = [projector.project("same input", llm_cb) for _ in range(10)]
states = [r.state.index for r in results]
consistency = len(set(states)) / len(states)  # 0.1 = 完全不一致, 1.0 = 完全一致
```

建议：投影用 LLM 设置 temperature=0（`LLMBridge._api_call` 中已设 temperature=0.3，建议投影场景降为 0）。

---

## 参考文献

1. Bengio, Y., et al. (2013). Estimating or Propagating Gradients Through Stochastic Neurons. *arXiv*.
2. Courbariaux, M., et al. (2016). Binarized Neural Networks. *NeurIPS*.
3. Tang, W., et al. (2017). Quantized Neural Networks. *ICLR Workshop*.
