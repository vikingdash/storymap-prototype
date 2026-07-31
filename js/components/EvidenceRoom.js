// Screen 7 — Evidence room (pack section 4). Every material statement should be traceable:
// source title, publisher, date, URL, excerpt, StoryMap paraphrase, what it supports, source
// type, evidence strength, freshness, confidence — all in one place, grouped by source.
//
// Each source shows a concise, always-visible summary (publisher, date, type, title, official
// link); the excerpts, paraphrases and per-dimension detail are collapsed behind "Show evidence
// details" so the screen scans instead of overwhelming. What a piece of evidence "supports" is
// grouped by which screen it appears on, with the exact claim/finding title (not truncated) as a
// link that jumps to that screen — not raw internal ids or clipped text. Filters narrow by
// source type, company the source is about, and which screen it supports.
import { strengthLabel, freshnessLabel, confidencePercent, escapeHtml } from "../labels.js";
import { getLastDiagnostics } from "../live-analysis-service.js";

const SOURCE_TYPE_LABELS = {
  internal: "Internal document",
  website: "Company website",
  press_release: "Press release",
  earnings: "Earnings report",
  interview: "Interview",
  customer_research: "Customer research",
  competitor: "Competitor source",
  other: "Other",
};

const SCREEN_LABELS = {
  foundation: "Strategic foundation",
  diagnosis: "Diagnosis",
  choices: "Narrative choices",
  map: "Narrative Map",
};

function inferCompany(source) {
  if (source.id.startsWith("src_webflow")) return "Webflow";
  if (source.id.startsWith("src_squarespace")) return "Squarespace";
  // Live-flow sources always use the "src_live_" id prefix (pipeline_runner.py) — a
  // prefix Wix/HPS never use — so this branch can never fire for the seeded cases and
  // their existing grouping below (including HPS's sources, which all fall through to
  // "Wix" today) is untouched.
  if (source.id.startsWith("src_live_")) return source.publisher || "This company";
  return "Wix";
}

// Live-only: rejected_records/dropped_links/statement_type_violations only ever exist in
// diagnostics for the live "Analyze a company" flow (see backend/pipeline_runner.py) —
// Wix/HPS have no such diagnostics object at all, so getLastDiagnostics() and this whole
// panel are only ever consulted behind the caseId === "live" gate below. The exact key
// set present varies by which action last touched the job (a full analyze vs. a
// regenerate vs. a manual retry persist different subsets — see jobs.py), so every field
// is read with a defensive fallback, never assumed present.
function buildDataQualityPanel() {
  const diagnostics = getLastDiagnostics();
  if (!diagnostics) return "";
  const rejected = diagnostics.rejected_records || [];
  const dropped = diagnostics.dropped_links || [];
  const downgrades = diagnostics.statement_type_violations || [];
  if (!rejected.length && !dropped.length && !downgrades.length) return "";

  const rejectedItems = rejected.map((r) => {
    const label = r.id ? `${escapeHtml(r.stage || "")} (${escapeHtml(r.id)})` : escapeHtml(r.stage || "");
    return `<li><strong>${label}:</strong> ${escapeHtml((r.reasons || []).join("; "))}</li>`;
  }).join("");
  const droppedItems = dropped.map((d) => {
    const where = d.evidenceId ? `evidence ${escapeHtml(d.evidenceId)}` : `record ${escapeHtml(d.recordId || "")}`;
    return `<li><strong>${escapeHtml(d.stage || "")}</strong> (${where}): ${escapeHtml(d.reason || "")}</li>`;
  }).join("");
  const downgradeItems = downgrades.map((v) => `<li>${escapeHtml(v)}</li>`).join("");

  return `
    <section class="card notice-card" data-role="data-quality-panel">
      <details>
        <summary>Data quality notes <span class="needs-review-badge" title="Records StoryMap rejected, dropped, or downgraded rather than presenting with false confidence">${rejected.length + dropped.length + downgrades.length}</span></summary>
        <p class="muted small">StoryMap rejects or downgrades anything it can't fully verify or classify with confidence, rather than presenting it as more certain than it is.</p>
        ${rejected.length ? `<h4>Rejected records</h4><ul class="numbered-list">${rejectedItems}</ul>` : ""}
        ${dropped.length ? `<h4>Dropped evidence links</h4><ul class="numbered-list">${droppedItems}</ul>` : ""}
        ${downgrades.length ? `<h4>Classification downgrades</h4><ul class="numbered-list">${downgradeItems}</ul>` : ""}
      </details>
    </section>
  `;
}

export async function renderEvidenceRoom(container, { service, state, onNavigate }) {
  container.innerHTML = `<div class="loading">Opening the evidence room…</div>`;
  const [index, foundation, diagnosis, candidates, map] = await Promise.all([
    service.getEvidenceIndex(),
    service.getStrategicFoundation(),
    service.getDiagnosis(),
    service.getCandidates(),
    service.getNarrativeMap(),
  ]);
  const bundles = index.allSourcesWithEvidence().map((b) => ({ ...b, company: inferCompany(b.source) }));
  const supportsInfo = buildSupportsInfoMap(foundation, diagnosis, candidates, map);

  const sourceTypes = [...new Set(bundles.map((b) => b.source.sourceType))];
  const companies = [...new Set(bundles.map((b) => b.company))];
  // Only the live flow ever has this data at all — see buildDataQualityPanel's own
  // internal empty-check too, so this is a double guard, not a single point of failure.
  const dataQualityPanel = state?.caseId === "live" ? buildDataQualityPanel() : "";

  container.innerHTML = `
    <section class="screen-header">
      <div class="eyebrow">Evidence room</div>
      <h1>Every source behind this analysis</h1>
      <p class="lead">The prototype separates sourced facts from StoryMap's interpretation. Every material statement on every screen traces back to one of these sources.</p>
    </section>
    ${dataQualityPanel}
    <div class="card evidence-filters">
      <label>Source type
        <select data-filter="sourceType">
          <option value="">All types</option>
          ${sourceTypes.map((t) => `<option value="${escapeHtml(t)}">${escapeHtml(SOURCE_TYPE_LABELS[t] || t)}</option>`).join("")}
        </select>
      </label>
      <label>Company
        <select data-filter="company">
          <option value="">All companies</option>
          ${companies.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("")}
        </select>
      </label>
      <label>Supports screen
        <select data-filter="screen">
          <option value="">Any screen</option>
          ${Object.entries(SCREEN_LABELS).map(([id, label]) => `<option value="${escapeHtml(id)}">${escapeHtml(label)}</option>`).join("")}
        </select>
      </label>
    </div>
    <div class="evidence-room-list" data-role="evidence-room-list"></div>
    <p class="muted small" data-role="empty-note" style="display:none">No sources match these filters.</p>
    <div class="screen-footer">
      <p class="muted small">You've reached the end of the guided workflow. Use the steps above to revisit any screen, or restart the demo.</p>
    </div>
  `;

  const list = container.querySelector('[data-role="evidence-room-list"]');
  const emptyNote = container.querySelector('[data-role="empty-note"]');
  const filters = { sourceType: "", company: "", screen: "" };

  function applyFilters() {
    list.innerHTML = "";
    let shown = 0;
    bundles.forEach(({ source, evidence, company }) => {
      if (filters.sourceType && source.sourceType !== filters.sourceType) return;
      if (filters.company && company !== filters.company) return;
      const visibleEvidence = filters.screen
        ? evidence.filter((ev) => ev.supportsIds.some((id) => supportsInfo.get(id)?.screen === filters.screen))
        : evidence;
      if (!visibleEvidence.length) return;
      shown++;
      list.appendChild(renderSourceBlock(source, visibleEvidence, supportsInfo, onNavigate));
    });
    emptyNote.style.display = shown ? "none" : "block";
  }

  container.querySelectorAll("[data-filter]").forEach((select) => {
    select.addEventListener("change", () => {
      filters[select.dataset.filter] = select.value;
      applyFilters();
    });
  });

  applyFilters();
}

function buildSupportsInfoMap(foundation, diagnosis, candidates, map) {
  const info = new Map();
  foundation.forEach((c) => info.set(c.id, { screen: "foundation", title: c.statement }));
  diagnosis.forEach((f) => info.set(f.id, { screen: "diagnosis", title: f.title }));
  candidates.forEach((c) => info.set(c.id, { screen: "choices", title: c.name }));
  // map is null in the live flow's zero-candidate-passed state (see Recommendation.js's
  // matching guard) — never null for the seeded cases.
  (map?.coreClaims || []).forEach((claim) => info.set(claim.id, { screen: "map", title: claim.statement }));
  return info;
}

function renderSourceBlock(source, evidenceItems, supportsInfo, onNavigate) {
  const el = document.createElement("div");
  el.className = "card source-block";
  const count = evidenceItems.length;
  el.innerHTML = `
    <div class="source-block-header">
      <div>
        <div class="meta-line">${escapeHtml(source.publisher || "")} · ${escapeHtml(source.publishedAt || "Undated")} · ${escapeHtml(SOURCE_TYPE_LABELS[source.sourceType] || source.sourceType)} · ${count} piece${count === 1 ? "" : "s"} of evidence</div>
        <h3>${escapeHtml(source.title)}</h3>
      </div>
      ${source.url ? `<a class="source-link" href="${escapeHtml(source.url)}" target="_blank" rel="noopener">Open official source ↗</a>` : ""}
    </div>
    <details class="source-evidence-toggle">
      <summary>Show evidence details</summary>
      <div class="source-evidence-list"></div>
    </details>
  `;
  const evList = el.querySelector(".source-evidence-list");
  evidenceItems.forEach((ev) => evList.appendChild(renderEvidenceRow(ev, supportsInfo, onNavigate)));
  return el;
}

function renderEvidenceRow(ev, supportsInfo, onNavigate) {
  const strength = strengthLabel(ev.strength);
  const freshness = freshnessLabel(ev.freshness);
  const row = document.createElement("div");
  row.className = "evidence-row";
  row.innerHTML = `
    <div class="chip-row">
      <span class="${strength.className}">${strength.label}</span>
      <span class="${freshness.className}">${freshness.label}</span>
      <span class="chip">Extraction confidence ${confidencePercent(ev.confidence)}</span>
    </div>
    <blockquote>&ldquo;${escapeHtml(ev.excerpt)}&rdquo;</blockquote>
    <p class="muted"><strong>StoryMap paraphrase:</strong> ${escapeHtml(ev.paraphrase)}</p>
    <div class="supports-groups" data-role="supports-groups"></div>
  `;
  const groupsEl = row.querySelector('[data-role="supports-groups"]');
  const byScreen = groupBy(ev.supportsIds.map((id) => supportsInfo.get(id)).filter(Boolean), (x) => x.screen);
  Object.entries(SCREEN_LABELS).forEach(([screenId, screenLabel]) => {
    const items = byScreen.get(screenId);
    if (!items || !items.length) return;
    const group = document.createElement("div");
    group.className = "supports-group";
    group.innerHTML = `<span class="supports-group-label">${escapeHtml(screenLabel)}</span>`;
    items.forEach((item) => {
      const link = document.createElement("button");
      link.type = "button";
      link.className = "text-link";
      link.textContent = item.title;
      link.addEventListener("click", () => onNavigate(screenId));
      group.appendChild(link);
    });
    groupsEl.appendChild(group);
  });
  if (!ev.supportsIds.length) {
    groupsEl.remove();
  }
  return row;
}

function groupBy(items, keyFn) {
  const map = new Map();
  items.forEach((item) => {
    const key = keyFn(item);
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(item);
  });
  return map;
}
