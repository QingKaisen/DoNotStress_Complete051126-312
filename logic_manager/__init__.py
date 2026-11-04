"""DoNotStress Logic Manager (Phase 2, object-oriented).

Applies the team's domain rules to a check-in that Gemini has already
analysed: it re-checks Gemini's score, runs the business rules, classifies
the outcome, and prepares the result for storage and for display.

Wiring in main.py::

    from logic_manager import AIScoreVerifier, LogicManager, ScoreCalculator

    calculator = ScoreCalculator()                  # one set of scoring numbers,
    logic = LogicManager(calculator=calculator)
    verifier = AIScoreVerifier(calculator)          # shared with the AI Manager

    enriched = ai.analyse(student)                  # dict from ai_manager
    result = logic.evaluate(enriched)               # EvaluationResult, or LogicManagerError
    store.save(result.to_record())                  # data_manager
    display.display_result(result.to_display())     # io_manager

Plain Python only: no printing, no network and no files. Every method gives
the same answer for the same input, so tests can use hardcoded sample AI
replies instead of the live API.
"""

from .base_evaluator import BaseEvaluator
from .business_rules import (
    ContextFlagRule,
    FinanceFlagRule,
    SafetyOverrideRule,
    SleepFlagRule,
    SupportFlagRule,
    SupportPriorityRule,
    WorkloadFlagRule,
)
from .errors import LogicManagerError, RecordValidationError, ScoreMismatchError
from .factor_cards import FactorCardBuilder
from .models import (
    AIAssessment,
    EnrichedRecord,
    EvaluationResult,
    FactorCard,
    RiskTier,
    RuleContext,
    RuleOutcome,
    RuleReport,
    ScoreBreakdown,
    StudentAnswers,
)
from .record_evaluator import LogicManager
from .score_calculator import ScoreCalculator
from .score_verifier import AIScoreVerifier
from .scoring_policy import ScoringPolicy
from .tip_planner import TipPlanner

__all__ = [
    "AIAssessment",
    "AIScoreVerifier",
    "BaseEvaluator",
    "ContextFlagRule",
    "EnrichedRecord",
    "EvaluationResult",
    "FactorCard",
    "FactorCardBuilder",
    "FinanceFlagRule",
    "LogicManager",
    "LogicManagerError",
    "RecordValidationError",
    "RiskTier",
    "RuleContext",
    "RuleOutcome",
    "RuleReport",
    "SafetyOverrideRule",
    "ScoreBreakdown",
    "ScoreCalculator",
    "ScoreMismatchError",
    "ScoringPolicy",
    "SleepFlagRule",
    "StudentAnswers",
    "SupportFlagRule",
    "SupportPriorityRule",
    "TipPlanner",
    "WorkloadFlagRule",
]
