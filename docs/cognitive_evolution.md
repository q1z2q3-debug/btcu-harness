# BTCU 认知架构演进：从工具到认知基础设施

**日期**: 2026-08-15
**主题**: LangChain Middleware → MCP Server → 双系统认知架构的范式跃迁
**状态**: 设计完成，待工程实现

---

## 一、起始问题：BTCU 如何与外部世界集成？

### 1.1 最初的错误理解

**错误假设**: BTCU 是一个"插件"，需要嵌入到某个框架中才能发挥作用。

**第一次尝试**: LangChain Middleware
- 在 LangChain 1.x 的 `AgentMiddleware.wrap_model_call` 中**强制注入**认知上下文到 system prompt
- 本质: **劫持** LLM 的输入，让 LLM "必须看到" BTCU 的提示
- 结果: LLM 被 BTCU **指导/控制**，而非被**赋能**

**问题**: 这与 BTCU 的设计哲学相悖。

### 1.2 用户的纠正

> "认知工具是赋能大模型的，就像大模型或者 agent 的眼镜，不是反过来指导大模型的，而是大模型加上翅膀，如虎添翼的状态。这个是大模型来用，而非是被用。"

**核心洞察**: BTCU 不是 LLM 的上级，而是 LLM 的**能力扩展**。

类比:
- **错误**: 给司机一个导航仪，强制只能按导航路线走（控制）
- **正确**: 给司机一副 AR 眼镜，实时显示路况、油耗、目的地信息（赋能），司机自己决定怎么走

---

## 二、范式跃迁：从 LangChain Middleware 到 MCP Server

### 2.1 为什么 LangChain Middleware 是错误方向

| 维度 | LangChain Middleware (错误) | MCP Server (正确) |
|---|---|---|
| **集成方式** | 侵入式——修改 LLM 的输入 | 服务式——LLM 主动查询 |
| **决策权** | BTCU 替 LLM 做选择 | LLM 自主使用 BTCU 信息 |
| **覆盖范围** | 仅限 LangChain | 任何 MCP Host (Claude/Cursor/OpenAI) |
| **本质关系** | 主从关系（BTCU 主，LLM 从） | 伙伴关系（LLM 主，BTCU 辅） |

### 2.2 MCP Server 的正确姿态

**BTCU MCP Server 应该提供什么？**

不是"指令"，而是"认知参考信息":

1. **Tools**: LLM 面临选择时，可以**主动查询** BTCU 的历史经验
2. **Resources**: 持续更新的认知仪表盘，LLM 随时可以"看一眼"
3. **Prompts**: 可选的认知模板，LLM 可以选择"戴不戴这副眼镜"

**关键差异**: LLM 调用 BTCU，而非 BTCU 劫持 LLM。

---

## 三、深层洞察：思维的快与慢

### 3.1 Kahneman 双系统理论的 BTCU 映射

**System 1 (快认知)**:
- 直觉、自动、低能耗
- 基于模式匹配
- 毫秒级响应

**System 2 (慢认知)**:
- 分析、有意识、高能耗
- 基于逻辑推理
- 秒级响应

**BTCU 的映射**:

```
System 1 (BTCU 认知空间)          System 2 (LLM 深度推理)
┌─────────────────────┐         ┌─────────────────────┐
│ 输入 → 模式匹配      │         │ 输入 → 语义分析      │
│     ↓               │         │     ↓               │
│ 查认知模式库        │         │ 9维投影             │
│     ↓               │         │     ↓               │
│ 命中?               │         │ 结构化解构          │
│ ├─ Yes → 直接决策   │         │     ↓               │
│ │     (0 tokens)    │         │ 创造性推理          │
│ └─ No  → 交给 S2    │         │     ↓               │
│                     │         │ 决策输出            │
│ 特征: <5ms, 95%准确率│         │ 特征: 200ms+,       │
│       (已知领域)    │         │       创造性处理    │
└─────────────────────┘         └─────────────────────┘
           ↑                              │
           └────── 模式积累 ←─────────────┘
```

### 3.2 "认知密度"决定 System 1 的效能

| 状态空间覆盖率 | System 1 命中率 | 特征 |
|---|---|---|
| < 0.1% | < 5% | "新手"——几乎全靠 LLM |
| 1-5% | 20-40% | "学徒"——部分模式，仍需大量推理 |
| 10-20% | 50-70% | "熟手"——大部分常见场景快认知 |
| > 30% | > 80% | "专家"——直觉为主，只在全新场景慢思考 |
| > 50% | > 90% | "大师"——几乎全快认知，System 2 仅用于验证 |

**关键命题**: 随着 BTCU 认知空间中模式密度的增加，LLM 调用频率递减，最终认知空间本身成为决策主体。

### 3.3 Token Economy 的数据支撑

之前的 Token Economy benchmark 显示:
- 1000 输入 → 400 次 LLM 调用
- reuse_rate 从 0% → 80%
- 60% 成本节省

但这只是**调用次数的复用**。双系统架构的目标是更激进的**认知替代**:

- **Phase 1 (School)**: LLM 投影 → 认知空间 → LLM 决策 → 记录模式
- **Phase 2 (Internalize)**: 模式匹配 → 认知空间 → 少量 LLM → 模式增强  
- **Phase 3 (Graduate)**: 模式匹配 → 认知空间 → 直接决策 → LLM 仅用于全新场景

---

## 四、System 1 的实现机制

### 4.1 模式库结构

```python
class CognitivePattern:
    """System 1 的原子单元"""
    
    trigger_hash: str          # 输入文本的语义指纹
    state_index: int           # 投影到的认知状态
    action_sequence: List[str] # 历史最优动作序列
    success_rate: float        # 历史成功率
    last_used: datetime        # 最后使用时间
    confidence: float           # 模式置信度
    system2_audit_score: float  # System 2 审计评分
```

### 4.2 双系统决策流程

```python
def cognitive_decide(input_text: str, session: SessionState) -> Decision:
    """
    双系统认知决策引擎。
    
    1. System 1 快速通道：模式匹配
    2. 置信度检查：模式是否足够可靠？
    3. 未命中或低置信度 → System 2 深度推理
    4. System 2 结果 → 反馈给 System 1，更新模式库
    """
    
    # === System 1: 快认知 ===
    exact = pattern_db.get(hash(input_text))
    if exact and exact.confidence > 0.8 and exact.system2_audit_score > 0.7:
        return Decision(
            action=exact.action,
            source="system1_exact",
            confidence=exact.confidence,
            tokens_consumed=0,
            latency_ms=<5
        )
    
    # 模糊匹配：认知空间最近邻
    projected_state = fast_project(input_text)  # rule-based, <5ms
    neighbors = find_knn(projected_state, k=3)
    
    if neighbors and all(n.confidence > 0.6 for n in neighbors):
        consensus_action = majority_vote([n.action for n in neighbors])
        return Decision(
            action=consensus_action,
            source="system1_consensus",
            confidence=avg_confidence(neighbors),
            tokens_consumed=0,
            latency_ms=<10
        )
    
    # === System 2: 慢认知 ===
    # 未命中 → 调用 LLM 进行深度推理
    llm_result = llm_process(input_text)
    
    # 学习：将 System 2 的结果记录到 System 1
    pattern_db.learn(
        input_hash=hash(input_text),
        state=projected_state,
        action=llm_result.action,
        source="system2_teach"
    )
    
    return Decision(
        action=llm_result.action,
        source="system2",
        confidence=llm_result.confidence,
        tokens_consumed=llm_result.tokens,
        latency_ms=llm_result.latency_ms
    )
```

---

## 五、认知惰性的风险与防御

### 5.1 风险 1：模式固化（Pattern Rigidity）

**现象**: 用户输入类型轻微变化，System 1 命中相似模式 → 复用旧决策
**问题**: 新场景需要细微调整，但 System 1 无法察觉差异
**防御**: `cognitive_compare(current_state, matched_pattern_state)`，如果距离 > 3，强制降级到 System 2

### 5.2 风险 2：状态空间盲区

**现象**: 模式库覆盖了 30% 状态空间，70% 从未被探索
**问题**: System 1 永远不知道"自己不知道什么"
**防御**: ε-探索策略——以 10% 概率强制使用 System 2，即使 System 1 有匹配模式

### 5.3 风险 3：反馈循环陷阱

**现象**: System 1 决策 → 结果还行 → 记录成功 → 模式强化 → "还行"被当作"最优"
**防御**: System 2 定期审计——随机抽取 5% 的 System 1 决策，用 LLM 重新评估是否有更好的替代方案

---

## 六、MCP Server 的重新设计：双系统认知接口

### 6.1 当前工具的局限性

当前的 `cognitive_project` 只是"投影"，没有体现 System 1/2 的区分。

### 6.2 改进方向

**新增 Tool: `cognitive_decide`**

LLM 调用它来获取"认知决策建议"，但**保留最终决定权**:

```json
{
  "name": "cognitive_decide",
  "arguments": {
    "input": "Calculate compound interest",
    "session_id": "sess_123",
    "system_preference": "auto"
  }
}
```

返回:
```json
{
  "recommended_action": "use_calculator",
  "system_used": "system1",
  "confidence": 0.87,
  "tokens_consumed": 0,
  "latency_ms": 3,
  "alternative_actions": ["use_search_then_calculate"],
  "system2_available": true,
  "message": "System 1 recognizes this as a standard math query."
}
```

**关键**: LLM 看到推荐后，可以选择接受、修改或拒绝——**决策权在 LLM**。

**新增 Resource: `cognitive://metacognition/speedometer`**

实时显示双系统运行状态:
```json
{
  "system1_hit_rate_24h": 0.73,
  "system2_tokens_consumed_24h": 15420,
  "estimated_cost_savings": "67%",
  "cognitive_lazy_alerts": 2,
  "exploration_rate": 0.08,
  "system1_coverage_pct": 0.3
}
```

**新增 Prompt: `cognitive://glasses/{mode}`**

可选的认知增强模式:
- `minimal`: 只显示极性和倾向
- `analytical`: 显示维度分解和风险提示
- `creative`: 显示 void 区域的机会空间

LLM（或用户）可以**自主决定**戴哪副眼镜、戴不戴。

---

## 七、核心认知修正

### 7.1 从"控制"到"赋能"

| 阶段 | 关系 | 本质 |
|---|---|---|
| LangChain Middleware | BTCU 控制 LLM | 主从关系 |
| MCP Server (初步) | LLM 使用 BTCU | 服务关系 |
| **双系统架构** | LLM + BTCU 协作 | **伙伴关系** |

### 7.2 从"插件"到"基础设施"

BTCU 不是某个框架的附属品，而是:
- **独立的认知服务**（MCP Server）
- **通用的认知坐标系**（19,683 状态空间）
- **可积累的智能资产**（模式库随使用增长）

### 7.3 从"单次调用"到"认知积累"

关键差异:
- **传统 API**: 每次调用独立，无记忆
- **BTCU**: 每次交互都积累模式，System 1 越来越"聪明"

这是真正的"学习型基础设施"——越用越省，越用越快。

---

## 八、未来方向

### 8.1 短期（已实现）
- [x] LangChain Middleware（保留但非主推）
- [x] MCP Server 基础版（Tools/Resources/Prompts）
- [x] Rule-based 投影（零 LLM 依赖）
- [x] Session 持久化（MongoDB + in-memory fallback）

### 8.2 中期（待实现）
- [ ] `cognitive_decide`：显式双系统决策
- [ ] `cognitive_mode`：System 1/2 模式切换（novice/apprentice/expert/master）
- [ ] `cognitive_audit`：System 2 定期审计 System 1
- [ ] Cognitive Coordination Layer：跨工具认知关联
- [ ] Cognitive Safety Guard：决策漂移检测

### 8.3 长期（愿景）
- [ ] 认知密度达到 30%+ → System 1 命中率 80%+
- [ ] Token 消耗减少 90%+
- [ ] 认知空间成为 LLM 的"默认认知层"
- [ ] 支持多 agent 共享认知空间（群体认知）

---

## 九、结论

### 核心命题

> BTCU 不是 LLM 的替代者，而是 LLM 的"认知加速器"。就像人类在熟悉领域依靠直觉（System 1），只在陌生或关键问题上启动深度思考（System 2），BTCU 让 LLM 也能拥有这种双系统认知能力。

### 关键洞察

1. **赋能而非控制**: BTCU 提供认知参考，LLM 保留决策主权
2. **快与慢的结合**: System 1（BTCU）处理熟悉场景，System 2（LLM）处理全新挑战
3. **认知积累**: 每次交互都在增厚模式库，System 1 覆盖率和命中率持续增长
4. **成本递减**: 随着模式库成熟，LLM 调用频率递减，Token 消耗趋近于零（在已知领域）
5. **框架无关**: MCP Server 让 BTCU 成为任何 AI 系统可调用的认知基础设施

### 最终定位

BTCU 是:
- **AI 的直觉层**（Intuition Layer）
- **决策的缓存层**（Decision Cache）
- **认知的坐标系**（Cognitive Coordinate System）
- **智能的复利引擎**（Intelligence Compounding Engine）

不是"给 LLM 戴上手铐"，而是"给 LLM 装上翅膀"。

---

*本文档记录了 BTCU 从 LangChain Middleware 到 MCP Server 再到双系统认知架构的范式演进过程。*
*核心转折发生在用户指出"赋能而非控制"和"思维的快与慢"两个关键洞察之后。*
*所有技术实现应服从这个哲学定位。*
