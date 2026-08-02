// Typed data shapes for the StoryMap prototype (see STORYMAP_CLAUDE_CODE_EXECUTION_PACK.md, section 6).
//
// This sandbox has no Node.js/npm, so the pack's suggested Zod dependency cannot be installed.
// This module is a dependency-free stand-in: it defines the same shapes as plain JSDoc typedefs
// and provides small runtime validators that check every seeded record on load, throwing a
// descriptive error the moment a required field is missing or a value falls outside its enum.
// Swapping in real Zod later is a mechanical change — call sites only need `validateX(record)`.

/**
 * "storymap_synthesis" is distinct from "storymap_inference": a synthesis combines several
 * atomic source facts into one summary statement without adding interpretive judgment beyond
 * aggregation (e.g. "faster site creation, strong Aria adoption, and Base44 approaching $150M
 * ARR" — each clause is separately traceable to one excerpt). An inference draws a conclusion
 * that goes beyond what any cited source states outright. Labeling a synthesis as "source_fact"
 * is misleading because no single excerpt says the combined sentence — see
 * STATEMENT_TYPE_LABELS below and StrategicFoundation.js's atomic-fact breakdown.
 * @typedef {"source_fact"|"storymap_inference"|"storymap_synthesis"|"recommendation"|"leadership_decision"|"aspiration"} StatementType
 */

/**
 * @typedef {Object} SourceDocument
 * @property {string} id
 * @property {string} companyId
 * @property {string} title
 * @property {string} [publisher]
 * @property {"internal"|"website"|"press_release"|"earnings"|"interview"|"customer_research"|"competitor"|"other"} sourceType
 * @property {string} [url]
 * @property {string} [publishedAt]
 * @property {string} retrievedAt
 * @property {string} [rawText]
 * @property {"approved"|"restricted"|"unknown"} permissionStatus
 */

/**
 * @typedef {Object} EvidenceItem
 * @property {string} id
 * @property {string} sourceId
 * @property {string} excerpt
 * @property {string} paraphrase
 * @property {string} evidenceType
 * @property {"strong"|"moderate"|"weak"|"unsupported"} strength
 * @property {"current"|"aging"|"stale"} freshness
 * @property {number} confidence
 * @property {string} [scope]
 * @property {string[]} supportsIds
 */

/**
 * How a specific piece of evidence relates to the specific statement it's attached to. Evidence
 * being real and evidence being *relevant to this exact claim* are different questions — an
 * EvidenceLink answers the second one. "direct"/"partial" evidence is allowed to raise a
 * statement's confidence; "context"/"conflicting" evidence is not (see recalculateConfidence in
 * case-utils.js). "company_position" is a fifth value, live-flow-only: the backend
 * (pipeline_runner.sanitize_links) deterministically downgrades a "direct" link to this when its
 * evidence came from a source with documentRole "current_draft_narrative" — the draft directly
 * states the claim, but that is not independent proof it's true, so (like "context"/"conflicting")
 * it must never raise confidence either. Never produced by Wix/HPS's static seed data.
 * @typedef {"direct"|"partial"|"context"|"conflicting"|"company_position"} EvidenceRelevance
 */

/**
 * @typedef {Object} EvidenceLink
 * @property {string} evidenceId
 * @property {EvidenceRelevance} relevance
 * @property {string} rationale — the logical connection: why (or how weakly) this source bears on this exact statement
 */

/**
 * Temporal/maturity axis — orthogonal to statementType (how do we know this — epistemic)
 * and to a StrategicChoice's own `type` (what kind of claim this is). narrativeStage
 * answers "when is this true." A claim can be storymap_synthesis + in_build at once: both
 * axes are real and independent, neither implies the other. Model-classified for the live
 * pipeline, never inferred from `type` — a "capability" can be proven_today, emerging, or
 * in_build; a "way_to_win" can describe current advantage or future intent. Required on
 * every StrategicChoice/NarrativeCoreClaim except type "unresolved" (a leadership decision
 * about a story gap has no temporal status, exactly like it has no evidence model).
 * @typedef {"proven_today"|"emerging"|"in_build"|"strategic_direction"|"aspiration_pending_leadership"} NarrativeStage
 */

/**
 * @typedef {Object} StrategicChoice
 * @property {string} id
 * @property {"customer"|"market"|"market_change"|"way_to_win"|"capability"|"proof"|"assumption"|"risk"|"unresolved"} type
 * @property {string} statement
 * @property {StatementType} statementType
 * @property {EvidenceLink[]} evidence
 * @property {number} confidence — evidence strength for what's actually claimed (unchanged meaning/formula); the authoritative number only for narrativeStage "proven_today", "emerging" and "in_build"
 * @property {number} [directionalCredibility] — present only for narrativeStage "strategic_direction"/"aspiration_pending_leadership": how credible the stated DIRECTION is (intent, commitment, market logic), never "how sure are we this already exists" — see case-utils.js
 * @property {NarrativeStage} [narrativeStage] — required for every type except "unresolved"
 * @property {"unreviewed"|"approved"|"edited"|"rejected"} approvalStatus
 * @property {"primary"|"secondary"} [priority] — only meaningful for type "unresolved": which leadership decisions are shown up front vs. under "Additional questions"
 */

/**
 * @typedef {Object} DiagnosisFinding
 * @property {string} id
 * @property {string} title
 * @property {string} explanation
 * @property {"high"|"medium"|"low"} significance
 * @property {StatementType} statementType
 * @property {EvidenceLink[]} evidence
 * @property {number} confidence
 * @property {"primary"|"secondary"} [priority] — which findings show up front vs. under "Additional findings"
 */

/**
 * One claim behind a candidate's narrative, tagged with its maturity — this is the
 * analytical-infrastructure layer (rationale/evidence view), never the primary narrative
 * document itself (the seven-part story stays the user-facing narrative; see
 * NarrativeCandidate.sevenParts). Used to build the compact per-candidate stage-mix
 * summary ("3 proven · 2 in build · 1 direction") and to feed the company-altitude /
 * direction-coverage checks — never rendered as a per-claim badge list on its own.
 * @typedef {Object} NarrativeStageEntry
 * @property {NarrativeStage} stage
 * @property {string} statement
 * @property {EvidenceLink[]} evidence
 */

/**
 * @typedef {Object} NarrativeCandidate
 * @property {string} id
 * @property {string} name
 * @property {string} oneSentenceStory
 * @property {{context:string, tension:string, belief:string, role:string, value:string, proof:string, direction:string}} sevenParts
 * @property {string[]} strategicLogic
 * @property {string} customerRelevance
 * @property {string} differentiation
 * @property {string[]} tradeoffs
 * @property {string[]} risks
 * @property {EvidenceLink[]} claims
 * @property {NarrativeStageEntry[]} narrativeStages — the candidate's key claims tagged by maturity; rationale-layer data, not the narrative itself
 * @property {Record<string, number>} scores
 * @property {string[]} criticFindings
 * @property {"candidate"|"recommended"|"rejected"} status
 */

/**
 * One explicit claim the Narrative Map rests on — not a bare evidence citation. "Core claims
 * behind this map" previously showed one chip per evidence item, which for this dataset means
 * "Wix Blog" three times over with no indication of what each one individually proves. A
 * NarrativeCoreClaim names the actual claim in plain language; its evidence links are the proof.
 * @typedef {Object} NarrativeCoreClaim
 * @property {string} id
 * @property {string} statement
 * @property {EvidenceLink[]} evidence
 * @property {NarrativeStage} narrativeStage
 */

/**
 * @typedef {Object} NarrativeMap
 * @property {string} id
 * @property {string} companyId
 * @property {number} version
 * @property {"draft"|"approved"|"active"|"archived"} status
 * @property {string} candidateId
 * @property {string} coreNarrative
 * @property {NarrativeCandidate["sevenParts"]} sevenParts
 * @property {NarrativeCoreClaim[]} coreClaims
 * @property {string[]} audienceIds
 * @property {string[]} competitorContrastIds
 * @property {string[]} unresolvedQuestions
 * @property {string} createdAt
 * @property {string} [approvedAt]
 */

const STATEMENT_TYPES = ["source_fact", "storymap_inference", "storymap_synthesis", "recommendation", "leadership_decision", "aspiration"];
const EVIDENCE_RELEVANCE_TYPES = ["direct", "partial", "context", "conflicting"];
export const NARRATIVE_STAGES = ["proven_today", "emerging", "in_build", "strategic_direction", "aspiration_pending_leadership"];

function fail(schemaName, record, message) {
  const label = record && record.id ? `${schemaName} "${record.id}"` : schemaName;
  throw new Error(`Schema validation failed for ${label}: ${message}`);
}

function requireString(schemaName, record, field, opts = {}) {
  const value = record[field];
  if (opts.optional && (value === undefined || value === null)) return;
  if (typeof value !== "string" || value.trim() === "") {
    fail(schemaName, record, `"${field}" must be a non-empty string`);
  }
}

function requireEnum(schemaName, record, field, allowed) {
  if (!allowed.includes(record[field])) {
    fail(schemaName, record, `"${field}" must be one of ${allowed.join(", ")}, got "${record[field]}"`);
  }
}

function requireArray(schemaName, record, field, opts = {}) {
  const value = record[field];
  if (!Array.isArray(value)) {
    fail(schemaName, record, `"${field}" must be an array`);
  }
  if (opts.itemsAreStrings) {
    value.forEach((item, i) => {
      if (typeof item !== "string") fail(schemaName, record, `"${field}[${i}]" must be a string`);
    });
  }
}

function requireConfidence(schemaName, record, field = "confidence") {
  const value = record[field];
  if (typeof value !== "number" || value < 0 || value > 1) {
    fail(schemaName, record, `"${field}" must be a number between 0 and 1, got ${value}`);
  }
}

export function validateSourceDocument(doc) {
  requireString("SourceDocument", doc, "id");
  requireString("SourceDocument", doc, "companyId");
  requireString("SourceDocument", doc, "title");
  requireEnum("SourceDocument", doc, "sourceType", [
    "internal", "website", "press_release", "earnings", "interview", "customer_research", "competitor", "other",
  ]);
  requireString("SourceDocument", doc, "retrievedAt");
  requireEnum("SourceDocument", doc, "permissionStatus", ["approved", "restricted", "unknown"]);
  return doc;
}

export function validateEvidenceLink(link, schemaName = "EvidenceLink") {
  requireString(schemaName, link, "evidenceId");
  requireEnum(schemaName, link, "relevance", EVIDENCE_RELEVANCE_TYPES);
  requireString(schemaName, link, "rationale");
  return link;
}

function requireEvidenceLinkArray(schemaName, record, field) {
  const value = record[field];
  if (!Array.isArray(value)) {
    fail(schemaName, record, `"${field}" must be an array`);
  }
  value.forEach((link, i) => validateEvidenceLink(link, `${schemaName}.${field}[${i}]`));
}

export function validateEvidenceItem(item) {
  requireString("EvidenceItem", item, "id");
  requireString("EvidenceItem", item, "sourceId");
  requireString("EvidenceItem", item, "excerpt");
  requireString("EvidenceItem", item, "paraphrase");
  requireString("EvidenceItem", item, "evidenceType");
  requireEnum("EvidenceItem", item, "strength", ["strong", "moderate", "weak", "unsupported"]);
  requireEnum("EvidenceItem", item, "freshness", ["current", "aging", "stale"]);
  requireConfidence("EvidenceItem", item);
  requireArray("EvidenceItem", item, "supportsIds", { itemsAreStrings: true });
  return item;
}

export function validateStrategicChoice(choice) {
  requireString("StrategicChoice", choice, "id");
  requireEnum("StrategicChoice", choice, "type", [
    "customer", "market", "market_change", "way_to_win", "capability", "proof", "assumption", "risk", "unresolved",
  ]);
  requireString("StrategicChoice", choice, "statement");
  requireEnum("StrategicChoice", choice, "statementType", STATEMENT_TYPES);
  requireEvidenceLinkArray("StrategicChoice", choice, "evidence");
  requireConfidence("StrategicChoice", choice);
  requireEnum("StrategicChoice", choice, "approvalStatus", ["unreviewed", "approved", "edited", "rejected"]);
  if (choice.type === "unresolved" && choice.priority !== undefined) {
    requireEnum("StrategicChoice", choice, "priority", ["primary", "secondary"]);
  }
  // "unresolved" items are leadership decisions about a story GAP, not claims about the
  // company — they have no temporal status, exactly like they have no evidence model /
  // confidence (case-utils.js's recalculateConfidence skips them the same way).
  if (choice.type !== "unresolved") {
    requireEnum("StrategicChoice", choice, "narrativeStage", NARRATIVE_STAGES);
  }
  return choice;
}

export function validateDiagnosisFinding(finding) {
  requireString("DiagnosisFinding", finding, "id");
  requireString("DiagnosisFinding", finding, "title");
  requireString("DiagnosisFinding", finding, "explanation");
  requireEnum("DiagnosisFinding", finding, "significance", ["high", "medium", "low"]);
  requireEnum("DiagnosisFinding", finding, "statementType", STATEMENT_TYPES);
  requireEvidenceLinkArray("DiagnosisFinding", finding, "evidence");
  requireConfidence("DiagnosisFinding", finding);
  if (finding.priority !== undefined) {
    requireEnum("DiagnosisFinding", finding, "priority", ["primary", "secondary"]);
  }
  return finding;
}

// Shared by NarrativeCandidate.narrativeStages entries — rationale/evidence-layer data,
// never rendered as a per-claim badge on the primary narrative (see NarrativeStageEntry's
// typedef comment above).
function validateNarrativeStageEntry(entry, schemaName) {
  requireEnum(schemaName, entry, "stage", NARRATIVE_STAGES);
  requireString(schemaName, entry, "statement");
  requireEvidenceLinkArray(schemaName, entry, "evidence");
  return entry;
}

export function validateNarrativeCandidate(candidate) {
  requireString("NarrativeCandidate", candidate, "id");
  requireString("NarrativeCandidate", candidate, "name");
  requireString("NarrativeCandidate", candidate, "oneSentenceStory");
  const parts = candidate.sevenParts || {};
  ["context", "tension", "belief", "role", "value", "proof", "direction"].forEach((key) => {
    requireString("NarrativeCandidate.sevenParts", parts, key);
  });
  requireArray("NarrativeCandidate", candidate, "strategicLogic", { itemsAreStrings: true });
  requireString("NarrativeCandidate", candidate, "customerRelevance");
  requireString("NarrativeCandidate", candidate, "differentiation");
  requireArray("NarrativeCandidate", candidate, "tradeoffs", { itemsAreStrings: true });
  requireArray("NarrativeCandidate", candidate, "risks", { itemsAreStrings: true });
  requireEvidenceLinkArray("NarrativeCandidate", candidate, "claims");
  requireArray("NarrativeCandidate", candidate, "narrativeStages");
  candidate.narrativeStages.forEach((entry) => validateNarrativeStageEntry(entry, "NarrativeCandidate.narrativeStages[]"));
  if (typeof candidate.scores !== "object" || candidate.scores === null) {
    fail("NarrativeCandidate", candidate, `"scores" must be an object`);
  }
  requireArray("NarrativeCandidate", candidate, "criticFindings", { itemsAreStrings: true });
  requireEnum("NarrativeCandidate", candidate, "status", ["candidate", "recommended", "rejected"]);
  return candidate;
}

export function validateNarrativeCoreClaim(claim) {
  requireString("NarrativeCoreClaim", claim, "id");
  requireString("NarrativeCoreClaim", claim, "statement");
  requireEvidenceLinkArray("NarrativeCoreClaim", claim, "evidence");
  requireEnum("NarrativeCoreClaim", claim, "narrativeStage", NARRATIVE_STAGES);
  return claim;
}

export function validateNarrativeMap(map) {
  requireString("NarrativeMap", map, "id");
  requireString("NarrativeMap", map, "companyId");
  if (typeof map.version !== "number" || map.version < 1) {
    fail("NarrativeMap", map, `"version" must be a positive number`);
  }
  requireEnum("NarrativeMap", map, "status", ["draft", "approved", "active", "archived"]);
  requireString("NarrativeMap", map, "candidateId");
  requireString("NarrativeMap", map, "coreNarrative");
  const parts = map.sevenParts || {};
  ["context", "tension", "belief", "role", "value", "proof", "direction"].forEach((key) => {
    requireString("NarrativeMap.sevenParts", parts, key);
  });
  requireArray("NarrativeMap", map, "coreClaims");
  map.coreClaims.forEach(validateNarrativeCoreClaim);
  requireArray("NarrativeMap", map, "audienceIds", { itemsAreStrings: true });
  requireArray("NarrativeMap", map, "competitorContrastIds", { itemsAreStrings: true });
  requireArray("NarrativeMap", map, "unresolvedQuestions", { itemsAreStrings: true });
  requireString("NarrativeMap", map, "createdAt");
  return map;
}

export function validateDataset(dataset) {
  dataset.sources.forEach(validateSourceDocument);
  dataset.evidence.forEach(validateEvidenceItem);
  dataset.strategicFoundation.forEach(validateStrategicChoice);
  dataset.diagnosis.forEach(validateDiagnosisFinding);
  dataset.candidates.forEach(validateNarrativeCandidate);
  validateNarrativeMap(dataset.narrativeMap);

  const evidenceIds = new Set(dataset.evidence.map((e) => e.id));
  const sourceIds = new Set(dataset.sources.map((s) => s.id));
  dataset.evidence.forEach((e) => {
    if (!sourceIds.has(e.sourceId)) {
      fail("EvidenceItem", e, `references unknown sourceId "${e.sourceId}"`);
    }
  });
  const checkEvidenceLinkRefs = (schemaName, record, field) => {
    (record[field] || []).forEach((link) => {
      if (!evidenceIds.has(link.evidenceId)) {
        fail(schemaName, record, `references unknown evidenceId "${link.evidenceId}" in "${field}"`);
      }
    });
  };
  dataset.strategicFoundation.forEach((c) => checkEvidenceLinkRefs("StrategicChoice", c, "evidence"));
  dataset.diagnosis.forEach((f) => checkEvidenceLinkRefs("DiagnosisFinding", f, "evidence"));
  dataset.candidates.forEach((c) => checkEvidenceLinkRefs("NarrativeCandidate", c, "claims"));
  dataset.candidates.forEach((c) => c.narrativeStages.forEach((entry) => checkEvidenceLinkRefs("NarrativeCandidate.narrativeStages[]", entry, "evidence")));
  dataset.narrativeMap.coreClaims.forEach((claim) => checkEvidenceLinkRefs("NarrativeCoreClaim", claim, "evidence"));
  (dataset.competitorContrasts || []).forEach((c) => checkEvidenceLinkRefs("CompetitorContrast", c, "evidence"));

  return dataset;
}

export const STATEMENT_TYPE_LABELS = {
  source_fact: "Source-derived fact",
  storymap_inference: "StoryMap inference",
  storymap_synthesis: "StoryMap synthesis",
  recommendation: "StoryMap recommendation",
  leadership_decision: "Leadership decision required",
  aspiration: "Company aspiration (not yet proven)",
};

// Short labels: the evidence drawer prefixes each with its own explicit dimension label
// ("Support for this statement: Direct"), so these shouldn't repeat "support"/"evidence" —
// see EvidenceDrawer.js.
export const EVIDENCE_RELEVANCE_LABELS = {
  direct: "Direct",
  partial: "Partial",
  context: "Context only",
  conflicting: "Conflicting",
  company_position: "Company's stated position",
};

export const NARRATIVE_STAGE_LABELS = {
  proven_today: "Proven today",
  emerging: "Emerging",
  in_build: "In build",
  strategic_direction: "Strategic direction",
  aspiration_pending_leadership: "Aspiration — requires leadership approval",
};
