// Screen 1 — Demo introduction (pack section 4). Establishes what StoryMap is, why the selected
// company is the demonstration case, the narrative question at stake, and the limits of a
// public-source-only analysis, before any diagnosis or scoring is shown. Also hosts the case
// selector — StoryMap ships with two independent public demonstrations (Wix, Hammond Power
// Solutions) and the user picks one before starting.
import { escapeHtml } from "../labels.js";
import { getAnalysisService, AVAILABLE_CASES } from "../analysis-service.js";

export async function renderDemoIntro(container, { service, state, onStart, onSelectCase }) {
  container.innerHTML = `<div class="loading">Loading case context…</div>`;
  const [ctx, allCases] = await Promise.all([
    service.getCaseContext(),
    Promise.all(AVAILABLE_CASES.map((id) => getAnalysisService(id).getCaseContext().then((c) => ({ id, ...c })))),
  ]);

  container.innerHTML = `
    <section class="case-selector">
      <span class="case-selector-label">Choose a public demonstration case</span>
      <div class="case-selector-options" data-role="case-options"></div>
    </section>

    <section class="intro-hero">
      <div class="eyebrow">StoryMap prototype demo</div>
      <p class="product-tagline">${escapeHtml(ctx.productTagline)}</p>
      <h1>What should ${escapeHtml(ctx.company.name)}'s corporate story be now?</h1>
      <p class="lead">
        To show how StoryMap works, this prototype uses <strong>${escapeHtml(ctx.company.name)}</strong> as the demonstration company. ${escapeHtml(ctx.company.oneLiner)}
      </p>
      <p class="lead">${escapeHtml(ctx.whyThisCompany)}</p>
      <blockquote class="question">${escapeHtml(ctx.headline)}</blockquote>
      <p class="lead">This prototype shows how StoryMap would help answer that question.</p>
    </section>

    <section class="intro-grid">
      <div class="card">
        <h2>What you are about to see</h2>
        <ol class="numbered-list">
          ${ctx.whatStoryMapWillDo.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}
        </ol>
      </div>
      <div class="card">
        <h2>The decision StoryMap is helping resolve</h2>
        <p class="question-inline">${escapeHtml(ctx.narrativeQuestion)}</p>
      </div>
    </section>

    <section class="card notice-card">
      <div class="eyebrow eyebrow-muted">Important context</div>
      <p>${escapeHtml(ctx.disclosure)}</p>
      <p class="muted">${escapeHtml(ctx.disclosureExtended)}</p>
    </section>

    <div class="intro-cta">
      <button class="primary-button" type="button" data-action="start">Start StoryMap analysis</button>
      <p class="muted small">Takes about 5 minutes to walk through. No account needed.</p>
    </div>
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
}
