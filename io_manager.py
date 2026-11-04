"""DoNotStress — IO Manager.

Student input validation and presentation for the evidence-v3 (1-5) survey.

Provides:
* Functional validators and formatters used by main.py and the campus UI.
* ResultDisplay implementations (ConsoleResultDisplay, RecordingDisplay).

Question wording and scales live in survey.py. Reflection is ephemeral.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

import survey

# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------

class ResultDisplay(ABC):
    @abstractmethod
    def display_result(self, view: Mapping[str, Any]) -> None:
        """Show one student's result."""

    @abstractmethod
    def display_record(self, record: Mapping[str, Any]) -> None:
        """Show one stored record."""

    @abstractmethod
    def display_list(self, records: Sequence[Mapping[str, Any]]) -> None:
        """Show a summary list of stored records."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUESTION_MAP = survey.QUESTION_MAP
QUESTIONS = survey.QUESTIONS
FORM_FIELDS = ("student_id", "feelings_text", *survey.QUESTION_MAP)
FORM_PROMPTS = {
    "student_id": "Student ID",
    "feelings_text": "Anything on your mind about school or life lately?",
    **{q["key"]: q["prompt"] for q in QUESTIONS},
}
RECORD_FIELD_ORDER = (
    "student_id", "survey_version", "safety_flag",
    *survey.QUESTION_MAP,
    "stress_score", "risk_category", "soft_label", "tips", "reasoning",
)
REQUIRED_FORM_FIELDS = ("student_id", *survey.QUESTION_MAP)
STUDENT_ID_EXAMPLE = "2605581"

SOFT_LABELS = ("You're doing ok", "Worth a check-in", "Please reach out")
SOFT_LABEL_COPY = {
    "You're doing ok": {
        "label": "You're doing ok",
        "heading": "You're doing ok",
        "body": "Your check-in looks steady. Keep looking after yourself.",
        "tone": "reassuring",
    },
    "Worth a check-in": {
        "label": "Worth a check-in",
        "heading": "Worth a check-in",
        "body": "Some things look a bit heavier right now. A conversation could help.",
        "tone": "supportive",
    },
    "Please reach out": {
        "label": "Please reach out",
        "heading": "Please reach out",
        "body": "Please reach out for support. You do not have to handle this on your own.",
        "tone": "urgent",
    },
}

TIPS_ALLOWLIST = {
    "sleep_routine": "Try to keep a regular sleep schedule, including on weekends.",
    "rest_a_little_more": "If you can, give yourself a bit more rest — even 30 extra minutes can help.",
    "short_breaks": "Take short, planned breaks between study blocks instead of pushing through without a pause.",
    "workload_chunks": "Break larger assignments into smaller tasks and spread them across the week.",
    "money_worries": "If money is on your mind, campus support can help you find the right next step.",
    "talk_to_someone": "Reach out to a friend, classmate, or family member — you do not have to handle this alone.",
    "keep_social_contact": "Stay in touch with people who help you feel supported, even with a short check-in.",
}

SPEAK_PROMINENCE = ("low", "medium", "high")
ADVISOR_EMAIL = "SITCounselling@SingaporeTech.edu.sg"
ADVISOR_HELPLINE = "6592 2030"
ADVISOR_MAILTO = "mailto:SITCounselling@SingaporeTech.edu.sg"
SOS_HELPLINE = "1767"
MINDLINE_HELPLINE = "1771"
ADVISOR_CONTACTS = {
    "email": ADVISOR_EMAIL,
    "helpline": ADVISOR_HELPLINE,
    "sos": SOS_HELPLINE,
    "mindline": MINDLINE_HELPLINE,
    "mailto": ADVISOR_MAILTO,
}

SPEAK_PANEL_COPY = {
    "low": {
        "heading": "Support is available",
        "body": "If you would like to talk, you can contact SIT Counselling.",
        "cta": "Optional: get in touch",
    },
    "medium": {
        "heading": "Consider speaking with someone",
        "body": "It may help to talk with SIT Counselling about how you have been feeling.",
        "cta": "Reach out when you are ready",
    },
    "high": {
        "heading": "Please reach out",
        "body": "You do not have to handle this on your own. SIT Counselling is here to help.",
        "cta": "Contact support now",
    },
}

AI_UNAVAILABLE_HEADING = "We could not finish your check-in"
AI_UNAVAILABLE_BODY = "Your answers are still here. Please try again in a moment."
AI_UNAVAILABLE_ACTION_LABEL = "Try again"
AI_UNAVAILABLE_TONE = "calm"
AI_REQUIRED_HINT = "This check-in needs the AI service to complete."
AI_RATE_LIMITED_BODY = "The service is busy right now. Please try again shortly."

AI_ERROR_CODES = (
    "missing_api_key", "timeout", "invalid_response",
    "retries_exhausted", "rate_limited", "unavailable",
)
AI_ERROR_HINTS = {
    "missing_api_key": "The assessment service is not configured.",
    "timeout": "The assessment took too long. Please try again.",
    "invalid_response": "The assessment could not be read. Please try again.",
    "retries_exhausted": "We tried a few times and could not complete the check-in.",
    "rate_limited": AI_RATE_LIMITED_BODY,
    "unavailable": AI_UNAVAILABLE_BODY,
}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _as_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _looks_like_int(value: Any) -> bool:
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False


def _form_get(values: Mapping[str, Any], key: str) -> Any:
    return values.get(key)


def _looks_like_secret(value: Any) -> bool:
    text = _as_text(value).lower()
    return any(word in text for word in ("password", "secret", "api_key", "token"))


def _sanitize_operator_detail(detail: str) -> str:
    return re.sub(r"[^\w\s.,:;!?-]", "", detail)[:200]


def normalize_form_value(raw: Any) -> Any:
    if isinstance(raw, str):
        return raw.strip()
    return raw


def validate_student_id(raw: Any) -> tuple[bool, str | None]:
    text = _as_text(raw)
    if not re.fullmatch(r"2\d{6}", text):
        return False, "Enter a 7-digit student ID starting with 2."
    return True, text


def validate_feelings_text(raw: Any) -> tuple[bool, str | None]:
    text = _as_text(raw)
    if len(text) > 2000:
        return False, "Reflection must be 2,000 characters or fewer."
    return True, text


def validate_student_form(values: Mapping[str, Any]) -> tuple[bool, dict[str, Any] | dict[str, str]]:
    """Validate a submitted check-in form.

    Returns (True, clean_record) or (False, errors_dict).
    """
    if not isinstance(values, Mapping):
        return False, {"form": "Please submit a check-in form."}
    errors: dict[str, str] = {}
    clean: dict[str, Any] = {}

    ok, sid = validate_student_id(values.get("student_id"))
    if not ok:
        errors["student_id"] = sid or "Invalid student ID."
    else:
        clean["student_id"] = sid

    ok, feelings = validate_feelings_text(values.get("feelings_text", ""))
    if not ok:
        errors["feelings_text"] = feelings or "Invalid reflection."
    else:
        clean["feelings_text"] = feelings or ""

    for key in survey.QUESTION_MAP:
        raw = values.get(key)
        valid, value_or_msg = survey.validate_question(raw, survey.QUESTION_MAP[key])
        if not valid:
            errors[key] = value_or_msg or "Please answer this question."
        else:
            clean[key] = value_or_msg

    if errors:
        return False, errors

    clean["survey_version"] = survey.VERSION
    clean["safety_flag"] = survey.safety_check(clean.get("feelings_text", ""))
    return True, clean


# ---------------------------------------------------------------------------
# Formatting (student-facing)
# ---------------------------------------------------------------------------

def format_soft_label(label: str) -> dict[str, str]:
    return SOFT_LABEL_COPY.get(label, SOFT_LABEL_COPY["Worth a check-in"])


def format_tips(tip_ids: Sequence[str]) -> dict[str, Any]:
    items = []
    for tip_id in tip_ids:
        text = TIPS_ALLOWLIST.get(str(tip_id))
        if text:
            items.append({"id": tip_id, "text": text})
    return {
        "heading": "A few ideas that might help",
        "items": items,
    }


def format_speak_to_advisor_panel(prominence: str) -> dict[str, Any]:
    copy = SPEAK_PANEL_COPY.get(prominence, SPEAK_PANEL_COPY["medium"])
    return {
        **copy,
        **ADVISOR_CONTACTS,
        "prominence": prominence,
    }


def _ai_failure_copy(code: str) -> dict[str, str]:
    body = AI_ERROR_HINTS.get(code, AI_UNAVAILABLE_BODY)
    return {
        "heading": AI_UNAVAILABLE_HEADING,
        "body": body,
        "action_label": AI_UNAVAILABLE_ACTION_LABEL,
        "tone": AI_UNAVAILABLE_TONE,
    }


def format_ai_error(code: str) -> dict[str, Any]:
    """Student-facing copy for an AI failure, including the advisor panel."""
    copy = _ai_failure_copy(code)
    prominence = "high" if code in {"rate_limited", "unavailable", "retries_exhausted"} else "medium"
    return {
        **copy,
        "speak_to_advisor": format_speak_to_advisor_panel(prominence),
        "error_code": code,
    }


def format_student_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """A compact, display-ready view of one stored record."""
    return {
        key: record.get(key)
        for key in RECORD_FIELD_ORDER
        if key in record
    }


# ---------------------------------------------------------------------------
# Optional CLI helpers (not used by the web app)
# ---------------------------------------------------------------------------

def print_message(text: str) -> None:
    print(text)


def print_error(text: str) -> None:
    print(f"Error: {text}")


def display_record(record: Mapping[str, Any]) -> None:
    print_message(str(format_student_record(record)))


def display_list(records: Sequence[Mapping[str, Any]]) -> None:
    for record in records:
        display_record(record)


def display_result(view: Mapping[str, Any]) -> None:
    soft = view.get("soft_label", "")
    print_message(format_soft_label(soft).get("heading", soft))
    tips = format_tips(view.get("tips", []))
    for item in tips["items"]:
        print_message(f"• {item['text']}")


# ---------------------------------------------------------------------------
# OOP display classes
# ---------------------------------------------------------------------------

class ConsoleResultDisplay(ResultDisplay):
    """Simple console implementation of ResultDisplay (useful for CLI demos)."""

    def display_result(self, view: Mapping[str, Any]) -> None:
        display_result(view)

    def display_record(self, record: Mapping[str, Any]) -> None:
        display_record(record)

    def display_list(self, records: Sequence[Mapping[str, Any]]) -> None:
        display_list(records)


class RecordingDisplay(ResultDisplay):
    """Test double that remembers what it was asked to show."""

    def __init__(self) -> None:
        self._shown: list[tuple[str, Any]] = []

    @property
    def shown(self) -> tuple[tuple[str, Any], ...]:
        return tuple(self._shown)

    def display_result(self, view: Mapping[str, Any]) -> None:
        self._shown.append(("result", dict(view)))

    def display_record(self, record: Mapping[str, Any]) -> None:
        self._shown.append(("record", dict(record)))

    def display_list(self, records: Sequence[Mapping[str, Any]]) -> None:
        self._shown.append(("list", [dict(r) for r in records]))


class StudentIO:
    """Student-facing I/O operations, injected into the app.

    Wraps the pure validators and formatters so main.py can depend on an
    instance instead of module-level functions.
    """

    def validate_form(self, values: Mapping[str, Any]) -> tuple[bool, dict[str, Any] | dict[str, str]]:
        return validate_student_form(values)

    def format_soft_label(self, label: str) -> dict[str, str]:
        return format_soft_label(label)

    def format_tips(self, tip_ids: Sequence[str]) -> dict[str, Any]:
        return format_tips(tip_ids)

    def format_advisor(self, prominence: str) -> dict[str, Any]:
        return format_speak_to_advisor_panel(prominence)

    def format_ai_error(self, code: str) -> dict[str, Any]:
        return format_ai_error(code)


__all__ = [
    "ResultDisplay",
    "ConsoleResultDisplay",
    "RecordingDisplay",
    "StudentIO",
    "validate_student_form",
    "validate_student_id",
    "validate_feelings_text",
    "format_soft_label",
    "format_tips",
    "format_speak_to_advisor_panel",
    "format_ai_error",
    "format_student_record",
    "display_result",
    "display_record",
    "display_list",
]
