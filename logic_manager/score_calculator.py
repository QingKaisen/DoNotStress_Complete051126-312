"""ScoreCalculator: Logic's own scoring and classification."""

from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType

from .models import RiskTier, ScoreBreakdown, StudentAnswers
from .scoring_policy import ScoringPolicy


class ScoreCalculator:
    """Works out the 1-5 stress score and its tier from the 11 answers.

    Single responsibility: arithmetic and classification only. It knows
    nothing about tips, Gemini, storage or display. It never changes after
    it is created, so one calculator can safely be shared: LogicManager and
    AIScoreVerifier use the same one, so the prompt, the check and the
    evaluation always agree on the numbers.
    """

    # Tiny allowance for floating-point error, so a score exactly 0.01 off
    # (for example 4.63 against 4.64) is accepted, as in Phase 1.
    _FLOAT_SLACK = 1e-9

    def __init__(self, policy: ScoringPolicy | None = None) -> None:
        self.__policy = policy if policy is not None else ScoringPolicy()

    @property
    def policy(self) -> ScoringPolicy:
        """The numbers this calculator uses (read-only)."""
        return self.__policy

    def convert(self, key: str, answer: float) -> int:
        """One answer on the 1-5 stress scale, where higher always means more stress."""
        if key == StudentAnswers.SLEEP_KEY:
            return self.sleep_hours_stress(answer)
        if key in self.__policy.reversed_keys:
            return int(self.__policy.scale_min + self.__policy.scale_max - answer)
        return int(answer)

    def sleep_hours_stress(self, hours: float) -> int:
        """Typical nightly hours on the 1-5 stress scale (used for scoring only)."""
        for at_least, value in self.__policy.sleep_hour_bands:
            if hours >= at_least:
                return value
        return self.__policy.sleep_hours_below_all

    def scored_items(self, answers: StudentAnswers) -> dict[str, int]:
        """All 11 answers converted. This is exactly what Gemini must return as scored_items."""
        return {key: self.convert(key, answers.value(key)) for key in StudentAnswers.KEYS}

    def stress_score(self, answers: StudentAnswers) -> float:
        """Mean of the 11 converted answers, rounded (2 decimal places by default)."""
        return self.__mean(self.scored_items(answers).values())

    def support_mean(self, answers: StudentAnswers) -> float:
        """Mean raw agreement of the support answers (not reverse-scored)."""
        return self.__mean(answers.value(key) for key in self.__policy.support_keys)

    def tier_for(self, stress_score: float) -> RiskTier:
        """Low below 2.5, Moderate 2.5 to 3.5 inclusive, High above 3.5 (by default)."""
        if stress_score > self.__policy.reach_out_above:
            return RiskTier.HIGH
        if stress_score >= self.__policy.check_in_from:
            return RiskTier.MODERATE
        return RiskTier.LOW

    def risk_score(self, stress_score: float) -> float:
        """The 1-5 score mapped onto 0-1. Kept for compatibility; not a probability."""
        span = self.__policy.scale_max - self.__policy.scale_min
        return (stress_score - self.__policy.scale_min) / span

    def within_tolerance(self, ai_score: float, logic_score: float) -> bool:
        """True when Gemini's score is close enough to Logic's (0.01 by default)."""
        return abs(ai_score - logic_score) <= self.__policy.score_tolerance + self._FLOAT_SLACK

    def breakdown(self, answers: StudentAnswers) -> ScoreBreakdown:
        """Every number Logic works out for one set of answers."""
        items = self.scored_items(answers)
        stress_score = self.__mean(items.values())
        return ScoreBreakdown(
            scored_items=MappingProxyType(items),
            stress_score=stress_score,
            support_mean=self.support_mean(answers),
            support_item_count=len(self.__policy.support_keys),
            tier=self.tier_for(stress_score),
        )

    def __mean(self, values: Iterable[float]) -> float:
        numbers = list(values)
        return round(sum(numbers) / len(numbers), self.__policy.decimal_places)
