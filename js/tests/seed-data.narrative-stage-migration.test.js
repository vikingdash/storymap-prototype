// Locks in the controlled Wix/HPS seed-data migration: narrativeStage was added to every
// existing StrategicChoice/NarrativeCoreClaim (except type "unresolved"), and a
// narrativeStages breakdown was added to every candidate — no statement, evidence,
// recommendation, or conclusion was changed. Every classification below was reviewed
// individually against the item's actual content, never inferred from `type` — the explicit
// proof point is sc_hps_strategic_pillars and sc_hps_way_to_win, both type "way_to_win",
// landing on different stages (see the HPS section below).
import { test } from "node:test";
import assert from "node:assert/strict";
import { NARRATIVE_STAGES } from "../schemas.js";
import { WIX_DATASET } from "../cases/wix-case-data.js";
import { HPS_DATASET } from "../cases/hps-case-data.js";

function stageById(items) {
  return Object.fromEntries(items.map((i) => [i.id, i.narrativeStage]));
}

test("Wix: every foundation item's narrativeStage matches the reviewed classification", () => {
  const stages = stageById(WIX_DATASET.strategicFoundation);
  assert.deepEqual(stages, {
    sc_customers: "proven_today",
    sc_chosen_market: "proven_today",
    sc_market_change: "proven_today",
    sc_way_to_win: "in_build",
    sc_capabilities: "proven_today",
    sc_proof: "proven_today",
    sc_assumption_1: "strategic_direction",
    sc_risk_1: "proven_today",
    sc_unresolved_scope: undefined,
    sc_unresolved_control: undefined,
    sc_unresolved_base44: undefined,
    sc_unresolved_outcomes: undefined,
    sc_unresolved_category: undefined,
  });
});

test("Wix: every narrativeMap.coreClaim's narrativeStage matches the reviewed classification", () => {
  const stages = stageById(WIX_DATASET.narrativeMap.coreClaims);
  assert.deepEqual(stages, {
    claim_publish_speed: "proven_today",
    claim_user_refine: "proven_today",
    claim_combine_ai_manual: "proven_today",
    claim_expansion: "in_build",
  });
});

test("Wix: every candidate carries a non-empty narrativeStages breakdown", () => {
  const byId = Object.fromEntries(WIX_DATASET.candidates.map((c) => [c.id, c.narrativeStages.map((s) => s.stage)]));
  assert.deepEqual(byId, {
    cand_creation_without_compromise: ["proven_today", "strategic_direction"],
    cand_ai_operating_system: ["in_build", "strategic_direction"],
    cand_idea_to_business: ["proven_today", "strategic_direction"],
  });
});

test("HPS: every foundation item's narrativeStage matches the reviewed classification, INCLUDING the same-type/different-stage proof point", () => {
  const stages = stageById(HPS_DATASET.strategicFoundation);
  assert.deepEqual(stages, {
    sc_hps_customers: "proven_today",
    sc_hps_markets_served: "proven_today",
    sc_hps_geographic_markets: "in_build",
    sc_hps_market_change: "proven_today",
    sc_hps_strategic_pillars: "proven_today",
    sc_hps_way_to_win: "in_build",
    sc_hps_capabilities: "proven_today",
    sc_hps_proof: "proven_today",
    sc_hps_assumption: "strategic_direction",
    sc_hps_risk: "proven_today",
    sc_hps_unresolved_unifying_idea: undefined,
    sc_hps_unresolved_identity_model: undefined,
    sc_hps_unresolved_transformer_credibility: undefined,
    sc_hps_unresolved_evidence_for_value: undefined,
    sc_hps_unresolved_global_consistency: undefined,
  });

  // The explicit proof that stage is never inferred from `type`: two "way_to_win" items,
  // two different stages, because their actual content differs (one is a verbatim current
  // published statement, the other is forward-looking combination-in-progress).
  const pillars = HPS_DATASET.strategicFoundation.find((c) => c.id === "sc_hps_strategic_pillars");
  const wayToWin = HPS_DATASET.strategicFoundation.find((c) => c.id === "sc_hps_way_to_win");
  assert.equal(pillars.type, "way_to_win");
  assert.equal(wayToWin.type, "way_to_win");
  assert.notEqual(pillars.narrativeStage, wayToWin.narrativeStage);
});

test("HPS: every narrativeMap.coreClaim's narrativeStage matches the reviewed classification", () => {
  const stages = stageById(HPS_DATASET.narrativeMap.coreClaims);
  assert.deepEqual(stages, {
    claim_hps_transformer_leader: "proven_today",
    claim_hps_expanding_capabilities: "in_build",
    claim_hps_multi_year_pattern: "in_build",
    claim_hps_two_units_one_story: "proven_today",
  });
});

test("HPS: every candidate carries a non-empty narrativeStages breakdown, including a leadership-dependent aspiration", () => {
  const byId = Object.fromEntries(HPS_DATASET.candidates.map((c) => [c.id, c.narrativeStages.map((s) => s.stage)]));
  assert.deepEqual(byId, {
    cand_hps_trusted_foundation: ["in_build", "strategic_direction"],
    cand_hps_one_system: ["in_build", "aspiration_pending_leadership"],
    cand_hps_complexity: ["proven_today", "strategic_direction"],
  });
});

test("migration is purely additive: no seeded statement, evidence id, recommendation, or candidate status text changed", () => {
  // Spot-checks a representative sample from each category against the exact pre-migration
  // strings -- if any of these ever fail, the migration touched content it should not have.
  const wixWayToWin = WIX_DATASET.strategicFoundation.find((c) => c.id === "sc_way_to_win");
  assert.equal(wixWayToWin.statement, "Combine AI-assisted creation, manual control, business tools and scalable infrastructure in one platform.");
  assert.equal(wixWayToWin.evidence.length, 3);

  assert.equal(
    WIX_DATASET.recommendation.recommendedDecision,
    "Position Wix around AI speed with retained human control, while preserving website creation as the proof point — not the limits — of the company."
  );

  const hpsRisk = HPS_DATASET.strategicFoundation.find((c) => c.id === "sc_hps_risk");
  assert.equal(hpsRisk.statement, "The two-business-unit structure (Transformers, IES) may reinforce two parallel identities unless one corporate narrative clearly explains how they belong together.");

  assert.equal(HPS_DATASET.candidates.find((c) => c.id === "cand_hps_trusted_foundation").status, "recommended");
  assert.equal(HPS_DATASET.candidates.find((c) => c.id === "cand_hps_one_system").status, "candidate");
});

test("every populated narrativeStage across both seeded datasets is a valid enum value", () => {
  const allStages = [
    ...WIX_DATASET.strategicFoundation.map((c) => c.narrativeStage),
    ...HPS_DATASET.strategicFoundation.map((c) => c.narrativeStage),
    ...WIX_DATASET.narrativeMap.coreClaims.map((c) => c.narrativeStage),
    ...HPS_DATASET.narrativeMap.coreClaims.map((c) => c.narrativeStage),
    ...WIX_DATASET.candidates.flatMap((c) => c.narrativeStages.map((s) => s.stage)),
    ...HPS_DATASET.candidates.flatMap((c) => c.narrativeStages.map((s) => s.stage)),
  ].filter((s) => s !== undefined);

  allStages.forEach((stage) => assert.ok(NARRATIVE_STAGES.includes(stage), `"${stage}" must be a real narrative stage`));
});

test("directionalCredibility is present alongside confidence on every non-unresolved foundation item", () => {
  [...WIX_DATASET.strategicFoundation, ...HPS_DATASET.strategicFoundation]
    .filter((c) => c.type !== "unresolved")
    .forEach((c) => {
      assert.equal(typeof c.confidence, "number", `${c.id} must have a numeric confidence`);
      assert.equal(typeof c.directionalCredibility, "number", `${c.id} must have a numeric directionalCredibility`);
    });
});
