"""Hardcoded sample check-ins for the Logic Manager tests (no live API).

Each ``*_STUDENT`` dict is what io_manager hands to the AI Manager.
Each ``*_REPLY`` dict is a validated Gemini reply for those answers.
Each combined dict (LOW_STRESS, ...) is what the AI Manager hands to
LogicManager.evaluate(): the student's answers plus Gemini's fields.

Copy a sample with copy.deepcopy() before changing it in a test.
"""

# --- Low stress: no flags -----------------------------------------------------
LOW_STRESS_STUDENT = {
    "student_id": "2605581",
    "pss_1": 2, "pss_2": 4, "pss_3": 4, "pss_4": 2,
    "sleep_hours_avg": 8.0, "sleep_quality": 2,
    "pas_workload": 2, "pas_catchup": 2,
    "fin_stress": 2,
    "mspss_friends": 4, "mspss_family": 5,
    "safety_flag": False,
    "survey_version": "evidence-v3",
}
LOW_STRESS_REPLY = {
    "scored_items": {
        "pss_1": 2, "pss_2": 2, "pss_3": 2, "pss_4": 2,
        "sleep_hours_avg": 1, "sleep_quality": 2,
        "pas_workload": 2, "pas_catchup": 2,
        "fin_stress": 2,
        "mspss_friends": 2, "mspss_family": 1,
    },
    "stress_score": 1.82,          # 20 / 11
    "risk_category": "Low",
    "primary_stressors": [],
    "confidence": 0.9,
    "reasoning": "Your check-in looks steady. Keep the routines that are working for you.",
    "soft_label": "You're doing ok",
    "tips": ["short_breaks"],
    "speak_prominence": "low",
}
LOW_STRESS = {**LOW_STRESS_STUDENT, **LOW_STRESS_REPLY, "source": "gemini"}

# --- Moderate: short sleep and heavy workload raise two flags -----------------
MODERATE_STUDENT = {
    "student_id": "2512345",
    "pss_1": 3, "pss_2": 3, "pss_3": 3, "pss_4": 3,
    "sleep_hours_avg": 5.5, "sleep_quality": 3,
    "pas_workload": 4, "pas_catchup": 3,
    "fin_stress": 3,
    "mspss_friends": 3, "mspss_family": 3,
    "safety_flag": False,
    "survey_version": "evidence-v3",
}
MODERATE_REPLY = {
    "scored_items": {
        "pss_1": 3, "pss_2": 3, "pss_3": 3, "pss_4": 3,
        "sleep_hours_avg": 4, "sleep_quality": 3,
        "pas_workload": 4, "pas_catchup": 3,
        "fin_stress": 3,
        "mspss_friends": 3, "mspss_family": 3,
    },
    "stress_score": 3.18,          # 35 / 11
    "risk_category": "Moderate",
    "primary_stressors": ["sleep_deprivation", "academic_overload"],
    "confidence": 0.8,
    "reasoning": "Short nights and a heavy workload seem to be adding up. Small changes can help.",
    "soft_label": "Worth a check-in",
    "tips": ["short_breaks", "rest_a_little_more"],
    "speak_prominence": "medium",
}
MODERATE_SLEEP_WORKLOAD = {**MODERATE_STUDENT, **MODERATE_REPLY, "source": "gemini"}

# --- High + low social support: the multi-condition rule fires -----------------
HIGH_STUDENT = {
    "student_id": "2400001",
    "pss_1": 5, "pss_2": 1, "pss_3": 1, "pss_4": 5,
    "sleep_hours_avg": 4.5, "sleep_quality": 5,
    "pas_workload": 5, "pas_catchup": 5,
    "fin_stress": 4,
    "mspss_friends": 2, "mspss_family": 1,
    "safety_flag": False,
    "survey_version": "evidence-v3",
}
HIGH_REPLY = {
    "scored_items": {
        "pss_1": 5, "pss_2": 5, "pss_3": 5, "pss_4": 5,
        "sleep_hours_avg": 5, "sleep_quality": 5,
        "pas_workload": 5, "pas_catchup": 5,
        "fin_stress": 4,
        "mspss_friends": 4, "mspss_family": 5,
    },
    "stress_score": 4.82,          # 53 / 11
    "risk_category": "High",
    "primary_stressors": ["sleep_deprivation", "academic_overload", "low_social_support"],
    "confidence": 0.85,
    "reasoning": "A lot is weighing on you right now, and you do not have to carry it alone.",
    "soft_label": "Please reach out",
    "tips": ["sleep_routine", "workload_chunks"],
    "speak_prominence": "high",
}
HIGH_LOW_SUPPORT = {**HIGH_STUDENT, **HIGH_REPLY, "source": "gemini"}

# --- Edge cases ---------------------------------------------------------------
# Low answers, but the reflection safety check fired.
SAFETY_FLAGGED = {**LOW_STRESS, "safety_flag": True}

# Gemini's arithmetic is wrong: 2.10 is far from the real 1.82.
SCORE_MISMATCH = {**LOW_STRESS, "stress_score": 2.1}
