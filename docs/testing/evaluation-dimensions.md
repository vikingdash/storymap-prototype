# Evaluation dimensions

Eleven dimensions, evaluated for every test case at every applicable level. Each is defined with
what it measures, what a pass looks like, what a defect looks like, and where in the product (or
output) to check it. These map directly onto the narrative-stage model already shipped in the
product (`docs/product-principles.md`, `backend/schema_constants.py`'s `NARRATIVE_STAGES`) — this
framework tests whether that model actually works in practice, not just whether it's implemented.

Use `scoring-rubric.md` for the numeric scale; this file defines what each number is a score *of*.

---

### 1. Company altitude
**Measures:** whether the recommended narrative defines the company as a whole, or has quietly
collapsed into one product, business unit, capability, or segment without that scope being the
company's genuine, evidenced reality.
**Pass:** the recommended candidate's `role`/`value` describe the company-level position; if
scope is narrow, the narrative explicitly says why the company is genuinely defined by that
narrow scope (not silently assumed).
**Defect example:** a candidate that's really "the Base44 story" or "the IES story" presented as
if it were the whole-company narrative.
**Where to check:** Narrative Choices screen (all 3 candidates, not just the winner — a narrow
candidate that lost is fine; a narrow candidate that *won* is the defect), `companyAltitudeGate`
result if visible in evidence detail.

### 2. Stage identification
**Measures:** whether `narrativeStage` classifications are actually grounded in the claim's own
content, not defaulted from its `type`.
**Pass:** spot-checking 3–4 items against their source text shows real content-based reasoning
(e.g. two items of the same `type` can land on different stages, as HPS's two `way_to_win` items
do in the seed data).
**Defect example:** every `capability` item is tagged `in_build`, every `way_to_win` item is
tagged `strategic_direction`, regardless of what each one actually says — a type→stage
shortcut, exactly what the governing framework explicitly rejected.
**Where to check:** Strategic Foundation screen, per-item badges; Evidence Room for live-flow
runs where classification isn't pre-reviewed.

### 3. Current state
**Measures:** accuracy and restraint of "proven today" claims — do they match direct evidence
only, without smuggling in aspiration.
**Pass:** every `proven_today` item is backed by direct/partial company-specific evidence; none
rest on inference dressed as fact.
**Defect example:** a `proven_today` claim whose only evidence is a company's own stated
intention, or a competitor-sourced link.
**Where to check:** Strategic Foundation, filter to `proven_today` items; Evidence drawer on each.

### 4. Transition
**Measures:** whether "what's changing" (emerging/in-build) is grounded in real, verifiable
movement or commitment (investment, acquisition, hiring, product launch), not just an
announcement or a hope.
**Pass:** every `emerging`/`in_build` item cites evidence of an actual action taken, not merely
a stated plan.
**Defect example:** "the company is transforming into X" with no cited investment, deal, launch,
or organizational change behind it.
**Where to check:** Strategic Foundation, `in_build`/`emerging` items; Narrative Map `proof`.

### 5. Future direction
**Measures:** whether the forward-looking claim is genuinely ambitious (not shrunk to the safest,
fully-provable subset) while staying honest about what isn't finished.
**Pass:** the `direction` part of the narrative describes where the company is headed in a way
that goes beyond a simple extrapolation of current metrics, grounded in the `strategic_direction`
foundation items and market context, explicitly marked as intent.
**Defect example (shrinkage):** a direction statement that's just a restatement of current-state
facts with no real forward claim — the exact failure this feature was built to fix.
**Defect example (overreach):** a direction statement phrased as already achieved.
**Where to check:** the recommended candidate's `sevenParts.direction`, `whyItWins`.

### 6. Market context
**Measures:** whether external/competitor/category evidence is used correctly — as support for
the *plausibility* of a direction, never as proof of a claim about the company itself.
**Pass:** every competitor/market-sourced evidence link on a company-specific claim is marked
`context` relevance (or excluded from confidence — see `backend/confidence.py`); the same
evidence is allowed to support `directionalCredibility` on a `strategic_direction`/`aspiration`
item.
**Defect example:** a competitor's page cited as `direct` evidence that the company being
analyzed possesses a capability.
**Where to check:** Evidence Room, filter to competitor-sourced items; cross-reference which
claims cite them and at what relevance.

### 7. Evidence discipline
**Measures:** the base reliability rules — every material claim links to real evidence, no
invented statistics, source strength/freshness honestly labeled.
**Pass:** matches `docs/product-principles.md` rules 1, 5, 9, 10 without exception.
**Defect example:** any number in the narrative that doesn't trace to a visible source; a
citation that doesn't actually say what the claim says it says.
**Where to check:** Evidence Room, spot-check every statistic in the final narrative against its
cited excerpt.

### 8. Temporal honesty
**Measures:** whether the *wording* of each claim matches its declared maturity — the literal
verb tense/phrasing test from `backend/schema_constants.NARRATIVE_STAGE_WORDING_GUIDANCE`.
**Pass:** `proven_today` = is/has/does; `emerging` = is beginning to/increasingly; `in_build` =
is building/developing/assembling; `strategic_direction` = is moving toward/aims to/positioning
to; `aspiration_pending_leadership` = could/intends to, explicitly leadership-owned.
**Defect example:** any claim whose narrativeStage is not `proven_today` but whose sentence is
phrased as a present, settled fact. This is the single most important dimension in the whole
framework — it's the literal difference between "directionally ambitious" and "dishonest."
**Where to check:** every visible claim text on every screen; do this check word-by-word, not by
skimming.

### 9. Differentiation
**Measures:** whether the recommended narrative is meaningfully distinct from (a) generic
competitor positioning and (b) what a competent general-purpose AI assistant would produce from
the same public inputs.
**Pass (internal, Level 1):** `differentiationGate`/score reflects a real, specific distinction
from the named competitors, not a category-convention claim ("operating system," "trusted
partner") that many companies could equally make.
**Pass (competitive, Level 2):** see `competitive-comparison-template.md` — StoryMap's output is
judged different-in-kind, not just different-in-wording, on this dimension.
**Where to check:** Narrative Choices `differentiation` field and competitor-contrast text;
Level 2 comparison sheet.

### 10. Leadership decisions
**Measures:** whether genuine open judgment calls are surfaced distinctly from resolved claims,
and whether `aspiration_pending_leadership` content is explicitly flagged as requiring approval
rather than presented with false confidence.
**Pass:** unresolved items are real, material, and phrased as decisions a leader must make — not
generic caveats; every `aspiration_pending_leadership` item reads as "requires leadership
approval," never with a confidence number attached.
**Defect example:** an unresolved item that's actually just restating a data gap that doesn't
matter, or a leadership-dependent claim presented with a specific confidence score.
**Where to check:** Strategic Foundation review strip, Recommendation's leadership-decisions list.

### 11. Quality of the final one- to two-page narrative
**Measures:** whether the seven-part narrative reads as ONE connected company story — current
state, what's changing, what it's becoming, why that's credible, what role it seeks, what
remains unfinished — not a mechanical stage report and not (per the product test in
`docs/testing/README.md`) "here is everything the company has already done."
**Pass:** a reader who has never seen the underlying data can restate, in their own words, the
company's direction and why it's credible after reading only the Narrative Map — the two
sentences below distinguish pass from fail directly.
- **Fail pattern:** "Here is everything the company has already done."
- **Pass pattern:** "Here is where the company stands, what is changing, where it is going, why
  that direction is credible, and what remains to be built."
**Where to check:** Narrative Map screen, read `coreNarrative` + `sevenParts` in one sitting, out
loud, as a reader would.
