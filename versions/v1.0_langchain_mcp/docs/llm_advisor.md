# BTCU Harness — LLM 顾问层规格说明

> 文档版本：1.0  
> 模块路径：`btcu_harness/llm/`  
> 关联模块：`agent.py`、`pattern_learner.py`、`climate.py`

---

## 1. 概述

LLM 在 BTCU Harness 中承担三个角色，按项目生命周期依次激活：

| 角色 | 调用频率 | 触发阶段 | 职责 |
|------|----------|----------|------|
| 维度适配器 | 每项目一次 | 项目初始化 | 将自然语言项目描述映射为内部维度标签集 |
| 输入投影器 | 视成长阶段而定 | 每次输入处理 | 将外部输入文本投影到已适配的维度空间，产出结构化评估 |
| 顾问 | 视成长阶段而定 | graduate 阶段 | 对真正未知的情况给出自由形式建议 |

三个角色的调用频率随成长阶段递减，体现了系统从"依赖 LLM"到"自主决策"的渐进脱钩设计：

```
school       →  每次调用 LLM（投影 + 建议）
internalize  →  仅在模式未命中时调用（投影），未访问状态时调用（建议）
graduate     →  仅在真正未知时调用（投影 + 建议）
```

---

## 2. 代码参考：LLMBridge 类

`LLMBridge` 是 LLM 层的统一入口，位于 `llm/bridge.py`。它封装了 API 调用、回调机制和成本统计。

### 2.1 构造函数

```python
class LLMBridge:
    def __init__(
        self,
        api_base: str,          # OpenAI 兼容 API 基地址
        api_key: str,            # API 密钥
        model: str,              # 模型名称，如 "gpt-4o-mini"
        callback: Callable | None = None  # 自定义回调（替代 HTTP 调用）
    ):
        self.api_base = api_base
        self.api_key = api_key
        self.model = model
        self.callback = callback

        # 成本统计
        self.total_calls = 0
        self.dimension_adaptation_calls = 0
        self.projection_calls = 0
        self.advisor_calls = 0
```

`callback` 参数允许注入自定义调用逻辑（如本地模型路由），不传则走默认 HTTP 请求。

### 2.2 核心方法

```python
def __call__(self, prompt: str) -> str:
    """便捷调用入口，等价于 query()。"""
    return self.query(prompt)

def query(self, prompt: str) -> str:
    """发送 prompt 到 LLM，返回原始文本响应。"""
    ...

def adapt_dimensions(self, project_description: str) -> str:
    """维度适配：将项目描述转换为维度标签 JSON。"""
    ...

def project_input(self, input_text: str, dimension_labels: list[str]) -> str:
    """输入投影：将输入文本投影到维度空间，返回评估 JSON。"""
    ...

def advise(self, question: str, context: str | None = None) -> str:
    """顾问：针对未知情况给出自由形式建议。"""
    ...
```

### 2.3 成本统计

`cost_stats` 属性返回当前累计的调用统计快照：

```python
@property
def cost_stats(self) -> dict:
    return {
        "total_calls": self.total_calls,
        "dimension_adaptation_calls": self.dimension_adaptation_calls,
        "projection_calls": self.projection_calls,
        "advisor_calls": self.advisor_calls,
    }
```

| 统计字段 | 含义 |
|----------|------|
| `total_calls` | 所有 LLM 调用总次数 |
| `dimension_adaptation_calls` | 维度适配调用次数（理论最大值为 1） |
| `projection_calls` | 输入投影调用次数 |
| `advisor_calls` | 顾问调用次数 |

---

## 3. LLM 调用时机

调用决策由 `agent.py` 的 `process()` 方法驱动，与成长阶段强绑定。

### 3.1 决策树

```
输入到达
  │
  ├─ school 阶段
  │    ├─ step 2: 始终调用 LLM 投影
  │    └─ step 7: 始终调用 LLM 建议
  │
  ├─ internalize 阶段
  │    ├─ step 2: PatternLearner 匹配 → 未命中时调用 LLM 投影
  │    └─ step 7: 状态未被访问过时调用 LLM 建议
  │
  └─ graduate 阶段
       ├─ step 2: PatternLearner 匹配 → 未命中 + 低相似度 → 调用 LLM 投影
       └─ step 7: 仅在真正未知状态时调用 LLM 建议
```

### 3.2 各阶段调用条件

| 阶段 | 投影调用条件 | 建议调用条件 | 预期调用比例 |
|------|-------------|-------------|-------------|
| school | 始终调用 | 始终调用 | 100% 输入 |
| internalize | 模式未命中 (`pattern_hit == False`) | 状态未访问过 | 约 30%–50% 输入 |
| graduate | 模式未命中 + 确认未知 | 真正未知状态 | < 10% 输入 |

### 3.3 agent.py 中的调用位置

```python
# agent.py — process() 简化示意

def process(self, input_text: str) -> State:
    # step 1: 成长阶段判定
    stage = self.growth_stage()

    # step 2: 投影决策
    if stage == "school":
        raw = self.llm.project_input(input_text, self.dimensions)
        state = self._parse_projection(raw)
    elif stage == "internalize":
        matched = self.pattern_learner.match(input_text)
        if matched and matched.similarity >= 0.7:
            state = matched.state  # 复用已知模式
        else:
            raw = self.llm.project_input(input_text, self.dimensions)  # 模式未命中
            state = self._parse_projection(raw)
    elif stage == "graduate":
        matched = self.pattern_learner.match(input_text)
        if matched and matched.similarity >= 0.7:
            state = matched.state
        elif matched and matched.similarity >= 0.5:
            state = matched.state  # 低置信度但仍复用
        else:
            raw = self.llm.project_input(input_text, self.dimensions)  # 真正未知
            state = self._parse_projection(raw)

    # step 3-6: 状态转换、执行、记忆更新 ...

    # step 7: 建议决策
    if stage == "school":
        advice = self.llm.advise(f"输入: {input_text}", context=self.memory)
    elif stage == "internalize":
        if not self.pattern_learner.is_visited(state):
            advice = self.llm.advise(f"未访问状态: {state}", context=self.memory)
    elif stage == "graduate":
        if self._is_truly_unknown(state):
            advice = self.llm.advise(f"未知状态: {state}", context=self.memory)

    return state
```

---

## 4. 输入/输出格式

### 4.1 维度适配

使用 `DIMENSION_ADAPTATION_PROMPT` 模板，将项目描述转化为维度标签集。

**输入示例：**

```
项目描述：一个基于 Python 的自动化测试框架，关注代码覆盖率、测试稳定性、执行速度。
```

**期望输出（JSON）：**

```json
{
  "dimensions": [
    "code_coverage",
    "test_stability",
    "execution_speed"
  ]
}
```

### 4.2 输入投影

使用 `PROJECTION_PROMPT_TEMPLATE` 模板，将输入文本投影到维度空间。

**输入示例：**

```
输入文本：测试套件运行时间从 30s 增长到 120s，覆盖率从 85% 降至 70%。
维度标签：["code_coverage", "test_stability", "execution_speed"]
```

**期望输出（JSON）：**

```json
{
  "assessments": [
    {"value": -1, "reason": "覆盖率从 85% 降至 70%，显著下降"},
    {"value": 0, "reason": "未提及测试稳定性变化"},
    {"value": -1, "reason": "执行时间增长 4 倍，严重恶化"}
  ]
}
```

`value` 取值约束：

| 值 | 含义 |
|----|------|
| `-1` | 该维度呈现负面趋势 |
| `0` | 该维度无变化或信息不足 |
| `1` | 该维度呈现正面趋势 |

### 4.3 顾问建议

自由形式问答，附加记忆上下文。无固定 JSON 格式约束。

```python
advice = self.llm.advise(
    question="当前所有测试执行缓慢且覆盖率持续下降，应优先修复哪个？",
    context=self.memory.summary()  # 最近 N 条状态转换历史
)
```

---

## 5. 降级策略

当 LLM 不可用或响应异常时，系统按以下策略逐级降级，确保不中断主流程：

| 异常类型 | 触发条件 | 降级行为 | 影响阶段 |
|----------|----------|----------|----------|
| LLM 不可用 | API 连接失败 / 网络中断 | 返回 `void_fallback` 空状态 | graduate |
| 解析错误 | LLM 返回非合法 JSON | 返回 `void` 状态，`source="llm_parse_error"` | 全阶段 |
| 超时 | 请求超过设定时限 | 重试 1 次 → 仍失败则 `void_fallback` | 全阶段 |
| 速率限制 | HTTP 429 | 入队批量处理，延迟重试 | 全阶段 |

### 5.1 降级代码示例

```python
def project_input(self, input_text: str, dimension_labels: list[str]) -> str:
    prompt = PROJECTION_PROMPT_TEMPLATE.format(
        input=input_text,
        dimensions=dimension_labels
    )
    try:
        raw = self.query(prompt)
        # 验证 JSON 可解析
        parsed = json.loads(raw)
        if "assessments" not in parsed:
            raise ValueError("missing 'assessments' key")
        return raw
    except json.JSONDecodeError:
        # 解析失败 → void 状态
        return json.dumps({
            "assessments": [{"value": 0, "reason": "llm_parse_error"}] * len(dimension_labels)
        })
    except (TimeoutError, ConnectionError):
        # 超时重试一次
        try:
            return self.query(prompt)
        except Exception:
            # 仍失败 → void_fallback
            return json.dumps({
                "assessments": [{"value": 0, "reason": "void_fallback"}] * len(dimension_labels)
            })
    except RateLimitError:
        # 入队批量处理
        self._enqueue(prompt)
        return json.dumps({
            "assessments": [{"value": 0, "reason": "queued_retry"}] * len(dimension_labels)
        })
```

---

## 6. 成本控制

### 6.1 成本模型

LLM 调用成本随成长阶段递减：

```
C_school       ∝ N_call           （每次输入都调用）
C_internalize  ∝ N_pattern_miss   （仅模式未命中时调用）
C_graduate     ∝ N_unknown        （仅真正未知时调用）
```

其中 `N_pattern_miss` 和 `N_unknown` 随 PatternLearner 积累而趋近于零。

### 6.2 复用率指标

`PatternLearner.reuse_rate` 是衡量成本效率的核心指标：

```python
@property
def reuse_rate(self) -> float:
    """已积累模式的复用率，越高表示 LLM 调用越少。"""
    if self.total_inputs == 0:
        return 0.0
    return self.pattern_hits / self.total_inputs
```

| 复用率区间 | 含义 | 建议动作 |
|-----------|------|----------|
| 0.0 – 0.3 | 模式积累不足，LLM 依赖高 | 维持 school/internalize 阶段 |
| 0.3 – 0.7 | 模式积累中，LLM 调用下降 | 可推进至 internalize |
| 0.7 – 0.9 | 模式成熟，LLM 仅处理边缘情况 | 可推进至 graduate |
| 0.9+ | 模式覆盖充分，LLM 几乎不调用 | graduate 稳态运行 |

### 6.3 Token 预算管理

```python
class TokenBudget:
    def __init__(self, daily_limit: int = 500_000):
        self.daily_limit = daily_limit
        self.used = 0

    def can_spend(self, estimated_tokens: int) -> bool:
        return self.used + estimated_tokens <= self.daily_limit

    def spend(self, actual_tokens: int):
        self.used += actual_tokens
        if self.used > self.daily_limit * 0.8:
            logger.warning(f"Token 预算已使用 {self.used/self.daily_limit:.0%}")
```

### 6.4 调用统计追踪

所有 LLM 调用均自动记录到 `cost_stats`，可通过日志或监控面板查看趋势：

```python
stats = self.llm.cost_stats
logger.info(
    f"LLM 调用统计 — 总计: {stats['total_calls']}, "
    f"维度适配: {stats['dimension_adaptation_calls']}, "
    f"投影: {stats['projection_calls']}, "
    f"建议: {stats['advisor_calls']}"
)
```

---

## 7. 避免过度依赖

系统设计三层防护，防止对 LLM 或已积累模式产生过度依赖：

### 7.1 模式匹配阈值

PatternLearner 的相似度阈值为 **0.7**，低于此值的匹配不被接受：

```python
SIMILARITY_THRESHOLD = 0.7

def match(self, input_text: str) -> PatternMatch | None:
    best = self._find_best_match(input_text)
    if best and best.similarity >= SIMILARITY_THRESHOLD:
        self.pattern_hits += 1
        return best
    # 低于阈值 → 视为未命中，触发 LLM 调用
    return None
```

这确保低相似度的"虚假匹配"不会替代 LLM 的独立判断。

### 7.2 自我对齐检查

当 LLM 建议与系统身份声明（identity）矛盾时，发出警告而非盲从：

```python
def _self_alignment_check(self, advice: str, identity: str) -> bool:
    """检查 LLM 建议是否与系统身份一致。"""
    contradictions = self._detect_contradiction(advice, identity)
    if contradictions:
        logger.warning(
            f"LLM 建议与身份声明存在矛盾: {contradictions}。"
            f"建议将被标记为 'low_confidence'。"
        )
        return False
    return True
```

### 7.3 气候报告中的探索阶段

`climate.py` 的气候报告包含 `exploration_phase` 字段，反映系统当前的探索活跃度：

| exploration_phase | 含义 | 诊断 |
|-------------------|------|------|
| `exploring` | 持续探索新状态 | 健康 |
| `consolidating` | 模式积累中，探索放缓 | 正常过渡 |
| `stagnant` | 长期未探索新状态 | 过度依赖模式，需注入新输入 |

当 `exploration_phase == "stagnant"` 时，系统提示用户输入更多样化的场景以重新激活探索。

---

## 8. 多供应商支持

### 8.1 当前支持的调用模式

| 模式 | 配置方式 | 适用场景 |
|------|----------|----------|
| OpenAI 兼容 API（默认） | 设置 `api_base` + `api_key` + `model` | 标准云端模型 |
| 自定义回调 | 注入 `callback` 函数 | 本地路由、测试 Mock、自定义协议 |

### 8.2 自定义回调示例

```python
def local_model_callback(prompt: str) -> str:
    """自定义回调：路由到本地推理服务。"""
    import requests
    resp = requests.post(
        "http://localhost:8080/v1/completions",
        json={"prompt": prompt, "max_tokens": 2048}
    )
    return resp.json()["choices"][0]["text"]

bridge = LLMBridge(
    api_base="",          # 使用回调时可为空
    api_key="",
    model="local-llama-8b",
    callback=local_model_callback
)
```

### 8.3 路线图

| 阶段 | 能力 | 状态 |
|------|------|------|
| v1.0 | OpenAI 兼容 API + 自定义回调 | 已实现 |
| v1.1 | 本地模型直连（llama.cpp / vLLM） | 规划中 |
| v2.0 | 多模型路由（按任务复杂度自动选择模型） | 规划中 |

多模型路由的目标架构：

```
输入 prompt
  │
  ├─ 简单投影 → 轻量模型（如 gpt-4o-mini）
  ├─ 维度适配 → 中等模型（如 gpt-4o）
  └─ 复杂建议 → 重型模型（如 gpt-4o / o1）
```

通过任务复杂度路由，在保证质量的前提下进一步降低 Token 成本。

---

## 附录：模块依赖关系

```
agent.py
  ├── llm/bridge.py        (LLMBridge)
  ├── pattern_learner.py   (PatternLearner, reuse_rate)
  ├── climate.py           (ClimateReport, exploration_phase)
  └── prompts/
       ├── dimension_adaptation.py   (DIMENSION_ADAPTATION_PROMPT)
       └── projection.py             (PROJECTION_PROMPT_TEMPLATE)
```

## 附录：配置示例

```yaml
# btcu_config.yaml
llm:
  api_base: "https://api.openai.com/v1"
  api_key: "${OPENAI_API_KEY}"
  model: "gpt-4o-mini"
  timeout_sec: 30
  retry_count: 1
  token_budget:
    daily_limit: 500000

pattern_learner:
  similarity_threshold: 0.7
  max_patterns: 10000

growth:
  initial_stage: "school"
  internalize_reuse_rate: 0.3
  graduate_reuse_rate: 0.7
```

---

*本文档随 BTCU Harness 版本迭代更新。如需修改维度适配或投影逻辑，请同步更新 `prompts/` 目录下对应模板及本文档第 4 节。*
