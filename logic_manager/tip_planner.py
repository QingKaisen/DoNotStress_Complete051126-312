"""TipPlanner: decides the final, ordered list of tips."""

from __future__ import annotations

from collections.abc import Iterable


class TipPlanner:
    """Merges the rules' tips and Gemini's tips into one short list.

    Order: the rules' lead tips, then all of Gemini's tips, then the rules'
    extra tips while there is room. Repeats are dropped and the list never
    grows past ``max_tips``. With the default rules the lead holds at most
    one tip and Gemini gives at most three, so Gemini's tips are never
    pushed out.
    """

    DEFAULT_MAX_TIPS = 4

    def __init__(self, max_tips: int = DEFAULT_MAX_TIPS) -> None:
        if max_tips < 1:
            raise ValueError("max_tips must be at least 1.")
        self.__max_tips = max_tips

    @property
    def max_tips(self) -> int:
        return self.__max_tips

    def plan(
        self,
        lead: Iterable[str],
        ai_tips: Iterable[str],
        extra: Iterable[str],
    ) -> tuple[str, ...]:
        """The final tip IDs, in the order the student will see them."""
        ordered: list[str] = []
        for tip in (*lead, *ai_tips):
            if tip not in ordered:
                ordered.append(tip)
        for tip in extra:
            if len(ordered) >= self.__max_tips:
                break
            if tip not in ordered:
                ordered.append(tip)
        return tuple(ordered[: self.__max_tips])
