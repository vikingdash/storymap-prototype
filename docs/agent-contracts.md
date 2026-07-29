# Agent contracts

The full 9-agent pipeline described in the execution pack (section 5) is implemented as nine
labeled functions in `js/analysis-service.js`, run in order over the seeded dataset:

| # | Agent | What it does today (seeded) | What it would do live |
|---|-------|------------------------------|------------------------|
| 1 | Intake Agent | Asserts every source has `sourceType`, `permissionStatus`, `retrievedAt` | Normalize freshly ingested URLs/files/transcripts into `SourceDocument` records |
| 2 | Strategy Extraction Agent | Asserts every `StrategicChoice` is classified by `type` and `statementType` | Extract customers/markets/way-to-win/capabilities from source text, distinguishing strategy from goals and aspirations |
| 3 | Evidence Agent | Pass-through (seed already classifies strength/freshness/confidence) | Extract and grade proof from source text |
| 4 | Contradiction Agent | Rejects any finding that rests on weak/unsupported evidence but is marked low significance | Diff claims against evidence and against each other; surface conflicts instead of resolving them |
| 5 | Competitor Agent | Pass-through (seed avoids "ownership" language) | Extract competitor claims and category conventions from competitor sources |
| 6 | Narrative Architect | Asserts exactly 3 candidates exist | Generate 3 structurally different candidates from the strategic foundation + diagnosis |
| 7 | Narrative Critic | Asserts every candidate has recorded critic findings | Independently stress-test each candidate without seeing the Architect's reasoning |
| 8 | Decision Agent | **Actually evaluates the 3 hard gates** (strategic accuracy, evidence support, differentiation) against the seed's own scores/evidence and throws if the seed's `status` field disagrees with what the gates compute | Score candidates and apply the same hard gates to freshly generated candidates |
| 9 | Executive Output Agent | Asserts the recommendation references a real candidate and explains every non-selected candidate | Render the structured decision into the prose shown on the Recommendation screen |

Stages 1, 2, 4, 6, 7, 8 and 9 are not purely cosmetic — they run real assertions against the
seed data on every load, for every case, so a future contributor who edits `js/cases/*.js` and
breaks a reliability rule (e.g. marks a weak-evidence finding as low significance, or recommends
two candidates at once) gets an immediate thrown error instead of a silently wrong UI. Each case
gets its own `createAnalysisService()` instance (`analysis-service.js`), so this pipeline — and
every rule it enforces — runs identically and independently per case.

## Replacing seeded stages with live agents

Each stage is a pure function `(dataset) => dataset`. To go live, replace a stage's body with a
call to a real model/tool and keep the same input/output shape — `analysis-service.js`'s public
methods (`getCaseContext`, `getStrategicFoundation`, ...) and every UI component are unaffected.
