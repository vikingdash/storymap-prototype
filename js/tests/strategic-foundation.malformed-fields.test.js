// Extends Phase 2's malformed-field audit pattern to this screen: proves BOTH that unsafe
// raw values never reach the UI, AND that a controlled fallback is shown, not just silence.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM, freshContainer } from "./helpers/dom-setup.js";

setupJSDOM();
const { renderStrategicFoundation, buildDimensionChips, buildSynthesizedSummary } = await import("../components/StrategicFoundation.js");

const UNSAFE_PATTERNS = [/\bundefined\b/, /\[object Object\]/, /\bat Object\./, /\bTypeError\b/, /\bStack:/];
function assertNoUnsafeTokens(text) {
  for (const pattern of UNSAFE_PATTERNS) assert.doesNotMatch(text, pattern, `found an unsafe token matching ${pattern}`);
}

test("a choice with missing evidence/confidence never crashes and never shows a raw undefined", async () => {
  const container = freshContainer();
  const malformedChoices = [
    // evidence, confidence, statementType all absent -- deliberately adversarial.
    { id: "sf_malformed", type: "customer", statement: "A malformed customer statement." },
    { id: "sf_synthesis_malformed", type: "capability", statement: "A malformed synthesis claim.", statementType: "storymap_synthesis" },
  ];
  const service = {
    getStrategicFoundation: async () => malformedChoices,
    getCaseContext: async () => ({ company: { name: "Acme" }, narrativeQuestion: "x" }),
    getEvidenceIndex: async () => ({ getEvidenceWithSource: () => null }),
  };
  const state = { caseId: "wix", approvals: {}, edits: {}, decisionResponses: {}, foundationConfirmed: false };

  await assert.doesNotReject(renderStrategicFoundation(container, { service, state, drawer: {}, onNavigate: () => {} }));
  assertNoUnsafeTokens(container.textContent);
  // Missing confidence falls back to "Early interpretation", a specific label, not a blank.
  assert.match(container.textContent, /Early interpretation/);
});

test("a decision item with no priority field is treated as secondary, not a crash", async () => {
  const container = freshContainer();
  const service = {
    getStrategicFoundation: async () => [{ id: "sf_decision_malformed", type: "unresolved", statement: "An unprioritized decision." }],
    getCaseContext: async () => ({ company: { name: "Acme" }, narrativeQuestion: "x" }),
    getEvidenceIndex: async () => ({ getEvidenceWithSource: () => null }),
  };
  const state = { caseId: "wix", approvals: {}, edits: {}, decisionResponses: {}, foundationConfirmed: false };
  await assert.doesNotReject(renderStrategicFoundation(container, { service, state, drawer: {}, onNavigate: () => {} }));
  assertNoUnsafeTokens(container.textContent);
});

test("buildDimensionChips shows the controlled 'Not yet determined' fallback per missing dimension, never a raw undefined", () => {
  const chips = buildDimensionChips([]);
  assert.equal(chips.length, 3, "always exactly three chips, even with zero data");
  chips.forEach((chip) => assert.equal(chip.value, "Not yet determined"));
});

test("buildSynthesizedSummary never throws on completely empty or malformed input", () => {
  assert.doesNotThrow(() => buildSynthesizedSummary([]));
  assert.doesNotThrow(() => buildSynthesizedSummary([{ id: "x", type: "customer" }])); // no statement field at all
});
