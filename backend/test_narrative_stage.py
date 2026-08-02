"""Tests for the narrative-stage model added on top of the existing evidence pipeline:
schema_constants.NARRATIVE_STAGES, confidence.py's confidence/directionalCredibility split
and competitor-source exclusion, and pipeline_runner.py's narrativeStage validation,
companyAltitudeGate, and the direction-coverage check. Governing principle under test:
"directionally ambitious but temporally honest" — no claim maturity is inferred from a
StrategicChoice's `type`, evidence thresholds differ by declared stage, and market/
competitor evidence may support a direction claim but can never prove a company fact.

Run with: python3 -m unittest test_narrative_stage -v
"""
import os
import unittest

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-do-not-use-not-a-real-key")

import confidence
import pipeline_runner as pr
from schema_constants import NARRATIVE_STAGES, NARRATIVE_STAGE_LABELS, NARRATIVE_STAGE_WORDING_GUIDANCE


class NarrativeStageConstants(unittest.TestCase):
    def test_five_stages_exactly(self):
        self.assertEqual(NARRATIVE_STAGES, [
            "proven_today", "emerging", "in_build", "strategic_direction", "aspiration_pending_leadership",
        ])

    def test_every_stage_has_a_label_and_wording_guidance(self):
        self.assertEqual(set(NARRATIVE_STAGE_LABELS), set(NARRATIVE_STAGES))
        self.assertEqual(set(NARRATIVE_STAGE_WORDING_GUIDANCE), set(NARRATIVE_STAGES))


def _ev(strength="strong", from_competitor=False, source_id="s1"):
    return {"strength": strength, "sourceId": source_id, "fromCompetitorSource": from_competitor}


class ConfidenceExcludesCompetitorEvidence(unittest.TestCase):
    """Rule 9: market/competitor sources can support a direction claim but can never
    establish that the company itself possesses a capability or has achieved an outcome —
    confidence.py enforces this structurally, not just via prompt instruction."""

    def test_competitor_sourced_direct_link_never_raises_confidence(self):
        evidence_by_id = {"e1": _ev(from_competitor=True)}
        links = [{"evidenceId": "e1", "relevance": "direct"}]
        self.assertEqual(
            confidence.compute_confidence_from_links(links, evidence_by_id),
            confidence.NO_DIRECT_EVIDENCE_CONFIDENCE,
            "a competitor-sourced link mislabeled 'direct' must still floor to the no-evidence baseline",
        )

    def test_company_sourced_direct_link_does_raise_confidence(self):
        evidence_by_id = {"e1": _ev(from_competitor=False)}
        links = [{"evidenceId": "e1", "relevance": "direct"}]
        self.assertGreater(confidence.compute_confidence_from_links(links, evidence_by_id), confidence.NO_DIRECT_EVIDENCE_CONFIDENCE)

    def test_mixed_links_only_company_evidence_contributes(self):
        evidence_by_id = {"e1": _ev(from_competitor=False, source_id="s1"), "e2": _ev(from_competitor=True, source_id="s2")}
        links = [{"evidenceId": "e1", "relevance": "direct"}, {"evidenceId": "e2", "relevance": "direct"}]
        only_company = confidence.compute_confidence_from_links([links[0]], evidence_by_id)
        mixed = confidence.compute_confidence_from_links(links, evidence_by_id)
        self.assertEqual(only_company, mixed, "adding a competitor-sourced link must not change the result at all")


class DirectionalCredibility(unittest.TestCase):
    """A separate measure from confidence (never shown alongside it for the same claim —
    see labels.js) that DOES count context-relevance and competitor/market-sourced
    evidence, since real signal for a direction is a different question from proof of a
    company fact."""

    def test_competitor_sourced_evidence_contributes_to_directional_credibility(self):
        evidence_by_id = {"e1": _ev(from_competitor=True)}
        links = [{"evidenceId": "e1", "relevance": "direct"}]
        self.assertGreater(
            confidence.compute_directional_credibility(links, evidence_by_id),
            confidence.NO_DIRECTIONAL_SUPPORT,
            "market/competitor evidence is legitimate signal for a direction claim",
        )

    def test_context_relevance_contributes_to_directional_credibility_but_not_confidence(self):
        evidence_by_id = {"e1": _ev(from_competitor=False)}
        links = [{"evidenceId": "e1", "relevance": "context"}]
        self.assertEqual(confidence.compute_confidence_from_links(links, evidence_by_id), confidence.NO_DIRECT_EVIDENCE_CONFIDENCE)
        self.assertGreater(confidence.compute_directional_credibility(links, evidence_by_id), confidence.NO_DIRECTIONAL_SUPPORT)

    def test_conflicting_relevance_never_contributes_to_either_measure(self):
        evidence_by_id = {"e1": _ev(from_competitor=False)}
        links = [{"evidenceId": "e1", "relevance": "conflicting"}]
        self.assertEqual(confidence.compute_confidence_from_links(links, evidence_by_id), confidence.NO_DIRECT_EVIDENCE_CONFIDENCE)
        self.assertEqual(confidence.compute_directional_credibility(links, evidence_by_id), confidence.NO_DIRECTIONAL_SUPPORT)

    def test_directional_credibility_never_exceeds_its_own_cap(self):
        evidence_by_id = {"e1": _ev(strength="strong", from_competitor=False)}
        links = [{"evidenceId": "e1", "relevance": "direct"}]
        self.assertLessEqual(confidence.compute_directional_credibility(links, evidence_by_id), confidence.DIRECTIONAL_CREDIBILITY_CAP)

    def test_directional_credibility_cap_is_lower_than_confidence_ceiling(self):
        """A well-evidenced direction must never be shown as more certain than a well-
        evidenced fact — governing narrative-stage decision 2."""
        self.assertLess(confidence.DIRECTIONAL_CREDIBILITY_CAP, confidence.MAX_CONFIDENCE)


def _evidence_pool_item(eid, strength="strong", verified=True):
    return {"id": eid, "sourceId": "s1", "excerpt": "x", "paraphrase": "x", "evidenceType": "x", "strength": strength, "freshness": "current", "verified": verified}


class FoundationNarrativeStageValidation(unittest.TestCase):
    """narrativeStage is required for every non-unresolved StrategicChoice; never inferred
    from `type` if the model omits or invents an invalid value — rejected for
    regeneration, exactly like an invalid statementType already is."""

    def _process(self, choice_overrides):
        evidence_pool = {"ev1": _evidence_pool_item("ev1")}
        choice = {
            "id": "sc1", "type": "capability", "statement": "x", "statementType": "source_fact",
            "evidence": [{"evidenceId": "ev1", "relevance": "direct", "rationale": "x"}],
        }
        choice.update(choice_overrides)
        response = {"evidence": [], "strategicFoundation": [choice], "narrativeQuestion": "q?"}
        dropped, rejected, violations = [], [], []
        kept, _ = pr.process_foundation_response(response, evidence_pool, {"s1": "x"}, dropped, rejected, violations)
        return kept, rejected

    def test_valid_stage_is_kept(self):
        kept, rejected = self._process({"narrativeStage": "in_build"})
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["narrativeStage"], "in_build")
        self.assertEqual(rejected, [])

    def test_missing_stage_is_rejected(self):
        kept, rejected = self._process({})
        self.assertEqual(kept, [])
        self.assertTrue(rejected)

    def test_invalid_stage_value_is_rejected(self):
        kept, rejected = self._process({"narrativeStage": "not_a_real_stage"})
        self.assertEqual(kept, [])
        self.assertTrue(rejected)

    def test_unresolved_item_never_requires_a_stage(self):
        kept, rejected = self._process({"type": "unresolved", "statementType": "leadership_decision", "evidence": []})
        self.assertEqual(len(kept), 1)
        self.assertIsNone(kept[0]["narrativeStage"])
        self.assertEqual(rejected, [])

    def test_foundation_item_gets_both_confidence_and_directional_credibility(self):
        kept, _ = self._process({"narrativeStage": "strategic_direction"})
        self.assertIsInstance(kept[0]["confidence"], float)
        self.assertIsInstance(kept[0]["directionalCredibility"], float)


def _make_candidate(cid, stages):
    return {
        "id": cid, "name": cid, "oneSentenceStory": "x",
        "sevenParts": {k: "x" for k in ["context", "tension", "belief", "role", "value", "proof", "direction"]},
        "strategicLogic": ["x"], "customerRelevance": "x", "differentiation": "x",
        "tradeoffs": ["x"], "risks": ["x"], "claims": [],
        "narrativeStages": [{"stage": s, "statement": "x", "evidence": []} for s in stages],
    }


class DirectionCoverageCheck(unittest.TestCase):
    """Structural check (not a generic 'ambition score'): when the foundation shows
    credible evidence of movement, candidate generation must include at least one
    company-level direction story — never silently return three current-state-only
    reflections."""

    def test_raises_when_foundation_shows_movement_but_all_candidates_are_current_state_only(self):
        foundation = [{"type": "way_to_win", "narrativeStage": "strategic_direction"}]
        candidates = [_make_candidate("c1", ["proven_today"]), _make_candidate("c2", ["proven_today"]), _make_candidate("c3", ["proven_today"])]
        with self.assertRaises(pr.DirectionCoverageError):
            pr.check_direction_coverage(foundation, candidates)

    def test_does_not_raise_when_one_candidate_covers_direction(self):
        foundation = [{"type": "way_to_win", "narrativeStage": "strategic_direction"}]
        candidates = [_make_candidate("c1", ["proven_today"]), _make_candidate("c2", ["proven_today"]), _make_candidate("c3", ["in_build"])]
        pr.check_direction_coverage(foundation, candidates)  # must not raise

    def test_does_not_raise_when_foundation_shows_no_movement_at_all(self):
        foundation = [{"type": "customer", "narrativeStage": "proven_today"}]
        candidates = [_make_candidate("c1", ["proven_today"]), _make_candidate("c2", ["proven_today"]), _make_candidate("c3", ["proven_today"])]
        pr.check_direction_coverage(foundation, candidates)  # must not raise

    def test_emerging_stage_alone_also_counts_as_movement_evidence(self):
        foundation = [{"type": "market_change", "narrativeStage": "emerging"}]
        candidates = [_make_candidate("c1", ["proven_today"]), _make_candidate("c2", ["proven_today"]), _make_candidate("c3", ["proven_today"])]
        with self.assertRaises(pr.DirectionCoverageError):
            pr.check_direction_coverage(foundation, candidates)

    def test_unresolved_foundation_items_are_never_read_as_movement_evidence(self):
        """type=='unresolved' items have no narrativeStage of their own (None/absent) —
        must never accidentally satisfy the movement check."""
        foundation = [{"type": "unresolved", "narrativeStage": None}]
        candidates = [_make_candidate("c1", ["proven_today"]), _make_candidate("c2", ["proven_today"]), _make_candidate("c3", ["proven_today"])]
        pr.check_direction_coverage(foundation, candidates)  # must not raise -- no real movement evidence present


class CompanyAltitudeGate(unittest.TestCase):
    """A fourth critique gate (not a generic ambition score) — reuses the existing
    generic GATE_CRITERIA-driven machinery unchanged; only the criteria list grew."""

    def test_gate_criteria_includes_company_altitude(self):
        self.assertIn(("companyAltitudeGate", "Company altitude"), pr.GATE_CRITERIA)

    def test_failing_company_altitude_alone_rejects_an_otherwise_strong_candidate(self):
        gate = {"strategicFitGate": "meets", "differentiationGate": "meets", "evidenceSupportGate": "supported", "companyAltitudeGate": "fails"}
        scores, status, gate_results, rejection_reasons = pr.build_candidate_scores_and_status(gate)
        self.assertEqual(status, "rejected")
        self.assertEqual({r["gateId"] for r in rejection_reasons}, {"companyAltitudeGate"})

    def test_all_four_gates_meeting_produces_four_scores(self):
        gate = {"strategicFitGate": "meets", "differentiationGate": "meets", "evidenceSupportGate": "supported", "companyAltitudeGate": "meets"}
        scores, status, gate_results, _ = pr.build_candidate_scores_and_status(gate)
        self.assertEqual(len(gate_results), 4)
        self.assertIn("Company altitude", scores)
        self.assertEqual(status, "viable")


if __name__ == "__main__":
    unittest.main()
