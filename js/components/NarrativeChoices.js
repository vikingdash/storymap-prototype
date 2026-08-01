// Screen 4 — Narrative choices (pack section 4). Three materially different strategic choices.
// A user should understand all three in under a minute, so only the core story, why customers
// care, differentiation, an overall assessment and primary trade-off show by default. Strategic
// logic, the full per-criterion score breakdown, risks and critic findings sit under "View full
// analysis." The main cards deliberately show no numeric score at all — a decimal like "4.6/5"
// implies a precision the underlying judgment doesn't have, on a corpus of six sources. Instead
// each candidate gets one of three qualitative labels (Recommended / Viable alternative / Does
// not pass [criterion] threshold), derived from the canonical persisted candidate.status/
// gateResults/rejectionReasons (governing spec Phase 1) — this screen never recomputes
// viability itself; candidate-state.js's normalizeCandidates() already produced the one
// canonical status every other screen (Recommendation, Narrative Map) reads too. "Recommended"
// is likewise never a persisted candidate status — it's derived here purely by comparing the
// candidate's id against the separately-fetched recommendation's selectedCandidateId. The 1-5
// criterion numbers still exist and are still real — they're just one click away, not front and
// center implying false certainty.
import { escapeHtml } from "../labels.js";
import { scoreBarWidthPercent, formatScore, SCORE_RUBRIC } from "../scoring.js";

export async function renderNarrativeChoices(container, { service, drawer, onNavigate }) {
  container.innerHTML = `<div class="loading">Generating narrative choices…</div>`;
  const [candidates, recommendation] = await Promise.all([service.getCandidates(), service.getRecommendation()]);
  const selectedCandidateId = recommendation && recommendation.outcome === "success" ? recommendation.selectedCandidateId : null;

  container.innerHTML = `
    <section class="screen-header">
      <div class="eyebrow">3 · Narrative choices</div>
      <h1>Three strategic stories, not three wordsmithing options</h1>
      <p class="lead">Each choice makes a different strategic decision about what the company should be known for — not just different phrasing of the same idea.</p>
    </section>
    <div class="candidates-grid"></div>
    <div class="screen-footer">
      <button class="primary-button" type="button" data-action="continue">See the recommendation →</button>
    </div>
  `;

  const grid = container.querySelector(".candidates-grid");
  candidates.forEach((c) => grid.appendChild(renderCandidateCard(c, drawer, selectedCandidateId)));

  container.querySelector('[data-action="continue"]').addEventListener("click", () => onNavigate("recommendation"));
}

function categorizeCandidate(candidate, selectedCandidateId) {
  if (candidate.status === "rejected") {
    const failingGate = (candidate.gateResults || []).find((g) => g.outcome === "fail");
    const label = failingGate ? `Does not pass ${failingGate.criterion} threshold` : "Does not pass StoryMap's evidence and differentiation bar";
    return { label, statusClass: "status-blocked" };
  }
  if (candidate.id === selectedCandidateId) {
    return { label: "Recommended", statusClass: "status-recommended" };
  }
  return { label: "Viable alternative", statusClass: "status-viable" };
}

function renderOverallStatus(candidate, selectedCandidateId) {
  const { label, statusClass } = categorizeCandidate(candidate, selectedCandidateId);
  return `
    <div class="overall-status ${statusClass}">
      <span class="score-label">Overall assessment</span>
      <span class="overall-status-value">${escapeHtml(label)}</span>
    </div>
  `;
}

function renderCandidateCard(candidate, drawer, selectedCandidateId) {
  const isRecommended = candidate.id === selectedCandidateId;
  const el = document.createElement("div");
  el.className = `candidate-card${isRecommended ? " recommended" : ""}`;

  const scoreRows = Object.entries(candidate.scores)
    .map(([criterion, score]) => `
      <div class="score-row">
        <span class="score-label">${escapeHtml(criterion)}</span>
        <div class="score-bar"><div class="score-fill" style="width:${scoreBarWidthPercent(score)}%"></div></div>
        <span class="score-value">${formatScore(score)}</span>
      </div>
    `)
    .join("");

  const rubricRows = Object.entries(candidate.scores)
    .map(([criterion, score]) => `
      <div class="rubric-row">
        <div class="rubric-row-top"><span class="rubric-criterion">${escapeHtml(criterion)}</span><span class="score-value">${formatScore(score)}</span></div>
        <p class="muted small">${escapeHtml(SCORE_RUBRIC[criterion] || "")}</p>
      </div>
    `)
    .join("");

  const sourceCount = candidate.claims.length;

  el.innerHTML = `
    <div class="candidate-tag">${isRecommended ? "StoryMap recommendation" : "Alternative"}</div>
    <h3>${escapeHtml(candidate.name)}</h3>
    <p class="candidate-statement">${escapeHtml(candidate.oneSentenceStory)}</p>

    <div class="candidate-section">
      <h4>Why customers would care</h4>
      <p class="muted">${escapeHtml(candidate.customerRelevance)}</p>
    </div>
    <div class="candidate-section">
      <h4>Differentiation</h4>
      <p class="muted">${escapeHtml(candidate.differentiation)}</p>
    </div>
    <div class="candidate-section">
      ${renderOverallStatus(candidate, selectedCandidateId)}
    </div>
    <div class="candidate-section">
      <h4>Primary trade-off</h4>
      <p class="muted">${escapeHtml(candidate.tradeoffs[0] || "")}</p>
    </div>
    ${sourceCount ? `<button type="button" class="text-link" data-action="view-sources">View ${sourceCount} source${sourceCount === 1 ? "" : "s"}</button>` : ""}

    <details class="view-full-analysis">
      <summary>View full analysis</summary>
      <div class="candidate-section">
        <h4>Strategic logic</h4>
        <ul>${candidate.strategicLogic.map((l) => `<li>${escapeHtml(l)}</li>`).join("")}</ul>
      </div>
      <div class="candidate-section">
        <h4>Scores</h4>
        ${scoreRows}
        <details class="how-scored">
          <summary>How StoryMap scored this</summary>
          ${rubricRows}
        </details>
      </div>
      <div class="candidate-section">
        <h4>All trade-offs</h4>
        <ul>${candidate.tradeoffs.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ul>
      </div>
      <div class="candidate-section risk-section">
        <h4>Risks</h4>
        <ul>${candidate.risks.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>
      </div>
      <div class="candidate-section critic-section">
        <h4>Narrative Critic findings</h4>
        <ul>${candidate.criticFindings.map((f) => `<li>${escapeHtml(f)}</li>`).join("")}</ul>
      </div>
    </details>
  `;

  const viewSourcesBtn = el.querySelector('[data-action="view-sources"]');
  if (viewSourcesBtn) {
    viewSourcesBtn.addEventListener("click", () => drawer.openEvidenceLinks(candidate.claims, candidate.name));
  }

  return el;
}
