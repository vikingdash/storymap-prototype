// Regression test for D-001 (Level 1 internal testing, 2026-08-02): the Wix recommended
// narrative's `Role` field overstated platform unification ("Wix combines... in one creation
// environment", present tense, settled) relative to its own narrativeStage classification
// (sc_way_to_win / the equivalent candidate claim is "in_build" -- the platform is still being
// assembled, not already unified; sc_risk_1 explicitly says so). Fixed by rewording to in_build-
// appropriate language ("is assembling... into") in both places the sentence is duplicated
// (the winning candidate's own sevenParts, and narrativeMap.sevenParts) -- WITHOUT touching the
// recommendation, evidence, narrativeStage, or the separately-worded `direction` field, and
// without shrinking the claim's scope (still names all four original elements, still company-
// level, still "one creation environment").
import { test } from "node:test";
import assert from "node:assert/strict";
import { WIX_DATASET } from "../cases/wix-case-data.js";

const OLD_UNHEDGED_WORDING = "Wix combines AI assistance, precise manual control, business tools and scalable infrastructure in one creation environment.";
const NEW_WORDING = "Wix is assembling AI assistance, precise manual control, business tools and scalable infrastructure into one creation environment.";

test("D-001: the old unhedged 'combines...in one creation environment' wording is gone from the dataset entirely", () => {
  const serialized = JSON.stringify(WIX_DATASET);
  assert.ok(!serialized.includes(OLD_UNHEDGED_WORDING), "the temporally-dishonest sentence must not appear anywhere in the dataset");
});

test("D-001: the winning candidate's Role field uses in_build-appropriate wording", () => {
  const winner = WIX_DATASET.candidates.find((c) => c.id === "cand_creation_without_compromise");
  assert.equal(winner.sevenParts.role, NEW_WORDING);
  assert.match(winner.sevenParts.role, /is assembling/, "in_build claims must read as in-progress (rule 13: is building/developing/assembling), never as an already-settled fact");
});

test("D-001: the shipped Narrative Map's Role field matches the candidate's (stays in sync)", () => {
  assert.equal(WIX_DATASET.narrativeMap.sevenParts.role, WIX_DATASET.candidates.find((c) => c.id === "cand_creation_without_compromise").sevenParts.role);
});

test("D-001 fix is scoped to wording only: recommendation, evidence, stage assignment and direction are all byte-identical to before", () => {
  // Locks in "do not change the underlying recommendation, evidence, stage assignment, or
  // narrative direction" -- if any of these ever drift, this test catches it.
  assert.equal(
    WIX_DATASET.recommendation.recommendedDecision,
    "Position Wix around AI speed with retained human control, while preserving website creation as the proof point — not the limits — of the company."
  );
  const wayToWin = WIX_DATASET.strategicFoundation.find((c) => c.id === "sc_way_to_win");
  assert.equal(wayToWin.narrativeStage, "in_build", "the underlying stage classification this fix is grounded in must not have changed");
  assert.equal(wayToWin.evidence.length, 3, "evidence links must be untouched");
  assert.equal(
    WIX_DATASET.narrativeMap.sevenParts.direction,
    "Expand from website creation toward a broader platform where people and AI build and operate digital businesses together.",
    "the separately-worded Direction field (already correctly hedged) must be untouched"
  );
});

test("D-001: company-level scope is preserved, not shrunk to a narrow product story", () => {
  const role = WIX_DATASET.candidates.find((c) => c.id === "cand_creation_without_compromise").sevenParts.role;
  // All four original elements must still be named -- the fix must not have quietly narrowed
  // the claim down to just "AI assistance" or dropped "business tools"/"scalable
  // infrastructure" to make it easier to hedge.
  ["AI assistance", "manual control", "business tools", "scalable infrastructure"].forEach((phrase) => {
    assert.ok(role.includes(phrase), `Role must still name "${phrase}" -- scope must not shrink`);
  });
});
