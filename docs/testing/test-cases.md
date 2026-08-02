# Test cases

Three cases, chosen to stress three different shapes of the same underlying problem: telling a
company's story honestly across current state, transition, and future direction.

## Case 1 — Wix: company expanding beyond its original identity

**Why this case.** Wix is the hardest kind of "identity drift" story: a company with a strong,
earned category label (website builder) that is visibly investing beyond it (Harmony, Aria,
Base44) without yet having a clean, unified way to describe what it's becoming. This is the
canonical test of company altitude (does the recommended narrative stay at the whole-company
level, or quietly collapse into "the Aria/Base44 story") and of transition honesty (is the
platform expansion described as real-but-in-progress, never as already-arrived).

**Source.** Seeded case, `js/cases/wix-case-data.js`. No live run required — this case already
runs the full pipeline deterministically through `WIX_DATASET`.

**What a passing run looks like.**
- Current state: website-builder identity described in present tense, matching direct evidence
  only (`sc_customers`, `sc_capabilities`).
- Transition: Base44/Harmony combination described as in-build, not as an already-unified
  platform (see `sc_way_to_win`'s `narrativeStage: "in_build"` and the risk item it's paired
  with, `sc_risk_1`).
- Future direction: the "broader platform" claim (`sevenParts.direction` on the recommended
  candidate) reads as intent, not fact.
- Company altitude: the recommended candidate (`cand_creation_without_compromise`) is a
  whole-company positioning, not an Aria/Base44 feature pitch — check this explicitly, since
  it's the candidate that scored differentiation lowest among the three and the temptation to
  narrow scope for a sharper claim is real.

**Known trap to probe for.** `cand_ai_operating_system` is the rejected-by-comparison candidate
that oversells maturity ("operating system") relative to its evidence. A tester or evaluator
should be able to articulate *why* it's weaker without being told — that's a real signal the
temporal-honesty distinction is legible, not just internally consistent.

## Case 2 — HPS: acquisition and broader company transformation

**Why this case.** Hammond Power Solutions just closed its largest acquisition (AEG) and
disclosed a new two-business-unit structure weeks before any of this evidence was gathered. This
is the sharpest test of the narrative-stage model in the product today: the seed data's own
critic findings already flag a real defect pattern ("'engineered end to end' is stated as
already true, but IES only formally launched... no evidence yet of system-level delivery") —
i.e. this case contains a *known example of the exact failure mode the whole feature exists to
catch*, deliberately preserved in a rejected/non-recommended candidate. A correct run must
surface that distinction, not paper over it.

**Source.** Seeded case, `js/cases/hps-case-data.js`. No live run required.

**What a passing run looks like.**
- Current state: transformer leadership, described with full confidence — it's the one part of
  the story with unambiguous, direct, current evidence.
- Transition: the AEG acquisition and IES formation are described as real, completed,
  in-progress-integration (in_build) — completed corporate actions, not yet a completed customer
  experience.
- Future direction: "one system, engineered end to end" is explicitly the rejected/lower-scored
  candidate's overreach — the recommended candidate (`cand_hps_trusted_foundation`) instead
  extends trust "as it matures," correctly hedged.
- Market context: HPS's own market-forces framing (electrification, data-center growth) supports
  the *plausibility* of the transformation without being cited as proof HPS itself has
  completed it.
- Leadership decisions: whether the public identity should formally include IES is surfaced as
  an open decision, not resolved by the system.

**Known trap to probe for.** `cand_hps_one_system` reads as the most impressive-sounding
candidate on a first skim (systems-integration claim, technically ambitious) and is exactly the
one a general-purpose AI prompt is most likely to produce and *not* flag as overreaching — this
is the strongest single scenario for Level 2's differentiation test.

## Case 3 — Weak-evidence company with no clear direction story

**Why this case.** Cases 1 and 2 both give the product a real, findable transformation to
describe. This case tests the opposite failure mode: what does StoryMap do when there genuinely
isn't much to say? A product that only looks good when fed a rich, dramatic company story is not
trustworthy — it needs to be honest, and still useful, when the input is thin.

**This case is deliberately not pre-selected or fabricated.** Inventing a plausible-sounding
"weak evidence" company profile for a test whose entire purpose is testing evidence discipline
would be circular. Instead, use this selection protocol at execution time to pick a real company:

**Selection criteria (must satisfy at least 4 of 5):**
1. Small-to-mid-size, privately held or a small public company with limited analyst/press coverage.
2. Fewer than ~5 substantive news or press items in the past 24 months (i.e., a public web search
   for the company name plus terms like "strategy," "expansion," or "acquisition" returns little).
3. Homepage / "About" copy is generic and could describe several competitors interchangeably
   ("innovative solutions," "trusted partner," no specific named capability or proof point).
4. No recent (past 24 months) acquisition, funding round, executive change, or product launch
   findable in public sources.
5. No investor materials, earnings calls, or founder interviews publicly available.

**Procedure:**
1. Identify 3 candidate companies meeting the criteria above (a plausible source: a mid-size
   regional B2B services or light-manufacturing company with a dated-looking website).
2. Spend no more than 15 minutes of manual research per candidate confirming criteria 1–5 by
   eye — do not use StoryMap or any AI tool for this step, to avoid contaminating the test with
   the very tool being tested.
3. Pick the strongest match. Record the company name, URL, and which criteria it satisfied in
   the results summary (`results-summary-template.md`) before running the test — this is itself
   evidence the case selection wasn't tuned to make the product look good or bad.

**What a passing run looks like.**
- The product does **not** invent a transformation story, a "way to win," or a market-change
  narrative where the evidence doesn't support one — an empty or thin `strategicFoundation`
  section, or several items landing honestly in `aspiration_pending_leadership` /
  low-confidence bands, is a correct outcome, not a bug.
- `assess_source_coverage`'s "Exploratory Narrative Hypothesis" labeling (see
  `backend/pipeline_runner.py`) is expected to trigger — verify it does, and that the frontend
  visibly shows the demoted label rather than presenting a thin case with the same confidence
  as Wix or HPS.
- Missing evidence is stated plainly (`missingEvidence`, the review-strip's unresolved items),
  not smoothed over with generic filler language.
- If a recommendation is still produced, its `whyCredible` field should read as appropriately
  modest — this is the sharpest test of whether "directionally ambitious" ever tips into
  "directionally invented" when the evidence genuinely doesn't support ambition.

**Execution note.** Unlike Cases 1 and 2, this case has no seeded dataset — it must be run
through the live "Analyze a company" flow (`AnalyzeCompany.js` → `backend/pipeline_runner.py`),
which makes real, billed Anthropic API calls. **Do not run this case until a paid-call budget is
explicitly approved separately from this framework.** Everything else in this folder can be
prepared and even partially exercised (Cases 1–2, the competitive prompt drafting, sheet
dry-runs) without spending anything.
