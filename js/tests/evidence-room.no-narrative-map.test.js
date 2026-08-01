import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM, freshContainer } from "./helpers/dom-setup.js";
import { FIXTURE_2_CANDIDATES, FIXTURE_5_STRATEGIC_FOUNDATION, stubEvidenceIndex } from "./helpers/fixtures.js";

setupJSDOM();
const { renderEvidenceRoom } = await import("../components/EvidenceRoom.js");

test("Evidence Room renders when narrativeMap is null, with foundation/diagnosis/candidate/source evidence still available", async () => {
  const container = freshContainer();
  const service = {
    getEvidenceIndex: async () => stubEvidenceIndex(),
    getStrategicFoundation: async () => FIXTURE_5_STRATEGIC_FOUNDATION,
    getDiagnosis: async () => [],
    getCandidates: async () => FIXTURE_2_CANDIDATES,
    getNarrativeMap: async () => null,
  };

  await assert.doesNotReject(renderEvidenceRoom(container, { service, state: { caseId: "live" }, onNavigate: () => {} }));

  const text = container.textContent;
  assert.match(text, /Every source behind this analysis/);
  assert.doesNotMatch(text, /\bundefined\b/);
  assert.doesNotMatch(text, /\bnull\b/);
});
