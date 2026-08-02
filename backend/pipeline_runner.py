"""Orchestrates the live 'Analyze a company' pipeline end to end: fetch real user-supplied
URLs, run the 5 Anthropic-backed stages, apply citation verification / statement-type
validation / confidence derivation, and assemble a dataset shaped exactly like
js/schemas.js's types so the existing frontend screens can render it unmodified.

Every one of the 5 model-backed stages goes through the same two-layer boundary:
  1. validate_stage_response() (stage_validation.py) — is the raw response envelope even
     a usable object with the right top-level keys and types? Checked BEFORE any other
     code ever does response["key"].
  2. Stage-specific per-item processing (filter_malformed_records, sanitize_links,
     validate_strategic_choice/validate_diagnosis_finding, validate_narrative_map_shape)
     — unchanged from before; these are genuinely stage-specific business rules, not
     duplicated ad hoc envelope checks.

Retry has two distinct mechanisms, per the approved policy:
  - AUTOMATIC, in-line, within a single run_analysis()/regenerate_from() call:
    run_model_stage() tries a stage up to MAX_TOTAL_ATTEMPTS times, feeding the exact
    validation failure from one attempt into the next attempt's prompt (never a blind
    identical repeat), never retrying anything outside this validation-failure class
    (SSRF blocks, unreachable URLs, missing API key, auth errors all propagate
    immediately, uncaught, from well outside this mechanism).
  - MANUAL, external, one attempt per call: the 5 retry_xxx() functions, meant to be
    invoked later via dedicated endpoints after automatic attempts are exhausted — each
    is a single deliberate attempt, not a new automatic-retry loop.

Used by both run_basecamp_test.py (CLI, one hardcoded company) and jobs.py (the Flask
background-job system, arbitrary user input) — this is the one place the actual pipeline
logic lives; neither caller re-implements it.
"""
import re
import traceback
from datetime import datetime, timezone
from urllib.parse import urlparse

import anthropic_pipeline as pipe
from citation_verify import excerpt_is_verified
from confidence import compute_confidence_from_links, compute_directional_credibility
from extractor import extract_readable_text
from fetcher import FetchError, fetch_url
from schema_constants import NARRATIVE_STAGES
from stage_validation import (
    CANDIDATES_RESPONSE_SCHEMA,
    CRITIQUE_RESPONSE_SCHEMA,
    DIAGNOSIS_RESPONSE_SCHEMA,
    FOUNDATION_RESPONSE_SCHEMA,
    RECOMMEND_AND_MAP_RESPONSE_SCHEMA,
    StageResponseError,
    validate_stage_response,
)
from statement_type_check import validate_diagnosis_finding, validate_strategic_choice

# Stages that count as "credible evidence of company movement" for the direction-coverage
# check below — proven_today alone never triggers it (nothing to require direction coverage
# against if the foundation shows no movement at all).
DIRECTION_COVERAGE_FOUNDATION_STAGES = {"emerging", "in_build", "strategic_direction"}
# Stages a CANDIDATE's own narrativeStages entry must include to count as "a genuine
# direction story" — deliberately excludes proven_today/emerging (a story about only what
# already exists or is just beginning isn't a direction story) but includes
# aspiration_pending_leadership (a clearly-flagged, leadership-owned future role still
# counts as the company expressing where it's going).
CANDIDATE_DIRECTION_STAGES = {"in_build", "strategic_direction", "aspiration_pending_leadership"}

MAX_SUPPORTING_URLS = 5
MAX_COMPETITOR_URLS = 3
MIN_WORD_COUNT_WARNING = 40

# Initial attempt + up to 2 automatic retries = 3 total, per the approved retry policy.
# After this many failed attempts for one stage within a single run, the stage is
# reported stage_failed and only a separate, deliberate MANUAL retry (retry_xxx() below,
# invoked later via its own endpoint) can try again — never another automatic attempt.
MAX_TOTAL_ATTEMPTS = 3

# Sonnet 5 introductory pricing (platform.claude.com/docs/en/about-claude/pricing,
# confirmed 2026-07-29, in effect through 2026-08-31): $2/MTok input, $10/MTok output.
SONNET5_INPUT_PER_MTOK = 2.0
SONNET5_OUTPUT_PER_MTOK = 10.0

# Deterministic, disclosed mapping from the critique stage's categorical gates to the 1-5
# numeric scale the existing NarrativeChoices.js/scoring.js already render — never model
# generated. "weak"/"partial" sit exactly at the pass threshold (>=3) so a borderline pass
# is still visibly a pass, not silently rounded up to look identical to "meets"/"supported".
# "Customer relevance" and "Durability" are deliberately never included — this pipeline
# never fabricates a customer-relevance score without customer evidence, and durability
# isn't assessed by the critique stage at all.
GATE_TO_SCORE = {"meets": 4, "weak": 3, "fails": 1, "supported": 4, "partial": 3, "unsupported": 1}

# Governing-spec Phase 1 canonical candidate status vocabulary. Exactly three values, each
# meaning one thing regardless of which pipeline stage last touched it (see
# build_candidate_scores_and_status/process_candidates_response/process_critique_response):
#   pending  — generated (narrative_choices), not yet evaluated by critique
#   viable   — passed every critique gate; MAY be shown as "Recommended" by the frontend
#              when its id matches recommendation.selectedCandidateId, but that is derived
#              at render time, never a fourth persisted status value (decision 1)
#   rejected — failed at least one critique gate
# Once set at critique, a candidate's status/gateResults/rejectionReasons are never
# rewritten again — see process_recommend_and_map_response, which only ever records the
# winner in the separate `recommendation.selectedCandidateId` field.
CANDIDATE_STATUS_PENDING = "pending"
CANDIDATE_STATUS_VIABLE = "viable"
CANDIDATE_STATUS_REJECTED = "rejected"

# Per-gate criterion label + machine-readable id, used to build the structured
# candidate.gateResults entries (governing spec Phase 1, decision 3) — one entry per
# critique gate, always present once critique has run, so the frontend never has to parse
# criticFindings prose to know why a candidate passed or failed.
GATE_CRITERIA = [
    ("strategicFitGate", "Strategic fit"),
    ("differentiationGate", "Differentiation"),
    ("evidenceSupportGate", "Evidence strength"),
    ("companyAltitudeGate", "Company altitude"),
]
GATE_PASS_THRESHOLD = 3
# "weak"/"partial" map to "borderline_pass" rather than a plain "pass" specifically so a
# borderline margin stays visible for later human review (decision 3's explicit
# requirement) instead of looking identical to a comfortable "meets"/"supported" pass.
GATE_OUTCOME_LABELS = {
    "meets": "pass", "supported": "pass",
    "weak": "borderline_pass", "partial": "borderline_pass",
    "fails": "fail", "unsupported": "fail",
}

# Same non-absolute ceiling used elsewhere in this app (case-utils.js's MAX_CONFIDENCE) —
# even a verified-exact-match excerpt doesn't get shown as 100% certain.
EXTRACTION_CONFIDENCE_VERIFIED = 0.95

# A user may trigger exactly this many DELIBERATE manual retries of a single stage
# (beyond the MAX_TOTAL_ATTEMPTS automatic ones already spent inside the original run) —
# see check_manual_retry_allowed(). Enforced server-side against the persisted attempt
# history, never trusted from the client.
MAX_MANUAL_RETRIES = 1


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def compute_cost(totals):
    return round(
        (totals["input_tokens"] / 1_000_000 * SONNET5_INPUT_PER_MTOK)
        + (totals["output_tokens"] / 1_000_000 * SONNET5_OUTPUT_PER_MTOK),
        4,
    )


def build_candidate_scores_and_status(gate, evaluated_at_stage="critique"):
    """Pure and unit-testable on its own: translates a critique gate assessment
    (categorical, from the model) into the candidate's numeric scores (deterministic
    GATE_TO_SCORE lookup — never model-generated), canonical status, and the structured
    gateResults/rejectionReasons the governing spec's Phase 1 decision 3 requires (machine-
    readable outcome, visible explanation, traceability to the gate, no parsing of prose to
    determine status). Never includes "Customer relevance" or "Durability" — see
    GATE_TO_SCORE's docstring for why. Returns (scores, status, gate_results,
    rejection_reasons)."""
    scores = {}
    gate_results = []
    for gate_id, criterion in GATE_CRITERIA:
        raw = gate[gate_id]
        score = GATE_TO_SCORE[raw]
        scores[criterion] = score
        gate_results.append({
            "gateId": gate_id,
            "criterion": criterion,
            "outcome": GATE_OUTCOME_LABELS[raw],
            "score": score,
            "threshold": GATE_PASS_THRESHOLD,
            "margin": score - GATE_PASS_THRESHOLD,
            "explanation": f'{criterion} assessed as "{raw}".',
            "evaluatedAtStage": evaluated_at_stage,
        })
    fails = any(gr["outcome"] == "fail" for gr in gate_results)
    status = CANDIDATE_STATUS_REJECTED if fails else CANDIDATE_STATUS_VIABLE
    rejection_reasons = [
        {"code": f'{gr["gateId"]}_failed', "gateId": gr["gateId"], "explanation": gr["explanation"]}
        for gr in gate_results if gr["outcome"] == "fail"
    ] if fails else []
    return scores, status, gate_results, rejection_reasons


class PipelineError(Exception):
    """A hard failure — outside model-response validation entirely (company URL
    unreachable/SSRF-blocked, etc.). Never caught or retried by run_model_stage; the
    approved policy explicitly excludes this class from automatic retry."""
    pass


class RetryLimitReachedError(ValueError):
    """Raised when a manual retry is requested for a stage that has already used its one
    allowed manual retry (see MAX_MANUAL_RETRIES/check_manual_retry_allowed), OR when one
    is already in flight for that stage (see the pendingManualRetry reservation jobs.py
    writes atomically under a per-job lock) — a hard stop enforced server-side, before
    any API call, so repeated/concurrent endpoint calls can never spend unlimited money
    on the same failed stage. `.code` is the exact machine-readable reason
    ("retry_limit_reached" or "retry_in_progress") — callers (app.py) surface it
    verbatim rather than re-deriving it from the message text."""

    def __init__(self, message, code="retry_limit_reached"):
        self.code = code
        super().__init__(message)


class RegenerationLimitReachedError(ValueError):
    """Raised when a full regeneration (editing the foundation and rerunning diagnosis
    onward) is requested for a job that has already used its MAX_FULL_REGENERATIONS
    allowance. A validation failure of the submitted edit never reaches this check (and
    never counts against the allowance) — only an actually-accepted, dispatched
    regeneration consumes it."""
    pass


class SourceExpansionLimitReachedError(ValueError):
    """Raised when "add sources and re-analyze" is requested for a job that has already
    used its MAX_SOURCE_EXPANSIONS allowance — tracked independently of
    RegenerationLimitReachedError; see MAX_SOURCE_EXPANSIONS's docstring for why the two
    are never shared."""
    pass


class RecommendationValidationError(ValueError):
    """Raised when the model's recommendedCandidateId doesn't reference one of the
    candidates that actually survived critique (governing spec Phase 1: "success requires
    a valid selectedCandidateId referencing a viable candidate"). Caught by the same
    attempt/retry machinery as every other stage-specific validation failure — see
    ATTEMPT_EXCEPTIONS below — so a model hallucinating an id costs a retry, not a crash."""
    pass


def build_recommendation_state(outcome, selected_candidate_id=None, failure_reason=None, missing_evidence=None, leadership_decisions=None, detail=None):
    """The one place the canonical recommendation-outcome object (governing spec Phase 1)
    is ever constructed — every call site (run_pipeline_from_sources, regenerate_from,
    retry_recommendation_and_map) builds it here via this single function, so
    success/no_candidate_passed/stage_failed always produce the exact same shape regardless
    of entry point, and regardless of whether recommendation_and_map ran at all (unlike
    before, this is now ALSO built and persisted for no_candidate_passed — previously that
    branch returned without ever calling persist_cb for this stage, which is the exact
    mechanism behind the checkpoint.recommendation_and_map == None ambiguity between
    no_candidate_passed and stage_failed that this schema exists to eliminate).

    Selection lives ONLY here (selectedCandidateId) — never as a second candidate.status
    value; see process_recommend_and_map_response, which no longer rewrites candidate
    status at all (decision 1: a selected candidate remains structurally "viable").
    """
    return {
        "outcome": outcome,
        "selectedCandidateId": selected_candidate_id,
        "failureReason": failure_reason,
        "missingEvidence": list(missing_evidence) if missing_evidence else [],
        "leadershipDecisions": list(leadership_decisions) if leadership_decisions else [],
        "createdAt": now_iso(),
        "detail": detail,
    }


def filter_malformed_records(items, required_keys, stage, rejected_records_report, record_kind="record"):
    """Boundary defense for ARRAY items — validate_stage_response (stage_validation.py)
    checks the top-level envelope; this checks each item inside an array field the
    envelope declared. Never coerces a malformed item into something usable — it is
    dropped and reported, consistent with "reject or regenerate, never silently coerce
    ambiguous data."
    """
    if not isinstance(items, list):
        rejected_records_report.append({
            "stage": stage, "id": None,
            "reasons": [f"expected a list of {record_kind}s, got {type(items).__name__}: {str(items)[:120]!r}"],
        })
        return []
    kept = []
    for item in items:
        if not isinstance(item, dict):
            rejected_records_report.append({
                "stage": stage, "id": None,
                "reasons": [f"malformed {record_kind}: expected an object, got {type(item).__name__} ({str(item)[:120]!r})"],
            })
            continue
        missing = [k for k in required_keys if k not in item]
        if missing:
            rejected_records_report.append({
                "stage": stage, "id": item.get("id"),
                "reasons": [f"malformed {record_kind}: missing required field(s) {missing}"],
            })
            continue
        kept.append(item)
    return kept


STRATEGIC_CHOICE_REQUIRED_KEYS = ["id", "type", "statement", "statementType", "evidence"]
DIAGNOSIS_FINDING_REQUIRED_KEYS = ["id", "title", "explanation", "significance", "statementType", "evidence"]
CANDIDATE_REQUIRED_KEYS = ["id", "name", "oneSentenceStory", "sevenParts", "strategicLogic", "customerRelevance", "differentiation", "tradeoffs", "risks", "claims", "narrativeStages"]
CRITIQUE_REQUIRED_KEYS = ["candidateId", "findings", "strategicFitGate", "differentiationGate", "evidenceSupportGate", "companyAltitudeGate"]
CORE_CLAIM_REQUIRED_KEYS = ["id", "statement", "evidence", "narrativeStage"]
NARRATIVE_STAGE_ENTRY_REQUIRED_KEYS = ["stage", "statement", "evidence"]
COMPETITOR_CONTRAST_REQUIRED_KEYS = ["competitor", "contrast"]
AUDIENCE_REQUIRED_KEYS = ["name", "description"]
EVIDENCE_ITEM_REQUIRED_KEYS = ["id", "sourceId", "excerpt", "paraphrase", "evidenceType", "strength", "freshness"]
NARRATIVE_MAP_REQUIRED_KEYS = ["coreNarrative", "coreClaims", "likelyObjections", "weakOrUnsupportedClaims", "unresolvedQuestions", "sevenParts"]
NARRATIVE_MAP_ARRAY_FIELDS = ["coreClaims", "likelyObjections", "weakOrUnsupportedClaims", "unresolvedQuestions"]
SEVEN_PARTS_KEYS = ["context", "tension", "belief", "role", "value", "proof", "direction"]


class NarrativeMapValidationError(ValueError):
    """Raised by validate_narrative_map_shape — a distinct type from the generic
    TypeError/KeyError catches elsewhere so this specific stage-unique deep check is
    still caught by the same attempt/retry machinery as everything else."""
    pass


def validate_narrative_map_shape(nm):
    """Requires narrativeMap to be a genuine object with all seven Context/Tension/
    Belief/Role/Value/Proof/Direction fields present as non-empty strings, plus its other
    required fields present with the right container type. Raises
    NarrativeMapValidationError with an exact, specific reason on any violation — never
    coerces a bare string, an array, a missing field, or a malformed nested record into
    something that merely looks valid."""
    if not isinstance(nm, dict):
        raise NarrativeMapValidationError(f"narrativeMap must be an object, got {type(nm).__name__}: {str(nm)[:160]!r}")

    missing_top = [k for k in NARRATIVE_MAP_REQUIRED_KEYS if k not in nm]
    if missing_top:
        raise NarrativeMapValidationError(f"narrativeMap is missing required field(s) {missing_top}")

    if not isinstance(nm["coreNarrative"], str) or not nm["coreNarrative"].strip():
        raise NarrativeMapValidationError(f"narrativeMap.coreNarrative must be a non-empty string, got {type(nm['coreNarrative']).__name__}")

    for field in NARRATIVE_MAP_ARRAY_FIELDS:
        if not isinstance(nm[field], list):
            raise NarrativeMapValidationError(f"narrativeMap.{field} must be an array, got {type(nm[field]).__name__}: {str(nm[field])[:120]!r}")

    seven_parts = nm["sevenParts"]
    if not isinstance(seven_parts, dict):
        raise NarrativeMapValidationError(f"narrativeMap.sevenParts must be an object, got {type(seven_parts).__name__}: {str(seven_parts)[:160]!r}")

    missing_parts = [k for k in SEVEN_PARTS_KEYS if k not in seven_parts]
    if missing_parts:
        raise NarrativeMapValidationError(f"narrativeMap.sevenParts is missing required field(s) {missing_parts} (Context/Tension/Belief/Role/Value/Proof/Direction all required)")

    invalid_parts = [k for k in SEVEN_PARTS_KEYS if not isinstance(seven_parts.get(k), str) or not seven_parts[k].strip()]
    if invalid_parts:
        raise NarrativeMapValidationError(f"narrativeMap.sevenParts has non-string or empty value(s) for {invalid_parts}")

    return nm


def _slugify(url):
    parsed = urlparse(url)
    slug = re.sub(r"[^a-z0-9]+", "_", (parsed.netloc + parsed.path).lower()).strip("_")
    return (slug or "source")[:50]


def fetch_all_sources(company_url, supporting_urls, competitor_urls, progress_cb=lambda *_: None):
    """Returns (sources, source_text_by_id, fetch_failures, company_doc). Raises
    PipelineError only if the company URL itself can't be fetched — a hard failure, never
    retried by anything in this module. Everything else degrades gracefully."""
    progress_cb("fetching_sources")
    sources = []
    source_text_by_id = {}
    fetch_failures = []
    used_ids = set()

    def add_one(url, source_type):
        try:
            fetched = fetch_url(url)
        except FetchError as exc:
            fetch_failures.append({"url": url, "reason": str(exc)})
            return None
        extracted = extract_readable_text(fetched["html"], fetched["final_url"])
        base_id = f"src_live_{_slugify(fetched['final_url'])}"
        source_id = base_id
        n = 2
        while source_id in used_ids:
            source_id = f"{base_id}_{n}"
            n += 1
        used_ids.add(source_id)
        doc = {
            "id": source_id,
            "companyId": "live",
            "title": extracted["title"] or url,
            "publisher": urlparse(fetched["final_url"]).netloc,
            "sourceType": source_type,
            "url": fetched["final_url"],
            "retrievedAt": datetime.now(timezone.utc).isoformat(),
            "permissionStatus": "approved",
        }
        sources.append(doc)
        source_text_by_id[source_id] = extracted["text"]
        if extracted["word_count"] < MIN_WORD_COUNT_WARNING:
            fetch_failures.append({
                "url": url,
                "reason": f"only {extracted['word_count']} words extracted — likely a JavaScript-rendered "
                          f"page with no server-side content; treated as unusable",
            })
        return doc

    company_doc = add_one(company_url, "website")
    if company_doc is None:
        raise PipelineError(f"Could not fetch the company URL ({company_url}); cannot proceed without it.")

    for url in supporting_urls[:MAX_SUPPORTING_URLS]:
        add_one(url, "website")
    for url in competitor_urls[:MAX_COMPETITOR_URLS]:
        add_one(url, "competitor")

    return sources, source_text_by_id, fetch_failures, company_doc


def merge_evidence(pool, new_items, stage_prefix, source_text_by_id, dropped_links_report, rejected_records_report, source_roles_by_id=None, source_types_by_id=None):
    id_map = {}
    valid_items = filter_malformed_records(new_items, EVIDENCE_ITEM_REQUIRED_KEYS, stage_prefix, rejected_records_report, "evidence item")
    for item in valid_items:
        original_id = item["id"]
        new_id = original_id if original_id not in pool else f"{stage_prefix}_{original_id}"
        id_map[original_id] = new_id
        item["id"] = new_id
        source_text = source_text_by_id.get(item["sourceId"], "")
        item["verified"] = excerpt_is_verified(item["excerpt"], source_text)
        # Stamped once, here, at creation — never asked of the model. This is what lets
        # sanitize_links() decide, deterministically and later, whether a "direct"
        # EvidenceLink pointing at this item needs to be downgraded to "company_position"
        # (see sanitize_links's docstring) — a fact about WHERE the evidence came from,
        # not something inferred from the excerpt text itself.
        item["sourceDocumentRole"] = (source_roles_by_id or {}).get(item["sourceId"])
        # Same pattern, same reason: WHERE evidence came from, stamped once, never asked of
        # the model or re-derived downstream. compute_confidence_from_links (confidence.py)
        # uses this to structurally exclude competitor/market-sourced evidence from ever
        # proving a fact about the company being analyzed (rule 9) — even a link the model
        # mislabeled "direct" is excluded, never trusted at face value.
        item["fromCompetitorSource"] = (source_types_by_id or {}).get(item["sourceId"]) == "competitor"
        # EvidenceItem.confidence (schemas.js) is "extraction confidence" — how sure
        # StoryMap is that this excerpt/paraphrase was captured correctly — not the
        # claim's truth (that's the separate statement-level confidence in
        # confidence.py). Every item that reaches this point either verified as an exact
        # substring of the real fetched text (deserves the same honest, non-absolute
        # ceiling as everything else in this app, hence not 1.0) or will be filtered out
        # of the final dataset entirely before it ever reaches the frontend.
        item["confidence"] = EXTRACTION_CONFIDENCE_VERIFIED if item["verified"] else 0.0
        if not item["verified"]:
            dropped_links_report.append({"stage": stage_prefix, "recordId": item["id"], "evidenceId": item["id"], "reason": "evidence excerpt failed server-side verification"})
        pool[new_id] = item
    return id_map


def remap_links(links, id_map):
    for link in links:
        # Malformed entries (not a dict, or missing evidenceId) are silently skipped here
        # and caught+reported by sanitize_links() instead, which runs immediately after
        # remap_links() at every call site — no need to report the same bad item twice.
        if not isinstance(link, dict) or "evidenceId" not in link:
            continue
        if link["evidenceId"] in id_map:
            link["evidenceId"] = id_map[link["evidenceId"]]


COMPANY_POSITION_RELEVANCE = "company_position"


def sanitize_links(record_id, links, pool, stage, dropped_links_report):
    """Citation verification (ev.get("verified")) is checked FIRST and is completely
    unaffected by anything below it — an excerpt that isn't a real substring of its
    source is dropped exactly as before, never reaching the relevance check at all.

    Only after a link survives verification: if the model labeled it "direct" and its
    evidence item came from a source with documentRole "current_draft_narrative" (stamped
    once, at creation, by merge_evidence — never asked of the model), it is deterministically
    downgraded to "company_position" here. This is never trusted to the model — a narrative
    directly stating its own claim is not proof the claim is true, and confidence.py's
    compute_confidence_from_links already only recognizes the literal strings "direct" and
    "partial" as confidence-raising, so "company_position" is automatically excluded from
    ever inflating a statement's confidence, by the exact same mechanism that already
    excludes "context"/"conflicting" — no change needed there. partial/context/conflicting
    links from a current_draft_narrative source are left exactly as the model labeled them;
    only "direct" is ever ambiguous enough to need this."""
    if not isinstance(links, list):
        dropped_links_report.append({"stage": stage, "recordId": record_id, "evidenceId": None, "reason": f"expected a list of evidence links, got {type(links).__name__}"})
        return []
    kept = []
    for link in links:
        if not isinstance(link, dict) or "evidenceId" not in link:
            dropped_links_report.append({
                "stage": stage, "recordId": record_id, "evidenceId": None,
                "reason": f"malformed evidence link: expected an object with evidenceId, got {type(link).__name__} ({str(link)[:120]!r})",
            })
            continue
        eid = link["evidenceId"]
        ev = pool.get(eid)
        if ev is None:
            dropped_links_report.append({"stage": stage, "recordId": record_id, "evidenceId": eid, "reason": "unknown evidenceId — not in evidence pool (fabricated)"})
            continue
        if not ev.get("verified", False):
            dropped_links_report.append({"stage": stage, "recordId": record_id, "evidenceId": eid, "reason": "excerpt failed server-side verification"})
            continue
        if link.get("relevance") == "direct" and ev.get("sourceDocumentRole") == "current_draft_narrative":
            link["relevance"] = COMPANY_POSITION_RELEVANCE
        kept.append(link)
    return kept


# --- Stage-specific per-item processing (unchanged business logic, now factored into ----
# --- named functions so run_analysis(), regenerate_from(), and every retry_xxx() share --
# --- exactly one copy each, per "do not create separate ad hoc checks for each call site")

def process_foundation_response(response, evidence_pool, source_text_by_id, dropped_links_report, rejected_records_report, statement_type_violations, has_current_draft_narrative=False, company_name=None, source_roles_by_id=None, source_types_by_id=None):
    id_map = merge_evidence(evidence_pool, response["evidence"], "f", source_text_by_id, dropped_links_report, rejected_records_report, source_roles_by_id, source_types_by_id)
    kept = []
    raw_choices = filter_malformed_records(response["strategicFoundation"], STRATEGIC_CHOICE_REQUIRED_KEYS, "strategic_foundation", rejected_records_report, "strategic-foundation item")
    for choice in raw_choices:
        remap_links(choice["evidence"], id_map)
        choice["evidence"] = sanitize_links(choice["id"], choice["evidence"], evidence_pool, "strategic_foundation", dropped_links_report)
        action, corrected, violations = validate_strategic_choice(choice)
        statement_type_violations.extend(violations)
        if action == "rejected":
            rejected_records_report.append({"stage": "strategic_foundation", "id": choice.get("id"), "reasons": violations})
            continue
        # narrativeStage (rule 13) — a SEPARATE temporal axis from statementType, checked
        # here rather than in statement_type_check.py (which stays scoped to statementType/
        # type compatibility). Required for every non-"unresolved" item; never inferred from
        # `type` — a model that omits/invents an invalid value is rejected for regeneration,
        # never silently defaulted to a guessed stage.
        if choice["type"] == "unresolved":
            choice["narrativeStage"] = None
        else:
            stage = choice.get("narrativeStage")
            if stage not in NARRATIVE_STAGES:
                rejected_records_report.append({
                    "stage": "strategic_foundation", "id": choice.get("id"),
                    "reasons": [f'"{choice["id"]}" has invalid or missing narrativeStage "{stage}" — rejecting for regeneration'],
                })
                continue
        choice["statementType"] = corrected
        choice["confidence"] = None if choice["type"] == "unresolved" else compute_confidence_from_links(choice["evidence"], evidence_pool)
        choice["directionalCredibility"] = None if choice["type"] == "unresolved" else compute_directional_credibility(choice["evidence"], evidence_pool)
        choice["approvalStatus"] = "unreviewed"
        kept.append(choice)
    # .get() here, not response["narrativeQuestion"] — the tool schema marks this required
    # (anthropic_pipeline.extract_foundation), but that's a prompt-level nudge, never a
    # guarantee; resolve_narrative_question is what makes "undefined" structurally
    # impossible regardless of what the model actually returned.
    narrative_question = resolve_narrative_question(response.get("narrativeQuestion"), has_current_draft_narrative, company_name)
    return kept, narrative_question


def process_diagnosis_response(response, evidence_pool, source_text_by_id, dropped_links_report, rejected_records_report, statement_type_violations, source_roles_by_id=None, source_types_by_id=None):
    id_map = merge_evidence(evidence_pool, response["evidence"], "d", source_text_by_id, dropped_links_report, rejected_records_report, source_roles_by_id, source_types_by_id)
    kept = []
    raw_findings = filter_malformed_records(response["diagnosis"], DIAGNOSIS_FINDING_REQUIRED_KEYS, "diagnosis", rejected_records_report, "diagnosis finding")
    for finding in raw_findings:
        remap_links(finding["evidence"], id_map)
        finding["evidence"] = sanitize_links(finding["id"], finding["evidence"], evidence_pool, "diagnosis", dropped_links_report)
        action, corrected, violations = validate_diagnosis_finding(finding)
        statement_type_violations.extend(violations)
        if action == "rejected":
            rejected_records_report.append({"stage": "diagnosis", "id": finding.get("id"), "reasons": violations})
            continue
        finding["statementType"] = corrected
        finding["confidence"] = compute_confidence_from_links(finding["evidence"], evidence_pool)
        kept.append(finding)
    # No item-level evidence citation is collected for competitor contrasts in this
    # implementation — a comparative judgment across two sets of pages, not a single
    # sourced claim. statementType is forced here, not trusted from the model, so it's
    # never displayed as a sourced fact regardless of how the model phrased the text.
    raw_contrasts = filter_malformed_records(response.get("competitorContrasts", []), COMPETITOR_CONTRAST_REQUIRED_KEYS, "diagnosis", rejected_records_report, "competitor contrast")
    competitor_contrasts = [{**c, "evidence": [], "statementType": "storymap_inference"} for c in raw_contrasts]
    return kept, competitor_contrasts


def process_narrative_stage_entries(candidate_id, raw_entries, evidence_pool, dropped_links_report, rejected_records_report):
    """Validates and sanitizes a candidate's narrativeStages array (rationale/evidence-layer
    data — see NARRATIVE_STAGE_ENTRY_REQUIRED_KEYS). Individual malformed/invalid-stage
    entries are dropped and reported, never coerced — this never rejects the whole
    candidate; an empty result just means no stage-mix summary is available for it."""
    raw = filter_malformed_records(raw_entries, NARRATIVE_STAGE_ENTRY_REQUIRED_KEYS, "candidates", rejected_records_report, "narrative-stage entry")
    kept = []
    for entry in raw:
        if entry.get("stage") not in NARRATIVE_STAGES:
            rejected_records_report.append({
                "stage": "candidates", "id": candidate_id,
                "reasons": [f'narrativeStages entry has invalid stage "{entry.get("stage")}" — dropped'],
            })
            continue
        entry["evidence"] = sanitize_links(candidate_id, entry["evidence"], evidence_pool, "candidates", dropped_links_report)
        kept.append(entry)
    return kept


def process_candidates_response(response, evidence_pool, dropped_links_report, rejected_records_report):
    candidates = filter_malformed_records(response["candidates"], CANDIDATE_REQUIRED_KEYS, "candidates", rejected_records_report, "narrative candidate")
    if len(candidates) != 3:
        rejected_records_report.append({"stage": "candidates", "id": None, "reasons": [f"expected exactly 3 candidates, got {len(candidates)}"]})
    for cand in candidates:
        cand["claims"] = sanitize_links(cand["id"], cand["claims"], evidence_pool, "candidates", dropped_links_report)
        cand["narrativeStages"] = process_narrative_stage_entries(cand["id"], cand["narrativeStages"], evidence_pool, dropped_links_report, rejected_records_report)
        cand["status"] = CANDIDATE_STATUS_PENDING
        cand["gateResults"] = []
        cand["rejectionReasons"] = []
        cand["statusEvaluatedAtStage"] = "narrative_choices"
        cand["statusUpdatedAt"] = now_iso()
    return candidates


class DirectionCoverageError(ValueError):
    """Raised when the strategic foundation shows credible evidence of company movement
    (an emerging/in_build/strategic_direction item) but none of the 3 generated candidates
    include a company-level direction claim (an in_build/strategic_direction/
    aspiration_pending_leadership entry in their own narrativeStages) — see rule 13 and
    generate_candidates' "DIRECTION COVERAGE" instruction. Caught by the same attempt/retry
    machinery as every other stage-specific validation failure (ATTEMPT_EXCEPTIONS), so this
    costs a retry with the reason fed back to the model, not a crash. Never raised when the
    foundation itself shows no movement — nothing to require direction coverage against."""
    pass


def check_direction_coverage(strategic_foundation, candidates):
    has_movement_evidence = any(
        c.get("type") != "unresolved" and c.get("narrativeStage") in DIRECTION_COVERAGE_FOUNDATION_STAGES
        for c in strategic_foundation
    )
    if not has_movement_evidence:
        return
    has_direction_candidate = any(
        any(entry.get("stage") in CANDIDATE_DIRECTION_STAGES for entry in (cand.get("narrativeStages") or []))
        for cand in candidates
    )
    if not has_direction_candidate:
        raise DirectionCoverageError(
            "The strategic foundation shows credible evidence of company movement "
            "(emerging/in_build/strategic_direction items exist), but none of the 3 "
            "candidates include a company-level in_build/strategic_direction/"
            "aspiration_pending_leadership claim in their narrativeStages. At least one "
            "candidate must be a genuine direction story — where the company is going — "
            "not only current-state reflections."
        )


def process_critique_response(response, candidates, rejected_records_report):
    """Sets each candidate's status/gateResults/rejectionReasons exactly once — this is the
    FIRST and ONLY time a candidate's evaluated-viability is ever written (see decision 1:
    process_recommend_and_map_response never touches candidate status again, it only
    records the winner separately in recommendation.selectedCandidateId)."""
    raw_critiques = filter_malformed_records(response["critiques"], CRITIQUE_REQUIRED_KEYS, "critique", rejected_records_report, "critique")
    gates_by_id = {c["candidateId"]: c for c in raw_critiques}
    survivors, rejected = [], []
    for cand in candidates:
        gate = gates_by_id.get(cand["id"])
        if gate is None:
            rejected_records_report.append({"stage": "critique", "id": cand["id"], "reasons": ["no critique returned for this candidate"]})
            cand["status"] = CANDIDATE_STATUS_REJECTED
            cand["scores"] = {"Strategic fit": 1, "Differentiation": 1, "Evidence strength": 1, "Company altitude": 1}
            cand["criticFindings"] = ["No critique was returned for this candidate — treated as failing."]
            cand["gateResults"] = []
            cand["rejectionReasons"] = [{"code": "no_critique_returned", "gateId": None, "explanation": "No critique was returned for this candidate — treated as failing."}]
            cand["statusEvaluatedAtStage"] = "critique"
            cand["statusUpdatedAt"] = now_iso()
            rejected.append(cand)
            continue
        cand["scores"], cand["status"], cand["gateResults"], cand["rejectionReasons"] = build_candidate_scores_and_status(gate)
        cand["criticFindings"] = gate["findings"]
        cand["statusEvaluatedAtStage"] = "critique"
        cand["statusUpdatedAt"] = now_iso()
        (rejected if cand["status"] == CANDIDATE_STATUS_REJECTED else survivors).append(cand)
    return candidates, survivors


def process_recommend_and_map_response(response, survivors, all_candidates, evidence_pool, dropped_links_report, rejected_records_report, map_id, map_version):
    winner_id = response["recommendedCandidateId"]
    survivor_ids = {c["id"] for c in survivors}
    if winner_id not in survivor_ids:
        raise RecommendationValidationError(
            f"recommendedCandidateId {winner_id!r} does not reference a candidate that survived critique"
        )
    # Candidate status/gateResults/rejectionReasons are never rewritten here — they were
    # set once, at critique (see process_critique_response), and stay exactly as they were.
    # Selection is recorded only in the caller's recommendation.selectedCandidateId; a
    # selected candidate remains structurally "viable" (decision 1).
    why_others = response["whyOthersNotSelected"]
    detail = {
        "candidateId": winner_id,
        "recommendedDecision": response["recommendedDecision"],
        "whyItWins": response["whyItWins"],
        "whyCustomersCare": response["whyCustomersCare"],
        "whyCredible": response["whyCredible"],
        "howDifferent": response["howDifferent"],
        "missingEvidence": response["missingEvidence"],
        "tradeoffs": response["tradeoffs"],
        "whyOthersNotSelected": why_others if isinstance(why_others, dict) else {},
    }
    audiences = filter_malformed_records(response["audiences"], AUDIENCE_REQUIRED_KEYS, "recommendation_and_map", rejected_records_report, "audience")
    nm = response["narrativeMap"]
    # validate_stage_response already confirmed "narrativeMap" is a dict at the envelope
    # level; this is the DEEPER, stage-unique check (all seven parts present as non-empty
    # strings) — the class of check "do not create ad hoc checks unless genuinely unique"
    # explicitly allows keeping separate from the generic envelope validator.
    validate_narrative_map_shape(nm)
    raw_core_claims = filter_malformed_records(nm["coreClaims"], CORE_CLAIM_REQUIRED_KEYS, "narrative_map", rejected_records_report, "core claim")
    core_claims = []
    for claim in raw_core_claims:
        if claim.get("narrativeStage") not in NARRATIVE_STAGES:
            rejected_records_report.append({
                "stage": "narrative_map", "id": claim.get("id"),
                "reasons": [f'core claim has invalid or missing narrativeStage "{claim.get("narrativeStage")}" — dropped'],
            })
            continue
        claim["evidence"] = sanitize_links(claim["id"], claim["evidence"], evidence_pool, "narrative_map", dropped_links_report)
        core_claims.append(claim)
    narrative_map = {
        "id": map_id,
        "companyId": "live",
        "version": map_version,
        "status": "draft",
        "candidateId": winner_id,
        "coreNarrative": nm["coreNarrative"],
        "sevenParts": nm["sevenParts"],
        "coreClaims": core_claims,
        "audienceIds": [],
        "competitorContrastIds": [],
        "likelyObjections": nm["likelyObjections"],
        "weakOrUnsupportedClaims": nm["weakOrUnsupportedClaims"],
        "unresolvedQuestions": nm["unresolvedQuestions"],
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    return detail, narrative_map, audiences


# --- Generic stage-attempt / stage-retry machinery ---------------------------------------

# Only response-shape/validation failures are ever retried — a real Anthropic SDK
# exception (auth, network, rate limit) is NOT in this tuple and propagates immediately,
# uncaught, exactly like PipelineError does. That is what makes "do not retry hard
# failures" true by construction rather than by a separate check.
ATTEMPT_EXCEPTIONS = (StageResponseError, KeyError, TypeError, StopIteration, NarrativeMapValidationError, RecommendationValidationError, DirectionCoverageError)


def _attempt_stage_once(stage_name, required_schema, api_call_fn, process_fn, usage, prior_failure):
    """Exactly one real attempt: call the model, validate the envelope, process it.
    Never retries itself. api_call_fn takes one argument, prior_failure (None on a first
    attempt). Returns (result, outcome, error_info, traceback, this_attempt_usage) —
    outcome is "success" or "failed"; this_attempt_usage is the single usage.calls entry
    this specific attempt produced (or None if the call never completed at all)."""
    calls_before = len(usage.calls)
    try:
        response = api_call_fn(prior_failure)
        validate_stage_response(stage_name, response, required_schema)
        result = process_fn(response)
    except ATTEMPT_EXCEPTIONS as exc:
        tb = traceback.format_exc()
        this_attempt_usage = usage.calls[-1] if len(usage.calls) > calls_before else None
        error_info = {"validation_error": str(exc), "field": getattr(exc, "field", None)}
        return None, "failed", error_info, tb, this_attempt_usage
    this_attempt_usage = usage.calls[-1] if len(usage.calls) > calls_before else None
    return result, "success", None, None, this_attempt_usage


def build_attempt_record(stage, attempt_number, manual, started_at, completed_at, outcome, validation_failure, attempt_usage):
    """The one shape every attempt at every stage is recorded in — automatic (inside
    run_model_stage) and manual (jobs.py, after calling a retry_xxx() function) alike —
    so a job's full retry history is uniform regardless of which path produced it. Carries
    everything the approved retry policy requires persisted per attempt: stage, attempt
    number, start/completion time, outcome, the exact validation failure (if any), token
    usage, and cost derived from that usage (never model-reported, never guessed)."""
    return {
        "stage": stage,
        "attempt": attempt_number,
        "manual": manual,
        "startedAt": started_at,
        "completedAt": completed_at,
        "outcome": outcome,
        "validationFailure": validation_failure,
        "usage": attempt_usage,
        "costUsd": compute_cost(attempt_usage) if attempt_usage else None,
    }


def run_model_stage(stage_name, required_schema, api_call_fn, process_fn, usage, progress_cb=lambda *_: None):
    """Automatic in-line retry: up to MAX_TOTAL_ATTEMPTS total attempts for this stage
    within THIS run, each one telling the model the exact validation failure from the
    previous attempt (never a blind identical repeat). Returns
    (result, outcome, stage_failure, traceback, attempts) where outcome is "success" or
    "stage_failed". On stage_failed, stage_failure is a structured dict:
    {stage, validation_error, field, retry_eligible, attempts, total_attempts} — a human
    can still trigger one further MANUAL retry later via the dedicated retry_xxx()
    function/endpoint, tracked completely separately from this automatic loop (and capped
    independently — see MAX_MANUAL_RETRIES).
    """
    progress_cb(stage_name)
    attempts = []
    prior_failure = None
    for attempt_number in range(1, MAX_TOTAL_ATTEMPTS + 1):
        started_at = now_iso()
        result, outcome, error_info, tb, attempt_usage = _attempt_stage_once(
            stage_name, required_schema, api_call_fn, process_fn, usage, prior_failure
        )
        completed_at = now_iso()
        if outcome == "failed":
            attempts.append(build_attempt_record(
                stage_name, attempt_number, False, started_at, completed_at,
                "failed", error_info["validation_error"], attempt_usage,
            ))
            prior_failure = error_info["validation_error"]
            if attempt_number == MAX_TOTAL_ATTEMPTS:
                stage_failure = {
                    "stage": stage_name,
                    "validation_error": error_info["validation_error"],
                    "field": error_info["field"],
                    "retry_eligible": True,
                    "attempts": attempts,
                    "total_attempts": attempt_number,
                }
                return None, "stage_failed", stage_failure, tb, attempts
            continue
        attempts.append(build_attempt_record(
            stage_name, attempt_number, False, started_at, completed_at, "success", None, attempt_usage,
        ))
        return result, "success", None, None, attempts


# Declares what each stage needs to already have succeeded before it can run — used both
# to decide what a manual retry_xxx() needs as input, and (via check_upstream_stages_valid)
# to reject a retry request up front when the checkpoint it would run against doesn't
# actually have valid upstream data.
STAGE_ORDER = ["fetching_sources", "strategic_foundation", "diagnosis", "narrative_choices", "critique", "recommendation_and_map"]
STAGE_DEPENDENCIES = {
    "strategic_foundation": ["fetching_sources"],
    "diagnosis": ["fetching_sources", "strategic_foundation"],
    "narrative_choices": ["fetching_sources", "strategic_foundation", "diagnosis"],
    "critique": ["fetching_sources", "strategic_foundation", "diagnosis", "narrative_choices"],
    "recommendation_and_map": ["fetching_sources", "strategic_foundation", "diagnosis", "narrative_choices", "critique"],
}


def check_upstream_stages_valid(checkpoint, stage_name):
    """Returns (True, None) if every stage `stage_name` depends on is present in
    `checkpoint` and (for model stages) completed with outcome "success". Returns
    (False, reason) otherwise — a retry endpoint must check this BEFORE spending any
    money attempting a stage whose real inputs don't actually exist yet."""
    if checkpoint is None:
        return False, "no job state found — nothing to retry from"
    for dep in STAGE_DEPENDENCIES.get(stage_name, []):
        section = checkpoint.get(dep)
        if section is None:
            return False, f'upstream stage "{dep}" has not been completed yet'
        if dep != "fetching_sources" and section.get("outcome") != "success":
            return False, f'upstream stage "{dep}" did not complete successfully (outcome={section.get("outcome")!r})'
    return True, None


def check_manual_retry_allowed(checkpoint, stage_name):
    """Returns (True, None) if this stage has used fewer than MAX_MANUAL_RETRIES manual
    (human-triggered) attempts so far — automatic in-run attempts (run_model_stage, up to
    MAX_TOTAL_ATTEMPTS, never flagged "manual") never count against this cap. Returns
    (False, "retry_limit_reached") once the cap is used, regardless of whether that one
    manual attempt succeeded or failed. Returns (False, "retry_in_progress") if a manual
    retry for this exact stage has already been RESERVED (pendingManualRetry — see
    jobs.py's create_retry_job, which sets this atomically under a per-job lock at
    enqueue time, before the attempt actually runs) and hasn't finished yet — this is
    what makes two concurrent requests for the same stage resolve to only one queued
    retry: whichever acquires the job lock second sees this flag already set. A caller
    must check this BEFORE spending anything on a further manual retry of the same
    stage."""
    section = (checkpoint or {}).get(stage_name) or {}
    if section.get("pendingManualRetry"):
        return False, "retry_in_progress"
    manual_attempts = [a for a in section.get("attempts", []) if a.get("manual")]
    if len(manual_attempts) >= MAX_MANUAL_RETRIES:
        return False, "retry_limit_reached"
    return True, None


# A user may trigger this many DELIBERATE full regenerations (edit the foundation, rerun
# diagnosis onward) per job. A validation failure of the submitted edit never reaches
# check_regeneration_allowed's caller's increment step — see jobs.create_regenerate_job —
# so a rejected edit costs nothing against this allowance.
MAX_FULL_REGENERATIONS = 2


def check_regeneration_allowed(checkpoint):
    """Returns (True, None) if this job has used fewer than MAX_FULL_REGENERATIONS full
    regenerations so far (checkpoint["regenerationCount"], persisted server-side — never
    trusted from a client). Returns (False, "regeneration_limit_reached") once the cap is
    used. A caller must check this BEFORE validating/accepting a new edited foundation,
    so a request that would be rejected anyway never even reaches the (cheap but
    non-zero) validation step."""
    count = (checkpoint or {}).get("regenerationCount", 0)
    if count >= MAX_FULL_REGENERATIONS:
        return False, "regeneration_limit_reached"
    return True, None


# A user may trigger this many DELIBERATE "add sources and re-analyze" actions per job —
# tracked SEPARATELY from MAX_FULL_REGENERATIONS/regenerationCount, even though both are
# "full redo" actions capped at the same count today. Reasoning: expand-sources (re-fetch
# + all 5 stages) and regenerate (no fetch, 4 stages, foundation held fixed) solve
# different problems — adding missing source coverage vs. editing foundation content —
# and the motivating scenario (a thin-sourced company, e.g. the real Schneider Electric
# run) is exactly the case where a user wants budget for BOTH independently. A shared cap
# would mean using both regenerate slots on foundation edits leaves zero budget to fix
# the actual sourcing problem this feature exists to solve.
MAX_SOURCE_EXPANSIONS = 2


def check_source_expansion_allowed(checkpoint):
    """Returns (True, None) if this job has used fewer than MAX_SOURCE_EXPANSIONS
    expand-sources actions so far (checkpoint["expandSourcesCount"], persisted
    server-side — never trusted from a client). Returns
    (False, "source_expansion_limit_reached") once the cap is used. Checked BEFORE
    re-fetching anything, so a request that would be rejected anyway never spends a
    single network call, let alone an API call."""
    count = (checkpoint or {}).get("expandSourcesCount", 0)
    if count >= MAX_SOURCE_EXPANSIONS:
        return False, "source_expansion_limit_reached"
    return True, None


SOURCE_COVERAGE_DIMENSIONS = ["strategy", "capabilities", "customers", "proof", "competitive_context", "current_narrative"]

# Maps each dimension to a concrete, actionable suggestion — what source TYPE would close
# that specific gap, per the explicit requirement that a user be shown exactly which
# dimensions are missing and what would fix each one (never just "add more sources").
SOURCE_COVERAGE_SUGGESTIONS = {
    "strategy": 'Add a page describing the company\'s strategy, investor relations, or market positioning — or fill in "existing narrative".',
    "capabilities": "Add a products, solutions, or capabilities page.",
    "customers": "Add a customers, case-studies, or testimonials page.",
    "proof": "Add a page with concrete proof points — certifications, press coverage, awards, or measured outcomes.",
    "competitive_context": "Add at least one competitor URL.",
    "current_narrative": 'Add an about/positioning page beyond the homepage, or fill in "existing narrative".',
}

# sufficient requires BOTH a floor on dimension coverage AND a floor on raw source count —
# the count floor alone is what correctly flags the real Schneider Electric run (a single
# homepage) as insufficient regardless of how its one page happens to be classified.
MIN_COVERED_DIMENSIONS_FOR_SUFFICIENT = 4
MIN_SOURCES_FOR_SUFFICIENT = 2


def assess_source_coverage(sources, strategic_foundation, evidence_pool, existing_narrative):
    """Deterministic, zero-cost, no-model-call assessment of whether the fetched source
    set is broad enough to support a definitive company-level recommendation, or only a
    narrower exploratory hypothesis. Never blocks or alters recommendation/narrative-map
    CONTENT — this only ever adds an additional honesty signal a caller (jobs.py, and
    ultimately the frontend) uses to decide whether to present the result as a
    "Recommendation" or an "Exploratory Narrative Hypothesis." Every existing evidence/
    classification/recommendation gate stays exactly as strict as it already is; this is
    purely an additive signal on top.

    Six dimensions, each answerable purely from data the pipeline already extracted (no
    new model call, no new fetch):
      strategy             — >=1 foundation item typed market/market_change/way_to_win,
                              OR existingNarrative given
      capabilities         — >=1 foundation item typed capability
      customers            — >=1 foundation item typed customer
      proof                — >=1 foundation item typed proof, OR >=1 verified evidence
                              item with strength strong/moderate
      competitive_context  — >=1 fetched source with sourceType == competitor
      current_narrative    — existingNarrative given, OR >=2 total sources fetched (more
                              than just the bare homepage)

    sufficient = at least MIN_COVERED_DIMENSIONS_FOR_SUFFICIENT of 6 dimensions covered,
    AND at least MIN_SOURCES_FOR_SUFFICIENT sources fetched.
    """
    foundation_types = {item.get("type") for item in strategic_foundation if isinstance(item, dict)}
    has_existing_narrative = bool((existing_narrative or "").strip())
    competitor_source_count = sum(1 for s in sources if isinstance(s, dict) and s.get("sourceType") == "competitor")
    has_strong_or_moderate_evidence = any(
        isinstance(e, dict) and e.get("verified") and e.get("strength") in ("strong", "moderate")
        for e in (evidence_pool or {}).values()
    )

    covered = set()
    if ({"market", "market_change", "way_to_win"} & foundation_types) or has_existing_narrative:
        covered.add("strategy")
    if "capability" in foundation_types:
        covered.add("capabilities")
    if "customer" in foundation_types:
        covered.add("customers")
    if "proof" in foundation_types or has_strong_or_moderate_evidence:
        covered.add("proof")
    if competitor_source_count >= 1:
        covered.add("competitive_context")
    if has_existing_narrative or len(sources) >= 2:
        covered.add("current_narrative")

    missing = [d for d in SOURCE_COVERAGE_DIMENSIONS if d not in covered]
    sufficient = len(covered) >= MIN_COVERED_DIMENSIONS_FOR_SUFFICIENT and len(sources) >= MIN_SOURCES_FOR_SUFFICIENT

    return {
        "coveredDimensions": [d for d in SOURCE_COVERAGE_DIMENSIONS if d in covered],
        "missingDimensions": missing,
        "sufficient": sufficient,
        "suggestions": {d: SOURCE_COVERAGE_SUGGESTIONS[d] for d in missing},
    }


def invalidate_downstream_stages(checkpoint, from_stage):
    """Returns a NEW checkpoint dict with every stage strictly after `from_stage` (per
    STAGE_ORDER) replaced wholesale with an {"outcome": "invalidated", ...} marker — no
    leftover data fields survive from the old section. Used exactly once, right after a
    user submits an edited foundation: the edit makes every already-computed downstream
    stage (diagnosis, narrative choices, critique, recommendation/map) stale, and a full
    replacement (not a merge) is what guarantees _dataset_from_checkpoint can never
    surface old data alongside the new foundation, even if the subsequent regenerate run
    fails partway through and never gets to overwrite these sections with fresh output.
    check_upstream_stages_valid() already treats any outcome other than "success" as
    invalid, so "invalidated" correctly blocks a stale-relative retry of anything
    downstream until it actually reruns.
    """
    checkpoint = dict(checkpoint)
    try:
        start_index = STAGE_ORDER.index(from_stage)
    except ValueError:
        raise ValueError(f"Unknown stage: {from_stage!r}")
    invalidated_at = now_iso()
    for stage in STAGE_ORDER[start_index + 1:]:
        if stage in checkpoint:
            checkpoint[stage] = {
                "outcome": "invalidated",
                "invalidatedAt": invalidated_at,
                "reason": f'upstream stage "{from_stage}" was edited/regenerated',
            }
    return checkpoint


def validate_edited_foundation(items):
    """Validates a user-submitted editedFoundation payload before it's ever accepted as
    the new canonical strategic_foundation for a job. Unlike model output — which is
    filtered item-by-item and silently drops malformed records — user input is rejected
    outright on ANY problem (never partially applied), so an edit either takes effect
    exactly as submitted or not at all. Checks the same shape (STRATEGIC_CHOICE_REQUIRED_KEYS)
    filter_malformed_records enforces on model output, PLUS the same semantic validity
    (validate_strategic_choice) a model-generated choice has to pass — a user edit can
    just as easily produce an internally inconsistent record (e.g. type="unresolved" with
    statementType="source_fact") as a model can.

    Returns None if valid, or a non-empty list of human-readable problem strings if not.
    """
    if not isinstance(items, list) or not items:
        return ["editedFoundation must be a non-empty array"]
    problems = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            problems.append(f"item {i}: expected an object, got {type(item).__name__}")
            continue
        missing = [k for k in STRATEGIC_CHOICE_REQUIRED_KEYS if k not in item]
        if missing:
            problems.append(f"item {i} (id={item.get('id')!r}): missing required field(s) {missing}")
            continue
        action, _corrected, violations = validate_strategic_choice(item)
        if action == "rejected":
            problems.append(f"item {i} (id={item.get('id')!r}): {'; '.join(violations)}")
    return problems or None


def _diagnostics_for_outcome(outcome, stage_failure, extra):
    failed_stage = stage_failure["stage"] if stage_failure else None
    failure_reason = stage_failure["validation_error"] if stage_failure else None
    critical_failure = None
    if outcome == "no_candidate_passed":
        critical_failure = "no_candidate_passed"
    elif outcome == "stage_failed":
        critical_failure = f"{failed_stage}_stage_failed: {failure_reason}"
    base = {
        "outcome": outcome,
        "failed_stage": failed_stage,
        "failure_reason": failure_reason,
        "stage_failure": stage_failure,
        "critical_failure": critical_failure,
    }
    base.update(extra)
    return base


def build_case_context(company_doc):
    """The one place this dict is ever built — shared by run_analysis() (fresh job) and
    jobs.py's expand-sources dispatch (re-fetch for an existing job), so a job's
    caseContext is always constructed identically regardless of which path produced it."""
    return {
        "id": "live",
        "selectorLabel": "Analyze a company",
        "selectorDescription": "Run StoryMap's analysis on a real, publicly available company you choose.",
        "company": {"name": company_doc["title"] or company_doc["publisher"], "oneLiner": ""},
    }


PASTED_NARRATIVE_SOURCE_ID = "src_pasted_narrative"


def sources_with_pasted_narrative(sources, source_text_by_id, existing_narrative):
    """Folds pasted "Existing narrative" text into `sources`/`source_text_by_id` as a
    synthetic source shaped exactly like an uploaded document with documentRole
    "current_draft_narrative" — unifying pasted-text and uploaded-file treatment so every
    downstream prompt/rule (role tagging in _format_sources, SYSTEM_RULES rule 11,
    narrativeQuestion derivation) handles both identically, with zero special-casing
    anywhere else. A no-op when existing_narrative is empty/whitespace, or when a source
    with this synthetic id is already present (idempotent — safe to call again on every
    entry point, including regenerate/retry paths that reuse an already-injected checkpoint,
    without ever double-inserting).

    Called at every place `sources`/`source_text_by_id` get assembled from a fresh state
    (run_analysis, jobs.py's expand-sources dispatch) so the pseudo-source is durably
    persisted into fetching_sources (and so visible in the Evidence Room, labeled "Internal
    company document — Current draft corporate narrative", exactly like an uploaded file).
    Also called defensively in regenerate_from/retry_extract_foundation/retry_diagnose,
    which normally just reuse an already-injected checkpoint's sources — a cheap no-op
    there today, but a safety net against ever silently losing role-awareness if a future
    caller passes sources that were never injected."""
    text = (existing_narrative or "").strip()
    if not text or any(s.get("id") == PASTED_NARRATIVE_SOURCE_ID for s in sources):
        return sources, source_text_by_id
    pseudo_source = {
        "id": PASTED_NARRATIVE_SOURCE_ID,
        "companyId": "live",
        "title": "Pasted existing narrative",
        "publisher": "User-supplied",
        "sourceType": "internal",
        "documentRole": "current_draft_narrative",
        "retrievedAt": now_iso(),
        "permissionStatus": "approved",
    }
    return sources + [pseudo_source], {**source_text_by_id, PASTED_NARRATIVE_SOURCE_ID: text}


# Values a model might emit that are technically non-empty strings but are placeholders,
# not real questions — checked in addition to the missing/None/wrong-type/empty cases so
# "never render ... an internal key" (the exact wording of the bug report) is covered too.
_INVALID_NARRATIVE_QUESTION_VALUES = {"undefined", "null", "none", "n/a", "na", "tbd", "narrativequestion", ""}


def resolve_narrative_question(raw_value, has_current_draft_narrative, company_name):
    """The ONE place a bad narrativeQuestion ever gets fixed, regardless of exactly how it
    was bad: missing (raw_value is None from response.get()), null (None from real JSON
    null), malformed (wrong type — int/list/dict), empty ("" or whitespace-only), or a
    placeholder-looking string a model sometimes emits instead of a real answer. Never
    returns anything falsy or placeholder-shaped — always a real, human-readable question."""
    if isinstance(raw_value, str):
        cleaned = raw_value.strip()
        if cleaned and cleaned.lower() not in _INVALID_NARRATIVE_QUESTION_VALUES:
            return cleaned
    name = company_name or "this company"
    if has_current_draft_narrative:
        return f"Is {name}'s current narrative the clearest, most credible way to describe what it does — and what would make it stronger?"
    return f"What should {name} be known for, based on what's publicly verifiable?"


def run_analysis(company_url, supporting_urls, competitor_urls, existing_narrative, progress_cb=lambda *_: None, persist_cb=lambda *_: None, uploaded_sources=(), uploaded_source_text_by_id=None):
    """Fetches sources for the FIRST time for a brand new job, then hands off to
    run_pipeline_from_sources() for everything from strategic_foundation onward — the two
    are split apart specifically so a second caller (jobs.py's expand-sources dispatch,
    which re-fetches an EXPANDED source set for an EXISTING job) can reuse the exact same
    stage sequence rather than re-implementing it a second time. See
    run_pipeline_from_sources()'s docstring for the full behavior contract (partial
    results preserved on failure, persist_cb per stage, etc.) — this function's own
    contract is identical, it just also owns the initial fetch.

    uploaded_sources/uploaded_source_text_by_id: already-validated, already-extracted
    internal .docx documents (sourceType "internal" — see document_extractor.py and
    jobs.py's "analyze" dispatch), shaped exactly like fetch_all_sources()'s own return
    values and merged in here, BEFORE run_pipeline_from_sources() is ever called. Default
    empty, so every existing caller (run_basecamp_test.py, every pre-upload test, an
    analyze job with no uploaded documents) is completely unaffected. Merging at this one
    point — rather than teaching run_pipeline_from_sources() or anything downstream about
    file uploads — is what keeps every stage prompt, citation check, evidence merge, and
    confidence computation identical regardless of whether a source came from a URL or a
    file; none of that code ever needs to know the difference.
    """
    sources, source_text_by_id, fetch_failures, company_doc = fetch_all_sources(
        company_url, supporting_urls, competitor_urls, progress_cb
    )
    case_context = build_case_context(company_doc)
    combined_sources = sources + list(uploaded_sources)
    combined_source_text_by_id = {**source_text_by_id, **(uploaded_source_text_by_id or {})}
    # Pasted "Existing narrative" text gets the exact same role-aware treatment as an
    # uploaded document with documentRole "current_draft_narrative" — see
    # sources_with_pasted_narrative's docstring. Injected here (before persist_cb) so the
    # Evidence Room sees it too, not just the model prompts.
    combined_sources, combined_source_text_by_id = sources_with_pasted_narrative(combined_sources, combined_source_text_by_id, existing_narrative)
    # sourceTextById is persisted here (not re-derivable from `sources` alone) so a later
    # manual retry of any downstream stage can rebuild its exact model inputs without
    # re-fetching a single URL (or re-parsing an uploaded file). caseContext is persisted
    # here too — it's otherwise never stored anywhere durable, which would silently break
    # dataset reconstruction from a checkpoint after a restart.
    persist_cb("fetching_sources", {
        "sources": combined_sources, "sourceTextById": combined_source_text_by_id,
        "fetchFailures": fetch_failures, "caseContext": case_context,
    })
    return run_pipeline_from_sources(combined_sources, combined_source_text_by_id, existing_narrative, case_context, fetch_failures, progress_cb, persist_cb)


def run_pipeline_from_sources(sources, source_text_by_id, existing_narrative, case_context, fetch_failures=(), progress_cb=lambda *_: None, persist_cb=lambda *_: None):
    """Runs strategic_foundation through recommendation_and_map against an ALREADY-fetched
    source set — the one place this 5-stage sequence is ever implemented (per this
    module's own long-standing design principle: "this is the one place the actual
    pipeline logic lives; neither caller re-implements it"). Two callers: run_analysis()
    (immediately after its own fresh fetch, for a brand new job) and jobs.py's
    expand-sources dispatch (after ITS OWN fresh re-fetch of an expanded URL set, for an
    EXISTING job whose downstream stages were just invalidated). regenerate_from() is
    deliberately NOT built on this — it holds strategic_foundation fixed at a user's edit
    and only reruns diagnosis onward, a genuinely different entry point.

    Every successful stage's validated output is handed to persist_cb(stage_name,
    section_dict) immediately — see job_persistence.py for the real disk-backed
    implementation jobs.py wires in; tests pass a no-op or a recording stub. Returns
    {dataset, diagnostics, context, debug_traceback}. dataset always contains whatever
    stages succeeded, even when a later stage fails.
    """
    client = pipe.get_client()

    def on_usage_call(entry, totals):
        persist_cb("usage", {"latestCall": entry, "totals": totals, "costUsd": compute_cost(totals)})

    usage = pipe.UsageTracker(on_call=on_usage_call)
    dropped_links_report = []
    statement_type_violations = []
    rejected_records_report = []
    fetch_failures = list(fetch_failures)  # the caller's own fetch results — never re-derived here

    # Defensive/idempotent: the primary injection already happened in run_analysis/jobs.py's
    # expand-sources dispatch (before fetching_sources was persisted, so the Evidence Room
    # sees it too) — this is a no-op in that case. See sources_with_pasted_narrative's
    # docstring for why it's safe and correct to call again here regardless.
    sources, source_text_by_id = sources_with_pasted_narrative(sources, source_text_by_id, existing_narrative)

    non_competitor = [{"id": s["id"], "text": source_text_by_id[s["id"]], "role": s.get("documentRole")} for s in sources if s["sourceType"] != "competitor"]
    competitor_sources = [{"id": s["id"], "text": source_text_by_id[s["id"]], "role": s.get("documentRole")} for s in sources if s["sourceType"] == "competitor"]
    has_current_draft_narrative = any(s.get("role") == "current_draft_narrative" for s in non_competitor)
    company_name = (case_context or {}).get("company", {}).get("name")
    source_roles_by_id = {s["id"]: s.get("documentRole") for s in sources}
    source_types_by_id = {s["id"]: s.get("sourceType") for s in sources}

    context = {"sources": sources, "source_text_by_id": source_text_by_id, "evidence_pool": {}}

    def _empty_return(outcome, stage_failure, tb, strategic_foundation, diagnosis, candidates, competitor_contrasts, recommendation, narrative_map, audiences, evidence_pool):
        context["evidence_pool"] = evidence_pool
        unverified_evidence = [e for e in evidence_pool.values() if not e.get("verified")]
        fabricated_by_stage = {}
        for entry in dropped_links_report:
            if "fabricated" in entry["reason"]:
                fabricated_by_stage[entry["stage"]] = fabricated_by_stage.get(entry["stage"], 0) + 1
        diagnostics = _diagnostics_for_outcome(outcome, stage_failure, {
            "fetch_failures": fetch_failures,
            "dropped_links": dropped_links_report,
            "fabricated_evidence_ids_by_stage": fabricated_by_stage,
            "unverified_evidence_count": len(unverified_evidence),
            "statement_type_violations": statement_type_violations,
            "rejected_records": rejected_records_report,
            "api_calls": usage.calls,
            "token_totals": usage.totals(),
        })
        dataset = {
            "caseContext": case_context,
            "sources": sources,
            "evidence": [e for e in evidence_pool.values() if e.get("verified")],
            "strategicFoundation": strategic_foundation,
            "diagnosis": diagnosis,
            "candidates": candidates,
            "recommendation": recommendation,
            "narrativeMap": narrative_map,
            "audiences": audiences,
            "competitorContrasts": competitor_contrasts,
        }
        return {"dataset": dataset, "diagnostics": diagnostics, "context": context, "debug_traceback": tb}

    evidence_pool = {}
    context["evidence_pool"] = evidence_pool

    # --- Stage: strategic_foundation ---
    foundation_result, outcome, stage_failure, tb, attempts = run_model_stage(
        "strategic_foundation", FOUNDATION_RESPONSE_SCHEMA,
        lambda pf: pipe.extract_foundation(client, usage, non_competitor, prior_failure=pf),
        lambda response: process_foundation_response(response, evidence_pool, source_text_by_id, dropped_links_report, rejected_records_report, statement_type_violations, has_current_draft_narrative, company_name, source_roles_by_id, source_types_by_id),
        usage, progress_cb,
    )
    if outcome == "stage_failed":
        persist_cb("strategic_foundation", {"outcome": outcome, "attempts": attempts})
        return _empty_return(outcome, stage_failure, tb, [], [], [], [], None, None, [], evidence_pool)
    strategic_foundation, narrative_question = foundation_result
    persist_cb("strategic_foundation", {"outcome": "success", "attempts": attempts, "strategicFoundation": strategic_foundation, "evidencePool": evidence_pool, "narrativeQuestion": narrative_question})
    case_context = {**case_context, "narrativeQuestion": narrative_question}

    # --- Stage: diagnosis ---
    foundation_summary = [{"id": c["id"], "type": c["type"], "statement": c["statement"], "statementType": c["statementType"], "narrativeStage": c.get("narrativeStage")} for c in strategic_foundation]
    diag_result, outcome, stage_failure, tb, attempts = run_model_stage(
        "diagnosis", DIAGNOSIS_RESPONSE_SCHEMA,
        lambda pf: pipe.diagnose(client, usage, non_competitor, foundation_summary, competitor_sources, existing_narrative, evidence_pool, prior_failure=pf),
        lambda response: process_diagnosis_response(response, evidence_pool, source_text_by_id, dropped_links_report, rejected_records_report, statement_type_violations, source_roles_by_id, source_types_by_id),
        usage, progress_cb,
    )
    if outcome == "stage_failed":
        persist_cb("diagnosis", {"outcome": outcome, "attempts": attempts})
        return _empty_return(outcome, stage_failure, tb, strategic_foundation, [], [], [], None, None, [], evidence_pool)
    diagnosis, competitor_contrasts = diag_result
    persist_cb("diagnosis", {"outcome": "success", "attempts": attempts, "diagnosis": diagnosis, "competitorContrasts": competitor_contrasts, "evidencePool": evidence_pool})

    # --- Stage: narrative_choices ---
    def _process_candidates_and_check_coverage(response):
        candidates = process_candidates_response(response, evidence_pool, dropped_links_report, rejected_records_report)
        check_direction_coverage(strategic_foundation, candidates)
        return candidates

    diagnosis_summary = [{"id": f["id"], "title": f["title"], "significance": f["significance"]} for f in diagnosis]
    cand_result, outcome, stage_failure, tb, attempts = run_model_stage(
        "narrative_choices", CANDIDATES_RESPONSE_SCHEMA,
        lambda pf: pipe.generate_candidates(client, usage, foundation_summary, diagnosis_summary, evidence_pool, prior_failure=pf),
        _process_candidates_and_check_coverage,
        usage, progress_cb,
    )
    if outcome == "stage_failed":
        persist_cb("narrative_choices", {"outcome": outcome, "attempts": attempts})
        return _empty_return(outcome, stage_failure, tb, strategic_foundation, diagnosis, [], competitor_contrasts, None, None, [], evidence_pool)
    candidates = cand_result
    persist_cb("narrative_choices", {"outcome": "success", "attempts": attempts, "candidates": candidates})

    # --- Stage: critique ---
    critique_result, outcome, stage_failure, tb, attempts = run_model_stage(
        "critique", CRITIQUE_RESPONSE_SCHEMA,
        lambda pf: pipe.critique_candidates(client, usage, candidates, prior_failure=pf),
        lambda response: process_critique_response(response, candidates, rejected_records_report),
        usage, progress_cb,
    )
    if outcome == "stage_failed":
        persist_cb("critique", {"outcome": outcome, "attempts": attempts})
        return _empty_return(outcome, stage_failure, tb, strategic_foundation, diagnosis, candidates, competitor_contrasts, None, None, [], evidence_pool)
    candidates, survivors = critique_result
    persist_cb("critique", {"outcome": "success", "attempts": attempts, "candidates": candidates})

    if not survivors:
        # Now ALWAYS persisted (previously this branch returned without ever calling
        # persist_cb for this stage — the exact gap behind the recommendation_and_map ==
        # None ambiguity between no_candidate_passed and stage_failed). recommendation is
        # the canonical outcome object itself, never None, once critique has completed.
        no_candidate_state = build_recommendation_state("no_candidate_passed")
        persist_cb("recommendation_and_map", {"outcome": "no_candidate_passed", "attempts": [], "recommendation": no_candidate_state})
        return _empty_return("no_candidate_passed", None, None, strategic_foundation, diagnosis, candidates, competitor_contrasts, no_candidate_state, None, [], evidence_pool)

    # --- Stage: recommendation_and_map ---
    rec_result, outcome, stage_failure, tb, attempts = run_model_stage(
        "recommendation_and_map", RECOMMEND_AND_MAP_RESPONSE_SCHEMA,
        lambda pf: pipe.recommend_and_map(client, usage, survivors, candidates, evidence_pool, foundation_summary, prior_failure=pf),
        lambda response: process_recommend_and_map_response(response, survivors, candidates, evidence_pool, dropped_links_report, rejected_records_report, "map_live_v1", 1),
        usage, progress_cb,
    )
    if outcome == "stage_failed":
        stage_failed_state = build_recommendation_state("stage_failed", failure_reason=stage_failure["validation_error"])
        persist_cb("recommendation_and_map", {"outcome": outcome, "attempts": attempts, "recommendation": stage_failed_state})
        # strategic_foundation/diagnosis/candidates are passed through UNCHANGED from
        # before this stage ran — this is what makes "stage_failed preserves all earlier
        # candidate statuses, evidence, diagnosis, critique, scores, and partial results"
        # true by construction rather than by a separate preservation step.
        return _empty_return(outcome, stage_failure, tb, strategic_foundation, diagnosis, candidates, competitor_contrasts, stage_failed_state, None, [], evidence_pool)
    detail, narrative_map, audiences = rec_result
    recommendation = build_recommendation_state(
        "success", selected_candidate_id=detail["candidateId"],
        missing_evidence=detail["missingEvidence"], leadership_decisions=narrative_map["unresolvedQuestions"],
        detail=detail,
    )
    persist_cb("recommendation_and_map", {"outcome": "success", "attempts": attempts, "recommendation": recommendation, "narrativeMap": narrative_map, "audiences": audiences})

    return _empty_return("success", None, None, strategic_foundation, diagnosis, candidates, competitor_contrasts, recommendation, narrative_map, audiences, evidence_pool)


def regenerate_from(sources, source_text_by_id, evidence_pool, edited_foundation, existing_narrative, progress_cb=lambda *_: None, persist_cb=lambda *_: None):
    """Re-runs diagnosis onward with a user-edited foundation held fixed. Does not
    re-fetch any URL. `sources`/`source_text_by_id`/`evidence_pool` come from the original
    completed job's persisted/in-memory context."""
    client = pipe.get_client()

    def on_usage_call(entry, totals):
        persist_cb("usage", {"latestCall": entry, "totals": totals, "costUsd": compute_cost(totals)})

    usage = pipe.UsageTracker(on_call=on_usage_call)
    dropped_links_report = []
    statement_type_violations = []
    rejected_records_report = []

    # Defensive/idempotent — see sources_with_pasted_narrative's docstring. In practice
    # sources here already came from a checkpoint that run_analysis injected into, so this
    # is normally a no-op; kept as a safety net regardless.
    sources, source_text_by_id = sources_with_pasted_narrative(sources, source_text_by_id, existing_narrative)

    non_competitor = [{"id": s["id"], "text": source_text_by_id[s["id"]], "role": s.get("documentRole")} for s in sources if s["sourceType"] != "competitor"]
    competitor_sources = [{"id": s["id"], "text": source_text_by_id[s["id"]], "role": s.get("documentRole")} for s in sources if s["sourceType"] == "competitor"]
    source_roles_by_id = {s["id"]: s.get("documentRole") for s in sources}
    source_types_by_id = {s["id"]: s.get("sourceType") for s in sources}

    strategic_foundation = edited_foundation
    foundation_summary = [{"id": c["id"], "type": c["type"], "statement": c["statement"], "statementType": c["statementType"], "narrativeStage": c.get("narrativeStage")} for c in strategic_foundation]

    def _empty_return(outcome, stage_failure, tb, diagnosis, candidates, competitor_contrasts, recommendation, narrative_map, audiences):
        diagnostics = _diagnostics_for_outcome(outcome, stage_failure, {
            "dropped_links": dropped_links_report,
            "statement_type_violations": statement_type_violations,
            "rejected_records": rejected_records_report,
            "api_calls": usage.calls,
            "token_totals": usage.totals(),
        })
        dataset = {
            "strategicFoundation": strategic_foundation,
            "diagnosis": diagnosis,
            "candidates": candidates,
            "recommendation": recommendation,
            "narrativeMap": narrative_map,
            "audiences": audiences,
            "competitorContrasts": competitor_contrasts,
            "evidence": [e for e in evidence_pool.values() if e.get("verified")],
        }
        return {"dataset": dataset, "diagnostics": diagnostics, "debug_traceback": tb}

    diag_result, outcome, stage_failure, tb, attempts = run_model_stage(
        "diagnosis", DIAGNOSIS_RESPONSE_SCHEMA,
        lambda pf: pipe.diagnose(client, usage, non_competitor, foundation_summary, competitor_sources, existing_narrative, evidence_pool, prior_failure=pf),
        lambda response: process_diagnosis_response(response, evidence_pool, source_text_by_id, dropped_links_report, rejected_records_report, statement_type_violations, source_roles_by_id, source_types_by_id),
        usage, progress_cb,
    )
    if outcome == "stage_failed":
        persist_cb("diagnosis", {"outcome": outcome, "attempts": attempts})
        return _empty_return(outcome, stage_failure, tb, [], [], [], None, None, [])
    diagnosis, competitor_contrasts = diag_result
    persist_cb("diagnosis", {"outcome": "success", "attempts": attempts, "diagnosis": diagnosis, "competitorContrasts": competitor_contrasts, "evidencePool": evidence_pool})

    def _process_candidates_and_check_coverage(response):
        candidates = process_candidates_response(response, evidence_pool, dropped_links_report, rejected_records_report)
        check_direction_coverage(strategic_foundation, candidates)
        return candidates

    diagnosis_summary = [{"id": f["id"], "title": f["title"], "significance": f["significance"]} for f in diagnosis]
    cand_result, outcome, stage_failure, tb, attempts = run_model_stage(
        "narrative_choices", CANDIDATES_RESPONSE_SCHEMA,
        lambda pf: pipe.generate_candidates(client, usage, foundation_summary, diagnosis_summary, evidence_pool, prior_failure=pf),
        _process_candidates_and_check_coverage,
        usage, progress_cb,
    )
    if outcome == "stage_failed":
        persist_cb("narrative_choices", {"outcome": outcome, "attempts": attempts})
        return _empty_return(outcome, stage_failure, tb, diagnosis, [], competitor_contrasts, None, None, [])
    candidates = cand_result
    persist_cb("narrative_choices", {"outcome": "success", "attempts": attempts, "candidates": candidates})

    critique_result, outcome, stage_failure, tb, attempts = run_model_stage(
        "critique", CRITIQUE_RESPONSE_SCHEMA,
        lambda pf: pipe.critique_candidates(client, usage, candidates, prior_failure=pf),
        lambda response: process_critique_response(response, candidates, rejected_records_report),
        usage, progress_cb,
    )
    if outcome == "stage_failed":
        persist_cb("critique", {"outcome": outcome, "attempts": attempts})
        return _empty_return(outcome, stage_failure, tb, diagnosis, candidates, competitor_contrasts, None, None, [])
    candidates, survivors = critique_result
    persist_cb("critique", {"outcome": "success", "attempts": attempts, "candidates": candidates})

    if not survivors:
        no_candidate_state = build_recommendation_state("no_candidate_passed")
        persist_cb("recommendation_and_map", {"outcome": "no_candidate_passed", "attempts": [], "recommendation": no_candidate_state})
        return _empty_return("no_candidate_passed", None, None, diagnosis, candidates, competitor_contrasts, no_candidate_state, None, [])

    rec_result, outcome, stage_failure, tb, attempts = run_model_stage(
        "recommendation_and_map", RECOMMEND_AND_MAP_RESPONSE_SCHEMA,
        lambda pf: pipe.recommend_and_map(client, usage, survivors, candidates, evidence_pool, foundation_summary, prior_failure=pf),
        lambda response: process_recommend_and_map_response(response, survivors, candidates, evidence_pool, dropped_links_report, rejected_records_report, "map_live_regenerated", 2),
        usage, progress_cb,
    )
    if outcome == "stage_failed":
        stage_failed_state = build_recommendation_state("stage_failed", failure_reason=stage_failure["validation_error"])
        persist_cb("recommendation_and_map", {"outcome": outcome, "attempts": attempts, "recommendation": stage_failed_state})
        return _empty_return(outcome, stage_failure, tb, diagnosis, candidates, competitor_contrasts, stage_failed_state, None, [])
    detail, narrative_map, audiences = rec_result
    recommendation = build_recommendation_state(
        "success", selected_candidate_id=detail["candidateId"],
        missing_evidence=detail["missingEvidence"], leadership_decisions=narrative_map["unresolvedQuestions"],
        detail=detail,
    )
    persist_cb("recommendation_and_map", {"outcome": "success", "attempts": attempts, "recommendation": recommendation, "narrativeMap": narrative_map, "audiences": audiences})

    return _empty_return("success", None, None, diagnosis, candidates, competitor_contrasts, recommendation, narrative_map, audiences)


# --- Manual, single-attempt retry functions ------------------------------------------------
# Each is exactly ONE deliberate attempt (never an internal automatic-retry loop — that
# would blur the line between "automatic retry within a run" and "the one manual retry a
# human triggers later"). Each rebuilds only the state IT needs from already-validated
# inputs; none re-fetch a URL or rerun an earlier stage.

def retry_extract_foundation(sources, source_text_by_id, existing_narrative="", company_name=None, prior_failure=None, progress_cb=lambda *_: None):
    client = pipe.get_client()
    usage = pipe.UsageTracker()
    dropped_links_report, rejected_records_report, statement_type_violations = [], [], []
    evidence_pool = {}  # foundation is the first model stage — nothing to reuse yet

    # Defensive/idempotent — see sources_with_pasted_narrative's docstring.
    sources, source_text_by_id = sources_with_pasted_narrative(sources, source_text_by_id, existing_narrative)

    non_competitor = [{"id": s["id"], "text": source_text_by_id[s["id"]], "role": s.get("documentRole")} for s in sources if s["sourceType"] != "competitor"]
    has_current_draft_narrative = any(s.get("role") == "current_draft_narrative" for s in non_competitor)
    source_roles_by_id = {s["id"]: s.get("documentRole") for s in sources}
    source_types_by_id = {s["id"]: s.get("sourceType") for s in sources}
    progress_cb("strategic_foundation")
    result, outcome, error_info, tb, attempt_usage = _attempt_stage_once(
        "strategic_foundation", FOUNDATION_RESPONSE_SCHEMA,
        lambda pf: pipe.extract_foundation(client, usage, non_competitor, prior_failure=pf),
        lambda response: process_foundation_response(response, evidence_pool, source_text_by_id, dropped_links_report, rejected_records_report, statement_type_violations, has_current_draft_narrative, company_name, source_roles_by_id, source_types_by_id),
        usage, prior_failure,
    )
    strategic_foundation, narrative_question = result if outcome == "success" else ([], None)
    outcome = "stage_failed" if outcome == "failed" else outcome
    diagnostics = {
        "outcome": outcome, "failure_reason": error_info["validation_error"] if error_info else None,
        "dropped_links": dropped_links_report, "rejected_records": rejected_records_report,
        "statement_type_violations": statement_type_violations, "api_calls": usage.calls, "token_totals": usage.totals(),
        "attempt_usage": attempt_usage,
    }
    return {
        "strategicFoundation": strategic_foundation, "evidencePool": evidence_pool, "narrativeQuestion": narrative_question,
        "outcome": outcome, "diagnostics": diagnostics, "debug_traceback": tb,
    }


def retry_diagnose(sources, source_text_by_id, evidence_pool, strategic_foundation, existing_narrative, prior_failure=None, progress_cb=lambda *_: None):
    client = pipe.get_client()
    usage = pipe.UsageTracker()
    dropped_links_report, rejected_records_report, statement_type_violations = [], [], []

    # Defensive/idempotent — see sources_with_pasted_narrative's docstring.
    sources, source_text_by_id = sources_with_pasted_narrative(sources, source_text_by_id, existing_narrative)

    non_competitor = [{"id": s["id"], "text": source_text_by_id[s["id"]], "role": s.get("documentRole")} for s in sources if s["sourceType"] != "competitor"]
    competitor_sources = [{"id": s["id"], "text": source_text_by_id[s["id"]], "role": s.get("documentRole")} for s in sources if s["sourceType"] == "competitor"]
    foundation_summary = [{"id": c["id"], "type": c["type"], "statement": c["statement"], "statementType": c["statementType"], "narrativeStage": c.get("narrativeStage")} for c in strategic_foundation]
    source_roles_by_id = {s["id"]: s.get("documentRole") for s in sources}
    source_types_by_id = {s["id"]: s.get("sourceType") for s in sources}

    progress_cb("diagnosis")
    result, outcome, error_info, tb, attempt_usage = _attempt_stage_once(
        "diagnosis", DIAGNOSIS_RESPONSE_SCHEMA,
        lambda pf: pipe.diagnose(client, usage, non_competitor, foundation_summary, competitor_sources, existing_narrative, evidence_pool, prior_failure=pf),
        lambda response: process_diagnosis_response(response, evidence_pool, source_text_by_id, dropped_links_report, rejected_records_report, statement_type_violations, source_roles_by_id, source_types_by_id),
        usage, prior_failure,
    )
    diagnosis, competitor_contrasts = result if outcome == "success" else ([], [])
    outcome = "stage_failed" if outcome == "failed" else outcome
    diagnostics = {
        "outcome": outcome, "failure_reason": error_info["validation_error"] if error_info else None,
        "dropped_links": dropped_links_report, "rejected_records": rejected_records_report,
        "statement_type_violations": statement_type_violations, "api_calls": usage.calls, "token_totals": usage.totals(),
        "attempt_usage": attempt_usage,
    }
    return {
        "diagnosis": diagnosis, "competitorContrasts": competitor_contrasts, "evidencePool": evidence_pool,
        "outcome": outcome, "diagnostics": diagnostics, "debug_traceback": tb,
    }


def retry_generate_candidates(evidence_pool, foundation_summary, diagnosis_summary, prior_failure=None, progress_cb=lambda *_: None):
    client = pipe.get_client()
    usage = pipe.UsageTracker()
    dropped_links_report, rejected_records_report = [], []

    def _process_candidates_and_check_coverage(response):
        candidates = process_candidates_response(response, evidence_pool, dropped_links_report, rejected_records_report)
        check_direction_coverage(foundation_summary, candidates)
        return candidates

    progress_cb("narrative_choices")
    result, outcome, error_info, tb, attempt_usage = _attempt_stage_once(
        "narrative_choices", CANDIDATES_RESPONSE_SCHEMA,
        lambda pf: pipe.generate_candidates(client, usage, foundation_summary, diagnosis_summary, evidence_pool, prior_failure=pf),
        _process_candidates_and_check_coverage,
        usage, prior_failure,
    )
    candidates = result if outcome == "success" else []
    outcome = "stage_failed" if outcome == "failed" else outcome
    diagnostics = {
        "outcome": outcome, "failure_reason": error_info["validation_error"] if error_info else None,
        "dropped_links": dropped_links_report, "rejected_records": rejected_records_report,
        "api_calls": usage.calls, "token_totals": usage.totals(), "attempt_usage": attempt_usage,
    }
    return {
        "candidates": candidates, "outcome": outcome, "diagnostics": diagnostics, "debug_traceback": tb,
    }


def retry_critique_candidates(candidates, prior_failure=None, progress_cb=lambda *_: None):
    client = pipe.get_client()
    usage = pipe.UsageTracker()
    rejected_records_report = []

    progress_cb("critique")
    result, outcome, error_info, tb, attempt_usage = _attempt_stage_once(
        "critique", CRITIQUE_RESPONSE_SCHEMA,
        lambda pf: pipe.critique_candidates(client, usage, candidates, prior_failure=pf),
        lambda response: process_critique_response(response, candidates, rejected_records_report),
        usage, prior_failure,
    )
    if outcome == "success":
        updated_candidates, survivors = result
    else:
        updated_candidates, survivors = candidates, []
    outcome = "stage_failed" if outcome == "failed" else outcome
    diagnostics = {
        "outcome": outcome, "failure_reason": error_info["validation_error"] if error_info else None,
        "rejected_records": rejected_records_report,
        "api_calls": usage.calls, "token_totals": usage.totals(), "attempt_usage": attempt_usage,
    }
    return {
        "candidates": updated_candidates, "survivors": survivors, "outcome": outcome,
        "diagnostics": diagnostics, "debug_traceback": tb,
    }


def retry_recommendation_and_map(candidates, evidence_pool, foundation_summary, prior_failure=None, progress_cb=lambda *_: None):
    """Stage-specific retry after a stage_failed on the final stage: reruns ONLY
    recommend_and_map using the already-validated candidates/evidence_pool/
    foundation_summary. Does not re-fetch any URL or rerun any earlier stage."""
    client = pipe.get_client()
    usage = pipe.UsageTracker()
    dropped_links_report, rejected_records_report = [], []

    survivors = [c for c in candidates if c.get("status") != CANDIDATE_STATUS_REJECTED]
    if not survivors:
        no_candidate_state = build_recommendation_state("no_candidate_passed")
        diagnostics = {"outcome": "no_candidate_passed", "failure_reason": None, "dropped_links": [], "rejected_records": [], "api_calls": usage.calls, "token_totals": usage.totals()}
        return {"recommendation": no_candidate_state, "narrativeMap": None, "audiences": [], "candidates": candidates,
                "outcome": "no_candidate_passed", "diagnostics": diagnostics, "debug_traceback": None}

    progress_cb("recommendation_and_map")
    result, outcome, error_info, tb, attempt_usage = _attempt_stage_once(
        "recommendation_and_map", RECOMMEND_AND_MAP_RESPONSE_SCHEMA,
        lambda pf: pipe.recommend_and_map(client, usage, survivors, candidates, evidence_pool, foundation_summary, prior_failure=pf),
        lambda response: process_recommend_and_map_response(response, survivors, candidates, evidence_pool, dropped_links_report, rejected_records_report, "map_live_retry", 1),
        usage, prior_failure,
    )
    outcome = "stage_failed" if outcome == "failed" else outcome
    if outcome == "success":
        detail, narrative_map, audiences = result
        recommendation = build_recommendation_state(
            "success", selected_candidate_id=detail["candidateId"],
            missing_evidence=detail["missingEvidence"], leadership_decisions=narrative_map["unresolvedQuestions"],
            detail=detail,
        )
    else:
        narrative_map, audiences = None, []
        recommendation = build_recommendation_state("stage_failed", failure_reason=error_info["validation_error"] if error_info else None)
    diagnostics = {
        "outcome": outcome, "failure_reason": error_info["validation_error"] if error_info else None,
        "dropped_links": dropped_links_report, "rejected_records": rejected_records_report,
        "api_calls": usage.calls, "token_totals": usage.totals(), "attempt_usage": attempt_usage,
    }
    return {
        "recommendation": recommendation, "narrativeMap": narrative_map, "audiences": audiences, "candidates": candidates,
        "outcome": outcome, "diagnostics": diagnostics, "debug_traceback": tb,
    }
