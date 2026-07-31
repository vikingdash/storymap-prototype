// Minimal app state: which screen is active, which case (Wix or HPS) is selected, and per-case
// workflow progress — edit/reject status on strategic-foundation items, leadership-decision
// responses, foundation confirmation, and narrative approval. Persisted to localStorage so a
// reload doesn't lose progress; "Restart" (pack section 10) clears it.
//
// Per-case state is namespaced under state.cases[caseId] rather than flat at the top level.
// Both cases reuse the same kind of ids (e.g. every case has an item shaped like "sc_customers"
// in spirit), so without namespacing, approving an item in one case could silently show as
// approved in the other. getState() still returns a flattened view merging the *current* case's
// state with top-level screen/caseId, so every component that reads state.approvals,
// state.edits, etc. keeps working unchanged — only the setters below know about the nesting.
//
// Note: there is no per-item "approved" status. Reviewing the strategic foundation is a single
// "Confirm strategic foundation" action (see StrategicFoundation.js) — an item is implicitly
// accepted unless the user edited or rejected it.

const STORAGE_KEY = "storymap_demo_state_v3";

function defaultCaseState() {
  return {
    visitedScreens: ["intro"],
    approvals: {}, // { [strategicChoiceId]: "edited" | "rejected" }
    edits: {}, // { [strategicChoiceId]: string } user-edited statement text
    decisionResponses: {}, // { [strategicChoiceId]: { response: string, deferred: boolean } } — leadership decisions
    foundationConfirmed: false,
    narrativeApproved: false, // user clicked "Save as working narrative" on the Narrative Map screen
  };
}

const DEFAULT_STATE = {
  screen: "intro",
  caseId: "wix",
  cases: { wix: defaultCaseState(), hps: defaultCaseState(), live: defaultCaseState() },
};

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_STATE };
    const parsed = JSON.parse(raw);
    return {
      ...DEFAULT_STATE,
      ...parsed,
      cases: { ...DEFAULT_STATE.cases, ...(parsed.cases || {}) },
    };
  } catch {
    return { ...DEFAULT_STATE };
  }
}

let state = load();
const listeners = new Set();

function persist() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function notify() {
  listeners.forEach((fn) => fn(state));
}

function currentCaseState() {
  return state.cases[state.caseId] || defaultCaseState();
}

// Immutably replaces the current case's slice of state — every setter below goes through this
// so state.cases[otherCaseId] is never touched by an action taken in the active case.
function updateCurrentCase(patch) {
  const caseId = state.caseId;
  state = {
    ...state,
    cases: {
      ...state.cases,
      [caseId]: { ...currentCaseState(), ...patch },
    },
  };
}

export function getState() {
  return { screen: state.screen, caseId: state.caseId, ...currentCaseState() };
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function setScreen(screenId) {
  const caseState = currentCaseState();
  state = { ...state, screen: screenId };
  updateCurrentCase({
    visitedScreens: caseState.visitedScreens.includes(screenId) ? caseState.visitedScreens : [...caseState.visitedScreens, screenId],
  });
  persist();
  notify();
}

// Switches the active case and returns to its intro screen. Each case's workflow progress
// (approvals, edits, confirmations) is independent and untouched by switching — selecting HPS
// after exploring Wix doesn't reset or leak into Wix's saved state.
export function setCase(caseId) {
  if (!state.cases[caseId]) return;
  state = { ...state, caseId, screen: "intro" };
  persist();
  notify();
}

// Deliberately does not call notify(): StrategicFoundation.js updates the affected item's DOM
// directly, so approving/editing/rejecting one item doesn't re-fetch and re-render the whole
// screen (which would flash a loading state over items the user isn't touching).
export function setApproval(choiceId, status, editedText) {
  const caseState = currentCaseState();
  updateCurrentCase({
    approvals: { ...caseState.approvals, [choiceId]: status },
    edits: editedText !== undefined ? { ...caseState.edits, [choiceId]: editedText } : caseState.edits,
  });
  persist();
}

// Also does not call notify() — see setApproval's note above; NarrativeMapView-style full
// re-renders aren't needed for typing into a response field or toggling "defer."
export function setDecisionResponse(choiceId, { response, deferred }) {
  const caseState = currentCaseState();
  updateCurrentCase({
    decisionResponses: { ...caseState.decisionResponses, [choiceId]: { response, deferred } },
  });
  persist();
}

export function setFoundationConfirmed(confirmed) {
  updateCurrentCase({ foundationConfirmed: confirmed });
  persist();
}

// Local-only signal that the user has provisionally approved the map — it does not mutate the
// underlying seed data (reliability rule: narrative versions are immutable) and does not publish
// or activate anything. NarrativeMapView.js updates its own DOM optimistically after calling
// this, so no notify() is needed here either.
export function setNarrativeApproved(approved) {
  updateCurrentCase({ narrativeApproved: approved });
  persist();
}

export function restart() {
  localStorage.removeItem(STORAGE_KEY);
  state = { ...DEFAULT_STATE, cases: { wix: defaultCaseState(), hps: defaultCaseState(), live: defaultCaseState() } };
  notify();
}
