// Shared label/badge vocabulary used across every screen so the same statement type,
// significance, or evidence strength always looks the same wherever it appears.
import { STATEMENT_TYPE_LABELS, EVIDENCE_RELEVANCE_LABELS } from "./schemas.js";

export function statementTypeBadge(statementType) {
  const label = STATEMENT_TYPE_LABELS[statementType] || statementType || "Unclassified";
  const className = {
    source_fact: "badge badge-fact",
    storymap_inference: "badge badge-inference",
    storymap_synthesis: "badge badge-synthesis",
    recommendation: "badge badge-recommendation",
    leadership_decision: "badge badge-decision",
    aspiration: "badge badge-aspiration",
  }[statementType] || "badge";
  return { label, className };
}

export function significanceLabel(significance) {
  return {
    high: { label: "High significance", className: "sev sev-high" },
    medium: { label: "Medium significance", className: "sev sev-medium" },
    low: { label: "Low significance", className: "sev sev-low" },
  }[significance] || { label: significance, className: "sev" };
}

export function strengthLabel(strength) {
  return {
    strong: { label: "Strong evidence", className: "chip chip-strong" },
    moderate: { label: "Moderate evidence", className: "chip chip-moderate" },
    weak: { label: "Weak evidence", className: "chip chip-weak" },
    unsupported: { label: "Unsupported", className: "chip chip-unsupported" },
  }[strength] || { label: strength, className: "chip" };
}

// How a piece of evidence relates to the specific statement it's attached to — separate from
// strengthLabel (how reliable the source itself is). A "direct" link to a weak source and a
// "context" link to a strong source are both real, valid combinations.
export function relevanceLabel(relevance) {
  const label = EVIDENCE_RELEVANCE_LABELS[relevance] || relevance;
  const className = {
    direct: "chip chip-strong",
    partial: "chip chip-moderate",
    context: "chip",
    conflicting: "chip chip-unsupported",
    // Same visual weight as "partial" — never as certain-looking as "direct" (chip-strong).
    // Only ever appears on live-flow evidence the backend downgraded from "direct" because
    // it came from the current draft narrative; Wix/HPS never produce this value.
    company_position: "chip chip-moderate",
  }[relevance] || "chip";
  return { label, className };
}

export function freshnessLabel(freshness) {
  return {
    current: { label: "Current", className: "chip chip-current" },
    aging: { label: "Aging", className: "chip chip-aging" },
    stale: { label: "Stale", className: "chip chip-stale" },
  }[freshness] || { label: freshness, className: "chip" };
}

// Human labels for the live "Analyze a company" flow's internal-document upload feature
// (backend/schema_constants.DOCUMENT_ROLES/DOCUMENT_ROLE_LABELS — kept in sync by hand,
// same convention as every other label map here). A source's documentRole is only ever
// set for sourceType "internal" uploads (AnalyzeCompany.js/EvidenceRoom.js); undefined
// for every other source, including every Wix/HPS source.
export const DOCUMENT_ROLE_LABELS = {
  current_draft_narrative: "Current draft corporate narrative",
  strategy_or_business_plan: "Strategy or business plan",
  customer_research: "Customer research",
  proof_or_performance_evidence: "Proof or performance evidence",
  investor_or_financial_material: "Investor or financial material",
  existing_messaging: "Existing messaging",
  other_internal_context: "Other internal context",
};

export function confidencePercent(confidence) {
  return `${Math.round(confidence * 100)}%`;
}

// Confidence presentation layer (UX & visual-system phase) — the DEFAULT visible signal is
// now a plain-language label, never a percentage; confidencePercent() above is unchanged and
// still used wherever the raw number is needed (tests, internal validation). Confidence
// itself is never recalculated here, only classified. "Conflicting evidence" is an
// evidence-STATE override, checked first and independent of the numeric band, since a
// statement can carry solid overall confidence while one link actively contradicts it.
const CONFIDENCE_BANDS = [
  { min: 0.75, label: "Well supported", className: "sf-conf sf-conf-well" },
  { min: 0.5, label: "Supported with gaps", className: "sf-conf sf-conf-gaps" },
  { min: 0.3, label: "Needs confirmation", className: "sf-conf sf-conf-confirm" },
];
const EARLY_INTERPRETATION = { label: "Early interpretation", className: "sf-conf sf-conf-early" };
const CONFLICTING_EVIDENCE = { label: "Conflicting evidence", className: "sf-conf sf-conf-conflict" };

export function confidenceLabel(confidence, evidence) {
  if ((evidence || []).some((link) => link.relevance === "conflicting")) {
    return CONFLICTING_EVIDENCE;
  }
  const band = CONFIDENCE_BANDS.find((b) => confidence >= b.min);
  return band ? { label: band.label, className: band.className } : EARLY_INTERPRETATION;
}

// Stage-aware judgment (governing narrative-stage decision 2): the user sees the ONE
// judgment appropriate to a claim's maturity, never confidence and directionalCredibility
// side by side. Same underlying visual tiers as CONFIDENCE_BANDS (well/gaps/confirm — no
// new colors, per "distinguish via labels, not more colors") but the LABEL TEXT and which
// number feeds it both change with narrativeStage:
//   proven_today                    -> confidence, framed as evidence strength
//   emerging / in_build             -> confidence, framed as evidence of movement (same
//                                      formula — "is the commitment/movement itself real,"
//                                      not "is the end-state already true")
//   strategic_direction             -> directionalCredibility, framed as directional
//                                      credibility (a lower ceiling, counts different
//                                      evidence — see case-utils.js)
//   aspiration_pending_leadership   -> no number at all; always "Requires leadership
//                                      approval" — "not fully built" must never be
//                                      presented as "not credible" by attaching a low score.
const MOVEMENT_BANDS = [
  { min: 0.75, label: "Well-evidenced movement", className: "sf-conf sf-conf-well" },
  { min: 0.5, label: "Movement with gaps", className: "sf-conf sf-conf-gaps" },
  { min: 0.3, label: "Early movement", className: "sf-conf sf-conf-confirm" },
];
const DIRECTIONAL_CREDIBILITY_BANDS = [
  { min: 0.6, label: "Strong directional credibility", className: "sf-conf sf-conf-well" },
  { min: 0.4, label: "Moderate directional credibility", className: "sf-conf sf-conf-gaps" },
];
const DIRECTIONAL_CREDIBILITY_LOW = { label: "Limited directional credibility", className: "sf-conf sf-conf-confirm" };
const LEADERSHIP_APPROVAL_REQUIRED = { label: "Requires leadership approval", className: "sf-conf sf-conf-confirm" };

export function narrativeStageJudgment(narrativeStage, confidence, directionalCredibility, evidence) {
  if ((evidence || []).some((link) => link.relevance === "conflicting")) {
    return CONFLICTING_EVIDENCE;
  }
  if (narrativeStage === "aspiration_pending_leadership") {
    return LEADERSHIP_APPROVAL_REQUIRED;
  }
  if (narrativeStage === "strategic_direction") {
    const band = DIRECTIONAL_CREDIBILITY_BANDS.find((b) => directionalCredibility >= b.min);
    return band || DIRECTIONAL_CREDIBILITY_LOW;
  }
  const bands = narrativeStage === "emerging" || narrativeStage === "in_build" ? MOVEMENT_BANDS : CONFIDENCE_BANDS;
  const band = bands.find((b) => confidence >= b.min);
  return band || EARLY_INTERPRETATION;
}

// Short labels for the compact per-candidate stage-mix summary (governing narrative-stage
// decision 8: summarize the mix on candidate directions, never a badge per claim). Deferred
// per-claim exposure and a dedicated rationale/evidence-layer stage view are intentionally
// NOT built in this pass — see the session report.
const NARRATIVE_STAGE_SHORT_LABELS = {
  proven_today: "proven today",
  emerging: "emerging",
  in_build: "in build",
  strategic_direction: "direction",
  aspiration_pending_leadership: "leadership-dependent",
};

export function narrativeStageMixSummary(narrativeStages) {
  if (!Array.isArray(narrativeStages) || narrativeStages.length === 0) return "";
  const counts = new Map();
  narrativeStages.forEach((entry) => {
    const label = NARRATIVE_STAGE_SHORT_LABELS[entry.stage] || entry.stage;
    counts.set(label, (counts.get(label) || 0) + 1);
  });
  return [...counts.entries()].map(([label, n]) => `${n} ${label}`).join(" · ");
}

export function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
