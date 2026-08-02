"""Confidence derivation, ported line-for-line in spirit from js/case-utils.js so live and
seeded cases enforce the exact same honesty rule: confidence is computed from evidence
links, never authored by a human or asserted by a model. Keep this in sync with
case-utils.js if either changes — see docs/agent-contracts.md.

Two separate measures, never conflated (governing narrative-stage decision 2):
  - compute_confidence_from_links: "how strongly is this claim established as true NOW."
    Unchanged formula/meaning. The authoritative number for narrativeStage proven_today/
    emerging/in_build. Evidence from a competitor/market source can never contribute here
    (structural enforcement of rule 9 — even if a model mislabels a competitor-sourced link
    "direct", it is filtered out before this formula ever sees it; see fromCompetitorSource,
    stamped once at evidence-pool creation in pipeline_runner.merge_evidence).
  - compute_directional_credibility: "how credible is the STATED DIRECTION, given company
    intent, commitment signals, and market/category logic." Only meaningful for
    narrativeStage strategic_direction/aspiration_pending_leadership. Deliberately counts
    context-relevance and competitor/market-sourced evidence (real signal for a direction
    claim) and company_position links (management's own stated intent) — evidence confidence
    structurally excludes for good reason, but a direction claim is a different question.
"""
STRENGTH_WEIGHT = {"strong": 1, "moderate": 0.65, "weak": 0.3, "unsupported": 0}
RELEVANCE_WEIGHT = {"direct": 1, "partial": 0.5, "context": 0, "conflicting": 0}

# No direct/partial support at all -> honestly low, not zero (it isn't contradicted, just
# unestablished).
NO_DIRECT_EVIDENCE_CONFIDENCE = 0.3
MAX_CONFIDENCE = 0.95
SINGLE_SOURCE_CONFIDENCE_CAP = 0.85

# directionalCredibility weighting/ceiling — deliberately looser (counts context/company-
# position, which confidence never does) but capped lower than confidence's 0.95: a
# well-evidenced DIRECTION is never shown as more certain than a well-evidenced FACT.
DIRECTIONAL_RELEVANCE_WEIGHT = {"direct": 1, "partial": 0.7, "context": 0.5, "company_position": 0.4, "conflicting": 0}
MARKET_LOGIC_WEIGHT = 0.5  # flat weight for any competitor/market-sourced link, regardless of its stated relevance
NO_DIRECTIONAL_SUPPORT = 0.25
DIRECTIONAL_CREDIBILITY_CAP = 0.85


def _is_company_fact_evidence(link, ev):
    """Company-specific claims must use company-specific evidence (rule 9) — a
    competitor/market-sourced link can never count as proof of a fact about the company
    being analyzed, regardless of how the model labeled its relevance."""
    return link["relevance"] in ("direct", "partial") and not ev.get("fromCompetitorSource", False)


def compute_confidence_from_links(links, evidence_by_id):
    contributing = [
        (link, evidence_by_id[link["evidenceId"]])
        for link in links
        if link["evidenceId"] in evidence_by_id and _is_company_fact_evidence(link, evidence_by_id[link["evidenceId"]])
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


def compute_directional_credibility(links, evidence_by_id):
    contributing_weights = []
    for link in links:
        ev = evidence_by_id.get(link["evidenceId"])
        if ev is None or link["relevance"] == "conflicting":
            continue
        relevance_weight = (
            MARKET_LOGIC_WEIGHT
            if ev.get("fromCompetitorSource", False)
            else DIRECTIONAL_RELEVANCE_WEIGHT.get(link["relevance"], 0)
        )
        contributing_weights.append(relevance_weight * STRENGTH_WEIGHT.get(ev["strength"], 0))

    if not contributing_weights:
        return NO_DIRECTIONAL_SUPPORT

    avg = sum(contributing_weights) / len(contributing_weights)
    return round(min(avg, DIRECTIONAL_CREDIBILITY_CAP) * 100) / 100
