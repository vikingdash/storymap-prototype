"""Live Anthropic-backed pipeline for the 'Analyze a company' flow.

Mirrors the stage structure in docs/agent-contracts.md (Agents 1-9), but each stage here
is a real model call instead of an assertion over seed data. Every call is forced (via
tool_choice) into a JSON shape matching js/schemas.js's types, and every cited excerpt is
verified against the actually-fetched source text (citation_verify.py) before it's
trusted anywhere downstream. Confidence is never asserted by the model — it's computed
by confidence.py from verified evidence links only, exactly like the seeded cases.

Five calls: foundation+evidence (all company/supporting sources at once), diagnosis
(including competitor overlap + competitorContrasts when competitor sources exist),
three candidates, critique (categorical gates, never numeric scores), and a final
recommendation+map+audiences call. Fewer than the pack's per-agent breakdown because
several seeded stages (Intake, Contradiction structural checks, Executive Output
formatting) are cheap Python-side checks here too — see pipeline_runner.py.
"""
import json
import os

import anthropic

from citation_verify import verify_evidence_items
from confidence import compute_confidence_from_links
from schema_constants import STATEMENT_TYPES, STRATEGIC_CHOICE_TYPES, DIAGNOSIS_STATEMENT_TYPE_ENUM, EVIDENCE_RELEVANCE_TYPES as RELEVANCE_TYPES

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_TOKENS = 8192

SYSTEM_RULES = """You are the analysis engine for StoryMap, a strategic-narrative tool. You are given
the actual fetched text of one or more public web pages about a company (and, separately,
about its competitors) and must produce strictly evidence-grounded structured output. These
rules are non-negotiable:

1. Every EvidenceItem "excerpt" must be copied VERBATIM, character-for-character, from the
   source text you were given, under the exact sourceId it came from. Do not paraphrase into
   the excerpt field and do not combine two separate sentences into one excerpt. A server-side
   check will strip any excerpt that is not a real substring of that source's text, and any
   claim that then has no remaining evidence will be marked provisional — so an invented or
   misattributed excerpt actively hurts the claim it was meant to support.
2. statementType must be one of: source_fact (directly stated by a source), storymap_inference
   (a conclusion that goes beyond what any source states outright), storymap_synthesis
   (combines multiple atomic source facts without adding interpretive judgment), recommendation,
   leadership_decision (a real decision leadership must make — no evidence model applies), or
   aspiration (the company's own stated goal, not yet proven true). source_fact requires at
   least one direct-relevance evidence link; storymap_synthesis requires at least two
   contributing evidence links — a single citation is not a synthesis.
3. EvidenceLink relevance must be one of: direct (proves this exact statement), partial (bears
   on it but doesn't fully establish it), context (related but doesn't support this specific
   claim), or conflicting (contradicts it). Do not mark evidence as "direct" just because it's
   topically related — e.g. revenue growth does not directly prove who the customers are.
4. Never invent a percentage, statistic, growth figure, or "momentum" claim that is not
   literally present in the source text.
5. Never assign a numeric customer-relevance score or any other numeric confidence/certainty
   value yourself. Where a field asks for customer relevance or differentiation, answer in a
   plain qualitative sentence, never a number or percentage.
6. Testimonials or quotes the company itself selected and published on its own site are NOT
   independent customer evidence — they are vendor-curated marketing content. Grade them "weak"
   or "moderate" strength (never "strong") and note the self-selection bias.
7. If the provided source text is insufficient to support a judgment, do not guess — express it
   as an "unresolved" strategic-choice item (statementType leadership_decision, empty evidence)
   or state plainly that evidence is missing, rather than asserting a confident claim.
8. Only use sourceId values you were explicitly given. Do not invent a source.
9. Competitor sources are for comparison only — never treat a competitor's page as evidence
   about the company being analyzed, and vice versa.
"""


def get_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in the environment")
    return anthropic.Anthropic(api_key=api_key)


def _retry_context_block(prior_failure):
    """Appended to a stage's prompt only on a retry attempt — never on the first. Per the
    retry policy: a retry must never blindly repeat the identical prompt after a
    validation failure; it must tell the model exactly what went wrong and require it to
    fix that specific problem, not just try its luck again."""
    if not prior_failure:
        return ""
    return (
        f"\n\nYour previous attempt at this exact request failed validation with this "
        f"exact reason: {prior_failure}\n"
        f"Fix that specific problem in this attempt — do not repeat the same mistake. "
        f"Regenerate the complete, corrected response.\n"
    )


class UsageTracker:
    """on_call, if given, fires immediately after every single API call is recorded —
    not just after a whole stage completes — so a caller (pipeline_runner.py) can persist
    cumulative cost to disk right away. This is what makes "usage data survives a later
    stage crash" true: even if the very next line of code raises, the tokens already
    spent on this call were durably recorded before that happened."""

    def __init__(self, on_call=None):
        self.calls = []
        self.on_call = on_call

    def record(self, label, usage):
        entry = {"label": label, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
        self.calls.append(entry)
        if self.on_call:
            self.on_call(entry, self.totals())

    def totals(self):
        return {
            "input_tokens": sum(c["input_tokens"] for c in self.calls),
            "output_tokens": sum(c["output_tokens"] for c in self.calls),
        }


def call_tool(client, usage_tracker, label, user_text, tool_name, tool_description, input_schema, max_tokens=MAX_TOKENS):
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=SYSTEM_RULES,
        messages=[{"role": "user", "content": user_text}],
        tools=[{"name": tool_name, "description": tool_description, "input_schema": input_schema}],
        tool_choice={"type": "tool", "name": tool_name},
    )
    usage_tracker.record(label, response.usage)
    tool_use = next(b for b in response.content if b.type == "tool_use")
    return tool_use.input


EVIDENCE_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "sourceId": {"type": "string"},
        "excerpt": {"type": "string", "description": "Verbatim substring of the named source's text."},
        "paraphrase": {"type": "string"},
        "evidenceType": {"type": "string"},
        "strength": {"type": "string", "enum": ["strong", "moderate", "weak", "unsupported"]},
        "freshness": {"type": "string", "enum": ["current", "aging", "stale"]},
    },
    "required": ["id", "sourceId", "excerpt", "paraphrase", "evidenceType", "strength", "freshness"],
}

EVIDENCE_LINK_SCHEMA = {
    "type": "object",
    "properties": {
        "evidenceId": {"type": "string"},
        "relevance": {"type": "string", "enum": RELEVANCE_TYPES},
        "rationale": {"type": "string"},
    },
    "required": ["evidenceId", "relevance", "rationale"],
}

SEVEN_PARTS_SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in ["context", "tension", "belief", "role", "value", "proof", "direction"]},
    "required": ["context", "tension", "belief", "role", "value", "proof", "direction"],
}


def _format_sources(sources):
    """sources: list of {id, text}. Renders each as a clearly delimited, labeled section so
    the model can't confuse which sourceId a given passage came from."""
    return "\n\n".join(f'--- SOURCE id="{s["id"]}" ---\n{s["text"]}\n--- END SOURCE id="{s["id"]}" ---' for s in sources)


def extract_foundation(client, usage_tracker, sources, prior_failure=None):
    """sources: list of {id, text} for the company + supporting URLs (never competitor URLs).
    prior_failure: the exact validation error from a previous attempt at this same call,
    if this is a retry — included in the prompt so the model fixes that specific problem
    instead of blindly repeating itself."""
    schema = {
        "type": "object",
        "properties": {
            "evidence": {"type": "array", "items": EVIDENCE_ITEM_SCHEMA},
            "strategicFoundation": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "type": {"type": "string", "enum": STRATEGIC_CHOICE_TYPES},
                        "statement": {"type": "string"},
                        "statementType": {"type": "string", "enum": STATEMENT_TYPES},
                        "evidence": {"type": "array", "items": EVIDENCE_LINK_SCHEMA},
                    },
                    "required": ["id", "type", "statement", "statementType", "evidence"],
                },
            },
        },
        "required": ["evidence", "strategicFoundation"],
    }
    source_ids = ", ".join(f'"{s["id"]}"' for s in sources)
    user_text = (
        f"Sources (verbatim, fetched from the company's own public pages):\n\n{_format_sources(sources)}\n\n"
        f"Only use these sourceId values: {source_ids}.\n\n"
        "Extract evidence items and a strategic foundation (chosen customers, chosen markets, "
        "how the company appears to intend to win, capabilities, proof, assumptions, and any "
        "unresolved questions a leader would need to answer). Cover every strategic-foundation "
        "category the source text actually supports; use type \"unresolved\" (empty evidence "
        "array, statementType leadership_decision) for anything a leader would need to decide "
        "or clarify that these pages alone cannot answer.\n\n"
        "Extract AT MOST 15 evidence items total — the strongest, most strategically relevant "
        "ones, not an exhaustive list of every sentence. Both 'evidence' and "
        "'strategicFoundation' must be present in your output; do not run out of room on "
        "evidence before writing strategicFoundation."
        + _retry_context_block(prior_failure)
    )
    return call_tool(
        client, usage_tracker, "foundation", user_text,
        "submit_foundation", "Submit extracted evidence and strategic foundation.", schema,
    )


def diagnose(client, usage_tracker, sources, foundation_summary, competitor_sources, existing_narrative, evidence_pool, prior_failure=None):
    """sources: company/supporting {id, text} list. competitor_sources: same shape, may be
    empty. existing_narrative: optional string the user supplied. prior_failure: see
    extract_foundation's matching docstring."""
    verified_evidence = _verified_evidence_for_prompt(evidence_pool)
    has_competitors = bool(competitor_sources)
    schema = {
        "type": "object",
        "properties": {
            "evidence": {"type": "array", "items": EVIDENCE_ITEM_SCHEMA, "description": "Any additional evidence items needed, beyond what's already listed."},
            "diagnosis": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "explanation": {"type": "string"},
                        "significance": {"type": "string", "enum": ["high", "medium", "low"]},
                        "statementType": {
                            "type": "string",
                            "enum": DIAGNOSIS_STATEMENT_TYPE_ENUM,
                            "description": (
                                "Never leadership_decision or recommendation — a diagnosis finding is always "
                                "evidence-grounded (a supported synthesis or inference), even one that reveals "
                                "a leadership decision is needed. Put that need into the explanation text, not "
                                "into this field."
                            ),
                        },
                        "evidence": {"type": "array", "items": EVIDENCE_LINK_SCHEMA},
                    },
                    "required": ["id", "title", "explanation", "significance", "statementType", "evidence"],
                },
            },
            "competitorOverlapAssessed": {"type": "boolean"},
            "competitorOverlapNote": {"type": "string"},
            "competitorContrasts": {
                "type": "array",
                "description": "One entry per competitor source, empty array if none were provided.",
                "items": {
                    "type": "object",
                    "properties": {"competitor": {"type": "string"}, "contrast": {"type": "string"}},
                    "required": ["competitor", "contrast"],
                },
            },
        },
        "required": ["evidence", "diagnosis", "competitorOverlapAssessed", "competitorOverlapNote", "competitorContrasts"],
    }
    narrative_block = (
        f"\n\nExisting corporate narrative the user supplied (compare the current story against this too):\n{existing_narrative}\n"
        if existing_narrative else ""
    )
    competitor_block = (
        f"\n\nCompetitor sources:\n\n{_format_sources(competitor_sources)}\n"
        if competitor_sources else ""
    )
    user_text = (
        f"Company/supporting sources:\n\n{_format_sources(sources)}\n"
        f"{narrative_block}"
        f"{competitor_block}\n"
        f"Already-extracted strategic foundation:\n{json.dumps(foundation_summary, indent=2)}\n\n"
        f"Verified evidence pool — these {len(verified_evidence)} items are the ONLY existing "
        f"evidenceId values. Every citation in a diagnosis finding's 'evidence' field must be "
        f"either (a) one of these exact ids, or (b) the id of a NEW evidence item you define in "
        f"your own 'evidence' array in this response. Do not cite a strategic-foundation item's "
        f"id as if it were an evidenceId:\n{json.dumps(verified_evidence, indent=2)}\n\n"
        "Diagnose the current story: what the company currently communicates, where the story "
        "is too narrow, generic, unsupported, or internally inconsistent, and what should be "
        "preserved. "
        + ("Competitor sources were provided — assess overlap and write one competitorContrasts "
           "entry per competitor, in the company's own voice (what's genuinely different, not "
           "an ownership claim)."
           if has_competitors else
           "No competitor sources were provided — set competitorOverlapAssessed to false, "
           "explain in competitorOverlapNote that overlap could not be assessed without "
           "competitor sources, and return an empty competitorContrasts array.")
        + " Add at most 5 NEW evidence items, and only if the existing pool above doesn't "
          "already cover something you need to cite — check the list first."
        + " Every finding's statementType must be source_fact, storymap_inference, "
          "storymap_synthesis, or aspiration — never leadership_decision or recommendation. "
          "If a finding reveals that leadership needs to decide something, say so in the "
          "explanation text; the finding itself still needs to be classified as a supported "
          "synthesis or inference about the CURRENT story, not as the decision itself."
        + _retry_context_block(prior_failure)
    )
    return call_tool(
        client, usage_tracker, "diagnosis", user_text,
        "submit_diagnosis", "Submit the current-story diagnosis.", schema,
    )


def _verified_evidence_for_prompt(evidence_pool):
    """Only ever show the model evidence that has already passed server-side citation
    verification — the fix for the fabricated-id bugs found in earlier test runs: a stage
    given no real ids to cite invents plausible-looking ones. Give it the actual pool,
    nothing else, so there's no id space left to invent from."""
    return [
        {"id": e["id"], "excerpt": e["excerpt"], "paraphrase": e["paraphrase"], "strength": e["strength"]}
        for e in evidence_pool.values()
        if e.get("verified")
    ]


def generate_candidates(client, usage_tracker, foundation_summary, diagnosis_summary, evidence_pool, prior_failure=None):
    verified_evidence = _verified_evidence_for_prompt(evidence_pool)
    schema = {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "oneSentenceStory": {"type": "string"},
                        "sevenParts": SEVEN_PARTS_SCHEMA,
                        "strategicLogic": {"type": "array", "items": {"type": "string"}},
                        "customerRelevance": {"type": "string", "description": "Qualitative sentence only — never a number or percentage."},
                        "differentiation": {"type": "string", "description": "Qualitative sentence only — never a number or percentage."},
                        "tradeoffs": {"type": "array", "items": {"type": "string"}},
                        "risks": {"type": "array", "items": {"type": "string"}},
                        "claims": {"type": "array", "items": EVIDENCE_LINK_SCHEMA},
                    },
                    "required": ["id", "name", "oneSentenceStory", "sevenParts", "strategicLogic", "customerRelevance", "differentiation", "tradeoffs", "risks", "claims"],
                },
            }
        },
        "required": ["candidates"],
    }
    user_text = (
        f"Strategic foundation:\n{json.dumps(foundation_summary, indent=2)}\n\n"
        f"Diagnosis:\n{json.dumps(diagnosis_summary, indent=2)}\n\n"
        f"Verified evidence pool — these {len(verified_evidence)} items are the ONLY "
        f"evidenceId values that exist. You may cite ONLY ids from this exact list. Do not "
        f"invent an id, and do not reference a strategic-foundation or diagnosis id as if it "
        f"were an evidenceId:\n{json.dumps(verified_evidence, indent=2)}\n\n"
        "Generate exactly 3 narrative candidates representing MATERIALLY DIFFERENT strategic "
        "directions (different roles the company could play, different value propositions, "
        "different bets) — not three versions of the same story with different wording. Every "
        "entry in a candidate's 'claims' array must cite one of the evidenceId values listed "
        "above; any id not in that list will be stripped before it reaches the user, and a "
        "candidate whose claims end up empty will likely fail evidence review. If you cannot "
        "find real evidence for part of a candidate, say so in tradeoffs/risks rather than "
        "citing something that isn't there."
        + _retry_context_block(prior_failure)
    )
    return call_tool(
        client, usage_tracker, "candidates", user_text,
        "submit_candidates", "Submit exactly three narrative candidates.", schema,
    )


def critique_candidates(client, usage_tracker, candidates, prior_failure=None):
    schema = {
        "type": "object",
        "properties": {
            "critiques": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "candidateId": {"type": "string"},
                        "findings": {"type": "array", "items": {"type": "string"}},
                        "strategicFitGate": {"type": "string", "enum": ["meets", "weak", "fails"]},
                        "differentiationGate": {"type": "string", "enum": ["meets", "weak", "fails"]},
                        "evidenceSupportGate": {"type": "string", "enum": ["supported", "partial", "unsupported"]},
                    },
                    "required": ["candidateId", "findings", "strategicFitGate", "differentiationGate", "evidenceSupportGate"],
                },
            }
        },
        "required": ["critiques"],
    }
    user_text = (
        f"Candidates to critique (you did not write these — review them independently and "
        f"skeptically):\n{json.dumps(candidates, indent=2)}\n\n"
        "For each candidate, assign three categorical gates (never numeric scores):\n"
        "- strategicFitGate: does it plausibly fit what the evidence shows about the company?\n"
        "- differentiationGate: is it meaningfully different from a generic competitor story?\n"
        "- evidenceSupportGate: are its core claims actually backed by direct/partial evidence, "
        "not just context or unsupported assertion?\n"
        "List concrete findings (strengths and weaknesses) for each."
        + _retry_context_block(prior_failure)
    )
    return call_tool(
        client, usage_tracker, "critique", user_text,
        "submit_critique", "Submit independent critique and gate assessment per candidate.", schema,
    )


def recommend_and_map(client, usage_tracker, survivors, all_candidates, evidence_pool, foundation_summary, prior_failure=None):
    verified_evidence = _verified_evidence_for_prompt(evidence_pool)
    schema = {
        "type": "object",
        "properties": {
            "recommendedCandidateId": {"type": "string"},
            "recommendedDecision": {"type": "string", "description": "One sentence naming the actual decision, e.g. 'Adopt X as the primary narrative.'"},
            "whyItWins": {"type": "string"},
            "whyCustomersCare": {"type": "string", "description": "If no independent customer evidence exists, say so plainly rather than asserting customer sentiment."},
            "whyCredible": {"type": "string"},
            "howDifferent": {"type": "string"},
            "missingEvidence": {"type": "array", "items": {"type": "string"}},
            "tradeoffs": {"type": "array", "items": {"type": "string"}},
            "leadershipDecisionsRequired": {"type": "array", "items": {"type": "string"}},
            "whyOthersNotSelected": {"type": "object", "additionalProperties": {"type": "string"}},
            "audiences": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "description": {"type": "string"}},
                    "required": ["name", "description"],
                },
            },
            "narrativeMap": {
                "type": "object",
                "properties": {
                    "coreNarrative": {"type": "string"},
                    "sevenParts": SEVEN_PARTS_SCHEMA,
                    "coreClaims": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "statement": {"type": "string"},
                                "evidence": {"type": "array", "items": EVIDENCE_LINK_SCHEMA},
                            },
                            "required": ["id", "statement", "evidence"],
                        },
                    },
                    "likelyObjections": {"type": "array", "items": {"type": "string"}},
                    "weakOrUnsupportedClaims": {"type": "array", "items": {"type": "string"}},
                    "unresolvedQuestions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["coreNarrative", "sevenParts", "coreClaims", "likelyObjections", "weakOrUnsupportedClaims", "unresolvedQuestions"],
            },
        },
        "required": [
            "recommendedCandidateId", "recommendedDecision", "whyItWins", "whyCustomersCare", "whyCredible",
            "howDifferent", "missingEvidence", "tradeoffs", "leadershipDecisionsRequired", "whyOthersNotSelected",
            "audiences", "narrativeMap",
        ],
    }
    user_text = (
        f"Candidates that passed every hard gate (strategic fit, differentiation, evidence "
        f"support) — choose the strongest and justify why:\n{json.dumps(survivors, indent=2)}\n\n"
        f"All candidates including rejected ones (for the 'why others not selected' "
        f"explanation, which must cover every non-recommended candidate):\n{json.dumps(all_candidates, indent=2)}\n\n"
        f"Strategic foundation (for deriving priority audiences from the chosen-customer items):"
        f"\n{json.dumps(foundation_summary, indent=2)}\n\n"
        f"Verified evidence pool — these {len(verified_evidence)} items are the ONLY "
        f"evidenceId values that exist; if coreClaims needs to cite anything beyond what the "
        f"winning candidate's own 'claims' array already covers, it must come from this list — "
        f"do not invent an id:\n{json.dumps(verified_evidence, indent=2)}\n\n"
        "Write the recommendation, priority audiences (grounded in the chosen-customer items "
        "above, qualitative descriptions only), and the Narrative Map (Context, Tension, "
        "Belief, Role, Value, Proof, Direction) for the winning candidate. coreClaims should "
        "restate the winning candidate's key claims as named statements with real evidence "
        "links. likelyObjections should be genuine, specific pushback a skeptical executive "
        "would raise — not rhetorical. weakOrUnsupportedClaims should name any part of the "
        "winning candidate that rests on thin evidence, even though it still passed review — "
        "flag it rather than polish it away. Keep whyItWins under 150 words, each "
        "tradeoff/leadership-decision/missing-evidence entry to one sentence, and coreClaims to "
        "at most 5 entries — be complete but not verbose."
        + _retry_context_block(prior_failure)
    )
    return call_tool(
        client, usage_tracker, "recommendation_and_map", user_text,
        "submit_recommendation_and_map", "Submit the final recommendation, audiences, and narrative map.", schema,
        max_tokens=12000,
    )
