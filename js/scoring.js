// Presentation helpers for the 1-5 criterion scores shown on narrative candidates.
// Scoring itself happens in analysis-service.js (Decision Agent stage); this module only
// formats what the Decision Agent already produced — it does not invent or adjust numbers.

const SCALE_MAX = 5;

export function scoreBarWidthPercent(score) {
  return Math.max(0, Math.min(100, (score / SCALE_MAX) * 100));
}

export function averageScore(scores) {
  const values = Object.values(scores);
  if (!values.length) return 0;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

export function formatScore(score) {
  return `${score}/${SCALE_MAX}`;
}

// A single blended number is only meaningful if the candidate clears a floor on the criteria
// that would make the whole story unusable if weak — a high average can otherwise paper over a
// candidate that's, say, barely differentiated from competitors. Below this floor, showing an
// average reads as false precision; showing *why* there's no average is more informative.
const MIN_SCORE_THRESHOLDS = { "Strategic fit": 3, Differentiation: 3, "Evidence strength": 3 };

export function computeOverallScore(scores) {
  const failing = Object.entries(MIN_SCORE_THRESHOLDS)
    .filter(([criterion, min]) => (scores[criterion] ?? 0) < min)
    .map(([criterion, min]) => ({ criterion, min, actual: scores[criterion] ?? 0 }));
  if (failing.length) {
    return { blocked: true, failing, value: null };
  }
  return { blocked: false, failing: [], value: averageScore(scores) };
}

// Explains *how* each criterion is scored, not just the number — shown collapsed under "How
// StoryMap scored this" so a score never appears without an explanation of what it measures.
export const SCORE_RUBRIC = {
  "Strategic fit": "How closely the candidate matches the reconstructed strategic foundation — the way to win, capabilities and market change from the Strategic Foundation screen.",
  "Customer relevance": "Whether the story addresses a tension or need customers actually described or exhibited in the evidence, not just a product category.",
  "Differentiation": "How distinct the story is from competitor positioning and category conventions surfaced in the diagnosis.",
  "Evidence strength": "The proportion of this candidate's claims that are directly supported by evidence rather than context-only, weighted by source quality.",
  "Durability": "Whether the story can absorb foreseeable product and portfolio changes without needing to be rewritten.",
};
