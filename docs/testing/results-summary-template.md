# Results summary template

Complete one of these per testing cycle (a cycle = one full pass through whichever levels were
run). Do not average across cycles — each cycle's summary stands on its own; trends across
cycles belong in a separate changelog, not in this template.

## Cycle metadata

- **Cycle dates:** _______________
- **Levels run this cycle:** [ ] L1 [ ] L2 [ ] L3
- **Cases run this cycle:** [ ] Wix [ ] HPS [ ] Case 3 — if Case 3, record the selected company
  and which selection criteria it met (from `test-cases.md`): _______________
- **Evaluators / moderators involved:** _______________
- **Paid model calls made this cycle:** [ ] none [ ] yes — count + approx. cost: _______________

## Level 1 — Internal case testing results

| Case | Weighted score | Blocker count | Major count | Minor count | Cosmetic count | Case-level pass? |
|---|---|---|---|---|---|---|
| Wix | | | | | | [ ] |
| HPS | | | | | | [ ] |
| Case 3 | | | | | | [ ] |

**Per-dimension scores (all 3 cases):**

| Dimension | Wix | HPS | Case 3 | Notes on any Blocker/Major |
|---|---|---|---|---|
| 1. Company altitude | | | | |
| 2. Stage identification | | | | |
| 3. Current state | | | | |
| 4. Transition | | | | |
| 5. Future direction | | | | |
| 6. Market context | | | | |
| 7. Evidence discipline | | | | |
| 8. Temporal honesty | | | | |
| 9. Differentiation | | | | |
| 10. Leadership decisions | | | | |
| 11. Narrative quality | | | | |

**Level 1 gate decision:** [ ] pass, proceed to Level 2  [ ] fail — do not proceed, see defect
log for what must be fixed first.

## Level 2 — Competitive testing results

| Case | StoryMap weighted | General-AI weighted | Tier-1 dims: StoryMap wins? (1,7,8) | Notes |
|---|---|---|---|---|
| Wix | | | | |
| HPS | | | | |
| Case 3 | | | | |

**Differentiation-in-kind findings (summarize from `competitive-comparison-template.md`):**
- What StoryMap's process prevented that the general-AI output did not: _______________
- Where the general-AI output matched or beat StoryMap, stated plainly: _______________

**Level 2 gate decision:** [ ] pass, proceed to Level 3  [ ] fail — do not proceed, see findings
above.

## Level 3 — Moderated user testing results

- **Participants:** _______________ (count, roles — do not include names here, see the separate
  consent log referenced in `user-observation-sheet.md`)
- **Sessions completed:** _______________

**Task completion summary (aggregate across participants):**

| Task | % completed unaided | % completed with hint | % not completed |
|---|---|---|---|
| Reach & explore Strategic Foundation | | | |
| Open evidence drawer | | | |
| Articulate a candidate preference before seeing the recommendation | | | |
| Summarize the story back after the Narrative Map | | | |

### Moat-evidence log

The single most important table in this document. One row per participant.

| Participant ID | Unprompted comparison made? | Q9 classification (a–e, from `post-test-interview.md`) | Verbatim quote |
|---|---|---|---|
| | | | |

**Q9 classification key** (from `post-test-interview.md`): (a) unprompted, specific, matches
litmus pattern; (b) unprompted but vague; (c) only produced when directly asked; (d) could not
articulate; (e) said there was no meaningful difference.

### Moat verdict

Answer directly, in writing, resisting the urge to hedge:

**Did participants consistently, in their own words, articulate a distinction resembling "it gave
me language, this helped me decide what the company should be known for"?**

[ ] Yes, consistently and largely unprompted (mostly (a) classifications)
[ ] Partially — present but often needed prompting or was vague (mix of (b)/(c))
[ ] No — participants could not articulate a real difference, or said there wasn't one (mostly (d)/(e))

**If not "Yes, consistently":** name the specific dimension(s) from `evaluation-dimensions.md`
most responsible, using both the Level 1/2 defect data and the Level 3 quotes as evidence — this
is the actionable output of the entire cycle. Per the framework's own rule, any resulting product
change is scoped to the specific material failure identified, not treated as license for a
broader redesign.

## Overall defect roll-up

Total defects this cycle, by severity, across all levels and cases:

| Severity | Count | Of which still open |
|---|---|---|
| Blocker | | |
| Major | | |
| Minor | | |
| Cosmetic | | |

Pattern escalations triggered this cycle (per `defect-classification.md`): _______________

## Recommendation

- [ ] Ship / proceed as-is
- [ ] Fix specific material failures (list defect IDs), then re-run the affected level only
- [ ] Do not proceed past this level this cycle

**One-paragraph summary for stakeholders outside the testing team:**

_______________________________________________________________________________
