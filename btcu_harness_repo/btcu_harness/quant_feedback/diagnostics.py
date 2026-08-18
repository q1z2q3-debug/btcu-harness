"""
认知诊断仪表盘 —— BTCU量化大脑的自指诊断模块

对应BTCU十一大公理中的自我观测：
- 意识相位角：认知状态在九维空间中的旋转角度
- 认知熵：因子分布的无序程度（熵增定律的体现）
- 曲率场：高共振区域的认知空间弯曲度
- 黑洞风险：过拟合/过度剥削已知区域的风险
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Dict
from collections import Counter

from ..core.state import CognitiveState
from .adapter import FactorInstance, FACTOR_DIMENSIONS
from .explorer import OrthogonalExplorer


@dataclass
class DiagnosticReport:
    """认知诊断报告"""
    # 基础指标
    total_factors: int
    explored_states: int
    exploration_ratio: float
    
    # 认知熵（分布无序程度）
    cognitive_entropy: float
    max_entropy: float
    entropy_ratio: float  # 实际/最大
    
    # 共振度（高成功区域聚集程度）
    resonance: float
    
    # 曲率场（最强格点的引力）
    curvature_max: float
    curvature_avg: float
    
    # 黑洞风险（过拟合风险）
    black_hole_risk: float  # 0~1
    
    # 相位角（当前认知方向）
    phase_angle: float  # 弧度制
    
    # 探索-剥削平衡
    explore_exploit_ratio: float
    
    # 总体评价
    overall_grade: str
    summary: str


class CognitiveDiagnostics:
    """
    自指诊断仪表盘
    
    实时监控量化大脑的认知健康状态：
    - 熵过高 → 漫无目的，需要聚焦
    - 熵过低 → 过拟合风险，需要探索新领域
    - 共振过低 → 认知分散，没有核心能力
    - 共振过高 → 局部最优陷阱
    """

    def __init__(self, explorer: OrthogonalExplorer):
        self.explorer = explorer

    def diagnose(self, factors: List[FactorInstance]) -> DiagnosticReport:
        """全维度诊断"""
        stats = self.explorer.get_space_stats()
        total = len(factors)
        
        # 1. 认知熵（按格点分布计算）
        entropy = self._calc_entropy(factors)
        max_entropy = math.log(stats["explored_states"]) if stats["explored_states"] > 1 else 1.0
        entropy_ratio = entropy / max_entropy if max_entropy > 0 else 0
        
        # 2. 共振度（高Fitness因子的聚集程度）
        resonance = self._calc_resonance(factors)
        
        # 3. 曲率场
        curvature_max, curvature_avg = self._calc_curvature(factors)
        
        # 4. 黑洞风险
        black_hole = self._calc_black_hole_risk(factors, entropy_ratio, resonance)
        
        # 5. 相位角
        phase = self._calc_phase_angle(factors)
        
        # 6. 探索-剥削比
        explore_ratio = self._calc_explore_exploit(factors)
        
        # 7. 综合评价
        grade, summary = self._evaluate(entropy_ratio, resonance, black_hole, explore_ratio, stats)
        
        return DiagnosticReport(
            total_factors=total,
            explored_states=stats["explored_states"],
            exploration_ratio=stats["exploration_ratio"],
            cognitive_entropy=entropy,
            max_entropy=max_entropy,
            entropy_ratio=entropy_ratio,
            resonance=resonance,
            curvature_max=curvature_max,
            curvature_avg=curvature_avg,
            black_hole_risk=black_hole,
            phase_angle=phase,
            explore_exploit_ratio=explore_ratio,
            overall_grade=grade,
            summary=summary,
        )

    def _calc_entropy(self, factors: List[FactorInstance]) -> float:
        """计算认知熵（基于格点分布的香农熵）"""
        state_counts = Counter()
        for f in factors:
            state = self._map_factor(f)
            state_counts[state.index] += 1
        
        total = len(factors)
        if total == 0:
            return 0.0
        
        entropy = 0.0
        for count in state_counts.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log(p)
        
        return entropy

    def _calc_resonance(self, factors: List[FactorInstance]) -> float:
        """
        共振度 = 高质量因子之间的接近程度
        高共振说明认知有核心优势区域
        """
        high_quality = [f for f in factors if f.fitness > 1.5]
        if len(high_quality) < 2:
            return 0.0
        
        # 计算高质量因子两两之间的平均汉明距离的倒数
        states = [self._map_factor(f) for f in high_quality]
        total_dist = 0
        pair_count = 0
        
        for i in range(len(states)):
            for j in range(i + 1, len(states)):
                dist = states[i].distance(states[j])
                total_dist += dist
                pair_count += 1
        
        if pair_count == 0:
            return 0.0
        
        avg_dist = total_dist / pair_count
        # 距离越小共振越高，归一化到0~1
        return 1.0 - avg_dist / 9.0

    def _calc_curvature(self, factors: List[FactorInstance]) -> tuple:
        """
        曲率场：每个格点的「质量密度」
        高曲率 = 该区域认知空间被高质量因子「弯曲」
        """
        state_quality = self.explorer.state_quality
        if not state_quality:
            return 0.0, 0.0
        
        values = list(state_quality.values())
        return max(values), sum(values) / len(values)

    def _calc_black_hole_risk(self, factors: List[FactorInstance], 
                             entropy_ratio: float, resonance: float) -> float:
        """
        黑洞风险 = 过度剥削已知区域的风险
        触发条件：低熵 + 高共振 + 高曲率集中
        """
        # 熵越低风险越高
        entropy_risk = 1.0 - entropy_ratio
        
        # 共振过高风险增加（说明都挤在一个区域）
        resonance_risk = max(0, (resonance - 0.5) * 2) if len(factors) > 20 else 0
        
        # 曲率集中（最大值远高于平均值）
        curv_max = self.explorer.state_quality
        if curv_max:
            vals = list(curv_max.values())
            max_v = max(vals)
            avg_v = sum(vals) / len(vals)
            concentration = (max_v - avg_v) / max_v if max_v > 0 else 0
        else:
            concentration = 0
        
        risk = 0.4 * entropy_risk + 0.3 * resonance_risk + 0.3 * concentration
        return min(1.0, max(0.0, risk))

    def _calc_phase_angle(self, factors: List[FactorInstance]) -> float:
        """
        意识相位角 = 九维动量在认知空间中的方向
        用平均状态向量的角度表示
        """
        if not factors:
            return 0.0
        
        # 计算质心向量
        dim_sums = [0.0] * 9
        for f in factors:
            for i, dim in enumerate(FACTOR_DIMENSIONS):
                dim_sums[i] += f.dim_values.get(dim, 0.0)
        
        n = len(factors)
        centroid = [s / n for s in dim_sums]
        
        # 投影到2D平面（取前两个主维度）计算角度
        # 简化：用第一维(x)和第二维(y)计算相位
        x = centroid[0]
        y = centroid[1] if len(centroid) > 1 else 0
        
        return math.atan2(y, x)

    def _calc_explore_exploit(self, factors: List[FactorInstance]) -> float:
        """
        探索-剥削比例
        探索 = 新格点首次尝试 / 总尝试
        剥削 = 在已有格点重复尝试 / 总尝试
        """
        state_counts = Counter()
        for f in factors:
            state = self._map_factor(f)
            state_counts[state.index] += 1
        
        if not state_counts:
            return 1.0
        
        # 只有1个因子的格点 = 探索性尝试
        exploratory = sum(1 for c in state_counts.values() if c == 1)
        total_states = len(state_counts)
        
        return exploratory / total_states

    def _evaluate(self, entropy_ratio: float, resonance: float, 
                 black_hole: float, explore_ratio: float, stats: dict) -> tuple:
        """综合评价"""
        score = 0.0
        notes = []
        
        # 熵：0.6~0.8 最佳（既不太散也不太挤）
        if 0.6 <= entropy_ratio <= 0.8:
            score += 25
            notes.append("认知熵健康")
        elif entropy_ratio < 0.4:
            score += 10
            notes.append("认知熵过低，过度集中")
        elif entropy_ratio > 0.9:
            score += 15
            notes.append("认知熵偏高，方向分散")
        else:
            score += 20
            notes.append("认知熵尚可")
        
        # 共振：适度最好
        if 0.3 <= resonance <= 0.6:
            score += 25
            notes.append("共振度良好")
        elif resonance < 0.2:
            score += 10
            notes.append("共振度低，缺乏核心能力区")
        else:
            score += 15
            notes.append("共振度偏高，注意局部最优")
        
        # 黑洞风险
        if black_hole < 0.3:
            score += 25
            notes.append("黑洞风险低")
        elif black_hole < 0.5:
            score += 15
            notes.append("黑洞风险中等")
        else:
            score += 5
            notes.append("黑洞风险高！")
        
        # 探索率
        if explore_ratio > 0.5:
            score += 25
            notes.append("探索充分")
        elif explore_ratio > 0.3:
            score += 20
            notes.append("探索-剥削平衡")
        else:
            score += 10
            notes.append("探索不足，偏剥削")
        
        # 评级
        if score >= 85:
            grade = "EXCELLENT"
        elif score >= 70:
            grade = "GOOD"
        elif score >= 50:
            grade = "AVERAGE"
        else:
            grade = "AT_RISK"
        
        summary = f"综合得分 {score}/100 ({grade})。" + "；".join(notes) + "。"
        summary += f"已探索 {stats['explored_states']}/{stats['total_states']} 个格点 ({stats['exploration_ratio']:.2%})。"
        
        return grade, summary

    def _map_factor(self, factor: FactorInstance) -> CognitiveState:
        from ..core.trit import YIN, VOID, YANG
        trits = []
        for dim in FACTOR_DIMENSIONS:
            val = factor.dim_values.get(dim, 0.0)
            if val > 0.3:
                trits.append(YANG)
            elif val < -0.3:
                trits.append(YIN)
            else:
                trits.append(VOID)
        return CognitiveState(trits)
