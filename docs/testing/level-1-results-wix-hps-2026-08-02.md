# Level 1 results — Wix & HPS — 2026-08-02

Completed using `results-summary-template.md`'s structure. This cycle covers two passes: an
initial run that found three material defects, and a fix-verification rerun after two of the
three were corrected. Reported exactly as observed — no score was adjusted without a
corresponding, itemized change.

## Cycle metadata

- **Cycle dates:** 2026-08-02 (initial run and fix-verification rerun, same day)
- **Levels run this cycle:** Level 1 only
- **Cases run this cycle:** Wix, HPS. Case 3 not run — requires a paid live call, explicitly held
  back per instruction.
- **Evaluators:** Claude (internal evaluator), executed against the live local app per
  `test-script.md`, all 7 screens, both cases, using `get_page_text` extraction plus targeted
  screenshots for visual sanity-checking.
- **Paid model calls made this cycle:** none. Both cases are pre-seeded (`WIX_DATASET`,
  `HPS_DATASET`) — no live pipeline run required.

## Level 1 — Initial run results

| Case | Weighted score | Blocker | Major | Minor | Cosmetic | Case-level pass? |
|---|---|---|---|---|---|---|
| Wix | 4.36 | 0 | 1 | 1 | 0 | No — Major on Dimension 8 |
| HPS | 4.82 | 0 | 2 | 1 | 0 | No — Major on Dimension 8 (×2 findings) |

**Per-dimension scores, initial run:**

| Dimension | Wix | HPS | Notes on Blocker/Major |
|---|---|---|---|
| 1. Company altitude | 5 | 5 | |
| 2. Stage identification | 5 | 5 | HPS: `sc_hps_strategic_pillars` vs `sc_hps_way_to_win`, same `type`, different (correct) stage — strongest evidence in the product against the type→stage shortcut |
| 3. Current state | 5 | 5 | |
| 4. Transition | 4 | 5 | Wix docked for D-001 (see below) |
| 5. Future direction | 4 | 5 | Wix docked for D-001 |
| 6. Market context | 5 | 5 | Audited every competitor-sourced link in the Evidence Room for both cases; none used as proof of a company-specific fact |
| 7. Evidence discipline | 5 | 5 | |
| 8. Temporal honesty | 3 | 4 | **D-001 (Wix, Major)**; **D-002 (HPS, Major)** |
| 9. Differentiation | 4 | 5 | |
| 10. Leadership decisions | 4 | 4 | **D-003 (both cases, Major, systemic)** |
| 11. Narrative quality | 4 | 5 | Wix docked for D-001; HPS's Narrative Map was the single strongest result of the cycle |

**Zero Blockers found in either case.** No fabricated evidence, no unproven claim shown with
false confidence, no competitor evidence misused as company proof, no aspiration presented as
decided.

### Defects found, initial run

| ID | Case | Dim | Category | Severity | Description |
|---|---|---|---|---|---|
| D-001 | Wix | 8 | Temporal misstatement | Major | Recommended narrative's `Role` field ("Wix combines... in one creation environment") overstated platform unification relative to its own `in_build` classification (`sc_way_to_win`) |
| D-002 | HPS | 8 | Temporal misstatement | Major (borderline — self-correcting, non-recommended) | Non-recommended candidate "One system, engineered end to end" overstated unification in its own headline, immediately self-flagged by its own Narrative Critic findings one section down; never reaches the shipped Narrative Map |
| D-003 | Wix + HPS (systemic) | 10 (primary), 8 (secondary) | UX/clarity | Major | Review strip flagged items by raw `confidence < 0.5` regardless of `narrativeStage`, sweeping a `strategic_direction` item with moderate directional credibility into the same bucket as genuine open leadership decisions, in both cases, same root cause |
| D-004 | Wix + HPS (systemic) | 2, 11 | UX/clarity — previously disclosed, not new | Minor | `NarrativeCoreClaim.narrativeStage` exists in data but isn't rendered anywhere in `NarrativeMapView.js` |

**Moat-relevant positive finding (initial run):** the HPS candidate set directly demonstrated
StoryMap's structural self-correction — "One system, engineered end to end" is exactly the
plausible, impressive-sounding overclaim a strong one-shot prompt is likely to produce, and
StoryMap's own critique step caught it, explained why in writing, and did not let it win the
recommendation.

**Level 1 gate decision (initial run): fail — do not proceed to Level 2.** Both cases carried a
Major defect on Dimension 8.

## Fixes applied between runs

- **D-001 fixed.** `Role` field reworded from settled-present-tense ("combines... in one
  creation environment") to `in_build`-appropriate wording ("is assembling... into one creation
  environment"), in both places it appears (`cand_creation_without_compromise.sevenParts.role`
  and `narrativeMap.sevenParts.role`). Recommendation, evidence, `narrativeStage`, and the
  `Direction` field left untouched.
- **D-003 fixed.** `StrategicFoundation.js`'s `buildReviewList` no longer uses one flat
  confidence threshold for every stage: `proven_today`/`emerging`/`in_build` still judged by
  confidence (unchanged); `strategic_direction` now judged by `directionalCredibility < 0.4`
  instead; `aspiration_pending_leadership` surfaced unconditionally (new `approval` tag), never
  gated by a number.
- **D-002 deliberately not touched**, per instruction — it's the lowest-risk of the three
  (self-correcting, confined to a non-recommended alternative) and was explicitly held back for
  a later cycle.
- Regression tests added: `js/tests/defect-regression.d001-temporal-wording.test.js` (5 tests),
  `js/tests/defect-regression.d003-stage-aware-review.test.js` (8 tests) — the latter includes
  two tests run directly against the real seed data confirming `sc_assumption_1` and
  `sc_hps_assumption` no longer appear in either case's live review strip.

## Level 1 — Fix-verification rerun results

| Case | Weighted score | Blocker | Major | Minor | Cosmetic | Case-level pass? |
|---|---|---|---|---|---|---|
| Wix | **4.95** | 0 | **0** | 1 (D-004) | 0 | **Yes** |
| HPS | **4.86** | 0 | **1** (D-002, known, deferred) | 1 (D-004) | 0 | No — solely due to D-002, deferred by instruction |

**Per-dimension scores, rerun (changed cells only; all others unchanged from the initial run):**

| Dimension | Wix before → after | HPS before → after |
|---|---|---|
| 4. Transition | 4 → 5 | 5 (unchanged) |
| 5. Future direction | 4 → 5 | 5 (unchanged) |
| 8. Temporal honesty | 3 → 5 | 4 (unchanged — D-002 untouched by design) |
| 10. Leadership decisions | 4 → 5 | 4 → 5 |
| 11. Narrative quality | 4 → 5 | 5 (unchanged) |

Verified live in the browser, not just via unit tests: Wix's Narrative Map now reads "is
assembling... into one creation environment"; both cases' review strips dropped from 4 flagged
items to 3, with the "All N items" overflow link gone entirely.

**Level 1 gate decision (rerun): Wix passes cleanly. HPS's only remaining gate failure is the
known, deliberately-deferred D-002** — not a new or missed issue. Per your instruction, proceeding
to Level 2 with D-002 still open.

## Overall defect roll-up, this cycle

| Severity | Count (initial) | Count (after fixes) | Still open |
|---|---|---|---|
| Blocker | 0 | 0 | 0 |
| Major | 3 (D-001, D-002, D-003) | 1 (D-002) | D-002 only |
| Minor | 1 (D-004) | 1 (D-004) | D-004 (not material, not blocking) |
| Cosmetic | 0 | 0 | 0 |

No pattern escalations.

## Recommendation

- [x] Fix specific material failures (D-001, D-003 — both fixed and regression-tested this
      cycle), then re-run the affected level — **done**.
- [ ] D-002 remains open by explicit instruction; revisit in a future cycle, not blocking Level 2.

**One-paragraph summary:** Level 1 found zero fabrication, zero misuse of competitor evidence,
and one genuinely strong positive signal — StoryMap's own critique step rejecting an attractive
but overstated HPS candidate before it could reach a recommendation. It also found and fixed two
real, user-facing defects (an overstated sentence in Wix's shipped narrative; a review-strip
mechanism that conflated "not yet proven" with "needs review" in both cases). One known, lower-risk
defect (D-002) remains open by design. Both cases are now cleared, with that one caveat, to proceed
to Level 2 competitive testing.
