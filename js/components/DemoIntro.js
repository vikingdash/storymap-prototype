// Screen 1 — Demo introduction. Demonstrates StoryMap rather than explaining it: a compact
// case selector, one dominant strategic question, one product-value sentence, a transformation
// graphic (scattered signals -> StoryMap analysis -> defensible narrative) built from the
// selected case's REAL seeded data, one primary action, and a collapsed disclosure. Also hosts
// the case selector — StoryMap ships with two independent public demonstrations (Wix, Hammond
// Power Solutions) plus a live "Analyze a company" mode, and the user picks one before starting.
import { escapeHtml } from "../labels.js";
import { getAnalysisService, AVAILABLE_CASES } from "../analysis-service.js";
import { hasCompletedAnalysis } from "../live-analysis-service.js";

// Fixed, case-invariant process labels — describes what StoryMap DOES, not company data (the
// same five-ish steps already exist case-invariantly as caseContext.whatStoryMapWillDo, which
// is byte-identical between Wix and HPS; this is that same process, condensed to five words for
// the graphic).
const ANALYSIS_STAGES = ["Understand", "Diagnose", "Compare", "Test evidence", "Recommend"];

// Distinct, meaningful generic copy per signal category for the live case before any analysis
// has run — describes what each category MEANS, not a repeated "not yet determined" filler.
const GENERIC_SIGNALS = {
  strategy: "How the company positions itself competitively.",
  products: "What the company actually offers.",
  market: "Who it serves, and where.",
};

// Same confidence-weighted "best item of a given type" pattern StrategicFoundation.js already
// uses (its own bestItemOfTypes/truncateToWords, not exported) — duplicated locally rather than
// imported, to keep this screen's presentation logic independent of that screen's internals.
function bestItemOfTypes(choices, types) {
  const matches = (choices || []).filter((c) => types.includes(c.type));
  if (!matches.length) return null;
  return [...matches].sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0))[0];
}

function truncateToWords(text, maxWords) {
  const words = (text || "").trim().split(/\s+/);
  if (words.length <= maxWords) return (text || "").trim();
  return `${words.slice(0, maxWords).join(" ")}…`;
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// Builds the graphic's data. For the live case before any analysis has completed, none of
// getStrategicFoundation/getCandidates/getRecommendation/getEvidenceIndex can be called — they
// throw (assertDatasetReady in live-analysis-service.js) until a backend job finishes, and this
// screen is shown BEFORE the user ever reaches the intake form. That path renders distinct,
// honest generic placeholders instead of fabricating company data.
async function buildGraphicData(caseId, service) {
  if (caseId === "live" && !hasCompletedAnalysis()) {
    return {
      signals: [
        { label: "Strategy", value: GENERIC_SIGNALS.strategy },
        { label: "Products", value: GENERIC_SIGNALS.products },
        { label: "Market position", value: GENERIC_SIGNALS.market },
        { label: "Public evidence", value: "Public sources you provide." },
      ],
      narrative: "Your recommended narrative direction will appear here.",
      judgment: "Open leadership questions will appear here.",
    };
  }

  const [foundation, recommendation, evidenceIndex] = await Promise.all([
    service.getStrategicFoundation(),
    service.getRecommendation(),
    service.getEvidenceIndex(),
  ]);

  const strategy = bestItemOfTypes(foundation, ["way_to_win"]);
  const products = bestItemOfTypes(foundation, ["capability", "proof"]);
  const market = bestItemOfTypes(foundation, ["market", "market_change"]);
  const sourceCount = evidenceIndex.allSourcesWithEvidence().length;

  const unresolved = foundation.filter((c) => c.type === "unresolved");
  const primaryUnresolved = unresolved.filter((c) => c.priority === "primary");
  const judgmentItem = primaryUnresolved[0] || unresolved[0] || null;

  // Wix/HPS's decisionAgent (analysis-service.js) already guarantees outcome "success" with a
  // real recommendedDecision whenever this path runs — the null-guard is defensive, never
  // exercised by the seeded cases, and means a genuinely missing recommendation omits the card
  // entirely rather than showing invented text (full recommendation meaning is never truncated
  // or paraphrased — shown exactly as written).
  const detail = recommendation && recommendation.outcome === "success" ? recommendation.detail : null;

  return {
    signals: [
      { label: "Strategy", value: strategy ? truncateToWords(strategy.statement, 7) : GENERIC_SIGNALS.strategy },
      { label: "Products", value: products ? truncateToWords(products.statement, 7) : GENERIC_SIGNALS.products },
      { label: "Market position", value: market ? truncateToWords(market.statement, 7) : GENERIC_SIGNALS.market },
      { label: "Public evidence", value: `${sourceCount} public source${sourceCount === 1 ? "" : "s"}` },
    ],
    narrative: detail ? detail.recommendedDecision : null,
    judgment: judgmentItem ? judgmentItem.statement : null,
  };
}

function renderGraphic(graphicData) {
  const { signals, narrative, judgment } = graphicData;
  return `
    <section class="tg" aria-label="How StoryMap turns scattered signals into a defensible narrative">
      <div class="tg-flow">
        <div class="tg-zone">
          <div class="tg-zone-label">Scattered signals</div>
          <div class="tg-signals">
            ${signals.map((s) => `
              <div class="tg-signal">
                <span class="tg-signal-label">${escapeHtml(s.label)}</span>
                <span class="tg-signal-value">${escapeHtml(s.value)}</span>
              </div>
            `).join("")}
          </div>
        </div>
        <div class="tg-connector" aria-hidden="true"></div>
        <div class="tg-zone">
          <div class="tg-zone-label">StoryMap analysis</div>
          <div class="tg-stages">
            ${ANALYSIS_STAGES.map((label) => `
              <div class="tg-stage">
                <span class="tg-stage-dot" aria-hidden="true"></span>
                <span class="tg-stage-label">${escapeHtml(label)}</span>
              </div>
            `).join("")}
          </div>
        </div>
        <div class="tg-connector" aria-hidden="true"></div>
        <div class="tg-zone">
          <div class="tg-zone-label">Defensible narrative</div>
          <div class="tg-output">
            ${narrative ? `
              <div class="tg-output-item tg-output-narrative">
                <span class="tg-output-label">Recommended direction</span>
                <p class="tg-output-text">${escapeHtml(narrative)}</p>
              </div>
            ` : ""}
            ${judgment ? `
              <div class="tg-output-item tg-output-judgment">
                <span class="tg-output-label">Open leadership judgment</span>
                <p class="tg-output-text">${escapeHtml(judgment)}</p>
              </div>
            ` : ""}
          </div>
        </div>
      </div>
    </section>
  `;
}

export async function renderDemoIntro(container, { service, state, onStart, onSelectCase }) {
  container.innerHTML = `<div class="loading">Loading case context…</div>`;
  const [ctx, allCases, graphicData] = await Promise.all([
    service.getCaseContext(),
    Promise.all(AVAILABLE_CASES.map((id) => getAnalysisService(id).getCaseContext().then((c) => ({ id, ...c })))),
    buildGraphicData(state.caseId, service),
  ]);

  container.innerHTML = `
    <section class="case-selector compact">
      <span class="case-selector-label">Choose a public demonstration case</span>
      <div class="case-selector-options" data-role="case-options"></div>
    </section>

    <section class="intro-hero">
      <h1 class="question">${escapeHtml(ctx.headline)}</h1>
      <p class="product-tagline">${escapeHtml(ctx.productTagline)}</p>
    </section>

    ${renderGraphic(graphicData)}

    <div class="intro-cta">
      <button class="primary-button" type="button" data-action="start">Start StoryMap analysis</button>
      <p class="muted small">Takes about 5 minutes to walk through. No account needed.</p>
    </div>

    <details class="about-disclosure">
      <summary>About this demonstration</summary>
      <p class="muted small">${escapeHtml(ctx.disclosure)}</p>
      <p class="muted small">${escapeHtml(ctx.disclosureExtended)}</p>
    </details>
  `;

  const optionsEl = container.querySelector('[data-role="case-options"]');
  allCases.forEach((c) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `case-option${c.id === state.caseId ? " active" : ""}`;
    btn.innerHTML = `
      <span class="case-option-title">${escapeHtml(c.selectorLabel)}</span>
      <span class="case-option-desc">${escapeHtml(c.selectorDescription)}</span>
    `;
    btn.addEventListener("click", () => {
      if (c.id !== state.caseId) onSelectCase(c.id);
    });
    optionsEl.appendChild(btn);
  });

  container.querySelector('[data-action="start"]').addEventListener("click", onStart);

  // Non-blocking, ~3s, single non-looping playthrough — the primary action is fully visible
  // and clickable from the first frame regardless of this class (see .tg-play in styles.css:
  // it only staggers opacity/transform on decorative reveal elements, never the CTA's presence
  // or listener). Reduced-motion: skip entirely, render already in the settled end-state — the
  // .tg-play class is simply never added, no separate "skip" control needed.
  if (!prefersReducedMotion()) {
    const graphicEl = container.querySelector(".tg");
    if (graphicEl) {
      // window.requestAnimationFrame (not the bare global) so this degrades to an immediate
      // class add rather than throwing in any environment that doesn't define it (e.g. jsdom
      // test setups that don't polyfill it onto globalThis directly).
      if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
        window.requestAnimationFrame(() => graphicEl.classList.add("tg-play"));
      } else {
        graphicEl.classList.add("tg-play");
      }
    }
  }
}
