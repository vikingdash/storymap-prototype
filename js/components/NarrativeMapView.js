// Screen 6 — Narrative Map (pack section 4). Context/Tension/Belief/Role/Value/Proof/Direction,
// plus core claims, priority audiences, likely objections, competitor contrast, unsupported or
// weak claims, version number and approval status. Core claims are explicit named statements
// (not a repeated, unlabeled source-publisher chip standing in for several different things the
// map asserts) — each shows its evidence strength, support classification and source count, and
// is individually click-through to the evidence drawer. The screen ends with a real decision
// action, "Approve as provisional narrative," not just a "continue" link.
import { escapeHtml, relevanceLabel, strengthLabel } from "../labels.js";
import { setNarrativeApproved } from "../state.js";

const PARTS = [
  ["context", "Context"],
  ["tension", "Tension"],
  ["belief", "Belief"],
  ["role", "Role"],
  ["value", "Value"],
  ["proof", "Proof"],
  ["direction", "Direction"],
];

export async function renderNarrativeMapView(container, { service, state, drawer, onNavigate }) {
  container.innerHTML = `<div class="loading">Structuring the Narrative Map…</div>`;
  const [map, audiences, competitorContrasts, evidenceIndex] = await Promise.all([
    service.getNarrativeMap(),
    service.getAudiences(),
    service.getCompetitorContrasts(),
    service.getEvidenceIndex(),
  ]);

  const approved = state.narrativeApproved;

  container.innerHTML = `
    <section class="screen-header">
      <div class="eyebrow">5 · Narrative Map</div>
      <h1>Draft Narrative Map</h1>
      <p class="lead">This is the structured output that messaging, executive communications and future monitoring would use once leadership approves it.</p>
      <div class="map-meta">
        <span class="chip">Version ${map.version}</span>
        <span class="chip chip-status-${approved ? "approved" : map.status}" data-role="status-chip">${approved ? "Approved (provisional)" : escapeHtml(capitalize(map.status))}</span>
      </div>
    </section>

    <div class="card">
      <div class="map-grid"></div>
    </div>

    <div class="two-col">
      <div class="card">
        <h3>Priority audiences</h3>
        <div class="audience-list"></div>
      </div>
      <div class="card">
        <h3>Competitor contrast</h3>
        <div class="contrast-list"></div>
      </div>
    </div>

    <div class="two-col">
      <div class="card">
        <h3>Likely objections</h3>
        <ul class="numbered-list">${map.likelyObjections.map((o) => `<li>${escapeHtml(o)}</li>`).join("")}</ul>
      </div>
      <div class="card">
        <h3>Unresolved leadership decisions</h3>
        <ul class="numbered-list">${map.unresolvedQuestions.map((q) => `<li>${escapeHtml(q)}</li>`).join("")}</ul>
      </div>
    </div>

    <div class="card notice-card">
      <h3>Unsupported or weak claims</h3>
      <p class="muted">StoryMap flags these rather than polishing them away.</p>
      <ul class="numbered-list">${map.weakOrUnsupportedClaims.map((c) => `<li>${escapeHtml(c)}</li>`).join("")}</ul>
    </div>

    <div class="card">
      <h3>Core claims behind this map</h3>
      <div class="map-claims-list" data-role="map-claims-list"></div>
    </div>

    <div class="card approve-card">
      <h3>Approve as provisional narrative</h3>
      <p class="muted small">This creates Narrative Map Version 1. It does not publish or activate external messaging.</p>
      <button class="primary-button" type="button" data-action="approve" ${approved ? "disabled" : ""}>
        ${approved ? "Approved as provisional narrative ✓" : "Approve as provisional narrative"}
      </button>
    </div>

    <div class="screen-footer">
      <button class="text-link" type="button" data-action="continue">Open the Evidence Room →</button>
    </div>
  `;

  const mapGrid = container.querySelector(".map-grid");
  PARTS.forEach(([key, label]) => {
    const row = document.createElement("div");
    row.className = "map-row";
    row.innerHTML = `<div class="map-key">${escapeHtml(label)}</div><div class="map-value">${escapeHtml(map.sevenParts[key])}</div>`;
    mapGrid.appendChild(row);
  });

  const audienceList = container.querySelector(".audience-list");
  audiences.forEach((a) => {
    const row = document.createElement("div");
    row.className = "list-row";
    row.innerHTML = `<b>${escapeHtml(a.name)}</b><span class="muted">${escapeHtml(a.description)}</span>`;
    audienceList.appendChild(row);
  });

  const contrastList = container.querySelector(".contrast-list");
  competitorContrasts.forEach((c) => {
    const row = document.createElement("div");
    row.className = "list-row";
    row.innerHTML = `<b>${escapeHtml(c.competitor)}</b><span class="muted">${escapeHtml(c.contrast)}</span>`;
    contrastList.appendChild(row);
  });

  const claimsList = container.querySelector('[data-role="map-claims-list"]');
  map.coreClaims.forEach((claim) => claimsList.appendChild(renderCoreClaim(claim, evidenceIndex, drawer)));

  container.querySelector('[data-action="continue"]').addEventListener("click", () => onNavigate("evidence"));

  const approveBtn = container.querySelector('[data-action="approve"]');
  approveBtn.addEventListener("click", () => {
    setNarrativeApproved(true);
    approveBtn.disabled = true;
    approveBtn.textContent = "Approved as provisional narrative ✓";
    const statusChip = container.querySelector('[data-role="status-chip"]');
    statusChip.textContent = "Approved (provisional)";
    statusChip.className = "chip chip-status-approved";
  });
}

function renderCoreClaim(claim, evidenceIndex, drawer) {
  const items = claim.evidence.map((link) => ({ link, ev: evidenceIndex.getEvidence(link.evidenceId) })).filter((x) => x.ev);
  const relevances = [...new Set(items.map((x) => x.link.relevance))];
  const strengths = [...new Set(items.map((x) => x.ev.strength))];
  const sourceCount = new Set(items.map((x) => x.ev.sourceId)).size;

  const el = document.createElement("div");
  el.className = "map-claim-row";
  el.innerHTML = `
    <p class="map-claim-statement">${escapeHtml(claim.statement)}</p>
    <div class="chip-row">
      ${relevances.map((r) => { const l = relevanceLabel(r); return `<span class="${l.className}">${l.label}</span>`; }).join("")}
      ${strengths.map((s) => { const l = strengthLabel(s); return `<span class="${l.className}">${l.label}</span>`; }).join("")}
      <span class="chip">${sourceCount} source${sourceCount === 1 ? "" : "s"}</span>
    </div>
    <button type="button" class="text-link" data-action="view-evidence">View evidence</button>
  `;
  el.querySelector('[data-action="view-evidence"]').addEventListener("click", () => drawer.openEvidenceLinks(claim.evidence, claim.statement));
  return el;
}

function capitalize(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
