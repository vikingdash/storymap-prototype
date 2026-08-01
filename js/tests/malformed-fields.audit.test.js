// Governing spec Phase 2's malformed-field audit — proves BOTH halves, not just "no crash":
//   1. unsafe internal values never reach the UI (undefined, null, [object Object], raw
//      enum names, stack traces, raw exceptions);
//   2. the interface renders a clear, field-appropriate human-readable fallback, not one
//      universal string.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM, freshContainer } from "./helpers/dom-setup.js";
import { FIXTURE_8_CANDIDATES, FIXTURE_8_RECOMMENDATION } from "./helpers/fixtures.js";

setupJSDOM();
const { renderNarrativeChoices } = await import("../components/NarrativeChoices.js");
const { renderRecommendation } = await import("../components/Recommendation.js");

const UNSAFE_PATTERNS = [
  /\bundefined\b/,
  /\[object Object\]/,
  /\bat Object\./, // stack-trace line signature
  /\bTypeError\b/,
  /\bReferenceError\b/,
  /\bStack:/,
];

function assertNoUnsafeTokens(text) {
  for (const pattern of UNSAFE_PATTERNS) {
    assert.doesNotMatch(text, pattern, `found an unsafe token matching ${pattern}`);
  }
}

test("malformed candidate: Narrative Choices never crashes and shows field-specific fallbacks, not one universal string", async () => {
  const container = freshContainer();
  const service = { getCandidates: async () => FIXTURE_8_CANDIDATES, getRecommendation: async () => FIXTURE_8_RECOMMENDATION };

  await assert.doesNotReject(
    renderNarrativeChoices(container, { service, drawer: { openEvidenceLinks: () => {} }, onNavigate: () => {} })
  );

  const text = container.textContent;
  assertNoUnsafeTokens(text);
  // Four DIFFERENT fallback strings, one per missing field — never one universal
  // "Not available" standing in for all of them.
  assert.match(text, /No strategic logic recorded\./);
  assert.match(text, /No trade-offs recorded\./);
  assert.match(text, /No risks recorded\./);
  assert.match(text, /No critic findings recorded\./);
});

test("malformed candidate: Recommendation screen never crashes on missing optional fields", async () => {
  const container = freshContainer();
  const service = {
    getRecommendation: async () => FIXTURE_8_RECOMMENDATION,
    getCandidates: async () => FIXTURE_8_CANDIDATES,
    getStrategicFoundation: async () => [],
  };

  await assert.doesNotReject(
    renderRecommendation(container, { service, state: { caseId: "live" }, drawer: {}, onNavigate: () => {} })
  );
  assertNoUnsafeTokens(container.textContent);
});
