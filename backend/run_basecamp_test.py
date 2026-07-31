"""One-shot CLI test of the live pipeline against a single real company (basecamp.com),
no supporting/competitor URLs, no existing narrative. Thin wrapper around
pipeline_runner.run_analysis() — the actual orchestration logic lives there now, shared
with the Flask job system (jobs.py) so this script and the real product code path can
never silently drift apart.

Run with: python3 run_basecamp_test.py
Writes the full result to the session scratchpad directory (never inside storymap-app/,
so there's no risk of fetched content or generated analysis ending up in Git).
"""
import json
import os

from dotenv import load_dotenv

load_dotenv()

from pipeline_runner import run_analysis

# Sonnet 5 introductory pricing, confirmed at platform.claude.com/docs/en/about-claude/pricing
# (in effect through 2026-08-31): $2/MTok input, $10/MTok output.
SONNET5_INPUT_PER_MTOK = 2.0
SONNET5_OUTPUT_PER_MTOK = 10.0

COMPANY_URL = "https://basecamp.com/"

OUTPUT_PATH = os.environ.get(
    "TEST_OUTPUT_PATH",
    "/private/tmp/claude-501/-Users-dash-Downloads-StoryMap-Claude-Code-Execution-Pack--1-/9867fa5e-cf8a-4965-b8b6-ceec57f8d4cf/scratchpad/basecamp_test_output.json",
)


def main():
    def progress(stage):
        print(f"=== Stage: {stage} ===")

    result = run_analysis(COMPANY_URL, [], [], "", progress_cb=progress)
    dataset = result["dataset"]
    diag = result["diagnostics"]

    totals = diag["token_totals"]
    cost = (totals["input_tokens"] / 1_000_000 * SONNET5_INPUT_PER_MTOK) + (totals["output_tokens"] / 1_000_000 * SONNET5_OUTPUT_PER_MTOK)

    report = {
        "critical_failure": diag["critical_failure"],
        "fetch_failures": diag.get("fetch_failures", []),
        "fabricated_evidence_ids_by_stage": diag["fabricated_evidence_ids_by_stage"],
        "unverified_evidence_count": diag["unverified_evidence_count"],
        "dropped_links": diag["dropped_links"],
        "statement_type_violations": diag["statement_type_violations"],
        "rejected_records": diag["rejected_records"],
        "strategic_foundation_count": len(dataset["strategicFoundation"]) if dataset else 0,
        "diagnosis_count": len(dataset["diagnosis"]) if dataset else 0,
        "candidate_count": len(dataset["candidates"]) if dataset else 0,
        "recommended_candidate_id": dataset["recommendation"]["candidateId"] if dataset and dataset["recommendation"] else None,
        "api_calls": diag["api_calls"],
        "token_totals": totals,
        "actual_cost_usd": round(cost, 4),
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump({"report": report, "dataset": dataset}, f, indent=2)

    print("\n=== SUMMARY ===")
    print(json.dumps(report, indent=2))
    print(f"\nFull result written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
