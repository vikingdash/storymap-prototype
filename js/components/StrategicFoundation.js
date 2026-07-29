// Screen 2 — Strategic foundation (pack section 4). Reconstructs what the business is trying to
// do. This is a compact review, not a checklist: items render as a dense two-column summary,
// only items below 65% confidence, backed by conflicting evidence, or flagged high-impact get a
// visible "Needs review" badge and border — and only those get a Reject control. Every other
// item only offers Edit. One "View N sources" link replaces a link per evidence item. A
// "StoryMap synthesis" item (one that combines several atomic facts) shows those facts broken
// out beneath it, each traceable to one exact excerpt — a synthesis sentence itself isn't
// traceable to a single quote, so it must not be labeled "source-derived fact." Unresolved
// leadership decisions are a separate pattern: a question, an optional response field, and
// "Defer for now" — never edit/reject — with only the most narrative-material ones shown by
// default and the rest tucked under "Additional questions." A persistent "Confirm strategic
// foundation" action sits at the bottom of the viewport throughout the review.
import { statementTypeBadge, confidencePercent, escapeHtml } from "../labels.js";
import { getState, setApproval, setDecisionResponse, setFoundationConfirmed } from "../state.js";

const TYPE_GROUPS = [
  { type: "customer", title: "Chosen customers" },
  { type: "market", title: "Chosen markets" },
  { type: "market_change", title: "How the market is changing" },
  { type: "way_to_win", title: "How the company intends to win" },
  { type: "capability", title: "Capabilities" },
  { type: "proof", title: "Proof of performance" },
  { type: "assumption", title: "Strategic assumptions" },
  { type: "risk", title: "Risks" },
];

const LOW_CONFIDENCE_THRESHOLD = 0.65;

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

  container.innerHTML = `
    <section class="screen-header">
      <div class="eyebrow">1 · Strategic foundation</div>
      <h1>What the business is trying to do</h1>
      <p class="lead">StoryMap's reconstruction of the strategy behind the story, built before it writes anything. Items marked <strong>Needs review</strong> are low-confidence, high-impact, or backed by conflicting evidence — everything else you can edit but doesn't require a decision.</p>
    </section>
    <div class="foundation-groups"></div>
    <div class="card">
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
      <p class="question-inline">${escapeHtml(ctx.narrativeQuestion)}</p>
    </div>
    <div class="confirm-footer">
      <p class="muted small" data-role="confirm-summary"></p>
      <button class="primary-button" type="button" data-action="confirm">Confirm strategic foundation →</button>
    </div>
  `;

  const groupsEl = container.querySelector(".foundation-groups");
  TYPE_GROUPS.forEach((group) => {
    const items = choices.filter((c) => c.type === group.type);
    if (!items.length) return;
    const section = document.createElement("div");
    section.className = "card";
    section.innerHTML = `<h2>${escapeHtml(group.title)}</h2><div class="foundation-items"></div>`;
    const itemsEl = section.querySelector(".foundation-items");
    const refreshSummary = () => updateConfirmSummary(container, getState(), choices);
    items.forEach((choice) => itemsEl.appendChild(renderFoundationItem(choice, state, drawer, evidenceIndex, refreshSummary)));
    groupsEl.appendChild(section);
  });

  const decisionList = container.querySelector(".decision-list");
  primaryDecisions.forEach((choice) => decisionList.appendChild(renderDecisionItem(choice, state)));
  const secondaryList = container.querySelector(".decision-list.secondary");
  secondaryDecisions.forEach((choice) => secondaryList.appendChild(renderDecisionItem(choice, state)));

  updateConfirmSummary(container, state, choices);

  container.querySelector('[data-action="confirm"]').addEventListener("click", () => {
    setFoundationConfirmed(true);
    onNavigate("diagnosis");
  });
}

// Confidence already reflects how well the linked evidence (weighted by relevance and strength)
// supports the statement — see recalculateConfidence() in case-utils.js — so a low score here is
// itself evidence of thin support, not a separate signal to recompute. "Conflicting evidence" is
// its own explicit reason since a statement can have solid confidence overall while still having
// one link that actively cuts against it.
function getReviewReasons(choice) {
  const reasons = [];
  if (choice.confidence > 0 && choice.confidence < LOW_CONFIDENCE_THRESHOLD) reasons.push("Below 65% confidence");
  if (choice.type === "risk") reasons.push("High impact");
  if (choice.evidence.some((link) => link.relevance === "conflicting")) reasons.push("Conflicting evidence");
  return reasons;
}

function renderFoundationItem(choice, state, drawer, evidenceIndex, refreshSummary) {
  const badge = statementTypeBadge(choice.statementType);
  const reviewReasons = getReviewReasons(choice);
  const needsReview = reviewReasons.length > 0;
  const userStatus = state.approvals[choice.id]; // "edited" | "rejected" | undefined
  const displayText = state.edits[choice.id] ?? choice.statement;
  const sourceCount = choice.evidence.length;
  const isSynthesis = choice.statementType === "storymap_synthesis";

  const el = document.createElement("div");
  el.className = `foundation-item${needsReview ? " needs-review" : ""}${userStatus === "rejected" ? " rejected" : ""}`;
  el.innerHTML = `
    <div class="foundation-item-top">
      <span class="${badge.className}">${badge.label}</span>
      ${needsReview ? `<span class="needs-review-badge" title="${escapeHtml(reviewReasons.join(" · "))}">Needs review</span>` : ""}
      ${choice.confidence > 0 ? `<span class="confidence-note">${confidencePercent(choice.confidence)} confidence</span>` : ""}
    </div>
    <p class="foundation-statement" data-role="statement">${escapeHtml(displayText)}</p>
    <textarea class="edit-textarea" style="display:none"></textarea>
    <div class="edit-save-row" style="display:none">
      <button type="button" class="pill-button" data-action="save-edit">Save</button>
      <button type="button" class="pill-button" data-action="cancel-edit">Cancel</button>
    </div>
    ${isSynthesis ? `<div class="atomic-facts" data-role="atomic-facts"></div>` : ""}
    <div class="item-footer">
      ${sourceCount ? `<button type="button" class="text-link" data-action="view-sources">View ${sourceCount} source${sourceCount === 1 ? "" : "s"}</button>` : `<span></span>`}
      <div class="item-actions" data-role="item-actions">
        <button type="button" class="text-link" data-action="edit">Edit</button>
        ${needsReview ? `<button type="button" class="text-link text-link-danger" data-action="reject">Reject</button>` : ""}
      </div>
    </div>
    <span class="item-status-note" data-role="status-note">${userStatus ? statusNote(userStatus) : ""}</span>
  `;

  const viewSourcesBtn = el.querySelector('[data-action="view-sources"]');
  if (viewSourcesBtn) {
    viewSourcesBtn.addEventListener("click", () => drawer.openEvidenceLinks(choice.evidence, choice.statement));
  }

  // A synthesis sentence itself isn't traceable to one excerpt — the atomic facts underneath it
  // are. Each row is its own source_fact, individually linked to exactly one evidence item.
  const atomicFactsEl = el.querySelector('[data-role="atomic-facts"]');
  if (atomicFactsEl) {
    const factBadge = statementTypeBadge("source_fact");
    choice.evidence
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
  const summaryEl = container.querySelector('[data-role="confirm-summary"]');
  if (!edited && !rejected) {
    summaryEl.textContent = "Reviewing StoryMap's understanding as shown above — nothing changed.";
  } else {
    const parts = [];
    if (edited) parts.push(`${edited} item${edited === 1 ? "" : "s"} edited`);
    if (rejected) parts.push(`${rejected} item${rejected === 1 ? "" : "s"} rejected`);
    summaryEl.textContent = `${parts.join(", ")}. Everything else is accepted as shown.`;
  }
}
