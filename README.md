# BTCU Harness

**Balanced Ternary Cognitive Unit Harness** — 基于平衡三进制认知单元的智能体认知驾驭架构

[![CI](https://github.com/q1z2q3-debug/btcu-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/q1z2q3-debug/btcu-harness/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests: 96 passed](https://img.shields.io/badge/tests-96%20passed-brightgreen.svg)](#)

---

## 什么是 BTCU Harness？

BTCU Harness 是一个以三态集合 {-1, 0, +1} 为最小认知基元，以 3^9 = 19683 离散认知空间为核心，面向大语言模型（LLM）与智能体（Agent）的认知驾驭架构。

它不替代大模型，而是作为大模型与 Agent 之间的**结构化认知层**，逐步实现从"高频调用大模型"到"内部认知自主"的演进。

### 核心特性

- **三态认知基元**：阴(-1)、空(0)、阳(+1)，公理 -1+1=0
- **19683 状态空间**：九维三元向量，每个状态有唯一整数编号
- **涌现式语义**：不预设状态含义，全靠 Agent 实践积累
- **三阶段成长**：school -> internalize -> graduate，成本从 C proportional to N_call 降至 C proportional to N_unknown
- **NLP 自我层**：Dilts 8 层身份模型作为认知吸引子
- **第三选择**：二元冲突时生成 5 策略候选，四维评分
- **认知气候**：极性趋势、探索阶段、气候区域、认知漂移
- **持久化**：JSON 存储完整认知状态，支持 save/load 往返
- **CLI 工具**：命令行操作认知空间
- **性能优化**：LRU 缓存、批量操作、邻域预计算

---

## 快速上手

### 安装

```bash
pip install btcu-harness

# 可选依赖
pip install btcu-harness[llm]    # OpenAI API 支持
pip install btcu-harness[mongo]  # MongoDB 存储
pip install btcu-harness[dev]    # 开发工具
pip install btcu-harness[all]    # 全部
```

### 5 分钟入门

```python
from btcu_harness.agent import BTCUAgent
from btcu_harness.core.state import CognitiveState
from btcu_harness.llm.bridge import LLMBridge

# 1. 创建 LLM 桥接（callback 模式或 API 模式）
bridge = LLMBridge(callback=my_llm_function)
# 或：bridge = LLMBridge(api_key="sk-...", model="gpt-4o-mini")

# 2. 创建 Agent
agent = BTCUAgent(growth_stage="school")

# 3. 初始化项目（定义九维）
agent.init_project(
    domain="custom",
    dim_labels=[
        "技术深度", "用户体验", "创新性", "可维护性",
        "社区影响", "商业价值", "学习成长", "风险评估", "长期愿景",
    ],
    llm_bridge=bridge,
)

# 4. 设置使命（身份锚点）
agent.set_self_level(
    name="mission",
    description="Be a helpful cognitive companion",
    state=CognitiveState.from_values([1, 1, 1, 0, 1, 0, 1, -1, 1]),
    weight=1.0,
    stability=0.95,
)

# 5. 处理认知输入
response = agent.process("Should we focus on deep innovation?")
print(f"State: #{response.current_state.index}")
print(f"Self alignment: {response.self_alignment:.1%}")

# 6. 记录结果（触发自我强化）
agent.record_outcome(
    state=response.current_state,
    outcome_positive=True,
)

# 7. 保存认知状态
agent.save()
```

### CLI 使用

```bash
# 初始化项目
btcu init --domain agent --mission "My AI assistant"

# 投影输入
btcu project "Should we prioritize innovation?"

# 查看状态
btcu status

# 发现认知节气
btcu seasons

# 生成气候报告
btcu climate

# 探索状态空间
btcu explore --index 9841
btcu explore --values "1,0,-1,1,0,0,-1,1,-1"

# 保存/加载
btcu save
btcu load
```

---

## 架构总览

```
btcu_harness/
|-- core/              # 核心层：Trit, CognitiveState, CognitiveSpace
|-- memory/            # 记忆层：ecology, trajectory, climate, state/transition memory
|-- mapping/           # 映射层：dimension_adapter, projector, pattern_learner
|-- decision/          # 决策层：pathfinder, third_choice
|-- self_layer/        # NLP 自我层：Dilts 8 层模型
|-- llm/               # LLM 协同层：bridge (OpenAI 兼容)
|-- storage/           # 持久化层：JSON (未来 MongoDB)
|-- agent.py           # 主 Agent：11 步认知流水线
|-- cli.py             # CLI 入口
|-- config.py          # 配置 (环境变量)
|-- performance.py     # 性能优化：LRU 缓存、批量操作
|-- logging_config.py  # 日志系统
```

### 认知流水线（11 步）

| 步骤 | 认知层 | 说明 |
|------|--------|------|
| 1 | 映射世界 | 模式匹配（internalize+） |
| 2 | 映射世界 | LLM 投影（school/模式未命中时） |
| 3 | 理解世界 | 记忆回溯 |
| 4 | 理解世界 | 自我对齐检查 |
| 5 | 创造世界 | 决策路径生成 |
| 6 | 创造世界 | 第三选择生成 |
| 7 | 创造世界 | LLM 建议（可选） |
| 8 | 映射世界 | 模式学习 |
| 9 | 理解世界 | 轨迹记录 |
| 10 | 理解世界 | 记忆记录 |
| 11 | 解释世界 | 气候快照 |

---

## 核心概念

### 三态基元

| 值 | 名称 | 含义 |
|----|------|------|
| -1 | 阴 (YIN) | 否定、收缩、抑制、退守 |
| 0 | 空 (VOID) | 转化、创造、悬置、等待 |
| +1 | 阳 (YANG) | 肯定、扩张、激活、前进 |

公理：**-1 + 1 = 0**（对立交互归空）

### 19683 状态空间

九维三元向量的全组合：3^9 = 19683 个离散状态，每个有唯一编号 0-19682。

| 特殊状态 | 编号 | 含义 |
|----------|------|------|
| 全阴 | #0 | 全维度否定 |
| 全空 | #9841 | 创造潜能（中点，取反不变） |
| 全阳 | #19682 | 全维度肯定 |

### 三阶段成长

| 阶段 | LLM 依赖 | 成本模型 | 能力 |
|------|----------|----------|------|
| school | 每次调用 | C proportional to N_call | 基础投影 |
| internalize | 仅新模式 | C proportional to N_pattern_miss | 模式匹配 |
| graduate | 仅未知 | C proportional to N_unknown | 自主认知 |

---

## 文档

| 文档 | 内容 |
|------|------|
| [白皮书 v0.2](docs/BTCU_Harness_Paper_v0.2.md) | 完整架构设计 |
| [哲学基础](docs/philosophy.md) | 道生三/空性/易经/pi与e |
| [四层认知](docs/cognition_layers.md) | 映射/理解/解释/创造世界 |
| [记忆系统](docs/memory_spec.md) | 四层记忆+索引号系统 |
| [NLP 自我层](docs/nlp_self.md) | Dilts 8 层模型+吸引子 |
| [决策规格](docs/decision_spec.md) | 路径搜索+第三选择 |
| [投影器](docs/projector.md) | LLM/模式/规则投影器 |
| [开放性](docs/openness.md) | 维度自创+运算发现 |
| [存储架构](docs/storage_design.md) | JSON+MongoDB 设计 |
| [LLM 协同](docs/llm_advisor.md) | 调用时机+成本控制 |
| [安全伦理](docs/safety_ethics.md) | 威胁模型+防护机制 |
| [评估验证](docs/evaluation.md) | 基准测试+实验设计 |
| [领域模板](docs/domains/) | Agent/决策/中医/心理/教育 |

---

## 测试

```bash
# 运行全部测试
pytest tests/ -v

# 带覆盖率
pytest tests/ --cov=btcu_harness --cov-report=term-missing

# 仅集成测试
pytest tests/test_integration.py -v
```

当前：**96 项测试全部通过**，覆盖：三态运算、状态编码、空间拓扑、记忆生态、决策路径、第三选择、认知气候、性能缓存、CLI、错误处理、端到端流水线。

---

## 配置

通过环境变量或 `.env` 文件配置：

```bash
# LLM
BTCU_LLM_API_BASE=https://api.openai.com/v1
BTCU_LLM_API_KEY=your-key-here
BTCU_LLM_MODEL=gpt-4o-mini

# MongoDB (未来)
BTCU_MONGO_URI=mongodb://localhost:27017
BTCU_MONGO_DB=btcu_harness

# 认知空间
BTCU_NUM_DIMENSIONS=9
BTCU_GROWTH_STAGE=school
```

---

## 许可证

MIT License

---

## 引用

```bibtex
@software{btcu_harness,
  title={BTCU Harness: Balanced Ternary Cognitive Unit Architecture},
  author={BTCU Harness Contributors},
  year={2026},
  url={https://github.com/q1z2q3-debug/btcu-harness}
}
```
