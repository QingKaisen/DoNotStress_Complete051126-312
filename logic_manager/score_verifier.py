"""AIScoreVerifier: the scoring contract between Logic and Gemini."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import RecordValidationError
from .field_reader import FieldReader
from .models import RiskTier, StudentAnswers
from .score_calculator import ScoreCalculator


class AIScoreVerifier:
    """Makes sure Gemini follows Logic's scoring rules.

    Logic owns the scoring rules, but the AI Manager is the one talking to
    Gemini. So main.py hands the AI Manager one of these objects:

    * ``instructions()`` gives the formula and tier rules for the prompt.
    * ``verify()`` checks Gemini's arithmetic and tier before the reply is
      accepted. The AI Manager retries a reply that fails, like bad JSON.

    The verifier uses a ScoreCalculator that it is given but does not own
    (association). Sharing one calculator with LogicManager means the prompt,
    the check and the evaluation can never disagree.
    """

    def __init__(self, calculator: ScoreCalculator) -> None:
        self.__calculator = calculator

    @property
    def calculator(self) -> ScoreCalculator:
        return self.__calculator

    def instructions(self) -> str:
        """The scoring formula and tier rules, written as instructions for Gemini."""
        policy = self.__calculator.policy
        low, high = policy.scale_min, policy.scale_max
        reversed_keys = ", ".join(policy.reversed_keys)
        bands = ", ".join(
            f"{hours:g} or more{' hours' if index == 0 else ''} -> {value}"
            for index, (hours, value) in enumerate(policy.sleep_hour_bands)
        )
        return (
            f"Convert each answer onto the {low} to {high} stress scale:\n"
            f"- {reversed_keys} are positively worded. Convert each as {low + high} - answer.\n"
            f"- {StudentAnswers.SLEEP_KEY} is hours from {StudentAnswers.SLEEP_HOURS_MIN:g} "
            f"to {StudentAnswers.SLEEP_HOURS_MAX:g} in half-hour steps. "
            f"Convert it as: {bands}, otherwise {policy.sleep_hours_below_all}.\n"
            f"- Every other answer is already on the {low} to {high} scale. "
            "Use the number as answered.\n"
            f"stress_score is the mean of those {len(StudentAnswers.KEYS)} converted values, "
            f"rounded to {policy.decimal_places} decimal places. Higher stress is worse.\n"
            "Then set the tier from that stress_score:\n"
            f"- below {policy.check_in_from:g}: {self.__describe(RiskTier.LOW)}\n"
            f"- {policy.check_in_from:g} to {policy.reach_out_above:g} inclusive: "
            f"{self.__describe(RiskTier.MODERATE)}\n"
            f"- above {policy.reach_out_above:g}: {self.__describe(RiskTier.HIGH)}\n"
            "These bands are a simple guide for this check-in, not clinical cut-offs.\n"
        )

    def verify(self, ai_fields: Mapping[str, Any], answers: Mapping[str, Any]) -> str | None:
        """Check Gemini's numbers against the student's answers.

        Checks, in order:
          1. risk_category, soft_label and speak_prominence match the tier of
             Gemini's own stress_score
          2. scored_items equal the converted answers exactly
          3. stress_score is within the tolerance of the mean of those items

        Returns the first problem as a message, or None when everything
        matches. Never raises.
        """
        if not isinstance(ai_fields, Mapping) or not isinstance(answers, Mapping):
            return "verify needs the AI fields and the answers as dicts."
        try:
            student = StudentAnswers.from_mapping(answers)
        except RecordValidationError as error:
            unusable = [key for key in StudentAnswers.KEYS if key in error.missing + error.invalid]
            return f"Cannot convert {', '.join(unusable)} onto the 1-5 stress scale."
        ai_score = FieldReader.to_number(ai_fields.get("stress_score"))
        if ai_score is None:
            return "stress_score must be a number."
        return self.__tier_problem(ai_fields, ai_score) or self.__arithmetic_problem(
            ai_fields, ai_score, student
        )

    def __tier_problem(self, ai_fields: Mapping[str, Any], ai_score: float) -> str | None:
        """The tier fields must match the tier of Gemini's own score."""
        expected = self.__calculator.tier_for(ai_score)
        if ai_fields.get("risk_category") != expected.category:
            return f"risk_category must be {expected.category} for stress_score {ai_score}."
        if ai_fields.get("soft_label") != expected.soft_label:
            return "soft_label must match risk_category."
        if ai_fields.get("speak_prominence") != expected.speak_prominence:
            return "speak_prominence must match risk_category."
        return None

    def __arithmetic_problem(
        self, ai_fields: Mapping[str, Any], ai_score: float, student: StudentAnswers
    ) -> str | None:
        """Gemini's converted items and mean must match Logic's arithmetic."""
        if ai_fields.get("scored_items") != self.__calculator.scored_items(student):
            return "scored_items does not match the converted answers."
        logic_score = self.__calculator.stress_score(student)
        if not self.__calculator.within_tolerance(ai_score, logic_score):
            return (
                f"stress_score must match the mean of the {len(StudentAnswers.KEYS)} "
                f"converted answers (expected {logic_score})."
            )
        return None

    @staticmethod
    def __describe(tier: RiskTier) -> str:
        return (
            f'risk_category {tier.category}, soft_label "{tier.soft_label}", '
            f"speak_prominence {tier.speak_prominence}"
        )
