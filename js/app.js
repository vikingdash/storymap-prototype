// Entry point: wires the analysis service, app state, workflow nav and evidence drawer to the
// seven screens. Routing is hash-based (#foundation, #diagnosis, ...) so any screen is
// deep-linkable and the browser back/forward buttons work.
import { getAnalysisService } from "./analysis-service.js";
import { getState, subscribe, setScreen, setCase, restart } from "./state.js";
import { renderWorkflowNav, SCREENS } from "./components/WorkflowNav.js";
import { mountEvidenceDrawer } from "./components/EvidenceDrawer.js";
import { renderDemoIntro } from "./components/DemoIntro.js";
import { renderAnalyzeCompany } from "./components/AnalyzeCompany.js";
import { renderStrategicFoundation } from "./components/StrategicFoundation.js";
import { renderDiagnosis } from "./components/Diagnosis.js";
import { renderNarrativeChoices } from "./components/NarrativeChoices.js";
import { renderRecommendation } from "./components/Recommendation.js";
import { renderNarrativeMapView } from "./components/NarrativeMapView.js";
import { renderEvidenceRoom } from "./components/EvidenceRoom.js";

const SCREEN_RENDERERS = {
  intro: renderDemoIntro,
  analyze: renderAnalyzeCompany,
  foundation: renderStrategicFoundation,
  diagnosis: renderDiagnosis,
  choices: renderNarrativeChoices,
  recommendation: renderRecommendation,
  map: renderNarrativeMapView,
  evidence: renderEvidenceRoom,
};

const VALID_SCREENS = new Set(["intro", "analyze", ...SCREENS.map((s) => s.id)]);

const navRoot = document.getElementById("workflow-nav");
const screenRoot = document.getElementById("screen-root");
const drawerRoot = document.getElementById("drawer-root");

// Passed as a getter, not a fixed instance, because which case is active can change after the
// drawer is mounted (case selector on the intro screen).
const drawer = mountEvidenceDrawer(drawerRoot, () => getAnalysisService(getState().caseId));

function navigate(screenId, { pushHash = true } = {}) {
  const target = VALID_SCREENS.has(screenId) ? screenId : "intro";
  // The drawer is a singleton mounted once, outside any screen's DOM — without this, navigating
  // away with it open leaves it showing the previous screen's evidence over the new screen,
  // which reads as "the wrong claim's evidence," not as "an old panel still open."
  drawer.close();
  setScreen(target);
  if (pushHash) {
    const hash = target === "intro" ? "" : `#${target}`;
    if (location.hash !== hash) history.pushState(null, "", hash || location.pathname);
  }
}

async function renderCurrentScreen() {
  const state = getState();
  navRoot.style.display = state.screen === "intro" || state.screen === "analyze" ? "none" : "flex";
  renderWorkflowNav(navRoot, {
    state,
    onNavigate: (id) => navigate(id),
    onRestart: () => {
      restart();
      navigate("intro");
    },
  });

  window.scrollTo(0, 0);

  const renderer = SCREEN_RENDERERS[state.screen] || renderDemoIntro;
  try {
    await renderer(screenRoot, {
      service: getAnalysisService(state.caseId),
      state,
      drawer,
      onStart: () => navigate(state.caseId === "live" ? "analyze" : "foundation"),
      onNavigate: (id) => navigate(id),
      onSelectCase: (caseId) => setCase(caseId),
    });
  } catch (err) {
    console.error("StoryMap screen render failed:", err);
    screenRoot.innerHTML = `
      <div class="card notice-card">
        <h2>Something went wrong loading this screen</h2>
        <p class="muted">${err instanceof Error ? err.message : String(err)}</p>
        <button class="primary-button" type="button" id="error-restart">Restart demo</button>
      </div>
    `;
    document.getElementById("error-restart")?.addEventListener("click", () => {
      restart();
      navigate("intro");
    });
  }
}

subscribe(() => {
  renderCurrentScreen();
});

window.addEventListener("popstate", () => {
  const fromHash = location.hash.replace("#", "") || "intro";
  navigate(fromHash, { pushHash: false });
});

// Initial route: every fresh script load — full page load or reload — starts at the demo
// introduction, unconditionally. This is deliberate and does NOT consult location.hash or
// getState().screen, even though both exist for in-session navigation below. Once a user clicks
// through a few screens, navigate() has already pushed hashes like "#foundation" into the
// address bar and getState().screen no longer says "intro" — so if the initial route trusted
// either one, simply reloading the tab (which is exactly what a "first-time user opens the
// prototype" scenario looks like after any prior use) would land past the intro. The intro is
// the pack's required guided-context step (what Wix is, why it was chosen, what decision is at
// stake, that this is public-source analysis) — it must be unskippable on load. Clearing the
// hash here also means a later reload behaves the same way, not just this one.
if (location.hash) history.replaceState(null, "", location.pathname);
navigate("intro", { pushHash: false });
