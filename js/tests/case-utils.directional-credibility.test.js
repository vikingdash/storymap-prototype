// case-utils.js's JS mirror of confidence.py's competitor-source exclusion and
// directionalCredibility split (governing narrative-stage decisions: rule 9 and decision 2).
// computeConfidenceFromLinks/computeDirectionalCredibility are module-private, so this drives
// them the same way the real app does: through buildCaseDataset() on a minimal synthetic
// dataset, exactly as the seeded Wix/HPS cases are built.
import { test } from "node:test";
import assert from "node:assert/strict";
import { buildCaseDataset, NO_DIRECT_EVIDENCE_CONFIDENCE, MAX_CONFIDENCE, DIRECTIONAL_CREDIBILITY_CAP } from "../case-utils.js";

function minimalDataset(foundationEvidenceLink) {
  return {
    caseContext: {},
    sources: [
      { id: "s1", companyId: "c", title: "T", sourceType: "website", retrievedAt: "x", permissionStatus: "approved" },
      { id: "s2", companyId: "c", title: "T", sourceType: "competitor", retrievedAt: "x", permissionStatus: "approved" },
    ],
    evidence: [
      { id: "e1", sourceId: "s1", excerpt: "x", paraphrase: "x", evidenceType: "x", strength: "strong", freshness: "current", confidence: 0.9, supportsIds: [] },
      { id: "e2", sourceId: "s2", excerpt: "x", paraphrase: "x", evidenceType: "x", strength: "strong", freshness: "current", confidence: 0.9, supportsIds: [] },
    ],
    strategicFoundation: [
      {
        id: "sc1", type: "capability", statement: "x", statementType: "source_fact", narrativeStage: "strategic_direction",
        evidence: [foundationEvidenceLink], approvalStatus: "unreviewed",
      },
    ],
    diagnosis: [],
    candidates: [],
    narrativeMap: {
      id: "m", companyId: "c", version: 1, status: "draft", candidateId: "x", coreNarrative: "x",
      sevenParts: { context: "x", tension: "x", belief: "x", role: "x", value: "x", proof: "x", direction: "x" },
      coreClaims: [], audienceIds: [], competitorContrastIds: [], unresolvedQuestions: [], createdAt: "x",
    },
    competitorContrasts: [],
    audiences: [],
  };
}

test("a competitor-sourced link labeled 'direct' never raises confidence, even though the model/case file said 'direct'", () => {
  const ds = buildCaseDataset(minimalDataset({ evidenceId: "e2", relevance: "direct", rationale: "x" }));
  assert.equal(ds.strategicFoundation[0].confidence, NO_DIRECT_EVIDENCE_CONFIDENCE);
});

test("the identical link, company-sourced instead, does raise confidence", () => {
  const ds = buildCaseDataset(minimalDataset({ evidenceId: "e1", relevance: "direct", rationale: "x" }));
  assert.ok(ds.strategicFoundation[0].confidence > NO_DIRECT_EVIDENCE_CONFIDENCE);
});

test("the same competitor-sourced link DOES contribute to directionalCredibility", () => {
  const ds = buildCaseDataset(minimalDataset({ evidenceId: "e2", relevance: "direct", rationale: "x" }));
  assert.ok(ds.strategicFoundation[0].directionalCredibility > NO_DIRECT_EVIDENCE_CONFIDENCE);
});

test("directionalCredibility's ceiling is strictly lower than confidence's — a direction is never shown as more certain than a fact", () => {
  assert.ok(DIRECTIONAL_CREDIBILITY_CAP < MAX_CONFIDENCE);
});

test("unresolved items never get a confidence or directionalCredibility computed", () => {
  const raw = minimalDataset({ evidenceId: "e1", relevance: "direct", rationale: "x" });
  raw.strategicFoundation.push({
    id: "sc2", type: "unresolved", statement: "x?", statementType: "leadership_decision",
    evidence: [], confidence: 0, approvalStatus: "unreviewed",
  });
  const ds = buildCaseDataset(raw);
  const unresolved = ds.strategicFoundation.find((c) => c.id === "sc2");
  assert.equal(unresolved.directionalCredibility, undefined);
});
