"""
Cognition package: System 1 / System 2 dual-system cognitive architecture.

Kahneman-style fast/slow thinking layered over the BTCU ternary state space.
"""

from .audit import (
    AuditConstants,
    AuditReport,
    AuditResult,
    CognitiveAuditor,
)
from .defense import (
    CognitiveSafetyGuard,
    SafetyConstants,
)
from .dual_system import Decision, DualSystemDecisionEngine
from .system1 import CognitivePattern, System1PatternLibrary

__all__ = [
    "AuditConstants",
    "AuditReport",
    "AuditResult",
    "CognitiveAuditor",
    "CognitivePattern",
    "CognitiveSafetyGuard",
    "Decision",
    "DualSystemDecisionEngine",
    "SafetyConstants",
    "System1PatternLibrary",
]
