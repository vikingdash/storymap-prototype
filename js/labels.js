// Shared label/badge vocabulary used across every screen so the same statement type,
// significance, or evidence strength always looks the same wherever it appears.
import { STATEMENT_TYPE_LABELS, EVIDENCE_RELEVANCE_LABELS } from "./schemas.js";

export function statementTypeBadge(statementType) {
  const label = STATEMENT_TYPE_LABELS[statementType] || statementType;
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

export function confidencePercent(confidence) {
  return `${Math.round(confidence * 100)}%`;
}

export function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
