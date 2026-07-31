"""Tests for stage_validation.py — the shared response-envelope validator.

Two of these cases (test_missing_evidence_key_is_rejected,
test_narrative_map_as_bare_string_is_rejected) directly reproduce the two real
2026-07-30/31 Schneider Electric production failures character-for-character: proof this
validator actually catches the bugs that motivated building it, not just synthetic cases.

Run with: python3 -m unittest test_stage_validation -v
"""
import unittest

from stage_validation import (
    CANDIDATES_RESPONSE_SCHEMA,
    CRITIQUE_RESPONSE_SCHEMA,
    DIAGNOSIS_RESPONSE_SCHEMA,
    FOUNDATION_RESPONSE_SCHEMA,
    RECOMMEND_AND_MAP_RESPONSE_SCHEMA,
    StageResponseError,
    validate_stage_response,
)


class EnvelopeShapeValidation(unittest.TestCase):
    def test_none_response_is_rejected(self):
        with self.assertRaises(StageResponseError) as ctx:
            validate_stage_response("diagnosis", None, DIAGNOSIS_RESPONSE_SCHEMA)
        self.assertIn("no response", str(ctx.exception))

    def test_bare_string_response_is_rejected(self):
        with self.assertRaises(StageResponseError) as ctx:
            validate_stage_response("diagnosis", "not an object", DIAGNOSIS_RESPONSE_SCHEMA)
        self.assertIn("must be an object", str(ctx.exception))

    def test_list_response_is_rejected(self):
        with self.assertRaises(StageResponseError):
            validate_stage_response("candidates", [1, 2, 3], CANDIDATES_RESPONSE_SCHEMA)

    def test_missing_evidence_key_is_rejected(self):
        """The actual 2026-07-31 Schneider Electric failure: diagnose() returned a
        response missing the top-level "evidence" key entirely, causing an unhandled
        KeyError deep inside run_analysis() that crashed the whole run and lost the
        already-succeeded strategic_foundation stage's cost/results."""
        response = {"diagnosis": [], "competitorOverlapAssessed": True, "competitorOverlapNote": "", "competitorContrasts": []}
        with self.assertRaises(StageResponseError) as ctx:
            validate_stage_response("diagnosis", response, DIAGNOSIS_RESPONSE_SCHEMA)
        self.assertIn("evidence", str(ctx.exception))
        self.assertEqual(ctx.exception.field, "evidence")

    def test_narrative_map_as_bare_string_is_rejected(self):
        """The actual 2026-07-30 Schneider Electric failure: recommend_and_map returned
        "narrativeMap" as a plain string, causing TypeError('string indices must be
        integers') the first time downstream code did narrativeMap["coreNarrative"]."""
        response = {
            "recommendedCandidateId": "c1", "recommendedDecision": "x", "whyItWins": "x",
            "whyCustomersCare": "x", "whyCredible": "x", "howDifferent": "x",
            "missingEvidence": [], "tradeoffs": [], "leadershipDecisionsRequired": [],
            "whyOthersNotSelected": {}, "audiences": [],
            "narrativeMap": "this is a malformed narrativeMap, not an object",
        }
        with self.assertRaises(StageResponseError) as ctx:
            validate_stage_response("recommendation_and_map", response, RECOMMEND_AND_MAP_RESPONSE_SCHEMA)
        self.assertIn("narrativeMap", str(ctx.exception))
        self.assertEqual(ctx.exception.field, "narrativeMap")

    def test_wrong_type_for_bool_field_is_rejected(self):
        response = {
            "evidence": [], "diagnosis": [], "competitorOverlapAssessed": "yes",
            "competitorOverlapNote": "", "competitorContrasts": [],
        }
        with self.assertRaises(StageResponseError) as ctx:
            validate_stage_response("diagnosis", response, DIAGNOSIS_RESPONSE_SCHEMA)
        self.assertEqual(ctx.exception.field, "competitorOverlapAssessed")

    def test_multiple_missing_fields_names_the_first_in_field_but_all_in_message(self):
        with self.assertRaises(StageResponseError) as ctx:
            validate_stage_response("candidates", {}, CANDIDATES_RESPONSE_SCHEMA)
        self.assertEqual(ctx.exception.field, "candidates")

    def test_valid_foundation_response_passes(self):
        response = {"evidence": [], "strategicFoundation": []}
        result = validate_stage_response("strategic_foundation", response, FOUNDATION_RESPONSE_SCHEMA)
        self.assertIs(result, response)

    def test_valid_critique_response_passes(self):
        response = {"critiques": []}
        validate_stage_response("critique", response, CRITIQUE_RESPONSE_SCHEMA)  # must not raise

    def test_never_coerces_a_dict_shaped_like_a_list_field(self):
        """A dict where a list was required must be rejected, never silently wrapped in a
        list or otherwise coerced into something merely usable."""
        response = {"critiques": {"not": "a list"}}
        with self.assertRaises(StageResponseError):
            validate_stage_response("critique", response, CRITIQUE_RESPONSE_SCHEMA)

    def test_bool_is_not_accidentally_accepted_as_int_where_dict_or_list_expected(self):
        response = {"evidence": True, "strategicFoundation": []}
        with self.assertRaises(StageResponseError) as ctx:
            validate_stage_response("strategic_foundation", response, FOUNDATION_RESPONSE_SCHEMA)
        self.assertEqual(ctx.exception.field, "evidence")


if __name__ == "__main__":
    unittest.main()
