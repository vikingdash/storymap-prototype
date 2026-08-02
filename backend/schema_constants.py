"""Single source of truth for every enum used by the live pipeline. Both the Anthropic
tool schemas (anthropic_pipeline.py, which tell the model what's allowed) and the
server-side validator (statement_type_check.py, which checks what the model actually
returned) import from here — so the two can never silently drift apart the way they did
before this file existed (the model produced statementType "unresolved", a value outside
the declared enum, and nothing generically checked for that).
"""
STATEMENT_TYPES = [
    "source_fact",
    "storymap_inference",
    "storymap_synthesis",
    "recommendation",
    "leadership_decision",
    "aspiration",
]

STRATEGIC_CHOICE_TYPES = [
    "customer",
    "market",
    "market_change",
    "way_to_win",
    "capability",
    "proof",
    "assumption",
    "risk",
    "unresolved",
]

EVIDENCE_RELEVANCE_TYPES = ["direct", "partial", "context", "conflicting"]
EVIDENCE_STRENGTH_TYPES = ["strong", "moderate", "weak", "unsupported"]
EVIDENCE_FRESHNESS_TYPES = ["current", "aging", "stale"]
SIGNIFICANCE_TYPES = ["high", "medium", "low"]

# Temporal/maturity axis — orthogonal to statementType (which answers "how do we know
# this," an epistemic question) and to a StrategicChoice's `type` (what KIND of claim).
# narrativeStage answers "when is this true." A claim can be e.g. storymap_synthesis +
# in_build at once: both axes are real and independent, neither implies the other.
# Required on every StrategicChoice/NarrativeCoreClaim except type=="unresolved" (a
# leadership decision about a story GAP has no temporal status of its own, exactly like
# it has no evidence model / confidence — see confidence.py). Model-classified, never
# inferred from `type` (a "capability" can be proven_today, emerging, or in_build; a
# "way_to_win" can describe current advantage or future intent — type and maturity are
# independent, so no type -> stage lookup table exists anywhere in this codebase).
NARRATIVE_STAGES = [
    "proven_today",
    "emerging",
    "in_build",
    "strategic_direction",
    "aspiration_pending_leadership",
]

NARRATIVE_STAGE_LABELS = {
    "proven_today": "Proven today",
    "emerging": "Emerging",
    "in_build": "In build",
    "strategic_direction": "Strategic direction",
    "aspiration_pending_leadership": "Aspiration — requires leadership approval",
}

# One-line temporal-honesty guidance per stage, shared verbatim between the prompt (so the
# model is told the same rule it's graded on) and statement_type_check.py's language
# checks below. "is/has/does" for proven_today down to "could/intends to" for aspiration —
# a future state must never be phrased as already achieved, regardless of how much
# evidence supports it.
NARRATIVE_STAGE_WORDING_GUIDANCE = {
    "proven_today": "present tense, stated as fact: is, has, does",
    "emerging": "is beginning to, is increasingly",
    "in_build": "is building, is developing, is assembling",
    "strategic_direction": "is moving toward, aims to become, is positioning to",
    "aspiration_pending_leadership": "could, intends to — explicitly leadership-owned, never asserted as decided",
}

# A StrategicChoice with type != "unresolved" is an actual analyzed claim, so its
# statementType may never be "leadership_decision" (that means "no claim yet, still
# needs deciding" — reserved exclusively for type == "unresolved") or "recommendation"
# (reserved for the final Recommendation object, not an intermediate foundation item).
NON_UNRESOLVED_ALLOWED_STATEMENT_TYPES = {"source_fact", "storymap_inference", "storymap_synthesis", "aspiration"}

# A DiagnosisFinding describes the current story as it exists today — it is never itself
# a leadership decision or a final recommendation; those belong to later pipeline stages.
# A finding MAY note that a leadership decision is required (that's content, in the
# explanation text), but the finding's own classification must be a supported synthesis
# or inference, never "leadership_decision" itself — that label means "no evidence model
# applies," which contradicts a diagnosis finding always being evidence-grounded.
# DIAGNOSIS_STATEMENT_TYPE_ENUM feeds anthropic_pipeline.py's JSON schema directly (a
# prompt-level constraint — the model is never even offered "leadership_decision" as an
# option for this field) and DIAGNOSIS_ALLOWED_STATEMENT_TYPES (the same values, as a set)
# is statement_type_check.py's server-side backstop for whenever the model ignores the
# schema anyway — the same two-layer pattern used throughout this file.
DIAGNOSIS_STATEMENT_TYPE_ENUM = ["source_fact", "storymap_inference", "storymap_synthesis", "aspiration"]
DIAGNOSIS_ALLOWED_STATEMENT_TYPES = set(DIAGNOSIS_STATEMENT_TYPE_ENUM)

# What an uploaded internal .docx document IS, in the analysis — set once by the user at
# upload time (AnalyzeCompany.js), never inferred by the model. Saved directly on the
# source's own "documentRole" field (jobs.py/document_extractor.py), passed through
# unchanged by every pipeline stage exactly like sourceType, and rendered in the Evidence
# Room (js/labels.js's DOCUMENT_ROLE_LABELS mirrors this list's display text).
DOCUMENT_ROLES = [
    "current_draft_narrative",
    "strategy_or_business_plan",
    "customer_research",
    "proof_or_performance_evidence",
    "investor_or_financial_material",
    "existing_messaging",
    "other_internal_context",
]

DOCUMENT_ROLE_LABELS = {
    "current_draft_narrative": "Current draft corporate narrative",
    "strategy_or_business_plan": "Strategy or business plan",
    "customer_research": "Customer research",
    "proof_or_performance_evidence": "Proof or performance evidence",
    "investor_or_financial_material": "Investor or financial material",
    "existing_messaging": "Existing messaging",
    "other_internal_context": "Other internal context",
}
