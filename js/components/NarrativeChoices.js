// Screen 4 — Narrative choices (pack section 4). Three materially different strategic choices.
// A user should understand all three in under a minute, so only the core story, why customers
// care, differentiation, an overall assessment and primary trade-off show by default. Strategic
// logic, the full per-criterion score breakdown, risks and critic findings sit under "View full
// analysis." The main cards deliberately show no numeric score at all — a decimal like "4.6/5"
// implies a precision the underlying judgment doesn't have, on a corpus of six sources. Instead
// each candidate gets one of three qualitative labels (Recommended / Viable alternative / Does
// not pass [criterion] threshold), derived from computeOverallScore() in scoring.js. The 1-5
// criterion numbers still exist and are still real — they're just one click away, not front and
// center implying false certainty.
import { escapeHtml } from "../labels.js";
import { scoreBarWidthPercent, formatScore, computeOverallScore, SCORE_RUBRIC } from "../scoring.js";

export async function renderNarrativeChoices(container, { service, drawer, onNavigate }) {
  container.innerHTML = `<div class="loading">Generating narrative choices…</div>`;
  const candidates = await service.getCandidates();

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
  candidates.forEach((c) => grid.appendChild(renderCandidateCard(c, drawer)));

  container.querySelector('[data-action="continue"]').addEventListener("click", () => onNavigate("recommendation"));
}

function categorizeCandidate(candidate) {
  const overall = computeOverallScore(candidate.scores);
  if (overall.blocked) {
    return { label: `Does not pass ${overall.failing[0].criterion} threshold`, statusClass: "status-blocked" };
  }
  if (candidate.status === "recommended") {
    return { label: "Recommended", statusClass: "status-recommended" };
  }
  return { label: "Viable alternative", statusClass: "status-viable" };
}

function renderOverallStatus(candidate) {
  const { label, statusClass } = categorizeCandidate(candidate);
  return `
    <div class="overall-status ${statusClass}">
      <span class="score-label">Overall assessment</span>
      <span class="overall-status-value">${escapeHtml(label)}</span>
    </div>
  `;
}

function renderCandidateCard(candidate, drawer) {
  const isRecommended = candidate.status === "recommended";
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
      ${renderOverallStatus(candidate)}
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
