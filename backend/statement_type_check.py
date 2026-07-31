"""Validates that a record's classification fields (type, statementType) are both
individually valid and compatible with each other, rather than trusting the model's
self-assigned labels at face value.

This replaced an earlier version that only checked one specific pattern (type
"unresolved" paired with the wrong statementType). That version missed a real case from
the 2026-07-29 test run: a record with type "market_change" carrying statementType
"unresolved" — a value that isn't even in the STATEMENT_TYPES enum — slipped through
untouched because the check only fired when type itself was "unresolved". This version
checks every record generically: missing fields, invalid enum membership on both fields,
and type/statementType compatibility, in that order, before ever reaching the semantic
checks (does a "source_fact" actually read like one).

Every outcome is one of three actions:
  - "ok"      — valid as submitted, nothing changed.
  - "mapped"  — corrected to a value the app's own rules make unambiguous (e.g. type
                "unresolved" always means statementType "leadership_decision"). The
                correction is recorded, never silent.
  - "rejected" — no unambiguous correction exists. The caller must drop this record from
                what reaches the user and mark it for regeneration — never ship a guess.
"""
import re

from schema_constants import (
    DIAGNOSIS_ALLOWED_STATEMENT_TYPES,
    NON_UNRESOLVED_ALLOWED_STATEMENT_TYPES,
    STATEMENT_TYPES,
    STRATEGIC_CHOICE_TYPES,
)

INFERENCE_SIGNAL_PATTERN = re.compile(
    r"\b(suggests?|implies?|likely|appears? to|may indicate|could mean|presumably|"
    r"seems? to|indicates? that|arguably|it'?s possible that|this implies|this suggests)\b",
    re.IGNORECASE,
)


def check_statement_type(record, text_fields):
    """Semantic checks only — assumes statementType is already a valid, compatible enum
    value. Returns (corrected_statement_type, [violation_strings]); never rejects, only
    downgrades toward the more epistemically humble type, since these corrections are
    well-established and safe by the app's own rules (schemas.js's own definitions)."""
    violations = []
    statement_type = record["statementType"]
    evidence_links = record.get("evidence", [])
    contributing = [link for link in evidence_links if link["relevance"] in ("direct", "partial")]
    has_direct = any(link["relevance"] == "direct" for link in evidence_links)
    text = " ".join(record.get(f) or "" for f in text_fields)

    if statement_type == "source_fact" and not has_direct:
        violations.append(
            f'"{record["id"]}" was labeled source_fact but has no direct-relevance evidence '
            f"link — downgraded to storymap_inference"
        )
        statement_type = "storymap_inference"

    match = INFERENCE_SIGNAL_PATTERN.search(text)
    if statement_type == "source_fact" and match:
        violations.append(
            f'"{record["id"]}" was labeled source_fact but its text uses inference language '
            f'("{match.group(0)}") — downgraded to storymap_inference'
        )
        statement_type = "storymap_inference"

    if statement_type == "storymap_synthesis" and len(contributing) < 2:
        violations.append(
            f'"{record["id"]}" was labeled storymap_synthesis but cites fewer than 2 '
            f"contributing evidence links — downgraded to storymap_inference"
        )
        statement_type = "storymap_inference"

    return statement_type, violations


def _missing(record, field):
    return field not in record or record.get(field) in (None, "")


def validate_strategic_choice(record, text_fields=("statement",)):
    """Returns (action, corrected_statement_type_or_None, [violation_strings]).
    action is "ok" | "mapped" | "rejected"."""
    record_id = record.get("id", "<missing id>")

    if _missing(record, "type"):
        return "rejected", None, [f'"{record_id}" is missing a "type" field — cannot classify, rejecting for regeneration']
    if _missing(record, "statementType"):
        return "rejected", None, [f'"{record_id}" is missing a "statementType" field — cannot classify, rejecting for regeneration']

    choice_type = record["type"]
    statement_type = record["statementType"]

    if choice_type not in STRATEGIC_CHOICE_TYPES:
        return "rejected", None, [
            f'"{record_id}" has invalid type "{choice_type}" (not one of {STRATEGIC_CHOICE_TYPES}) — rejecting for regeneration'
        ]

    if statement_type not in STATEMENT_TYPES:
        if choice_type == "unresolved":
            return "mapped", "leadership_decision", [
                f'"{record_id}" has statementType "{statement_type}", which is not a valid statementType at all; '
                f'type "unresolved" makes the correction unambiguous — mapped to leadership_decision'
            ]
        return "rejected", None, [
            f'"{record_id}" has invalid statementType "{statement_type}" (not one of {STATEMENT_TYPES}) and type '
            f'"{choice_type}" gives no unambiguous correction — rejecting for regeneration'
        ]

    if choice_type == "unresolved":
        if statement_type != "leadership_decision":
            return "mapped", "leadership_decision", [
                f'"{record_id}" has type "unresolved" but statementType "{statement_type}" — unresolved items '
                f"always mean leadership_decision — mapped"
            ]
        return "ok", "leadership_decision", []

    # choice_type != "unresolved" from here on: this is a claim, not an open decision.
    if statement_type == "leadership_decision":
        return "rejected", None, [
            f'"{record_id}" has type "{choice_type}" (an analyzed claim) but statementType "leadership_decision" '
            f"(implies no claim exists yet) — contradictory with no unambiguous fix, rejecting for regeneration"
        ]
    if statement_type not in NON_UNRESOLVED_ALLOWED_STATEMENT_TYPES:
        return "rejected", None, [
            f'"{record_id}" has type "{choice_type}" but statementType "{statement_type}", which is not valid for a '
            f"non-unresolved strategic-foundation item — rejecting for regeneration"
        ]

    corrected, semantic_violations = check_statement_type(record, text_fields)
    action = "mapped" if semantic_violations else "ok"
    return action, corrected, semantic_violations


def validate_diagnosis_finding(record, text_fields=("title", "explanation")):
    """Returns (action, corrected_statement_type_or_None, [violation_strings]).
    DiagnosisFinding has no "type" field — only statementType is checked."""
    record_id = record.get("id", "<missing id>")

    if _missing(record, "statementType"):
        return "rejected", None, [f'"{record_id}" is missing a "statementType" field — cannot classify, rejecting for regeneration']

    statement_type = record["statementType"]

    if statement_type not in STATEMENT_TYPES:
        return "rejected", None, [
            f'"{record_id}" has invalid statementType "{statement_type}" (not one of {STATEMENT_TYPES}) — rejecting for regeneration'
        ]
    if statement_type not in DIAGNOSIS_ALLOWED_STATEMENT_TYPES:
        return "rejected", None, [
            f'"{record_id}" has statementType "{statement_type}", which is not valid for a diagnosis finding '
            f"(a diagnosis describes the current story, not a leadership decision or final recommendation) — "
            f"rejecting for regeneration"
        ]

    corrected, semantic_violations = check_statement_type(record, text_fields)
    action = "mapped" if semantic_violations else "ok"
    return action, corrected, semantic_violations
