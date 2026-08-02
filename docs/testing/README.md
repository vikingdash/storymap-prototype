# StoryMap product-testing framework

We are moving from product development into product testing. This folder is the testing
program, not a development plan — **nothing in here authorizes a feature, a redesign, or a
new screen.** A change to the product is justified only when a test in this framework surfaces
a **material failure** (defined precisely in `defect-classification.md`). Everything else —
polish, preference, "wouldn't it be nice if" — gets logged and left alone.

## The question this framework exists to answer

StoryMap's claimed advantage over a general-purpose AI assistant is not a feature list. It is a
claim about what the product *does for the user's thinking* that a well-crafted ChatGPT/Claude
prompt does not. That claim cannot be asserted from inside the building. It has to be observed.

**The litmus test**, stated exactly as the standard we're holding ourselves to:

> If users consistently say — in their own words, unprompted — something like *"ChatGPT gave me
> language. StoryMap helped me decide what the company should be known for,"* then we have a
> real product.
>
> If they do not say that, or have to be led to it, we fix the product before we add monitoring,
> macro intelligence, or more integrations.

Every other deliverable in this folder — the rubric, the scripts, the interview guide — exists
to get an honest, unbiased reading on that one question, plus the supporting analytical
correctness the product needs to have *before* that question is even worth asking a real
professional to answer.

## Three levels, in order

Each level is a gate for the next. Do not skip ahead — running moderated user sessions against
a product that fails internal case testing burns a scarce, expensive resource (a communications
or strategy professional's time) on defects a spreadsheet would have caught for free.

### Level 1 — Internal case testing
No external participants. Run the product (or, where a live run is required, plan the run) against
the three test cases in `test-cases.md` and score every one of the 11 dimensions in
`evaluation-dimensions.md` using `scoring-rubric.md`. This is where analytical-correctness defects
get caught — a company altitude that's secretly one product line, a "current state" claim with no
real evidence behind it, a future-direction sentence phrased as already true. Cheap, fast,
repeatable, no paid model calls required for the two seeded cases (Wix, HPS); one live run
required for the third case (see `test-cases.md`, Case 3).

**Gate to Level 2:** no unresolved Blocker or Major defect (see `defect-classification.md`) on
any of the 11 dimensions, for any of the 3 cases.

### Level 2 — Competitive testing against a strong general-AI prompt
Same three cases, run through a standardized, deliberately strong general-purpose prompt (given
in full in `competitive-comparison-template.md`) against a frontier general-AI assistant, blind
side-by-side against StoryMap's output, scored on the same 11 dimensions plus a differentiation
delta. This is where we find out whether StoryMap is actually doing something a great prompt
cannot — or whether the product is a worse UI wrapped around the same underlying capability.

**Gate to Level 3:** StoryMap outperforms or is judged distinctly different-in-kind (not just
different-in-wording) on company altitude, temporal honesty, and evidence discipline — the three
dimensions a general-purpose prompt has no structural mechanism to enforce. If it does not clear
this bar, fix the product first; do not spend a professional's time confirming what the internal
comparison already showed.

### Level 3 — Moderated user testing with communications/strategy professionals
Real target users, think-aloud, moderated, observed, then interviewed. This is where the litmus
quote either shows up or it doesn't. The moderator's job is to never say the word "ChatGPT," never
say "moat," and never ask a leading question that could produce the target quote by suggestion —
see `post-test-interview.md`'s explicit non-leading protocol.

## What's in this folder

| File | Deliverable |
|---|---|
| `test-cases.md` | The 3 required test cases: Wix, HPS, and a weak-evidence/no-direction company (with a selection protocol, not a fabricated profile) |
| `evaluation-dimensions.md` | The 11 evaluation dimensions, each defined against the narrative-stage model already in the product |
| `test-script.md` | The standardized test script — one script, used at all 3 levels, with per-level branches |
| `scoring-rubric.md` | 1–5 scoring anchors per dimension, weighting, pass/fail thresholds |
| `competitive-comparison-template.md` | The standardized general-AI prompt + blind side-by-side comparison template |
| `user-observation-sheet.md` | Structured behavioral-observation sheet for moderated sessions |
| `post-test-interview.md` | Post-test interview guide, including the non-leading path to the litmus question |
| `defect-classification.md` | Severity/category taxonomy and the precise definition of "material failure" |
| `results-summary-template.md` | Roll-up template across all levels/cases, ending in a go/no-go verdict |

## Status of this session

This session produced the testing materials only. No production code was changed. No paid model
call was made — Level 1's live case (Case 3) and all of Level 2/3 require a deliberate,
separately-approved run.
