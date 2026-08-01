import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM, freshContainer } from "./helpers/dom-setup.js";

setupJSDOM();
// Must be set BEFORE the dynamic import below -- live-analysis-service.js's
// checkBackendAvailable() calls the global fetch, and AnalyzeCompany.js calls it
// synchronously during its own render.
globalThis.fetch = async () => {
  throw new Error("network error — backend unreachable");
};
const { renderAnalyzeCompany } = await import("../components/AnalyzeCompany.js");

test("backend-unavailable state produces the controlled, disabled-form message, never the generic app.js catch-all", async () => {
  const container = freshContainer();

  await assert.doesNotReject(renderAnalyzeCompany(container, { onNavigate: () => {} }));

  const text = container.textContent;
  assert.match(text, /Live analysis requires a backend/);
  assert.doesNotMatch(text, /Something went wrong loading this screen/);

  const submitBtn = container.querySelector('[data-action="submit"]');
  assert.ok(submitBtn, "submit button must still be present, just disabled");
  assert.equal(submitBtn.disabled, true);
});
