// Stepper nav: keeps "a visible path through the workflow" (pack section 10) on screen at all
// times once the user has left the intro. Steps are freely clickable — this is a demo the tester
// explores, not a locked wizard — but the current step and completed steps are always visually
// distinct, and Restart is always one click away.
import { escapeHtml } from "../labels.js";
import { getUsage, getSourceCoverage } from "../live-analysis-service.js";

export const SCREENS = [
  { id: "foundation", label: "1. Strategic foundation" },
  { id: "diagnosis", label: "2. Current-story diagnosis" },
  { id: "choices", label: "3. Narrative choices" },
  { id: "recommendation", label: "4. Recommendation" },
  { id: "map", label: "5. Narrative Map" },
  { id: "evidence", label: "Evidence room" },
];

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

export function renderWorkflowNav(container, { state, onNavigate, onRestart }) {
  let liveTag = "";
  if (state.caseId === "live") {
    const usageSummary = formatUsageSummary(getUsage());
    const usageSuffix = usageSummary ? ` · ${escapeHtml(usageSummary)}` : "";
    liveTag = `<span class="chip live-flow-tag" title="Public-source analysis, generated locally — not an internal-data assessment. Cost/usage reflects every API call made on this job so far.">Provisional · local only${usageSuffix}</span>`;
  }

  container.innerHTML = `
    <div class="nav-shell">
      <button class="brand-button" type="button" data-action="home" title="Back to introduction">
        <span class="brand-dot"></span> StoryMap
      </button>
      <div class="nav-steps" role="tablist" aria-label="StoryMap workflow"></div>
      ${liveTag}
      <button class="restart-button" type="button" data-action="restart">Restart demo</button>
    </div>
  `;

  const stepsEl = container.querySelector(".nav-steps");
  SCREENS.forEach((screen) => {
    const isActive = state.screen === screen.id;
    const isVisited = state.visitedScreens.includes(screen.id);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `nav-step${isActive ? " active" : ""}${isVisited ? " visited" : ""}`;
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", String(isActive));
    // "Recommendation" must never be shown as the step label unless the source-coverage
    // gate actually passed — SCREENS itself (its id, used for routing) is never mutated,
    // only the rendered text for this one step, and only for the live case.
    const isUnderCoverageRecommendationStep = screen.id === "recommendation" && state.caseId === "live";
    const coverage = isUnderCoverageRecommendationStep ? getSourceCoverage() : null;
    const label = coverage && coverage.sufficient === false ? "4. Exploratory Narrative Hypothesis" : screen.label;
    btn.innerHTML = escapeHtml(label);
    btn.addEventListener("click", () => onNavigate(screen.id));
    stepsEl.appendChild(btn);
  });

  container.querySelector('[data-action="home"]').addEventListener("click", () => onNavigate("intro"));
  container.querySelector('[data-action="restart"]').addEventListener("click", () => {
    if (confirm("Restart the demo? This clears your approvals and returns to the introduction.")) {
      onRestart();
    }
  });
}
