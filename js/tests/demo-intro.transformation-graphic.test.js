// DemoIntro.js had zero test coverage before this file. Exercises the REAL Wix/HPS seed data
// through the REAL service layer (matching wix-hps.candidate-label-regression.test.js's own
// "no mocking" convention) plus the real (untouched, never-mutated-by-any-other-test-file)
// liveAnalysisService for the live-pre-analysis path.
//
// Several signal tiles (Products, Market position) combine more than one strategicFoundation
// type and pick the highest-confidence match — confidence is RECOMPUTED from evidence links at
// dataset-build time (case-utils.js's recalculateConfidence), not the raw seed's placeholder
// `confidence: 0`, so this file deliberately does not hardcode which of several real candidates
// wins; it only asserts the rendered value is a real truncated prefix of one of them, never the
// generic placeholder. Strategy (way_to_win) has exactly one candidate in both seeds, so that
// tile IS asserted exactly. Output (recommendedDecision / the primary unresolved statement) is
// asserted exactly in full — verifying both the recommendation.detail.recommendedDecision field
// path and that "full recommendation meaning preserved" means literally no truncation there.
import { test } from "node:test";
import assert from "node:assert/strict";
import { setupJSDOM, freshContainer } from "./helpers/dom-setup.js";

setupJSDOM();
const { getAnalysisService } = await import("../analysis-service.js");
const { renderDemoIntro } = await import("../components/DemoIntro.js");

function truncateToWords(text, maxWords) {
  const words = text.trim().split(/\s+/);
  if (words.length <= maxWords) return text.trim();
  return `${words.slice(0, maxWords).join(" ")}…`;
}

async function render(caseId) {
  const container = freshContainer();
  const service = getAnalysisService(caseId);
  await renderDemoIntro(container, {
    service,
    state: { caseId },
    onStart: () => {},
    onSelectCase: () => {},
  });
  return container;
}

test("Wix: removed sections are gone, first-viewport elements are present", async () => {
  const container = await render("wix");

  assert.ok(!container.textContent.includes("StoryMap prototype demo"), "the old eyebrow line must be removed");
  assert.ok(!container.querySelector(".intro-grid"), "'What you are about to see' / decision cards must be removed");
  assert.ok(!container.querySelector(".numbered-list"), "numbered workflow prose must be removed");
  assert.ok(!container.querySelector("section.notice-card"), "the large always-open context panel must be removed");
  assert.ok(!container.textContent.includes("This prototype shows how StoryMap would help answer that question"), "the repeated question sentence must be removed");

  assert.ok(container.querySelector(".case-selector"), "compact case selector must be present");
  const question = container.querySelector("h1.question");
  assert.ok(question, "one dominant strategic question, as the page's real h1");
  assert.equal(container.querySelectorAll("h1").length, 1, "exactly one h1 on the screen");
  assert.ok(container.querySelector(".product-tagline"), "one short product-value sentence must be present");
  assert.ok(container.querySelector(".tg"), "the transformation graphic must be present");
  assert.ok(container.querySelector('[data-action="start"]'), "the primary action must be present");
  assert.ok(container.querySelector(".about-disclosure"), "the compact About-this-demonstration disclosure must be present");
  assert.ok(!container.querySelector(".tg-skip"), "no skip-animation control");
});

test("Wix: signal tiles and output are derived from the real seeded dataset", async () => {
  const container = await render("wix");
  const service = getAnalysisService("wix");
  const [foundation, recommendation, evidenceIndex] = await Promise.all([
    service.getStrategicFoundation(),
    service.getRecommendation(),
    service.getEvidenceIndex(),
  ]);

  const tiles = [...container.querySelectorAll(".tg-signal")];
  const byLabel = Object.fromEntries(tiles.map((t) => [t.querySelector(".tg-signal-label").textContent, t.querySelector(".tg-signal-value").textContent]));

  const wayToWin = foundation.find((c) => c.type === "way_to_win");
  assert.equal(byLabel["Strategy"], truncateToWords(wayToWin.statement, 7), "Strategy tile: Wix has exactly one way_to_win item, so this is deterministic");

  const productCandidates = foundation.filter((c) => ["capability", "proof"].includes(c.type)).map((c) => truncateToWords(c.statement, 7));
  assert.ok(productCandidates.includes(byLabel["Products"]), "Products tile must be a real truncated candidate statement, not invented text");

  const marketCandidates = foundation.filter((c) => ["market", "market_change"].includes(c.type)).map((c) => truncateToWords(c.statement, 7));
  assert.ok(marketCandidates.includes(byLabel["Market position"]), "Market position tile must be a real truncated candidate statement");

  const sourceCount = evidenceIndex.allSourcesWithEvidence().length;
  assert.equal(byLabel["Public evidence"], `${sourceCount} public sources`);

  const narrativeText = container.querySelector(".tg-output-narrative .tg-output-text").textContent;
  assert.equal(narrativeText, recommendation.detail.recommendedDecision, "the recommended direction must be shown in full, verbatim -- no truncation");

  const primaryUnresolved = foundation.filter((c) => c.type === "unresolved" && c.priority === "primary");
  const judgmentText = container.querySelector(".tg-output-judgment .tg-output-text").textContent;
  assert.equal(judgmentText, primaryUnresolved[0].statement, "the leadership judgment must be the first primary unresolved item, in full");
});

test("HPS: output is derived from the real seeded dataset (generalizes beyond Wix)", async () => {
  const container = await render("hps");
  const service = getAnalysisService("hps");
  const [foundation, recommendation, evidenceIndex] = await Promise.all([
    service.getStrategicFoundation(),
    service.getRecommendation(),
    service.getEvidenceIndex(),
  ]);

  const narrativeText = container.querySelector(".tg-output-narrative .tg-output-text").textContent;
  assert.equal(narrativeText, recommendation.detail.recommendedDecision);

  const primaryUnresolved = foundation.filter((c) => c.type === "unresolved" && c.priority === "primary");
  const judgmentText = container.querySelector(".tg-output-judgment .tg-output-text").textContent;
  assert.equal(judgmentText, primaryUnresolved[0].statement);

  const sourceCount = evidenceIndex.allSourcesWithEvidence().length;
  const publicEvidenceTile = [...container.querySelectorAll(".tg-signal")].find((t) => t.querySelector(".tg-signal-label").textContent === "Public evidence");
  assert.equal(publicEvidenceTile.querySelector(".tg-signal-value").textContent, `${sourceCount} public sources`);
});

test("Live, before any analysis has run: renders distinct generic placeholders and never throws", async () => {
  // liveAnalysisService's dataset state is module-level and starts (and, since no other test
  // file in this suite calls startAnalysis/pollJob, stays) null for this whole test run -- see
  // live-analysis-service.js's hasCompletedAnalysis(). If this ever throws, it means the
  // component called getStrategicFoundation/getCandidates/getRecommendation/getEvidenceIndex
  // pre-analysis, which live-analysis-service.js's assertDatasetReady() rejects by design.
  const container = await render("live");

  const tiles = [...container.querySelectorAll(".tg-signal")];
  assert.equal(tiles.length, 4);
  const values = tiles.map((t) => t.querySelector(".tg-signal-value").textContent);
  assert.equal(new Set(values).size, 4, "all four placeholder values must be distinct, not the same repeated filler string");
  values.forEach((v) => assert.ok(!/not yet determined/i.test(v), "must not repeat the StrategicFoundation-screen fallback string"));

  assert.ok(container.querySelector(".tg-output-narrative"), "a narrative placeholder card is still shown");
  assert.ok(container.querySelector(".tg-output-judgment"), "a judgment placeholder card is still shown");
  assert.match(container.querySelector(".tg-output-narrative .tg-output-text").textContent, /will appear here/i);
});

test("reduced motion: .tg-play is never added, content renders already in its final state", async () => {
  const originalMatchMedia = window.matchMedia;
  window.matchMedia = (query) => ({ matches: query.includes("prefers-reduced-motion"), media: query, addListener() {}, removeListener() {} });
  try {
    const container = await render("wix");
    assert.ok(!container.querySelector(".tg.tg-play"), "no animation class under reduced motion");
  } finally {
    window.matchMedia = originalMatchMedia;
  }
});

test("normal motion: the reveal class is applied (non-blocking -- doesn't delay render or the primary action)", async () => {
  const originalMatchMedia = window.matchMedia;
  window.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {} });
  try {
    const container = await render("wix");
    assert.ok(container.querySelector(".tg.tg-play"), "reveal class applied when motion is not reduced");
    const startBtn = container.querySelector('[data-action="start"]');
    assert.ok(startBtn, "primary action exists immediately, not gated behind animation completion");
    assert.notEqual(getComputedStyleFallback(startBtn), "none", "primary action is not display:none");
  } finally {
    window.matchMedia = originalMatchMedia;
  }
});

// jsdom has no real layout engine (see responsive.single-column.test.js's own note on this) --
// this only guards against the button being hidden via the `hidden` attribute or display:none
// inline style, not real CSS cascade.
function getComputedStyleFallback(el) {
  return el.hidden ? "none" : (el.style && el.style.display) || "";
}

test("case selection and start are still wired the same as before", async () => {
  let selected = null;
  let started = false;
  const container = freshContainer();
  const service = getAnalysisService("wix");
  await renderDemoIntro(container, {
    service,
    state: { caseId: "wix" },
    onStart: () => { started = true; },
    onSelectCase: (id) => { selected = id; },
  });

  const hpsOption = [...container.querySelectorAll(".case-option")].find((o) => o.textContent.includes("Hammond Power Solutions"));
  hpsOption.click();
  assert.equal(selected, "hps");

  container.querySelector('[data-action="start"]').click();
  assert.ok(started);
});
