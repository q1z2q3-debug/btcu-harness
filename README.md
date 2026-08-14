# BTCU Harness

**Balanced Ternary Cognitive Unit Harness**

基于平衡三进制认知单元的智能体认知驾驭架构

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-64%20passed-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 概述

BTCU Harness 是一个以三态集合 {-1, 0, +1} 为最小认知基元，以 19683 离散认知空间为核心，面向大模型与 Agent 的认知驾驭架构。

该架构通过三态基元、柔性维度、状态编码、记忆生态、决策路径生成与认知内化机制，为智能体建立可解释、可追踪、可演化的认知基础系统。

BTCU Harness 不替代大模型，而是作为大模型与 Agent 之间的结构化认知层，逐步实现从"高频调用大模型"到"内部认知自主"的演进。

## 核心概念

### 三态基元

系统唯一封闭的认知基元：

| 值 | 名称 | 语义 |
|----|------|------|
| -1 | 阴 | 否定、收缩、抑制、回退 |
| 0 | 空 | 转化、创造、等待、悬置 |
| +1 | 阳 | 肯定、扩张、激活、前进 |

核心公理：**-1 + 1 = 0** —— 对立认知状态的交互进入空态，空态是创造与第三选择的入口。

### 九维认知空间

九个维度，每维取三态之一，产生 3^9 = 19683 个认知状态。

维度是柔性的——新项目启动时适配，然后固定。默认维度集为时间/空间/因果三元组：

- 时间：过去 / 现在 / 未来
- 空间：内部 / 中间 / 外部
- 因果：因 / 缘 / 果

### 19683 认知状态空间

每个状态有唯一编码 [0, 19682]。状态空间是对称的：

- 状态 0：全阴（极否）
- 状态 9841：全空（无极，创造潜能）
- 状态 19682：全阳（极泰）

## 架构

```
BTCU Harness
├── 认知基元层 (core/)        三态定义与基本运算
├── 状态空间层 (core/)        19683 编码、距离、拓扑
├── 认知映射层 (mapping/)     输入到九维三态的投影
├── 记忆生态层 (memory/)      轨迹、共振、悬置、抑制
├── 决策行动层 (decision/)    路径生成、第三选择
├── LLM协同层 (llm/)          大模型作为顾问与生成引擎
└── 主Agent (agent.py)        整合所有层的认知循环
```

## 安装

```bash
git clone https://github.com/yourusername/btcu-harness.git
cd btcu-harness
pip install -e ".[dev]"
```

## 快速开始

```python
from btcu_harness.agent import BTCUAgent
from btcu_harness.llm.bridge import LLMBridge

# 使用自定义 LLM 回调
def my_llm(prompt: str) -> str:
    # 调用你的 LLM API
    return '{"assessments": [...]}'

bridge = LLMBridge(callback=my_llm)
agent = BTCUAgent(growth_stage="school")
agent.init_project(domain="default", llm_bridge=bridge)

# 处理输入
response = agent.process("Should I invest in AI chips?")
print(response.summary())

# 记录结果
agent.record_outcome(
    state=response.current_state,
    decision="invest",
    outcome="profit",
    outcome_positive=True,
)

# 发现认知模式
seasons = agent.discover_seasons()
for s in seasons:
    print(f"[{s.season_type}] {s.description}")
```

## 三阶段成长模型

| 阶段 | LLM 角色 | BTCU 角色 | 成本模型 |
|------|---------|----------|---------|
| 学校 | 主要推理 | 建立状态空间 | C ∝ N_call |
| 内化 | 辅助推理 | 自主匹配与演化 | C ∝ N_pattern_miss |
| 毕业 | 顾问 | 内部推理为主 | C ∝ N_unknown |

```python
agent.advance_stage()  # school -> internalize
agent.advance_stage()  # internalize -> graduate
```

## 第三选择

当面临二元冲突时，BTCU 不是选择 A 或 B，而是生成第三选择 C：

1. 保留 A 和 B 一致的维度
2. 将冲突维度置空（进入创造潜能）
3. 从空中涌现新的认知

```python
third = agent.third_choice_gen.generate(state_a, state_b)
print(third.summary())
```

## 记忆生态

记忆不是静态存储，而是状态轨迹与认知生态：

- **状态共振**：访问一个状态时自动激活相关状态
- **空性悬置**：遗忘是抑制而非删除
- **认知节气**：从重复模式中涌现的规律（吸引子、美德、陷阱、盲区）
- **记忆传承**：导出/导入认知经验

```python
# 导出记忆
legacy = agent.export_memory()

# 导入到新 agent
new_agent = BTCUAgent()
new_agent.init_project(domain="default")
new_agent.import_memory(legacy)
```

## 测试

```bash
pytest tests/ -v
```

64 个测试覆盖：三态基元运算、状态编码/解码、空间拓扑、记忆生态、决策路径、第三选择。

## 项目结构

```
btcu-harness/
├── btcu_harness/
│   ├── core/           # Trit, CognitiveState, CognitiveSpace
│   ├── mapping/        # DimensionAdapter, InputProjector
│   ├── memory/         # StateMemory, TransitionMemory, MemoryEcology
│   ├── decision/       # DecisionPathfinder, ThirdChoiceGenerator
│   ├── llm/            # LLMBridge
│   ├── agent.py        # BTCUAgent 主循环
│   └── config.py       # 配置
├── tests/              # 64 个测试
├── examples/           # 使用示例
├── docs/               # 文档
└── pyproject.toml
```

## 许可证

MIT

## 引用

```bibtex
@software{btcu_harness,
  title={BTCU Harness: Balanced Ternary Cognitive Unit Harness},
  year={2025},
  description={A cognitive architecture for LLM agents based on balanced ternary cognition}
}
```
