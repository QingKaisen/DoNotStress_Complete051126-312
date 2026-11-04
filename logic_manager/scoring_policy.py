"""ScoringPolicy: the team's scoring numbers in one place."""

from __future__ import annotations

from dataclasses import dataclass

from .models import StudentAnswers


@dataclass(frozen=True)
class ScoringPolicy:
    """The numbers behind the stress score and the tiers.

    The defaults are the Phase 1 rules (logic_rule "v3"):

    * pss_2, pss_3 and the two support items are positively worded, so they
      are scored as 6 - answer.
    * Sleep hours become 1-5: 8+ h -> 1, 7 to <8 -> 2, 6 to <7 -> 3,
      5 to <6 -> 4, under 5 -> 5.
    * Tiers: Low below 2.5, Moderate 2.5 to 3.5 inclusive, High above 3.5.
    * Gemini's score must be within 0.01 of Logic's.

    To try other numbers, pass a different policy to ScoreCalculator; no
    class has to change (Open/Closed). The policy checks itself when it is
    created, so a typo cannot quietly produce wrong scores.
    """

    scale_min: int = StudentAnswers.LIKERT_MIN
    scale_max: int = StudentAnswers.LIKERT_MAX
    reversed_keys: tuple[str, ...] = ("pss_2", "pss_3", "mspss_friends", "mspss_family")
    support_keys: tuple[str, ...] = ("mspss_friends", "mspss_family")
    sleep_hour_bands: tuple[tuple[float, int], ...] = ((8, 1), (7, 2), (6, 3), (5, 4))
    sleep_hours_below_all: int = 5
    check_in_from: float = 2.5
    reach_out_above: float = 3.5
    score_tolerance: float = 0.01
    decimal_places: int = 2

    def __post_init__(self) -> None:
        known = set(StudentAnswers.KEYS)
        unknown = [key for key in (*self.reversed_keys, *self.support_keys) if key not in known]
        if unknown:
            raise ValueError(f"Unknown answer keys in the policy: {', '.join(unknown)}")
        if not self.support_keys:
            raise ValueError("support_keys needs at least one answer key.")
        if self.scale_min >= self.scale_max:
            raise ValueError("scale_min must be below scale_max.")
        if not self.scale_min <= self.check_in_from <= self.reach_out_above <= self.scale_max:
            raise ValueError("Tier thresholds must sit inside the scale, lowest first.")
        hours = [band[0] for band in self.sleep_hour_bands]
        if not hours or hours != sorted(hours, reverse=True):
            raise ValueError("sleep_hour_bands must run from the most hours to the fewest.")
        if self.score_tolerance < 0 or self.decimal_places < 0:
            raise ValueError("score_tolerance and decimal_places cannot be negative.")
