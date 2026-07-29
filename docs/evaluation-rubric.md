# Evaluation rubric

Use this alongside the user test script in the execution pack (section 14).

## Acceptance criteria (execution pack section 13)

- [ ] A person unfamiliar with StoryMap understands the product within 60 seconds (intro screen).
- [ ] A person unfamiliar with Wix understands why Wix is being analyzed (intro screen).
- [ ] The user can complete the full workflow without explanation.
- [ ] Every material factual statement has a visible source (evidence chips + drawer + Evidence Room).
- [ ] Source facts are clearly separated from StoryMap analysis (statement-type badges throughout).
- [ ] The three narrative choices are strategically distinct (different roles, not different wording).
- [ ] The recommendation explains why it wins and what trade-offs it creates.
- [ ] The user can inspect evidence behind findings and claims (click any source chip).
- [ ] The product identifies unresolved leadership decisions (foundation screen + recommendation + map).
- [ ] No invented metrics appear (every number in `js/cases/wix-case-data.js` and
      `js/cases/hps-case-data.js` traces to a real public source).
- [ ] The case selector correctly isolates state — approving/editing in one case never affects the other.
- [ ] The app works on desktop and mobile (responsive breakpoint at 900px).
- [ ] The app runs locally with one command (`python3 serve.py 4173`, see repo root README).
- [ ] No console errors (verified in Chrome DevTools during build — see session notes).
- [ ] The code is structured for replacement of seeded analysis with live agents later
      (`analysis-service.js` interface + `docs/agent-contracts.md`).

## Scoring during a user test

For each of the 12 questions in the execution pack's test script, capture a 1-5 rating plus a
verbatim quote. Weight "did the recommendation feel credible" and "could you tell sources from
analysis" most heavily — those two map directly to reliability rules 1 and 2.
