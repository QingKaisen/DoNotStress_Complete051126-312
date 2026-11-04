"""Integration tests: Logic working with the other three managers' contracts.

The AI, data and IO managers are replaced by their test doubles, so the
whole pipeline runs without a live API or files:

    io (student dict) -> MockAIManager -> LogicManager -> InMemoryRecordRepository
                                                     '-> RecordingDisplay
"""

import unittest

from ai_manager import AIManagerInterface, AIProcessingError, MockAIManager
from data_manager import InMemoryRecordRepository, RecordRepository
from io_manager import RecordingDisplay, ResultDisplay
from logic_manager import AIScoreVerifier, LogicManager, ScoreCalculator
from sample_ai_records import HIGH_REPLY, HIGH_STUDENT, MODERATE_REPLY, MODERATE_STUDENT


class ManagerContractTests(unittest.TestCase):
    def setUp(self):
        calculator = ScoreCalculator()  # one calculator shared by Logic and the verifier
        self.logic = LogicManager(calculator=calculator)
        self.verifier = AIScoreVerifier(calculator)
        self.store = InMemoryRecordRepository()
        self.display = RecordingDisplay()

    def test_full_pipeline_without_a_live_api(self):
        ai = MockAIManager(MODERATE_REPLY, verifier=self.verifier)

        enriched = ai.analyse(MODERATE_STUDENT)
        result = self.logic.evaluate(enriched)
        stored = self.store.save(result.to_record())
        self.display.display_result(result.to_display())

        self.assertEqual(stored["student_id"], "2512345")
        self.assertEqual(stored["risk_category"], "Moderate")
        self.assertEqual(stored["source"], "ai_logic")
        self.assertIn("record_id", stored)
        kind, view = self.display.shown[0]
        self.assertEqual(kind, "result")
        self.assertEqual(view["soft_label"], "Worth a check-in")
        self.assertNotIn("stress_score", view)

    def test_wrong_ai_arithmetic_stops_before_logic(self):
        ai = MockAIManager({**MODERATE_REPLY, "stress_score": 2.9}, verifier=self.verifier)
        with self.assertRaises(AIProcessingError) as caught:
            ai.analyse(MODERATE_STUDENT)
        self.assertEqual(caught.exception.code, "invalid_response")
        self.assertEqual(self.store.load(), [])

    def test_saved_records_can_be_queried(self):
        for student, reply in ((MODERATE_STUDENT, MODERATE_REPLY), (HIGH_STUDENT, HIGH_REPLY)):
            enriched = MockAIManager(reply, verifier=self.verifier).analyse(student)
            self.store.save(self.logic.evaluate(enriched).to_record())

        high = self.store.query(lambda record: record["risk_category"] == "High")
        self.assertEqual([record["student_id"] for record in high], ["2400001"])
        self.assertTrue(high[0]["support_priority"])

    def test_store_never_keeps_reflection_text(self):
        stored = self.store.save({"student_id": "2605581", "feelings_text": "private"})
        self.assertNotIn("feelings_text", stored)
        self.assertNotIn("feelings_text", self.store.load()[0])

    def test_interfaces_cannot_be_created_directly(self):
        for interface in (AIManagerInterface, RecordRepository, ResultDisplay):
            with self.subTest(interface=interface.__name__), self.assertRaises(TypeError):
                interface()


if __name__ == "__main__":
    unittest.main()
