"""FactorCardBuilder: the four cards on the student result page."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .models import (
    FLAG_FINANCES,
    FLAG_SLEEP,
    FLAG_SUPPORT,
    FLAG_WORKLOAD,
    FactorCard,
    ScoreBreakdown,
    StudentAnswers,
)


class FactorCardBuilder:
    """Builds the four factor cards: rest, study, money and support.

    A card is marked ``flagged`` (shown as "Worth some attention") only when
    its context flag is raised. The wording is the same as in Phase 1.
    """

    _SLEEP_QUALITY_LABELS = ("Very good", "Fairly good", "Okay", "Fairly bad", "Very bad")
    _AGREE_LABELS = ("Strongly disagree", "Disagree", "Neutral", "Agree", "Strongly agree")
    _FINANCE_LABELS = (
        "No stress at all",
        "A little stress",
        "Moderate stress",
        "High stress",
        "Overwhelming stress",
    )

    def build(
        self,
        answers: StudentAnswers,
        scores: ScoreBreakdown,
        flags: Mapping[str, bool],
    ) -> tuple[FactorCard, ...]:
        """The four cards, in the order the result page shows them."""
        return (
            self._rest_card(answers, flags.get(FLAG_SLEEP, False)),
            self._study_card(answers, flags.get(FLAG_WORKLOAD, False)),
            self._money_card(answers, flags.get(FLAG_FINANCES, False)),
            self._support_card(scores, flags.get(FLAG_SUPPORT, False)),
        )

    def _rest_card(self, answers: StudentAnswers, flagged: bool) -> FactorCard:
        quality = self._label(self._SLEEP_QUALITY_LABELS, answers.sleep_quality)
        return FactorCard(
            title="Rest & recovery",
            flagged=flagged,
            value=f"{answers.sleep_hours_avg:g} hours · {quality} quality",
            text=(
                "Sleep and stress affect each other. When sleep is short or "
                "restless, everyday tasks can feel harder, and stress can make "
                "it harder to sleep well."
            ),
        )

    def _study_card(self, answers: StudentAnswers, flagged: bool) -> FactorCard:
        workload = answers.pas_workload
        return FactorCard(
            title="Study demands",
            flagged=flagged,
            value=f"{workload}/5 · {self._label(self._AGREE_LABELS, workload)}",
            text=(
                "A heavy workload can leave less time to rest and recharge. "
                "Feeling behind or overloaded is one of the most common sources "
                "of student stress."
            ),
        )

    def _money_card(self, answers: StudentAnswers, flagged: bool) -> FactorCard:
        finances = answers.fin_stress
        return FactorCard(
            title="Money pressures",
            flagged=flagged,
            value=f"{finances}/5 · {self._label(self._FINANCE_LABELS, finances)}",
            text=(
                "Financial worries can add to the pressure of studying. "
                "Concerns about money often weigh on focus and sleep."
            ),
        )

    def _support_card(self, scores: ScoreBreakdown, flagged: bool) -> FactorCard:
        return FactorCard(
            title="Support & connection",
            flagged=flagged,
            value=(
                f"{scores.support_mean:g}/5 agreement across "
                f"{scores.support_item_count} answers"
            ),
            text=(
                "Having people to turn to can make stressful times easier to "
                "handle. Strong support from friends or family helps protect "
                "against stress."
            ),
        )

    @staticmethod
    def _label(labels: Sequence[str], answer: int) -> str:
        """The word for a 1-5 answer, e.g. 3 -> "Okay"."""
        return labels[answer - 1]
