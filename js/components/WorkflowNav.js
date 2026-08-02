// Calm progress rail (UX & visual-system phase) — replaces the prior always-visible,
// equal-weight tab row. SCREENS ids are the routing/hash identifiers and are UNCHANGED —
// only the six user-facing labels changed. Steps are still freely clickable (this is a demo
// the tester explores, not a locked wizard) but current/done/needs-attention are each
// expressed through more than color: current gets elevation (a white pill + shadow), done
// gets an explicit checkmark glyph, attention gets an explicit dot glyph — never color alone.
import { escapeHtml } from "../labels.js";
import { getUsage, getSourceCoverage, getStageProgress } from "../live-analysis-service.js";

export const SCREENS = [
  { id: "foundation", label: "Understand the business" },
  { id: "diagnosis", label: "Diagnose the current story" },
  { id: "choices", label: "Explore directions" },
  { id: "recommendation", label: "Choose a direction" },
  { id: "map", label: "Build the narrative" },
  { id: "evidence", label: "Review the evidence" },
];

// Maps a nav step id to the internal pipeline stage name stageProgress uses — live case
// only; Wix/HPS have no stageProgress concept at all, so this signal is simply absent for
// them (never fabricated). "evidence" has no owning stage — it's a viewer, not a pipeline
// step, so it can never itself be the site of a stage failure.
const STEP_TO_STAGE = {
  foundation: "strategic_foundation",
  diagnosis: "diagnosis",
  choices: "narrative_choices",
  recommendation: "recommendation_and_map",
};

// Only ever called for the live case (see the caseId === "live" gate below) — getUsage()
// reads live-analysis-service.js's own isolated module state, never touching Wix/HPS.
// Absent/incomplete usage (e.g. before the first API call of a run has completed) simply
// renders no summary — never a placeholder like "$0.00" that could misrepresent cost.
function formatUsageSummary(usage) {
  if (!usage || !usage.totals) return "";
  const totalTokens = (usage.totals.input_tokens || 0) + (usage.totals.output_tokens || 0);
  const tokenText = `${totalTokens.toLocaleString()} tokens`;
  return typeof usage.costUsd === "number" ? `$${usage.costUsd.toFixed(2)} · ${tokenText}` : tokenText;
}

function stepStatus(screen, state, stageProgress) {
  if (state.screen === screen.id) return "current";
  const stage = STEP_TO_STAGE[screen.id];
  if (state.caseId === "live" && stage && stageProgress && stageProgress[stage]?.outcome === "stage_failed") {
    return "attention";
  }
  if (state.visitedScreens.includes(screen.id)) return "done";
  return "upcoming";
}

export function renderWorkflowNav(container, { state, onNavigate, onRestart }) {
  let liveTag = "";
  // Live-only — getStageProgress() reads live-analysis-service.js's own isolated module
  // state, same posture as getUsage()/getSourceCoverage() above; Wix/HPS never call it.
  const stageProgress = state.caseId === "live" ? getStageProgress() : null;
  if (state.caseId === "live") {
    const usageSummary = formatUsageSummary(getUsage());
    const usageSuffix = usageSummary ? ` · ${escapeHtml(usageSummary)}` : "";
    liveTag = `<span class="chip live-flow-tag" title="Public-source analysis, generated locally — not an internal-data assessment. Cost/usage reflects every API call made on this job so far.">Provisional · local only${usageSuffix}</span>`;
  }

  const currentIndex = SCREENS.findIndex((s) => s.id === state.screen);
  const stepNumber = currentIndex >= 0 ? currentIndex + 1 : 1;
  const currentScreen = currentIndex >= 0 ? SCREENS[currentIndex] : SCREENS[0];
  const progressPercent = Math.round((stepNumber / SCREENS.length) * 100);

  container.innerHTML = `
    <div class="nav-shell">
      <button class="brand-button" type="button" data-action="home" title="Back to introduction">
        <span class="brand-dot"></span> StoryMap
      </button>
      <button class="nav-mobile-summary" type="button" data-action="toggle-rail" aria-expanded="false">
        <span class="nav-mobile-summary-row">
          <span>Step ${stepNumber} of ${SCREENS.length} · ${escapeHtml(currentScreen.label)}</span>
          <span aria-hidden="true">▾</span>
        </span>
        <span class="nav-mobile-progress"><span class="nav-mobile-progress-fill" style="width:${progressPercent}%"></span></span>
      </button>
      <div class="nav-rail" role="tablist" aria-label="StoryMap workflow"></div>
      ${liveTag}
      <button class="restart-button" type="button" data-action="restart">Restart demo</button>
    </div>
  `;

  const railEl = container.querySelector(".nav-rail");
  SCREENS.forEach((screen, index) => {
    const status = stepStatus(screen, state, stageProgress);
    // "Recommendation" must never be shown as passed unless the source-coverage gate
    // actually passed — SCREENS itself (its id, used for routing) is never mutated, only
    // the rendered text for this one step, and only for the live case.
    const isUnderCoverageRecommendationStep = screen.id === "recommendation" && state.caseId === "live";
    const coverage = isUnderCoverageRecommendationStep ? getSourceCoverage() : null;
    const label = coverage && coverage.sufficient === false ? "Exploratory hypothesis" : screen.label;

    if (index > 0) {
      const sep = document.createElement("div");
      sep.className = "nav-rail-sep";
      sep.setAttribute("aria-hidden", "true");
      railEl.appendChild(sep);
    }
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `nav-rail-step ${status}`;
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", String(status === "current"));
    btn.innerHTML = `<span class="nav-rail-dot" aria-hidden="true"></span><span>${escapeHtml(label)}</span>`;
    btn.addEventListener("click", () => onNavigate(screen.id));
    railEl.appendChild(btn);
  });

  container.querySelector('[data-action="home"]').addEventListener("click", () => onNavigate("intro"));
  container.querySelector('[data-action="restart"]').addEventListener("click", () => {
    if (confirm("Restart the demo? This clears your approvals and returns to the introduction.")) {
      onRestart();
    }
  });

  const toggleBtn = container.querySelector('[data-action="toggle-rail"]');
  toggleBtn.addEventListener("click", () => {
    const isOpen = railEl.classList.toggle("open");
    toggleBtn.setAttribute("aria-expanded", String(isOpen));
  });
}
