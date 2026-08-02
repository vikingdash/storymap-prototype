import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM, freshContainer } from "./helpers/dom-setup.js";

setupJSDOM();
const { renderStrategicFoundation } = await import("../components/StrategicFoundation.js");

function choice(id, type, statement, extra = {}) {
  return { id, type, statement, statementType: "source_fact", confidence: 0.8, evidence: [], priority: undefined, ...extra };
}

// A realistic mix, deliberately including more than 3 review-worthy items (2 risks + 1
// unresponded primary decision + 1 low-confidence item = 4) so the cap is actually exercised.
function buildChoices() {
  return [
    choice("sf_cust", "customer", "Serves industrial manufacturers and utility operators."),
    choice("sf_mkt", "market", "Operates primarily in North American grid infrastructure."),
    choice("sf_cap", "capability", "Decades of transformer engineering depth."),
    choice("sf_win", "way_to_win", "Deepening specialist expertise rather than broadening."),
    choice("sf_proof", "proof", "Certified to IEEE and ANSI transformer standards."),
    choice("sf_assume", "assumption", "Assumes demand for grid modernization continues."),
    choice("sf_risk1", "risk", "Execution risk if manufacturing capacity can't scale."),
    choice("sf_risk2", "risk", "Key-customer concentration risk in one segment."),
    choice("sf_low_conf", "capability", "Weakly evidenced secondary capability claim.", { confidence: 0.2 }),
    choice("sf_decision_primary", "unresolved", "Should the company expand beyond core transformers?", { priority: "primary" }),
  ];
}

function buildService() {
  return {
    getStrategicFoundation: async () => buildChoices(),
    getCaseContext: async () => ({ company: { name: "Acme Power" }, narrativeQuestion: "What should Acme be known for?" }),
    getEvidenceIndex: async () => ({ getEvidenceWithSource: () => null }),
  };
}

function baseState() {
  return { caseId: "wix", approvals: {}, edits: {}, decisionResponses: {}, foundationConfirmed: false };
}

test("first viewport answers where/what/why/next: synthesized summary, three dimensions, capped review strip, one primary action", async () => {
  const container = freshContainer();
  await renderStrategicFoundation(container, { service: buildService(), state: baseState(), drawer: {}, onNavigate: () => {} });

  assert.ok(container.querySelector(".sf-summary-text"), "synthesized summary must be present");
  const dims = container.querySelectorAll(".sf-dim");
  assert.equal(dims.length, 3, "exactly three compact dimensions, always");

  const reviewRows = container.querySelectorAll(".sf-review-item");
  assert.ok(reviewRows.length <= 3, `review strip must show at most 3 items, got ${reviewRows.length}`);
  assert.ok(container.querySelector('[data-action="show-all-review"]'), "an overflow link must exist when more than 3 items need review");

  const confirmButtons = container.querySelectorAll('[data-action="confirm"]');
  assert.equal(confirmButtons.length, 1, "exactly one primary action, not several competing CTAs");
});

test("\"All N items\" expands the review strip to the full ranked list", async () => {
  const container = freshContainer();
  await renderStrategicFoundation(container, { service: buildService(), state: baseState(), drawer: {}, onNavigate: () => {} });

  const showAllBtn = container.querySelector('[data-action="show-all-review"]');
  showAllBtn.dispatchEvent(new window.Event("click", { bubbles: true }));
  const reviewRows = container.querySelectorAll(".sf-review-item");
  // 2 risks + 1 primary decision + 1 low-confidence item = 4 total.
  assert.equal(reviewRows.length, 4);
});
