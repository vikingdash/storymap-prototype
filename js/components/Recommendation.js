// Screen 5 — Recommendation (pack section 4). Presented as a reasoned recommendation, not an
// objective truth: why it wins, why customers care, why it's credible, how it differs, what
// leadership must still decide, what evidence is missing, and why the alternatives lost.
import { escapeHtml } from "../labels.js";
import { getSourceCoverage, expandSources, getSourceExpansionsUsed, getMaxSourceExpansions, getCurrentSourceUrls } from "../live-analysis-service.js";

// Human-readable labels for backend/pipeline_runner.py's SOURCE_COVERAGE_DIMENSIONS keys
// — defined locally rather than imported, matching how EvidenceRoom.js already keeps its
// own domain-specific label maps (SOURCE_TYPE_LABELS, SCREEN_LABELS) rather than routing
// everything through labels.js.
const COVERAGE_DIMENSION_LABELS = {
  strategy: "Strategy",
  capabilities: "Capabilities",
  customers: "Customers",
  proof: "Proof",
  competitive_context: "Competitive context",
  current_narrative: "Current narrative",
};

// Same caps as AnalyzeCompany.js's intake form (backend/pipeline_runner.py's
// MAX_SUPPORTING_URLS/MAX_COMPETITOR_URLS) — redefined locally rather than imported,
// since AnalyzeCompany.js doesn't export its own copies either; both files independently
// mirror the same server-enforced constants.
const MAX_SUPPORTING = 5;
const MAX_COMPETITOR = 3;

export async function renderRecommendation(container, { service, state, drawer, onNavigate }) {
  container.innerHTML = `<div class="loading">Assembling the recommendation…</div>`;
  const [recommendation, candidates, foundation] = await Promise.all([
    service.getRecommendation(),
    service.getCandidates(),
    service.getStrategicFoundation(),
  ]);

  // Only reachable in the live "Analyze a company" flow — the seeded Wix/HPS pipelines
  // (analysis-service.js's decisionAgent) assert exactly one recommended candidate always
  // exists, so recommendation is never null for them. A live analysis can legitimately
  // have zero candidates pass every hard gate; StoryMap must say so honestly rather than
  // force a choice.
  if (!recommendation) {
    renderNoRecommendation(container, candidates, onNavigate);
    return;
  }

  const winner = recommendation.candidate;
  const others = candidates.filter((c) => c.id !== winner.id);
  const allDecisions = foundation.filter((c) => c.type === "unresolved");
  const primaryDecisions = allDecisions.filter((d) => d.priority === "primary");
  const secondaryDecisions = allDecisions.filter((d) => d.priority !== "primary");

  // The source-coverage gate (backend/pipeline_runner.assess_source_coverage) is a
  // Wix/HPS-never-reachable, live-only concept — only ever consulted when caseId is
  // "live", and treated as "not sufficient" if absent (e.g. still loading), never
  // assumed sufficient by default. This is what this screen may NEVER call a
  // "Recommendation" unless the gate has actually passed.
  const sourceCoverage = state?.caseId === "live" ? getSourceCoverage() : null;
  const isExploratory = !!(sourceCoverage && sourceCoverage.sufficient === false);
  const screenLabel = isExploratory ? "Exploratory Narrative Hypothesis" : "Recommendation";
  const tagText = isExploratory ? "StoryMap exploratory hypothesis" : "StoryMap recommendation";
  const headline = isExploratory
    ? "An exploratory narrative hypothesis — not yet a recommendation"
    : "StoryMap's recommendation — not a verdict";
  const leadText = isExploratory
    ? "The source set behind this analysis is too narrow to support a definitive company-level recommendation. What follows is a well-reasoned hypothesis built from what's available — add more sources to strengthen it into a recommendation."
    : "This is a reasoned recommendation built from the evidence and diagnosis you've just seen. It is not presented as objective truth, and leadership decisions remain before it can be activated.";

  container.innerHTML = `
    <section class="screen-header">
      <div class="eyebrow">4 · ${escapeHtml(screenLabel)}</div>
      <h1>${escapeHtml(headline)}</h1>
      <p class="lead">${escapeHtml(leadText)}</p>
    </section>

    ${isExploratory ? `
    <section class="card notice-card">
      <div class="eyebrow eyebrow-muted">Why this is exploratory, not definitive</div>
      <p class="muted small">This analysis is missing coverage of the following, and what fetching would close each gap:</p>
      <ul class="numbered-list">
        ${sourceCoverage.missingDimensions.map((d) => `<li><strong>${escapeHtml(COVERAGE_DIMENSION_LABELS[d] || d)}:</strong> ${escapeHtml(sourceCoverage.suggestions[d] || "")}</li>`).join("")}
      </ul>
    </section>

    <section class="card" data-role="add-sources-panel">
      <div class="eyebrow eyebrow-muted">Add sources to strengthen this analysis</div>
      <p class="muted small" data-role="add-sources-remaining"></p>
      <h2>Supporting sources <span class="muted small">(up to ${MAX_SUPPORTING})</span></h2>
      <div data-role="add-supporting-list"></div>
      <button type="button" class="pill-button" data-action="add-supporting-url">+ Add supporting URL</button>
      <h2>Competitors <span class="muted small">(up to ${MAX_COMPETITOR})</span></h2>
      <div data-role="add-competitor-list"></div>
      <button type="button" class="pill-button" data-action="add-competitor-url">+ Add competitor URL</button>
      <p class="muted small" data-role="add-sources-error" style="display:none;color:var(--red)"></p>
      <div class="intro-cta">
        <button class="primary-button" type="button" data-action="submit-add-sources">Add sources and re-analyze</button>
      </div>
    </section>
    ` : ""}

    <section class="recommend-panel">
      <div class="candidate-tag">${escapeHtml(tagText)}</div>
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
        <p class="muted small">None of these block this ${isExploratory ? "exploratory hypothesis" : "provisional recommendation"} — they'd sharpen or extend it before wider activation.</p>
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

  if (isExploratory) {
    wireAddSourcesPanel(container, { service, state, drawer, onNavigate });
  }

  container.querySelector('[data-action="continue"]').addEventListener("click", () => onNavigate("map"));
}

// Removes exact-duplicate URLs (after trimming), keeping the first occurrence — applied
// to the FULL list (existing + newly typed) right before submission, never to what's
// displayed in the form itself (a duplicate row, if the user creates one, stays visible
// and editable; only the outgoing request is deduplicated).
function dedupeUrls(urls) {
  const seen = new Set();
  const result = [];
  for (const url of urls) {
    const trimmed = url.trim();
    if (!trimmed || seen.has(trimmed)) continue;
    seen.add(trimmed);
    result.push(trimmed);
  }
  return result;
}

// Wires the "Add sources" panel — only ever called when isExploratory (see
// renderRecommendation above), i.e. never reachable for Wix/HPS. Adding sources is a
// genuinely more expensive action than a stage retry: it re-fetches EVERY source (not
// just the new ones) and reruns the full pipeline from strategic foundation onward, so
// this is treated with the same seriousness as the initial "Run analysis" submission —
// an explicit confirm() before spending anything, matching the existing confirm() dialog
// pattern already used for "Restart demo" in WorkflowNav.js rather than inventing a new
// modal/dialog paradigm.
//
// The form is pre-populated with every currently-configured supporting/competitor URL
// (getCurrentSourceUrls()) as visible, removable, clearly-labeled "Already added" rows —
// the backend's /expand-sources treats the submitted list as the COMPLETE desired source
// set, not additive, so silently submitting only newly-typed URLs would silently drop
// every URL already supplied. Existing URLs are only ever removed by an explicit click on
// that row's own "Remove" button, never as a side effect of adding a new one.
function wireAddSourcesPanel(container, options) {
  const used = getSourceExpansionsUsed();
  const max = getMaxSourceExpansions();
  const remaining = max - used;

  const supportingListEl = container.querySelector('[data-role="add-supporting-list"]');
  const competitorListEl = container.querySelector('[data-role="add-competitor-list"]');
  const remainingEl = container.querySelector('[data-role="add-sources-remaining"]');
  const errorEl = container.querySelector('[data-role="add-sources-error"]');
  const submitBtn = container.querySelector('[data-action="submit-add-sources"]');
  const addSupportingBtn = container.querySelector('[data-action="add-supporting-url"]');
  const addCompetitorBtn = container.querySelector('[data-action="add-competitor-url"]');

  if (remaining <= 0) {
    remainingEl.textContent = `This analysis has already used its ${max} allowed source expansions — no more sources can be added to it.`;
    submitBtn.disabled = true;
    addSupportingBtn.disabled = true;
    addCompetitorBtn.disabled = true;
    return;
  }
  remainingEl.textContent = `You can add sources ${remaining} more time${remaining === 1 ? "" : "s"} for this analysis. Each addition re-fetches every source (existing and new) and reruns the full analysis — a new paid model run.`;

  function addUrlRow(listEl, field, capMax, value, isExisting) {
    if (listEl.children.length >= capMax) return;
    const row = document.createElement("div");
    row.className = "url-row";
    row.innerHTML = `
      <input type="url" class="text-input" data-field="${field}" placeholder="https://..." value="${escapeHtml(value || "")}" />
      ${isExisting ? '<span class="muted small" data-role="existing-source-tag">Already added</span>' : ""}
      <button type="button" class="text-link" data-action="remove-row">Remove</button>
    `;
    row.querySelector('[data-action="remove-row"]').addEventListener("click", () => row.remove());
    listEl.appendChild(row);
  }

  // Pre-populate with whatever is CURRENTLY configured for this job — the original
  // intake, or the last successfully-validated expansion's list if one already
  // happened. Each existing URL gets its own visible, removable row and the
  // "Already added" tag — never silently omitted.
  const { supportingUrls: existingSupporting, competitorUrls: existingCompetitor } = getCurrentSourceUrls();
  existingSupporting.forEach((url) => addUrlRow(supportingListEl, "addSupportingUrl", MAX_SUPPORTING, url, true));
  existingCompetitor.forEach((url) => addUrlRow(competitorListEl, "addCompetitorUrl", MAX_COMPETITOR, url, true));

  addSupportingBtn.addEventListener("click", () => addUrlRow(supportingListEl, "addSupportingUrl", MAX_SUPPORTING, "", false));
  addCompetitorBtn.addEventListener("click", () => addUrlRow(competitorListEl, "addCompetitorUrl", MAX_COMPETITOR, "", false));

  submitBtn.addEventListener("click", async () => {
    errorEl.style.display = "none";
    // Every ROW currently present — existing (not removed) + newly added — is the
    // complete desired list; nothing here distinguishes "existing" from "new" at
    // submission time beyond having started life pre-populated, exactly matching what
    // the backend expects to receive.
    const supportingUrls = dedupeUrls(Array.from(container.querySelectorAll('[data-field="addSupportingUrl"]')).map((i) => i.value));
    const competitorUrls = dedupeUrls(Array.from(container.querySelectorAll('[data-field="addCompetitorUrl"]')).map((i) => i.value));
    if (!supportingUrls.length && !competitorUrls.length) {
      errorEl.textContent = "At least one supporting or competitor URL is required.";
      errorEl.style.display = "block";
      return;
    }
    const confirmed = confirm(
      "This will re-fetch every source (existing and new) and rerun the FULL analysis — strategic foundation through recommendation — as a new paid model run. Continue?"
    );
    if (!confirmed) return;

    submitBtn.disabled = true;
    addSupportingBtn.disabled = true;
    addCompetitorBtn.disabled = true;
    const originalLabel = submitBtn.textContent;
    submitBtn.textContent = "Adding sources and re-analyzing…";

    try {
      await expandSources(supportingUrls, competitorUrls, (s) => {
        if (s.stage) submitBtn.textContent = `Running ${s.stage.replace(/_/g, " ")}…`;
      });
      // Re-render this screen in place — reflects either the refreshed analysis
      // (success) or the rolled-back prior validated view AND prior source list
      // (failure, per expandSources()'s own snapshot/rollback in
      // live-analysis-service.js) — re-reading getCurrentSourceUrls() fresh here is
      // what makes the form correctly re-populate from whichever one actually applies.
      await renderRecommendation(container, options);
    } catch (err) {
      submitBtn.disabled = false;
      addSupportingBtn.disabled = false;
      addCompetitorBtn.disabled = false;
      submitBtn.textContent = originalLabel;
      errorEl.textContent = friendlyExpandSourcesError(err instanceof Error ? err.message : String(err));
      errorEl.style.display = "block";
    }
  });
}

function friendlyExpandSourcesError(message) {
  if (message === "source_expansion_limit_reached") return "This analysis has already used its allowed source expansions.";
  return message;
}

function renderNoRecommendation(container, candidates, onNavigate) {
  container.innerHTML = `
    <section class="screen-header">
      <div class="eyebrow">4 · Recommendation</div>
      <h1>StoryMap cannot yet recommend a direction</h1>
      <p class="lead">None of the three narrative candidates cleared StoryMap's evidence and differentiation bar. Rather than force a choice, StoryMap is flagging this honestly — strengthening the evidence below and regenerating would let it try again.</p>
    </section>

    <section class="card notice-card">
      <h3>What's missing</h3>
      <div data-role="missing-list"></div>
    </section>

    <section class="card">
      <h3>Candidates considered</h3>
      <div class="rejected-list" data-role="candidate-list"></div>
    </section>

    <div class="screen-footer">
      <button class="text-link" type="button" data-action="continue">Open the Evidence Room →</button>
    </div>
  `;

  const reasons = new Set();
  candidates.forEach((c) => (c.criticFindings || []).forEach((f) => reasons.add(f)));
  const missingListEl = container.querySelector('[data-role="missing-list"]');
  const ul = document.createElement("ul");
  ul.className = "numbered-list";
  [...reasons].slice(0, 8).forEach((reason) => {
    const li = document.createElement("li");
    li.textContent = reason;
    ul.appendChild(li);
  });
  missingListEl.appendChild(ul);

  const candidateListEl = container.querySelector('[data-role="candidate-list"]');
  candidates.forEach((c) => {
    const row = document.createElement("div");
    row.className = "rejected-item";
    row.innerHTML = `
      <h4>${escapeHtml(c.name)}</h4>
      <p class="muted">${escapeHtml(c.oneSentenceStory)}</p>
    `;
    candidateListEl.appendChild(row);
  });

  container.querySelector('[data-action="continue"]').addEventListener("click", () => onNavigate("evidence"));
}
