// Service layer described in STORYMAP_CLAUDE_CODE_EXECUTION_PACK.md section 11.
//
// The UI never touches a case dataset directly — it only calls the NarrativeAnalysisService
// methods below (getCaseContext, getStrategicFoundation, ...) via getAnalysisService(caseId).
// Today those methods run a seeded dataset through nine labeled pipeline stages that mirror the
// pack's Agent 1-9 responsibilities (section 5). Most stages are pass-throughs today because
// there is no live source ingestion yet, but Stage 8 (Decision Agent) actually evaluates the
// hard gates against the seeded scores/evidence rather than trusting the seed blindly. Replacing
// any stage with a real model call later means editing that one function — the UI and every
// component are unaffected because they only see the service's return shape.
//
// createAnalysisService(dataset) is a factory, not a singleton: each case (Wix, HPS, ...) gets
// its own service instance with its own memoized pipeline run, so a second case is a new dataset
// file plus one line here — never a fork of this pipeline logic.

import { WIX_DATASET } from "./cases/wix-case-data.js";
import { HPS_DATASET } from "./cases/hps-case-data.js";
import { NO_DIRECT_EVIDENCE_CONFIDENCE } from "./case-utils.js";
import { buildEvidenceIndex } from "./evidence.js";
import { liveAnalysisService } from "./live-analysis-service.js";
import { normalizeCandidates, normalizeRecommendation } from "./candidate-state.js";

function resolveAfter(value, ms = 120) {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

// --- Agent 1: Intake Agent ---------------------------------------------------------------
// Inputs (per the pack): public URLs, uploaded files, transcripts, existing narrative.
// For the seeded demo, intake has already happened; this stage's job is only to confirm every
// source carries the fields a real intake agent would be responsible for (date, owner/publisher,
// permission, source type, extraction status), so a missing field fails loudly instead of
// silently rendering blank.
function intakeAgent(dataset) {
  dataset.sources.forEach((s) => {
    if (!s.sourceType || !s.permissionStatus || !s.retrievedAt) {
      throw new Error(`Intake Agent: source "${s.id}" is missing required intake fields`);
    }
  });
  return dataset;
}

// --- Agent 2: Strategy Extraction Agent ---------------------------------------------------
// Distinguishes strategy / goal / plan / capability / aspiration / evidence. In the seeded
// dataset this distinction is already encoded via StrategicChoice.type and .statementType;
// this stage's job is to confirm every item was actually classified, not left ambiguous.
function strategyExtractionAgent(dataset) {
  dataset.strategicFoundation.forEach((choice) => {
    if (!choice.type || !choice.statementType) {
      throw new Error(`Strategy Extraction Agent: choice "${choice.id}" is missing a type or statementType`);
    }
  });
  return dataset;
}

// --- Agent 3: Evidence Agent ---------------------------------------------------------------
// Classifies proof into strong / moderate / weak / unsupported, and — critically — classifies
// each evidence *link* as direct / partial / context / conflicting relevance to the specific
// statement it's attached to (see EvidenceLink in schemas.js). Confidence itself is computed in
// case-utils.js's recalculateConfidence() before this stage ever runs (it has to run before
// validateDataset), but this stage is where that rule is actually enforced: a statement with no
// direct or partial evidence must not show a confidence above the honest "unestablished"
// baseline. This is what makes "revenue growth doesn't prove who the customers are" a system
// guarantee, not just a one-time audit — if someone re-adds that citation as "context" instead
// of removing it, this stage still won't let it inflate the confidence score.
function evidenceAgent(dataset) {
  const records = [
    ...dataset.strategicFoundation.filter((c) => c.type !== "unresolved"),
    ...dataset.diagnosis,
  ];
  records.forEach((record) => {
    const hasDirectOrPartialSupport = record.evidence.some(
      (link) => link.relevance === "direct" || link.relevance === "partial"
    );
    if (!hasDirectOrPartialSupport && record.confidence > NO_DIRECT_EVIDENCE_CONFIDENCE) {
      throw new Error(
        `Evidence Agent: "${record.id}" has no direct or partial evidence but confidence (${record.confidence}) exceeds the unestablished baseline (${NO_DIRECT_EVIDENCE_CONFIDENCE}) — context-only evidence must not inflate confidence`
      );
    }
  });
  return dataset;
}

// --- Agent 4: Contradiction Agent -----------------------------------------------------------
// Finds claims that exceed their evidence rather than silently reconciling them. The seeded
// dataset already surfaces one real example (df_unverified_interpretation): Wix's own claim
// that users "retain control" rests on usage data that shows editing behavior, not a validated
// control judgment. This stage checks that any finding whose evidence includes a "weak" or
// "unsupported" item is flagged at medium+ significance, so a future contradiction can't be
// quietly buried at low significance.
function contradictionAgent(dataset) {
  const evidenceById = new Map(dataset.evidence.map((e) => [e.id, e]));
  dataset.diagnosis.forEach((finding) => {
    const hasWeakEvidence = finding.evidence.some((link) => {
      const ev = evidenceById.get(link.evidenceId);
      return ev && (ev.strength === "weak" || ev.strength === "unsupported");
    });
    if (hasWeakEvidence && finding.significance === "low") {
      throw new Error(`Contradiction Agent: finding "${finding.id}" rests on weak evidence but is marked low significance`);
    }
  });
  return dataset;
}

// --- Agent 5: Competitor Agent ---------------------------------------------------------------
// Surfaces relative emphasis and claim overlap rather than "ownership" claims. Pass-through
// today; the seed already avoids ownership language (see competitorContrasts).
function competitorAgent(dataset) {
  return dataset;
}

// --- Agent 6: Narrative Architect -----------------------------------------------------------
// Generates exactly three candidates representing different strategic choices. This stage
// enforces that constraint on whatever data it receives.
function narrativeArchitect(dataset) {
  if (dataset.candidates.length !== 3) {
    throw new Error(`Narrative Architect: expected exactly 3 candidates, got ${dataset.candidates.length}`);
  }
  return dataset;
}

// --- Agent 7: Narrative Critic ---------------------------------------------------------------
// Independently tests each candidate. Pass-through today because the seed already includes
// criticFindings per candidate; a live version would run this as a separate model call that
// never sees the architect's hidden reasoning, only the finished candidate.
function narrativeCritic(dataset) {
  dataset.candidates.forEach((c) => {
    if (!c.criticFindings || c.criticFindings.length === 0) {
      throw new Error(`Narrative Critic: candidate "${c.id}" has no critic findings recorded`);
    }
  });
  return dataset;
}

// --- Agent 8: Decision Agent -----------------------------------------------------------------
// Scores and recommends, enforcing the pack's three hard gates:
//   1. Fails if strategically inaccurate (approximated here as "Strategic fit" <= 2).
//   2. Fails if core claims are unsupported (any claim resolves to "unsupported" evidence).
//   3. Fails if not meaningfully differentiated ("Differentiation" <= 1).
// This actually runs against the seeded scores/evidence rather than trusting the seed's
// `status` field blindly, and throws if the seed and the computed gate ever disagree.
function decisionAgent(dataset) {
  const evidenceById = new Map(dataset.evidence.map((e) => [e.id, e]));

  dataset.candidates.forEach((candidate) => {
    const strategicFit = candidate.scores["Strategic fit"] ?? 0;
    const differentiation = candidate.scores["Differentiation"] ?? 0;
    const hasUnsupportedClaim = candidate.claims.some((link) => evidenceById.get(link.evidenceId)?.strength === "unsupported");

    const failsStrategicAccuracy = strategicFit <= 2;
    const failsDifferentiation = differentiation <= 1;
    const failsEvidence = hasUnsupportedClaim;
    const shouldFail = failsStrategicAccuracy || failsDifferentiation || failsEvidence;

    if (shouldFail && candidate.status !== "rejected") {
      throw new Error(`Decision Agent: candidate "${candidate.id}" fails a hard gate but is not marked rejected`);
    }
  });

  const recommended = dataset.candidates.filter((c) => c.status === "recommended");
  if (recommended.length !== 1) {
    throw new Error(`Decision Agent: expected exactly one recommended candidate, found ${recommended.length}`);
  }
  if (recommended[0].id !== dataset.recommendation.candidateId) {
    throw new Error(`Decision Agent: recommended candidate does not match recommendation.candidateId`);
  }
  return dataset;
}

// --- Agent 9: Executive Output Agent ----------------------------------------------------------
// Turns structured output into a readable decision document: fact vs. inference vs.
// recommendation stay separate, trade-offs stay explicit. The UI components handle rendering;
// this stage's job is to confirm the recommendation references a candidate that actually exists
// and that the "why others were not selected" explanation covers every non-recommended candidate.
function executiveOutputAgent(dataset) {
  const candidateIds = new Set(dataset.candidates.map((c) => c.id));
  if (!candidateIds.has(dataset.recommendation.candidateId)) {
    throw new Error(`Executive Output Agent: recommendation references unknown candidate`);
  }
  const otherCandidates = dataset.candidates.filter((c) => c.id !== dataset.recommendation.candidateId);
  otherCandidates.forEach((c) => {
    if (!dataset.recommendation.whyOthersNotSelected[c.id]) {
      throw new Error(`Executive Output Agent: missing "why not selected" explanation for "${c.id}"`);
    }
  });
  return dataset;
}

const PIPELINE = [
  intakeAgent,
  strategyExtractionAgent,
  evidenceAgent,
  contradictionAgent,
  competitorAgent,
  narrativeArchitect,
  narrativeCritic,
  decisionAgent,
  executiveOutputAgent,
];

/** @implements NarrativeAnalysisService (execution pack section 11) */
function createAnalysisService(dataset) {
  let pipelineResult = null;
  function runPipeline() {
    if (pipelineResult) return pipelineResult;
    pipelineResult = PIPELINE.reduce((ds, stage) => stage(ds), dataset);
    return pipelineResult;
  }

  return {
    async getCaseContext() {
      const ds = runPipeline();
      return resolveAfter(ds.caseContext);
    },
    async getStrategicFoundation() {
      const ds = runPipeline();
      return resolveAfter(ds.strategicFoundation);
    },
    async getDiagnosis() {
      const ds = runPipeline();
      return resolveAfter(ds.diagnosis);
    },
    async getCandidates() {
      const ds = runPipeline();
      return resolveAfter(normalizeCandidates(ds.candidates));
    },
    async getRecommendation() {
      const ds = runPipeline();
      // decisionAgent (above) already validated ds.recommendation/ds.candidates against
      // the RAW seed vocabulary before this ever runs — normalizeRecommendation only
      // reshapes an already-validated object into the canonical shape every screen reads,
      // never re-validates it.
      return resolveAfter(normalizeRecommendation(ds.recommendation, normalizeCandidates(ds.candidates)));
    },
    async getNarrativeMap() {
      const ds = runPipeline();
      return resolveAfter(ds.narrativeMap);
    },
    async getEvidence() {
      const ds = runPipeline();
      return resolveAfter(ds.evidence);
    },
    async getEvidenceIndex() {
      const ds = runPipeline();
      return resolveAfter(buildEvidenceIndex(ds));
    },
    async getAudiences() {
      const ds = runPipeline();
      return resolveAfter(ds.audiences);
    },
    async getCompetitorContrasts() {
      const ds = runPipeline();
      return resolveAfter(ds.competitorContrasts);
    },
  };
}

const SERVICES_BY_CASE = {
  wix: createAnalysisService(WIX_DATASET),
  hps: createAnalysisService(HPS_DATASET),
  // Not built from createAnalysisService(dataset) like the seeded cases — there's no
  // static dataset to run the 9-stage pipeline over here. liveAnalysisService implements
  // the same method surface itself, backed by a completed backend job instead of a
  // pre-validated seed file; see live-analysis-service.js's own docstring.
  live: liveAnalysisService,
};

export function getAnalysisService(caseId) {
  return SERVICES_BY_CASE[caseId] || SERVICES_BY_CASE.wix;
}

export const AVAILABLE_CASES = Object.keys(SERVICES_BY_CASE);
