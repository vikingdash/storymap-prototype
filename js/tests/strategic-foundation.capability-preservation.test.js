// Direct extension of Phase 2's cross-screen-consistency pattern: every action the prior
// dense layout offered must still fire its existing handler once the item's section is
// opened. Uses the REAL state.js module (localStorage-backed, already set up by jsdom) so
// this proves actual state mutation, not just that a click handler exists.
import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM, freshContainer } from "./helpers/dom-setup.js";

setupJSDOM();
const { renderStrategicFoundation } = await import("../components/StrategicFoundation.js");
const { getState, restart } = await import("../state.js");

beforeEach(() => restart());

function choice(id, type, statement, extra = {}) {
  return { id, type, statement, statementType: "source_fact", confidence: 0.8, evidence: [], ...extra };
}

function buildChoices() {
  return [
    choice("sf_risk", "risk", "Execution risk if capacity can't scale."),
    choice("sf_decision", "unresolved", "Should the company expand?", { priority: "primary" }),
  ];
}

function buildService() {
  return {
    getStrategicFoundation: async () => buildChoices(),
    getCaseContext: async () => ({ company: { name: "Acme" }, narrativeQuestion: "x" }),
    getEvidenceIndex: async () => ({ getEvidenceWithSource: () => null }),
  };
}

async function renderFresh() {
  const container = freshContainer();
  const state = getState();
  await renderStrategicFoundation(container, { service: buildService(), state, drawer: {}, onNavigate: () => {} });
  return container;
}

test("Edit -> Save persists the edited text via setApproval", async () => {
  const container = await renderFresh();
  container.querySelector("#sf-section-risks summary").click();
  const item = container.querySelector("#sf-section-risks .sf-item");
  item.querySelector('[data-action="edit"]').click();
  const textarea = item.querySelector(".edit-textarea");
  textarea.value = "An edited risk statement.";
  item.querySelector('[data-action="save-edit"]').click();

  assert.equal(getState().approvals.sf_risk, "edited");
  assert.equal(getState().edits.sf_risk, "An edited risk statement.");
});

test("Reject then Undo round-trips cleanly through real state", async () => {
  const container = await renderFresh();
  container.querySelector("#sf-section-risks summary").click();
  const item = container.querySelector("#sf-section-risks .sf-item");
  item.querySelector('[data-action="reject"]').click();
  assert.equal(getState().approvals.sf_risk, "rejected");
  assert.ok(item.classList.contains("rejected"));

  const undoBtn = [...item.querySelectorAll("button")].find((b) => b.textContent === "Undo");
  assert.ok(undoBtn, "Undo control must appear after rejecting");
  undoBtn.click();
  assert.equal(getState().approvals.sf_risk, undefined);
  assert.ok(!item.classList.contains("rejected"));
});

test("leadership decision: Save answer and Defer both persist via setDecisionResponse", async () => {
  const container = await renderFresh();
  const decisionItem = container.querySelector(".decision-item");
  const textarea = decisionItem.querySelector(".decision-response-textarea");
  textarea.value = "Yes, in phase two.";
  decisionItem.querySelector('[data-action="save-response"]').click();
  assert.equal(getState().decisionResponses.sf_decision.response, "Yes, in phase two.");

  decisionItem.querySelector('[data-action="defer"]').click();
  assert.equal(getState().decisionResponses.sf_decision.deferred, true);
});

test("Confirm strategic foundation still navigates and persists foundationConfirmed", async () => {
  const container = await renderFresh();
  let navigatedTo = null;
  const state = getState();
  await renderStrategicFoundation(container, { service: buildService(), state, drawer: {}, onNavigate: (id) => { navigatedTo = id; } });
  container.querySelector('[data-action="confirm"]').click();
  assert.equal(navigatedTo, "diagnosis");
  assert.equal(getState().foundationConfirmed, true);
});
