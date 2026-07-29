// Stepper nav: keeps "a visible path through the workflow" (pack section 10) on screen at all
// times once the user has left the intro. Steps are freely clickable — this is a demo the tester
// explores, not a locked wizard — but the current step and completed steps are always visually
// distinct, and Restart is always one click away.
import { escapeHtml } from "../labels.js";

export const SCREENS = [
  { id: "foundation", label: "1. Strategic foundation" },
  { id: "diagnosis", label: "2. Current-story diagnosis" },
  { id: "choices", label: "3. Narrative choices" },
  { id: "recommendation", label: "4. Recommendation" },
  { id: "map", label: "5. Narrative Map" },
  { id: "evidence", label: "Evidence room" },
];

export function renderWorkflowNav(container, { state, onNavigate, onRestart }) {
  container.innerHTML = `
    <div class="nav-shell">
      <button class="brand-button" type="button" data-action="home" title="Back to introduction">
        <span class="brand-dot"></span> StoryMap
      </button>
      <div class="nav-steps" role="tablist" aria-label="StoryMap workflow"></div>
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
    btn.innerHTML = escapeHtml(screen.label);
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
