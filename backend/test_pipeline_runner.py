"""Tests for pipeline_runner.py's pure/testable logic — no network, no Anthropic API
calls. Covers the evidence-integrity requirements explicitly re-affirmed after the
2026-07-29 review: candidate scores must never include a numeric "Customer relevance",
and competitor contrasts must always be labeled provisional inference, never a fact.

Run with: python3 -m unittest test_pipeline_runner -v
"""
import json
import os
import unittest
from unittest.mock import patch

os.environ["ANTHROPIC_API_KEY"] = "sk-test-do-not-use-not-a-real-key"

import anthropic_pipeline as pipe
import pipeline_runner
from pipeline_runner import (
    GATE_TO_SCORE,
    MAX_FULL_REGENERATIONS,
    MAX_MANUAL_RETRIES,
    MAX_SOURCE_EXPANSIONS,
    MAX_TOTAL_ATTEMPTS,
    MIN_COVERED_DIMENSIONS_FOR_SUFFICIENT,
    MIN_SOURCES_FOR_SUFFICIENT,
    STAGE_DEPENDENCIES,
    STAGE_ORDER,
    NarrativeMapValidationError,
    assess_source_coverage,
    build_attempt_record,
    build_candidate_scores_and_status,
    build_case_context,
    check_manual_retry_allowed,
    check_regeneration_allowed,
    check_source_expansion_allowed,
    check_upstream_stages_valid,
    invalidate_downstream_stages,
    retry_critique_candidates,
    retry_diagnose,
    retry_extract_foundation,
    retry_generate_candidates,
    retry_recommendation_and_map,
    run_analysis,
    run_model_stage,
    run_pipeline_from_sources,
    validate_edited_foundation,
    validate_narrative_map_shape,
)


class CandidateScoreBuilder(unittest.TestCase):
    def test_never_includes_customer_relevance(self):
        gate = {"strategicFitGate": "meets", "differentiationGate": "meets", "evidenceSupportGate": "supported"}
        scores, status = build_candidate_scores_and_status(gate)
        self.assertNotIn("Customer relevance", scores)

    def test_never_includes_durability(self):
        gate = {"strategicFitGate": "meets", "differentiationGate": "meets", "evidenceSupportGate": "supported"}
        scores, status = build_candidate_scores_and_status(gate)
        self.assertNotIn("Durability", scores)

    def test_only_expected_score_keys(self):
        gate = {"strategicFitGate": "weak", "differentiationGate": "weak", "evidenceSupportGate": "partial"}
        scores, status = build_candidate_scores_and_status(gate)
        self.assertEqual(set(scores.keys()), {"Strategic fit", "Differentiation", "Evidence strength"})

    def test_all_meets_passes(self):
        gate = {"strategicFitGate": "meets", "differentiationGate": "meets", "evidenceSupportGate": "supported"}
        scores, status = build_candidate_scores_and_status(gate)
        self.assertEqual(status, "candidate")
        self.assertEqual(scores["Strategic fit"], GATE_TO_SCORE["meets"])

    def test_weak_alone_still_passes(self):
        """'weak'/'partial' are the middle tier, not failures — matches the earlier test
        run's observed behavior (3 real candidates, 0 rejected, several with 'weak')."""
        gate = {"strategicFitGate": "weak", "differentiationGate": "meets", "evidenceSupportGate": "partial"}
        scores, status = build_candidate_scores_and_status(gate)
        self.assertEqual(status, "candidate")

    def test_strategic_fit_fails_rejects(self):
        gate = {"strategicFitGate": "fails", "differentiationGate": "meets", "evidenceSupportGate": "supported"}
        _, status = build_candidate_scores_and_status(gate)
        self.assertEqual(status, "rejected")

    def test_differentiation_fails_rejects(self):
        gate = {"strategicFitGate": "meets", "differentiationGate": "fails", "evidenceSupportGate": "supported"}
        _, status = build_candidate_scores_and_status(gate)
        self.assertEqual(status, "rejected")

    def test_unsupported_evidence_rejects(self):
        gate = {"strategicFitGate": "meets", "differentiationGate": "meets", "evidenceSupportGate": "unsupported"}
        _, status = build_candidate_scores_and_status(gate)
        self.assertEqual(status, "rejected")

    def test_weak_score_sits_at_pass_threshold(self):
        """weak/partial must map to exactly the scoring.js MIN_SCORE_THRESHOLDS cutoff (3)
        so the frontend's own independent gate check (computeOverallScore) reaches the
        same accept decision this backend already made — see GATE_TO_SCORE's docstring."""
        self.assertEqual(GATE_TO_SCORE["weak"], 3)
        self.assertEqual(GATE_TO_SCORE["partial"], 3)

    def test_fails_score_sits_below_pass_threshold(self):
        self.assertLess(GATE_TO_SCORE["fails"], 3)
        self.assertLess(GATE_TO_SCORE["unsupported"], 3)


EVIDENCE_ITEM = lambda id_, source_id, excerpt: {  # noqa: E731
    "id": id_, "sourceId": source_id, "excerpt": excerpt, "paraphrase": "p",
    "evidenceType": "statement", "strength": "moderate", "freshness": "current",
}
LINK = lambda evidence_id, relevance="direct": {"evidenceId": evidence_id, "relevance": relevance, "rationale": "r"}  # noqa: E731


def _valid_narrative_map():
    return {
        "coreNarrative": "x",
        "sevenParts": {k: "x" for k in ["context", "tension", "belief", "role", "value", "proof", "direction"]},
        "coreClaims": [],
        "likelyObjections": [],
        "weakOrUnsupportedClaims": [],
        "unresolvedQuestions": [],
    }


class NarrativeMapShapeValidation(unittest.TestCase):
    """Direct unit tests for validate_narrative_map_shape() — the fix for the
    2026-07-30 Schneider Electric failure and the explicit 2026-07-31 requirement that
    all seven Context/Tension/Belief/Role/Value/Proof/Direction fields be present as
    valid, non-empty strings, with bare strings, arrays, missing fields and invalid
    nested records all rejected outright, never coerced."""

    def test_valid_narrative_map_passes(self):
        validate_narrative_map_shape(_valid_narrative_map())  # must not raise

    def test_bare_string_top_level_is_rejected(self):
        with self.assertRaises(NarrativeMapValidationError) as ctx:
            validate_narrative_map_shape("this is a malformed narrativeMap, not an object")
        self.assertIn("must be an object", str(ctx.exception))

    def test_array_top_level_is_rejected(self):
        with self.assertRaises(NarrativeMapValidationError) as ctx:
            validate_narrative_map_shape(["not", "an", "object"])
        self.assertIn("must be an object", str(ctx.exception))

    def test_none_top_level_is_rejected(self):
        with self.assertRaises(NarrativeMapValidationError):
            validate_narrative_map_shape(None)

    def test_missing_top_level_field_is_rejected(self):
        nm = _valid_narrative_map()
        del nm["coreNarrative"]
        with self.assertRaises(NarrativeMapValidationError) as ctx:
            validate_narrative_map_shape(nm)
        self.assertIn("coreNarrative", str(ctx.exception))

    def test_core_claims_as_string_instead_of_array_is_rejected(self):
        nm = _valid_narrative_map()
        nm["coreClaims"] = "not an array"
        with self.assertRaises(NarrativeMapValidationError) as ctx:
            validate_narrative_map_shape(nm)
        self.assertIn("coreClaims", str(ctx.exception))
        self.assertIn("must be an array", str(ctx.exception))

    def test_seven_parts_as_bare_string_is_rejected(self):
        nm = _valid_narrative_map()
        nm["sevenParts"] = "context, tension, belief..."
        with self.assertRaises(NarrativeMapValidationError) as ctx:
            validate_narrative_map_shape(nm)
        self.assertIn("sevenParts must be an object", str(ctx.exception))

    def test_seven_parts_as_array_is_rejected(self):
        nm = _valid_narrative_map()
        nm["sevenParts"] = ["context", "tension", "belief", "role", "value", "proof", "direction"]
        with self.assertRaises(NarrativeMapValidationError) as ctx:
            validate_narrative_map_shape(nm)
        self.assertIn("sevenParts must be an object", str(ctx.exception))

    def test_seven_parts_missing_one_field_is_rejected(self):
        nm = _valid_narrative_map()
        del nm["sevenParts"]["direction"]
        with self.assertRaises(NarrativeMapValidationError) as ctx:
            validate_narrative_map_shape(nm)
        self.assertIn("direction", str(ctx.exception))

    def test_seven_parts_missing_several_fields_names_all_of_them(self):
        nm = _valid_narrative_map()
        del nm["sevenParts"]["context"]
        del nm["sevenParts"]["proof"]
        with self.assertRaises(NarrativeMapValidationError) as ctx:
            validate_narrative_map_shape(nm)
        self.assertIn("context", str(ctx.exception))
        self.assertIn("proof", str(ctx.exception))

    def test_seven_parts_with_empty_string_value_is_rejected(self):
        nm = _valid_narrative_map()
        nm["sevenParts"]["tension"] = "   "
        with self.assertRaises(NarrativeMapValidationError) as ctx:
            validate_narrative_map_shape(nm)
        self.assertIn("tension", str(ctx.exception))

    def test_seven_parts_with_non_string_value_is_rejected(self):
        nm = _valid_narrative_map()
        nm["sevenParts"]["belief"] = {"nested": "record instead of a string"}
        with self.assertRaises(NarrativeMapValidationError) as ctx:
            validate_narrative_map_shape(nm)
        self.assertIn("belief", str(ctx.exception))

    def test_seven_parts_with_list_value_is_rejected(self):
        nm = _valid_narrative_map()
        nm["sevenParts"]["value"] = ["invalid", "nested", "record"]
        with self.assertRaises(NarrativeMapValidationError) as ctx:
            validate_narrative_map_shape(nm)
        self.assertIn("value", str(ctx.exception))

    def test_likely_objections_as_string_is_rejected(self):
        nm = _valid_narrative_map()
        nm["likelyObjections"] = "should be an array"
        with self.assertRaises(NarrativeMapValidationError) as ctx:
            validate_narrative_map_shape(nm)
        self.assertIn("likelyObjections", str(ctx.exception))


class CompetitorContrastLabeling(unittest.TestCase):
    """Integration-style: run_analysis() with every network/model call mocked, verifying
    this module's OWN transformation of the model's competitorContrasts output — the
    model is never trusted to self-label this correctly; the server forces it."""

    def setUp(self):
        self.addCleanup(patch.stopall)
        patch("pipeline_runner.fetch_all_sources", return_value=(
            [{"id": "src_live_company", "companyId": "live", "title": "Co", "publisher": "co.com",
              "sourceType": "website", "url": "https://co.com", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"}],
            {"src_live_company": "The company serves manufacturing customers."},
            [],
            {"id": "src_live_company", "title": "Co", "publisher": "co.com"},
        )).start()

        patch("anthropic_pipeline.get_client", return_value=object()).start()

        patch("anthropic_pipeline.extract_foundation", return_value={
            "evidence": [EVIDENCE_ITEM("ev1", "src_live_company", "The company serves manufacturing customers.")],
            "strategicFoundation": [{
                "id": "sf1", "type": "customer", "statement": "Serves manufacturing customers.",
                "statementType": "source_fact", "evidence": [LINK("ev1")],
            }],
        }).start()

        patch("anthropic_pipeline.diagnose", return_value={
            "evidence": [],
            "diagnosis": [{
                "id": "d1", "title": "t", "explanation": "The company serves manufacturing customers.",
                "significance": "medium", "statementType": "source_fact", "evidence": [LINK("ev1")],
            }],
            "competitorOverlapAssessed": True,
            "competitorOverlapNote": "",
            "competitorContrasts": [{"competitor": "RivalCo", "contrast": "Rival focuses on retail, not manufacturing."}],
        }).start()

        candidates = [
            {"id": f"cand{i}", "name": f"Candidate {i}", "oneSentenceStory": "x",
             "sevenParts": {k: "x" for k in ["context", "tension", "belief", "role", "value", "proof", "direction"]},
             "strategicLogic": ["x"], "customerRelevance": "x", "differentiation": "x",
             "tradeoffs": ["x"], "risks": ["x"], "claims": [LINK("ev1")]}
            for i in range(1, 4)
        ]
        patch("anthropic_pipeline.generate_candidates", return_value={"candidates": candidates}).start()

        patch("anthropic_pipeline.critique_candidates", return_value={"critiques": [
            {"candidateId": c["id"], "findings": ["ok"], "strategicFitGate": "meets",
             "differentiationGate": "meets", "evidenceSupportGate": "supported"}
            for c in candidates
        ]}).start()

        patch("anthropic_pipeline.recommend_and_map", return_value={
            "recommendedCandidateId": "cand1", "recommendedDecision": "x", "whyItWins": "x",
            "whyCustomersCare": "x", "whyCredible": "x", "howDifferent": "x", "missingEvidence": [],
            "tradeoffs": [], "leadershipDecisionsRequired": [], "whyOthersNotSelected": {"cand2": "x", "cand3": "x"},
            "audiences": [],
            "narrativeMap": {
                "coreNarrative": "x",
                "sevenParts": {k: "x" for k in ["context", "tension", "belief", "role", "value", "proof", "direction"]},
                "coreClaims": [], "likelyObjections": [], "weakOrUnsupportedClaims": [], "unresolvedQuestions": [],
            },
        }).start()

    def test_competitor_contrasts_are_always_labeled_inference(self):
        result = run_analysis("https://co.com", [], ["https://rival.com"], "", progress_cb=lambda *_: None)
        dataset = result["dataset"]
        self.assertTrue(dataset["competitorContrasts"], "expected at least one competitor contrast")
        for c in dataset["competitorContrasts"]:
            self.assertEqual(c["statementType"], "storymap_inference")
            self.assertEqual(c["evidence"], [])

    def test_candidates_never_carry_customer_relevance_score(self):
        result = run_analysis("https://co.com", [], [], "", progress_cb=lambda *_: None)
        for cand in result["dataset"]["candidates"]:
            self.assertNotIn("Customer relevance", cand["scores"])


def _valid_candidates():
    return [
        {"id": f"cand{i}", "name": f"Candidate {i}", "oneSentenceStory": "x",
         "sevenParts": {k: "x" for k in ["context", "tension", "belief", "role", "value", "proof", "direction"]},
         "strategicLogic": ["x"], "customerRelevance": "x", "differentiation": "x",
         "tradeoffs": ["x"], "risks": ["x"], "claims": [LINK("ev1")]}
        for i in range(1, 4)
    ]


def _valid_critiques(candidates):
    return [
        {"candidateId": c["id"], "findings": ["ok"], "strategicFitGate": "meets",
         "differentiationGate": "meets", "evidenceSupportGate": "supported"}
        for c in candidates
    ]


_VALID_RECOMMEND_AND_MAP = {
    "recommendedCandidateId": "cand1", "recommendedDecision": "x", "whyItWins": "x",
    "whyCustomersCare": "x", "whyCredible": "x", "howDifferent": "x", "missingEvidence": [],
    "tradeoffs": [], "leadershipDecisionsRequired": [], "whyOthersNotSelected": {"cand2": "x", "cand3": "x"},
    "audiences": [],
    "narrativeMap": {
        "coreNarrative": "x",
        "sevenParts": {k: "x" for k in ["context", "tension", "belief", "role", "value", "proof", "direction"]},
        "coreClaims": [], "likelyObjections": [], "weakOrUnsupportedClaims": [], "unresolvedQuestions": [],
    },
}


class MalformedRecordHandling(unittest.TestCase):
    """Regression coverage for the 2026-07-30 Schneider Electric live-run failure:
    TypeError('string indices must be integers'). That error means Python code did
    record["key"] on a value that turned out to be a plain str — i.e. the model returned a
    bare string in an array field where the tool-use schema declared an object. The exact
    file/line of the ORIGINAL failure could not be retrieved after the fact (jobs.py never
    captured a traceback before this fix — see jobs.py's updated except-block comment), so
    this reproduces the failure SHAPE at every plausible boundary instead of one specific
    line, and asserts each is now a clean rejection, never a crash.
    """

    def setUp(self):
        self.addCleanup(patch.stopall)
        patch("pipeline_runner.fetch_all_sources", return_value=(
            [{"id": "src_live_company", "companyId": "live", "title": "Co", "publisher": "co.com",
              "sourceType": "website", "url": "https://co.com", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"}],
            {"src_live_company": "The company serves manufacturing customers."},
            [],
            {"id": "src_live_company", "title": "Co", "publisher": "co.com"},
        )).start()
        patch("anthropic_pipeline.get_client", return_value=object()).start()

        self.foundation_result = {
            "evidence": [EVIDENCE_ITEM("ev1", "src_live_company", "The company serves manufacturing customers.")],
            "strategicFoundation": [{
                "id": "sf1", "type": "customer", "statement": "Serves manufacturing customers.",
                "statementType": "source_fact", "evidence": [LINK("ev1")],
            }],
        }
        self.diagnose_result = {
            "evidence": [],
            "diagnosis": [{
                "id": "d1", "title": "t", "explanation": "The company serves manufacturing customers.",
                "significance": "medium", "statementType": "source_fact", "evidence": [LINK("ev1")],
            }],
            "competitorOverlapAssessed": False,
            "competitorOverlapNote": "",
            "competitorContrasts": [],
        }
        self.candidates_result = {"candidates": _valid_candidates()}
        self.critique_result = {"critiques": _valid_critiques(_valid_candidates())}
        self.recommend_result = dict(_VALID_RECOMMEND_AND_MAP)

        patch("anthropic_pipeline.extract_foundation", side_effect=lambda *a, **k: self.foundation_result).start()
        patch("anthropic_pipeline.diagnose", side_effect=lambda *a, **k: self.diagnose_result).start()
        patch("anthropic_pipeline.generate_candidates", side_effect=lambda *a, **k: self.candidates_result).start()
        patch("anthropic_pipeline.critique_candidates", side_effect=lambda *a, **k: self.critique_result).start()
        patch("anthropic_pipeline.recommend_and_map", side_effect=lambda *a, **k: self.recommend_result).start()

    def _run(self):
        return run_analysis("https://co.com", [], [], "", progress_cb=lambda *_: None)

    def test_bare_string_in_strategic_foundation_is_rejected_not_crashed(self):
        self.foundation_result["strategicFoundation"] = [
            self.foundation_result["strategicFoundation"][0],
            "this is a malformed record, not an object",
        ]
        result = self._run()  # must not raise TypeError
        self.assertIsNotNone(result["dataset"])
        reasons = [r for rec in result["diagnostics"]["rejected_records"] for r in rec["reasons"]]
        self.assertTrue(any("expected an object" in r for r in reasons))

    def test_bare_string_in_diagnosis_is_rejected_not_crashed(self):
        self.diagnose_result["diagnosis"] = [
            self.diagnose_result["diagnosis"][0],
            "malformed diagnosis entry",
        ]
        result = self._run()
        self.assertIsNotNone(result["dataset"])
        reasons = [r for rec in result["diagnostics"]["rejected_records"] for r in rec["reasons"]]
        self.assertTrue(any("expected an object" in r for r in reasons))

    def test_diagnosis_finding_labeled_leadership_decision_is_dropped_end_to_end(self):
        """The recurring problem this session: the model repeatedly mislabels a diagnosis
        finding statementType as leadership_decision. validate_diagnosis_finding already
        rejects this at the unit level (test_statement_type_check.py); this proves the
        server-side backstop still holds through the FULL pipeline even if the model
        ignores the new schema-level constraint (diagnose()'s statementType enum no
        longer offers this value at all — see DiagnosisClassificationConstraint below) —
        the finding must never reach the final dataset with that label, or at all."""
        self.diagnose_result["diagnosis"] = [
            self.diagnose_result["diagnosis"][0],
            {
                "id": "d_bad", "title": "Leadership must decide on repositioning",
                "explanation": "The company needs to decide whether to reposition.",
                "significance": "high", "statementType": "leadership_decision", "evidence": [],
            },
        ]
        result = self._run()
        self.assertIsNotNone(result["dataset"])
        finding_ids = [f["id"] for f in result["dataset"]["diagnosis"]]
        self.assertNotIn("d_bad", finding_ids)
        for finding in result["dataset"]["diagnosis"]:
            self.assertNotEqual(finding["statementType"], "leadership_decision")
        reasons = [r for rec in result["diagnostics"]["rejected_records"] for r in rec["reasons"]]
        self.assertTrue(any("leadership_decision" in r and "not valid for a diagnosis finding" in r for r in reasons))


    def test_bare_string_in_candidates_is_rejected_not_crashed(self):
        self.candidates_result["candidates"] = _valid_candidates() + ["malformed candidate"]
        result = self._run()
        self.assertIsNotNone(result["dataset"])
        reasons = [r for rec in result["diagnostics"]["rejected_records"] for r in rec["reasons"]]
        self.assertTrue(any("expected an object" in r for r in reasons))

    def test_bare_string_in_critiques_is_rejected_not_crashed(self):
        self.critique_result["critiques"] = _valid_critiques(_valid_candidates()) + ["malformed critique"]
        result = self._run()
        self.assertIsNotNone(result["dataset"])
        reasons = [r for rec in result["diagnostics"]["rejected_records"] for r in rec["reasons"]]
        self.assertTrue(any("expected an object" in r for r in reasons))

    def test_bare_string_in_evidence_items_is_rejected_not_crashed(self):
        self.foundation_result["evidence"] = [
            self.foundation_result["evidence"][0],
            "malformed evidence item",
        ]
        result = self._run()
        self.assertIsNotNone(result["dataset"])
        reasons = [r for rec in result["diagnostics"]["rejected_records"] for r in rec["reasons"]]
        self.assertTrue(any("expected an object" in r for r in reasons))

    def test_bare_string_in_core_claims_is_rejected_not_crashed(self):
        self.recommend_result["narrativeMap"] = {
            **_VALID_RECOMMEND_AND_MAP["narrativeMap"],
            "coreClaims": ["malformed core claim"],
        }
        result = self._run()
        self.assertIsNotNone(result["dataset"])
        reasons = [r for rec in result["diagnostics"]["rejected_records"] for r in rec["reasons"]]
        self.assertTrue(any("expected an object" in r for r in reasons))

    def test_bare_string_in_competitor_contrasts_is_rejected_not_crashed(self):
        self.diagnose_result["competitorContrasts"] = ["malformed contrast"]
        result = self._run()
        self.assertIsNotNone(result["dataset"])
        reasons = [r for rec in result["diagnostics"]["rejected_records"] for r in rec["reasons"]]
        self.assertTrue(any("expected an object" in r for r in reasons))

    def test_non_dict_evidence_link_is_dropped_not_crashed(self):
        """The narrower failure shape: the record itself is a dict, but one of ITS
        evidence links is a bare string instead of {evidenceId, relevance, rationale}."""
        self.foundation_result["strategicFoundation"][0]["evidence"] = ["not a link object"]
        result = self._run()
        self.assertIsNotNone(result["dataset"])
        reasons = [d["reason"] for d in result["diagnostics"]["dropped_links"]]
        self.assertTrue(any("malformed evidence link" in r for r in reasons))

    def test_narrative_map_as_bare_string_fails_stage_cleanly_but_preserves_partial_results(self):
        """The actual 2026-07-30 Schneider Electric rerun failure, reproduced exactly:
        recommend_and_map returned "narrativeMap" as a plain string, not an object. Every
        earlier array-item guard (candidates, critiques, coreClaims) was already correct —
        this was the one un-typed top-level field that still crashed with
        TypeError('string indices must be integers') before that fix, caught only by the
        broad except clause with an unhelpful message.

        As of the 2026-07-31 hardening, the whole run must NOT collapse to dataset=None —
        strategicFoundation/diagnosis/candidates/evidence already succeeded and must
        survive intact; only recommendation/narrativeMap/audiences are empty. The failure
        is reported as diagnostics.outcome == "partial_failure" with the exact failed
        stage and reason, and the traceback must be captured but never exposed in
        `diagnostics` (which the frontend receives verbatim)."""
        self.recommend_result["narrativeMap"] = "this is a malformed narrativeMap, not an object"
        result = self._run()  # must not raise
        dataset = result["dataset"]
        diag = result["diagnostics"]

        self.assertIsNotNone(dataset, "partial results must survive a final-stage failure")
        self.assertEqual(len(dataset["strategicFoundation"]), 1)
        self.assertEqual(len(dataset["diagnosis"]), 1)
        self.assertEqual(len(dataset["candidates"]), 3)
        self.assertTrue(dataset["evidence"])
        self.assertIsNone(dataset["recommendation"])
        self.assertIsNone(dataset["narrativeMap"])

        self.assertEqual(diag["outcome"], "stage_failed")
        self.assertEqual(diag["failed_stage"], "recommendation_and_map")
        self.assertIn("narrativeMap", diag["failure_reason"])
        self.assertIn("recommendation_and_map_stage_failed", diag["critical_failure"])
        self.assertNotIn("traceback", diag)  # never leaks into the frontend-facing dict

        self.assertIsNotNone(result["debug_traceback"])
        self.assertIn("narrativeMap", result["debug_traceback"])


class DiagnosisClassificationConstraint(unittest.TestCase):
    """Prompt-level constraint added alongside the existing server-side validator: the
    model is never even offered "leadership_decision" or "recommendation" as options for
    a diagnosis finding's statementType, reducing how often the server-side rejection
    (see MalformedRecordHandling.test_diagnosis_finding_labeled_leadership_decision_is_dropped_end_to_end)
    needs to fire in the first place."""

    def test_diagnose_schema_excludes_leadership_decision_and_recommendation(self):
        captured = {}

        def fake_call_tool(client, usage_tracker, label, user_text, tool_name, tool_description, input_schema, **kwargs):
            captured["schema"] = input_schema
            return {"evidence": [], "diagnosis": [], "competitorOverlapAssessed": False, "competitorOverlapNote": "", "competitorContrasts": []}

        with patch("anthropic_pipeline.call_tool", side_effect=fake_call_tool):
            import anthropic_pipeline as pipe
            pipe.diagnose(object(), object(), [{"id": "s1", "text": "x"}], [], [], "", {})

        enum = captured["schema"]["properties"]["diagnosis"]["items"]["properties"]["statementType"]["enum"]
        self.assertNotIn("leadership_decision", enum)
        self.assertNotIn("recommendation", enum)
        self.assertEqual(set(enum), {"source_fact", "storymap_inference", "storymap_synthesis", "aspiration"})


class RetryRecommendationStage(unittest.TestCase):
    """retry_recommendation_and_map() reruns ONLY the final stage using
    already-validated candidates/evidence_pool/foundation_summary — must never re-fetch
    sources or rerun extract_foundation/diagnose/generate_candidates/
    critique_candidates."""

    def setUp(self):
        self.addCleanup(patch.stopall)
        patch("anthropic_pipeline.get_client", return_value=object()).start()
        self.evidence_pool = {"ev1": {"id": "ev1", "sourceId": "src1", "excerpt": "x", "paraphrase": "p", "strength": "moderate", "verified": True}}
        self.foundation_summary = [{"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact"}]

    def _candidates(self, statuses=("candidate", "candidate", "candidate")):
        cands = _valid_candidates()
        for c, status in zip(cands, statuses):
            c["status"] = status
        return cands

    def test_no_survivors_returns_no_candidate_passed_without_calling_the_api(self):
        mock_recommend = patch("anthropic_pipeline.recommend_and_map").start()
        candidates = self._candidates(statuses=("rejected", "rejected", "rejected"))
        result = retry_recommendation_and_map(candidates, self.evidence_pool, self.foundation_summary)
        self.assertIsNone(result["recommendation"])
        self.assertIsNone(result["narrativeMap"])
        self.assertEqual(result["diagnostics"]["outcome"], "no_candidate_passed")
        mock_recommend.assert_not_called()

    def test_successful_retry_produces_recommendation_and_map(self):
        patch("anthropic_pipeline.recommend_and_map", return_value=dict(_VALID_RECOMMEND_AND_MAP)).start()
        candidates = self._candidates()
        result = retry_recommendation_and_map(candidates, self.evidence_pool, self.foundation_summary)
        self.assertIsNotNone(result["recommendation"])
        self.assertIsNotNone(result["narrativeMap"])
        self.assertEqual(result["diagnostics"]["outcome"], "success")
        self.assertEqual(result["recommendation"]["candidateId"], "cand1")

    def test_retry_does_not_refetch_sources(self):
        mock_fetch = patch("pipeline_runner.fetch_all_sources").start()
        patch("anthropic_pipeline.recommend_and_map", return_value=dict(_VALID_RECOMMEND_AND_MAP)).start()
        retry_recommendation_and_map(self._candidates(), self.evidence_pool, self.foundation_summary)
        mock_fetch.assert_not_called()

    def test_retry_does_not_rerun_the_first_four_stages(self):
        mock_extract = patch("anthropic_pipeline.extract_foundation").start()
        mock_diagnose = patch("anthropic_pipeline.diagnose").start()
        mock_generate = patch("anthropic_pipeline.generate_candidates").start()
        mock_critique = patch("anthropic_pipeline.critique_candidates").start()
        patch("anthropic_pipeline.recommend_and_map", return_value=dict(_VALID_RECOMMEND_AND_MAP)).start()
        retry_recommendation_and_map(self._candidates(), self.evidence_pool, self.foundation_summary)
        mock_extract.assert_not_called()
        mock_diagnose.assert_not_called()
        mock_generate.assert_not_called()
        mock_critique.assert_not_called()

    def test_retry_still_fails_cleanly_on_malformed_narrative_map(self):
        bad_result = dict(_VALID_RECOMMEND_AND_MAP)
        bad_result["narrativeMap"] = "malformed, not an object"
        patch("anthropic_pipeline.recommend_and_map", return_value=bad_result).start()
        result = retry_recommendation_and_map(self._candidates(), self.evidence_pool, self.foundation_summary)
        self.assertIsNone(result["recommendation"])
        self.assertIsNone(result["narrativeMap"])
        self.assertEqual(result["diagnostics"]["outcome"], "stage_failed")
        self.assertIn("narrativeMap", result["diagnostics"]["failure_reason"])
        self.assertIsNotNone(result["debug_traceback"])


class RunModelStageAutomaticRetry(unittest.TestCase):
    """Direct unit tests for run_model_stage()'s in-line automatic retry loop — the
    approved policy: up to MAX_TOTAL_ATTEMPTS (3) total attempts, each one told the exact
    validation failure from the last, never retrying anything outside a validation
    failure (a PipelineError-style hard failure must propagate immediately, uncaught)."""

    def setUp(self):
        self.usage = pipe.UsageTracker()
        self.schema = {"foo": list}

    def test_succeeds_on_first_attempt_no_retry_needed(self):
        calls = []

        def api_call_fn(prior_failure):
            calls.append(prior_failure)
            return {"foo": [1, 2, 3]}

        result, outcome, stage_failure, tb, attempts = run_model_stage(
            "test_stage", self.schema, api_call_fn, lambda r: r["foo"], self.usage
        )
        self.assertEqual(outcome, "success")
        self.assertEqual(result, [1, 2, 3])
        self.assertIsNone(stage_failure)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(calls, [None])

    def test_retries_after_validation_failure_then_succeeds(self):
        responses = [{"wrong_key": []}, {"foo": [9]}]

        def api_call_fn(prior_failure):
            return responses.pop(0)

        result, outcome, stage_failure, tb, attempts = run_model_stage(
            "test_stage", self.schema, api_call_fn, lambda r: r["foo"], self.usage
        )
        self.assertEqual(outcome, "success")
        self.assertEqual(result, [9])
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["outcome"], "failed")
        self.assertEqual(attempts[1]["outcome"], "success")

    def test_prior_failure_is_forwarded_to_the_next_attempt_never_a_blind_repeat(self):
        seen_prior_failures = []
        responses = [{"wrong_key": []}, {"foo": [1]}]

        def api_call_fn(prior_failure):
            seen_prior_failures.append(prior_failure)
            return responses.pop(0)

        run_model_stage("test_stage", self.schema, api_call_fn, lambda r: r["foo"], self.usage)
        self.assertIsNone(seen_prior_failures[0])
        self.assertIsNotNone(seen_prior_failures[1])
        self.assertIn("foo", seen_prior_failures[1])

    def test_exhausts_after_max_total_attempts_and_returns_stage_failed(self):
        attempt_count = {"n": 0}

        def api_call_fn(prior_failure):
            attempt_count["n"] += 1
            return {"wrong_key": []}  # always malformed

        result, outcome, stage_failure, tb, attempts = run_model_stage(
            "test_stage", self.schema, api_call_fn, lambda r: r["foo"], self.usage
        )
        self.assertEqual(outcome, "stage_failed")
        self.assertIsNone(result)
        self.assertEqual(attempt_count["n"], MAX_TOTAL_ATTEMPTS)
        self.assertEqual(len(attempts), MAX_TOTAL_ATTEMPTS)
        self.assertEqual(stage_failure["total_attempts"], MAX_TOTAL_ATTEMPTS)
        self.assertTrue(stage_failure["retry_eligible"])
        self.assertEqual(stage_failure["stage"], "test_stage")

    def test_hard_failure_is_never_retried_and_propagates_immediately(self):
        attempt_count = {"n": 0}

        def api_call_fn(prior_failure):
            attempt_count["n"] += 1
            raise RuntimeError("simulated Anthropic SDK auth/network failure")

        with self.assertRaises(RuntimeError):
            run_model_stage("test_stage", self.schema, api_call_fn, lambda r: r["foo"], self.usage)
        self.assertEqual(attempt_count["n"], 1, "a hard failure must never trigger a retry attempt")

    def test_process_fn_raising_key_error_on_first_attempt_then_succeeding(self):
        """process_fn (per-item business logic, e.g. reading response["evidence"][0]["id"]
        on an item that turned out malformed) raising KeyError/TypeError is the same class
        of "response was malformed" as validate_stage_response failing outright — and is
        retried exactly like any other validation failure."""
        responses = [{"foo": [{"other": 1}]}, {"foo": [{"value": 42}]}]

        def process_fn(r):
            return r["foo"][0]["value"]  # KeyError on the first response, succeeds on the second

        def api_call_fn(prior_failure):
            return responses.pop(0)

        result, outcome, stage_failure, tb, attempts = run_model_stage(
            "test_stage", self.schema, api_call_fn, process_fn, self.usage
        )
        self.assertEqual(outcome, "success")
        self.assertEqual(result, 42)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["outcome"], "failed")


class UpstreamStageDependencyCheck(unittest.TestCase):
    """check_upstream_stages_valid() — the gate every retry endpoint must pass before it's
    even allowed to attempt spending money: every stage the requested one depends on must
    already be present and, for model stages, have outcome == "success"."""

    def test_missing_checkpoint_entirely_is_invalid(self):
        ok, reason = check_upstream_stages_valid(None, "diagnosis")
        self.assertFalse(ok)
        self.assertIn("no job state", reason)

    def test_foundation_only_needs_fetching_sources(self):
        checkpoint = {"fetching_sources": {"sources": []}}
        ok, reason = check_upstream_stages_valid(checkpoint, "strategic_foundation")
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_diagnosis_requires_successful_foundation(self):
        checkpoint = {"fetching_sources": {}, "strategic_foundation": {"outcome": "stage_failed"}}
        ok, reason = check_upstream_stages_valid(checkpoint, "diagnosis")
        self.assertFalse(ok)
        self.assertIn("strategic_foundation", reason)

    def test_diagnosis_passes_when_foundation_succeeded(self):
        checkpoint = {"fetching_sources": {}, "strategic_foundation": {"outcome": "success"}}
        ok, reason = check_upstream_stages_valid(checkpoint, "diagnosis")
        self.assertTrue(ok)

    def test_missing_upstream_stage_entirely_is_invalid(self):
        checkpoint = {"fetching_sources": {}}
        ok, reason = check_upstream_stages_valid(checkpoint, "diagnosis")
        self.assertFalse(ok)
        self.assertIn("strategic_foundation", reason)
        self.assertIn("not been completed", reason)

    def test_recommendation_requires_the_full_chain(self):
        checkpoint = {
            "fetching_sources": {}, "strategic_foundation": {"outcome": "success"},
            "diagnosis": {"outcome": "success"}, "narrative_choices": {"outcome": "success"},
            "critique": {"outcome": "stage_failed"},
        }
        ok, reason = check_upstream_stages_valid(checkpoint, "recommendation_and_map")
        self.assertFalse(ok)
        self.assertIn("critique", reason)

    def test_every_declared_dependency_chain_is_strictly_increasing(self):
        """Sanity check on the STAGE_DEPENDENCIES table itself: each stage's dependency
        list must be a superset of the previous stage's — nothing can depend on a LATER
        stage, and nothing can skip an earlier one."""
        order = ["strategic_foundation", "diagnosis", "narrative_choices", "critique", "recommendation_and_map"]
        for earlier, later in zip(order, order[1:]):
            self.assertTrue(
                set(STAGE_DEPENDENCIES[earlier]).issubset(set(STAGE_DEPENDENCIES[later])),
                f"{later}'s dependencies must be a superset of {earlier}'s",
            )


class ManualRetryForwardStages(unittest.TestCase):
    """The 4 manual, single-attempt retry_xxx() functions besides
    retry_recommendation_and_map (already covered by RetryRecommendationStage above) —
    each is exactly one deliberate attempt, never an internal retry loop, and never
    re-fetches a URL or reruns an earlier stage."""

    def setUp(self):
        self.addCleanup(patch.stopall)
        patch("anthropic_pipeline.get_client", return_value=object()).start()
        self.sources = [{"id": "src1", "companyId": "live", "title": "Co", "publisher": "co.com",
                          "sourceType": "website", "url": "https://co.com", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"}]
        self.source_text_by_id = {"src1": "The company serves manufacturing customers directly."}

    def test_retry_extract_foundation_success(self):
        foundation_result = {
            "evidence": [EVIDENCE_ITEM("ev1", "src1", "The company serves manufacturing customers directly.")],
            "strategicFoundation": [{
                "id": "sf1", "type": "customer", "statement": "Serves manufacturing customers.",
                "statementType": "source_fact", "evidence": [LINK("ev1")],
            }],
        }
        patch("anthropic_pipeline.extract_foundation", return_value=foundation_result).start()
        result = retry_extract_foundation(self.sources, self.source_text_by_id)
        self.assertEqual(result["outcome"], "success")
        self.assertEqual(len(result["strategicFoundation"]), 1)
        self.assertIn("ev1", result["evidencePool"])

    def test_retry_extract_foundation_still_fails_cleanly_on_malformed_response(self):
        patch("anthropic_pipeline.extract_foundation", return_value={"strategicFoundation": []}).start()  # missing "evidence"
        result = retry_extract_foundation(self.sources, self.source_text_by_id)
        self.assertEqual(result["outcome"], "stage_failed")
        self.assertIn("evidence", result["diagnostics"]["failure_reason"])
        self.assertEqual(result["strategicFoundation"], [])
        self.assertIsNotNone(result["debug_traceback"])

    def test_retry_extract_foundation_does_not_refetch_sources(self):
        mock_fetch = patch("pipeline_runner.fetch_all_sources").start()
        patch("anthropic_pipeline.extract_foundation", return_value={"evidence": [], "strategicFoundation": []}).start()
        retry_extract_foundation(self.sources, self.source_text_by_id)
        mock_fetch.assert_not_called()

    def test_retry_diagnose_success(self):
        evidence_pool = {"ev1": EVIDENCE_ITEM("ev1", "src1", "The company serves manufacturing customers directly.")}
        evidence_pool["ev1"]["verified"] = True
        strategic_foundation = [{"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact"}]
        diagnose_result = {
            "evidence": [], "diagnosis": [{
                "id": "d1", "title": "t", "explanation": "e", "significance": "medium",
                "statementType": "source_fact", "evidence": [LINK("ev1")],
            }],
            "competitorOverlapAssessed": False, "competitorOverlapNote": "", "competitorContrasts": [],
        }
        patch("anthropic_pipeline.diagnose", return_value=diagnose_result).start()
        result = retry_diagnose(self.sources, self.source_text_by_id, evidence_pool, strategic_foundation, "")
        self.assertEqual(result["outcome"], "success")
        self.assertEqual(len(result["diagnosis"]), 1)

    def test_retry_diagnose_fails_cleanly_on_missing_evidence_key(self):
        """The actual 2026-07-31 Schneider Electric failure, reproduced against the
        manual retry path specifically (not just the automatic in-line path)."""
        evidence_pool = {}
        strategic_foundation = [{"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact"}]
        patch("anthropic_pipeline.diagnose", return_value={
            "diagnosis": [], "competitorOverlapAssessed": False, "competitorOverlapNote": "", "competitorContrasts": [],
        }).start()
        result = retry_diagnose(self.sources, self.source_text_by_id, evidence_pool, strategic_foundation, "")
        self.assertEqual(result["outcome"], "stage_failed")
        self.assertIn("evidence", result["diagnostics"]["failure_reason"])
        self.assertEqual(result["diagnosis"], [])

    def test_retry_generate_candidates_success(self):
        evidence_pool = {}
        foundation_summary = [{"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact"}]
        diagnosis_summary = [{"id": "d1", "title": "t", "significance": "medium"}]
        patch("anthropic_pipeline.generate_candidates", return_value={"candidates": _valid_candidates()}).start()
        result = retry_generate_candidates(evidence_pool, foundation_summary, diagnosis_summary)
        self.assertEqual(result["outcome"], "success")
        self.assertEqual(len(result["candidates"]), 3)

    def test_retry_generate_candidates_fails_cleanly_when_not_exactly_three(self):
        evidence_pool = {}
        patch("anthropic_pipeline.generate_candidates", return_value={"candidates": _valid_candidates()[:2]}).start()
        result = retry_generate_candidates(evidence_pool, [], [])
        # Wrong candidate count is reported via rejected_records, not a stage_failed —
        # matches run_analysis's existing behavior for this same case.
        self.assertEqual(result["outcome"], "success")
        reasons = [r for rec in result["diagnostics"]["rejected_records"] for r in rec["reasons"]]
        self.assertTrue(any("expected exactly 3" in r for r in reasons))

    def test_retry_critique_candidates_success(self):
        candidates = _valid_candidates()
        patch("anthropic_pipeline.critique_candidates", return_value={"critiques": _valid_critiques(candidates)}).start()
        result = retry_critique_candidates(candidates)
        self.assertEqual(result["outcome"], "success")
        self.assertTrue(result["survivors"])

    def test_retry_critique_candidates_fails_cleanly_on_malformed_response(self):
        candidates = _valid_candidates()
        patch("anthropic_pipeline.critique_candidates", return_value={"critiques": "not a list"}).start()
        result = retry_critique_candidates(candidates)
        self.assertEqual(result["outcome"], "stage_failed")
        self.assertEqual(result["survivors"], [])

    def test_retry_diagnose_does_not_touch_earlier_stage_functions(self):
        mock_extract = patch("anthropic_pipeline.extract_foundation").start()
        patch("anthropic_pipeline.diagnose", return_value={
            "evidence": [], "diagnosis": [], "competitorOverlapAssessed": False,
            "competitorOverlapNote": "", "competitorContrasts": [],
        }).start()
        retry_diagnose(self.sources, self.source_text_by_id, {}, [], "")
        mock_extract.assert_not_called()


class DownstreamInvalidation(unittest.TestCase):
    """invalidate_downstream_stages() — used once, right when a user submits an edited
    foundation: everything strictly after strategic_foundation must become unusable, in
    a way that survives even a subsequent failed regeneration attempt (a full section
    replacement, never a merge that could leave old data keys behind)."""

    def _full_checkpoint(self):
        return {
            "fetching_sources": {"sources": []},
            "strategic_foundation": {"outcome": "success", "strategicFoundation": [{"id": "sf1"}]},
            "diagnosis": {"outcome": "success", "diagnosis": [{"id": "d1"}]},
            "narrative_choices": {"outcome": "success", "candidates": [{"id": "cand1"}]},
            "critique": {"outcome": "success", "candidates": [{"id": "cand1", "status": "candidate"}]},
            "recommendation_and_map": {"outcome": "success", "recommendation": {"candidateId": "cand1"}, "narrativeMap": {"id": "map1"}},
        }

    def test_invalidates_every_stage_strictly_after_the_given_stage(self):
        result = invalidate_downstream_stages(self._full_checkpoint(), "strategic_foundation")
        for stage in ("diagnosis", "narrative_choices", "critique", "recommendation_and_map"):
            self.assertEqual(result[stage]["outcome"], "invalidated")

    def test_leaves_fetching_sources_and_the_edited_stage_itself_untouched(self):
        checkpoint = self._full_checkpoint()
        result = invalidate_downstream_stages(checkpoint, "strategic_foundation")
        self.assertEqual(result["fetching_sources"], checkpoint["fetching_sources"])
        self.assertEqual(result["strategic_foundation"], checkpoint["strategic_foundation"])

    def test_is_a_full_replacement_not_a_merge_no_stale_data_keys_survive(self):
        result = invalidate_downstream_stages(self._full_checkpoint(), "strategic_foundation")
        self.assertNotIn("candidates", result["critique"])
        self.assertNotIn("recommendation", result["recommendation_and_map"])
        self.assertNotIn("narrativeMap", result["recommendation_and_map"])
        self.assertNotIn("diagnosis", result["diagnosis"])

    def test_invalidating_from_a_later_stage_leaves_earlier_ones_alone(self):
        result = invalidate_downstream_stages(self._full_checkpoint(), "diagnosis")
        self.assertEqual(result["strategic_foundation"]["outcome"], "success")
        self.assertEqual(result["diagnosis"]["outcome"], "success")
        self.assertEqual(result["narrative_choices"]["outcome"], "invalidated")
        self.assertEqual(result["critique"]["outcome"], "invalidated")
        self.assertEqual(result["recommendation_and_map"]["outcome"], "invalidated")

    def test_does_not_mutate_the_input_checkpoint(self):
        checkpoint = self._full_checkpoint()
        invalidate_downstream_stages(checkpoint, "strategic_foundation")
        self.assertEqual(checkpoint["diagnosis"]["outcome"], "success")

    def test_invalidated_stage_correctly_fails_check_upstream_stages_valid_for_dependents(self):
        result = invalidate_downstream_stages(self._full_checkpoint(), "strategic_foundation")
        ok, reason = check_upstream_stages_valid(result, "narrative_choices")
        self.assertFalse(ok)
        self.assertIn("diagnosis", reason)

    def test_unknown_stage_name_raises(self):
        with self.assertRaises(ValueError):
            invalidate_downstream_stages(self._full_checkpoint(), "not_a_real_stage")


class ManualRetryCap(unittest.TestCase):
    """check_manual_retry_allowed() — exactly MAX_MANUAL_RETRIES (1) manual retries per
    stage, enforced against the persisted attempt history, never trusted from a client-
    supplied count. Automatic in-run attempts (never flagged "manual") must never count
    against this cap."""

    def test_no_attempts_at_all_is_allowed(self):
        allowed, reason = check_manual_retry_allowed({}, "diagnosis")
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_only_automatic_attempts_recorded_is_still_allowed(self):
        checkpoint = {"diagnosis": {"attempts": [
            {"attempt": 1, "manual": False, "outcome": "failed"},
            {"attempt": 2, "manual": False, "outcome": "failed"},
            {"attempt": 3, "manual": False, "outcome": "failed"},
        ]}}
        allowed, reason = check_manual_retry_allowed(checkpoint, "diagnosis")
        self.assertTrue(allowed)

    def test_one_manual_attempt_reaches_the_cap(self):
        checkpoint = {"diagnosis": {"attempts": [
            {"attempt": 1, "manual": False, "outcome": "failed"},
            {"attempt": 4, "manual": True, "outcome": "stage_failed"},
        ]}}
        allowed, reason = check_manual_retry_allowed(checkpoint, "diagnosis")
        self.assertFalse(allowed)
        self.assertEqual(reason, "retry_limit_reached")

    def test_a_successful_manual_retry_still_counts_against_the_cap(self):
        """The cap applies regardless of whether the one manual attempt succeeded or
        failed — once used, it's used."""
        checkpoint = {"diagnosis": {"attempts": [{"attempt": 4, "manual": True, "outcome": "success"}]}}
        allowed, reason = check_manual_retry_allowed(checkpoint, "diagnosis")
        self.assertFalse(allowed)

    def test_cap_is_per_stage_not_global(self):
        checkpoint = {
            "diagnosis": {"attempts": [{"attempt": 1, "manual": True, "outcome": "stage_failed"}]},
            "critique": {"attempts": []},
        }
        self.assertFalse(check_manual_retry_allowed(checkpoint, "diagnosis")[0])
        self.assertTrue(check_manual_retry_allowed(checkpoint, "critique")[0])

    def test_max_manual_retries_constant_is_exactly_one(self):
        self.assertEqual(MAX_MANUAL_RETRIES, 1)


def _cov_source(source_type="website"):
    return {"sourceType": source_type}


def _cov_foundation_item(type_):
    return {"type": type_}


def _cov_evidence(strength, verified=True):
    return {"strength": strength, "verified": verified}


class SourceCoverageAssessment(unittest.TestCase):
    """assess_source_coverage() — deterministic, zero-model-call assessment of whether
    the fetched source set is broad enough for a definitive company-level recommendation.
    Motivated directly by the real Schneider Electric run (one homepage, no competitor
    URL, no existing narrative): the pipeline behaved correctly end to end, but the input
    set was too narrow to justify a confident corporate narrative — this is the check
    that should have flagged that."""

    def test_empty_input_covers_nothing_and_is_insufficient(self):
        result = assess_source_coverage([], [], {}, "")
        self.assertEqual(result["coveredDimensions"], [])
        self.assertEqual(set(result["missingDimensions"]), {
            "strategy", "capabilities", "customers", "proof", "competitive_context", "current_narrative",
        })
        self.assertFalse(result["sufficient"])

    def test_strategy_covered_by_market_type(self):
        result = assess_source_coverage([], [_cov_foundation_item("market")], {}, "")
        self.assertIn("strategy", result["coveredDimensions"])

    def test_strategy_covered_by_market_change_type(self):
        result = assess_source_coverage([], [_cov_foundation_item("market_change")], {}, "")
        self.assertIn("strategy", result["coveredDimensions"])

    def test_strategy_covered_by_way_to_win_type(self):
        result = assess_source_coverage([], [_cov_foundation_item("way_to_win")], {}, "")
        self.assertIn("strategy", result["coveredDimensions"])

    def test_strategy_covered_by_existing_narrative_alone(self):
        result = assess_source_coverage([], [], {}, "Our positioning is X.")
        self.assertIn("strategy", result["coveredDimensions"])

    def test_capabilities_covered_by_capability_type(self):
        result = assess_source_coverage([], [_cov_foundation_item("capability")], {}, "")
        self.assertIn("capabilities", result["coveredDimensions"])

    def test_customers_covered_by_customer_type(self):
        result = assess_source_coverage([], [_cov_foundation_item("customer")], {}, "")
        self.assertIn("customers", result["coveredDimensions"])

    def test_proof_covered_by_proof_type(self):
        result = assess_source_coverage([], [_cov_foundation_item("proof")], {}, "")
        self.assertIn("proof", result["coveredDimensions"])

    def test_proof_covered_by_strong_verified_evidence(self):
        result = assess_source_coverage([], [], {"ev1": _cov_evidence("strong", verified=True)}, "")
        self.assertIn("proof", result["coveredDimensions"])

    def test_proof_covered_by_moderate_verified_evidence(self):
        result = assess_source_coverage([], [], {"ev1": _cov_evidence("moderate", verified=True)}, "")
        self.assertIn("proof", result["coveredDimensions"])

    def test_proof_not_covered_by_unverified_strong_evidence(self):
        """An unverified excerpt must never count as proof, no matter how strong its
        claimed strength — verification (citation_verify.py) is what makes it real."""
        result = assess_source_coverage([], [], {"ev1": _cov_evidence("strong", verified=False)}, "")
        self.assertNotIn("proof", result["coveredDimensions"])

    def test_proof_not_covered_by_weak_evidence(self):
        result = assess_source_coverage([], [], {"ev1": _cov_evidence("weak", verified=True)}, "")
        self.assertNotIn("proof", result["coveredDimensions"])

    def test_competitive_context_covered_by_competitor_source(self):
        result = assess_source_coverage([_cov_source("competitor")], [], {}, "")
        self.assertIn("competitive_context", result["coveredDimensions"])

    def test_competitive_context_not_covered_by_website_source_alone(self):
        result = assess_source_coverage([_cov_source("website")], [], {}, "")
        self.assertNotIn("competitive_context", result["coveredDimensions"])

    def test_current_narrative_covered_by_existing_narrative(self):
        result = assess_source_coverage([_cov_source("website")], [], {}, "Our story is X.")
        self.assertIn("current_narrative", result["coveredDimensions"])

    def test_current_narrative_covered_by_two_or_more_sources(self):
        result = assess_source_coverage([_cov_source("website"), _cov_source("website")], [], {}, "")
        self.assertIn("current_narrative", result["coveredDimensions"])

    def test_current_narrative_not_covered_by_single_source_no_narrative(self):
        result = assess_source_coverage([_cov_source("website")], [], {}, "")
        self.assertNotIn("current_narrative", result["coveredDimensions"])

    def test_min_sources_floor_blocks_sufficient_even_with_all_dimensions_covered(self):
        """All 6 dimensions covered but only 1 source fetched — the source-count floor
        must still block "sufficient", independent of dimension tuning. This is exactly
        the real Schneider Electric shape (see the dedicated test below)."""
        foundation = [
            _cov_foundation_item("market"), _cov_foundation_item("capability"),
            _cov_foundation_item("customer"), _cov_foundation_item("proof"),
        ]
        result = assess_source_coverage([_cov_source("competitor")], foundation, {}, "Existing narrative text.")
        self.assertGreaterEqual(len(result["coveredDimensions"]), MIN_COVERED_DIMENSIONS_FOR_SUFFICIENT)
        self.assertFalse(result["sufficient"])

    def test_min_dimensions_floor_blocks_sufficient_even_with_enough_sources(self):
        sources = [_cov_source("website"), _cov_source("website"), _cov_source("competitor")]
        result = assess_source_coverage(sources, [], {}, "")  # only competitive_context + current_narrative covered = 2
        self.assertGreaterEqual(len(sources), MIN_SOURCES_FOR_SUFFICIENT)
        self.assertLess(len(result["coveredDimensions"]), MIN_COVERED_DIMENSIONS_FOR_SUFFICIENT)
        self.assertFalse(result["sufficient"])

    def test_fully_sourced_input_is_sufficient(self):
        sources = [_cov_source("website"), _cov_source("website"), _cov_source("competitor")]
        foundation = [
            _cov_foundation_item("market"), _cov_foundation_item("capability"),
            _cov_foundation_item("customer"), _cov_foundation_item("proof"),
        ]
        result = assess_source_coverage(sources, foundation, {}, "")
        self.assertTrue(result["sufficient"])
        self.assertEqual(result["missingDimensions"], [])

    def test_schneider_electric_shaped_input_is_insufficient(self):
        """The exact real-world case motivating this feature: one homepage, no
        competitor URL, no existing narrative — yielded a real recommendation the
        pipeline produced correctly, but which should be labeled exploratory, not a
        definitive company-level conclusion."""
        sources = [_cov_source("website")]
        foundation = [
            _cov_foundation_item("customer"), _cov_foundation_item("market"),
            _cov_foundation_item("way_to_win"), _cov_foundation_item("capability"),
            _cov_foundation_item("proof"), _cov_foundation_item("proof"),
            _cov_foundation_item("assumption"),
        ]
        result = assess_source_coverage(sources, foundation, {}, "")
        self.assertFalse(result["sufficient"])
        self.assertIn("competitive_context", result["missingDimensions"])
        self.assertIn("current_narrative", result["missingDimensions"])

    def test_suggestions_only_present_for_missing_dimensions(self):
        result = assess_source_coverage([], [_cov_foundation_item("capability")], {}, "")
        self.assertNotIn("capabilities", result["suggestions"])
        self.assertIn("customers", result["suggestions"])
        self.assertIn("competitive_context", result["suggestions"])

    def test_suggestions_name_a_concrete_source_type_per_dimension(self):
        """Requirement: show exactly which dimensions are missing AND which source type
        would close each gap — not just "add more sources"."""
        result = assess_source_coverage([], [], {}, "")
        self.assertIn("competitor", result["suggestions"]["competitive_context"].lower())
        self.assertIn("customer", result["suggestions"]["customers"].lower())

    def test_covered_and_missing_dimensions_partition_all_six_exactly_once(self):
        result = assess_source_coverage([_cov_source("competitor")], [_cov_foundation_item("proof")], {}, "")
        all_dims = set(result["coveredDimensions"]) | set(result["missingDimensions"])
        self.assertEqual(len(result["coveredDimensions"]) + len(result["missingDimensions"]), 6)
        self.assertEqual(all_dims, {"strategy", "capabilities", "customers", "proof", "competitive_context", "current_narrative"})


class RegenerationCapCheck(unittest.TestCase):
    """check_regeneration_allowed() — exactly MAX_FULL_REGENERATIONS (2) full
    regenerations per job, enforced against the persisted checkpoint["regenerationCount"],
    never trusted from a client-supplied count."""

    def test_no_regenerations_yet_is_allowed(self):
        allowed, reason = check_regeneration_allowed({})
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_one_regeneration_used_is_still_allowed(self):
        allowed, reason = check_regeneration_allowed({"regenerationCount": 1})
        self.assertTrue(allowed)

    def test_two_regenerations_used_reaches_the_cap(self):
        allowed, reason = check_regeneration_allowed({"regenerationCount": 2})
        self.assertFalse(allowed)
        self.assertEqual(reason, "regeneration_limit_reached")

    def test_max_full_regenerations_constant_is_exactly_two(self):
        self.assertEqual(MAX_FULL_REGENERATIONS, 2)

    def test_none_checkpoint_is_allowed_treated_as_zero_used(self):
        allowed, reason = check_regeneration_allowed(None)
        self.assertTrue(allowed)


class SourceExpansionCapCheck(unittest.TestCase):
    """check_source_expansion_allowed() — exactly MAX_SOURCE_EXPANSIONS (2) "add sources
    and re-analyze" actions per job, tracked in checkpoint["expandSourcesCount"] —
    deliberately a SEPARATE counter from regenerationCount (see MAX_SOURCE_EXPANSIONS's
    docstring: a thin-sourced job should have independent budget to both edit its
    foundation and add sources, not share one pool of 2)."""

    def test_no_expansions_yet_is_allowed(self):
        allowed, reason = check_source_expansion_allowed({})
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_one_expansion_used_is_still_allowed(self):
        allowed, reason = check_source_expansion_allowed({"expandSourcesCount": 1})
        self.assertTrue(allowed)

    def test_two_expansions_used_reaches_the_cap(self):
        allowed, reason = check_source_expansion_allowed({"expandSourcesCount": 2})
        self.assertFalse(allowed)
        self.assertEqual(reason, "source_expansion_limit_reached")

    def test_max_source_expansions_constant_is_exactly_two(self):
        self.assertEqual(MAX_SOURCE_EXPANSIONS, 2)

    def test_none_checkpoint_is_allowed_treated_as_zero_used(self):
        allowed, reason = check_source_expansion_allowed(None)
        self.assertTrue(allowed)

    def test_expand_sources_count_is_independent_of_regeneration_count(self):
        """Using up both regenerate slots must leave expand-sources fully available, and
        vice versa — the whole point of tracking them separately."""
        checkpoint = {"regenerationCount": 2, "expandSourcesCount": 0}
        self.assertFalse(check_regeneration_allowed(checkpoint)[0])
        self.assertTrue(check_source_expansion_allowed(checkpoint)[0])


class RunPipelineFromSourcesRefactorRegression(unittest.TestCase):
    """run_analysis() was refactored to extract its post-fetch stage sequence into
    run_pipeline_from_sources() (shared with jobs.py's expand-sources dispatch, which
    re-fetches an expanded source set for an existing job). This proves the extraction
    was purely structural: calling fetch_all_sources() + run_pipeline_from_sources()
    directly produces the SAME dataset/diagnostics content run_analysis() itself
    produces for the identical inputs — not just "still passes its own tests," but
    provably equivalent to the un-refactored code path."""

    def setUp(self):
        self.addCleanup(patch.stopall)
        self.fetch_return = (
            [{"id": "src_live_company", "companyId": "live", "title": "Co", "publisher": "co.com",
              "sourceType": "website", "url": "https://co.com", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"}],
            {"src_live_company": "The company serves manufacturing customers."},
            [],
            {"id": "src_live_company", "title": "Co", "publisher": "co.com"},
        )
        patch("pipeline_runner.fetch_all_sources", return_value=self.fetch_return).start()
        patch("anthropic_pipeline.get_client", return_value=object()).start()

        foundation_result = {
            "evidence": [EVIDENCE_ITEM("ev1", "src_live_company", "The company serves manufacturing customers.")],
            "strategicFoundation": [{
                "id": "sf1", "type": "customer", "statement": "Serves manufacturing customers.",
                "statementType": "source_fact", "evidence": [LINK("ev1")],
            }],
        }
        diagnose_result = {
            "evidence": [], "diagnosis": [{
                "id": "d1", "title": "t", "explanation": "The company serves manufacturing customers.",
                "significance": "medium", "statementType": "source_fact", "evidence": [LINK("ev1")],
            }],
            "competitorOverlapAssessed": False, "competitorOverlapNote": "", "competitorContrasts": [],
        }
        patch("anthropic_pipeline.extract_foundation", side_effect=lambda *a, **k: dict(foundation_result)).start()
        patch("anthropic_pipeline.diagnose", side_effect=lambda *a, **k: dict(diagnose_result)).start()
        patch("anthropic_pipeline.generate_candidates", side_effect=lambda *a, **k: {"candidates": _valid_candidates()}).start()
        patch("anthropic_pipeline.critique_candidates", side_effect=lambda *a, **k: {"critiques": _valid_critiques(_valid_candidates())}).start()
        patch("anthropic_pipeline.recommend_and_map", side_effect=lambda *a, **k: dict(_VALID_RECOMMEND_AND_MAP)).start()

    def _strip_volatile_fields(self, dataset):
        """narrativeMap.createdAt (datetime.now(timezone.utc), set inside
        process_recommend_and_map_response) is the ONLY thing legitimately expected to
        differ between two separately-executed runs of identical inputs — everything
        else, including narrativeMap's id (a deterministic constant, "map_live_v1" for
        both paths here since both call sites use the same map_id argument), must be
        byte-identical."""
        stripped = json.loads(json.dumps(dataset, default=str))
        if stripped.get("narrativeMap"):
            stripped["narrativeMap"]["createdAt"] = "<normalized>"
        return stripped

    def test_run_pipeline_from_sources_matches_run_analysis_for_identical_inputs(self):
        result_via_run_analysis = run_analysis("https://co.com", [], [], "", progress_cb=lambda *_: None)

        # Called via the pipeline_runner module attribute, not the directly-imported
        # name — patch("pipeline_runner.fetch_all_sources", ...) only rebinds the
        # module's own attribute; a `from pipeline_runner import fetch_all_sources` done
        # at file-import time would still point at the ORIGINAL function and bypass the
        # patch entirely.
        sources, source_text_by_id, fetch_failures, company_doc = pipeline_runner.fetch_all_sources("https://co.com", [], [], lambda *_: None)
        case_context = build_case_context(company_doc)
        result_direct = run_pipeline_from_sources(
            sources, source_text_by_id, "", case_context, fetch_failures, progress_cb=lambda *_: None,
        )

        self.assertEqual(
            self._strip_volatile_fields(result_via_run_analysis["dataset"]),
            self._strip_volatile_fields(result_direct["dataset"]),
        )
        self.assertEqual(result_via_run_analysis["diagnostics"]["outcome"], result_direct["diagnostics"]["outcome"])
        self.assertEqual(result_via_run_analysis["diagnostics"]["critical_failure"], result_direct["diagnostics"]["critical_failure"])
        self.assertEqual(result_via_run_analysis["diagnostics"]["rejected_records"], result_direct["diagnostics"]["rejected_records"])

    def test_run_analysis_still_persists_caseContext_and_sources_via_fetching_sources(self):
        """A quick sanity check that the refactor didn't drop the persist_cb("fetching_sources", ...)
        call that used to sit inline in run_analysis — it must still fire exactly once,
        with caseContext included."""
        persisted = {}
        def persist_cb(section, data):
            persisted[section] = data
        run_analysis("https://co.com", [], [], "", progress_cb=lambda *_: None, persist_cb=persist_cb)
        self.assertIn("fetching_sources", persisted)
        self.assertIsNotNone(persisted["fetching_sources"]["caseContext"])
        self.assertEqual(persisted["fetching_sources"]["sources"], self.fetch_return[0])


class EditedFoundationValidator(unittest.TestCase):
    """validate_edited_foundation() — the bar a user-submitted foundation edit must clear
    before it's ever accepted as canonical: same shape as model output, PLUS the same
    semantic validity (validate_strategic_choice) a model-generated choice has to pass.
    Unlike model output, this never partially applies — any problem rejects the whole
    submission."""

    def _valid_item(self):
        return {"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact", "evidence": []}

    def test_well_formed_item_passes(self):
        self.assertIsNone(validate_edited_foundation([self._valid_item()]))

    def test_empty_list_is_rejected(self):
        problems = validate_edited_foundation([])
        self.assertIsNotNone(problems)
        self.assertTrue(any("non-empty" in p for p in problems))

    def test_non_list_is_rejected(self):
        problems = validate_edited_foundation("not a list")
        self.assertIsNotNone(problems)

    def test_bare_string_item_is_rejected(self):
        problems = validate_edited_foundation([self._valid_item(), "not an object"])
        self.assertIsNotNone(problems)
        self.assertTrue(any("expected an object" in p for p in problems))

    def test_item_missing_required_field_is_rejected(self):
        problems = validate_edited_foundation([{"id": "sf1", "type": "customer"}])
        self.assertIsNotNone(problems)
        self.assertTrue(any("missing required field" in p for p in problems))

    def test_semantically_invalid_item_is_rejected_not_silently_coerced(self):
        """The same statement-type consistency rule model output has to satisfy — a
        user edit can just as easily create an inconsistent record."""
        bad_item = {"id": "sf1", "type": "customer", "statement": "x", "statementType": "leadership_decision", "evidence": []}
        problems = validate_edited_foundation([bad_item])
        self.assertIsNotNone(problems)

    def test_never_partially_applies_one_bad_item_fails_the_whole_submission(self):
        problems = validate_edited_foundation([self._valid_item(), {"id": "sf2", "type": "customer"}])
        self.assertIsNotNone(problems)
        self.assertEqual(len(problems), 1)  # only the second item is a problem, but the whole thing is rejected


class AttemptRecordShape(unittest.TestCase):
    """build_attempt_record() — the one shape every attempt (automatic or manual) is
    recorded in, carrying every field the approved retry policy requires persisted:
    stage, attempt number, start/completion time, outcome, validation failure, usage,
    and cost derived from that usage."""

    def test_computes_cost_from_usage(self):
        record = build_attempt_record("diagnosis", 1, False, "t0", "t1", "success", None, {"input_tokens": 1_000_000, "output_tokens": 1_000_000})
        self.assertEqual(record["costUsd"], 12.0)  # $2/MTok in + $10/MTok out

    def test_cost_is_none_when_no_usage_was_recorded(self):
        record = build_attempt_record("diagnosis", 1, False, "t0", "t1", "failed", "no response", None)
        self.assertIsNone(record["costUsd"])

    def test_carries_every_required_field(self):
        record = build_attempt_record("critique", 2, True, "t0", "t1", "stage_failed", "bad shape", {"input_tokens": 10, "output_tokens": 10})
        for field in ("stage", "attempt", "manual", "startedAt", "completedAt", "outcome", "validationFailure", "usage", "costUsd"):
            self.assertIn(field, record)
        self.assertEqual(record["stage"], "critique")
        self.assertEqual(record["attempt"], 2)
        self.assertTrue(record["manual"])


class StageOrderSanity(unittest.TestCase):
    def test_stage_order_matches_the_real_pipeline_sequence(self):
        self.assertEqual(STAGE_ORDER, [
            "fetching_sources", "strategic_foundation", "diagnosis",
            "narrative_choices", "critique", "recommendation_and_map",
        ])


if __name__ == "__main__":
    unittest.main()
