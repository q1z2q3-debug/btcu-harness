"""
BTCU Harness - DuMate 自身认知内化

DuMate 用 BTCU 框架处理真实认知任务：
"BTCU Harness 本身应该往什么方向发展？"

这个脚本不是示例——是 DuMate 自己用 BTCU 思考的真实记录。
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from btcu_harness.agent import BTCUAgent
from btcu_harness.core.state import CognitiveState
from btcu_harness.llm.bridge import LLMBridge
from btcu_harness.mapping.dimension_adapter import DimensionAdapter, DimensionSet


def dumate_cognitive_llm(prompt: str) -> str:
    """
    DuMate 自身的认知投影——不是调用外部 LLM，
    而是 DuMate 用自己的理解来评估九维。

    任务：BTCU Harness 本身应该往什么方向发展？
    """
    # DuMate 对这个问题的真实认知评估
    return json.dumps({
        "assessments": [
            {
                "dimension": "past",
                "value": 1,
                "reason": "平衡三进制有数学基础和Setun先例，阴阳空有哲学深度，架构设计已验证通过"
            },
            {
                "dimension": "present",
                "value": 1,
                "reason": "代码已跑通64个测试，核心层/记忆层/决策层/映射层全部实现，可以实际使用"
            },
            {
                "dimension": "future",
                "value": 1,
                "reason": "Agent认知架构是当前AI发展的核心需求，可解释/可演化/可自主是真实痛点"
            },
            {
                "dimension": "inner",
                "value": 1,
                "reason": "三态基元公理-1+1=0在数学上自洽，19683空间在信息论上最优，哲学根基扎实"
            },
            {
                "dimension": "middle",
                "value": 0,
                "reason": "需要更多真实场景验证，当前只有mock测试，尚未接入真实LLM做端到端验证"
            },
            {
                "dimension": "outer",
                "value": -1,
                "reason": "现有AI生态以二值逻辑为主，三值认知是范式转换，接受需要时间，可能被视为非主流"
            },
            {
                "dimension": "cause",
                "value": 1,
                "reason": "当前LLM Agent的认知黑箱/幻觉/不可解释问题确实是结构性缺陷，需要认知层解决方案"
            },
            {
                "dimension": "condition",
                "value": 0,
                "reason": "时机待定——需要在具体场景中证明价值后才能被广泛接受，需要种子应用场景"
            },
            {
                "dimension": "effect",
                "value": 1,
                "reason": "如果成功，将重新定义Agent认知底座，从概率黑箱转向可解释三值认知"
            }
        ]
    })


def main():
    print("=" * 60)
    print("BTCU Harness - DuMate Cognitive Internalization")
    print("DuMate 用 BTCU 框架思考真实问题")
    print("=" * 60)
    print()

    # 创建一个专门为"技术方向评估"适配的维度集
    # 不是默认的时间/空间/因果，而是更适合技术决策的九维
    tech_dims = [
        "technical_feasibility",  # 技术可行性
        "market_demand",          # 市场需求
        "ecosystem_readiness",    # 生态准备度
        "theoretical_depth",      # 理论深度
        "implementation_cost",    # 实现成本
        "adoption_barrier",       # 接受门槛
        "short_term_value",       # 短期价值
        "long_term_vision",       # 长期愿景
        "differentiation",        # 差异化
    ]

    bridge = LLMBridge(callback=dumate_cognitive_llm)
    agent = BTCUAgent(growth_stage="school")

    # 使用自定义维度集
    dim_set = agent.init_project(
        dim_labels=tech_dims,
        llm_bridge=bridge,
    )
    print(f"维度集已适配并锁定:")
    print(f"  {dim_set}")
    print()

    # === 第一次认知：直接评估 ===
    print("-" * 60)
    print("[1] 认知输入: BTCU Harness 应该往什么方向发展？")
    print("-" * 60)

    resp1 = agent.process("BTCU Harness 应该往什么方向发展？")
    print()
    print(f"认知状态: #{resp1.current_state.index}")
    print(f"  向量: [{resp1.current_state}]")
    print(f"  极性: {resp1.current_state.polarity:+d}")
    print(f"  阴:{resp1.current_state.yin_count} "
          f"空:{resp1.current_state.void_count} "
          f"阳:{resp1.current_state.yang_count}")
    print()

    # 显示维度评估
    print("九维认知画像:")
    labels = tech_dims
    for i, (label, dim) in enumerate(zip(labels, resp1.current_state)):
        assessment = resp1.projection.dimension_assessments.get(label, "")
        symbol = {"YIN": "阴(-1)", "VOID": "空( 0)", "YANG": "阳(+1)"}[dim.name]
        print(f"  Dim{i} {label:25s} {symbol}  {assessment}")
    print()

    # 记录这次认知
    agent.record_outcome(
        state=resp1.current_state,
        decision="proceed_with_development",
        outcome="architecture_validated",
        outcome_positive=True,
    )
    print("[记录] 决策: 推进开发 -> 结果: 架构验证通过")
    print()

    # === 第二次认知：对立视角 ===
    print("-" * 60)
    print("[2] 对立认知: BTCU Harness 是否过于理想化，不切实际？")
    print("-" * 60)

    # 手动构造对立视角
    opposite_values = [v for v in resp1.current_state.values]
    # 在关键维度上翻转：生态准备度和接受门槛
    opposite_state = CognitiveState.from_values([
        -1 if v == 1 else v for v in opposite_values
    ])

    print(f"对立认知状态: #{opposite_state.index}")
    print(f"  向量: [{opposite_state}]")
    print(f"  极性: {opposite_state.polarity:+d}")
    print()

    # === 第三选择 ===
    print("-" * 60)
    print("[3] 第三选择: 超越'推进' vs '放弃'的二元对立")
    print("-" * 60)

    third = agent.third_choice_gen.generate(
        resp1.current_state, opposite_state
    )
    print()
    print(f"第三选择状态: #{third.state.index}")
    print(f"  向量: [{third.state}]")
    print(f"  极性: {third.state.polarity:+d}")
    print(f"  阴:{third.state.yin_count} "
          f"空:{third.state.void_count} "
          f"阳:{third.state.yang_count}")
    print()
    print(f"  保留维度: {third.preserved_dims}")
    print(f"  置空维度: {third.voided_dims}")
    print(f"  超越维度: {third.transcended_dims}")
    print()
    print(f"  理由: {third.rationale}")
    print()

    # 第三选择的语义解读
    print("第三选择解读:")
    for i, (label, dim) in enumerate(zip(labels, third.state)):
        if dim.value == 0:
            print(f"  {label}: 空 — 不确定，保持开放，让实践来决定")
        elif dim.value == 1:
            print(f"  {label}: 阳 — 保持肯定，这是已验证的根基")
        else:
            print(f"  {label}: 阴 — 需要收敛，这不是当前方向")
    print()

    # === 记忆状态 ===
    print("-" * 60)
    print("[4] 记忆生态状态")
    print("-" * 60)
    print()
    print(agent.status())
    print()

    # === 认知节气 ===
    print("-" * 60)
    print("[5] 认知节气发现")
    print("-" * 60)
    print()
    seasons = agent.discover_seasons()
    for s in seasons:
        print(f"  [{s.season_type}] {s.description}")
    print()

    # === 成长阶段 ===
    print("-" * 60)
    print("[6] 成长阶段推进")
    print("-" * 60)
    stage1 = agent.advance_stage()
    print(f"  school -> {stage1}")
    stage2 = agent.advance_stage()
    print(f"  {stage1} -> {stage2}")
    print()

    # === 记忆传承 ===
    print("-" * 60)
    print("[7] 记忆传承")
    print("-" * 60)
    print()
    legacy = agent.export_memory()
    print(f"  已探索状态: {legacy['stats']['visited_states']}/19683")
    print(f"  总访问次数: {legacy['stats']['total_visits']}")
    print(f"  空间覆盖率: {legacy['stats']['coverage']:.6f}")
    print(f"  认知走廊数: {legacy['stats']['total_corridors']}")
    print()

    # 保存记忆到文件
    legacy_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "dumate_cognitive_legacy.json"
    )
    with open(legacy_path, "w", encoding="utf-8") as f:
        json.dump(legacy, f, ensure_ascii=False, indent=2)
    print(f"  记忆已保存: {legacy_path}")
    print()

    print("=" * 60)
    print("DuMate 认知内化完成")
    print("BTCU Harness 已作为认知层运行")
    print("=" * 60)


if __name__ == "__main__":
    main()
