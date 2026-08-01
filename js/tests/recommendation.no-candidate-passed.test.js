import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM, freshContainer } from "./helpers/dom-setup.js";
import { FIXTURE_3_CANDIDATES, FIXTURE_3_RECOMMENDATION } from "./helpers/fixtures.js";

setupJSDOM();
const { renderRecommendation } = await import("../components/Recommendation.js");

test("no_candidate_passed uses distinct wording from stage_failed and displays zero viable candidates", async () => {
  const container = freshContainer();
  const service = {
    getRecommendation: async () => FIXTURE_3_RECOMMENDATION,
    getCandidates: async () => FIXTURE_3_CANDIDATES,
    getStrategicFoundation: async () => [],
  };

  await renderRecommendation(container, { service, state: { caseId: "live" }, drawer: {}, onNavigate: () => {} });

  const text = container.textContent;
  assert.match(text, /StoryMap cannot yet recommend a direction/);
  assert.doesNotMatch(text, /The final recommendation needs another attempt/);
  assert.doesNotMatch(text, /Viable alternative/);
  assert.doesNotMatch(text, /Recommended/);
  assert.ok(!container.querySelector('[data-action="retry-recommendation"]'), "no retry action on this distinct screen");
});
