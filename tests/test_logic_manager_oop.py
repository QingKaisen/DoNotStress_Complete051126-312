"""Unit tests for the OOP Logic Manager.

Every test uses the hardcoded sample AI records in sample_ai_records.py, so
no live API, network or file is needed.

Run from the project root:  python -m unittest discover -s tests -v
"""

import copy
import json
import unittest
from dataclasses import fields

from logic_manager import (
    AIScoreVerifier,
    BaseEvaluator,
    ContextFlagRule,
    EnrichedRecord,
    FinanceFlagRule,
    LogicManager,
    LogicManagerError,
    RecordValidationError,
    RiskTier,
    RuleContext,
    RuleOutcome,
    SafetyOverrideRule,
    ScoreCalculator,
    ScoreMismatchError,
    ScoringPolicy,
    SleepFlagRule,
    StudentAnswers,
    SupportFlagRule,
    SupportPriorityRule,
    TipPlanner,
    WorkloadFlagRule,
)
from sample_ai_records import (
    HIGH_LOW_SUPPORT,
    LOW_STRESS,
    MODERATE_REPLY,
    MODERATE_SLEEP_WORKLOAD,
    MODERATE_STUDENT,
    SAFETY_FLAGGED,
    SCORE_MISMATCH,
)

ALL_SAMPLES = (LOW_STRESS, MODERATE_SLEEP_WORKLOAD, HIGH_LOW_SUPPORT, SAFETY_FLAGGED)


def changed(record, **changes):
    """A deep copy of ``record`` with some fields replaced."""
    data = copy.deepcopy(record)
    data.update(changes)
    return data


def context_for(record):
    """The RuleContext LogicManager would build for ``record``."""
    enriched = EnrichedRecord.from_dict(record)
    return RuleContext(record=enriched, scores=ScoreCalculator().breakdown(enriched.answers))


class ScoreCalculatorTests(unittest.TestCase):
    def setUp(self):
        self.calculator = ScoreCalculator()

    def test_positively_worded_items_are_reverse_scored(self):
        self.assertEqual(self.calculator.convert("pss_2", 4), 2)
        self.assertEqual(self.calculator.convert("mspss_family", 5), 1)
        self.assertEqual(self.calculator.convert("pss_1", 4), 4)

    def test_sleep_hours_bands(self):
        cases = {14: 1, 8: 1, 7.5: 2, 7: 2, 6.5: 3, 6: 3, 5.5: 4, 5: 4, 4.5: 5, 0: 5}
        for hours, expected in cases.items():
            with self.subTest(hours=hours):
                self.assertEqual(self.calculator.sleep_hours_stress(hours), expected)

    def test_stress_score_is_mean_of_converted_answers(self):
        answers = StudentAnswers.from_mapping(LOW_STRESS)
        self.assertEqual(self.calculator.scored_items(answers), LOW_STRESS["scored_items"])
        self.assertEqual(self.calculator.stress_score(answers), 1.82)
        self.assertEqual(self.calculator.support_mean(answers), 4.5)

    def test_tier_boundaries(self):
        cases = {
            1.0: RiskTier.LOW,
            2.49: RiskTier.LOW,
            2.5: RiskTier.MODERATE,
            3.5: RiskTier.MODERATE,
            3.51: RiskTier.HIGH,
            5.0: RiskTier.HIGH,
        }
        for score, tier in cases.items():
            with self.subTest(score=score):
                self.assertIs(self.calculator.tier_for(score), tier)

    def test_tolerance_accepts_exactly_one_hundredth(self):
        self.assertTrue(self.calculator.within_tolerance(4.63, 4.64))
        self.assertFalse(self.calculator.within_tolerance(4.62, 4.64))

    def test_risk_score_maps_the_scale_onto_zero_to_one(self):
        self.assertEqual(self.calculator.risk_score(1.0), 0.0)
        self.assertEqual(self.calculator.risk_score(3.0), 0.5)
        self.assertEqual(self.calculator.risk_score(5.0), 1.0)

    def test_custom_policy_changes_thresholds_without_code_changes(self):
        calculator = ScoreCalculator(ScoringPolicy(check_in_from=2.0, reach_out_above=3.0))
        self.assertIs(calculator.tier_for(2.2), RiskTier.MODERATE)
        self.assertIs(calculator.tier_for(3.2), RiskTier.HIGH)

    def test_policy_refuses_impossible_settings(self):
        with self.assertRaises(ValueError):
            ScoringPolicy(check_in_from=4.0, reach_out_above=3.0)
        with self.assertRaises(ValueError):
            ScoringPolicy(reversed_keys=("not_a_question",))
        with self.assertRaises(ValueError):
            ScoringPolicy(sleep_hour_bands=((5, 4), (8, 1)))


class BusinessRuleTests(unittest.TestCase):
    def test_safety_override_raises_the_tier_and_leads_with_support(self):
        outcome = SafetyOverrideRule().evaluate(context_for(SAFETY_FLAGGED))
        self.assertTrue(outcome.triggered)
        self.assertIs(outcome.minimum_tier, RiskTier.HIGH)
        self.assertEqual(outcome.lead_tips, ("talk_to_someone",))

    def test_safety_override_stays_silent_without_the_flag(self):
        outcome = SafetyOverrideRule().evaluate(context_for(LOW_STRESS))
        self.assertFalse(outcome.triggered)
        self.assertIsNone(outcome.minimum_tier)

    def test_multi_condition_rule_needs_both_ai_fields(self):
        rule = SupportPriorityRule()
        self.assertTrue(rule.evaluate(context_for(HIGH_LOW_SUPPORT)).triggered)

        high_without_stressor = changed(HIGH_LOW_SUPPORT, primary_stressors=["academic_overload"])
        self.assertFalse(rule.evaluate(context_for(high_without_stressor)).triggered)

        stressor_without_high = changed(
            MODERATE_SLEEP_WORKLOAD, primary_stressors=["low_social_support"]
        )
        self.assertFalse(rule.evaluate(context_for(stressor_without_high)).triggered)

    def test_context_flags_for_each_sample(self):
        flag_rules = (SleepFlagRule(), WorkloadFlagRule(), FinanceFlagRule(), SupportFlagRule())
        expected = {  # sample: (sleep, workload, finances, support)
            "low": (LOW_STRESS, (False, False, False, False)),
            "moderate": (MODERATE_SLEEP_WORKLOAD, (True, True, False, False)),
            "high": (HIGH_LOW_SUPPORT, (True, True, True, True)),
        }
        for label, (record, flags) in expected.items():
            context = context_for(record)
            with self.subTest(sample=label):
                raised = tuple(rule.evaluate(context).triggered for rule in flag_rules)
                self.assertEqual(raised, flags)
                self.assertEqual(
                    [rule.name for rule in flag_rules], ["sleep", "workload", "finances", "support"]
                )

    def test_poor_sleep_quality_alone_raises_the_sleep_flag(self):
        well_rested_but_restless = changed(LOW_STRESS, sleep_quality=4)
        outcome = SleepFlagRule().evaluate(context_for(well_rested_but_restless))
        self.assertTrue(outcome.triggered)
        self.assertEqual(outcome.extra_tips, ("sleep_routine",))

    def test_every_rule_keeps_the_shared_contract(self):
        """Liskov Substitution: any rule can stand in for any other."""
        for rule in LogicManager.default_rules():
            for record in ALL_SAMPLES:
                context = context_for(record)
                with self.subTest(rule=rule.name, student=record["student_id"]):
                    first = rule.evaluate(context)
                    self.assertIsInstance(first, RuleOutcome)
                    self.assertEqual(first.rule_name, rule.name)
                    self.assertEqual(first, rule.evaluate(context))  # same input, same outcome

    def test_abstract_classes_cannot_be_created(self):
        with self.assertRaises(TypeError):
            BaseEvaluator()
        with self.assertRaises(TypeError):
            ContextFlagRule("sleep_routine")

    def test_a_rule_that_did_not_fire_cannot_change_the_result(self):
        with self.assertRaises(ValueError):
            RuleOutcome(rule_name="sleep", triggered=False, extra_tips=("sleep_routine",))


class TipPlannerTests(unittest.TestCase):
    def test_lead_then_gemini_then_extra_while_there_is_room(self):
        tips = TipPlanner().plan(
            lead=["talk_to_someone"],
            ai_tips=["sleep_routine", "workload_chunks"],
            extra=["keep_social_contact", "money_worries"],
        )
        self.assertEqual(
            tips, ("talk_to_someone", "sleep_routine", "workload_chunks", "keep_social_contact")
        )

    def test_repeats_are_dropped(self):
        tips = TipPlanner().plan(["talk_to_someone"], ["talk_to_someone"], ["talk_to_someone"])
        self.assertEqual(tips, ("talk_to_someone",))

    def test_limit_must_be_positive(self):
        with self.assertRaises(ValueError):
            TipPlanner(max_tips=0)


class LogicManagerTests(unittest.TestCase):
    def setUp(self):
        self.logic = LogicManager()

    def test_low_stress_keeps_geminis_result(self):
        result = self.logic.evaluate(LOW_STRESS)
        self.assertIs(result.tier, RiskTier.LOW)
        self.assertEqual(result.tips, ("short_breaks",))
        self.assertEqual(result.notes, ())

    def test_flag_tips_follow_geminis_tips(self):
        result = self.logic.evaluate(MODERATE_SLEEP_WORKLOAD)
        self.assertIs(result.tier, RiskTier.MODERATE)
        self.assertEqual(
            result.tips, ("short_breaks", "rest_a_little_more", "sleep_routine", "workload_chunks")
        )

    def test_multi_condition_rule_puts_support_first(self):
        result = self.logic.evaluate(HIGH_LOW_SUPPORT)
        self.assertTrue(result.support_priority)
        self.assertEqual(
            result.tips, ("talk_to_someone", "sleep_routine", "workload_chunks", "keep_social_contact")
        )
        self.assertEqual(result.notes, ("support_priority: High tier with low social support",))

    def test_safety_flag_forces_reach_out_but_keeps_the_score(self):
        result = self.logic.evaluate(SAFETY_FLAGGED)
        self.assertIs(result.tier, RiskTier.HIGH)
        self.assertEqual(result.soft_label, "Please reach out")
        self.assertEqual(result.speak_prominence, "high")
        self.assertEqual(result.stress_score, 1.82)
        self.assertEqual(result.tips, ("talk_to_someone", "short_breaks"))

    def test_score_mismatch_is_rejected(self):
        with self.assertRaises(ScoreMismatchError) as caught:
            self.logic.evaluate(SCORE_MISMATCH)
        self.assertEqual(caught.exception.ai_score, 2.1)
        self.assertEqual(caught.exception.logic_score, 1.82)
        self.assertEqual(caught.exception.code, "score_mismatch")

    def test_a_score_exactly_one_hundredth_off_is_accepted(self):
        result = self.logic.evaluate(changed(LOW_STRESS, stress_score=1.83))
        self.assertEqual(result.stress_score, 1.83)
        self.assertEqual(result.logic_stress_score, 1.82)

    def test_missing_fields_are_all_listed(self):
        record = copy.deepcopy(LOW_STRESS)
        del record["tips"], record["pss_1"]
        with self.assertRaises(RecordValidationError) as caught:
            self.logic.evaluate(record)
        self.assertEqual(set(caught.exception.missing), {"tips", "pss_1"})
        self.assertEqual(caught.exception.code, "ai_fields_required")

    def test_unusable_values_are_all_listed(self):
        record = changed(
            LOW_STRESS, pss_2=2.5, pss_3=True, sleep_hours_avg=15, stress_score="abc", tips="short_breaks"
        )
        with self.assertRaises(RecordValidationError) as caught:
            self.logic.evaluate(record)
        self.assertEqual(
            set(caught.exception.invalid), {"pss_2", "pss_3", "sleep_hours_avg", "stress_score", "tips"}
        )

    def test_labels_must_agree_with_the_tier(self):
        record = changed(LOW_STRESS, soft_label="Please reach out", speak_prominence="high")
        with self.assertRaises(RecordValidationError) as caught:
            self.logic.evaluate(record)
        self.assertEqual(set(caught.exception.invalid), {"soft_label", "speak_prominence"})

    def test_input_that_is_not_a_dict_is_refused(self):
        for bad in (None, [], "record"):
            with self.subTest(record=bad), self.assertRaises(RecordValidationError):
                self.logic.evaluate(bad)

    def test_every_failure_is_a_logic_manager_error(self):
        for record in (SCORE_MISMATCH, {}):
            with self.subTest(record=record), self.assertRaises(LogicManagerError):
                self.logic.evaluate(record)

    def test_evaluation_is_pure(self):
        record = copy.deepcopy(HIGH_LOW_SUPPORT)
        first = self.logic.evaluate(record)
        self.assertEqual(record, HIGH_LOW_SUPPORT)  # input not changed
        self.assertEqual(first, self.logic.evaluate(record))  # same answer every time

    def test_score_and_route(self):
        self.assertEqual(self.logic.score(MODERATE_SLEEP_WORKLOAD), 3.18)
        self.assertEqual(self.logic.route(self.logic.evaluate(MODERATE_SLEEP_WORKLOAD)), "Moderate")

    def test_new_rule_can_be_added_without_changing_logic_manager(self):
        """Open/Closed: a new strategy class plugs in through the constructor."""

        class LowConfidenceRule(BaseEvaluator):
            @property
            def name(self):
                return "low_confidence"

            def evaluate(self, context):
                if context.assessment.confidence >= 0.5:
                    return RuleOutcome.not_triggered(self.name)
                return RuleOutcome(
                    rule_name=self.name,
                    triggered=True,
                    extra_tips=("talk_to_someone",),
                    minimum_tier=RiskTier.MODERATE,
                    note="low_confidence: Gemini was unsure",
                )

        logic = LogicManager(rules=(*LogicManager.default_rules(), LowConfidenceRule()))
        result = logic.evaluate(changed(LOW_STRESS, confidence=0.3))
        self.assertIs(result.tier, RiskTier.MODERATE)
        self.assertIn("talk_to_someone", result.tips)
        self.assertIn("low_confidence: Gemini was unsure", result.notes)

    def test_rules_must_be_evaluators_with_unique_names(self):
        with self.assertRaises(TypeError):
            LogicManager(rules=["not a rule"])
        with self.assertRaises(ValueError):
            LogicManager(rules=(SleepFlagRule(), SleepFlagRule()))


class OutputContractTests(unittest.TestCase):
    def setUp(self):
        self.result = LogicManager().evaluate(HIGH_LOW_SUPPORT)

    def test_record_meets_data_manager_rules(self):
        record = self.result.to_record()
        self.assertEqual(record["student_id"], "2400001")
        self.assertTrue(0.0 <= record["risk_score"] <= 1.0)
        self.assertTrue(0.0 <= record["confidence"] <= 1.0)
        self.assertIn(record["risk_category"], {"Low", "Moderate", "High"})
        self.assertTrue(all(isinstance(item, str) for item in record["primary_stressors"]))
        self.assertIsInstance(record["recommended_support"], str)
        self.assertIsInstance(record["reasoning"], str)
        self.assertEqual((record["source"], record["ai_ok"], record["logic_rule"]), ("ai_logic", True, "v3"))
        for key in StudentAnswers.KEYS:
            self.assertEqual(record[key], HIGH_LOW_SUPPORT[key])

    def test_record_is_json_ready(self):
        record = self.result.to_record()
        self.assertEqual(json.loads(json.dumps(record)), record)

    def test_reflection_text_never_leaves_logic(self):
        result = LogicManager().evaluate(changed(LOW_STRESS, feelings_text="private words"))
        self.assertNotIn("feelings_text", result.to_record())
        self.assertNotIn("private words", json.dumps(result.to_record()))
        self.assertNotIn("private words", json.dumps(result.to_display()))

    def test_student_view_leaves_out_raw_scores(self):
        view = self.result.to_display()
        for hidden in ("stress_score", "logic_stress_score", "risk_score", "student_id"):
            self.assertNotIn(hidden, view)
        self.assertEqual(view["soft_label"], "Please reach out")
        self.assertEqual(len(view["factor_insights"]), 4)

    def test_factor_cards(self):
        cards = self.result.to_record()["factor_insights"]
        self.assertEqual(
            [card["title"] for card in cards],
            ["Rest & recovery", "Study demands", "Money pressures", "Support & connection"],
        )
        self.assertEqual(cards[0]["value"], "4.5 hours · Very bad quality")
        self.assertEqual(cards[3]["value"], "1.5/5 agreement across 2 answers")
        self.assertTrue(all(card["flagged"] for card in cards))

    def test_answer_keys_match_the_dataclass_fields(self):
        self.assertEqual(StudentAnswers.KEYS, tuple(field.name for field in fields(StudentAnswers)))


class AIScoreVerifierTests(unittest.TestCase):
    def setUp(self):
        self.verifier = AIScoreVerifier(ScoreCalculator())

    def test_a_correct_reply_passes(self):
        self.assertIsNone(self.verifier.verify(MODERATE_REPLY, MODERATE_STUDENT))

    def test_wrong_replies_are_caught(self):
        items = dict(MODERATE_REPLY["scored_items"], pss_2=1)
        cases = {
            "tier": ({"risk_category": "High"}, "risk_category must be Moderate"),
            "label": ({"soft_label": "You're doing ok"}, "soft_label must match"),
            "prominence": ({"speak_prominence": "low"}, "speak_prominence must match"),
            "items": ({"scored_items": items}, "scored_items does not match"),
            "score": ({"stress_score": 3.4}, "expected 3.18"),
            "not a number": ({"stress_score": "high"}, "stress_score must be a number"),
        }
        for label, (change, message) in cases.items():
            with self.subTest(case=label):
                self.assertIn(message, self.verifier.verify({**MODERATE_REPLY, **change}, MODERATE_STUDENT))

    def test_unusable_answers_are_named(self):
        message = self.verifier.verify(MODERATE_REPLY, changed(MODERATE_STUDENT, pss_1=2.5))
        self.assertEqual(message, "Cannot convert pss_1 onto the 1-5 stress scale.")

    def test_instructions_describe_the_rules(self):
        text = self.verifier.instructions()
        self.assertIn("pss_2, pss_3, mspss_friends, mspss_family are positively worded", text)
        self.assertIn("8 or more hours -> 1", text)
        self.assertIn("2.5 to 3.5 inclusive", text)

    def test_one_policy_drives_prompt_check_and_evaluation(self):
        calculator = ScoreCalculator(ScoringPolicy(check_in_from=3.0, reach_out_above=4.0))
        verifier = AIScoreVerifier(calculator)
        self.assertIn("below 3: risk_category Low", verifier.instructions())
        # 3.18 is Moderate under the default policy, but Moderate here too (3.0-4.0).
        self.assertIsNone(verifier.verify(MODERATE_REPLY, MODERATE_STUDENT))
        low_reply = {**MODERATE_REPLY, "stress_score": 1.82}
        self.assertIn("risk_category must be Low", verifier.verify(low_reply, MODERATE_STUDENT))


if __name__ == "__main__":
    unittest.main()
