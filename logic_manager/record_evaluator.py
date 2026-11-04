"""LogicManager: the coordinator of the Logic layer."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .base_evaluator import BaseEvaluator
from .business_rules import (
    FinanceFlagRule,
    SafetyOverrideRule,
    SleepFlagRule,
    SupportFlagRule,
    SupportPriorityRule,
    WorkloadFlagRule,
)
from .errors import ScoreMismatchError
from .factor_cards import FactorCardBuilder
from .models import EnrichedRecord, EvaluationResult, RiskTier, RuleContext, RuleReport
from .score_calculator import ScoreCalculator
from .tip_planner import TipPlanner


class LogicManager:
    """Turns one AI-enriched check-in into an EvaluationResult.

    For every record it:
      1. checks the record's fields                    (EnrichedRecord)
      2. works out Logic's own score                   (ScoreCalculator)
      3. cross-checks Gemini's score, within 0.01      (else ScoreMismatchError)
      4. runs every business rule the same way         (BaseEvaluator objects)
      5. picks the final tier, tips and factor cards   (TipPlanner, FactorCardBuilder)

    Logic never replaces Gemini's score with its own. Its own score is kept
    only as an audit value (``logic_stress_score``).

    Relationships with the objects it uses:
      * aggregation: the rules are created outside and handed in. They exist
        on their own and can be reused (tests and other managers do).
      * association: the ScoreCalculator is also used by AIScoreVerifier.
        LogicManager uses it but does not own it.
      * composition: the TipPlanner and FactorCardBuilder are created here,
        are private, and exist only as part of this manager.

    A LogicManager never changes after it is created, so one instance can
    safely serve every request.
    """

    LOGIC_RULE_VERSION = "v3"

    def __init__(
        self,
        rules: Iterable[BaseEvaluator] | None = None,
        calculator: ScoreCalculator | None = None,
        max_tips: int = TipPlanner.DEFAULT_MAX_TIPS,
    ) -> None:
        self.__rules = tuple(rules) if rules is not None else self.default_rules()
        if not all(isinstance(rule, BaseEvaluator) for rule in self.__rules):
            raise TypeError("Every rule must be a BaseEvaluator.")
        names = [rule.name for rule in self.__rules]
        if len(names) != len(set(names)):
            raise ValueError("Every rule needs a different name.")
        self.__calculator = calculator if calculator is not None else ScoreCalculator()
        self.__tip_planner = TipPlanner(max_tips)
        self.__card_builder = FactorCardBuilder()

    @staticmethod
    def default_rules() -> tuple[BaseEvaluator, ...]:
        """The Phase 1 rules, in the Phase 1 order."""
        return (
            SafetyOverrideRule(),
            SupportPriorityRule(),
            SleepFlagRule(),
            WorkloadFlagRule(),
            FinanceFlagRule(),
            SupportFlagRule(),
        )

    @property
    def rules(self) -> tuple[BaseEvaluator, ...]:
        """The rules this manager runs, in order (read-only)."""
        return self.__rules

    @property
    def calculator(self) -> ScoreCalculator:
        return self.__calculator

    def evaluate(self, record: Mapping[str, Any]) -> EvaluationResult:
        """Evaluate the dict that ai_manager produced.

        Raises RecordValidationError if fields are missing or unusable, and
        ScoreMismatchError if Gemini's score disagrees with the answers.
        Both are LogicManagerError: treat them like any AI failure.
        """
        return self.evaluate_record(EnrichedRecord.from_dict(record))

    def evaluate_record(self, record: EnrichedRecord) -> EvaluationResult:
        """Evaluate a record that has already been converted to an EnrichedRecord."""
        scores = self.__calculator.breakdown(record.answers)
        ai = record.assessment
        if not self.__calculator.within_tolerance(ai.stress_score, scores.stress_score):
            raise ScoreMismatchError(ai.stress_score, scores.stress_score)

        context = RuleContext(record=record, scores=scores)
        # Polymorphism: every rule is called the same way, whatever its class.
        report = RuleReport(tuple(rule.evaluate(context) for rule in self.__rules))

        return EvaluationResult(
            record=record,
            scores=scores,
            tier=RiskTier.most_severe((ai.tier, *report.escalations)),
            tips=self.__tip_planner.plan(report.lead_tips, ai.tips, report.extra_tips),
            risk_score=self.__calculator.risk_score(ai.stress_score),
            report=report,
            factor_cards=self.__card_builder.build(record.answers, scores, report.context_flags),
            logic_rule=self.LOGIC_RULE_VERSION,
        )

    def score(self, record: Mapping[str, Any]) -> float:
        """Gemini's stress score once Logic has accepted it.

        Raises LogicManagerError when Logic rejects the record (Phase 1
        returned None instead).
        """
        return self.evaluate(record).stress_score

    def route(self, result: EvaluationResult) -> str:
        """The outcome path for an evaluated record: "Low", "Moderate" or "High"."""
        return result.route
