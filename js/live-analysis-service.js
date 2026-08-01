// Live counterpart to analysis-service.js's createAnalysisService() factory — but unlike
// Wix/HPS, there is no static dataset to build a service around at module load. This
// module exposes the exact same async method surface (getStrategicFoundation,
// getDiagnosis, ...) so every existing screen component works unmodified, but those
// methods only return real data once a backend job has completed; before that, callers
// must go through startAnalysis()/pollJob() from the new intake screen
// (components/AnalyzeCompany.js), which is the only place that calls those.
//
// State here is a small set of module-level variables, not part of state.js — this is
// deliberately kept OUT of the shared per-case state shape (approvals/edits/etc.) because
// none of it (job id, in-flight dataset, backend availability) applies to Wix/HPS or
// needs to persist across a reload the way workflow progress does.
import { buildEvidenceIndex } from "./evidence.js";
import { normalizeCandidates, normalizeRecommendation } from "./candidate-state.js";
import { API_CONTRACT_VERSION } from "./build-info.js";

// Derived from the browser's own address rather than hardcoded, so the same build works
// unmodified whether the page was opened as localhost, 127.0.0.1, or a LAN IP (e.g. a
// second device on the same Wi-Fi testing against a backend started with
// STORYMAP_HOST=0.0.0.0 — see backend/app.py's docstring). The backend always runs on
// the same host as the frontend in every supported setup, only the port differs.
const BACKEND_BASE = `http://${window.location.hostname}:5055`;
const POLL_INTERVAL_MS = 1500;
const HEALTH_CHECK_TIMEOUT_MS = 2500;

let currentDataset = null;
let currentDiagnostics = null;
let currentUsage = null;
let currentStageProgress = null;
let currentSourceCoverage = null;
let currentJobId = null;
// A client-side HINT only — mirrors backend/pipeline_runner.MAX_SOURCE_EXPANSIONS, but
// the server is the actual enforcer and is re-checked on every real request regardless
// (a page reload resets this to 0 even if the server-side count is nonzero; the UI must
// still handle a 429 gracefully rather than trust this alone — see expandSources()).
const MAX_SOURCE_EXPANSIONS_HINT = 2;
let sourceExpansionsUsed = 0;
// Remembered from the original startAnalysis() call so regenerateAnalysis() can resend
// the full original intake context (company/supporting/competitor URLs, existingNarrative)
// on every regenerate — a fix for a real bug where existingNarrative was silently dropped
// (hardcoded to "") on regeneration. The backend does NOT re-fetch any of these URLs on
// regenerate (it reuses the stored evidence pool — see pipeline_runner.regenerate_from);
// resending them here is about keeping the request a complete, self-describing "redo this
// analysis with an edit" rather than a partial one, not about triggering new fetches.
let originalIntake = null;

function withTimeout(promise, ms) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error("Request timed out")), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

async function backendFetch(path, options = {}) {
  // A FormData body (internal-document uploads — see startAnalysis) must NOT get an
  // explicit Content-Type: the browser sets its own multipart boundary parameter
  // automatically only when it's left unset; forcing application/json here would break
  // Flask's multipart parsing. Every existing caller passes a JSON string body (or none),
  // so this branch is a no-op for all of them — behavior is unchanged.
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  let response;
  try {
    response = await fetch(`${BACKEND_BASE}${path}`, {
      ...options,
      headers: isFormData ? options.headers : { "Content-Type": "application/json", ...options.headers },
    });
  } catch (err) {
    throw new Error(
      "Could not reach the local StoryMap backend. This flow requires running it separately " +
      "(python3 backend/app.py) — see README. " + (err instanceof Error ? err.message : String(err))
    );
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error || `Backend request failed (${response.status})`);
  }
  return body;
}

// Used by AnalyzeCompany.js to decide whether to show a live "submit" form or the
// graceful "local development only" notice — most relevantly true on the public GitHub
// Pages build, where no backend exists at all.
export async function checkBackendAvailable() {
  try {
    const res = await withTimeout(fetch(`${BACKEND_BASE}/api/health`), HEALTH_CHECK_TIMEOUT_MS);
    return res.ok;
  } catch {
    return false;
  }
}

// Detection only (governing spec's "stale frontend assets" gap, worst-detectability item
// in the whole FMEA table) — no UI is wired to this yet; that's deferred. Returns null if
// the backend can't be reached at all (nothing to compare against, not a mismatch), so a
// caller must treat null and {matches:false} differently rather than conflating
// "can't tell" with "definitely stale."
export async function checkApiContractVersion() {
  try {
    const res = await withTimeout(fetch(`${BACKEND_BASE}/api/health`), HEALTH_CHECK_TIMEOUT_MS);
    if (!res.ok) return null;
    const body = await res.json();
    const backendVersion = body.apiContractVersion;
    return { matches: backendVersion === API_CONTRACT_VERSION, backendVersion, frontendVersion: API_CONTRACT_VERSION };
  } catch {
    return null;
  }
}

// internalDocuments: optional array of {file: File, role: string} — AnalyzeCompany.js is
// the only caller that ever populates it. Empty/omitted takes the exact same JSON-body
// path this always used, byte-for-byte — only a non-empty list switches to a
// multipart/form-data body (files can't be JSON-encoded). The backend expects one JSON
// "meta" field (the same companyUrl/supportingUrls/competitorUrls/existingNarrative
// shape as the plain-JSON path, plus internalDocumentRoles index-matched to the file
// parts) alongside indexed internalDocument_0, internalDocument_1, ... file parts — see
// backend/app.py's analyze_company().
export async function startAnalysis({ companyUrl, supportingUrls, competitorUrls, existingNarrative, internalDocuments = [] }) {
  let jobId;
  if (internalDocuments.length) {
    const formData = new FormData();
    formData.append("meta", JSON.stringify({
      companyUrl, supportingUrls, competitorUrls, existingNarrative,
      internalDocumentRoles: internalDocuments.map((d) => d.role),
    }));
    internalDocuments.forEach((d, i) => formData.append(`internalDocument_${i}`, d.file, d.file.name));
    ({ jobId } = await backendFetch("/api/analyze-company", { method: "POST", body: formData }));
  } else {
    ({ jobId } = await backendFetch("/api/analyze-company", {
      method: "POST",
      body: JSON.stringify({ companyUrl, supportingUrls, competitorUrls, existingNarrative }),
    }));
  }
  currentJobId = jobId;
  originalIntake = { companyUrl, supportingUrls, competitorUrls, existingNarrative };
  return jobId;
}

// Polls until the job reaches a terminal state ("done" or "failed"), calling onStage with
// every intermediate status so the caller can render stage-by-stage progress. "done" with
// dataset === null is the valid zero-candidate-passed state, not a failure — see jobs.py.
//
// Captures dataset/diagnostics/usage/stageProgress on EITHER terminal state, not just
// "done" — the backend already preserves and returns whatever stages succeeded even when
// a later stage fails (its own "preserve earlier validated stages" principle), so a
// failed job's status response already carries real, useful partial data. Previously this
// was only captured on "done", which left partial results unreachable after a failure —
// the direct blocker for showing "view partial results" on a failed run.
export async function pollJob(jobId, onStage) {
  for (;;) {
    const status = await backendFetch(`/api/analyze-company/${jobId}/status`);
    if (onStage) onStage(status);
    if (status.dataset != null) currentDataset = status.dataset;
    if (status.diagnostics != null) currentDiagnostics = status.diagnostics;
    if (status.usage != null) currentUsage = status.usage;
    if (status.stageProgress != null) currentStageProgress = status.stageProgress;
    if (status.sourceCoverage != null) currentSourceCoverage = status.sourceCoverage;
    if (status.status === "done" || status.status === "failed") {
      return status;
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
}

// The ONLY trigger for downstream regeneration — never called on keystroke/edit alone.
// StrategicFoundation.js's "Regenerate analysis" button (live case only) calls this
// directly with the user's edited foundation array. Resends the FULL original intake
// context remembered from startAnalysis() — including existingNarrative, previously
// dropped here — even though the backend reuses the stored evidence pool rather than
// re-fetching any URL from it.
export async function regenerateAnalysis(editedFoundation, onStage) {
  if (!currentJobId || !originalIntake) {
    throw new Error("No prior analysis to regenerate from — start a new analysis first.");
  }
  const { jobId } = await backendFetch("/api/regenerate", {
    method: "POST",
    body: JSON.stringify({
      sourceJobId: currentJobId,
      companyUrl: originalIntake.companyUrl,
      supportingUrls: originalIntake.supportingUrls,
      competitorUrls: originalIntake.competitorUrls,
      existingNarrative: originalIntake.existingNarrative,
      editedFoundation,
    }),
  });
  // pollJob() (fixed above) now unconditionally captures status.dataset into
  // currentDataset on every poll — and the server's /status response is ALREADY the
  // complete, freshly-reconstructed dataset (caseContext/sources included, regardless of
  // regenerate never touching those sections) built straight from the checkpoint, not a
  // partial regenerate-only payload. A hand-merge here would only risk drifting from what
  // the server actually validated and stored (e.g. hard-coding strategicFoundation to
  // whatever was SENT rather than what was accepted), so none is needed.
  return pollJob(jobId, onStage);
}

// The backend's per-stage progress (stageProgress, STAGE_LABELS elsewhere in this app)
// uses the pipeline's internal stage names, but its retry endpoint's URL uses a
// different, shorter set of names (backend/app.py's RETRY_STAGE_TO_KIND) — translated
// here once so every caller only ever deals with the one naming scheme already used
// everywhere else in this app.
const RETRY_ENDPOINT_STAGE_NAMES = {
  strategic_foundation: "foundation",
  diagnosis: "diagnosis",
  narrative_choices: "candidates",
  critique: "critique",
  recommendation_and_map: "recommendation",
};

// Manually retries exactly one failed stage of the current job — one deliberate attempt,
// real API call, real cost (see backend/app.py's retry endpoint docstring: automatic
// in-line retries already ran up to 3 attempts before this was ever reachable). `stage`
// is one of this app's usual internal stage names (e.g. "diagnosis",
// "recommendation_and_map" — the same keys stageProgress uses). Retrying always targets
// the SAME canonical job_id — never a new one — so polling afterward is just pollJob on
// whatever id the endpoint returns (which is always currentJobId itself).
export async function retryStage(stage, onStage) {
  if (!currentJobId) {
    throw new Error("No prior analysis to retry — start a new analysis first.");
  }
  const endpointStage = RETRY_ENDPOINT_STAGE_NAMES[stage];
  if (!endpointStage) {
    throw new Error(`Unknown stage: ${stage}`);
  }
  const { jobId } = await backendFetch(`/api/analyze-company/${currentJobId}/retry/${endpointStage}`, {
    method: "POST",
  });
  return pollJob(jobId, onStage);
}

// Re-fetches with an EXPANDED source set and reruns the full pipeline from
// strategic_foundation onward — a genuinely different, more expensive action than
// retryStage/regenerateAnalysis (a real re-fetch, not just a rerun), capped at
// MAX_SOURCE_EXPANSIONS_HINT (2) per job, tracked independently of regenerate's own cap.
// supportingUrls/competitorUrls MUST be the FULL desired lists (same "complete resend"
// philosophy as regenerateAnalysis, and required by the backend, which treats the payload
// as authoritative, not additive) — callers (Recommendation.js's add-sources panel) are
// responsible for pre-populating a form with getCurrentSourceUrls() and submitting
// existing + new URLs together, never just the newly typed ones; this function does not
// merge anything on the caller's behalf.
//
// The backend invalidates every downstream stage the MOMENT the request is accepted —
// before the re-fetch or re-run even happens, let alone succeeds — so a failure here
// would otherwise leave currentDataset showing LESS than what was validated before (new
// sources, but empty foundation/diagnosis/recommendation). Snapshotting BOTH the dataset
// state AND the prior source list first, and rolling both back on failure, keeps "on
// failure, the prior validated analysis AND source list stay visible" true as a property
// of this module's exposed state, independent of what the backend's own checkpoint
// (correctly) now shows.
export async function expandSources(supportingUrls, competitorUrls, onStage) {
  if (!currentJobId || !originalIntake) {
    throw new Error("No prior analysis to add sources to — start a new analysis first.");
  }
  if (sourceExpansionsUsed >= MAX_SOURCE_EXPANSIONS_HINT) {
    throw new Error(`This analysis has already used its ${MAX_SOURCE_EXPANSIONS_HINT} allowed source expansions.`);
  }

  const snapshot = {
    dataset: currentDataset, diagnostics: currentDiagnostics, usage: currentUsage,
    stageProgress: currentStageProgress, sourceCoverage: currentSourceCoverage,
    supportingUrls: originalIntake.supportingUrls, competitorUrls: originalIntake.competitorUrls,
  };

  const { jobId } = await backendFetch(`/api/analyze-company/${currentJobId}/expand-sources`, {
    method: "POST",
    body: JSON.stringify({ companyUrl: originalIntake.companyUrl, supportingUrls, competitorUrls }),
  });
  // The request was ACCEPTED — the server's cap slot is now consumed regardless of how
  // the re-run eventually turns out (see backend/jobs.create_expand_sources_job: the
  // count increments synchronously, before any fetch or API call). This is the one piece
  // of state that is NEVER rolled back on failure — the slot really was spent.
  sourceExpansionsUsed += 1;

  const status = await pollJob(jobId, onStage);
  if (status.status === "failed") {
    currentDataset = snapshot.dataset;
    currentDiagnostics = snapshot.diagnostics;
    currentUsage = snapshot.usage;
    currentStageProgress = snapshot.stageProgress;
    currentSourceCoverage = snapshot.sourceCoverage;
    // The submitted source list was never actually validated end-to-end — restore the
    // prior one so a subsequent "add sources" attempt (if any expansions remain) starts
    // from what's REALLY still configured, not from a list the run never completed.
    originalIntake = { ...originalIntake, supportingUrls: snapshot.supportingUrls, competitorUrls: snapshot.competitorUrls };
  } else {
    originalIntake = { ...originalIntake, supportingUrls, competitorUrls };
  }
  return status;
}

// The CURRENT desired supporting/competitor URL lists — i.e. what's actually configured
// for this job right now (the original intake, or the last successfully-validated
// expansion's list if one happened). This is what any "add sources" UI must pre-populate
// its form with, so an edit is always additive-by-default (existing URLs visibly present
// and removable, never silently dropped by only sending what's newly typed).
export function getCurrentSourceUrls() {
  return {
    supportingUrls: originalIntake ? [...originalIntake.supportingUrls] : [],
    competitorUrls: originalIntake ? [...originalIntake.competitorUrls] : [],
  };
}

export function getSourceExpansionsUsed() {
  return sourceExpansionsUsed;
}

export function getMaxSourceExpansions() {
  return MAX_SOURCE_EXPANSIONS_HINT;
}

export function hasCompletedAnalysis() {
  return currentDataset !== null;
}

export function getLastDiagnostics() {
  return currentDiagnostics;
}

// Cumulative token usage/cost for the job's entire lifetime (every analyze/regenerate/
// retry action combined — see backend/jobs.py's usage-merge fix), or null before the
// first API call of a run completes. Read defensively by callers.
export function getUsage() {
  return currentUsage;
}

// Per-stage {outcome, attempts, lastFailureReason} — durable retry history that survives
// even after a later action succeeds (unlike getLastDiagnostics(), which only reflects
// the most recent action). Read defensively by callers; any given stage may be absent
// (not reached yet).
export function getStageProgress() {
  return currentStageProgress;
}

// {coveredDimensions, missingDimensions, sufficient, suggestions} or null before
// strategic_foundation has succeeded — see backend/pipeline_runner.assess_source_coverage.
// Never null-checked away silently by callers: this is what decides whether a screen may
// call its output a "Recommendation" (sufficient) or must call it an "Exploratory
// Narrative Hypothesis" (not sufficient) — treat a null/absent value as "not sufficient,"
// never as "assume it's fine."
export function getSourceCoverage() {
  return currentSourceCoverage;
}

export function resetLiveAnalysis() {
  currentDataset = null;
  currentDiagnostics = null;
  currentUsage = null;
  currentStageProgress = null;
  currentSourceCoverage = null;
  currentJobId = null;
  originalIntake = null;
  sourceExpansionsUsed = 0;
}

function assertDatasetReady() {
  if (!currentDataset) {
    throw new Error("No completed analysis yet. Start one from the intake screen first.");
  }
}

const STATIC_CASE_CONTEXT = {
  id: "live",
  selectorLabel: "Analyze a company",
  selectorDescription: "Run StoryMap on a real, publicly available company you choose — not a pre-built demonstration.",
  productTagline: "Turn scattered public information into one evidence-backed story.",
  company: { name: "a company you choose", oneLiner: "You'll enter its website and a few supporting links next." },
  whyThisCompany:
    "Unlike the Wix and Hammond Power Solutions cases, this analysis is generated live from whatever public " +
    "sources you provide — nothing here is pre-seeded.",
  headline: "What should this company's story be?",
  whatStoryMapWillDo: [
    "Fetch the public pages you provide",
    "Reconstruct the strategic foundation from what's actually stated",
    "Diagnose the current story's gaps",
    "Generate three materially different narrative directions",
    "Critique each one and recommend a direction — or say so honestly if none clears the bar",
  ],
  narrativeQuestion: "What should this company be known for, based only on what's publicly verifiable?",
  disclosure:
    "This analysis is provisional. It is built only from the public sources you provide — it has no access to " +
    "internal strategy, customer research, or proprietary data.",
  disclosureExtended:
    "Every claim is labeled as a source fact, a StoryMap synthesis, a StoryMap inference, or a leadership " +
    "decision — and any claim without direct evidence is marked as such rather than shown with false confidence.",
};

export const liveAnalysisService = {
  async getCaseContext() {
    return currentDataset?.caseContext || STATIC_CASE_CONTEXT;
  },
  async getStrategicFoundation() {
    assertDatasetReady();
    return currentDataset.strategicFoundation;
  },
  async getDiagnosis() {
    assertDatasetReady();
    return currentDataset.diagnosis;
  },
  async getCandidates() {
    assertDatasetReady();
    return normalizeCandidates(currentDataset.candidates);
  },
  async getRecommendation() {
    assertDatasetReady();
    // currentDataset.recommendation is already the canonical
    // {outcome, selectedCandidateId, failureReason, missingEvidence, leadershipDecisions,
    // createdAt, detail} object once critique has succeeded (backend/pipeline_runner.py's
    // build_recommendation_state) — null only when recommendation_and_map hasn't been
    // reached at all (an earlier stage failed). normalizeRecommendation is a no-op in
    // that already-canonical case; it only does real work for legacy/Wix-HPS shapes.
    return normalizeRecommendation(currentDataset.recommendation, normalizeCandidates(currentDataset.candidates));
  },
  async getNarrativeMap() {
    assertDatasetReady();
    return currentDataset.narrativeMap; // may be null — zero-candidate state
  },
  async getEvidence() {
    assertDatasetReady();
    return currentDataset.evidence;
  },
  async getEvidenceIndex() {
    assertDatasetReady();
    return buildEvidenceIndex(currentDataset);
  },
  async getAudiences() {
    assertDatasetReady();
    return currentDataset.audiences;
  },
  async getCompetitorContrasts() {
    assertDatasetReady();
    return currentDataset.competitorContrasts;
  },
};
