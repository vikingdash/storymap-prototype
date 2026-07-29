# Product principles

Source of truth: `STORYMAP_CLAUDE_CODE_EXECUTION_PACK.md` at the repo root. This file is a quick
reference for what the prototype must never violate.

## Core product rule

When a narrative exists, StoryMap tests and strengthens it. When it does not, StoryMap builds
one from the company's strategy, market context, capabilities and proof.

## Non-negotiable reliability rules

1. Every material factual claim links to evidence.
2. Facts, inferences, recommendations and aspirations are stored separately (`StatementType`).
3. No agent validates its own output (Narrative Architect and Narrative Critic are separate
   pipeline stages; Decision Agent, not the Architect, applies the hard gates).
4. Conflicting evidence remains visible (see `df_unverified_interpretation` in the seed data —
   the Contradiction Agent stage does not reconcile it away).
5. Unsupported claims are flagged, not polished (see Narrative Map's `weakOrUnsupportedClaims`).
6. Every narrative version is immutable — `NarrativeMap.version` starts at 1 and a new version
   would be a new object, not a mutation.
7. The active narrative changes only after explicit user approval — the seed map's status is
   `"draft"`, not `"active"`.
8. No public content is automatically published — there is no publish action in this prototype.
9. No invented market data, customer data, scores or momentum — every number in either case's
   seed data (`js/cases/wix-case-data.js`, `js/cases/hps-case-data.js`) traces to a real public
   source.
10. Every score shows its component reasoning and evidence — see the score rows and evidence
    chips on each narrative candidate.
11. Missing strategy decisions become questions, not hallucinated answers — see the "unresolved"
    strategic-choice items and the Narrative Map's `unresolvedQuestions`.
12. The demo clearly discloses that Wix did not commission or approve the analysis (shown on the
    introduction screen).

## What this prototype is not

Not a media-monitoring dashboard, not a scoring engine that hides its evidence, not an
autonomous publishing tool. There is no "ownership" language anywhere in the seed data —
competitor comparisons use relative emphasis and claim overlap instead.
