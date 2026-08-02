// Screen 2 — Strategic foundation (pack section 4; rebuilt per the approved UX & visual-system
// wireframe). Progressive disclosure over one dense grid: the first viewport answers "where am
// I / what did StoryMap conclude / what needs my attention / why trust it / what next" without
// scrolling — a synthesized summary, three compact business dimensions, at most three review
// items, one primary action. The seven detailed categories (Customers, Markets, Capabilities,
// Competitive approach, Proof, Assumptions, Risks — Risks deliberately kept separate from
// Assumptions, never merged) sit collapsed behind native <details> until opened. Every field and
// action the previous dense layout offered still exists; nothing analytical was dropped, only
// regrouped or moved behind a click. Confidence is shown as a plain-language label by default —
// never a percentage; the underlying number is preserved on each rendered item as a data
// attribute for tests, and confidence itself is never recalculated here. The label shown is
// now stage-aware (labels.js's narrativeStageJudgment) rather than one flat confidence band
// for every claim — a strategic_direction claim is judged on directional credibility, not
// "is this already proven," and a leadership-dependent aspiration always reads as needing
// approval rather than showing a low, falsely-discouraging score.
import { statementTypeBadge, narrativeStageJudgment, escapeHtml } from "../labels.js";
import { getState, setApproval, setDecisionResponse, setFoundationConfirmed } from "../state.js";
import { regenerateAnalysis } from "../live-analysis-service.js";

const TYPE_GROUPS = [
  { types: ["customer"], id: "customers", title: "Customers" },
  { types: ["market", "market_change"], id: "markets", title: "Markets" },
  { types: ["capability"], id: "capabilities", title: "Capabilities" },
  { types: ["way_to_win"], id: "competitive-approach", title: "Competitive approach" },
  { types: ["proof"], id: "proof", title: "Proof" },
  { types: ["assumption"], id: "assumptions", title: "Assumptions" },
  { types: ["risk"], id: "risks", title: "Risks" },
];

const MAX_REVIEW_ITEMS = 3;
const LOW_CONFIDENCE_FOR_REVIEW = 0.5;
// D-003 fix: the floor for genuinely LIMITED directional credibility (matches labels.js's
// DIRECTIONAL_CREDIBILITY_BANDS "Moderate" floor) — a strategic_direction claim with
// Moderate or Strong directional credibility must never be swept into "needs your
// attention" merely because its present-state confidence is naturally low, which is
// expected and correct for a forward-looking claim, not a defect in it.
const LOW_DIRECTIONAL_CREDIBILITY_FOR_REVIEW = 0.4;

// --- Deterministic synthesized summary --------------------------------------------------
// Built ONLY from already-persisted strategic-foundation fields, via a fixed template — no
// model call, no invented connecting claims. Each dimension's sentence is either an existing
// item's own statement text (normalized for capitalization/punctuation only, never edited in
// substance) or omitted entirely if that dimension has no qualifying item. Capped at roughly
// 80 words. Exported so it's independently unit-testable without a DOM render.
export const SYNTHESIS_FALLBACK =
  "StoryMap hasn't reconstructed enough of the strategic foundation yet to summarize it in one paragraph — see the sections below for what's confirmed so far.";

function bestItemOfTypes(choices, types) {
  const matches = choices.filter((c) => types.includes(c.type));
  if (!matches.length) return null;
  return [...matches].sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0))[0];
}

function normalizeSentence(text) {
  const trimmed = (text || "").trim();
  if (!trimmed) return "";
  const withPeriod = /[.!?]$/.test(trimmed) ? trimmed : `${trimmed}.`;
  return withPeriod.charAt(0).toUpperCase() + withPeriod.slice(1);
}

function truncateToWords(text, maxWords) {
  const words = text.trim().split(/\s+/);
  if (words.length <= maxWords) return text.trim();
  return `${words.slice(0, maxWords).join(" ")}…`;
}

export function buildSynthesizedSummary(choices) {
  const who = bestItemOfTypes(choices, ["customer"]);
  const value = bestItemOfTypes(choices, ["capability", "proof"]);
  const compete = bestItemOfTypes(choices, ["way_to_win"]);
  const sentences = [who, value, compete].filter(Boolean).map((item) => normalizeSentence(item.statement)).filter(Boolean);
  if (!sentences.length) return SYNTHESIS_FALLBACK;
  return truncateToWords(sentences.join(" "), 80);
}

const DIMENSION_FALLBACK = "Not yet determined";

export function buildDimensionChips(choices) {
  const who = bestItemOfTypes(choices, ["customer"]);
  const value = bestItemOfTypes(choices, ["capability", "proof"]);
  const compete = bestItemOfTypes(choices, ["way_to_win"]);
  return [
    { label: "Who it serves", value: who ? truncateToWords(who.statement, 6) : DIMENSION_FALLBACK },
    { label: "What it creates", value: value ? truncateToWords(value.statement, 6) : DIMENSION_FALLBACK },
    { label: "How it competes", value: compete ? truncateToWords(compete.statement, 6) : DIMENSION_FALLBACK },
  ];
}

// --- Review strip (max 3, ranked) ---------------------------------------------------------
// Ranking: unresolved primary leadership decisions, then risk items, then conflicting-evidence
// items, then approval-required items, then stage-unsupported items — every one of these is
// real, already-persisted data, never a fourth independent recalculation of "what matters."
//
// D-003 fix: this used to flag anything with confidence < 0.5, full stop — which meant a
// strategic_direction claim landed in "needs your attention" for exactly the reason it's
// SUPPOSED to have low present-state confidence (it's a forward claim, not yet a proven
// fact), conflating "not fully proven yet" with "needs review," the precise failure the
// narrative-stage model exists to prevent. An item now only surfaces here for one of four
// reasons: (1) it's a genuine open leadership decision (primaryDecisions, unchanged), (2) a
// real risk (riskItems, unchanged), (3) its evidence materially conflicts (conflicting,
// unchanged), (4) leadership approval is genuinely required by its own declared maturity
// (aspiration_pending_leadership — always surfaced, never gated by a number) or it is
// actually unsupported FOR ITS OWN STAGE (proven_today/emerging/in_build still judged by
// confidence, exactly as before; strategic_direction judged by directionalCredibility
// against its own, separate, correct floor). Wording that overstates maturity (e.g. D-001)
// is not mechanically detectable here and is not attempted — that stays a manual/editorial
// check, not a new automated feature.
function hasDecisionResponse(choiceId, decisionResponses) {
  const r = decisionResponses[choiceId];
  return !!(r && (r.response || r.deferred));
}

function isUnsupportedForItsStage(choice) {
  if (choice.narrativeStage === "strategic_direction") {
    return typeof choice.directionalCredibility === "number" && choice.directionalCredibility < LOW_DIRECTIONAL_CREDIBILITY_FOR_REVIEW;
  }
  if (choice.narrativeStage === "aspiration_pending_leadership") {
    return false; // surfaced unconditionally via approvalRequired below, never by a number
  }
  return typeof choice.confidence === "number" && choice.confidence < LOW_CONFIDENCE_FOR_REVIEW;
}

export function buildReviewList(choices, decisionResponses) {
  const primaryDecisions = choices.filter((c) => c.type === "unresolved" && c.priority === "primary" && !hasDecisionResponse(c.id, decisionResponses));
  const riskItems = choices.filter((c) => c.type === "risk");
  const conflicting = choices.filter((c) => c.type !== "unresolved" && c.type !== "risk" && (c.evidence || []).some((l) => l.relevance === "conflicting"));
  const conflictingIds = new Set(conflicting.map((c) => c.id));
  const approvalRequired = choices.filter(
    (c) => c.type !== "unresolved" && c.type !== "risk" && !conflictingIds.has(c.id) && c.narrativeStage === "aspiration_pending_leadership"
  );
  const approvalRequiredIds = new Set(approvalRequired.map((c) => c.id));
  const unsupportedForStage = choices.filter(
    (c) => c.type !== "unresolved" && c.type !== "risk" && !conflictingIds.has(c.id) && !approvalRequiredIds.has(c.id) && isUnsupportedForItsStage(c)
  );
  return [
    ...primaryDecisions.map((c) => ({ item: c, tag: "decision", sectionId: null })),
    ...riskItems.map((c) => ({ item: c, tag: "risk", sectionId: "risks" })),
    ...conflicting.map((c) => ({ item: c, tag: "conflicting", sectionId: sectionIdForType(c.type) })),
    ...approvalRequired.map((c) => ({ item: c, tag: "approval", sectionId: sectionIdForType(c.type) })),
    ...unsupportedForStage.map((c) => ({ item: c, tag: "confirm", sectionId: sectionIdForType(c.type) })),
  ];
}

function sectionIdForType(type) {
  const group = TYPE_GROUPS.find((g) => g.types.includes(type));
  return group ? group.id : null;
}

const REVIEW_TAG_LABELS = { decision: "decision", risk: "risk", conflicting: "conflicting", confirm: "confirm", approval: "requires approval" };

export async function renderStrategicFoundation(container, { service, state, drawer, onNavigate }) {
  container.innerHTML = `<div class="loading">Reconstructing strategic foundation…</div>`;
  const [choices, ctx, evidenceIndex] = await Promise.all([
    service.getStrategicFoundation(),
    service.getCaseContext(),
    service.getEvidenceIndex(),
  ]);

  const decisions = choices.filter((c) => c.type === "unresolved");
  const primaryDecisions = decisions.filter((d) => d.priority === "primary");
  const secondaryDecisions = decisions.filter((d) => d.priority !== "primary");

  const summaryText = buildSynthesizedSummary(choices);
  const dimensionChips = buildDimensionChips(choices);
  const reviewList = buildReviewList(choices, state.decisionResponses);
  const visibleReview = reviewList.slice(0, MAX_REVIEW_ITEMS);
  const overflowReview = reviewList.slice(MAX_REVIEW_ITEMS);

  container.innerHTML = `
    <section class="screen-header">
      <div class="eyebrow">1 · Strategic foundation</div>
      <h1 class="sf-h1">What ${escapeHtml(ctx?.company?.name || "the business")} is trying to do</h1>
    </section>

    <div class="sf-summary-card">
      <p class="sf-summary-text">${escapeHtml(summaryText)}</p>
      <div class="sf-dims">
        ${dimensionChips.map((d) => `
          <div class="sf-dim">
            <div class="sf-dim-label">${escapeHtml(d.label)}</div>
            <div class="sf-dim-value">${escapeHtml(d.value)}</div>
          </div>
        `).join("")}
      </div>
    </div>

    ${visibleReview.length ? `
    <div class="sf-review-card">
      <div class="sf-review-title">${visibleReview.length} item${visibleReview.length === 1 ? "" : "s"} need${visibleReview.length === 1 ? "s" : ""} your attention</div>
      <div data-role="review-list"></div>
      ${overflowReview.length ? `<button type="button" class="sf-review-more" data-action="show-all-review">All ${reviewList.length} items needing review →</button>` : ""}
    </div>
    ` : ""}

    <div class="confirm-footer sf-cta-sticky-mobile">
      <p class="muted small" data-role="confirm-summary"></p>
      ${state.caseId === "live" ? `<p class="muted small" data-role="regenerate-status"></p>` : ""}
      <button class="primary-button" type="button" data-action="confirm">Confirm strategic foundation →</button>
    </div>

    <div class="sf-sections" data-role="sections"></div>

    <div class="card" style="margin-top:24px;">
      <h2>Leadership decisions needed</h2>
      <p class="muted small">StoryMap can proceed with a provisional recommendation, but these choices affect the final narrative.</p>
      <div class="decision-list"></div>
      <details class="additional-questions" ${secondaryDecisions.length ? "" : "style=\"display:none\""}>
        <summary>Additional questions (${secondaryDecisions.length})</summary>
        <div class="decision-list secondary"></div>
      </details>
    </div>

    <div class="card notice-card">
      <h3>Decision the narrative must resolve</h3>
      <p class="question-inline">${escapeHtml(ctx?.narrativeQuestion || "")}</p>
    </div>

    ${state.caseId === "live" ? `
    <div class="card" data-role="regenerate-card">
      <h3>Regenerate analysis</h3>
      <p class="muted small">Reruns diagnosis onward using any edits/rejections above. Never fires on its own — only when you click this.</p>
      <button class="pill-button" type="button" data-action="regenerate">Regenerate analysis</button>
    </div>
    ` : ""}
  `;

  // --- Review strip rows ---
  const reviewListEl = container.querySelector('[data-role="review-list"]');
  function renderReviewRow(entry, index) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "sf-review-item";
    row.innerHTML = `<span class="sf-review-num">${index + 1}</span><span>${escapeHtml(entry.item.statement)}</span><span class="sf-review-tag">${escapeHtml(REVIEW_TAG_LABELS[entry.tag] || entry.tag)}</span>`;
    row.addEventListener("click", () => jumpToReviewTarget(container, entry));
    return row;
  }
  if (reviewListEl) {
    visibleReview.forEach((entry, index) => reviewListEl.appendChild(renderReviewRow(entry, index)));
    const showAllBtn = container.querySelector('[data-action="show-all-review"]');
    if (showAllBtn) {
      showAllBtn.addEventListener("click", () => {
        reviewListEl.innerHTML = "";
        reviewList.forEach((entry, index) => reviewListEl.appendChild(renderReviewRow(entry, index)));
        showAllBtn.remove();
      });
    }
  }

  // --- Disclosure sections ---
  const sectionsEl = container.querySelector('[data-role="sections"]');
  const refreshSummary = () => updateConfirmSummary(container, getState(), choices);
  TYPE_GROUPS.forEach((group) => {
    const items = choices.filter((c) => group.types.includes(c.type));
    if (!items.length) return;
    const details = document.createElement("details");
    details.className = "sf-section";
    details.id = `sf-section-${group.id}`;
    // tabindex="0" is a no-op in a real browser (summary is natively focusable) — added
    // explicitly because it makes the focus behavior robust rather than implicit, and
    // several DOM test environments don't model native <summary> focusability correctly.
    details.innerHTML = `<summary tabindex="0">${escapeHtml(group.title)} <span class="sf-count">${items.length} item${items.length === 1 ? "" : "s"}</span></summary><div class="sf-section-body" data-role="section-body"></div>`;
    const bodyEl = details.querySelector('[data-role="section-body"]');
    items.forEach((choice) => bodyEl.appendChild(renderFoundationItem(choice, state, drawer, evidenceIndex, refreshSummary)));
    sectionsEl.appendChild(details);
  });

  // --- Leadership decisions ---
  const decisionList = container.querySelector(".decision-list");
  primaryDecisions.forEach((choice) => decisionList.appendChild(renderDecisionItem(choice, state)));
  const secondaryList = container.querySelector(".decision-list.secondary");
  secondaryDecisions.forEach((choice) => secondaryList.appendChild(renderDecisionItem(choice, state)));

  updateConfirmSummary(container, state, choices);

  container.querySelectorAll('[data-action="confirm"]').forEach((btn) => {
    btn.addEventListener("click", () => {
      setFoundationConfirmed(true);
      onNavigate("diagnosis");
    });
  });

  // Live case only — the ONLY trigger for downstream regeneration. Never fires on a
  // keystroke or an individual edit/reject action above; the user must explicitly click
  // this after making whatever edits they want. Moved to the sections footer (demoted
  // from the primary CTA row) — same behavior as before, different position.
  const regenerateBtn = container.querySelector('[data-action="regenerate"]');
  if (regenerateBtn) {
    const statusEl = container.querySelector('[data-role="regenerate-status"]');
    regenerateBtn.addEventListener("click", async () => {
      const current = getState();
      const editedFoundation = choices
        .filter((c) => c.type !== "unresolved")
        .filter((c) => current.approvals[c.id] !== "rejected")
        .map((c) => ({ ...c, statement: current.edits[c.id] ?? c.statement }));

      regenerateBtn.disabled = true;
      regenerateBtn.textContent = "Regenerating…";
      if (statusEl) { statusEl.textContent = ""; statusEl.style.color = ""; }
      try {
        const status = await regenerateAnalysis(editedFoundation);
        if (statusEl) {
          if (status.status === "failed") {
            statusEl.textContent = status.error || "Regeneration failed.";
            statusEl.style.color = "var(--red)";
          } else {
            statusEl.textContent = "Done — diagnosis, narrative choices and recommendation now reflect your edits.";
          }
        }
      } catch (err) {
        if (statusEl) {
          statusEl.textContent = err instanceof Error ? err.message : String(err);
          statusEl.style.color = "var(--red)";
        }
      } finally {
        regenerateBtn.disabled = false;
        regenerateBtn.textContent = "Regenerate analysis";
      }
    });
  }
}

// Opens the review item's owning section (expanding it) and moves focus to its <summary> —
// not just a scroll — so a keyboard user lands somewhere operable. Leadership-decision
// entries (sectionId === null) scroll/focus the Leadership decisions card instead, since
// they live outside the seven disclosure sections.
function jumpToReviewTarget(container, entry) {
  if (!entry.sectionId) {
    const decisionsCard = container.querySelector(".decision-list")?.closest(".card");
    if (decisionsCard) {
      decisionsCard.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
      decisionsCard.setAttribute("tabindex", "-1");
      decisionsCard.focus();
    }
    return;
  }
  const section = container.querySelector(`#sf-section-${entry.sectionId}`);
  if (!section) return;
  section.open = true;
  const summary = section.querySelector("summary");
  summary.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
  summary.focus();
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function renderFoundationItem(choice, state, drawer, evidenceIndex, refreshSummary) {
  const badge = statementTypeBadge(choice.statementType);
  const conf = narrativeStageJudgment(choice.narrativeStage, choice.confidence, choice.directionalCredibility, choice.evidence);
  const userStatus = state.approvals[choice.id]; // "edited" | "rejected" | undefined
  const displayText = state.edits[choice.id] ?? choice.statement;
  const evidenceLinks = choice.evidence || [];
  const sourceCount = evidenceLinks.length;
  const isSynthesis = choice.statementType === "storymap_synthesis";
  // Matches the original rule exactly: a risk item is always offered Reject (inherently
  // "high impact", regardless of how confidently it's evidenced) — confidence/conflict
  // alone would have silently dropped this for a well-evidenced risk, which is a real
  // capability regression the capability-preservation tests exist to catch.
  const needsReview = choice.type === "risk"
    || conf.className.includes("sf-conf-confirm") || conf.className.includes("sf-conf-conflict") || conf.className.includes("sf-conf-early");

  const el = document.createElement("div");
  el.className = `sf-item${userStatus === "rejected" ? " rejected" : ""}`;
  el.dataset.confidence = typeof choice.confidence === "number" ? String(choice.confidence) : "";
  el.innerHTML = `
    <div class="sf-item-top">
      <span class="${badge.className}">${badge.label}</span>
      <span class="${conf.className}">${escapeHtml(conf.label)}</span>
    </div>
    <p class="sf-item-text" data-role="statement">${escapeHtml(displayText)}</p>
    <textarea class="edit-textarea" style="display:none"></textarea>
    <div class="edit-save-row" style="display:none">
      <button type="button" class="pill-button" data-action="save-edit">Save</button>
      <button type="button" class="pill-button" data-action="cancel-edit">Cancel</button>
    </div>
    ${isSynthesis ? `<div class="atomic-facts" data-role="atomic-facts"></div>` : ""}
    <div class="item-footer">
      ${sourceCount ? `<button type="button" class="text-link" data-action="view-sources">View evidence (${sourceCount})</button>` : `<span></span>`}
      <div class="item-actions" data-role="item-actions">
        <button type="button" class="text-link" data-action="edit">Edit</button>
        ${needsReview ? `<button type="button" class="text-link text-link-danger" data-action="reject">Reject</button>` : ""}
      </div>
    </div>
    <span class="item-status-note" data-role="status-note">${userStatus ? statusNote(userStatus) : ""}</span>
  `;

  const viewSourcesBtn = el.querySelector('[data-action="view-sources"]');
  if (viewSourcesBtn) {
    viewSourcesBtn.addEventListener("click", () => drawer.openEvidenceLinks(evidenceLinks, choice.statement));
  }

  // A synthesis sentence itself isn't traceable to one excerpt — the atomic facts underneath
  // it are. Each row is its own source_fact, individually linked to exactly one evidence item.
  const atomicFactsEl = el.querySelector('[data-role="atomic-facts"]');
  if (atomicFactsEl) {
    const factBadge = statementTypeBadge("source_fact");
    evidenceLinks
      .filter((link) => link.relevance === "direct")
      .forEach((link) => {
        const found = evidenceIndex.getEvidenceWithSource(link.evidenceId);
        if (!found) return;
        const row = document.createElement("button");
        row.type = "button";
        row.className = "atomic-fact-row";
        row.innerHTML = `<span class="${factBadge.className}">${factBadge.label}</span><span class="atomic-fact-text">${escapeHtml(found.evidence.paraphrase)}</span>`;
        row.addEventListener("click", () => drawer.openEvidenceLink(link, choice.statement));
        atomicFactsEl.appendChild(row);
      });
  }

  const statementEl = el.querySelector('[data-role="statement"]');
  const textarea = el.querySelector(".edit-textarea");
  const editSaveRow = el.querySelector(".edit-save-row");
  const itemActions = el.querySelector('[data-role="item-actions"]');
  const statusNoteEl = el.querySelector('[data-role="status-note"]');

  function enterEditMode() {
    textarea.value = state.edits[choice.id] ?? choice.statement;
    statementEl.style.display = "none";
    textarea.style.display = "block";
    editSaveRow.style.display = "flex";
    itemActions.style.display = "none";
    textarea.focus();
  }

  function exitEditMode() {
    statementEl.style.display = "block";
    textarea.style.display = "none";
    editSaveRow.style.display = "none";
    itemActions.style.display = "flex";
  }

  el.querySelector('[data-action="edit"]').addEventListener("click", enterEditMode);
  el.querySelector('[data-action="cancel-edit"]').addEventListener("click", exitEditMode);
  el.querySelector('[data-action="save-edit"]').addEventListener("click", () => {
    setApproval(choice.id, "edited", textarea.value);
    statementEl.textContent = textarea.value;
    statusNoteEl.textContent = statusNote("edited");
    exitEditMode();
    refreshSummary();
  });

  const rejectBtn = el.querySelector('[data-action="reject"]');
  if (rejectBtn) {
    rejectBtn.addEventListener("click", () => {
      setApproval(choice.id, "rejected");
      el.classList.add("rejected");
      statusNoteEl.innerHTML = "";
      statusNoteEl.appendChild(document.createTextNode(statusNote("rejected") + " "));
      const undo = document.createElement("button");
      undo.type = "button";
      undo.className = "text-link";
      undo.textContent = "Undo";
      undo.addEventListener("click", () => {
        setApproval(choice.id, undefined);
        el.classList.remove("rejected");
        statusNoteEl.textContent = "";
        refreshSummary();
      });
      statusNoteEl.appendChild(undo);
      refreshSummary();
    });
  }

  return el;
}

function statusNote(status) {
  return { edited: "Edited by you", rejected: "Rejected — excluded from the narrative" }[status] || "";
}

function renderDecisionItem(choice, state) {
  const existing = state.decisionResponses[choice.id] || { response: "", deferred: false };
  const el = document.createElement("div");
  el.className = `decision-item${existing.deferred ? " deferred" : ""}`;
  el.innerHTML = `
    <p class="decision-question">${escapeHtml(choice.statement)}</p>
    <textarea class="edit-textarea decision-response-textarea" placeholder="Add leadership's answer (optional)">${escapeHtml(existing.response)}</textarea>
    <div class="decision-actions">
      <button type="button" class="pill-button" data-action="save-response">Save answer</button>
      <button type="button" class="pill-button ${existing.deferred ? "pill-active-defer" : ""}" data-action="defer">${existing.deferred ? "Deferred" : "Defer for now"}</button>
      <span class="item-status-note" data-role="decision-note"></span>
    </div>
  `;

  const textarea = el.querySelector(".decision-response-textarea");
  const deferBtn = el.querySelector('[data-action="defer"]');
  const note = el.querySelector('[data-role="decision-note"]');

  el.querySelector('[data-action="save-response"]').addEventListener("click", () => {
    const deferred = el.classList.contains("deferred");
    setDecisionResponse(choice.id, { response: textarea.value, deferred });
    note.textContent = textarea.value ? "Answer saved" : "";
  });

  deferBtn.addEventListener("click", () => {
    const nowDeferred = !el.classList.contains("deferred");
    el.classList.toggle("deferred", nowDeferred);
    deferBtn.textContent = nowDeferred ? "Deferred" : "Defer for now";
    deferBtn.classList.toggle("pill-active-defer", nowDeferred);
    setDecisionResponse(choice.id, { response: textarea.value, deferred: nowDeferred });
    note.textContent = nowDeferred ? "Deferred — revisit before activation" : "";
  });

  return el;
}

function updateConfirmSummary(container, state, choices) {
  const foundationIds = new Set(choices.filter((c) => c.type !== "unresolved").map((c) => c.id));
  let edited = 0;
  let rejected = 0;
  Object.entries(state.approvals).forEach(([id, status]) => {
    if (!foundationIds.has(id)) return;
    if (status === "edited") edited++;
    if (status === "rejected") rejected++;
  });
  container.querySelectorAll('[data-role="confirm-summary"]').forEach((summaryEl) => {
    if (!edited && !rejected) {
      summaryEl.textContent = "Reviewing StoryMap's understanding as shown above — nothing changed.";
    } else {
      const parts = [];
      if (edited) parts.push(`${edited} item${edited === 1 ? "" : "s"} edited`);
      if (rejected) parts.push(`${rejected} item${rejected === 1 ? "" : "s"} rejected`);
      summaryEl.textContent = `${parts.join(", ")}. Everything else is accepted as shown.`;
    }
  });
}
