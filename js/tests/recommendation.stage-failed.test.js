import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM, freshContainer } from "./helpers/dom-setup.js";
import { FIXTURE_2_CANDIDATES, FIXTURE_2_RECOMMENDATION } from "./helpers/fixtures.js";

setupJSDOM();
const { renderRecommendation } = await import("../components/Recommendation.js");

test("stage_failed shows the final-step retry message and preserves actual candidate statuses", async () => {
  const container = freshContainer();
  const service = {
    getRecommendation: async () => FIXTURE_2_RECOMMENDATION,
    getCandidates: async () => FIXTURE_2_CANDIDATES,
    getStrategicFoundation: async () => [],
  };

  await renderRecommendation(container, { service, state: { caseId: "live" }, drawer: {}, onNavigate: () => {} });

  const text = container.textContent;
  assert.match(text, /The final recommendation needs another attempt/);
  assert.match(text, /The earlier analysis and viable directions are preserved/);
  assert.match(text, /The Proven Specialist/);
  assert.match(text, /The Emerging Platform/);
  assert.match(text, /The Challenger/);
  assert.match(text, /Viable/);
  assert.match(text, /Rejected/);
  assert.ok(container.querySelector('[data-action="retry-recommendation"]'), "retry action must be present");
});
