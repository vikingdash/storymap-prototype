// Shared case-building logic used by every case file (js/cases/*.js). Extracted from the
// original single-case demo-data.js so a second case (or a third, later) gets byte-identical
// evidence-integrity enforcement — confidence caps, support-classification rules, structural
// validation — rather than each case file reimplementing (and risking drifting from) these
// rules. A case file should only ever need to define its raw content and call
// buildCaseDataset(raw) once at the bottom.
import { validateDataset } from "./schemas.js";

const STRENGTH_WEIGHT = { strong: 1, moderate: 0.65, weak: 0.3, unsupported: 0 };
const RELEVANCE_WEIGHT = { direct: 1, partial: 0.5, context: 0, conflicting: 0 };
export const NO_DIRECT_EVIDENCE_CONFIDENCE = 0.3; // no direct/partial support at all -> honestly low, not zero (it isn't contradicted, just unestablished)

// A public-source strategic interpretation should never read as certain — even a claim with
// only strong, direct, multi-source evidence tops out at MAX_CONFIDENCE, not 100%. And evidence
// clustered in a single source (even several distinct excerpts from it) is corroborated by
// nobody else, so it's capped further at SINGLE_SOURCE_CONFIDENCE_CAP until a second source
// backs it up. Only claims with strong direct support from 2+ distinct current sources can
// approach the ceiling.
export const MAX_CONFIDENCE = 0.95;
export const SINGLE_SOURCE_CONFIDENCE_CAP = 0.85;

// Confidence is derived, not authored: only "direct" and "partial" links can raise it, weighted
// by how strong the underlying EvidenceItem is. "context" and "conflicting" links never
// contribute — auditing away an irrelevant citation (like revenue growth "supporting" a customer
// segment claim) has to actually lower confidence, or the audit is cosmetic.
function computeConfidenceFromLinks(links, evidenceById) {
  const contributing = links
    .filter((link) => link.relevance === "direct" || link.relevance === "partial")
    .map((link) => ({ link, ev: evidenceById.get(link.evidenceId) }))
    .filter(({ ev }) => ev);

  if (!contributing.length) return NO_DIRECT_EVIDENCE_CONFIDENCE;

  const weights = contributing.map(({ link, ev }) => (STRENGTH_WEIGHT[ev.strength] ?? 0) * RELEVANCE_WEIGHT[link.relevance]);
  const avg = weights.reduce((sum, w) => sum + w, 0) / weights.length;

  const distinctSources = new Set(contributing.map(({ ev }) => ev.sourceId)).size;
  const cap = distinctSources >= 2 ? MAX_CONFIDENCE : SINGLE_SOURCE_CONFIDENCE_CAP;

  return Math.round(Math.min(avg, cap) * 100) / 100;
}

function recalculateConfidence(dataset) {
  const evidenceById = new Map(dataset.evidence.map((e) => [e.id, e]));
  dataset.strategicFoundation.forEach((choice) => {
    if (choice.type === "unresolved") return; // leadership decisions have no evidence model; confidence stays 0
    choice.confidence = computeConfidenceFromLinks(choice.evidence, evidenceById);
  });
  dataset.diagnosis.forEach((finding) => {
    finding.confidence = computeConfidenceFromLinks(finding.evidence, evidenceById);
  });
  return dataset;
}

function wireEvidenceSupportsIds(dataset) {
  const evidenceById = new Map(dataset.evidence.map((e) => [e.id, e]));
  const addSupport = (links, supportingId) => {
    (links || []).forEach((link) => {
      const ev = evidenceById.get(link.evidenceId);
      if (ev && !ev.supportsIds.includes(supportingId)) ev.supportsIds.push(supportingId);
    });
  };
  dataset.strategicFoundation.forEach((c) => addSupport(c.evidence, c.id));
  dataset.diagnosis.forEach((f) => addSupport(f.evidence, f.id));
  dataset.candidates.forEach((cand) => addSupport(cand.claims, cand.id));
  dataset.narrativeMap.coreClaims.forEach((claim) => addSupport(claim.evidence, claim.id));
  dataset.competitorContrasts.forEach((c) => addSupport(c.evidence, c.id));
  return dataset;
}

// Order matters: confidence must be recalculated from evidence links before validateDataset
// checks that every confidence value is a valid number — validateDataset is a structural check,
// not a computation, so the derived values need to already be in place by the time it runs.
export function buildCaseDataset(raw) {
  return validateDataset(recalculateConfidence(wireEvidenceSupportsIds(raw)));
}
