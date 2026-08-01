// Canonical candidate/recommendation state adapter (governing spec Phase 1: "one
// canonical persisted state for candidates and recommendation outcomes, then make every
// relevant screen read that same state").
//
// Three shapes of raw data reach this module, none of which any screen component should
// ever see directly:
//   - Live case, schema v2: candidate.status is already "pending"/"viable"/"rejected",
//     gateResults/rejectionReasons already present, dataset.recommendation is already the
//     canonical {outcome, selectedCandidateId, failureReason, missingEvidence,
//     leadershipDecisions, createdAt, detail} object (backend/job_persistence.py migrates
//     any older on-disk checkpoint to this shape before jobs.py's /status ever returns it
//     — see migrate_checkpoint_v1_to_v2).
//   - Wix/HPS seeded cases (js/cases/wix-case-data.js, hps-case-data.js): hand-authored,
//     status is one of "candidate"/"recommended"/"rejected" (schemas.js's
//     NarrativeCandidate enum — that validator keeps checking the RAW seed value,
//     unchanged, since it runs at module load time, before anything here does), and
//     dataset.recommendation is the older flat content shape ({candidateId,
//     recommendedDecision, whyItWins, ...}) with no outcome/selectedCandidateId wrapper —
//     these seed files are never edited (explicit constraint), so this module normalizes
//     them at READ time instead.
//
// Every screen (NarrativeChoices, Recommendation, NarrativeMapView, WorkflowNav,
// EvidenceRoom) reaches this data only via service.getCandidates()/service.getRecommendation(),
// which already route through normalizeCandidates()/normalizeRecommendation() below
// (analysis-service.js and live-analysis-service.js both call in at exactly one place
// each) — no component recomputes viability itself; see NarrativeChoices.js, which used
// to derive "blocked"/"Recommended" independently via scoring.js's computeOverallScore
// and no longer does.

const CANONICAL_CANDIDATE_STATUSES = new Set(["pending", "viable", "rejected"]);
const LEGACY_CANDIDATE_STATUS_MAP = { candidate: "viable", recommended: "viable", rejected: "rejected" };

export function normalizeCandidateStatus(candidate) {
  if (!candidate) return candidate;
  if (CANONICAL_CANDIDATE_STATUSES.has(candidate.status)) {
    // Already canonical (live, schema v2) — gateResults/rejectionReasons already present.
    return candidate;
  }
  // Legacy Wix/HPS vocabulary, normalized here without ever touching the seed file.
  const status = LEGACY_CANDIDATE_STATUS_MAP[candidate.status] || candidate.status;
  return {
    ...candidate,
    status,
    gateResults: candidate.gateResults || [],
    rejectionReasons:
      candidate.rejectionReasons ||
      (status === "rejected"
        ? [{
            code: "rejected_pre_canonical_schema",
            gateId: null,
            explanation: "This candidate was rejected by a seeded demonstration case, which predates structured gate results.",
          }]
        : []),
  };
}

export function normalizeCandidates(candidates) {
  return (candidates || []).map(normalizeCandidateStatus);
}

// rawRecommendation: either the canonical live shape (has .outcome already), the legacy
// flat Wix/HPS content shape (no .outcome — {candidateId, recommendedDecision, ...}), or
// null/undefined (nothing to report — e.g. the stage genuinely hasn't run yet). Returns
// the ONE canonical shape every screen reads:
//   {outcome, selectedCandidateId, failureReason, missingEvidence, leadershipDecisions,
//    createdAt, detail, candidate}
// `candidate` is the resolved winning NarrativeCandidate object (already normalized),
// attached here so callers never need a second lookup — mirrors what both services
// already did before this module existed.
export function normalizeRecommendation(rawRecommendation, normalizedCandidates) {
  if (!rawRecommendation) return null;

  if (rawRecommendation.outcome) {
    // Already canonical (live, schema v2, any of the three outcomes).
    const candidate = (normalizedCandidates || []).find((c) => c.id === rawRecommendation.selectedCandidateId) || null;
    return { ...rawRecommendation, candidate };
  }

  // Legacy flat content shape (Wix/HPS) — wrapped into the canonical shape without
  // altering a single value inside it. Wix/HPS's own decisionAgent (analysis-service.js)
  // already guarantees exactly one "recommended" candidate exists whenever this runs, so
  // outcome is always "success" here — this path never produces no_candidate_passed or
  // stage_failed, matching Wix/HPS's actual (unchanged) behavior.
  const { candidateId, missingEvidence, ...detail } = rawRecommendation;
  const candidate = (normalizedCandidates || []).find((c) => c.id === candidateId) || null;
  return {
    outcome: "success",
    selectedCandidateId: candidateId,
    failureReason: null,
    missingEvidence: missingEvidence || [],
    leadershipDecisions: [],
    createdAt: null,
    detail,
    candidate,
  };
}
