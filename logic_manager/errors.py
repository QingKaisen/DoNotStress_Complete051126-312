"""Errors the Logic Manager raises when it cannot give a result.

Every error here is a ``LogicManagerError``. The caller (main.py) can catch
that one type and treat the check-in like any other AI failure: save it as
pending and show no result. Each class also has a short ``code`` that the
I/O layer can turn into a message.
"""

from __future__ import annotations

from collections.abc import Iterable


class LogicManagerError(Exception):
    """Base class: Logic refused to produce a result for this record."""

    code = "logic_error"


class RecordValidationError(LogicManagerError):
    """The record from ai_manager is missing fields or has unusable values."""

    code = "ai_fields_required"

    def __init__(self, missing: Iterable[str] = (), invalid: Iterable[str] = ()) -> None:
        self._missing = tuple(missing)
        self._invalid = tuple(invalid)
        details = []
        if self._missing:
            details.append("missing " + ", ".join(self._missing))
        if self._invalid:
            details.append("unusable " + ", ".join(self._invalid))
        super().__init__(
            "Logic needs a complete AI-enriched record ("
            + ("; ".join(details) or "no details")
            + ")."
        )

    @property
    def missing(self) -> tuple[str, ...]:
        """Keys that were not in the record."""
        return self._missing

    @property
    def invalid(self) -> tuple[str, ...]:
        """Keys that were present but held a value Logic cannot use."""
        return self._invalid


class ScoreMismatchError(LogicManagerError):
    """Gemini's stress_score does not match the score worked out from the answers."""

    code = "score_mismatch"

    def __init__(self, ai_score: float, logic_score: float) -> None:
        self._ai_score = ai_score
        self._logic_score = logic_score
        super().__init__(
            f"Gemini stress_score {ai_score:g} does not match the answers "
            f"({logic_score:g}); no result is given."
        )

    @property
    def ai_score(self) -> float:
        """The score Gemini gave."""
        return self._ai_score

    @property
    def logic_score(self) -> float:
        """The score Logic worked out from the same answers."""
        return self._logic_score
