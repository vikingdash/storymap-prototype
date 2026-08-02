# Scoring rubric

Score each of the 11 dimensions from `evaluation-dimensions.md` on a 1–5 scale, using the
anchors below. Use whole numbers only — no halves; if you're between two anchors, the defect you
can point to decides which one you round to. Every score of 3 or below **must** have a
corresponding entry in the defect log (`defect-classification.md`) — a low score with no logged
defect is not a usable data point.

## General anchor meaning (applies to every dimension unless overridden below)

| Score | Meaning |
|---|---|
| 5 | No defect found. Would hold up under a skeptical expert's scrutiny. |
| 4 | Minor defect(s) only — cosmetic or edge-case, does not affect trust in the output. |
| 3 | At least one Minor-classified defect that a careful user would notice and question. |
| 2 | At least one Major-classified defect — materially undermines this dimension for this case. |
| 1 | Blocker-classified defect — this dimension has failed outright for this case. |

See `defect-classification.md` for the Blocker/Major/Minor/Cosmetic definitions those scores
refer to.

## Per-dimension overrides and specific anchors

**1. Company altitude**
- 5: recommended candidate is unambiguously whole-company scope, or narrow scope is explicitly
  justified.
- 3: scope is ambiguous — a careful reader could read it either as whole-company or as one
  product line.
- 1: recommended candidate is narrow scope presented as if it were the whole company, no
  justification given.

**2. Stage identification**
- 5: every spot-checked item's stage matches independent judgment of its content.
- 3: 1 of 3–4 spot-checked items seems misclassified but the error is defensible/borderline.
- 1: stages are visibly correlated with `type` rather than content (the type→stage shortcut).

**8. Temporal honesty** (weighted most heavily — see below)
- 5: every claim's wording matches its stage exactly, verified word-by-word.
- 3: one non-`proven_today` claim uses present-tense/settled phrasing but is a minor
  offender (e.g. a headline/name, not a substantive claim).
- 1: any substantive claim (something a leader would act on) is phrased as already-achieved
  when its own stage says otherwise.

**11. Quality of the final narrative**
- 5: unmistakably the "pass pattern" — reads as one story, a naive reader can restate direction
  + credibility + what's unfinished after one read.
- 3: informative but reads as a list of facts more than a story — the reader could restate what
  the company has done, but not clearly what it's becoming or why that's credible.
- 1: unmistakably the "fail pattern" — a catalogue of accomplishments with no forward claim, or
  a forward claim with no credibility grounding.

## Weighting

Not all 11 dimensions carry equal weight in the overall verdict. Weight tiers:

**Tier 1 (weight ×3) — the dimensions a general-purpose AI prompt has no structural mechanism to
enforce, and therefore the core of any real differentiation claim:**
- Dimension 1 — Company altitude
- Dimension 8 — Temporal honesty
- Dimension 7 — Evidence discipline

**Tier 2 (weight ×2) — core to the narrative-stage model specifically:**
- Dimension 3 — Current state
- Dimension 4 — Transition
- Dimension 5 — Future direction
- Dimension 6 — Market context
- Dimension 11 — Quality of the final narrative

**Tier 3 (weight ×1) — important, but secondary to the above:**
- Dimension 2 — Stage identification
- Dimension 9 — Differentiation
- Dimension 10 — Leadership decisions

**Weighted case score** = `(sum of Tier 1 scores × 3 + sum of Tier 2 scores × 2 + sum of Tier 3
scores × 1) / (3×3 + 5×2 + 3×1)`, giving a 1–5 weighted average per case. Report this alongside
the raw 11 individual scores — never in place of them; a good weighted average hiding one
Blocker-tier defect is itself a reporting defect.

## Pass/fail thresholds

- **Case-level pass:** weighted case score ≥ 4.0 **and** zero Blocker defects **and** zero Major
  defects on Dimension 1, 7, or 8.
- **Program-level (Level 1) pass, gating Level 2:** all 3 cases individually pass.
- **Program-level (Level 2) pass, gating Level 3:** StoryMap's weighted score on Dimensions 1, 7,
  8 exceeds the general-AI comparison's score on the same three dimensions, for at least 2 of 3
  cases (see `competitive-comparison-template.md` for how the comparison itself is scored).
- **Program-level (Level 3) verdict:** not numeric — see `results-summary-template.md`'s
  moat-verdict section. The litmus question in `post-test-interview.md` is the deciding input,
  not the dimension scores (which still matter as supporting/diagnostic evidence).
