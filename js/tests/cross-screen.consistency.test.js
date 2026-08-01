import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM, freshContainer } from "./helpers/dom-setup.js";
import { FIXTURE_1_CANDIDATES, FIXTURE_1_RECOMMENDATION, stubEvidenceIndex } from "./helpers/fixtures.js";

setupJSDOM();
const { renderNarrativeChoices } = await import("../components/NarrativeChoices.js");
const { renderRecommendation } = await import("../components/Recommendation.js");
const { renderNarrativeMapView } = await import("../components/NarrativeMapView.js");

const FIXTURE_1_MAP = {
  id: "map1", companyId: "live", version: 1, status: "draft", candidateId: "cand1",
  coreNarrative: "x",
  sevenParts: { context: "x", tension: "x", belief: "x", role: "x", value: "x", proof: "x", direction: "x" },
  coreClaims: [], audienceIds: [], competitorContrastIds: [], likelyObjections: [],
  weakOrUnsupportedClaims: [], unresolvedQuestions: [], createdAt: "2026-01-01T00:00:00Z",
};

function buildService() {
  return {
    getCandidates: async () => FIXTURE_1_CANDIDATES,
    getRecommendation: async () => FIXTURE_1_RECOMMENDATION,
    getStrategicFoundation: async () => [],
    getNarrativeMap: async () => FIXTURE_1_MAP,
    getAudiences: async () => [],
    getCompetitorContrasts: async () => [],
    getEvidenceIndex: async () => stubEvidenceIndex(),
  };
}

test("Narrative Choices, Recommendation, and Narrative Map all agree on which candidate is selected, from the same fixture", async () => {
  const service = buildService();
  const drawer = { openEvidenceLinks: () => {}, openEvidenceLink: () => {} };

  const choicesContainer = freshContainer();
  await renderNarrativeChoices(choicesContainer, { service, drawer, onNavigate: () => {} });
  const recommendedCards = [...choicesContainer.querySelectorAll(".candidate-card")].filter((c) => c.classList.contains("recommended"));
  assert.equal(recommendedCards.length, 1, "exactly one card must be marked recommended");
  assert.match(recommendedCards[0].textContent, /The Selected Direction/);
  assert.match(recommendedCards[0].textContent, /Recommended/);

  const recContainer = freshContainer();
  await renderRecommendation(recContainer, { service, state: { caseId: "live" }, drawer, onNavigate: () => {} });
  assert.match(recContainer.textContent, /The Selected Direction/);

  const mapContainer = freshContainer();
  await renderNarrativeMapView(mapContainer, { service, state: { caseId: "live", narrativeApproved: false }, drawer, onNavigate: () => {} });
  assert.doesNotMatch(mapContainer.textContent, /No Narrative Map yet/);
  assert.doesNotMatch(mapContainer.textContent, /needs another attempt/);
});
