// Screen 3 — Current-story diagnosis (pack section 4). Each finding is Finding + Why it
// matters + Evidence + Confidence + Significance + statement type, exactly as the pack requires.
// Seven findings read as exhaustive rather than decisive, so only the three most important show
// by default; the rest sit under a collapsed "Additional findings." Each finding shows one "View
// N supporting sources" link — not one chip per evidence item, which repeats the same publisher
// name with no indication of what each source individually proves.
import { statementTypeBadge, significanceLabel, confidencePercent, escapeHtml } from "../labels.js";

export async function renderDiagnosis(container, { service, drawer, onNavigate }) {
  container.innerHTML = `<div class="loading">Diagnosing the current story…</div>`;
  const findings = await service.getDiagnosis();

  const order = { high: 0, medium: 1, low: 2 };
  const bySignificance = (a, b) => order[a.significance] - order[b.significance];
  const primary = findings.filter((f) => f.priority === "primary").sort(bySignificance);
  const secondary = findings.filter((f) => f.priority !== "primary").sort(bySignificance);

  container.innerHTML = `
    <section class="screen-header">
      <div class="eyebrow">2 · Current-story diagnosis</div>
      <h1>Where the current story is strong — and where it breaks</h1>
      <p class="lead">Each finding is tied to evidence, labeled by significance, and marked as a source fact, synthesis or StoryMap inference. Click a source to inspect the basis.</p>
    </section>
    <div class="diagnosis-list"></div>
    <details class="additional-questions" ${secondary.length ? "" : "style=\"display:none\""}>
      <summary>Additional findings (${secondary.length})</summary>
      <div class="diagnosis-list secondary"></div>
    </details>
    <div class="screen-footer">
      <button class="primary-button" type="button" data-action="continue">Continue to narrative choices →</button>
    </div>
  `;

  const list = container.querySelector(".diagnosis-list");
  primary.forEach((finding) => list.appendChild(renderFinding(finding, drawer)));
  const secondaryList = container.querySelector(".diagnosis-list.secondary");
  secondary.forEach((finding) => secondaryList.appendChild(renderFinding(finding, drawer)));

  container.querySelector('[data-action="continue"]').addEventListener("click", () => onNavigate("choices"));
}

function renderFinding(finding, drawer) {
  const sev = significanceLabel(finding.significance);
  const badge = statementTypeBadge(finding.statementType);
  const sourceCount = finding.evidence.length;
  const el = document.createElement("div");
  el.className = "finding-card";
  el.innerHTML = `
    <div class="finding-sidebar">
      <span class="${sev.className}">${sev.label}</span>
      <span class="${badge.className}">${badge.label}</span>
      <span class="confidence-note">Confidence ${confidencePercent(finding.confidence)}</span>
    </div>
    <div class="finding-body">
      <h3>${escapeHtml(finding.title)}</h3>
      <p class="muted">${escapeHtml(finding.explanation)}</p>
      ${sourceCount ? `<button type="button" class="text-link" data-action="view-sources">View ${sourceCount} supporting source${sourceCount === 1 ? "" : "s"}</button>` : ""}
    </div>
  `;
  const viewSourcesBtn = el.querySelector('[data-action="view-sources"]');
  if (viewSourcesBtn) {
    viewSourcesBtn.addEventListener("click", () => drawer.openEvidenceLinks(finding.evidence, finding.title));
  }
  return el;
}
