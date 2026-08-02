// jsdom has no real layout engine, so actual CSS reflow at a given viewport width isn't
// verifiable here -- this test instead proves the STRUCTURAL markup the responsive CSS
// rules key off of actually exists with the right class names, which is what a real
// browser's media query then acts on. Full visual confirmation is a manual-checklist item.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM, freshContainer } from "./helpers/dom-setup.js";

setupJSDOM();
const { renderStrategicFoundation } = await import("../components/StrategicFoundation.js");
const { renderWorkflowNav } = await import("../components/WorkflowNav.js");

function choice(id, type, statement) {
  return { id, type, statement, statementType: "source_fact", confidence: 0.8, evidence: [] };
}

test("Strategic Foundation: the sticky mobile CTA structure exists (single-column collapse target)", async () => {
  const container = freshContainer();
  const service = {
    getStrategicFoundation: async () => [choice("sf_cust", "customer", "Serves manufacturers.")],
    getCaseContext: async () => ({ company: { name: "Acme" }, narrativeQuestion: "x" }),
    getEvidenceIndex: async () => ({ getEvidenceWithSource: () => null }),
  };
  const state = { caseId: "wix", approvals: {}, edits: {}, decisionResponses: {}, foundationConfirmed: false };
  await renderStrategicFoundation(container, { service, state, drawer: {}, onNavigate: () => {} });

  const stickyFooter = container.querySelector(".confirm-footer.sf-cta-sticky-mobile");
  assert.ok(stickyFooter, "the sticky-CTA class the mobile media query targets must be present");
  assert.ok(stickyFooter.querySelector(".primary-button"), "the primary action must live inside it");

  const dims = container.querySelector(".sf-dims");
  assert.ok(dims, "the three-dimension grid (1fr on mobile, 3 columns on desktop) must be present");
});

test("Workflow Nav: the mobile single-line summary + progress bar structure exists alongside the desktop rail", () => {
  const container = freshContainer();
  renderWorkflowNav(container, {
    state: { screen: "diagnosis", caseId: "wix", visitedScreens: ["intro", "foundation", "diagnosis"] },
    onNavigate: () => {}, onRestart: () => {},
  });
  assert.ok(container.querySelector(".nav-mobile-summary"), "mobile-only collapsed summary must exist");
  assert.ok(container.querySelector(".nav-mobile-progress-fill"), "mobile progress bar must exist");
  assert.ok(container.querySelector(".nav-rail"), "desktop rail must also exist (CSS decides which is visible)");
});
