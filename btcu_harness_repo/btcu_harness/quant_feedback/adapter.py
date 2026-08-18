"""
因子实例适配器 —— 将WQB量化因子实例注入BTCU认知架构

把每个回测完成的因子当作一次「认知实验」：
- 成功的因子（高Fitness/低SC）→ 正反馈，强化对应维度的认知路径
- 失败的因子（INFERIOR/高SC）→ 负反馈，抑制并标记盲区
- 未知领域 → 悬置（空态），标记为高价值探索方向
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from ..core.state import CognitiveState
from ..core.trit import YIN, VOID, YANG
from ..memory.ecology import MemoryEcology, CognitiveEvent
from ..memory.trajectory import CognitiveTrajectory
from ..memory.climate import CognitiveClimate


FACTOR_DIMENSIONS = [
    "price_momentum",   # 价格动量
    "fundamental_value", # 基本面价值
    "quality_score",    # 质量因子
    "volatility_regime", # 波动率状态
    "liquidity_flow",   # 流动性
    "size_exposure",    # 市值暴露
    "sentiment_score",  # 情绪因子
    "analyst_momentum", # 分析师预期
    "options_signal",   # 期权信号
]


@dataclass
class FactorInstance:
    """一个因子实例 = 一次认知实验的完整记录"""
    alpha_id: str
    name: str
    expression: str
    fitness: float
    sharpe: float
    drawdown: float
    self_correlation: float
    grade: str
    stage: str
    data_sources: List[str]
    dim_values: Dict[str, float] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    @property
    def is_success(self) -> bool:
        return (self.fitness > 1.5 and 
                self.self_correlation < 0.3 and 
                self.drawdown < 0.09 and 
                self.grade in ("GOOD", "EXCELLENT", "SPECTACULAR", "SUPER", "LEGENDARY"))

    @property
    def novelty_score(self) -> float:
        return max(0.0, 1.0 - self.self_correlation) if self.self_correlation > 0 else 0.5

    @property
    def quality_score(self) -> float:
        return self.fitness * self.novelty_score * max(0, 1 - self.drawdown)


class QuantFeedbackAdapter:
    """
    量化反馈适配器
    
    将WQB因子实例转化为BTCU认知事件，驱动认知架构进化：
    1. 把因子特征映射到九维认知格点（CognitiveState）
    2. 根据因子质量决定反馈极性（+1成功 / -1失败 / 0未知）
    3. 更新气候、记忆、轨迹
    """

    def __init__(self, ecology: MemoryEcology, trajectory: CognitiveTrajectory, climate: CognitiveClimate):
        self.ecology = ecology
        self.trajectory = trajectory
        self.climate = climate
        self.factor_history: List[FactorInstance] = []
        self.dim_stats: Dict[str, Dict] = {d: {"count": 0, "sum": 0.0, "success_count": 0} for d in FACTOR_DIMENSIONS}

    def feed_factor(self, factor: FactorInstance) -> Dict:
        """注入一个因子实例，更新认知状态"""
        # 1. 映射到认知状态
        state = self._map_factor_to_state(factor)
        
        # 2. 确定反馈极性
        polarity = self._determine_polarity(factor)
        
        # 3. 记录认知事件到生态记忆
        outcome_map = {1: "positive", -1: "negative", 0: "neutral"}
        event = CognitiveEvent(
            state=state,
            context={
                "alpha_id": factor.alpha_id,
                "name": factor.name,
                "fitness": factor.fitness,
                "sc": factor.self_correlation,
                "grade": factor.grade,
                "polarity": polarity,
                "data_sources": factor.data_sources,
            },
            decision="factor_exploration",
            outcome=outcome_map.get(polarity, "neutral"),
            outcome_positive=polarity > 0 if polarity != 0 else None,
            trigger="factor_feedback",
        )
        self.ecology.remember(event)
        
        # 4. 更新轨迹
        self.trajectory.record(state, context={"factor": factor.name, "polarity": polarity})
        
        # 5. 更新维度统计
        self._update_dim_stats(factor)
        
        self.factor_history.append(factor)
        
        return {
            "alpha_id": factor.alpha_id,
            "state_index": state.index,
            "state_repr": str(state),
            "polarity": polarity,
            "quality": factor.quality_score,
            "novelty": factor.novelty_score,
        }

    def batch_feed(self, factors: List[FactorInstance]) -> List[Dict]:
        """批量注入因子实例"""
        return [self.feed_factor(f) for f in factors]

    def _map_factor_to_state(self, factor: FactorInstance) -> CognitiveState:
        """将因子特征映射到九维认知状态"""
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

    def _determine_polarity(self, factor: FactorInstance) -> int:
        """
        确定反馈极性：
        +1 = 成功因子（GOOD+ 且 F>1.5）
         0 = 中性（F在1.0~1.5）
        -1 = 失败（INFERIOR 或 F<1.0）
        """
        if factor.fitness > 1.5 and factor.grade in ("GOOD", "EXCELLENT", "SPECTACULAR", "SUPER", "LEGENDARY"):
            return 1
        elif factor.fitness < 1.0 or factor.grade == "INFERIOR":
            return -1
        else:
            return 0

    def _update_dim_stats(self, factor: FactorInstance):
        """更新每个维度的统计特征"""
        success = factor.fitness > 1.5
        for dim in FACTOR_DIMENSIONS:
            val = factor.dim_values.get(dim, 0.0)
            self.dim_stats[dim]["count"] += 1
            self.dim_stats[dim]["sum"] += val
            if success:
                self.dim_stats[dim]["success_count"] += 1

    def get_dimension_success_rates(self) -> Dict[str, float]:
        """获取每个维度的成功率"""
        rates = {}
        for dim, stats in self.dim_stats.items():
            if stats["count"] > 0:
                rates[dim] = stats["success_count"] / stats["count"]
            else:
                rates[dim] = 0.0
        return rates

    def get_summary(self) -> Dict:
        """获取反馈系统总览"""
        n = len(self.factor_history)
        if n == 0:
            return {"total_factors": 0}
        successes = sum(1 for f in self.factor_history if f.fitness > 1.5)
        avg_fitness = sum(f.fitness for f in self.factor_history) / n
        sc_values = [f.self_correlation for f in self.factor_history if f.self_correlation > 0]
        avg_sc = sum(sc_values) / len(sc_values) if sc_values else 0
        
        return {
            "total_factors": n,
            "success_count": successes,
            "success_rate": successes / n,
            "avg_fitness": avg_fitness,
            "avg_self_correlation": avg_sc,
            "trajectory_length": self.trajectory.length,
            "dimension_rates": self.get_dimension_success_rates(),
        }
