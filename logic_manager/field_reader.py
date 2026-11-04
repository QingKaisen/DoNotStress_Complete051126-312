"""FieldReader: reads typed values out of one input dict and collects problems."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .errors import RecordValidationError


class FieldReader:
    """Reads fields from a plain dict (one record from ai_manager).

    It does not stop at the first bad field. It remembers every missing or
    unusable key, so a single RecordValidationError can list all of them.
    The dict itself is only read, never changed.
    """

    def __init__(self, data: Mapping[str, Any]) -> None:
        self.__data = data
        self.__missing: list[str] = []
        self.__invalid: list[str] = []

    @property
    def has_problems(self) -> bool:
        """True once any field was missing or unusable."""
        return bool(self.__missing or self.__invalid)

    def raise_if_problems(self) -> None:
        """Raise one RecordValidationError that lists every problem found so far."""
        if self.has_problems:
            raise RecordValidationError(missing=self.__missing, invalid=self.__invalid)

    def mark_invalid(self, key: str) -> None:
        """Record that ``key`` is present but unusable."""
        if key not in self.__invalid:
            self.__invalid.append(key)

    def number(self, key: str, low: float, high: float, *, whole: bool = False) -> float | None:
        """A finite number from ``low`` to ``high`` (inclusive), or None.

        With ``whole=True`` the number must also be a whole number (3 or 3.0,
        not 2.5).
        """
        if not self.__present(key):
            return None
        number = self.to_number(self.__data[key])
        if number is None or not low <= number <= high or (whole and not number.is_integer()):
            self.mark_invalid(key)
            return None
        return number

    def text(self, key: str) -> str | None:
        """A string value, or None if it is missing or not a string."""
        if not self.__present(key):
            return None
        value = self.__data[key]
        if not isinstance(value, str):
            self.mark_invalid(key)
            return None
        return value

    def text_list(self, key: str) -> tuple[str, ...] | None:
        """A list of strings, returned as a tuple, or None if unusable."""
        if not self.__present(key):
            return None
        value = self.__data[key]
        if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
            self.mark_invalid(key)
            return None
        return tuple(value)

    def optional_mapping(self, key: str) -> dict[str, Any] | None:
        """A copy of an optional dict. Absent or None gives None; anything else is unusable."""
        value = self.__data.get(key)
        if value is None:
            return None
        if not isinstance(value, Mapping):
            self.mark_invalid(key)
            return None
        return dict(value)

    @staticmethod
    def to_number(value: Any) -> float | None:
        """``value`` as a finite float, or None.

        None, True/False, text that is not a number, NaN and infinity all
        give None. Number-like text such as "3" is accepted, as in Phase 1.
        """
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if math.isfinite(number) else None

    def __present(self, key: str) -> bool:
        """True if ``key`` is in the dict; otherwise note it as missing."""
        if key in self.__data:
            return True
        self.__missing.append(key)
        return False
