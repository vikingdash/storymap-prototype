"""Confidence derivation, ported line-for-line in spirit from js/case-utils.js so live and
seeded cases enforce the exact same honesty rule: confidence is computed from evidence
links, never authored by a human or asserted by a model. Keep this in sync with
case-utils.js if either changes — see docs/agent-contracts.md.
"""
STRENGTH_WEIGHT = {"strong": 1, "moderate": 0.65, "weak": 0.3, "unsupported": 0}
RELEVANCE_WEIGHT = {"direct": 1, "partial": 0.5, "context": 0, "conflicting": 0}

# No direct/partial support at all -> honestly low, not zero (it isn't contradicted, just
# unestablished).
NO_DIRECT_EVIDENCE_CONFIDENCE = 0.3
MAX_CONFIDENCE = 0.95
SINGLE_SOURCE_CONFIDENCE_CAP = 0.85


def compute_confidence_from_links(links, evidence_by_id):
    contributing = [
        (link, evidence_by_id[link["evidenceId"]])
        for link in links
        if link["relevance"] in ("direct", "partial") and link["evidenceId"] in evidence_by_id
    ]

    if not contributing:
        return NO_DIRECT_EVIDENCE_CONFIDENCE

    weights = [
        STRENGTH_WEIGHT.get(ev["strength"], 0) * RELEVANCE_WEIGHT.get(link["relevance"], 0)
        for link, ev in contributing
    ]
    avg = sum(weights) / len(weights)

    distinct_sources = len({ev["sourceId"] for _, ev in contributing})
    cap = MAX_CONFIDENCE if distinct_sources >= 2 else SINGLE_SOURCE_CONFIDENCE_CAP

    return round(min(avg, cap) * 100) / 100
