// Regression test for a real bug found and fixed during Phase 1: NarrativeChoices.js used
// to independently recompute viability from scoring.js's MIN_SCORE_THRESHOLDS
// (Differentiation >= 3), which mislabeled a genuinely viable seeded candidate on BOTH
// Wix and HPS (Differentiation score of 2, never rejected by the real seed status or the
// backend-equivalent decisionAgent gate, whose real threshold is <= 1). Reading
// candidate.status directly (governing spec Phase 1, decision 2) fixed this. This test
// exercises the REAL, untouched seed data through the REAL service layer — no mocking.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM, freshContainer } from "./helpers/dom-setup.js";

setupJSDOM();
const { getAnalysisService } = await import("../analysis-service.js");
const { renderNarrativeChoices } = await import("../components/NarrativeChoices.js");

test("Wix's Differentiation-2 candidate ('From idea to working business') shows Viable alternative, not a threshold failure", async () => {
  const container = freshContainer();
  const service = getAnalysisService("wix");
  await renderNarrativeChoices(container, { service, drawer: { openEvidenceLinks: () => {} }, onNavigate: () => {} });

  const cards = [...container.querySelectorAll(".candidate-card")];
  const target = cards.find((c) => c.textContent.includes("From idea to working business"));
  assert.ok(target, "expected Wix candidate not found in the rendered cards -- has the seed data changed?");
  assert.match(target.textContent, /Viable alternative/);
  assert.doesNotMatch(target.textContent, /Does not pass/);
});

test("HPS's Differentiation-2 candidate ('Built for increasingly complex power') shows Viable alternative, not a threshold failure", async () => {
  const container = freshContainer();
  const service = getAnalysisService("hps");
  await renderNarrativeChoices(container, { service, drawer: { openEvidenceLinks: () => {} }, onNavigate: () => {} });

  const cards = [...container.querySelectorAll(".candidate-card")];
  const target = cards.find((c) => c.textContent.includes("Built for increasingly complex power"));
  assert.ok(target, "expected HPS candidate not found in the rendered cards -- has the seed data changed?");
  assert.match(target.textContent, /Viable alternative/);
  assert.doesNotMatch(target.textContent, /Does not pass/);
});
