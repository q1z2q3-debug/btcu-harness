"""
量化反馈模块 - 将WQB因子研究数据注入BTCU认知架构

核心功能：
1. 因子实例反馈：每个因子作为认知事件，更新气候/记忆/轨迹
2. 九维因子空间映射：把实际因子特征映射到九维认知格点
3. 正交性探索推荐：基于已发布因子空间，推荐下一步探索方向
4. 进化诊断：计算认知熵、共振度、曲率场等指标
"""

from .adapter import QuantFeedbackAdapter, FactorInstance, FACTOR_DIMENSIONS
from .explorer import OrthogonalExplorer, ExplorationCandidate
from .diagnostics import CognitiveDiagnostics, DiagnosticReport
from .data_loader import WQBDataLoader

__all__ = [
    "QuantFeedbackAdapter", "FactorInstance", "FACTOR_DIMENSIONS",
    "OrthogonalExplorer", "ExplorationCandidate",
    "CognitiveDiagnostics", "DiagnosticReport",
    "WQBDataLoader",
]
