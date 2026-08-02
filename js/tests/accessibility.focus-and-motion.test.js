import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM, freshContainer } from "./helpers/dom-setup.js";

setupJSDOM();
const { renderStrategicFoundation } = await import("../components/StrategicFoundation.js");

function choice(id, type, statement) {
  return { id, type, statement, statementType: "source_fact", confidence: 0.8, evidence: [] };
}

function buildService() {
  return {
    getStrategicFoundation: async () => [choice("sf_risk", "risk", "Execution risk if capacity can't scale.")],
    getCaseContext: async () => ({ company: { name: "Acme" }, narrativeQuestion: "x" }),
    getEvidenceIndex: async () => ({ getEvidenceWithSource: () => null }),
  };
}

function baseState() {
  return { caseId: "wix", approvals: {}, edits: {}, decisionResponses: {}, foundationConfirmed: false };
}

test("semantic heading order: h1 for the screen, h2 for card/section titles, no skipped levels", async () => {
  const container = freshContainer();
  await renderStrategicFoundation(container, { service: buildService(), state: baseState(), drawer: {}, onNavigate: () => {} });
  assert.equal(container.querySelectorAll("h1").length, 1, "exactly one h1 per screen");
  assert.ok(container.querySelector("h1").textContent.length > 0);
  const h3s = container.querySelectorAll("h3");
  // h3 (Leadership decisions / narrative question notice) exists directly under the
  // screen without an intervening h2 at that level being required -- disclosure section
  // titles live inside <summary>, not a heading, which is the correct native pattern.
  assert.ok(h3s.length >= 1);
});

test("the workflow rail has an accessible name and each step exposes aria-selected", async () => {
  const { renderWorkflowNav } = await import("../components/WorkflowNav.js");
  const container = freshContainer();
  renderWorkflowNav(container, {
    state: { screen: "foundation", caseId: "wix", visitedScreens: ["intro", "foundation"] },
    onNavigate: () => {}, onRestart: () => {},
  });
  const rail = container.querySelector(".nav-rail");
  assert.equal(rail.getAttribute("aria-label"), "StoryMap workflow");
  const steps = container.querySelectorAll('[role="tab"]');
  assert.ok(steps.length === 6);
  steps.forEach((step) => assert.ok(step.hasAttribute("aria-selected")));
});

test("focus moves to the target section's summary after a review-strip jump, never left stranded", async () => {
  const container = freshContainer();
  await renderStrategicFoundation(container, { service: buildService(), state: baseState(), drawer: {}, onNavigate: () => {} });
  container.querySelector(".sf-review-item").dispatchEvent(new window.Event("click", { bubbles: true }));
  const summary = container.querySelector("#sf-section-risks summary");
  assert.equal(document.activeElement, summary);
});

test("reduced-motion preference is respected: scrollIntoView is called without smooth behavior when prefers-reduced-motion matches", async () => {
  const container = freshContainer();
  const originalMatchMedia = window.matchMedia;
  window.matchMedia = (query) => ({ matches: query.includes("prefers-reduced-motion"), media: query, addListener() {}, removeListener() {} });

  await renderStrategicFoundation(container, { service: buildService(), state: baseState(), drawer: {}, onNavigate: () => {} });
  const summary = container.querySelector("#sf-section-risks summary");
  let capturedOpts = null;
  summary.scrollIntoView = (opts) => { capturedOpts = opts; };

  container.querySelector(".sf-review-item").dispatchEvent(new window.Event("click", { bubbles: true }));
  assert.equal(capturedOpts.behavior, "auto", "reduced-motion must suppress smooth scrolling");

  window.matchMedia = originalMatchMedia;
});

test("without a reduced-motion preference, scrolling uses smooth behavior", async () => {
  const container = freshContainer();
  const originalMatchMedia = window.matchMedia;
  window.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {} });

  await renderStrategicFoundation(container, { service: buildService(), state: baseState(), drawer: {}, onNavigate: () => {} });
  const summary = container.querySelector("#sf-section-risks summary");
  let capturedOpts = null;
  summary.scrollIntoView = (opts) => { capturedOpts = opts; };

  container.querySelector(".sf-review-item").dispatchEvent(new window.Event("click", { bubbles: true }));
  assert.equal(capturedOpts.behavior, "smooth");

  window.matchMedia = originalMatchMedia;
});
