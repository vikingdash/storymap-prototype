# StoryMap prototype — Wix + Hammond Power Solutions narrative decision demos

Implements `STORYMAP_CLAUDE_CODE_EXECUTION_PACK.md` (repo root, one directory up). Ships with
two independent, self-contained demonstration cases — Wix and Hammond Power Solutions (HPS) —
selectable on the intro screen. See "Two cases" below.

## Run it

```
cd storymap-app
python3 serve.py 4173
```

Then open **http://localhost:4173/** in a browser. Stop the server with `Ctrl+C`.

`serve.py` is a thin wrapper around Python's built-in `http.server` that adds
`Cache-Control: no-store` to every response — plain `python3 -m http.server` works too, but
during active iteration a browser can silently keep serving a stale cached copy of a JS module
after you've fixed it on disk, which happened once during this build. If you don't need that
guarantee, `python3 -m http.server 4173` is a drop-in substitute.

No install step, no build step, no dependencies. Any static file server works if you'd rather
not use Python — e.g. `npx serve .` if you have Node, or double-check `index.html` opens fine
directly via `file://` (it does not, because it uses ES module imports, which browsers block
under `file://` for CORS reasons — always serve it over HTTP as shown above).

## Stack note — deviation from the execution pack

The pack recommends Next.js + TypeScript + Tailwind + Zod. This sandbox has no Node.js, npm, or
Homebrew installed and no path to install them, so that toolchain could not be used. Instead:

- **TypeScript** → JSDoc typedefs in `js/schemas.js` describe the same shapes as the pack's `.ts`
  definitions (section 6), so the data model is unchanged.
- **Zod** → hand-written runtime validators in `js/schemas.js` (`validateDataset` etc.) that
  check every seeded record on load and throw a descriptive error on any violation — same job,
  no dependency.
- **Tailwind** → plain CSS in `css/styles.css`, same visual system as the original
  `storymap_wix_real_value_demo.html` (dark theme, orange accent), extended to cover every
  screen and made responsive.
- **Next.js** → native ES modules loaded directly by the browser (`js/app.js` as
  `<script type="module">`), with the same `/components`, `/lib`(≈ root of `js/`)-style
  separation the pack asks for. No JSX; components are functions that build DOM directly.

Everything else in the pack — the data model, the 9-agent pipeline structure, the service-layer
interface, the seven-screen flow, the reliability rules — is implemented as specified. If Node
becomes available later, porting this to Next.js is mechanical: the schemas, seed data and
service interface carry over unchanged; only the rendering layer needs rewriting as React
components.

## Two cases

The intro screen opens with a case selector: **Wix public demonstration** and **Hammond Power
Solutions public demonstration**. Both run through the identical 7-screen workflow, schemas,
evidence-integrity rules (relevance classification, confidence caps, hard gates) and
`analysis-service.js` pipeline — only the seed content differs. Each case is a fully
self-contained file in `js/cases/`; nothing about one case's data can leak into or collide with
the other (see `js/state.js`'s per-case state namespacing).

The HPS case was built from primary sources only, verified during a live research session:
official HPS press releases, its 2025 Annual Report and 2025 ESG Report (both downloaded and
parsed directly with `pypdf` after exceeding the fetch tool's size limit), official AEG Power
Solutions product pages (AEG was acquired by HPS in June 2026), and one competitor page (Eaton)
kept strictly as background context, never as a source for HPS's own strategy. No customer
research, market-share figures, or third-party industry aggregates were used or invented.

## File structure

```
storymap-app/
  index.html                    entry point
  serve.py                      no-cache local dev server (see "Run it")
  css/styles.css                all styling
  js/
    schemas.js                  typed shapes + runtime validation (Zod substitute)
    case-utils.js                confidence caps, support-wiring, buildCaseDataset() — shared by every case
    cases/
      wix-case-data.js          seeded Wix dataset, built only from public sources
      hps-case-data.js          seeded Hammond Power Solutions dataset, built only from public sources
    analysis-service.js         NarrativeAnalysisService factory — the 9-agent pipeline, one instance per case
    state.js                    app state (screen, active case, per-case approvals), localStorage-backed
    labels.js / evidence.js / scoring.js   shared presentation helpers
    app.js                      router, wires everything together
    components/
      WorkflowNav.js            stepper nav + restart control
      EvidenceDrawer.js         slide-in evidence detail panel
      DemoIntro.js              screen 1 + case selector
      StrategicFoundation.js    screen 2
      Diagnosis.js              screen 3
      NarrativeChoices.js       screen 4
      Recommendation.js         screen 5
      NarrativeMapView.js       screen 6
      EvidenceRoom.js           screen 7
  docs/
    product-principles.md       the pack's 12 reliability rules, cross-referenced to the code
    agent-contracts.md          what each of the 9 agents does today vs. live
    evaluation-rubric.md        acceptance criteria + user-test scoring guide
```

To add a third case: create `js/cases/<name>-case-data.js` following the same shape as the
existing two (ending in `export const X_DATASET = buildCaseDataset({...})`), add it to
`SERVICES_BY_CASE` in `analysis-service.js`, and add its id to `state.js`'s `defaultCaseState()`
registration in `DEFAULT_STATE.cases`. No component needs to change.

## What's seeded vs. functional

**Functional (real code, not decoration):**
- The full 7-screen guided workflow, hash-routed and deep-linkable (`#foundation`, `#diagnosis`, ...).
- Approve / Edit / Reject on every strategic-foundation item, persisted to `localStorage`.
- The evidence drawer — click any source chip anywhere in the app to see the exact excerpt,
  paraphrase, strength, freshness and confidence, with a link to the real public source.
- Runtime schema validation — edit either case file and violate a reliability rule (e.g. mark a
  weak-evidence finding as low significance) and the app throws a descriptive error on load
  instead of silently rendering something wrong.
- The Decision Agent's hard gates are real checks against the seeded scores/evidence, not just
  a `status` field taken on faith (see `js/analysis-service.js`, stage 8).
- The case selector and per-case state isolation — approvals, edits and confirmations made in
  one case are never visible in or overwritten by the other.
- Restart control clears all state (both cases) and returns to the introduction.
- Responsive layout (breakpoint at 900px) for desktop and mobile.

**Seeded (would become live agent calls later):**
- Every source and excerpt in `js/cases/wix-case-data.js` and `js/cases/hps-case-data.js`. Every
  excerpt is a real fact from a real public source; nothing is invented.
- The three narrative candidates per case, their scores, and the recommendation. In production
  this is where Agents 6-9 (Narrative Architect, Critic, Decision, Executive Output) would run
  live instead of reading from a seed file.

## Known limitations from this build session

- No automated test suite yet (the pack's build order lists this as step 14; skipped in favor of
  the manual verification described below).
- No headless browser or interactive browser tool was available in this build environment, so
  the app was verified by: serving it, confirming every file returns HTTP 200 and matches disk,
  cross-checking every `import`/`export` pair across all modules, verifying every
  dynamically-referenced CSS class exists in `styles.css`, and tracing the full data graph in
  both case files with a script (every evidence reference resolves, no duplicate ids, every
  candidate passes the Decision Agent's hard gates, every non-recommended candidate has a "why
  not selected" explanation). **This was not confirmed by actually loading the page in a browser
  and clicking through it** — do that before showing this to a real tester, on both cases, and
  open the DevTools console while doing so.
- Editing a foundation item's text and then re-approving elsewhere is a simple merge in
  `localStorage`; there's no undo history beyond the browser's own back button.
- The HPS case's AEG-derived evidence relies on AEG's own marketing pages (aegps.com), which is
  appropriately weaker sourcing than HPS's own investor-relations documents — reflected in
  slightly lower confidence scores on claims that lean on AEG-only evidence.
