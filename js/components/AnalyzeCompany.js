// "Analyze a company" intake screen — the live counterpart to the seeded cases' intro.
// There is no pre-chosen company here, so this screen (not DemoIntro.js) is where the
// user actually supplies one, before any of the seven standard screens have anything to
// show. Three states: (1) backend unreachable — explain why, keep the form visible but
// disabled, never a raw network-error page (matters most on the public GitHub Pages
// build, which has no backend at all); (2) intake form; (3) stage-by-stage progress while
// a job runs. On completion, hands off to the normal screen flow starting at "foundation".
import { escapeHtml } from "../labels.js";
import { checkBackendAvailable, startAnalysis, pollJob, retryStage, getStageProgress } from "../live-analysis-service.js";

const STAGE_LABELS = {
  fetching_sources: "Fetching sources",
  strategic_foundation: "Strategic foundation",
  diagnosis: "Diagnosis",
  narrative_choices: "Narrative choices",
  critique: "Critique",
  recommendation_and_map: "Recommendation and Narrative Map",
};
const STAGE_ORDER = Object.keys(STAGE_LABELS);

const MAX_SUPPORTING = 5;
const MAX_COMPETITOR = 3;

export async function renderAnalyzeCompany(container, { onNavigate }) {
  container.innerHTML = `<div class="loading">Checking local backend…</div>`;
  const backendAvailable = await checkBackendAvailable();

  container.innerHTML = `
    <section class="screen-header">
      <div class="eyebrow">Analyze a company</div>
      <h1>Run StoryMap on a real company</h1>
      <p class="lead">Enter a company's public website and (optionally) a few supporting pages, an existing narrative, and up to three competitors. StoryMap will fetch only what you provide and build an evidence-backed analysis from it.</p>
    </section>

    <section class="card notice-card">
      <div class="eyebrow eyebrow-muted">Important context</div>
      <p>This analysis is <strong>provisional</strong>. It is built only from the public sources you provide — it has no access to internal strategy, customer research, or proprietary data. Claims without direct evidence are labeled as such, not presented with false confidence.</p>
    </section>

    ${backendAvailable ? "" : `
    <section class="card notice-card">
      <div class="eyebrow eyebrow-muted">Local development only</div>
      <p>Live analysis requires a backend that isn't part of this public demo site. This feature is currently available only when running StoryMap locally with the backend started (<code>python3 backend/app.py</code>) — see the project README. The form below is shown so you can see how it works, but submission is disabled here.</p>
    </section>
    `}

    <section class="card" data-role="intake-form">
      <h2>Company</h2>
      <label class="field-label">Company website (required)
        <input type="url" class="text-input" data-field="companyUrl" placeholder="https://example.com" ${backendAvailable ? "" : "disabled"} />
      </label>

      <h2>Supporting sources <span class="muted small">(up to ${MAX_SUPPORTING}, optional)</span></h2>
      <div data-role="supporting-list"></div>
      <button type="button" class="pill-button" data-action="add-supporting" ${backendAvailable ? "" : "disabled"}>+ Add supporting URL</button>

      <h2>Existing narrative <span class="muted small">(optional)</span></h2>
      <textarea class="edit-textarea" data-field="existingNarrative" placeholder="Paste the company's current positioning or narrative, if you have one" ${backendAvailable ? "" : "disabled"}></textarea>

      <h2>Competitors <span class="muted small">(up to ${MAX_COMPETITOR}, optional)</span></h2>
      <div data-role="competitor-list"></div>
      <button type="button" class="pill-button" data-action="add-competitor" ${backendAvailable ? "" : "disabled"}>+ Add competitor URL</button>

      <p class="muted small" data-role="form-error" style="display:none;color:var(--red)"></p>

      <div class="intro-cta">
        <button class="primary-button" type="button" data-action="submit" ${backendAvailable ? "" : "disabled"}>Run analysis</button>
      </div>
    </section>

    <section class="card" data-role="progress-panel" style="display:none">
      <h2>Running analysis…</h2>
      <div class="stage-list" data-role="stage-list"></div>
      <p class="muted small" data-role="progress-note">This runs several real model calls in sequence — it can take a minute or two.</p>
    </section>

    <section class="card notice-card" data-role="failure-panel" style="display:none">
      <div class="eyebrow eyebrow-muted">Analysis stopped</div>
      <p data-role="failure-reason"></p>
      <div class="intro-cta" data-role="failure-actions"></div>
    </section>
  `;

  const supportingListEl = container.querySelector('[data-role="supporting-list"]');
  const competitorListEl = container.querySelector('[data-role="competitor-list"]');

  function addUrlRow(listEl, field, disabled) {
    if (listEl.children.length >= (field === "supporting" ? MAX_SUPPORTING : MAX_COMPETITOR)) return;
    const row = document.createElement("div");
    row.className = "url-row";
    row.innerHTML = `
      <input type="url" class="text-input" data-field="${field}Url" placeholder="https://..." ${disabled ? "disabled" : ""} />
      <button type="button" class="text-link" data-action="remove-row">Remove</button>
    `;
    row.querySelector('[data-action="remove-row"]').addEventListener("click", () => row.remove());
    listEl.appendChild(row);
  }

  container.querySelector('[data-action="add-supporting"]')?.addEventListener("click", () => addUrlRow(supportingListEl, "supporting", !backendAvailable));
  container.querySelector('[data-action="add-competitor"]')?.addEventListener("click", () => addUrlRow(competitorListEl, "competitor", !backendAvailable));

  if (backendAvailable) {
    addUrlRow(supportingListEl, "supporting", false);
    addUrlRow(competitorListEl, "competitor", false);
  }

  const submitBtn = container.querySelector('[data-action="submit"]');
  const formErrorEl = container.querySelector('[data-role="form-error"]');
  const formEl = container.querySelector('[data-role="intake-form"]');
  const progressEl = container.querySelector('[data-role="progress-panel"]');
  const stageListEl = container.querySelector('[data-role="stage-list"]');
  const failurePanelEl = container.querySelector('[data-role="failure-panel"]');
  const failureReasonEl = container.querySelector('[data-role="failure-reason"]');
  const failureActionsEl = container.querySelector('[data-role="failure-actions"]');

  function collectUrls(field) {
    return Array.from(container.querySelectorAll(`[data-field="${field}Url"]`))
      .map((input) => input.value.trim())
      .filter(Boolean);
  }

  function renderStageList(currentStage) {
    const currentIndex = STAGE_ORDER.indexOf(currentStage);
    const stageProgress = getStageProgress() || {};
    stageListEl.innerHTML = STAGE_ORDER.map((stage, i) => {
      const state = currentIndex === -1 ? "pending" : i < currentIndex ? "done" : i === currentIndex ? "active" : "pending";
      const icon = state === "done" ? "✓" : state === "active" ? "…" : "";
      const attempts = stageProgress[stage]?.attempts || 0;
      const retryNote = attempts > 1 ? ` <span class="muted small">(retried automatically — ${attempts} attempts)</span>` : "";
      return `<div class="stage-row stage-${state}"><span class="stage-icon">${icon}</span><span>${escapeHtml(STAGE_LABELS[stage])}${retryNote}</span></div>`;
    }).join("");
  }

  // Whether the failed job still has anything worth showing — the backend preserves
  // whatever stages succeeded before a later one failed, per its "preserve earlier
  // validated stages" principle; this is just checking whether that preserved content
  // is non-empty, not re-deriving any pipeline logic.
  function hasPartialResults(dataset) {
    if (!dataset) return false;
    return (dataset.strategicFoundation || []).length > 0
      || (dataset.diagnosis || []).length > 0
      || (dataset.candidates || []).length > 0;
  }

  function findFailedStage(stageProgress) {
    if (!stageProgress) return null;
    return STAGE_ORDER.find((stage) => stageProgress[stage]?.outcome === "stage_failed") || null;
  }

  function friendlyRetryError(message) {
    if (message === "retry_limit_reached") return "This stage has already used its one allowed manual retry.";
    if (message === "retry_in_progress") return "A retry for this stage is already running.";
    return message;
  }

  async function handleFailure(status) {
    progressEl.style.display = "none";
    const partial = hasPartialResults(status.dataset);
    const failedStage = findFailedStage(status.stageProgress);

    if (!partial) {
      // Nothing usable succeeded (e.g. the company URL itself couldn't be fetched) —
      // the plain dead-end error is the honest state here; there is nothing to view.
      formEl.style.opacity = "1";
      submitBtn.disabled = false;
      formErrorEl.textContent = status.error || "Analysis failed for an unknown reason.";
      formErrorEl.style.display = "block";
      return;
    }

    failureReasonEl.textContent = failedStage
      ? `This analysis stopped at "${STAGE_LABELS[failedStage]}" after the automatic retries were exhausted — the stages above it are preserved below.`
      : (status.error || "This analysis stopped partway through.");
    failureActionsEl.innerHTML = "";

    const viewBtn = document.createElement("button");
    viewBtn.type = "button";
    viewBtn.className = "primary-button";
    viewBtn.textContent = "View partial results";
    viewBtn.addEventListener("click", () => onNavigate("foundation"));
    failureActionsEl.appendChild(viewBtn);

    if (failedStage) {
      const retryBtn = document.createElement("button");
      retryBtn.type = "button";
      retryBtn.className = "pill-button";
      retryBtn.textContent = `Retry ${STAGE_LABELS[failedStage]}`;
      retryBtn.addEventListener("click", async () => {
        failurePanelEl.style.display = "none";
        progressEl.style.display = "block";
        renderStageList(failedStage);
        try {
          const retryStatus = await retryStage(failedStage, (s) => renderStageList(s.stage));
          if (retryStatus.status === "failed") {
            await handleFailure(retryStatus);
            return;
          }
          progressEl.style.display = "none";
          onNavigate("foundation");
        } catch (err) {
          progressEl.style.display = "none";
          failurePanelEl.style.display = "block";
          failureReasonEl.textContent = friendlyRetryError(err instanceof Error ? err.message : String(err));
          failureActionsEl.innerHTML = "";
        }
      });
      failureActionsEl.appendChild(retryBtn);
    }

    failurePanelEl.style.display = "block";
  }

  if (!backendAvailable) return;

  submitBtn.addEventListener("click", async () => {
    formErrorEl.style.display = "none";
    const companyUrl = container.querySelector('[data-field="companyUrl"]').value.trim();
    if (!companyUrl) {
      formErrorEl.textContent = "Company website is required.";
      formErrorEl.style.display = "block";
      return;
    }
    const supportingUrls = collectUrls("supporting");
    const competitorUrls = collectUrls("competitor");
    const existingNarrative = container.querySelector('[data-field="existingNarrative"]').value.trim();

    submitBtn.disabled = true;
    formEl.style.opacity = "0.6";
    progressEl.style.display = "block";
    renderStageList(null);

    try {
      const jobId = await startAnalysis({ companyUrl, supportingUrls, competitorUrls, existingNarrative });
      const status = await pollJob(jobId, (s) => renderStageList(s.stage));
      if (status.status === "failed") {
        await handleFailure(status);
        return;
      }
      onNavigate("foundation");
    } catch (err) {
      progressEl.style.display = "none";
      formEl.style.opacity = "1";
      submitBtn.disabled = false;
      formErrorEl.textContent = err instanceof Error ? err.message : String(err);
      formErrorEl.style.display = "block";
    }
  });
}
