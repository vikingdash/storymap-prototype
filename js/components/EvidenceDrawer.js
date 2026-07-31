// Slide-in evidence detail panel. Every call site passes an EvidenceLink (or several), not a bare
// evidence id — the drawer's whole job is to show not just what a source says, but the specific
// classification (direct / partial / context / conflicting support) and rationale for why it
// does or doesn't prove the exact statement it's attached to. drawer.openEvidenceLink(link, title)
// shows one; drawer.openEvidenceLinks(links, title) shows several stacked in one panel, which is
// how a single "View N sources" link (instead of one link per evidence item) still gives access
// to everything behind a claim. This is how "evidence is one click away" (design principle, pack
// section 10) is met without leaving the current screen.
import { strengthLabel, freshnessLabel, relevanceLabel, confidencePercent, escapeHtml } from "../labels.js";

// Four separate dimensions, shown as four separate labeled rows — never juxtaposed as bare
// chips. "Support for this statement" (relevance) and "Source quality" (strength) answer
// different questions: a source can be high quality and still not support this exact claim
// (context/conflicting), or be a weak source that's nonetheless the only direct statement of an
// assumption. Collapsing them into one unlabeled row of chips reads as contradictory even when
// each number is individually correct.
//
// SOURCE_QUALITY_TEXT holds short text just for this row — strengthLabel()'s own text ("Strong
// evidence") is written for standalone display elsewhere (EvidenceRoom.js) and would read
// redundantly next to an explicit "Source quality:" prefix.
const SOURCE_QUALITY_TEXT = { strong: "Strong", moderate: "Moderate", weak: "Weak", unsupported: "Unsupported" };

function dimensionRow(label, valueLabel, className) {
  return `<div class="dimension-row"><span class="dimension-label">${escapeHtml(label)}</span><span class="${className}">${escapeHtml(valueLabel)}</span></div>`;
}

// getService is a function, not a fixed instance: the drawer is a singleton mounted once at
// startup, but which case is active can change (case selector, or navigating back to intro and
// picking the other case), so every open call must resolve the *current* case's service rather
// than one captured at mount time.
export function mountEvidenceDrawer(root, getService) {
  const drawer = document.createElement("div");
  drawer.className = "drawer";
  drawer.innerHTML = `
    <button class="drawer-close" aria-label="Close">&times;</button>
    <div class="drawer-eyebrow">Evidence detail</div>
    <div class="drawer-body"></div>
  `;
  root.appendChild(drawer);

  const body = drawer.querySelector(".drawer-body");
  const close = () => drawer.classList.remove("open");
  drawer.querySelector(".drawer-close").addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") close();
  });
  drawer.addEventListener("click", (e) => {
    if (e.target === drawer) close();
  });

  function renderEvidenceCard(link, evidence, source) {
    const relevance = relevanceLabel(link.relevance);
    const strength = strengthLabel(evidence.strength);
    const freshness = freshnessLabel(evidence.freshness);
    return `
      <div class="evidence-card">
        <span class="${relevance.className} relevance-badge">Support for this statement: ${relevance.label}</span>
        ${link.relevance === "company_position" ? `<p class="muted small">The company makes this claim. Independent evidence is still needed to confirm it.</p>` : ""}
        <blockquote>&ldquo;${escapeHtml(evidence.excerpt)}&rdquo;</blockquote>
        <p class="muted"><strong>StoryMap interpretation:</strong> ${escapeHtml(evidence.paraphrase)}</p>
        <p class="rationale-line"><strong>How this supports the statement:</strong> ${escapeHtml(link.rationale)}</p>
        <div class="dimension-list">
          ${dimensionRow("Source quality", SOURCE_QUALITY_TEXT[evidence.strength] || evidence.strength, strength.className)}
          ${dimensionRow("Source freshness", freshness.label, freshness.className)}
          ${dimensionRow("Extraction confidence", confidencePercent(evidence.confidence), "chip")}
        </div>
        ${evidence.scope ? `<p class="muted small"><strong>Scope:</strong> ${escapeHtml(evidence.scope)}</p>` : ""}
        <p class="source-line">
          <span>${escapeHtml(source?.publisher || "Unknown publisher")}</span> ·
          <span>${escapeHtml(source?.publishedAt || "Undated")}</span>
        </p>
        ${source?.url ? `<a class="source-link" href="${escapeHtml(source.url)}" target="_blank" rel="noopener">Open official source ↗</a>` : ""}
      </div>
    `;
  }

  async function resolveLink(link) {
    const index = await getService().getEvidenceIndex();
    const found = index.getEvidenceWithSource(link.evidenceId);
    return found ? { link, evidence: found.evidence, source: found.source } : null;
  }

  // Every open call is async (it awaits the service). If a user clicks two different chips in
  // quick succession, the first click's fetch could in principle still be in flight when it
  // finishes and would otherwise overwrite whatever the second click already rendered. This
  // token guard makes only the most recently *initiated* call allowed to paint — a superseded
  // call detects it lost the race and does nothing, so the drawer can never show evidence for a
  // claim other than the one most recently clicked.
  let requestToken = 0;

  async function openEvidenceLink(link, title) {
    const myToken = ++requestToken;
    const resolved = await resolveLink(link);
    if (myToken !== requestToken || !resolved) return;
    body.innerHTML = `
      <h2>${escapeHtml(title || resolved.source?.title || "Evidence")}</h2>
      ${renderEvidenceCard(resolved.link, resolved.evidence, resolved.source)}
    `;
    drawer.classList.add("open");
  }

  async function openEvidenceLinks(links, title) {
    const myToken = ++requestToken;
    const resolved = (await Promise.all(links.map(resolveLink))).filter(Boolean);
    if (myToken !== requestToken) return;
    body.innerHTML = `
      <h2>${escapeHtml(title || "Sources")}</h2>
      ${resolved.map(({ link, evidence, source }) => renderEvidenceCard(link, evidence, source)).join('<div class="drawer-divider"></div>')}
    `;
    drawer.classList.add("open");
  }

  return { openEvidenceLink, openEvidenceLinks, close };
}
