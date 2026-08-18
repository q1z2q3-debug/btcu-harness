"""
正交探索引擎 —— 基于已发布因子空间，推荐下一步探索方向

原理：
1. 把所有已发布因子映射到九维认知格点
2. 分析哪些格点已饱和（高Fitness因子密集）
3. 哪些格点是盲区（因子稀少或全失败）
4. 基于BTCU全空态扇出最优性，推荐正交探索方向

九维空间的3⁹=19683个格点，每个格点代表一种「因子认知类型」
格点越稀疏，说明该领域越未被探索，正交性潜力越大
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

from ..core.state import CognitiveState
from ..core.space import CognitiveSpace
from ..core.trit import YIN, VOID, YANG

from .adapter import FactorInstance, FACTOR_DIMENSIONS


@dataclass
class ExplorationCandidate:
    """探索候选方向"""
    direction: List[str]  # 九维的三态组合描述
    state_index: int
    sparsity: float  # 稀疏度 = 1 / (1 + count)
    expected_orthogonality: float  # 预期正交性评分
    expected_fitness: float  # 预期Fitness（基于邻近格点外推）
    priority_score: float  # 综合优先级
    rationale: str  # 推荐理由


class OrthogonalExplorer:
    """
    正交探索引擎
    
    基于BTCU认知空间的因子探索推荐系统：
    - 统计19683个格点的因子分布
    - 发现稀疏区域（未被探索的正交方向）
    - 结合邻近格点质量，预测新方向潜力
    """

    def __init__(self):
        from .adapter import FACTOR_DIMENSIONS
        self.dimensions = 9
        self.space = CognitiveSpace(FACTOR_DIMENSIONS)
        self.state_factors: Dict[int, List[FactorInstance]] = defaultdict(list)
        self.state_quality: Dict[int, float] = {}  # 每个格点的平均质量

    def fit(self, factors: List[FactorInstance]):
        """用已有因子训练分布模型"""
        self.state_factors.clear()
        self.state_quality.clear()
        
        for factor in factors:
            state = self._map_factor(factor)
            self.state_factors[state.index].append(factor)
        
        # 计算每个格点的质量分
        for idx, flist in self.state_factors.items():
            if flist:
                avg_f = sum(f.fitness for f in flist) / len(flist)
                avg_novelty = sum(f.novelty_score for f in flist) / len(flist)
                self.state_quality[idx] = avg_f * avg_novelty

    def _map_factor(self, factor: FactorInstance) -> CognitiveState:
        """将因子映射到认知状态格点"""
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

    def get_state_density(self, state_index: int) -> float:
        """获取格点密度（0~1，越高越饱和）"""
        count = len(self.state_factors.get(state_index, []))
        # 用对数压缩，避免单个格点10+个因子就饱和
        return 1.0 - math.exp(-count / 3.0)

    def get_neighbor_states(self, state_index: int, radius: int = 1) -> List[int]:
        """获取邻近格点（汉明距离=radius）"""
        state = CognitiveState.from_index(state_index)
        if radius == 1:
            return [n.index for n in state.neighbors()]
        # radius > 1 时用BFS
        visited = {state_index}
        current = {state_index}
        for _ in range(radius):
            next_layer = set()
            for idx in current:
                s = CognitiveState.from_index(idx)
                for n in s.neighbors():
                    if n.index not in visited:
                        next_layer.add(n.index)
                        visited.add(n.index)
            current = next_layer
        return list(current)

    def recommend_explorations(self, top_k: int = 10) -> List[ExplorationCandidate]:
        """
        推荐最有价值的探索方向
        
        优先级 = 稀疏度 × 邻近格点平均质量 × 创新潜力
        """
        candidates = []
        
        # 遍历已有因子的邻近空白格点（从已探索区域外推）
        for idx in list(self.state_factors.keys()):
            neighbors = self.get_neighbor_states(idx, radius=1)
            for n_idx in neighbors:
                if n_idx in self.state_factors and len(self.state_factors[n_idx]) >= 3:
                    continue  # 已饱和的跳过
                
                # 计算稀疏度
                count = len(self.state_factors.get(n_idx, []))
                sparsity = 1.0 / (1.0 + count)
                
                # 邻近格点平均质量（外推预期）
                nn_neighbors = self.get_neighbor_states(n_idx, radius=1)
                neighbor_quality = 0.0
                neighbor_count = 0
                for nn_idx in nn_neighbors:
                    if nn_idx in self.state_quality:
                        neighbor_quality += self.state_quality[nn_idx]
                        neighbor_count += 1
                
                if neighbor_count == 0:
                    expected_fitness = 0.5  # 完全未知，保守估计
                else:
                    expected_fitness = neighbor_quality / neighbor_count
                
                # 创新潜力：格点越远离已探索中心，正交性越高
                distance_from_saturated = self._distance_from_saturated(n_idx)
                orthogonality = min(1.0, distance_from_saturated / 9.0)
                
                # 综合优先级
                priority = sparsity * (0.5 + expected_fitness / 6.0) * (0.5 + orthogonality)
                
                state = CognitiveState.from_index(n_idx)
                direction_desc = self._describe_direction(state)
                
                candidates.append(ExplorationCandidate(
                    direction=direction_desc,
                    state_index=n_idx,
                    sparsity=sparsity,
                    expected_orthogonality=orthogonality,
                    expected_fitness=expected_fitness,
                    priority_score=priority,
                    rationale=self._generate_rationale(state, sparsity, expected_fitness, orthogonality),
                ))
        
        # 按优先级排序，去重
        seen = set()
        unique_candidates = []
        for c in sorted(candidates, key=lambda x: -x.priority_score):
            if c.state_index not in seen:
                seen.add(c.state_index)
                unique_candidates.append(c)
                if len(unique_candidates) >= top_k:
                    break
        
        return unique_candidates

    def _distance_from_saturated(self, state_index: int) -> float:
        """计算到最近饱和格点的平均汉明距离"""
        if not self.state_factors:
            return 9.0
        
        state = CognitiveState.from_index(state_index)
        min_dist = 999
        for idx in self.state_factors:
            if len(self.state_factors[idx]) >= 3:  # 饱和格点
                other = CognitiveState.from_index(idx)
                dist = state.distance(other)
                min_dist = min(min_dist, dist)
        
        return min_dist if min_dist < 999 else 9.0

    def _describe_direction(self, state: CognitiveState) -> List[str]:
        """描述一个认知状态对应的因子方向"""
        desc = []
        for i, dim in enumerate(FACTOR_DIMENSIONS):
            val = state.dims[i].value
            if val == 1:
                desc.append(f"{dim}: +1 (阳)")
            elif val == -1:
                desc.append(f"{dim}: -1 (阴)")
            else:
                desc.append(f"{dim}: 0 (空)")
        return desc

    def _generate_rationale(self, state: CognitiveState, sparsity: float, 
                           expected_fitness: float, orthogonality: float) -> str:
        """生成推荐理由"""
        yang_dims = [FACTOR_DIMENSIONS[i] for i in range(9) if state.dims[i].value == 1]
        yin_dims = [FACTOR_DIMENSIONS[i] for i in range(9) if state.dims[i].value == -1]
        void_dims = [FACTOR_DIMENSIONS[i] for i in range(9) if state.dims[i].value == 0]
        
        parts = []
        if yang_dims:
            parts.append(f"正向驱动: {', '.join(yang_dims[:3])}")
        if yin_dims:
            parts.append(f"反向驱动: {', '.join(yin_dims[:3])}")
        if void_dims:
            parts.append(f"悬置维度: {len(void_dims)}个（留空创造空间）")
        
        parts.append(f"稀疏度: {sparsity:.1%}")
        parts.append(f"预期正交性: {orthogonality:.1%}")
        
        return "; ".join(parts)

    def get_space_stats(self) -> Dict:
        """获取认知空间统计"""
        total_states = 3 ** 9
        explored = len(self.state_factors)
        total_factors = sum(len(v) for v in self.state_factors.values())
        avg_per_state = total_factors / explored if explored else 0
        
        # 高成功格点
        high_quality = [idx for idx, q in self.state_quality.items() if q > 2.0]
        
        return {
            "total_states": total_states,
            "explored_states": explored,
            "exploration_ratio": explored / total_states,
            "total_factors": total_factors,
            "avg_factors_per_explored_state": avg_per_state,
            "high_quality_states": len(high_quality),
        }
