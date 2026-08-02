# Competitive comparison template (Level 2)

The point of this test is not to find a weak prompt and beat it. A strawman comparison tells us
nothing. The prompt below is deliberately strong — it asks for structure, evidence, and honesty
about maturity, because a sophisticated user's *first move* if StoryMap didn't exist would be a
sophisticated prompt, not a lazy one. If StoryMap can't beat this, it can't beat what a
competent professional will actually do.

## The standardized prompt

Use this exact prompt, unedited, against a frontier general-purpose assistant (Claude or
ChatGPT, whichever the target user population actually uses day to day — record which). Fill in
only the three bracketed fields. Do not add follow-up instructions, do not iterate on the
output, do not regenerate — one shot, exactly like a real user's first attempt.

```
I need to develop a corporate narrative for [COMPANY NAME]. Here is what I know publicly about
them:

[PASTE: the same public source material StoryMap was given for this case — company website
copy, press releases, any competitor pages used. Use the exact same source set, no more and no
less, so the comparison is fair.]

Please help me write a one-to-two-page corporate narrative that:
1. Describes where the company stands today, based only on what's demonstrably true right now.
2. Explains what's changing about the company — new investments, acquisitions, products, or
   market shifts — and how far along that change actually is.
3. Describes where the company is heading and why that direction makes sense, without
   overstating anything as already accomplished.
4. Explains why this direction is credible given the company's actual capabilities and the
   market it's in.
5. Identifies what still needs to be decided by company leadership, and what evidence is still
   missing.
6. Is honest throughout about the difference between what's proven, what's in progress, and
   what's aspirational — please don't state anything as fact that isn't actually established by
   the sources above.

Cite which part of the source material supports each major claim you make.
```

This prompt is intentionally close to what StoryMap's own output structure asks for — that's
the point. If the general assistant, given a comparably explicit set of instructions, produces
comparable rigor, that's a real finding, not a flaw in the test design.

## Blind labeling protocol

1. Generate the general-AI output first, before looking at StoryMap's Narrative Map for this
   case (avoids anchoring the evaluator).
2. Strip any model/product-identifying text from both outputs (no "As an AI..." disclaimers, no
   StoryMap screen chrome — paste both as plain narrative text).
3. Label them **Output A** and **Output B**, randomizing which is which per case (use a coin
   flip or `A`/`B` decided before either output is generated). Record the true mapping
   separately, sealed until scoring is complete.
4. Score both outputs against the same 11 dimensions and the same rubric in
   `scoring-rubric.md`, blind, before revealing which is which.
5. Reveal the mapping only after scoring is locked in.

## Side-by-side comparison sheet

Fill in once per case. Duplicate this table for each of the 3 test cases.

**Case:** _______________  **Date:** _______________  **General-AI system used:** _______________
**Evaluator:** _______________ **Mapping revealed after scoring:** [ ] yes

| Dimension | Output A score (1–5) | Output B score (1–5) | Notes / specific evidence |
|---|---|---|---|
| 1. Company altitude | | | |
| 2. Stage identification | | | |
| 3. Current state | | | |
| 4. Transition | | | |
| 5. Future direction | | | |
| 6. Market context | | | |
| 7. Evidence discipline | | | |
| 8. Temporal honesty | | | |
| 9. Differentiation | | | |
| 10. Leadership decisions | | | |
| 11. Quality of final narrative | | | |
| **Weighted average** | | | |

## Differentiation-in-kind assessment

Score alone is not the finding — the finding is *what kind* of difference exists, if any. After
scoring, answer these directly:

1. **Where did the general-AI output fail, structurally, that StoryMap's process made
   impossible?** (e.g., did it invent a statistic; did it phrase an in-progress acquisition as
   already delivering results; did it cite a competitor's claim as proof about the company being
   analyzed.) List concretely — this is the evidence for the "moat," if one exists.
2. **Where did the general-AI output match or beat StoryMap?** List concretely, without
   softening. If nothing is listed here, be suspicious of the evaluation, not the finding.
3. **If you gave both outputs to a communications professional with no context, could they tell
   which one came from a purpose-built tool and which came from a general chat prompt — and
   would they be able to say *why*, specifically?** This question is a rehearsal for the Level 3
   interview; answer it as the evaluator first so Level 3 has a baseline to compare against.

## What this level is not

Not a test of writing quality, tone, or polish — a general assistant will often *write better
prose*. This level tests whether StoryMap enforces discipline (temporal honesty, evidence
grounding, company altitude) that a well-crafted prompt, run once, does not reliably enforce on
its own. A finding of "the general AI wrote more fluently but stated a claim as fact that wasn't
established" is a StoryMap win on the dimension that matters, even if it reads as a StoryMap loss
on style.
