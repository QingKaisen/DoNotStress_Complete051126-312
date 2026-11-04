"""Data contracts and value objects for the Logic Manager.

How a check-in moves through Logic::

    ai_manager --dict--> EnrichedRecord.from_dict()      INPUT contract
                                 |
                          LogicManager.evaluate()
                                 |
                          EvaluationResult
                            |-- .to_record()  --> data_manager  (storage)
                            '-- .to_display() --> io_manager    (student page)

Every class here is immutable (frozen dataclasses and an Enum). Once a value
has been checked it cannot be changed by mistake later, so the rules and the
result can trust it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, ClassVar

from .errors import RecordValidationError
from .field_reader import FieldReader

# Names shared by the rules and the output contract. Changing one changes
# the stored records, so they live here, next to the contracts.
RULE_SAFETY_OVERRIDE = "safety_override"
RULE_SUPPORT_PRIORITY = "support_priority"
FLAG_SLEEP = "sleep"
FLAG_WORKLOAD = "workload"
FLAG_FINANCES = "finances"
FLAG_SUPPORT = "support"


class RiskTier(Enum):
    """The three outcome tiers and the wording that goes with each one.

    These bands are team guidance, not clinical cut-offs or a diagnosis.
    """

    #         category    soft label           prominence  severity
    LOW = ("Low", "You're doing ok", "low", 1)
    MODERATE = ("Moderate", "Worth a check-in", "medium", 2)
    HIGH = ("High", "Please reach out", "high", 3)

    def __init__(self, category: str, soft_label: str, speak_prominence: str, severity: int) -> None:
        self._category = category
        self._soft_label = soft_label
        self._speak_prominence = speak_prominence
        self._severity = severity

    @property
    def category(self) -> str:
        """The risk_category value: "Low", "Moderate" or "High"."""
        return self._category

    @property
    def soft_label(self) -> str:
        """The student-facing tier name, e.g. "Worth a check-in"."""
        return self._soft_label

    @property
    def speak_prominence(self) -> str:
        """How strongly the UI highlights "Talk to someone": low, medium or high."""
        return self._speak_prominence

    @property
    def severity(self) -> int:
        """1 (Low) to 3 (High). Used to pick the more serious of two tiers."""
        return self._severity

    @property
    def recommended_support(self) -> str:
        """Short internal note stored with each record (data_manager requires it)."""
        return f"Internal: {self._category.lower()} stress. The UI shows tips, not this field."

    @classmethod
    def from_category(cls, category: object) -> RiskTier:
        """The tier whose risk_category equals ``category``. Raises ValueError."""
        for tier in cls:
            if tier.category == category:
                return tier
        raise ValueError(f"Unknown risk_category: {category!r}")

    @classmethod
    def most_severe(cls, tiers: Iterable[RiskTier]) -> RiskTier:
        """The most serious tier in ``tiers``. Rules can raise a tier, never lower it."""
        return max(tiers, key=lambda tier: tier.severity)


@dataclass(frozen=True)
class StudentAnswers:
    """The 11 scored answers exactly as the student gave them (not converted).

    Ten answers are whole numbers from 1 to 5. ``sleep_hours_avg`` is hours
    from 0 to 14. The student ID and the reflection are not part of this.
    """

    pss_1: int
    pss_2: int
    pss_3: int
    pss_4: int
    sleep_hours_avg: float
    sleep_quality: int
    pas_workload: int
    pas_catchup: int
    fin_stress: int
    mspss_friends: int
    mspss_family: int

    KEYS: ClassVar[tuple[str, ...]] = (
        "pss_1",
        "pss_2",
        "pss_3",
        "pss_4",
        "sleep_hours_avg",
        "sleep_quality",
        "pas_workload",
        "pas_catchup",
        "fin_stress",
        "mspss_friends",
        "mspss_family",
    )
    SLEEP_KEY: ClassVar[str] = "sleep_hours_avg"
    LIKERT_MIN: ClassVar[int] = 1
    LIKERT_MAX: ClassVar[int] = 5
    SLEEP_HOURS_MIN: ClassVar[int] = 0
    SLEEP_HOURS_MAX: ClassVar[int] = 14

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> StudentAnswers:
        """Build from any dict holding the 11 answers. Raises RecordValidationError."""
        if not isinstance(data, Mapping):
            raise RecordValidationError(invalid=("answers",))
        reader = FieldReader(data)
        values = cls._read(reader)
        reader.raise_if_problems()
        return cls(**values)

    @classmethod
    def _read(cls, reader: FieldReader) -> dict[str, Any]:
        """Read the 11 answers through ``reader`` (None where a value is unusable)."""
        values: dict[str, Any] = {}
        for key in cls.KEYS:
            if key == cls.SLEEP_KEY:
                values[key] = reader.number(key, cls.SLEEP_HOURS_MIN, cls.SLEEP_HOURS_MAX)
            else:
                number = reader.number(key, cls.LIKERT_MIN, cls.LIKERT_MAX, whole=True)
                values[key] = None if number is None else int(number)
        return values

    def value(self, key: str) -> int | float:
        """One answer by its key, for example ``answers.value("pss_1")``."""
        if key not in self.KEYS:
            raise KeyError(key)
        return getattr(self, key)

    def to_dict(self) -> dict[str, int | float]:
        """The 11 answers as a plain dict, in survey order."""
        return {key: getattr(self, key) for key in self.KEYS}


@dataclass(frozen=True)
class AIAssessment:
    """Gemini's validated analysis of one check-in.

    ai_manager has already checked the reply's schema and arithmetic. This
    class keeps what Logic needs with tidy types, and it refuses values that
    disagree with each other (for example a High tier with the "You're doing
    ok" label). The label and prominence are read from ``tier``, so they can
    never drift apart afterwards.
    """

    stress_score: float
    tier: RiskTier
    primary_stressors: tuple[str, ...]
    tips: tuple[str, ...]
    reasoning: str
    confidence: float
    scored_items: Mapping[str, int] | None = None

    REQUIRED_KEYS: ClassVar[tuple[str, ...]] = (
        "stress_score",
        "risk_category",
        "soft_label",
        "speak_prominence",
        "primary_stressors",
        "tips",
        "reasoning",
        "confidence",
    )
    SCORE_MIN: ClassVar[float] = 1.0
    SCORE_MAX: ClassVar[float] = 5.0

    @property
    def risk_category(self) -> str:
        return self.tier.category

    @property
    def soft_label(self) -> str:
        return self.tier.soft_label

    @property
    def speak_prominence(self) -> str:
        return self.tier.speak_prominence

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> AIAssessment:
        """Build from Gemini's validated fields. Raises RecordValidationError."""
        if not isinstance(data, Mapping):
            raise RecordValidationError(invalid=("ai_fields",))
        reader = FieldReader(data)
        values = cls._read(reader)
        reader.raise_if_problems()
        return cls(**values)

    @classmethod
    def _read(cls, reader: FieldReader) -> dict[str, Any]:
        """Read Gemini's fields through ``reader`` (None where a value is unusable)."""
        scored_items = reader.optional_mapping("scored_items")
        return {
            "stress_score": reader.number("stress_score", cls.SCORE_MIN, cls.SCORE_MAX),
            "tier": cls._read_tier(reader),
            "primary_stressors": reader.text_list("primary_stressors"),
            "tips": reader.text_list("tips"),
            "reasoning": reader.text("reasoning"),
            "confidence": reader.number("confidence", 0.0, 1.0),
            "scored_items": None if scored_items is None else MappingProxyType(scored_items),
        }

    @staticmethod
    def _read_tier(reader: FieldReader) -> RiskTier | None:
        """risk_category as a RiskTier; soft_label and speak_prominence must agree with it."""
        category = reader.text("risk_category")
        soft_label = reader.text("soft_label")
        prominence = reader.text("speak_prominence")
        if category is None:
            return None
        try:
            tier = RiskTier.from_category(category)
        except ValueError:
            reader.mark_invalid("risk_category")
            return None
        if soft_label is not None and soft_label != tier.soft_label:
            reader.mark_invalid("soft_label")
        if prominence is not None and prominence != tier.speak_prominence:
            reader.mark_invalid("speak_prominence")
        return tier


@dataclass(frozen=True)
class EnrichedRecord:
    """INPUT CONTRACT: one check-in after ai_manager and before Logic.

    ai_manager hands Logic a plain dict shaped like this (see
    tests/sample_ai_records.py for complete examples)::

        {
          "student_id": "2605581",           # str, optional; stored, never used by rules
          "survey_version": "evidence-v3",   # str, optional
          "safety_flag": False,              # bool from the reflection check (the text is never sent)
          "pss_1": 3, ..., "mspss_family": 4,  # the 11 answers: 10 whole numbers 1-5,
                                             #   sleep_hours_avg 0-14 hours
          "scored_items": {...},             # Gemini's 11 converted values (optional, kept for audit)
          "stress_score": 3.18,              # Gemini, 1.0-5.0
          "risk_category": "Moderate",       # Gemini: "Low" | "Moderate" | "High"
          "soft_label": "Worth a check-in",  # must match risk_category
          "speak_prominence": "medium",      # must match risk_category
          "primary_stressors": ["sleep_deprivation"],
          "tips": ["sleep_routine"],         # tip IDs; io_manager owns the wording
          "reasoning": "...",                # warm sentences written to the student
          "confidence": 0.8,                 # 0.0-1.0
          "source": "gemini"                 # ignored by Logic
        }

    Any other key, such as a reflection, is ignored and never stored.
    """

    answers: StudentAnswers
    assessment: AIAssessment
    student_id: str | None = None
    survey_version: str | None = None
    safety_flag: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EnrichedRecord:
        """Check and convert ai_manager's dict.

        Raises RecordValidationError listing every missing or unusable field
        at once, so one failed check-in shows all of its problems.
        """
        if not isinstance(data, Mapping):
            raise RecordValidationError(invalid=("record",))
        reader = FieldReader(data)
        answer_values = StudentAnswers._read(reader)
        ai_values = AIAssessment._read(reader)
        reader.raise_if_problems()
        student_id = data.get("student_id")
        survey_version = data.get("survey_version")
        return cls(
            answers=StudentAnswers(**answer_values),
            assessment=AIAssessment(**ai_values),
            student_id=None if student_id is None else str(student_id),
            survey_version=None if survey_version is None else str(survey_version),
            safety_flag=data.get("safety_flag") is True,
        )


@dataclass(frozen=True)
class ScoreBreakdown:
    """Logic's own scores for one set of answers (kept as an audit of Gemini)."""

    scored_items: Mapping[str, int]
    stress_score: float
    support_mean: float
    support_item_count: int
    tier: RiskTier


@dataclass(frozen=True)
class RuleContext:
    """Everything a business rule may look at. Rules read it and never change it."""

    record: EnrichedRecord
    scores: ScoreBreakdown

    @property
    def answers(self) -> StudentAnswers:
        return self.record.answers

    @property
    def assessment(self) -> AIAssessment:
        return self.record.assessment


@dataclass(frozen=True)
class RuleOutcome:
    """What one business rule decided for one record.

    * ``lead_tips`` go before Gemini's tips.
    * ``extra_tips`` are added after Gemini's tips while there is room.
    * ``minimum_tier`` raises the final tier to at least this tier.
    * ``note`` is stored in ``logic_clamp_notes`` to explain the change.
    * ``context_flag`` marks the outcome as one of the four context flags.

    A rule that did not fire is not allowed to change anything. That check
    is part of the shared rule contract (Liskov Substitution).
    """

    rule_name: str
    triggered: bool
    lead_tips: tuple[str, ...] = ()
    extra_tips: tuple[str, ...] = ()
    minimum_tier: RiskTier | None = None
    note: str | None = None
    context_flag: bool = False

    def __post_init__(self) -> None:
        if not self.rule_name:
            raise ValueError("A rule outcome needs the rule's name.")
        changes_something = (
            bool(self.lead_tips or self.extra_tips or self.note)
            or self.minimum_tier is not None
        )
        if not self.triggered and changes_something:
            raise ValueError(f"Rule {self.rule_name!r} did not fire, so it cannot change the result.")

    @classmethod
    def not_triggered(cls, rule_name: str, *, context_flag: bool = False) -> RuleOutcome:
        """The outcome of a rule that did not apply to this record."""
        return cls(rule_name=rule_name, triggered=False, context_flag=context_flag)


@dataclass(frozen=True)
class RuleReport:
    """Everything the business rules decided for one record, in rule order."""

    outcomes: tuple[RuleOutcome, ...] = ()

    @property
    def lead_tips(self) -> tuple[str, ...]:
        return tuple(tip for outcome in self.outcomes for tip in outcome.lead_tips)

    @property
    def extra_tips(self) -> tuple[str, ...]:
        return tuple(tip for outcome in self.outcomes for tip in outcome.extra_tips)

    @property
    def escalations(self) -> tuple[RiskTier, ...]:
        """Tiers that rules asked for (the final tier is at least each of these)."""
        return tuple(o.minimum_tier for o in self.outcomes if o.minimum_tier is not None)

    @property
    def notes(self) -> tuple[str, ...]:
        """Why Logic changed anything (empty when nothing changed)."""
        return tuple(o.note for o in self.outcomes if o.note)

    @property
    def context_flags(self) -> dict[str, bool]:
        """The context flags, e.g. {"sleep": True, "workload": False, ...}."""
        return {o.rule_name: o.triggered for o in self.outcomes if o.context_flag}

    @property
    def triggered_rules(self) -> tuple[str, ...]:
        return tuple(o.rule_name for o in self.outcomes if o.triggered)

    def fired(self, rule_name: str) -> bool:
        """True if the rule called ``rule_name`` applied to this record."""
        return rule_name in self.triggered_rules


@dataclass(frozen=True)
class FactorCard:
    """One card on the student result page (rest, study, money or support)."""

    title: str
    flagged: bool
    value: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "flagged": self.flagged, "value": self.value, "text": self.text}


@dataclass(frozen=True)
class EvaluationResult:
    """OUTPUT CONTRACT: Logic's final decision for one check-in.

    Use ``to_record()`` for data_manager and ``to_display()`` for io_manager.
    Gemini's stress score is kept as it is; Logic's own score is only an
    audit value (``logic_stress_score``).
    """

    record: EnrichedRecord
    scores: ScoreBreakdown
    tier: RiskTier
    tips: tuple[str, ...]
    risk_score: float
    report: RuleReport
    factor_cards: tuple[FactorCard, ...]
    logic_rule: str

    SOURCE: ClassVar[str] = "ai_logic"

    @property
    def stress_score(self) -> float:
        """Gemini's verified 1-5 stress score."""
        return self.record.assessment.stress_score

    @property
    def logic_stress_score(self) -> float:
        """Logic's own score for the same answers (audit only)."""
        return self.scores.stress_score

    @property
    def route(self) -> str:
        """The outcome path: "Low", "Moderate" or "High"."""
        return self.tier.category

    @property
    def soft_label(self) -> str:
        return self.tier.soft_label

    @property
    def speak_prominence(self) -> str:
        return self.tier.speak_prominence

    @property
    def recommended_support(self) -> str:
        return self.tier.recommended_support

    @property
    def notes(self) -> tuple[str, ...]:
        return self.report.notes

    @property
    def context_flags(self) -> dict[str, bool]:
        return self.report.context_flags

    @property
    def support_priority(self) -> bool:
        """True when the multi-condition rule (High tier + low social support) fired."""
        return self.report.fired(RULE_SUPPORT_PRIORITY)

    def to_record(self) -> dict[str, Any]:
        """OUTPUT CONTRACT for data_manager: one JSON-ready dict per check-in.

        Same keys and values as a Phase 1 evaluated record, so saved files
        and the admin table keep working:

        * identity: student_id (str|None), survey_version (str|None), safety_flag (bool)
        * the 11 raw answers (int, sleep_hours_avg float)
        * Gemini: scored_items (dict|None), stress_score (float 1-5),
          primary_stressors (list[str]), reasoning (str), confidence (float 0-1)
        * final outcome: risk_category, soft_label, speak_prominence (str),
          tips (list[str], at most 4)
        * Logic: ok=True, error=None, source="ai_logic", ai_ok=True,
          logic_rule (str), logic_stress_score (float), risk_score (float 0-1,
          not a probability), recommended_support (str),
          logic_clamp_notes (list[str]), support_priority (bool),
          context_flags (dict[str, bool]), support_mean (float),
          factor_insights (list of 4 dicts: title, flagged, value, text)

        The reflection text is never part of a record.
        """
        ai = self.record.assessment
        return {
            "student_id": self.record.student_id,
            "survey_version": self.record.survey_version,
            **self.record.answers.to_dict(),
            "safety_flag": self.record.safety_flag,
            "scored_items": None if ai.scored_items is None else dict(ai.scored_items),
            "stress_score": ai.stress_score,
            "risk_category": self.tier.category,
            "soft_label": self.soft_label,
            "speak_prominence": self.speak_prominence,
            "primary_stressors": list(ai.primary_stressors),
            "tips": list(self.tips),
            "reasoning": ai.reasoning,
            "confidence": ai.confidence,
            "ok": True,
            "error": None,
            "source": self.SOURCE,
            "ai_ok": True,
            "logic_rule": self.logic_rule,
            "logic_stress_score": self.logic_stress_score,
            "risk_score": self.risk_score,
            "recommended_support": self.recommended_support,
            "logic_clamp_notes": list(self.notes),
            "support_priority": self.support_priority,
            "context_flags": self.context_flags,
            "support_mean": self.scores.support_mean,
            "factor_insights": [card.to_dict() for card in self.factor_cards],
        }

    def to_display(self) -> dict[str, Any]:
        """OUTPUT CONTRACT for io_manager: what the student's result page needs.

        Tips are IDs; io_manager turns them into wording and adds the support
        contacts. Raw scores are left out on purpose: the stress score stays
        in the admin table, not on the student page.
        """
        ai = self.record.assessment
        return {
            "soft_label": self.soft_label,
            "speak_prominence": self.speak_prominence,
            "risk_category": self.tier.category,
            "tips": list(self.tips),
            "reasoning": ai.reasoning,
            "primary_stressors": list(ai.primary_stressors),
            "factor_insights": [card.to_dict() for card in self.factor_cards],
            "context_flags": self.context_flags,
            "safety_flag": self.record.safety_flag,
            "survey_version": self.record.survey_version,
            "answers": self.record.answers.to_dict(),
        }
