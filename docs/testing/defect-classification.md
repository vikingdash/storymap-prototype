# Defect classification framework

Every defect found at any level, in any case, gets logged here — regardless of severity. A
defect that seems trivial today is data later; do not filter at the point of logging.

## The rule this framework exists to enforce

> Do not add new features or redesign screens unless a test reveals a material failure.

This file defines **material failure** precisely so that rule is enforceable rather than a
matter of taste. Only **Blocker** and **Major** defects (defined below) constitute a material
failure. **Minor** and **Cosmetic** defects are logged, tracked, and left alone unless they
accumulate into a pattern that itself rises to Major (see "Pattern escalation" below).

## Severity tiers

### Blocker
The product asserts something false, or asserts something as more certain/complete than it is,
in a way a professional user would act on to their detriment. This is almost always a
**Dimension 7 (evidence discipline)** or **Dimension 8 (temporal honesty)** failure.

*Examples:* a claim with no supporting evidence presented with high confidence; an
`aspiration_pending_leadership` item phrased as already decided; an invented statistic; a
competitor-sourced link cited as direct proof of a fact about the company being analyzed.

**Action:** stops the test level from passing its gate (see `scoring-rubric.md`). Always
material. Always justifies a fix, even mid-cycle.

### Major
The product's output is misleading or meaningfully weaker than it should be, but not to the
point a reasonable professional would be actively deceived — they'd likely catch it themselves
with a moment's scrutiny, but shouldn't have had to.

*Examples:* company altitude drift (a narrow candidate framed at whole-company scope) that a
careful reader would question; a "transition" claim resting on an announcement with no
commitment evidence; a leadership-decision item that's really a non-decision; the final narrative
reading closer to a list of accomplishments than a direction story (Dimension 11's fail pattern),
without any individual claim being false.

**Action:** material. Gates the level (see thresholds in `scoring-rubric.md`). Justifies a fix.

### Minor
A real defect, but one that doesn't change what a user believes or decides — a labeling
inconsistency, an awkward phrasing that's still technically honest, a missing-but-not-misleading
piece of context, an evidence chip that's technically correct but harder to find than it should
be.

**Action:** not material on its own. Log it. Do not fix reactively — batch these and revisit
only if `Pattern escalation` below applies, or as ordinary backlog grooming outside this testing
cycle.

### Cosmetic
Visual, copy, or polish issues with no bearing on any of the 11 dimensions — a misaligned badge,
an inconsistent capitalization, a slightly awkward line break.

**Action:** log and ignore for the purposes of this testing program entirely. Never justifies a
mid-cycle change under the "no new features/redesigns" rule.

## Pattern escalation

Three or more **Minor** defects that all map to the *same dimension* in the *same case* escalate
to a **Major** for reporting purposes, even though no single instance would qualify alone — a
pattern is itself evidence of a systemic (not incidental) problem. Note the escalation explicitly
in the results summary rather than silently upgrading the individual log entries.

## Category taxonomy

Tag every logged defect with the evaluation dimension(s) it maps to (from
`evaluation-dimensions.md`, numbered 1–11) plus one of these cross-cutting categories:

- **Fabrication** — content not traceable to any real evidence.
- **Temporal misstatement** — wording doesn't match declared/actual maturity.
- **Scope drift** — company altitude narrows without justification.
- **Evidence misuse** — market/competitor evidence used as company-fact proof, or evidence
  strength/relevance mislabeled.
- **Missing disclosure** — a real gap or open decision that isn't surfaced.
- **Narrative incoherence** — individually correct claims that don't add up to one connected
  story (Dimension 11).
- **UX/clarity** — the information is correct and honest but poorly surfaced (usually Minor).
- **Comparative** — found only via the Level 2 competitive comparison (StoryMap underperforms
  the general-AI output on a specific dimension).

## Defect log template

Copy this table into the results summary for each test session; one row per defect.

| ID | Level | Case | Dimension(s) | Category | Severity | Description | Evidence/quote | Screen/location |
|---|---|---|---|---|---|---|---|---|
| D-001 | | | | | | | | |

**ID convention:** `D-` + sequential number, never reused, even if a defect is later judged
invalid — log the invalidation as a note on the same ID rather than deleting it.

## What happens after a Blocker or Major is logged

1. Confirm it's reproducible — re-run the same step in `test-script.md` once more before
   escalating.
2. Record it in `results-summary-template.md`'s defect summary.
3. Only at this point does the "material failure" exception to the no-new-features/no-redesign
   rule apply — and only to the extent of fixing the specific defect, not as license for a
   broader change. A Blocker in one candidate's temporal honesty is not license to redesign the
   Narrative Choices screen.
