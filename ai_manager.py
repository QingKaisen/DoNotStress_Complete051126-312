"""DoNotStress — AI Processing Layer (ai_manager).

Sole owner of Gemini prompt construction, structured JSON API calls,
schema validation, and graceful retries.

This module provides both:
* An OOP GeminiAIManager that implements AIManagerInterface.
* Functional entry points (analyse_student, build_prompt, ...) used by main.py.

The AI Manager never invents a result. On failure it raises AIProcessingError
or returns a structured error so the check-in can be saved as pending.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from abc import ABC, abstractmethod
from typing import Protocol

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Contract (same as the interface stub so tests and main.py can import it)
# ---------------------------------------------------------------------------

class AIProcessingError(Exception):
    """AI could not give a usable result."""
    CODES = (
        "missing_api_key", "timeout", "invalid_response",
        "retries_exhausted", "rate_limited", "unavailable",
    )

    def __init__(self, code: str, detail: str = "") -> None:
        self._code = code if code in self.CODES else "unavailable"
        super().__init__(f"{self._code}: {detail}" if detail else self._code)

    @property
    def code(self) -> str:
        return self._code


class ScoreVerifier(Protocol):
    def instructions(self) -> str: ...
    def verify(self, ai_fields: Mapping[str, Any], answers: Mapping[str, Any]) -> str | None: ...


class AIManagerInterface(ABC):
    @abstractmethod
    def analyse(self, student: Mapping[str, Any]) -> dict[str, Any]:
        """Analyse one validated check-in from io_manager."""


# ---------------------------------------------------------------------------
# Constants (shared with the functional layer)
# ---------------------------------------------------------------------------

RAW_ANSWER_KEYS = (
    "pss_1", "pss_2", "pss_3", "pss_4",
    "sleep_hours_avg", "sleep_quality",
    "pas_workload", "pas_catchup",
    "fin_stress",
    "mspss_friends", "mspss_family",
)

STUDENT_PROMPT_FIELDS = ("survey_version",)

SOFT_LABEL_OK = "You're doing ok"
SOFT_LABEL_CHECK_IN = "Worth a check-in"
SOFT_LABEL_REACH_OUT = "Please reach out"
SOFT_LABELS = (SOFT_LABEL_OK, SOFT_LABEL_CHECK_IN, SOFT_LABEL_REACH_OUT)
ALLOWED_SOFT_LABELS = frozenset(SOFT_LABELS)

SPEAK_PROMINENCE = ("low", "medium", "high")
ALLOWED_SPEAK_PROMINENCE = frozenset(SPEAK_PROMINENCE)
ALLOWED_RISK_CATEGORIES = frozenset({"Low", "Moderate", "High"})
ALLOWED_PRIMARY_STRESSORS = frozenset({
    "academic_overload", "low_social_support", "high_stress",
    "financial_pressure", "sleep_deprivation",
})
ALLOWED_TIP_IDS = frozenset({
    "rest_a_little_more", "workload_chunks", "sleep_routine",
    "keep_social_contact", "talk_to_someone", "short_breaks", "money_worries",
})

STRESS_SCORE_MIN, STRESS_SCORE_MAX = 1.0, 5.0

ERROR_CODE_MISSING_API_KEY = "missing_api_key"
ERROR_CODE_TIMEOUT = "timeout"
ERROR_CODE_INVALID_RESPONSE = "invalid_response"
ERROR_CODE_RETRIES_EXHAUSTED = "retries_exhausted"
ERROR_CODE_RATE_LIMITED = "rate_limited"
ERROR_CODE_UNAVAILABLE = "unavailable"

AI_ERROR_CODES = (
    ERROR_CODE_MISSING_API_KEY, ERROR_CODE_TIMEOUT, ERROR_CODE_INVALID_RESPONSE,
    ERROR_CODE_RETRIES_EXHAUSTED, ERROR_CODE_RATE_LIMITED, ERROR_CODE_UNAVAILABLE,
)

AI_SOURCE = "gemini"
MODEL_CHAIN = (
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.8-flash",
)
_DEFAULT_MODEL = MODEL_CHAIN[0]
_DEFAULT_TEMPERATURE = 0.2
MAX_TOTAL_CALLS = 6

_REQUIRED_FIELDS = (
    "scored_items", "stress_score", "risk_category", "primary_stressors",
    "confidence", "reasoning", "soft_label", "tips", "speak_prominence",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _structured_ai_error(code: str, detail: str = "") -> dict[str, str]:
    code = code if code in AI_ERROR_CODES else ERROR_CODE_UNAVAILABLE
    return {"error_code": code, "detail": detail}


def _final_ai_error(last_kind: str, last_detail: str, attempts: int,
                    last_was_api_exception: bool,
                    failure_kinds: list[str] | None = None) -> dict[str, str]:
    if last_kind == ERROR_CODE_MISSING_API_KEY:
        return _structured_ai_error(ERROR_CODE_MISSING_API_KEY, last_detail)
    if last_kind == ERROR_CODE_RATE_LIMITED:
        return _structured_ai_error(ERROR_CODE_RATE_LIMITED, last_detail)
    if attempts >= 3 or (failure_kinds and len(set(failure_kinds)) > 1):
        return _structured_ai_error(ERROR_CODE_RETRIES_EXHAUSTED, last_detail)
    return _structured_ai_error(last_kind or ERROR_CODE_UNAVAILABLE, last_detail)


def _redact_secret(text: str, secret: str) -> str:
    if secret and secret in text:
        return text.replace(secret, "***")
    return text


def _backoff_seconds(attempt: int, base: float = 0.5) -> float:
    return min(base * (2 ** (attempt - 1)), 8.0)


def _exception_status_code(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _is_rate_limited(exc: BaseException) -> bool:
    status = _exception_status_code(exc)
    if status == 429:
        return True
    msg = str(exc).lower()
    return "rate limit" in msg or "resource exhausted" in msg or "quota" in msg


def _models_for_call(model_name: str) -> tuple[str, ...]:
    if model_name in MODEL_CHAIN:
        idx = MODEL_CHAIN.index(model_name)
        return MODEL_CHAIN[idx:]
    return (model_name,) + MODEL_CHAIN


def _tries_on_one_model(max_attempts: int) -> int:
    return max(1, min(max_attempts, 3))


def _log_model_fallback(failed: str, next_model: str, reason: str) -> None:
    logger.info("Falling back from %s to %s (%s)", failed, next_model, reason)


def _mark_gemini_success(ai_fields: dict[str, Any]) -> dict[str, Any]:
    return {**ai_fields, "source": AI_SOURCE}


def _as_unit_interval(value: Any, field_name: str) -> tuple[bool, Any]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False, None
    if not 0.0 <= number <= 1.0:
        return False, None
    return True, number


def _as_stress_score(value: Any) -> tuple[bool, Any]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False, None
    if not STRESS_SCORE_MIN <= number <= STRESS_SCORE_MAX:
        return False, None
    return True, round(number, 2)


def _normalise_soft_label(value: Any) -> tuple[bool, Any]:
    if not isinstance(value, str):
        return False, None
    cleaned = value.strip()
    if cleaned in ALLOWED_SOFT_LABELS:
        return True, cleaned
    return False, None


def _normalise_stressors(value: Any) -> tuple[bool, Any]:
    if not isinstance(value, (list, tuple)):
        return False, None
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    if any(item not in ALLOWED_PRIMARY_STRESSORS for item in cleaned):
        return False, None
    return True, cleaned


def _normalise_tips(value: Any) -> tuple[bool, Any]:
    if not isinstance(value, (list, tuple)):
        return False, None
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    if not 1 <= len(cleaned) <= 3:
        return False, None
    if any(item not in ALLOWED_TIP_IDS for item in cleaned):
        return False, None
    return True, cleaned


def _normalise_scored_items(value: Any) -> tuple[bool, Any]:
    if not isinstance(value, Mapping):
        return False, None
    items = {}
    for key in RAW_ANSWER_KEYS:
        if key not in value:
            return False, None
        try:
            num = int(value[key])
        except (TypeError, ValueError):
            return False, None
        if not 1 <= num <= 5:
            return False, None
        items[key] = num
    return True, items


def validate_ai_response(payload: Any) -> tuple[bool, Any]:
    """Schema validation for a Gemini reply. Returns (ok, cleaned_or_error)."""
    if not isinstance(payload, Mapping):
        return False, "response is not a JSON object"
    cleaned: dict[str, Any] = {}
    missing = [k for k in _REQUIRED_FIELDS if k not in payload]
    if missing:
        return False, f"missing fields: {', '.join(missing)}"

    ok, scored = _normalise_scored_items(payload.get("scored_items"))
    if not ok:
        return False, "scored_items invalid"
    cleaned["scored_items"] = scored

    ok, score = _as_stress_score(payload.get("stress_score"))
    if not ok:
        return False, "stress_score invalid"
    cleaned["stress_score"] = score

    category = payload.get("risk_category")
    if category not in ALLOWED_RISK_CATEGORIES:
        return False, "risk_category invalid"
    cleaned["risk_category"] = category

    ok, stressors = _normalise_stressors(payload.get("primary_stressors"))
    if not ok:
        return False, "primary_stressors invalid"
    cleaned["primary_stressors"] = stressors

    ok, conf = _as_unit_interval(payload.get("confidence"), "confidence")
    if not ok:
        return False, "confidence invalid"
    cleaned["confidence"] = conf

    reasoning = payload.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        return False, "reasoning invalid"
    cleaned["reasoning"] = reasoning.strip()

    ok, label = _normalise_soft_label(payload.get("soft_label"))
    if not ok:
        return False, "soft_label invalid"
    cleaned["soft_label"] = label

    ok, tips = _normalise_tips(payload.get("tips"))
    if not ok:
        return False, "tips invalid"
    cleaned["tips"] = tips

    prom = payload.get("speak_prominence")
    if prom not in ALLOWED_SPEAK_PROMINENCE:
        return False, "speak_prominence invalid"
    cleaned["speak_prominence"] = prom

    return True, cleaned


def parse_response(raw: Any) -> dict[str, Any] | None:
    """Extract a JSON object from Gemini's text reply."""
    if isinstance(raw, Mapping):
        return dict(raw)
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def validate_response(data: Any) -> tuple[bool, Any]:
    """Alias used by some callers; same as validate_ai_response."""
    return validate_ai_response(data)


def _format_question(question: Mapping[str, Any]) -> str:
    key = question.get("key", "?")
    prompt = question.get("prompt", "")
    if "options" in question:
        opts = ", ".join(f"{i+1}={label}" for i, label in enumerate(question["options"]))
        return f"- {key}: {prompt} ({opts})"
    low = question.get("low", "")
    high = question.get("high", "")
    return f"- {key}: {prompt} ({low} → {high})"


def build_prompt(
    student_dict: Mapping[str, Any],
    questions: Sequence[Mapping[str, Any]] | None = None,
    instructions: str | None = None,
) -> str:
    """Build the Gemini prompt from the 11 answers + survey_version only."""
    if questions is None:
        questions = []  # caller should pass survey.QUESTIONS
    lines = [
        "You are a supportive student-wellbeing assistant for DoNotStress, a local check-in used by students.",
        "Calculate stress_score from the 11 answers with the formula below. You are not given a score, a tier, or a written reflection. Do not diagnose, and do not invent contacts.",
        "",
    ]
    if instructions:
        lines.append(instructions.strip())
        lines.append("")
    lines.append("Question wording and answer labels:")
    for q in questions:
        lines.append(_format_question(q))
    lines.append("")
    lines.append(
        "Speak to the student with warmth. Return ONLY a single JSON object (no markdown fences, no commentary) with exactly these keys:"
    )
    lines.append(
        '- "scored_items": object of the 11 converted values. Keys are pss_1, pss_2, pss_3, pss_4, '
        "sleep_hours_avg, sleep_quality, pas_workload, pas_catchup, fin_stress, mspss_friends, mspss_family. "
        "Each value is an integer from 1 to 5."
    )
    lines.append(
        f'- "stress_score": the mean of those 11 converted values, from {STRESS_SCORE_MIN:g} to {STRESS_SCORE_MAX:g}, rounded to 2 decimal places'
    )
    lines.append('- "risk_category": "Low", "Moderate", or "High", matching stress_score')
    lines.append(
        f'- "primary_stressors": list of snake_case strings chosen ONLY from: {", ".join(sorted(ALLOWED_PRIMARY_STRESSORS))}'
    )
    lines.append('- "confidence": number from 0.0 to 1.0')
    lines.append(
        '- "reasoning": 2 or 3 warm, plain sentences written to the student. No numbers, no jargon, no diagnosis, and no contacts'
    )
    lines.append(
        f'- "soft_label": exactly one of {", ".join(SOFT_LABELS)}, matching risk_category. Use a straight apostrophe in You\'re doing ok'
    )
    lines.append(
        f'- "tips": list of 1 to 3 tip IDs only, each one of: {", ".join(sorted(ALLOWED_TIP_IDS))}. Do not invent tip text'
    )
    lines.append(
        '- "speak_prominence": "low", "medium", or "high", matching risk_category. '
        "This is how strongly the UI highlights Talk to someone. SIT Counselling stays available and is shown more prominently when stress is higher"
    )
    lines.append("Do not add other keys. Never invent phone numbers, emails, or offices. SIT Counselling contacts are shown by the UI, not by you.")
    lines.append("")
    lines.append("Student check-in:")
    # Only the 11 answers and survey_version
    payload = {k: student_dict.get(k) for k in RAW_ANSWER_KEYS}
    payload["survey_version"] = student_dict.get("survey_version")
    lines.append(json.dumps(payload, ensure_ascii=False))
    return "\n".join(lines)


def _run_check(
    verify_fn: Callable[[dict[str, Any], Mapping[str, Any]], str | None],
    ai_fields: dict[str, Any],
    answers: Mapping[str, Any],
) -> str | None:
    try:
        return verify_fn(ai_fields, answers)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Score verifier raised: %s", type(exc).__name__)
        return "verifier error"


def _default_generate(prompt: str, api_key: str, model_name: str) -> str:
    """Real Gemini call. Tries the SDK, then a direct REST call for AQ. keys."""
    try:
        from google import genai
        from google.genai import types as genai_types
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=_DEFAULT_TEMPERATURE,
                response_mime_type="application/json",
            ),
        )
        text = getattr(response, "text", None) or ""
        if not text and hasattr(response, "candidates"):
            for cand in response.candidates or []:
                for part in getattr(cand.content, "parts", []) or []:
                    if getattr(part, "text", None):
                        text = part.text
                        break
        if text:
            return text
    except Exception as exc:
        logger.warning("SDK call failed (%s): %s", model_name, _redact_secret(str(exc), api_key)[:180])

    # REST fallback — works with both AIza and AQ. auth keys.
    import urllib.request
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent?key={api_key}"
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": _DEFAULT_TEMPERATURE,
            "responseMimeType": "application/json",
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        return parts[0].get("text", "") if parts else ""
    except Exception as exc:
        detail = _redact_secret(str(exc), api_key)[:180]
        logger.warning("REST call failed (%s): %s", model_name, detail)
        raise RuntimeError(detail) from exc


def call_gemini(
    prompt: str,
    api_key: str | None = None,
    model_name: str = _DEFAULT_MODEL,
    max_attempts: int = 3,
    retry_delay_sec: float = 0.5,
    generate_fn: Callable[[str, str, str], str] | None = None,
    answers: Mapping[str, Any] | None = None,
    verify_fn: Callable[[dict[str, Any], Mapping[str, Any]], str | None] | None = None,
) -> tuple[bool, dict[str, Any] | None, dict[str, str] | None]:
    """Call Gemini with retries and model fallback. Returns (ok, fields, error)."""
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    # Allow a test double to run without a real key
    if not key and generate_fn is None:
        return False, None, _structured_ai_error(ERROR_CODE_MISSING_API_KEY, "GEMINI_API_KEY is not set")
    if not key:
        key = "test-key"

    generate = generate_fn or _default_generate
    models = _models_for_call(model_name)
    tries_per = _tries_on_one_model(max_attempts)
    last_kind = ERROR_CODE_UNAVAILABLE
    last_detail = ""
    failure_kinds: list[str] = []
    total_calls = 0

    for model in models:
        for attempt in range(1, tries_per + 1):
            if total_calls >= MAX_TOTAL_CALLS:
                break
            total_calls += 1
            try:
                raw = generate(prompt, key, model)
                parsed = parse_response(raw)
                if parsed is None:
                    last_kind = ERROR_CODE_INVALID_RESPONSE
                    last_detail = "could not parse JSON"
                    failure_kinds.append(last_kind)
                    time.sleep(_backoff_seconds(attempt, retry_delay_sec))
                    continue
                ok, cleaned = validate_ai_response(parsed)
                if not ok:
                    last_kind = ERROR_CODE_INVALID_RESPONSE
                    last_detail = str(cleaned)
                    failure_kinds.append(last_kind)
                    time.sleep(_backoff_seconds(attempt, retry_delay_sec))
                    continue
                if verify_fn is not None and answers is not None:
                    problem = _run_check(verify_fn, cleaned, answers)
                    if problem:
                        last_kind = ERROR_CODE_INVALID_RESPONSE
                        last_detail = problem
                        failure_kinds.append(last_kind)
                        time.sleep(_backoff_seconds(attempt, retry_delay_sec))
                        continue
                return True, _mark_gemini_success(cleaned), None
            except Exception as exc:  # noqa: BLE001
                last_was_api = True
                detail = _redact_secret(str(exc), key)
                if _is_rate_limited(exc):
                    last_kind = ERROR_CODE_RATE_LIMITED
                elif "timeout" in detail.lower() or "timed out" in detail.lower():
                    last_kind = ERROR_CODE_TIMEOUT
                elif "404" in detail or "NOT_FOUND" in detail or "no longer available" in detail.lower():
                    last_kind = ERROR_CODE_UNAVAILABLE
                    last_detail = detail
                    failure_kinds.append(last_kind)
                    logger.warning("Gemini model gone (%s), skipping: %s", model, detail[:100])
                    break
                elif "503" in detail or "UNAVAILABLE" in detail or "high demand" in detail.lower():
                    last_kind = ERROR_CODE_UNAVAILABLE
                    last_detail = detail
                    failure_kinds.append(last_kind)
                    logger.warning("Gemini busy (%s), trying next: %s", model, detail[:100])
                    break  # high demand is temporary; try another model now
                else:
                    last_kind = ERROR_CODE_UNAVAILABLE
                last_detail = detail
                failure_kinds.append(last_kind)
                logger.warning("Gemini call failed (%s): %s — %s", model, last_kind, last_detail[:120])
                if model != models[-1] and attempt == tries_per:
                    _log_model_fallback(model, models[models.index(model) + 1], last_kind)
                time.sleep(_backoff_seconds(attempt, retry_delay_sec))

    return False, None, _final_ai_error(last_kind, last_detail, total_calls, True, failure_kinds)


def call_api(prompt: str, generate_fn: Callable[[str, str, str], str] | None = None,
             answers: Mapping[str, Any] | None = None,
             verify_fn: Callable[[dict[str, Any], Mapping[str, Any]], str | None] | None = None) -> tuple[bool, Any, Any]:
    """Thin wrapper around call_gemini used by some tests and main.py."""
    return call_gemini(prompt, generate_fn=generate_fn, answers=answers, verify_fn=verify_fn)


def analyse_student(
    student_dict: Mapping[str, Any],
    generate_fn: Callable[[str, str, str], str] | None = None,
    max_attempts: int = 3,
    retry_delay_sec: float = 0.5,
    instructions: str | None = None,
    verify_fn: Callable[[dict[str, Any], Mapping[str, Any]], str | None] | None = None,
    questions: Sequence[Mapping[str, Any]] | None = None,
    api_key: str | None = None,
    model_name: str = _DEFAULT_MODEL,
) -> tuple[bool, dict[str, Any] | None, dict[str, str] | None]:
    """Functional entry point used by main.py.

    Returns (ok, enriched_record_or_None, error_dict_or_None).
    """
    if not isinstance(student_dict, Mapping):
        return False, None, _structured_ai_error(ERROR_CODE_INVALID_RESPONSE, "student_dict must be a dict")

    # Never send student_id or reflection
    prompt = build_prompt(student_dict, questions=questions, instructions=instructions)
    ok, fields, error = call_gemini(
        prompt,
        api_key=api_key,
        model_name=model_name,
        max_attempts=max_attempts,
        retry_delay_sec=retry_delay_sec,
        generate_fn=generate_fn,
        answers=student_dict,
        verify_fn=verify_fn,
    )
    if not ok or fields is None:
        return False, None, error
    # Merge student answers + validated AI fields (student_id stays, reflection does not)
    enriched = {**dict(student_dict), **fields}
    # Ensure reflection is stripped
    enriched.pop("feelings_text", None)
    enriched.pop("reflection", None)
    return True, enriched, None


# ---------------------------------------------------------------------------
# OOP class implementing the interface
# ---------------------------------------------------------------------------

class GeminiAIManager(AIManagerInterface):
    """Real AI Manager that talks to Gemini.

    Implements AIManagerInterface.analyse(). Uses the same prompt, validation
    and verifier logic as the functional layer so behaviour stays consistent.
    """

    def __init__(
        self,
        verifier: ScoreVerifier | None = None,
        generate_fn: Callable[[str, str, str], str] | None = None,
        max_attempts: int = 3,
        retry_delay_sec: float = 0.5,
        questions: Sequence[Mapping[str, Any]] | None = None,
        api_key: str | None = None,
        model_name: str = _DEFAULT_MODEL,
    ) -> None:
        self._verifier = verifier
        self._generate_fn = generate_fn
        self._max_attempts = max_attempts
        self._retry_delay_sec = retry_delay_sec
        self._questions = questions
        self._api_key = api_key
        self._model_name = model_name

    def analyse(self, student: Mapping[str, Any]) -> dict[str, Any]:
        """Analyse one validated check-in. Raises AIProcessingError on failure."""
        instructions = self._verifier.instructions() if self._verifier else None
        verify = self._verifier.verify if self._verifier else None
        ok, enriched, error = analyse_student(
            student,
            generate_fn=self._generate_fn,
            max_attempts=self._max_attempts,
            retry_delay_sec=self._retry_delay_sec,
            instructions=instructions,
            verify_fn=verify,
            questions=self._questions,
            api_key=self._api_key,
            model_name=self._model_name,
        )
        if not ok or enriched is None:
            code = error.get("error_code", ERROR_CODE_UNAVAILABLE) if error else ERROR_CODE_UNAVAILABLE
            detail = error.get("detail", "") if error else ""
            raise AIProcessingError(code, detail)
        return enriched


class MockAIManager(AIManagerInterface):
    """TEST DOUBLE: answers every check-in with one fixed Gemini reply.

    For tests only. Never wire this into the running app.
    """

    def __init__(self, reply: Mapping[str, Any], verifier: ScoreVerifier | None = None) -> None:
        self._reply = dict(reply)
        self._verifier = verifier
        self._calls = 0

    @property
    def calls(self) -> int:
        return self._calls

    def analyse(self, student: Mapping[str, Any]) -> dict[str, Any]:
        self._calls += 1
        reply = dict(self._reply)
        if self._verifier is not None:
            problem = self._verifier.verify(reply, student)
            if problem:
                raise AIProcessingError("invalid_response", problem)
        return {**dict(student), **reply, "source": AI_SOURCE}


__all__ = [
    "GeminiAIManager",
    "MockAIManager",
    "AIManagerInterface",
    "AIProcessingError",
    "ScoreVerifier",
    "analyse_student",
    "build_prompt",
    "call_api",
    "call_gemini",
    "parse_response",
    "validate_response",
    "validate_ai_response",
    "AI_SOURCE",
]
