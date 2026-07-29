// Screen 5 — Recommendation (pack section 4). Presented as a reasoned recommendation, not an
// objective truth: why it wins, why customers care, why it's credible, how it differs, what
// leadership must still decide, what evidence is missing, and why the alternatives lost.
import { escapeHtml } from "../labels.js";

export async function renderRecommendation(container, { service, drawer, onNavigate }) {
  container.innerHTML = `<div class="loading">Assembling the recommendation…</div>`;
  const [recommendation, candidates, foundation] = await Promise.all([
    service.getRecommendation(),
    service.getCandidates(),
    service.getStrategicFoundation(),
  ]);

  const winner = recommendation.candidate;
  const others = candidates.filter((c) => c.id !== winner.id);
  const allDecisions = foundation.filter((c) => c.type === "unresolved");
  const primaryDecisions = allDecisions.filter((d) => d.priority === "primary");
  const secondaryDecisions = allDecisions.filter((d) => d.priority !== "primary");

  container.innerHTML = `
    <section class="screen-header">
      <div class="eyebrow">4 · Recommendation</div>
      <h1>StoryMap's recommendation — not a verdict</h1>
      <p class="lead">This is a reasoned recommendation built from the evidence and diagnosis you've just seen. It is not presented as objective truth, and leadership decisions remain before it can be activated.</p>
    </section>

    <section class="recommend-panel">
      <div class="candidate-tag">StoryMap recommendation</div>
      <h2>${escapeHtml(winner.name)}</h2>
      <div class="decision-statement">
        <span class="decision-statement-label">Recommended decision</span>
        <p>${escapeHtml(recommendation.recommendedDecision)}</p>
      </div>
      <blockquote class="recommend-quote">${escapeHtml(winner.oneSentenceStory)}</blockquote>
      <div class="why-grid">
        <div><h4>Why this option wins</h4><p class="muted">${escapeHtml(recommendation.whyItWins)}</p></div>
        <div><h4>Why customers should care</h4><p class="muted">${escapeHtml(recommendation.whyCustomersCare)}</p></div>
        <div><h4>Why the company can credibly own it</h4><p class="muted">${escapeHtml(recommendation.whyCredible)}</p></div>
        <div><h4>How it differs from competitors</h4><p class="muted">${escapeHtml(recommendation.howDifferent)}</p></div>
      </div>
    </section>

    <section class="card">
      <h3>What leadership must decide before activation</h3>
      <ul class="numbered-list">
        ${primaryDecisions.map((d) => `<li>${escapeHtml(d.statement)}</li>`).join("")}
      </ul>
    </section>

    <section class="card">
      <h3>Why the other options were not selected</h3>
      <div class="rejected-list"></div>
    </section>

    <div class="card">
      <details class="additional-questions">
        <summary>Evidence and decisions needed next</summary>
        <p class="muted small">None of these block a provisional recommendation — they'd sharpen or extend it before wider activation.</p>
        <h4>Additional leadership decisions</h4>
        <ul class="numbered-list">
          ${secondaryDecisions.map((d) => `<li>${escapeHtml(d.statement)}</li>`).join("")}
        </ul>
        <h4>Missing evidence</h4>
        <ul class="numbered-list">
          ${recommendation.missingEvidence.map((m) => `<li>${escapeHtml(m)}</li>`).join("")}
        </ul>
      </details>
    </div>

    <div class="screen-footer">
      <button class="primary-button" type="button" data-action="continue">View the Narrative Map →</button>
    </div>
  `;

  const rejectedList = container.querySelector(".rejected-list");
  others.forEach((c) => {
    const row = document.createElement("div");
    row.className = "rejected-item";
    row.innerHTML = `
      <h4>${escapeHtml(c.name)}</h4>
      <p class="muted">${escapeHtml(recommendation.whyOthersNotSelected[c.id] || "")}</p>
    `;
    rejectedList.appendChild(row);
  });

  container.querySelector('[data-action="continue"]').addEventListener("click", () => onNavigate("map"));
}
