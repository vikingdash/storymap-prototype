// Pure unit tests — no DOM needed, but setupJSDOM() still runs first since labels.js is an
// ES module and every test file in this suite follows the same import order for consistency.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM } from "./helpers/dom-setup.js";

setupJSDOM();
const { confidenceLabel } = await import("../labels.js");

test("Well supported: confidence >= 0.75", () => {
  assert.equal(confidenceLabel(0.75, []).label, "Well supported");
  assert.equal(confidenceLabel(0.95, []).label, "Well supported");
});

test("Supported with gaps: 0.50-0.74", () => {
  assert.equal(confidenceLabel(0.5, []).label, "Supported with gaps");
  assert.equal(confidenceLabel(0.74, []).label, "Supported with gaps");
});

test("Needs confirmation: 0.30-0.49", () => {
  assert.equal(confidenceLabel(0.3, []).label, "Needs confirmation");
  assert.equal(confidenceLabel(0.49, []).label, "Needs confirmation");
});

test("Early interpretation: below 0.30", () => {
  assert.equal(confidenceLabel(0.29, []).label, "Early interpretation");
  assert.equal(confidenceLabel(0, []).label, "Early interpretation");
});

test("Conflicting evidence overrides the numeric band regardless of how high confidence is", () => {
  const highConfidenceButConflicting = confidenceLabel(0.9, [{ relevance: "conflicting" }]);
  assert.equal(highConfidenceButConflicting.label, "Conflicting evidence");
});

test("boundary values are inclusive on the lower edge of each band, not the upper", () => {
  assert.equal(confidenceLabel(0.75, []).label, "Well supported");
  assert.notEqual(confidenceLabel(0.7499, []).label, "Well supported");
  assert.equal(confidenceLabel(0.5, []).label, "Supported with gaps");
  assert.equal(confidenceLabel(0.3, []).label, "Needs confirmation");
});
