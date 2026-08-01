import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM, freshContainer } from "./helpers/dom-setup.js";
import { FIXTURE_5_CANDIDATES, FIXTURE_5_RECOMMENDATION, FIXTURE_5_STRATEGIC_FOUNDATION } from "./helpers/fixtures.js";

setupJSDOM();
const { renderRecommendation } = await import("../components/Recommendation.js");

test("partial results remain navigable after an early-stage failure (diagnosis failed, nothing after it reached)", async () => {
  const container = freshContainer();
  let navigatedTo = null;
  const service = {
    getRecommendation: async () => FIXTURE_5_RECOMMENDATION,
    getCandidates: async () => FIXTURE_5_CANDIDATES,
    getStrategicFoundation: async () => FIXTURE_5_STRATEGIC_FOUNDATION,
  };

  await assert.doesNotReject(
    renderRecommendation(container, { service, state: { caseId: "live" }, drawer: {}, onNavigate: (id) => { navigatedTo = id; } })
  );

  const continueBtn = container.querySelector('[data-action="continue"]');
  assert.ok(continueBtn, "a navigation action must be present even with zero candidates");
  continueBtn.dispatchEvent(new window.Event("click", { bubbles: true }));
  assert.equal(navigatedTo, "evidence");
});
