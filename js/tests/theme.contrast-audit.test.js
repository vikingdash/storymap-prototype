// WCAG 2.1 contrast audit for the Arctic Blue & Haze token set. Computes real relative-
// luminance contrast ratios (no approximation) for every text/background pairing the theme
// actually uses, and pins them against the correct threshold for that pairing's real usage
// (4.5:1 for text under 18px/24px regular or 14pt/18.66px bold, 3:1 for large text and for
// non-text UI components per WCAG 1.4.11).
//
// Two pairings are KNOWN, ACCEPTED gaps: --color-evidence and --color-review used as small
// (<18px) text land at ~4.2-4.3:1, just under the 4.5:1 text floor. This was flagged during
// design review and knowingly accepted (evidence text/links/icons must stay evidence-blue;
// review must stay the attention/leadership-judgment color) rather than silently deviating
// from the approved hexes. These two cases assert the measured ratio directly, banded
// tightly, so a future change to either hex is caught and re-evaluated rather than silently
// drifting further from AA.
import { test } from "node:test";
import assert from "node:assert/strict";

const TOKENS = {
  page: "#F7FAFC",
  surface: "#FFFFFF",
  surfaceSecondary: "#EEF4FA",
  surfaceTertiary: "#E7EEF6",
  textPrimary: "#1D2A3A",
  textSecondary: "#536273",
  textMuted: "#5B6B7A",
  primary: "#3E73C8",
  primaryHover: "#315FA7",
  evidence: "#537DB7",
  success: "#4C7A68",
  review: "#9A742F",
  risk: "#A75A62",
};

function hexToRgb(hex) {
  const n = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16));
}

function relativeLuminance(hex) {
  const [r, g, b] = hexToRgb(hex).map((c) => c / 255);
  const linearize = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const [lr, lg, lb] = [r, g, b].map(linearize);
  return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb;
}

function contrastRatio(hexA, hexB) {
  const [lLight, lDark] = [relativeLuminance(hexA), relativeLuminance(hexB)].sort((a, b) => b - a);
  return (lLight + 0.05) / (lDark + 0.05);
}

const AA_TEXT = 4.5;
const AA_LARGE_OR_UI = 3.0;

test("text-primary clears AA on every surface it appears on", () => {
  for (const bg of [TOKENS.surface, TOKENS.page, TOKENS.surfaceSecondary, TOKENS.surfaceTertiary]) {
    assert.ok(contrastRatio(TOKENS.textPrimary, bg) >= AA_TEXT, `text-primary on ${bg} must clear ${AA_TEXT}:1`);
  }
});

test("text-secondary clears AA text threshold on white (its most demanding real surface)", () => {
  const ratio = contrastRatio(TOKENS.textSecondary, TOKENS.surface);
  assert.ok(ratio >= AA_TEXT, `text-secondary on white was ${ratio.toFixed(2)}:1, must clear ${AA_TEXT}:1`);
});

test("text-muted (darkened from the originally-approved hex) clears AA text threshold on its worst-case surface", () => {
  // surface-tertiary is the darkest background text-muted realistically sits on
  // (evidence-filters <select>, .chip base) — the tightest case, so the one that matters.
  const ratio = contrastRatio(TOKENS.textMuted, TOKENS.surfaceTertiary);
  assert.ok(ratio >= AA_TEXT, `text-muted on surface-tertiary was ${ratio.toFixed(2)}:1, must clear ${AA_TEXT}:1`);
});

test("white button label clears AA on primary and primary-hover fills", () => {
  assert.ok(contrastRatio(TOKENS.surface, TOKENS.primary) >= AA_TEXT, "white on primary must clear AA");
  assert.ok(contrastRatio(TOKENS.surface, TOKENS.primaryHover) >= AA_TEXT, "white on primary-hover must clear AA");
});

test("primary as link/interactive text clears AA on white", () => {
  const ratio = contrastRatio(TOKENS.primary, TOKENS.surface);
  assert.ok(ratio >= AA_TEXT, `primary text on white was ${ratio.toFixed(2)}:1, must clear ${AA_TEXT}:1`);
});

test("success and risk clear AA as small text on white", () => {
  assert.ok(contrastRatio(TOKENS.success, TOKENS.surface) >= AA_TEXT, "success text must clear AA");
  assert.ok(contrastRatio(TOKENS.risk, TOKENS.surface) >= AA_TEXT, "risk text must clear AA");
});

test("primary and evidence clear the 3:1 non-text/UI-component threshold (borders, icons, focus rings)", () => {
  assert.ok(contrastRatio(TOKENS.primary, TOKENS.surface) >= AA_LARGE_OR_UI, "primary must clear 3:1 as a UI component");
  assert.ok(contrastRatio(TOKENS.evidence, TOKENS.surface) >= AA_LARGE_OR_UI, "evidence must clear 3:1 as a UI component");
  assert.ok(contrastRatio(TOKENS.review, TOKENS.surface) >= AA_LARGE_OR_UI, "review must clear 3:1 as a UI component");
});

test("KNOWN GAP (accepted): evidence as small text on white sits just under the 4.5:1 AA text floor", () => {
  const ratio = contrastRatio(TOKENS.evidence, TOKENS.surface);
  assert.ok(ratio >= 4.15 && ratio < 4.5, `evidence-on-white drifted to ${ratio.toFixed(2)}:1 — re-run the design review if this moved`);
});

test("KNOWN GAP (accepted): review as small text on white sits just under the 4.5:1 AA text floor", () => {
  const ratio = contrastRatio(TOKENS.review, TOKENS.surface);
  assert.ok(ratio >= 4.15 && ratio < 4.5, `review-on-white drifted to ${ratio.toFixed(2)}:1 — re-run the design review if this moved`);
});

test("border-strong is a real step darker than border, not a duplicate", () => {
  // Both are intentionally low-contrast decorative dividers/hover cues by design (thin
  // borders, low-chrome cards, restrained per the approved direction) — neither is asserted
  // against the 3:1 WCAG 1.4.11 threshold, since the actual accessible state signal for
  // selection/hover is the primary-color border + background change layered on top, not
  // these alone. This only guards that the two border tokens remain visually distinct.
  const border = "#D8E1EA";
  const borderStrong = "#C4D0DC";
  assert.ok(contrastRatio(borderStrong, TOKENS.surface) > contrastRatio(border, TOKENS.surface), "border-strong must read darker against white than border");
});
