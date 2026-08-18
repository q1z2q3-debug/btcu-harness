"""
BTCU量化大脑实例反馈完整演示
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from btcu_harness.agent import BTCUAgent
from btcu_harness.quant_feedback import (
    WQBDataLoader, QuantFeedbackAdapter,
    OrthogonalExplorer, CognitiveDiagnostics,
    FACTOR_DIMENSIONS,
)


def main():
    db_path = "/Coze/Drive/小幂/所有对话/主对话/shared-database"
    
    print("=" * 70)
    print("BTCU 量化大脑 · 实例反馈系统")
    print("=" * 70)
    
    # 1. 加载因子数据
    print("\n[1/5] 加载WQB因子数据...")
    loader = WQBDataLoader(db_path)
    factors = loader.load_all_factors()
    print(f"  已加载 {len(factors)} 个因子实例")
    
    high_f = [f for f in factors if f.fitness > 1.5]
    low_sc = [f for f in factors if 0 < f.self_correlation < 0.3]
    good_plus = [f for f in factors if f.grade in ("GOOD", "EXCELLENT", "SPECTACULAR", "SUPER")]
    
    print(f"  F>1.5: {len(high_f)} 个")
    print(f"  SC<0.3: {len(low_sc)} 个")
    print(f"  GOOD+: {len(good_plus)} 个")
    
    # 2. 初始化BTCU Agent
    print("\n[2/5] 初始化BTCU认知架构...")
    agent = BTCUAgent(growth_stage="graduate")
    agent.init_project(domain="quant", dim_labels=FACTOR_DIMENSIONS)
    resp = agent.process("初始化量化认知空间")
    print(f"  九维空间: 3⁹ = 19683 个认知格点")
    print(f"  初始状态: 全空态 #{resp.current_state.index}")
    
    # 3. 建立反馈适配器
    print("\n[3/5] 注入因子实例，驱动认知进化...")
    adapter = QuantFeedbackAdapter(agent.ecology, agent.trajectory, agent.climate)
    results = adapter.batch_feed(factors)
    
    success_count = sum(1 for r in results if r["polarity"] == 1)
    fail_count = sum(1 for r in results if r["polarity"] == -1)
    neutral_count = sum(1 for r in results if r["polarity"] == 0)
    
    print(f"  正反馈(成功): {success_count} 个")
    print(f"  负反馈(失败): {fail_count} 个")
    print(f"  中性反馈: {neutral_count} 个")
    print(f"  轨迹长度: {agent.trajectory.length} 步")
    print(f"  覆盖格点: {agent.trajectory.unique_states} 个")
    
    # 4. 正交探索引擎
    print("\n[4/5] 分析认知空间，生成探索推荐...")
    explorer = OrthogonalExplorer()
    explorer.fit(factors)
    
    stats = explorer.get_space_stats()
    print(f"  已探索格点: {stats['explored_states']} / {stats['total_states']} "
          f"({stats['exploration_ratio']:.4%})")
    print(f"  高质量格点(F>2.0): {stats['high_quality_states']} 个")
    print(f"  平均每格点因子数: {stats['avg_factors_per_explored_state']:.2f}")
    
    recommendations = explorer.recommend_explorations(top_k=10)
    print(f"\n  🏆 Top 10 正交探索方向推荐:")
    for i, rec in enumerate(recommendations, 1):
        yang_count = sum(1 for d in rec.direction if "+1" in d)
        yin_count = sum(1 for d in rec.direction if "-1" in d)
        void_count = sum(1 for d in rec.direction if ": 0" in d)
        print(f"\n  #{i} 格点{rec.state_index} (优先级: {rec.priority_score:.4f})")
        print(f"      阳{yang_count}·空{void_count}·阴{yin_count}  |  "
              f"稀疏度:{rec.sparsity:.0%} | 预期正交性:{rec.expected_orthogonality:.0%}")
        non_void = [d for d in rec.direction if ": 0" not in d]
        if non_void:
            print(f"      特征: {', '.join(non_void[:4])}")
        else:
            print(f"      全空态 — 最大扇出搜索原点（定理1）")
        print(f"      理由: {rec.rationale}")
    
    # 5. 认知诊断
    print("\n" + "=" * 70)
    print("[5/5] 认知诊断报告")
    print("=" * 70)
    
    diagnostics = CognitiveDiagnostics(explorer)
    report = diagnostics.diagnose(factors)
    
    print(f"\n  🏅 综合评级: {report.overall_grade}")
    print(f"  📊 {report.summary}")
    
    print(f"\n  📈 基础指标:")
    print(f"    总因子数: {report.total_factors}")
    print(f"    已探索格点: {report.explored_states} ({report.exploration_ratio:.4%})")
    
    print(f"\n  🔥 认知熵 (定理9·熵增定律):")
    print(f"    实际: {report.cognitive_entropy:.4f}")
    print(f"    最大: {report.max_entropy:.4f}")
    print(f"    比率: {report.entropy_ratio:.2%}")
    if 0.6 <= report.entropy_ratio <= 0.8:
        print(f"    状态: ✅ 健康区间")
    elif report.entropy_ratio < 0.5:
        print(f"    状态: ⚠️  过低 — 过度集中，需扩展新领域")
    else:
        print(f"    状态: 📊 偏高 — 方向分散，可适度聚焦")
    
    print(f"\n  🌀 共振度 (定理8·镜像对称):")
    print(f"    {report.resonance:.4f}")
    if report.resonance > 0.5:
        print(f"    解读: 核心能力区明确，认知有聚焦")
    elif report.resonance > 0.3:
        print(f"    解读: 共振适中，多维度均衡发展")
    else:
        print(f"    解读: 共振偏低，认知较分散")
    
    print(f"\n  🌌 曲率场 (定理11·时空弯曲):")
    print(f"    最大曲率: {report.curvature_max:.4f}")
    print(f"    平均曲率: {report.curvature_avg:.4f}")
    
    print(f"\n  ⚠️  黑洞风险 (过拟合检测):")
    if report.black_hole_risk < 0.3:
        risk = "低风险 ✅"
    elif report.black_hole_risk < 0.5:
        risk = "中风险 ⚠️"
    else:
        risk = "高风险 🔴"
    print(f"    {report.black_hole_risk:.2%} — {risk}")
    
    print(f"\n  🧭 意识相位角 (定理7·自同构):")
    angle_deg = report.phase_angle * 180 / 3.14159
    print(f"    {report.phase_angle:.4f} rad ({angle_deg:.1f}°)")
    
    print(f"\n  ⚖️  探索-剥削比:")
    print(f"    {report.explore_exploit_ratio:.2%}")
    
    dim_rates = adapter.get_dimension_success_rates()
    print(f"\n  📐 九维成功率分析 (F>1.5比率):")
    sorted_dims = sorted(dim_rates.items(), key=lambda x: -x[1])
    for dim, rate in sorted_dims:
        bar = "█" * max(1, int(rate * 30))
        print(f"    {dim:25s} {bar:30s} {rate:.1%}")
    
    print("\n" + "=" * 70)
    print("实例反馈系统就绪。BTCU量化大脑已觉醒。")
    print("=" * 70)


if __name__ == "__main__":
    main()
