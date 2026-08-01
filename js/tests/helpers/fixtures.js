// Hand-authored fixture literals mirroring the backend contract shapes proven in
// backend/test_analyze_endpoints.py's Phase2StateFixtureContracts (fixture builders
// _seed_success_job / _seed_stage_failed_two_viable_job / _seed_no_candidate_passed_job /
// _seed_partial_results_early_failure_job). Deliberately duplicated by hand rather than
// shared across languages -- these two suites are independent on purpose: the backend
// suite proves the JSON is correct, this one proves a screen given that exact JSON
// actually renders it correctly. Keep both in sync by hand when either shape changes.

function candidate(id, name, status, scores, extra = {}) {
  return {
    id, name, status, scores,
    oneSentenceStory: `${name}'s one-sentence story.`,
    sevenParts: { context: "x", tension: "x", belief: "x", role: "x", value: "x", proof: "x", direction: "x" },
    strategicLogic: ["Logic point one.", "Logic point two."],
    customerRelevance: "Relevant to customers because x.",
    differentiation: "Different from competitors because x.",
    tradeoffs: ["Trade-off one."],
    risks: ["Risk one."],
    criticFindings: ["Passes the strategic-fit check."],
    claims: [],
    gateResults: [],
    rejectionReasons: [],
    ...extra,
  };
}

// --- Fixture 1: success ----------------------------------------------------------------
export const FIXTURE_1_CANDIDATES = [
  candidate("cand1", "The Selected Direction", "viable", { "Strategic fit": 4, "Differentiation": 4, "Evidence strength": 4 }),
  candidate("cand2", "An Alternative Direction", "viable", { "Strategic fit": 4, "Differentiation": 3, "Evidence strength": 3 }),
  candidate("cand3", "A Rejected Direction", "rejected", { "Strategic fit": 1, "Differentiation": 3, "Evidence strength": 3 },
    { rejectionReasons: [{ code: "strategic_fit_failed", gateId: "strategicFitGate", explanation: 'Strategic fit assessed as "fails".' }] }),
];
export const FIXTURE_1_RECOMMENDATION = {
  outcome: "success", selectedCandidateId: "cand1", failureReason: null,
  missingEvidence: ["Needs more customer proof."], leadershipDecisions: ["Should we expand into adjacent markets?"],
  createdAt: "2026-01-01T00:00:00Z", candidate: FIXTURE_1_CANDIDATES[0],
  detail: {
    recommendedDecision: "Position around the selected direction.", whyItWins: "It wins because x.",
    whyCustomersCare: "Customers care because x.", whyCredible: "Credible because x.", howDifferent: "Different because x.",
    tradeoffs: [], whyOthersNotSelected: { cand2: "Broadly appealing but less differentiated.", cand3: "Fails the strategic-fit gate." },
  },
};

// --- Fixture 2: stage_failed, two viable ------------------------------------------------
export const FIXTURE_2_CANDIDATES = [
  candidate("cand1", "The Proven Specialist", "viable", { "Strategic fit": 4, "Differentiation": 4, "Evidence strength": 3 }),
  candidate("cand2", "The Emerging Platform", "viable", { "Strategic fit": 4, "Differentiation": 4, "Evidence strength": 3 }),
  candidate("cand3", "The Challenger", "rejected", { "Strategic fit": 3, "Differentiation": 3, "Evidence strength": 1 },
    { rejectionReasons: [{ code: "evidence_support_failed", gateId: "evidenceSupportGate", explanation: 'Evidence strength assessed as "unsupported".' }] }),
];
export const FIXTURE_2_RECOMMENDATION = {
  outcome: "stage_failed", selectedCandidateId: null,
  failureReason: 'recommendation_and_map response field "narrativeMap" must be dict, got str',
  missingEvidence: [], leadershipDecisions: [], createdAt: "2026-01-01T00:00:00Z", detail: null, candidate: null,
};

// --- Fixture 3: genuine no_candidate_passed ----------------------------------------------
export const FIXTURE_3_CANDIDATES = [
  candidate("cand1", "Direction One", "rejected", { "Strategic fit": 1, "Differentiation": 3, "Evidence strength": 3 },
    { rejectionReasons: [{ code: "strategic_fit_failed", gateId: "strategicFitGate", explanation: 'Strategic fit assessed as "fails".' }] }),
  candidate("cand2", "Direction Two", "rejected", { "Strategic fit": 3, "Differentiation": 1, "Evidence strength": 3 },
    { rejectionReasons: [{ code: "differentiation_failed", gateId: "differentiationGate", explanation: 'Differentiation assessed as "fails".' }] }),
  candidate("cand3", "Direction Three", "rejected", { "Strategic fit": 3, "Differentiation": 3, "Evidence strength": 1 },
    { rejectionReasons: [{ code: "evidence_support_failed", gateId: "evidenceSupportGate", explanation: 'Evidence strength assessed as "unsupported".' }] }),
];
export const FIXTURE_3_RECOMMENDATION = {
  outcome: "no_candidate_passed", selectedCandidateId: null, failureReason: null,
  missingEvidence: [], leadershipDecisions: [], createdAt: "2026-01-01T00:00:00Z", detail: null, candidate: null,
};

// --- Fixture 5: partial results, early failure (diagnosis failed, nothing reached after) --
export const FIXTURE_5_STRATEGIC_FOUNDATION = [
  { id: "sf1", type: "customer", statement: "Serves manufacturing customers.", statementType: "source_fact", evidence: [], confidence: 0.8, approvalStatus: "unreviewed" },
];
export const FIXTURE_5_CANDIDATES = [];
export const FIXTURE_5_RECOMMENDATION = null;

// --- Fixture 8: deliberately malformed optional fields -----------------------------------
export const FIXTURE_8_CANDIDATES = [
  candidate("cand1", "A Normal Candidate", "viable", { "Strategic fit": 4, "Differentiation": 4, "Evidence strength": 4 }),
  {
    // Every optional list field a real backend or seeded candidate always carries is
    // missing here, on purpose -- this is the adversarial case, not a real one.
    id: "cand2", name: "A Malformed Candidate", status: "viable",
    scores: { "Strategic fit": 3, "Differentiation": 3, "Evidence strength": 3 },
    oneSentenceStory: "A malformed candidate's one-sentence story.",
    sevenParts: { context: "x", tension: "x", belief: "x", role: "x", value: "x", proof: "x", direction: "x" },
    customerRelevance: "x", differentiation: "x",
    // strategicLogic, tradeoffs, risks, criticFindings, claims, gateResults,
    // rejectionReasons: all deliberately absent.
  },
];
export const FIXTURE_8_RECOMMENDATION = {
  outcome: "success", selectedCandidateId: "cand1", failureReason: null,
  missingEvidence: [], leadershipDecisions: [], createdAt: "2026-01-01T00:00:00Z", candidate: FIXTURE_8_CANDIDATES[0],
  detail: {
    recommendedDecision: "x", whyItWins: "x", whyCustomersCare: "x", whyCredible: "x", howDifferent: "x",
    tradeoffs: [], whyOthersNotSelected: { cand2: "x" },
  },
};

// --- Minimal supporting fixtures used across multiple test files -------------------------
export function stubEvidenceIndex() {
  return {
    allSourcesWithEvidence: () => [],
    getEvidence: () => null,
    getEvidenceWithSource: () => null,
  };
}

export const STUB_CASE_CONTEXT = {
  id: "live", selectorLabel: "Analyze a company", selectorDescription: "x",
  company: { name: "Acme", oneLiner: "" }, narrativeQuestion: "What should Acme be known for?",
};
