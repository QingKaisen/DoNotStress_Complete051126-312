"""DoNotStress — Data Layer (data_manager).

Sole owner of flat-file persistence for evaluated student check-in records.

Provides:
* JsonRecordRepository — OOP implementation of RecordRepository.
* Functional wrappers (save_record, load_all_records, ...) used by main.py.

Reflection text is never stored. Missing or corrupt files are tolerated.
"""

from __future__ import annotations

import json
import os
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------

class DataStoreError(Exception):
    """The record store could not be written (or could not be read at all)."""


class RecordRepository(ABC):
    @abstractmethod
    def save(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """Store one record and return the stored copy."""

    @abstractmethod
    def load(self) -> list[dict[str, Any]]:
        """Every stored record, oldest first."""

    def query(self, predicate: Callable[[dict[str, Any]], bool]) -> list[dict[str, Any]]:
        return [record for record in self.load() if predicate(record)]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_DATA_DIR = "data"
DEFAULT_FILENAME = "student_records.json"

TIER_TO_CATEGORY = {
    "You're doing ok": "Low",
    "Worth a check-in": "Moderate",
    "Please reach out": "High",
}

_AI_SUCCESS_SOURCES = frozenset({"ai_manager", "ai", "gemini", "gemini+logic", "ai_logic"})
_FORBIDDEN_SOURCES = frozenset({"logic_fallback", "fallback", "logic", "logic_only"})

_REQUIRED_AI_FIELDS = (
    "risk_score", "risk_category", "primary_stressors",
    "recommended_support", "confidence", "reasoning",
)

PRIVATE_FIELDS = ("feelings_text", "reflection")


def get_default_data_path() -> Path:
    return Path(DEFAULT_DATA_DIR) / DEFAULT_FILENAME


def _resolve_path(data_path: str | None) -> Path:
    if data_path:
        return Path(data_path)
    return get_default_data_path()


def _is_opted_in(opt_in: Any) -> bool:
    return opt_in is True


def _is_valid_probability(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return 0.0 <= number <= 1.0


def _validate_ai_fields(record: Mapping[str, Any]) -> str | None:
    """Return an error message if the record is missing required AI fields."""
    source = str(record.get("source", "")).lower()
    if source in _FORBIDDEN_SOURCES:
        return "logic-only fallback is not allowed"
    if record.get("ai_ok") is not True and source not in _AI_SUCCESS_SOURCES:
        return "record was not successfully processed by AI"
    for key in _REQUIRED_AI_FIELDS:
        if key not in record:
            return f"missing AI field: {key}"
    if not _is_valid_probability(record.get("confidence")):
        return "confidence must be between 0 and 1"
    if not _is_valid_probability(record.get("risk_score")):
        return "risk_score must be between 0 and 1"
    category = record.get("risk_category")
    if category not in {"Low", "Moderate", "High"}:
        return "risk_category invalid"
    stressors = record.get("primary_stressors")
    if not isinstance(stressors, (list, tuple)) or not all(isinstance(s, str) for s in stressors):
        return "primary_stressors must be a list of strings"
    if not isinstance(record.get("reasoning"), str):
        return "reasoning must be a string"
    if not isinstance(record.get("recommended_support"), str):
        return "recommended_support must be a string"
    return None


def _ai_success_error(record: Mapping[str, Any]) -> str | None:
    return _validate_ai_fields(record)


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _ensure_record_id(stored: dict[str, Any]) -> str:
    rid = stored.get("record_id")
    if isinstance(rid, str) and rid.strip():
        return rid.strip()
    new_id = uuid.uuid4().hex
    stored["record_id"] = new_id
    return new_id


def _strip_private(record: Mapping[str, Any]) -> dict[str, Any]:
    cleaned = dict(record)
    for key in PRIVATE_FIELDS:
        cleaned.pop(key, None)
    return cleaned


def _read_records_file(path: Path) -> tuple[bool, list[dict[str, Any]], str | None]:
    if not path.exists():
        return True, [], None
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return True, [], None
        data = json.loads(text)
        if isinstance(data, list):
            return True, [item for item in data if isinstance(item, dict)], None
        return False, [], "Corrupted records file"
    except (OSError, json.JSONDecodeError):
        return False, [], "Corrupted records file"


def _write_records_file(path: Path, records: list[dict[str, Any]]) -> tuple[bool, str | None]:
    try:
        _ensure_parent_dir(path)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return True, None
    except OSError as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Functional API used by main.py
# ---------------------------------------------------------------------------

def load_all_records(data_path: str | None = None) -> dict[str, Any]:
    path = _resolve_path(data_path)
    ok, records, error = _read_records_file(path)
    return {
        "ok": ok,
        "records": records,
        "error": error,
        "path": str(path),
    }


def save_record(
    record: Mapping[str, Any],
    data_path: str | None = None,
    opt_in: Any = None,
) -> dict[str, Any]:
    if not _is_opted_in(opt_in):
        return {"ok": False, "error": "Save refused: student opt-in required (pass opt_in=True)."}
    if not isinstance(record, Mapping):
        return {"ok": False, "error": "record must be a dict"}
    ai_error = _ai_success_error(record)
    if ai_error:
        return {"ok": False, "error": ai_error}
    path = _resolve_path(data_path)
    ok, records, load_error = _read_records_file(path)
    if not ok:
        return {"ok": False, "error": load_error or "Corrupted"}
    stored = _strip_private(record)
    _ensure_record_id(stored)
    stored.setdefault("saved_at", datetime.now(timezone.utc).isoformat())
    stored["save_opt_in"] = True
    records.append(stored)
    write_ok, write_error = _write_records_file(path, records)
    if not write_ok:
        return {"ok": False, "error": write_error or "write failed"}
    return {"ok": True, "record": stored}


def save(record: Mapping[str, Any], data_path: str | None = None, opt_in: Any = None) -> dict[str, Any]:
    return save_record(record, data_path=data_path, opt_in=opt_in)


def load(data_path: str | None = None) -> list[dict[str, Any]]:
    result = load_all_records(data_path)
    return result.get("records", []) if result.get("ok") else []


def query(filter_fn: Callable[[dict[str, Any]], Any], data_path: str | None = None) -> list[dict[str, Any]]:
    return [record for record in load(data_path) if filter_fn(record)]


def save_pending_record(
    record: Mapping[str, Any],
    data_path: str | None = None,
    opt_in: Any = None,
) -> dict[str, Any]:
    if not _is_opted_in(opt_in):
        return {"ok": False, "error": "Save refused: student opt-in required (pass opt_in=True)."}
    if not isinstance(record, Mapping):
        return {"ok": False, "error": "record must be a dict"}
    path = _resolve_path(data_path)
    ok, records, load_error = _read_records_file(path)
    if not ok:
        return {"ok": False, "error": load_error or "Corrupted"}
    stored = _strip_private(record)
    _ensure_record_id(stored)
    stored.setdefault("saved_at", datetime.now(timezone.utc).isoformat())
    stored["status"] = "pending"
    stored["ai_ok"] = False
    stored["save_opt_in"] = True
    records.append(stored)
    write_ok, write_error = _write_records_file(path, records)
    if not write_ok:
        return {"ok": False, "error": write_error or "write failed"}
    return {"ok": True, "record": stored}


def replace_pending_record(
    record_id: str,
    new_record: Mapping[str, Any],
    data_path: str | None = None,
    opt_in: Any = None,
) -> dict[str, Any]:
    if not isinstance(record_id, str) or not record_id.strip():
        return {"ok": False, "error": "record_id is required"}
    if not _is_opted_in(opt_in):
        return {"ok": False, "error": "Save refused: student opt-in required (pass opt_in=True)."}
    if not isinstance(new_record, Mapping):
        return {"ok": False, "error": "record must be a dict"}
    ai_error = _ai_success_error(new_record)
    if ai_error:
        return {"ok": False, "error": ai_error}
    path = _resolve_path(data_path)
    ok, records, load_error = _read_records_file(path)
    if not ok:
        return {"ok": False, "error": load_error or "Corrupted"}
    stored = _strip_private(new_record)
    stored["record_id"] = record_id.strip()
    stored.setdefault("saved_at", datetime.now(timezone.utc).isoformat())
    stored.pop("status", None)
    stored["ai_ok"] = True
    stored["save_opt_in"] = True
    replaced = False
    for index, existing in enumerate(records):
        if existing.get("record_id") == stored["record_id"]:
            records[index] = stored
            replaced = True
            break
    if not replaced:
        records.append(stored)
    write_ok, write_error = _write_records_file(path, records)
    if not write_ok:
        return {"ok": False, "error": write_error or "write failed"}
    return {"ok": True, "record": stored}


def filter_records(records: list[dict[str, Any]], **filters: Any) -> list[dict[str, Any]]:
    student_id = str(filters.get("student_id", "") or "").strip()
    risk_category = str(filters.get("risk_category", "") or "").strip()
    tier = str(filters.get("tier", "") or "").strip()
    cohort_year = str(filters.get("cohort_year", "") or "").strip()
    out = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if student_id and student_id not in str(record.get("student_id", "")):
            continue
        if risk_category and record.get("risk_category") != risk_category:
            continue
        if tier:
            category = TIER_TO_CATEGORY.get(tier)
            label = record.get("soft_label") or record.get("risk_category")
            if label != tier and record.get("risk_category") != category:
                continue
        if cohort_year:
            sid = str(record.get("student_id", ""))
            prefix = sid[:2] if len(sid) >= 2 else ""
            if prefix != cohort_year and not (len(cohort_year) == 4 and sid.startswith(cohort_year[2:])):
                continue
        out.append(record)
    return out


# ---------------------------------------------------------------------------
# OOP implementation
# ---------------------------------------------------------------------------

class JsonRecordRepository(RecordRepository):
    """File-backed RecordRepository using a JSON list.

    Follows the same rules as the functional layer: adds record_id and
    saved_at, drops reflection text, tolerates a missing file.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else get_default_data_path()

    @property
    def path(self) -> Path:
        return self._path

    def save(self, record: Mapping[str, Any]) -> dict[str, Any]:
        result = save_record(record, data_path=str(self._path), opt_in=True)
        if not result.get("ok"):
            raise DataStoreError(result.get("error", "save failed"))
        return result["record"]

    def load(self) -> list[dict[str, Any]]:
        ok, records, _ = _read_records_file(self._path)
        return records if ok else []

    def save_pending(self, record: Mapping[str, Any]) -> dict[str, Any]:
        result = save_pending_record(record, data_path=str(self._path), opt_in=True)
        if not result.get("ok"):
            raise DataStoreError(result.get("error", "save pending failed"))
        return result["record"]

    def replace_pending(self, record_id: str, new_record: Mapping[str, Any]) -> dict[str, Any]:
        result = replace_pending_record(record_id, new_record, data_path=str(self._path), opt_in=True)
        if not result.get("ok"):
            raise DataStoreError(result.get("error", "replace failed"))
        return result["record"]

    def load_all(self) -> dict[str, Any]:
        """Structured load used by the admin endpoint."""
        return load_all_records(str(self._path))

    def filter(self, records: list[dict[str, Any]], **filters: Any) -> list[dict[str, Any]]:
        return filter_records(records, **filters)


class InMemoryRecordRepository(RecordRepository):
    """TEST DOUBLE: keeps records in a list instead of a file."""

    PRIVATE_FIELDS = PRIVATE_FIELDS

    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []

    def save(self, record: Mapping[str, Any]) -> dict[str, Any]:
        stored = _strip_private(record)
        stored.setdefault("record_id", f"mem-{len(self._records) + 1}")
        stored.setdefault("saved_at", datetime.now(timezone.utc).isoformat())
        self._records.append(stored)
        return dict(stored)

    def load(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._records]


__all__ = [
    "DataStoreError",
    "RecordRepository",
    "JsonRecordRepository",
    "InMemoryRecordRepository",
    "TIER_TO_CATEGORY",
    "load_all_records",
    "save_record",
    "save",
    "load",
    "query",
    "save_pending_record",
    "replace_pending_record",
    "filter_records",
]
