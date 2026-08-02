import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM, freshContainer } from "./helpers/dom-setup.js";

setupJSDOM();
const { renderWorkflowNav, SCREENS } = await import("../components/WorkflowNav.js");

function baseState(overrides = {}) {
  return { screen: "diagnosis", caseId: "wix", visitedScreens: ["intro", "foundation", "diagnosis"], ...overrides };
}

test("the six new user-facing labels render for the six unchanged screen ids, in order", () => {
  const expected = [
    ["foundation", "Understand the business"],
    ["diagnosis", "Diagnose the current story"],
    ["choices", "Explore directions"],
    ["recommendation", "Choose a direction"],
    ["map", "Build the narrative"],
    ["evidence", "Review the evidence"],
  ];
  assert.deepEqual(SCREENS.map((s) => [s.id, s.label]), expected);
});

test("current step is distinguishable via a semantic class, not color alone", () => {
  const container = freshContainer();
  renderWorkflowNav(container, { state: baseState(), onNavigate: () => {}, onRestart: () => {} });

  const steps = [...container.querySelectorAll(".nav-rail-step")];
  const current = steps.find((s) => s.classList.contains("current"));
  assert.ok(current, "a step must carry the current class");
  assert.match(current.textContent, /Diagnose the current story/);
  assert.equal(current.getAttribute("aria-selected"), "true");
});

test("visited steps are marked done via a semantic class", () => {
  const container = freshContainer();
  renderWorkflowNav(container, { state: baseState(), onNavigate: () => {}, onRestart: () => {} });
  const steps = [...container.querySelectorAll(".nav-rail-step")];
  const done = steps.find((s) => s.textContent.includes("Understand the business"));
  assert.ok(done.classList.contains("done"));
});

test("clicking a step navigates using its unchanged internal id, not the new label text", () => {
  const container = freshContainer();
  let navigatedTo = null;
  renderWorkflowNav(container, { state: baseState(), onNavigate: (id) => { navigatedTo = id; }, onRestart: () => {} });
  const step = [...container.querySelectorAll(".nav-rail-step")].find((s) => s.textContent.includes("Choose a direction"));
  step.click();
  assert.equal(navigatedTo, "recommendation");
});

test("mobile summary shows the current step number and label", () => {
  const container = freshContainer();
  renderWorkflowNav(container, { state: baseState(), onNavigate: () => {}, onRestart: () => {} });
  const summary = container.querySelector(".nav-mobile-summary");
  assert.match(summary.textContent, /Step 2 of 6/);
  assert.match(summary.textContent, /Diagnose the current story/);
});

test("tapping the mobile summary toggles the rail open state", () => {
  const container = freshContainer();
  renderWorkflowNav(container, { state: baseState(), onNavigate: () => {}, onRestart: () => {} });
  const toggleBtn = container.querySelector('[data-action="toggle-rail"]');
  const rail = container.querySelector(".nav-rail");
  assert.equal(rail.classList.contains("open"), false);
  toggleBtn.click();
  assert.equal(rail.classList.contains("open"), true);
  assert.equal(toggleBtn.getAttribute("aria-expanded"), "true");
});
