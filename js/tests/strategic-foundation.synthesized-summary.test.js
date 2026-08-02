import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM } from "./helpers/dom-setup.js";

setupJSDOM();
const { buildSynthesizedSummary, SYNTHESIS_FALLBACK } = await import("../components/StrategicFoundation.js");

function choice(type, statement, confidence = 0.8) {
  return { id: `sf_${type}`, type, statement, statementType: "source_fact", confidence, evidence: [] };
}

test("all three dimensions present: one sentence per dimension, no invented connecting text between them", () => {
  const choices = [
    choice("customer", "Serves industrial manufacturers and utility operators."),
    choice("capability", "Decades of transformer engineering depth."),
    choice("way_to_win", "Deepening specialist expertise rather than broadening."),
  ];
  const summary = buildSynthesizedSummary(choices);
  assert.notEqual(summary, SYNTHESIS_FALLBACK);
  assert.match(summary, /Serves industrial manufacturers/);
  assert.match(summary, /Decades of transformer engineering depth/);
  assert.match(summary, /Deepening specialist expertise/);
});

test("one dimension missing: the summary is still coherent, the missing dimension is simply absent", () => {
  const choices = [choice("customer", "Serves industrial manufacturers.")];
  const summary = buildSynthesizedSummary(choices);
  assert.match(summary, /Serves industrial manufacturers/);
  assert.notEqual(summary, SYNTHESIS_FALLBACK);
});

test("two dimensions missing: still human-readable with just one sentence", () => {
  const choices = [choice("way_to_win", "Competes on specialist depth.")];
  const summary = buildSynthesizedSummary(choices);
  assert.equal(summary, "Competes on specialist depth.");
});

test("zero usable dimensions: shows the controlled fallback, never an empty string or broken partial sentence", () => {
  const choices = [choice("assumption", "Some unrelated assumption.")];
  const summary = buildSynthesizedSummary(choices);
  assert.equal(summary, SYNTHESIS_FALLBACK);
});

test("empty choices list: shows the controlled fallback", () => {
  assert.equal(buildSynthesizedSummary([]), SYNTHESIS_FALLBACK);
});

test("never exceeds roughly 80 words", () => {
  const longStatement = new Array(60).fill("word").join(" ") + ".";
  const choices = [choice("customer", longStatement), choice("capability", longStatement), choice("way_to_win", longStatement)];
  const summary = buildSynthesizedSummary(choices);
  const wordCount = summary.trim().split(/\s+/).length;
  assert.ok(wordCount <= 82, `expected roughly <=80 words, got ${wordCount}`);
});

test("picks the highest-confidence item per dimension when more than one qualifies", () => {
  const choices = [
    choice("customer", "Low confidence customer statement.", 0.3),
    choice("customer", "High confidence customer statement.", 0.9),
  ];
  choices[1].id = "sf_customer_2";
  const summary = buildSynthesizedSummary(choices);
  assert.match(summary, /High confidence customer statement/);
  assert.doesNotMatch(summary, /Low confidence customer statement/);
});
