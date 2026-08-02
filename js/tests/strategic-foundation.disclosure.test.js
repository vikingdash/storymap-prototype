import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM, freshContainer } from "./helpers/dom-setup.js";

setupJSDOM();
const { renderStrategicFoundation } = await import("../components/StrategicFoundation.js");

function choice(id, type, statement, extra = {}) {
  return { id, type, statement, statementType: "source_fact", confidence: 0.8, evidence: [], ...extra };
}

function buildChoices() {
  return [
    choice("sf_cust", "customer", "Serves industrial manufacturers."),
    choice("sf_mkt", "market", "North American grid infrastructure."),
    choice("sf_mktchg", "market_change", "Grid modernization is accelerating."),
    choice("sf_cap", "capability", "Transformer engineering depth."),
    choice("sf_win", "way_to_win", "Deepening specialist expertise."),
    choice("sf_proof", "proof", "Certified to IEEE and ANSI standards."),
    choice("sf_assume", "assumption", "Assumes continued grid-modernization demand."),
    choice("sf_risk", "risk", "Execution risk if capacity can't scale."),
  ];
}

function buildService() {
  return {
    getStrategicFoundation: async () => buildChoices(),
    getCaseContext: async () => ({ company: { name: "Acme" }, narrativeQuestion: "x" }),
    getEvidenceIndex: async () => ({ getEvidenceWithSource: () => null }),
  };
}

function baseState() {
  return { caseId: "wix", approvals: {}, edits: {}, decisionResponses: {}, foundationConfirmed: false };
}

test("all seven sections render, collapsed by default, Risks kept distinct from Assumptions", async () => {
  const container = freshContainer();
  await renderStrategicFoundation(container, { service: buildService(), state: baseState(), drawer: {}, onNavigate: () => {} });

  const expectedIds = ["customers", "markets", "capabilities", "competitive-approach", "proof", "assumptions", "risks"];
  for (const id of expectedIds) {
    const section = container.querySelector(`#sf-section-${id}`);
    assert.ok(section, `section #sf-section-${id} must exist`);
    assert.equal(section.open, false, `section #sf-section-${id} must be collapsed by default`);
  }

  const risksSection = container.querySelector("#sf-section-risks");
  const assumptionsSection = container.querySelector("#sf-section-assumptions");
  assert.notEqual(risksSection, assumptionsSection);
  assert.match(risksSection.textContent, /Execution risk/);
  assert.doesNotMatch(assumptionsSection.textContent, /Execution risk/);
  assert.match(assumptionsSection.textContent, /grid-modernization demand/);
});

test("a section opens on clicking its summary (keyboard-operable native disclosure)", async () => {
  const container = freshContainer();
  await renderStrategicFoundation(container, { service: buildService(), state: baseState(), drawer: {}, onNavigate: () => {} });

  const section = container.querySelector("#sf-section-customers");
  assert.equal(section.open, false);
  section.querySelector("summary").click();
  assert.equal(section.open, true);
});

test("a review-strip jump-link opens its owning section and moves focus to the summary, not just scrolls", async () => {
  const container = freshContainer();
  await renderStrategicFoundation(container, { service: buildService(), state: baseState(), drawer: {}, onNavigate: () => {} });

  const risksSection = container.querySelector("#sf-section-risks");
  assert.equal(risksSection.open, false);

  const reviewRow = container.querySelector(".sf-review-item");
  assert.ok(reviewRow, "expected at least one review item (the risk)");
  reviewRow.dispatchEvent(new window.Event("click", { bubbles: true }));

  assert.equal(risksSection.open, true, "clicking the review item must open its section");
  assert.equal(document.activeElement, risksSection.querySelector("summary"), "focus must move to the section summary, not just scroll");
});
