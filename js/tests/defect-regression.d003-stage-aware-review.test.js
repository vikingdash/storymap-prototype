// Regression test for D-003 (Level 1 internal testing, 2026-08-02): the "needs your attention"
// review strip flagged items by raw confidence < 0.5, regardless of narrativeStage -- so a
// strategic_direction claim with genuinely moderate directional credibility got swept into the
// same bucket as real open leadership decisions, purely because its present-state confidence is
// naturally (and correctly) low for a forward-looking claim. Fixed in
// StrategicFoundation.js's buildReviewList: proven_today/emerging/in_build items are still
// judged by confidence (unchanged); strategic_direction items are now judged by
// directionalCredibility against its own floor; aspiration_pending_leadership items are always
// surfaced (tag "approval"), never gated by a number, since leadership approval is genuinely
// required by definition of that stage.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM } from "./helpers/dom-setup.js";

setupJSDOM();
const { buildReviewList } = await import("../components/StrategicFoundation.js");
const { WIX_DATASET } = await import("../cases/wix-case-data.js");
const { HPS_DATASET } = await import("../cases/hps-case-data.js");

function choice(overrides) {
  return {
    id: "sc1", type: "capability", statement: "x", statementType: "source_fact",
    narrativeStage: "proven_today", confidence: 0.9, directionalCredibility: undefined,
    evidence: [], approvalStatus: "unreviewed",
    ...overrides,
  };
}

test("D-003: a strategic_direction item with moderate directional credibility is NOT flagged, even though its confidence is low", () => {
  const c = choice({ narrativeStage: "strategic_direction", confidence: 0.48, directionalCredibility: 0.48 });
  const list = buildReviewList([c], {});
  assert.equal(list.length, 0, "moderate directional credibility (>= 0.4) must not trigger review -- that's the exact D-003 failure mode");
});

test("D-003: a strategic_direction item with genuinely LIMITED directional credibility IS flagged", () => {
  const c = choice({ narrativeStage: "strategic_direction", confidence: 0.2, directionalCredibility: 0.2 });
  const list = buildReviewList([c], {});
  assert.equal(list.length, 1);
  assert.equal(list[0].tag, "confirm");
});

test("D-003: an aspiration_pending_leadership item is always flagged, regardless of any number", () => {
  const c = choice({ narrativeStage: "aspiration_pending_leadership", confidence: 0.9, directionalCredibility: 0.9 });
  const list = buildReviewList([c], {});
  assert.equal(list.length, 1, "leadership approval is required by definition of this stage, not by a confidence threshold");
  assert.equal(list[0].tag, "approval");
});

test("D-003: proven_today/emerging/in_build items are still judged by confidence, exactly as before (no regression on the working half of the old logic)", () => {
  const weak = choice({ narrativeStage: "in_build", confidence: 0.3 });
  const strong = choice({ id: "sc2", narrativeStage: "proven_today", confidence: 0.9 });
  const list = buildReviewList([weak, strong], {});
  assert.equal(list.length, 1);
  assert.equal(list[0].item.id, "sc1");
  assert.equal(list[0].tag, "confirm");
});

test("D-003: conflicting evidence still takes priority over stage-based flagging, unchanged", () => {
  const c = choice({
    narrativeStage: "strategic_direction", directionalCredibility: 0.9,
    evidence: [{ evidenceId: "e1", relevance: "conflicting", rationale: "x" }],
  });
  const list = buildReviewList([c], {});
  assert.equal(list.length, 1);
  assert.equal(list[0].tag, "conflicting", "conflicting evidence must win regardless of otherwise-strong directional credibility");
});

test("D-003 against the real seed data: Wix's sc_assumption_1 no longer appears in the review list", () => {
  const list = buildReviewList(WIX_DATASET.strategicFoundation, {});
  assert.ok(!list.some((entry) => entry.item.id === "sc_assumption_1"), "the exact item the original D-003 bug report named must no longer be flagged");
});

test("D-003 against the real seed data: HPS's sc_hps_assumption no longer appears in the review list", () => {
  const list = buildReviewList(HPS_DATASET.strategicFoundation, {});
  assert.ok(!list.some((entry) => entry.item.id === "sc_hps_assumption"), "the exact item the original D-003 bug report named must no longer be flagged");
});

test("D-003 against real seed data: genuine leadership decisions and risks are still surfaced, unaffected by the fix", () => {
  const wixList = buildReviewList(WIX_DATASET.strategicFoundation, {});
  assert.ok(wixList.some((e) => e.item.id === "sc_unresolved_scope" && e.tag === "decision"));
  assert.ok(wixList.some((e) => e.item.id === "sc_risk_1" && e.tag === "risk"));
});
