# Standardized test script

One script, used at all three levels. Levels 1 and 2 are run by an internal evaluator alone
(silent, analytical). Level 3 adds a live participant with think-aloud — those steps are marked
**[L3 only]**. Do not deviate from the step order; consistency across runs is what makes scores
comparable across cases and across evaluators.

## Before you start

- [ ] Confirm which case you're running (Case 1 Wix / Case 2 HPS / Case 3 live) and which level
      (1 / 2 / 3).
- [ ] Confirm the app is running locally (`python3 serve.py 4173`) and loads with no console
      errors.
- [ ] **[L3 only]** Confirm the participant profile matches the target user (communications or
      strategy professional — see `user-observation-sheet.md` for the intake fields). Confirm
      recording consent if a recording will be made.
- [ ] Have `scoring-rubric.md` and (for L3) `user-observation-sheet.md` open and ready to fill
      in live, not reconstructed afterward.
- [ ] **[L2 only]** Have the standardized general-AI prompt from `competitive-comparison-template.md`
      already run and its output printed/saved, blind-labeled, before the session starts.

## Step 1 — Introduction screen
**[L3]** Hand the device to the participant with only this instruction: *"This is a prototype.
Explore it however you'd naturally explore something like this. Talk through what you're
thinking as you go. There's no wrong way to do this."* Do not explain what StoryMap does.

Observe / evaluate:
- Does the participant (or evaluator, reading cold) understand within ~60 seconds what this tool
  is for and why the selected company is being analyzed?
- Note the case-selector and disclosure copy — is it read, skipped, or does it prompt a question?

## Step 2 — Strategic Foundation screen
- Read the synthesized summary and the three compact dimensions. Score **Dimension 3 (current
  state)** and **Dimension 8 (temporal honesty)** here first — this screen has the highest
  density of individually-checkable claims.
- Open at least 2 of the 7 collapsed sections (rotate which ones across runs so all 7 get covered
  over a full test cycle). For each opened item, click into the evidence drawer at least once.
- **[L3]** Note whether the participant opens sections unprompted, and what they say when they
  first see a confidence/stage badge — do they understand what it means without being told?
- Score **Dimension 2 (stage identification)**: pick 3 items, read their statement text against
  their declared `narrativeStage`, and judge independently whether you'd have classified them
  the same way.
- Score **Dimension 6 (market context)**: check whether any evidence link on a company-specific
  claim traces back to a competitor source.

## Step 3 — Diagnosis screen
- Read all findings. Score **Dimension 7 (evidence discipline)**: for every quantitative or
  specific factual claim, open its evidence and confirm the excerpt actually supports it.
- **[L3]** Note any moment the participant questions a finding or looks for its source
  unprompted — that's a strong evidence-discipline signal either way.

## Step 4 — Narrative choices screen
- Read all three candidates in full, including "View full analysis" for each.
- Score **Dimension 1 (company altitude)** and **Dimension 9 (differentiation)** across all
  three candidates, not just the recommended one.
- Note the stage-mix summary line on each card; sanity-check it against the candidate's own
  `sevenParts.direction` and `proof` text.
- **[L3]** Ask nothing yet. Note which candidate the participant instinctively prefers and why,
  in their own words, before they see which one StoryMap recommends.

## Step 5 — Recommendation screen
- Score **Dimension 5 (future direction)** and **Dimension 10 (leadership decisions)**.
- Confirm `whyItWins`, `whyCredible`, and `missingEvidence` are internally consistent — does
  `whyCredible` overstate relative to what `missingEvidence` admits is still open?
- **[L3]** Ask: *"Does this match what you would have picked?"* (only after Step 4's unprompted
  answer is already recorded).

## Step 6 — Narrative Map screen
- Read `coreNarrative` and all seven parts as one continuous piece, out loud if evaluating alone.
- Score **Dimension 11 (quality of the final narrative)** using the pass/fail pattern in
  `evaluation-dimensions.md` — literally judge whether it reads closer to "here is everything
  the company has already done" or "here is where the company stands, what's changing, where
  it's going, why that's credible, what's unfinished."
- **[L3]** Ask the participant to summarize the company's story back in their own words after
  reading this screen only. Write the summary down verbatim.

## Step 7 — Evidence Room
- Spot-check 3 additional sources beyond what earlier steps already covered.
- Confirm the "Exploratory Narrative Hypothesis" vs. "Recommendation" labeling (Case 3 only,
  live-flow) matches the actual source coverage.

## Step 8 — Wrap-up
- **[L1/L2]** Finalize all 11 dimension scores in `scoring-rubric.md`. Log every defect found
  (however small) in `defect-classification.md`'s log, even ones you don't think are material.
- **[L2]** Complete the side-by-side comparison in `competitive-comparison-template.md` while
  the run is fresh.
- **[L3]** Move immediately to `post-test-interview.md`. Do not let more than a few minutes
  pass between the participant finishing and the interview starting.

## Timing guidance
- Level 1 (evaluator alone): ~30–40 minutes per case.
- Level 2 (adds the competitive comparison): ~50–60 minutes per case.
- Level 3 (participant session + interview): budget 60 minutes total — roughly 30–35 minutes of
  product exploration, 20–25 minutes of interview. Do not rush the interview to protect
  exploration time; the interview is where the litmus quote lives or doesn't.
