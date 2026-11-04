"""Concrete business rules (strategies) that LogicManager runs.

LogicManager applies rules in the order it is given them, and earlier
rules' tips come first. LogicManager.default_rules() keeps the Phase 1 order.

Class tree::

    BaseEvaluator (interface)
    |-- SafetyOverrideRule
    |-- SupportPriorityRule         (the multi-condition rule on 2 AI fields)
    '-- ContextFlagRule (abstract)
        |-- SleepFlagRule
        |-- WorkloadFlagRule
        |-- FinanceFlagRule
        '-- SupportFlagRule
"""

from __future__ import annotations

from abc import abstractmethod
from typing import final

from .base_evaluator import BaseEvaluator
from .models import (
    FLAG_FINANCES,
    FLAG_SLEEP,
    FLAG_SUPPORT,
    FLAG_WORKLOAD,
    RULE_SAFETY_OVERRIDE,
    RULE_SUPPORT_PRIORITY,
    RiskTier,
    RuleContext,
    RuleOutcome,
)


class SafetyOverrideRule(BaseEvaluator):
    """If the reflection safety check fired, show "Please reach out".

    The check itself runs in io_manager. Logic only sees the True/False
    safety_flag, never the text. The tier is raised to High and "talk to
    someone" goes first. The stress score is not changed.
    """

    TIP = "talk_to_someone"
    NOTE = "safety_override: reflection safety check fired"

    @property
    def name(self) -> str:
        return RULE_SAFETY_OVERRIDE

    def evaluate(self, context: RuleContext) -> RuleOutcome:
        if not context.record.safety_flag:
            return RuleOutcome.not_triggered(self.name)
        return RuleOutcome(
            rule_name=self.name,
            triggered=True,
            lead_tips=(self.TIP,),
            minimum_tier=RiskTier.HIGH,
            note=self.NOTE,
        )


class SupportPriorityRule(BaseEvaluator):
    """The brief's multi-condition rule, using two fields from Gemini's reply.

    Fires when Gemini rated the check-in High (``risk_category``) AND named
    low social support as a stressor (``primary_stressors``). Then "talk to
    someone" goes first and "keep in touch" is added if there is room.

    It reads Gemini's own tier, not the tier after the safety override,
    exactly as in Phase 1.
    """

    REQUIRED_TIER = RiskTier.HIGH
    REQUIRED_STRESSOR = "low_social_support"
    LEAD_TIP = "talk_to_someone"
    EXTRA_TIP = "keep_social_contact"
    NOTE = "support_priority: High tier with low social support"

    @property
    def name(self) -> str:
        return RULE_SUPPORT_PRIORITY

    def evaluate(self, context: RuleContext) -> RuleOutcome:
        ai = context.assessment
        high_tier = ai.tier is self.REQUIRED_TIER
        low_support = self.REQUIRED_STRESSOR in ai.primary_stressors
        if not (high_tier and low_support):
            return RuleOutcome.not_triggered(self.name)
        return RuleOutcome(
            rule_name=self.name,
            triggered=True,
            lead_tips=(self.LEAD_TIP,),
            extra_tips=(self.EXTRA_TIP,),
            note=self.NOTE,
        )


class ContextFlagRule(BaseEvaluator):
    """ABSTRACT CLASS for the four context flags.

    The shared behaviour lives here (Template Method pattern): a raised flag
    adds its own tip and is reported in ``context_flags``. Each subclass
    only decides WHEN its flag is raised, by implementing ``_is_raised``.

    Flags never change the tier and never remove one of Gemini's tips.
    Their tip is only added if there is room.
    """

    def __init__(self, tip_id: str) -> None:
        self._tip_id = tip_id

    @property
    def tip_id(self) -> str:
        """The tip this flag adds when it is raised."""
        return self._tip_id

    @final
    def evaluate(self, context: RuleContext) -> RuleOutcome:
        if not self._is_raised(context):
            return RuleOutcome.not_triggered(self.name, context_flag=True)
        return RuleOutcome(
            rule_name=self.name,
            triggered=True,
            extra_tips=(self._tip_id,),
            context_flag=True,
        )

    @abstractmethod
    def _is_raised(self, context: RuleContext) -> bool:
        """True when this flag applies to the record."""


class SleepFlagRule(ContextFlagRule):
    """Short sleep (under 6 hours) OR poor sleep quality (fairly or very bad)."""

    def __init__(self, short_sleep_below: float = 6, poor_quality_from: int = 4) -> None:
        super().__init__("sleep_routine")
        self.__short_sleep_below = short_sleep_below
        self.__poor_quality_from = poor_quality_from

    @property
    def name(self) -> str:
        return FLAG_SLEEP

    @property
    def short_sleep_below(self) -> float:
        return self.__short_sleep_below

    @property
    def poor_quality_from(self) -> int:
        return self.__poor_quality_from

    def _is_raised(self, context: RuleContext) -> bool:
        answers = context.answers
        return (
            answers.sleep_hours_avg < self.__short_sleep_below
            or answers.sleep_quality >= self.__poor_quality_from
        )


class WorkloadFlagRule(ContextFlagRule):
    """The student agrees (4) or strongly agrees (5) that coursework is too much.

    The catch-up answer counts in the score but does not raise this flag.
    """

    def __init__(self, agree_from: int = 4) -> None:
        super().__init__("workload_chunks")
        self.__agree_from = agree_from

    @property
    def name(self) -> str:
        return FLAG_WORKLOAD

    @property
    def agree_from(self) -> int:
        return self.__agree_from

    def _is_raised(self, context: RuleContext) -> bool:
        return context.answers.pas_workload >= self.__agree_from


class FinanceFlagRule(ContextFlagRule):
    """High (4) or overwhelming (5) stress about money."""

    def __init__(self, stress_from: int = 4) -> None:
        super().__init__("money_worries")
        self.__stress_from = stress_from

    @property
    def name(self) -> str:
        return FLAG_FINANCES

    @property
    def stress_from(self) -> int:
        return self.__stress_from

    def _is_raised(self, context: RuleContext) -> bool:
        return context.answers.fin_stress >= self.__stress_from


class SupportFlagRule(ContextFlagRule):
    """Mostly disagreeing that friends and family are there (raw mean below 2.5)."""

    def __init__(self, mean_below: float = 2.5) -> None:
        super().__init__("talk_to_someone")
        self.__mean_below = mean_below

    @property
    def name(self) -> str:
        return FLAG_SUPPORT

    @property
    def mean_below(self) -> float:
        return self.__mean_below

    def _is_raised(self, context: RuleContext) -> bool:
        return context.scores.support_mean < self.__mean_below
