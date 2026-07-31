"""Automated tests for statement_type_check.py — no network, no API calls, no cost.
Run with: python3 -m unittest test_statement_type_check -v
"""
import unittest

from statement_type_check import validate_diagnosis_finding, validate_strategic_choice


def direct(evidence_id):
    return {"evidenceId": evidence_id, "relevance": "direct", "rationale": "r"}


def partial(evidence_id):
    return {"evidenceId": evidence_id, "relevance": "partial", "rationale": "r"}


class ValidEnumCombinations(unittest.TestCase):
    def test_source_fact_with_direct_evidence_is_ok(self):
        record = {"id": "sf1", "type": "customer", "statement": "The company states X.", "evidence": [direct("e1")], "statementType": "source_fact"}
        action, corrected, violations = validate_strategic_choice(record)
        self.assertEqual(action, "ok")
        self.assertEqual(corrected, "source_fact")
        self.assertEqual(violations, [])

    def test_unresolved_with_leadership_decision_is_ok(self):
        record = {"id": "sf2", "type": "unresolved", "statement": "Needs a decision.", "evidence": [], "statementType": "leadership_decision"}
        action, corrected, violations = validate_strategic_choice(record)
        self.assertEqual(action, "ok")
        self.assertEqual(corrected, "leadership_decision")
        self.assertEqual(violations, [])

    def test_storymap_synthesis_with_two_contributing_links_is_ok(self):
        record = {"id": "sf3", "type": "market", "statement": "Combines two facts.", "evidence": [direct("e1"), partial("e2")], "statementType": "storymap_synthesis"}
        action, corrected, violations = validate_strategic_choice(record)
        self.assertEqual(action, "ok")
        self.assertEqual(corrected, "storymap_synthesis")
        self.assertEqual(violations, [])

    def test_aspiration_is_valid_for_non_unresolved_choice(self):
        record = {"id": "sf4", "type": "way_to_win", "statement": "The company aims to X.", "evidence": [], "statementType": "aspiration"}
        action, corrected, violations = validate_strategic_choice(record)
        self.assertEqual(action, "ok")
        self.assertEqual(corrected, "aspiration")

    def test_diagnosis_source_fact_with_direct_evidence_is_ok(self):
        record = {"id": "d1", "title": "t", "explanation": "The page states X plainly.", "evidence": [direct("e1")], "statementType": "source_fact"}
        action, corrected, violations = validate_diagnosis_finding(record)
        self.assertEqual(action, "ok")
        self.assertEqual(corrected, "source_fact")
        self.assertEqual(violations, [])

    def test_diagnosis_storymap_inference_is_ok(self):
        record = {"id": "d2", "title": "t", "explanation": "This suggests a broader pattern.", "evidence": [direct("e1")], "statementType": "storymap_inference"}
        action, corrected, violations = validate_diagnosis_finding(record)
        self.assertEqual(action, "ok")
        self.assertEqual(corrected, "storymap_inference")


class InvalidStatementType(unittest.TestCase):
    def test_non_unresolved_type_with_invalid_statement_type_is_rejected(self):
        """The actual bug found in the 2026-07-29 test run: type "market_change" carried
        statementType "unresolved", which isn't a real enum value at all. Since the type
        field isn't "unresolved", there's no unambiguous correction — must reject, not
        guess. (This is the case the old, narrower validator missed entirely.)"""
        record = {"id": "sf10", "type": "market_change", "statement": "No evidence available.", "evidence": [], "statementType": "unresolved"}
        action, corrected, violations = validate_strategic_choice(record)
        self.assertEqual(action, "rejected")
        self.assertTrue(any("invalid statementType" in v for v in violations))

    def test_unresolved_type_field_with_bogus_statement_type_maps_to_leadership_decision(self):
        record = {"id": "sf11", "type": "unresolved", "statement": "x", "evidence": [], "statementType": "unresolved"}
        action, corrected, violations = validate_strategic_choice(record)
        self.assertEqual(action, "mapped")
        self.assertEqual(corrected, "leadership_decision")

    def test_nonsense_statement_type_on_diagnosis_is_rejected(self):
        record = {"id": "d3", "title": "t", "explanation": "e", "evidence": [], "statementType": "settled_fact"}
        action, corrected, violations = validate_diagnosis_finding(record)
        self.assertEqual(action, "rejected")
        self.assertIsNone(corrected)
        self.assertTrue(any("invalid statementType" in v for v in violations))


class InvalidType(unittest.TestCase):
    def test_unknown_type_value_is_rejected(self):
        record = {"id": "sf5", "type": "goal", "statement": "x", "evidence": [direct("e1")], "statementType": "source_fact"}
        action, corrected, violations = validate_strategic_choice(record)
        self.assertEqual(action, "rejected")
        self.assertIsNone(corrected)
        self.assertTrue(any("invalid type" in v for v in violations))

    def test_empty_string_type_is_rejected_as_missing(self):
        record = {"id": "sf6", "type": "", "statement": "x", "evidence": [], "statementType": "source_fact"}
        action, corrected, violations = validate_strategic_choice(record)
        self.assertEqual(action, "rejected")


class MismatchedTypeAndStatementType(unittest.TestCase):
    def test_non_unresolved_type_with_leadership_decision_is_rejected(self):
        record = {"id": "sf7", "type": "customer", "statement": "x", "evidence": [direct("e1")], "statementType": "leadership_decision"}
        action, corrected, violations = validate_strategic_choice(record)
        self.assertEqual(action, "rejected")
        self.assertIsNone(corrected)
        self.assertTrue(any("contradictory" in v for v in violations))

    def test_unresolved_type_with_source_fact_is_mapped_to_leadership_decision(self):
        record = {"id": "sf8", "type": "unresolved", "statement": "x", "evidence": [], "statementType": "source_fact"}
        action, corrected, violations = validate_strategic_choice(record)
        self.assertEqual(action, "mapped")
        self.assertEqual(corrected, "leadership_decision")

    def test_non_unresolved_type_with_recommendation_statement_type_is_rejected(self):
        record = {"id": "sf9", "type": "proof", "statement": "x", "evidence": [direct("e1")], "statementType": "recommendation"}
        action, corrected, violations = validate_strategic_choice(record)
        self.assertEqual(action, "rejected")
        self.assertIsNone(corrected)

    def test_diagnosis_with_leadership_decision_statement_type_is_rejected(self):
        record = {"id": "d4", "title": "t", "explanation": "e", "evidence": [], "statementType": "leadership_decision"}
        action, corrected, violations = validate_diagnosis_finding(record)
        self.assertEqual(action, "rejected")
        self.assertIsNone(corrected)

    def test_diagnosis_with_recommendation_statement_type_is_rejected(self):
        record = {"id": "d5", "title": "t", "explanation": "e", "evidence": [], "statementType": "recommendation"}
        action, corrected, violations = validate_diagnosis_finding(record)
        self.assertEqual(action, "rejected")


class MissingClassificationFields(unittest.TestCase):
    def test_missing_type_field_is_rejected(self):
        record = {"id": "sf12", "statement": "x", "evidence": [], "statementType": "source_fact"}
        action, corrected, violations = validate_strategic_choice(record)
        self.assertEqual(action, "rejected")
        self.assertIsNone(corrected)
        self.assertTrue(any("missing" in v for v in violations))

    def test_missing_statement_type_field_is_rejected(self):
        record = {"id": "sf13", "type": "customer", "statement": "x", "evidence": []}
        action, corrected, violations = validate_strategic_choice(record)
        self.assertEqual(action, "rejected")
        self.assertIsNone(corrected)
        self.assertTrue(any("missing" in v for v in violations))

    def test_missing_statement_type_on_diagnosis_is_rejected(self):
        record = {"id": "d6", "title": "t", "explanation": "e", "evidence": []}
        action, corrected, violations = validate_diagnosis_finding(record)
        self.assertEqual(action, "rejected")
        self.assertIsNone(corrected)


class SemanticDowngrades(unittest.TestCase):
    """Regression coverage for the pre-existing, already-shipped semantic rules."""

    def test_source_fact_without_direct_evidence_is_mapped(self):
        record = {"id": "sf14", "type": "customer", "statement": "x", "evidence": [partial("e1")], "statementType": "source_fact"}
        action, corrected, violations = validate_strategic_choice(record)
        self.assertEqual(action, "mapped")
        self.assertEqual(corrected, "storymap_inference")

    def test_source_fact_with_hedge_language_is_mapped(self):
        record = {"id": "sf15", "type": "customer", "statement": "This suggests broad appeal.", "evidence": [direct("e1")], "statementType": "source_fact"}
        action, corrected, violations = validate_strategic_choice(record)
        self.assertEqual(action, "mapped")
        self.assertEqual(corrected, "storymap_inference")

    def test_synthesis_with_one_contributing_link_is_mapped(self):
        record = {"id": "sf16", "type": "market", "statement": "x", "evidence": [direct("e1")], "statementType": "storymap_synthesis"}
        action, corrected, violations = validate_strategic_choice(record)
        self.assertEqual(action, "mapped")
        self.assertEqual(corrected, "storymap_inference")


if __name__ == "__main__":
    unittest.main()
