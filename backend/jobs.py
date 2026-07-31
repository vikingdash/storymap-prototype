"""Background-job system for the live 'Analyze a company' flow.

A single dedicated worker thread processes jobs sequentially from a queue — deliberately
not one-thread-per-request. ssrf_guard.guarded_dns() patches socket.getaddrinfo()
process-globally for the duration of a fetch (see ssrf_guard.py's docstring); running two
analyses concurrently would let one job's guarded_dns() context manager exit while
another job's fetch is still relying on the patch being active. A single worker thread
makes that race structurally impossible without needing a lock. The Flask app itself can
still run multi-threaded (app.py) because request handling — creating a job, polling its
status — never touches the network directly; only the worker thread does.

THE ORIGINAL job_id IS ALWAYS CANONICAL. A stage retry or a foundation-edit regeneration
never mints a new job_id — both dispatch actions run against the SAME job_id's checkpoint,
so /status on that one id always reflects the latest state, including after a backend
restart. The in-memory JOBS dict is a write-through CACHE for the currently-resident
process only; job_persistence's on-disk checkpoint is the actual source of truth. Every
mutation (creation, stage progress, completion, any retry, any regeneration) is written to
the checkpoint synchronously, so get_job() can always reconstruct a fully-accurate view
straight from disk even if JOBS itself was never populated in this process (e.g. after a
restart, or — in tests — when a checkpoint is seeded directly without going through the
in-memory job lifecycle at all).
"""
import os
import queue
import sys
import threading
import time
import traceback
import uuid

import job_persistence
from pipeline_runner import (
    PipelineError,
    RegenerationLimitReachedError,
    RetryLimitReachedError,
    STAGE_ORDER,
    SourceExpansionLimitReachedError,
    assess_source_coverage,
    build_attempt_record,
    build_case_context,
    check_manual_retry_allowed,
    check_regeneration_allowed,
    check_source_expansion_allowed,
    check_upstream_stages_valid,
    compute_cost,
    fetch_all_sources,
    invalidate_downstream_stages,
    now_iso,
    regenerate_from,
    retry_critique_candidates,
    retry_diagnose,
    retry_extract_foundation,
    retry_generate_candidates,
    retry_recommendation_and_map,
    run_analysis,
    run_pipeline_from_sources,
    validate_edited_foundation,
)

JOBS = {}
_JOBS_LOCK = threading.Lock()
_QUEUE = queue.Queue()

# One lock per job_id, serializing every check-then-mutate sequence that must be atomic
# against a concurrent request for the SAME job: the manual-retry-cap check + pending-
# retry reservation, and the regeneration-cap check + count increment. Two DIFFERENT
# jobs never contend with each other — only concurrent requests against the same job_id
# do, which is the actual race being closed. _JOB_LOCKS_META_LOCK protects only the
# dict of locks itself (lock creation), never held during the actual critical section.
_JOB_LOCKS = {}
_JOB_LOCKS_META_LOCK = threading.Lock()


def _get_job_lock(job_id):
    with _JOB_LOCKS_META_LOCK:
        if job_id not in _JOB_LOCKS:
            _JOB_LOCKS[job_id] = threading.Lock()
        return _JOB_LOCKS[job_id]

STAGES = [
    "fetching_sources",
    "strategic_foundation",
    "diagnosis",
    "narrative_choices",
    "critique",
    "recommendation_and_map",
]

# Maps each public retry job "kind"/dispatch action to the pipeline stage name it
# retries — the single source of truth both create_retry_job() (upstream validation) and
# _run_retry_job() (dispatch) key off of.
RETRY_KIND_TO_STAGE = {
    "retry_foundation": "strategic_foundation",
    "retry_diagnosis": "diagnosis",
    "retry_candidates": "narrative_choices",
    "retry_critique": "critique",
    "retry_recommendation": "recommendation_and_map",
}

# Local single-user tool — cleanup runs at startup AND on this interval while the process
# is alive, both configurable via env var so a long-running dev instance doesn't
# accumulate job_state/ directories forever without needing a restart. Never removes an
# active/recently-updated job: cleanup_expired_jobs() keys off each checkpoint's own
# savedAt, which is refreshed by every persist_cb call an in-progress job makes — a job
# that's actively running is, by construction, never "expired."
CLEANUP_INTERVAL_SECONDS = int(os.environ.get("STORYMAP_CLEANUP_INTERVAL_SECONDS", "3600"))
JOB_RETENTION_SECONDS = int(os.environ.get("STORYMAP_JOB_RETENTION_SECONDS", str(job_persistence.DEFAULT_MAX_AGE_SECONDS)))


def _new_job_id():
    return uuid.uuid4().hex


def _make_persist_cb(job_id):
    """Load-merge-save into this job's on-disk checkpoint. Called after every completed
    API call (usage/cost) and after every stage concludes (success or exhausted retries)
    — see pipeline_runner.run_analysis/regenerate_from's persist_cb call sites. The extra
    disk round trip per call is negligible next to the seconds a real API call takes.

    Every load-modify-save cycle in this module — this one included — runs under
    _get_job_lock(job_id). The worker thread calls this (and _update_meta, _finish_job)
    constantly while a job is in flight; a concurrent Flask request thread doing its own
    load-modify-save (create_retry_job's cap check + reservation,
    create_regenerate_job's cap check + increment) would otherwise race it — whichever
    saves last silently overwrites the other's update (a classic lost-update bug). The
    lock is what makes EVERY checkpoint mutation for a given job_id atomic with respect
    to every other one, not just retry/regenerate creation against itself.
    """

    def persist_cb(section, data):
        with _get_job_lock(job_id):
            try:
                existing = job_persistence.load_job_state(job_id) or {}
            except job_persistence.JobStateError:
                existing = {}
            if section == "usage":
                # pipeline_runner.py's on_usage_call fires once per completed API call,
                # every time passing "totals" cumulative WITHIN the current
                # run_analysis/regenerate_from invocation only — never across the job's
                # whole lifetime. Overwriting checkpoint["usage"] with that value
                # directly (as every other section is) would silently discard whatever
                # an EARLIER action on this same job already spent the moment a second
                # action (e.g. a /regenerate after the original analyze) makes its first
                # call. _merge_usage adds just this call's own tokens (data["latestCall"])
                # onto the checkpoint's real running total instead.
                existing["usage"] = _merge_usage(existing.get("usage"), data)
            else:
                existing[section] = data
            existing["jobId"] = job_id
            job_persistence.save_job_state(job_id, existing)

    return persist_cb


def _merge_usage(prior_usage, new_call_data):
    """Adds ONE completed API call's tokens (new_call_data["latestCall"]) onto the
    checkpoint's true lifetime-cumulative usage for this job — never trusts
    new_call_data["totals"], which (from pipeline_runner.py's on_usage_call) is only
    cumulative within a single run_analysis/regenerate_from invocation, not across every
    action ever taken on this job_id. Shared by _make_persist_cb's "usage" handling and
    _run_retry_job_inner's manual-retry usage merge, so there is exactly one place this
    arithmetic is ever done."""
    prior_totals = (prior_usage or {}).get("totals", {"input_tokens": 0, "output_tokens": 0})
    latest_call = new_call_data.get("latestCall") or {}
    merged_totals = {
        "input_tokens": prior_totals.get("input_tokens", 0) + latest_call.get("input_tokens", 0),
        "output_tokens": prior_totals.get("output_tokens", 0) + latest_call.get("output_tokens", 0),
    }
    return {
        "totals": merged_totals,
        "costUsd": compute_cost(merged_totals),
        "latestCall": latest_call,
    }


def _update_meta(job_id, **fields):
    """Partial-field merge into the checkpoint's "meta" section (kind/status/stage/error/
    createdAt) — the durable record of overall job status get_job() reads back after a
    restart. Also mirrors onto the in-memory JOBS entry when one is resident, so a poll
    from the SAME process doesn't need a disk round trip mid-run. Lock-protected — see
    _make_persist_cb's docstring for why every checkpoint mutation must be."""
    with _get_job_lock(job_id):
        _update_meta_locked(job_id, **fields)


def _update_meta_locked(job_id, **fields):
    """The actual body of _update_meta — factored out so create_retry_job/
    create_regenerate_job, which already hold the lock for their own multi-step critical
    section, can update meta as part of that SAME held lock instead of deadlocking on
    threading.Lock's non-reentrancy by calling _update_meta (which would try to
    re-acquire it)."""
    try:
        checkpoint = job_persistence.load_job_state(job_id) or {}
    except job_persistence.JobStateError:
        checkpoint = {}
    meta = dict(checkpoint.get("meta") or {})
    meta.update(fields)
    checkpoint["meta"] = meta
    checkpoint["jobId"] = job_id
    job_persistence.save_job_state(job_id, checkpoint)
    with _JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update({k: v for k, v in fields.items() if k in ("status", "stage", "error")})


def _create_job_record(kind):
    """Every job — analyze, regenerate, or any retry — starts life through here (or, for
    regenerate/retry, already exists via this path from its original analyze call).
    Writes both the in-memory JOBS entry AND an initial checkpoint synchronously, so even
    a job that's never polled while queued still has a durable "meta" record from the
    first instant it exists."""
    job_id = _new_job_id()
    created_at = now_iso()
    with _JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id, "kind": kind, "status": "queued", "stage": None,
            "dataset": None, "diagnostics": None, "error": None, "traceback": None,
            "createdAt": created_at,
        }
    job_persistence.save_job_state(job_id, {
        "meta": {"kind": kind, "status": "queued", "stage": None, "error": None, "createdAt": created_at},
    })
    return job_id


def create_analyze_job(company_url, supporting_urls, competitor_urls, existing_narrative):
    job_id = _create_job_record("analyze")
    payload = {
        "companyUrl": company_url, "supportingUrls": supporting_urls,
        "competitorUrls": competitor_urls, "existingNarrative": existing_narrative,
    }
    _make_persist_cb(job_id)("jobInput", payload)
    _QUEUE.put((job_id, "analyze"))
    return job_id


def create_regenerate_job(job_id, edited_foundation, existing_narrative):
    """Amends an EXISTING job in place — never mints a new job_id. The cap check and the
    regenerationCount increment happen inside the SAME per-job-lock critical section as
    the rest of this function's checkpoint mutation, so two concurrent /api/regenerate
    calls against the same job can never both be accepted once the cap is reached — the
    second one, once it acquires the lock, re-reads the just-incremented count and is
    rejected. Validates the edited foundation (shape + semantic validity, same bar model
    output has to clear) BEFORE incrementing the count — a rejected edit never consumes
    the allowance. On success: persists the edit as the new canonical strategic_foundation,
    invalidates every downstream stage so stale pre-edit data can never be served again
    even if this regeneration itself fails partway, then dispatches diagnosis-onward
    using ONLY the freshly edited foundation."""
    with _get_job_lock(job_id):
        try:
            checkpoint = job_persistence.load_job_state(job_id)
        except job_persistence.JobStateError as exc:
            raise ValueError(f"Cannot regenerate job {job_id}: {exc}") from exc
        if checkpoint is None:
            raise KeyError(f"Unknown job id: {job_id}")
        ok, reason = check_upstream_stages_valid(checkpoint, "strategic_foundation")
        if not ok:
            raise ValueError(f"Cannot regenerate job {job_id}: {reason}")

        allowed, limit_reason = check_regeneration_allowed(checkpoint)
        if not allowed:
            raise RegenerationLimitReachedError(f"Cannot regenerate job {job_id}: {limit_reason}")

        # Validation happens AFTER the cap check (so an already-exhausted job fails fast
        # without spending effort validating) but BEFORE the count is incremented (so a
        # rejected edit — bad shape, bad semantics — never counts as a used
        # regeneration, per "do not count failed validation as a regeneration").
        problems = validate_edited_foundation(edited_foundation)
        if problems:
            raise ValueError("editedFoundation is invalid: " + "; ".join(problems))

        prior_fs = checkpoint.get("strategic_foundation") or {}
        evidence_pool = prior_fs.get("evidencePool", {})

        checkpoint["strategic_foundation"] = {
            "outcome": "success",
            "strategicFoundation": edited_foundation,
            "evidencePool": evidence_pool,
            "editedManually": True,
            "editedAt": now_iso(),
            "attempts": [],  # a fresh manually-authored value starts a fresh attempt history
        }
        checkpoint = invalidate_downstream_stages(checkpoint, "strategic_foundation")
        checkpoint["regenerationInput"] = {"existingNarrative": existing_narrative}
        checkpoint["regenerationCount"] = checkpoint.get("regenerationCount", 0) + 1
        job_persistence.save_job_state(job_id, checkpoint)

        _update_meta_locked(job_id, status="queued", stage=None, error=None)
        _QUEUE.put((job_id, "regenerate"))
        return job_id


def create_expand_sources_job(job_id, company_url, supporting_urls, competitor_urls):
    """Amends an EXISTING job in place — never mints a new job_id, same as
    create_regenerate_job. Unlike regenerate, this DOES need to re-fetch (new URLs were
    added), so the actual fetch never happens here — only validation, the cap
    check-and-increment, and enqueueing happen synchronously; the real network work runs
    in the worker thread later (see _run_job's "expand_sources" branch), exactly like
    create_analyze_job never fetches anything itself either. That's also why, unlike
    create_regenerate_job, there's no upstream-stage precondition here: this re-fetches
    from scratch regardless of whether the original fetch ever succeeded, so it can even
    recover a job whose company URL hard-failed before any source was ever persisted.

    companyUrl is required and must match the job's ORIGINAL company URL
    (checkpoint["jobInput"]["companyUrl"]) — the server always re-fetches its own stored
    URL, never a client-resent one; a mismatch is rejected so a client can never silently
    repurpose an existing job's identity to a different company via the same job_id.

    Downstream stages are invalidated synchronously (same "no stale data even if this
    then fails partway" guarantee create_regenerate_job provides for foundation edits) —
    but fetching_sources itself is NOT touched here, since the new fetch hasn't happened
    yet; it's overwritten by the worker once the new fetch actually completes.
    """
    with _get_job_lock(job_id):
        try:
            checkpoint = job_persistence.load_job_state(job_id)
        except job_persistence.JobStateError as exc:
            raise ValueError(f"Cannot add sources to job {job_id}: {exc}") from exc
        if checkpoint is None:
            raise KeyError(f"Unknown job id: {job_id}")

        stored_company_url = (checkpoint.get("jobInput") or {}).get("companyUrl")
        if stored_company_url and company_url != stored_company_url:
            raise ValueError(
                f"Cannot add sources to job {job_id}: companyUrl does not match this job's original "
                f"company URL — a job's company identity can never change."
            )

        allowed, limit_reason = check_source_expansion_allowed(checkpoint)
        if not allowed:
            raise SourceExpansionLimitReachedError(f"Cannot add sources to job {job_id}: {limit_reason}")

        checkpoint["expandSourcesInput"] = {"supportingUrls": supporting_urls, "competitorUrls": competitor_urls}
        checkpoint = invalidate_downstream_stages(checkpoint, "fetching_sources")
        checkpoint["expandSourcesCount"] = checkpoint.get("expandSourcesCount", 0) + 1
        job_persistence.save_job_state(job_id, checkpoint)

        _update_meta_locked(job_id, status="queued", stage=None, error=None)
        _QUEUE.put((job_id, "expand_sources"))
        return job_id


def create_retry_job(retry_kind, job_id):
    """Validates BEFORE spending anything: the retry kind must be real, the job's
    checkpoint must exist and be readable, every stage the requested one depends on must
    already have succeeded, the target stage must not have already used its one allowed
    manual retry (or already have one in flight), and — specifically for
    retry_foundation — the foundation must not have been manually edited (retrying it
    would silently discard that edit; the user should submit a new edit via
    /api/regenerate instead). Raises KeyError/ValueError/RetryLimitReachedError —
    callers (app.py) turn those into 404/400/429, never queueing a doomed or over-quota
    retry. Always dispatches against the SAME job_id.

    The cap check AND the pendingManualRetry reservation happen inside the SAME per-job
    lock, atomically: this is what makes two concurrent requests for the same stage
    resolve to only one queued retry. Whichever request acquires the lock first reserves
    the slot (writes pendingManualRetry=True) before releasing it; the second, once it
    acquires the lock, sees that reservation and is rejected with retry_in_progress —
    never both queued. The reservation is cleared by _run_retry_job (via try/finally,
    even on an unexpected crash) once the actual attempt concludes.
    """
    if retry_kind not in RETRY_KIND_TO_STAGE:
        raise ValueError(f"Unknown retry kind: {retry_kind!r}")
    stage_name = RETRY_KIND_TO_STAGE[retry_kind]
    with _get_job_lock(job_id):
        try:
            checkpoint = job_persistence.load_job_state(job_id)
        except job_persistence.JobStateError as exc:
            raise ValueError(f"Cannot retry job {job_id}: {exc}") from exc
        if checkpoint is None:
            raise KeyError(f"Unknown job id: {job_id}")

        ok, reason = check_upstream_stages_valid(checkpoint, stage_name)
        if not ok:
            raise ValueError(f"Cannot retry {stage_name} for job {job_id}: {reason}")

        if stage_name == "strategic_foundation" and (checkpoint.get("strategic_foundation") or {}).get("editedManually"):
            raise ValueError(
                f"Cannot retry {stage_name} for job {job_id}: strategic_foundation was manually edited — "
                "retrying it would discard that edit; submit a new edit via /api/regenerate instead"
            )

        allowed, limit_reason = check_manual_retry_allowed(checkpoint, stage_name)
        if not allowed:
            raise RetryLimitReachedError(f"Cannot retry {stage_name} for job {job_id}: {limit_reason}", code=limit_reason)

        section = dict(checkpoint.get(stage_name) or {"attempts": []})
        section["pendingManualRetry"] = True
        checkpoint[stage_name] = section
        job_persistence.save_job_state(job_id, checkpoint)

        _update_meta_locked(job_id, status="queued")
        _QUEUE.put((job_id, retry_kind))
        return job_id


def get_job(job_id):
    """Checkpoint-first: if a checkpoint exists for job_id, it is ALWAYS the source of
    truth for the returned view (this is what makes /status restart-safe and what makes
    the original job_id canonical across any retry or regeneration). Falls back to the
    in-memory JOBS entry only in the narrow window before a job's first checkpoint write
    has happened — see _create_job_record(), which writes one synchronously at creation,
    so in practice this fallback is barely reachable outside a test that seeds JOBS
    directly without going through _create_job_record."""
    try:
        checkpoint = job_persistence.load_job_state(job_id)
    except job_persistence.JobStateError:
        checkpoint = None
    if checkpoint is not None:
        return _job_view_from_checkpoint(job_id, checkpoint)
    with _JOBS_LOCK:
        return JOBS.get(job_id)


def _job_view_from_checkpoint(job_id, checkpoint):
    meta = checkpoint.get("meta") or {}
    status = meta.get("status", "running")
    return {
        "id": job_id,
        "kind": meta.get("kind"),
        "status": status,
        "stage": meta.get("stage"),
        "dataset": _dataset_from_checkpoint(checkpoint) if status in ("done", "failed") else None,
        "diagnostics": checkpoint.get("lastDiagnostics"),
        "error": meta.get("error"),
        "traceback": checkpoint.get("_debugTraceback"),
        "createdAt": meta.get("createdAt"),
        # usage/stageProgress are both always derived fresh from the checkpoint, same
        # "never a cached snapshot" posture as _dataset_from_checkpoint above — they
        # automatically reflect the latest retry/regenerate, no separate invalidation
        # logic needed.
        "usage": checkpoint.get("usage"),
        "stageProgress": _stage_progress_from_checkpoint(checkpoint),
        "sourceCoverage": _source_coverage_from_checkpoint(checkpoint),
    }


def _source_coverage_from_checkpoint(checkpoint):
    """Read-time derivation — mirrors _dataset_from_checkpoint's own "always fresh, never
    a cached snapshot" posture. Deliberately NOT persisted at write time: strategic_foundation
    can reach outcome "success" via four different paths (a full run, a manual foundation
    retry, a user-edited foundation via /regenerate, or an expand-sources re-run) and
    persisting at write time would need a call site in all four, with staleness risk if a
    fifth is ever added. Computing it fresh from already-persisted data on every read has
    exactly one call site, ever, and can never go stale. Returns None if strategic_foundation
    hasn't succeeded (nothing to assess yet)."""
    fs = checkpoint.get("strategic_foundation") or {}
    if fs.get("outcome") != "success":
        return None
    fetching = checkpoint.get("fetching_sources") or {}
    existing_narrative = (
        checkpoint.get("regenerationInput") or checkpoint.get("expandSourcesInput") or checkpoint.get("jobInput") or {}
    ).get("existingNarrative", "")
    return assess_source_coverage(
        fetching.get("sources", []), fs.get("strategicFoundation", []), fs.get("evidencePool", {}), existing_narrative,
    )


def _stage_progress_from_checkpoint(checkpoint):
    """Per-stage retry history for the UI — durable in a way checkpoint["lastDiagnostics"]
    alone can't be, since lastDiagnostics only reflects the MOST RECENT action's outcome
    and loses an earlier stage's failure/retry history once a later action succeeds (e.g.
    once diagnosis's manual retry succeeds, diagnostics no longer mentions that it took 2
    attempts to get there — this reads it straight from that stage's own persisted
    "attempts" list instead, which is never overwritten, only appended to).

    Returns one entry per stage in STAGE_ORDER (excluding fetching_sources, which has its
    own fetchFailures reporting already):
      {outcome: "success"|"stage_failed"|"invalidated"|None (not reached yet),
       attempts: <count>, lastFailureReason: <most recent non-success attempt's
       validationFailure, else None>}
    """
    progress = {}
    for stage in STAGE_ORDER[1:]:
        section = checkpoint.get(stage)
        if section is None:
            progress[stage] = {"outcome": None, "attempts": 0, "lastFailureReason": None}
            continue
        attempts = section.get("attempts", [])
        last_failure_reason = None
        for attempt in reversed(attempts):
            if attempt.get("outcome") != "success":
                last_failure_reason = attempt.get("validationFailure")
                break
        progress[stage] = {
            "outcome": section.get("outcome"),
            "attempts": len(attempts),
            "lastFailureReason": last_failure_reason,
        }
    return progress


def _dataset_from_checkpoint(checkpoint):
    """Reassembles the frontend-shaped dataset from a job's persisted checkpoint. Always
    derived fresh from the current state of each section — never a cached snapshot — so
    it automatically reflects the latest successful retry or regeneration, and an
    "invalidated" section (see invalidate_downstream_stages) naturally contributes
    nothing (its old data keys are gone, replaced by the invalidation marker), making
    stale post-edit data structurally impossible to return."""
    fetching = checkpoint.get("fetching_sources") or {}
    fs = checkpoint.get("strategic_foundation") or {}
    diag = checkpoint.get("diagnosis") or {}
    nc = checkpoint.get("narrative_choices") or {}
    crit = checkpoint.get("critique") or {}
    rec = checkpoint.get("recommendation_and_map") or {}
    evidence_pool = diag.get("evidencePool") or fs.get("evidencePool") or {}
    return {
        "caseContext": fetching.get("caseContext"),
        "sources": fetching.get("sources", []),
        "evidence": [e for e in evidence_pool.values() if e.get("verified")],
        "strategicFoundation": fs.get("strategicFoundation", []),
        "diagnosis": diag.get("diagnosis", []),
        "competitorContrasts": diag.get("competitorContrasts", []),
        "candidates": crit.get("candidates") or nc.get("candidates", []),
        "recommendation": rec.get("recommendation"),
        "narrativeMap": rec.get("narrativeMap"),
        "audiences": rec.get("audiences", []),
    }


def _set_stage(job_id, stage):
    _update_meta(job_id, stage=stage, status="running")


def _run_job(job_id, action):
    """Dispatches one queued (job_id, action) pair. action is "analyze", "regenerate", or
    one of the 5 retry_* kinds — never job["kind"] itself, which stays fixed at the job's
    original type ("analyze") for display purposes even after regeneration/retries amend
    it in place."""
    _update_meta(job_id, status="running")
    try:
        if action == "analyze":
            checkpoint = job_persistence.load_job_state(job_id)
            payload = checkpoint["jobInput"]
            persist_cb = _make_persist_cb(job_id)
            result = run_analysis(
                payload["companyUrl"], payload["supportingUrls"], payload["competitorUrls"],
                payload["existingNarrative"], progress_cb=lambda stage: _set_stage(job_id, stage),
                persist_cb=persist_cb,
            )
        elif action == "regenerate":
            checkpoint = job_persistence.load_job_state(job_id)
            fetching = checkpoint.get("fetching_sources") or {}
            fs = checkpoint.get("strategic_foundation") or {}
            existing_narrative = (checkpoint.get("regenerationInput") or checkpoint.get("jobInput") or {}).get("existingNarrative", "")
            persist_cb = _make_persist_cb(job_id)
            result = regenerate_from(
                fetching.get("sources", []), fetching.get("sourceTextById", {}), fs.get("evidencePool", {}),
                fs.get("strategicFoundation", []), existing_narrative,
                progress_cb=lambda stage: _set_stage(job_id, stage), persist_cb=persist_cb,
            )
        elif action == "expand_sources":
            checkpoint = job_persistence.load_job_state(job_id)
            company_url = (checkpoint.get("jobInput") or {}).get("companyUrl")
            expand_input = checkpoint.get("expandSourcesInput") or {}
            existing_narrative = (checkpoint.get("regenerationInput") or checkpoint.get("jobInput") or {}).get("existingNarrative", "")
            persist_cb = _make_persist_cb(job_id)
            # Genuinely re-fetches — create_expand_sources_job() only validated and
            # invalidated downstream stages synchronously; the real network work (the
            # whole reason this is a distinct action from "regenerate") happens here,
            # in the worker thread, same as create_analyze_job() never fetches anything
            # itself either.
            sources, source_text_by_id, fetch_failures, company_doc = fetch_all_sources(
                company_url, expand_input.get("supportingUrls", []), expand_input.get("competitorUrls", []),
                progress_cb=lambda stage: _set_stage(job_id, stage),
            )
            case_context = build_case_context(company_doc)
            persist_cb("fetching_sources", {
                "sources": sources, "sourceTextById": source_text_by_id,
                "fetchFailures": fetch_failures, "caseContext": case_context,
            })
            result = run_pipeline_from_sources(
                sources, source_text_by_id, existing_narrative, case_context, fetch_failures,
                progress_cb=lambda stage: _set_stage(job_id, stage), persist_cb=persist_cb,
            )
        else:
            _run_retry_job(job_id, action)
            return
    except PipelineError as exc:
        tb = traceback.format_exc()
        print(f"[job {job_id}] pipeline error:\n{tb}", file=sys.stderr)
        _fail_job(job_id, str(exc), tb)
        return
    except Exception as exc:  # noqa: BLE001 — a job must never crash the worker thread silently
        tb = traceback.format_exc()
        print(f"[job {job_id}] unexpected pipeline error:\n{tb}", file=sys.stderr)
        _fail_job(job_id, f"Unexpected pipeline error: {exc!r}", tb)
        return

    critical_failure = result["diagnostics"].get("critical_failure")
    tb = result.get("debug_traceback")
    if tb:
        print(f"[job {job_id}] stage error:\n{tb}", file=sys.stderr)
    if critical_failure not in (None, "no_candidate_passed"):
        _finish_job(job_id, "failed", error=critical_failure, diagnostics=result["diagnostics"], tb=tb)
    else:
        _finish_job(job_id, "done", error=None, diagnostics=result["diagnostics"], tb=tb)


def _fail_job(job_id, error, tb=None):
    _finish_job(job_id, "failed", error=error, diagnostics=None, tb=tb)


def _finish_job(job_id, status, error, diagnostics, tb=None):
    # error (unlike tb) IS returned directly to the client via /status — redacted here
    # too, at the same single choke point, since an unexpected exception's message (a
    # network/SDK library this code doesn't control the wording of — see the generic
    # `except Exception` branch in _run_job) could embed a header value, URL query
    # param, or other secret exactly like a traceback can.
    error = job_persistence.redact_traceback(error) if error else error
    tb = job_persistence.redact_traceback(tb) if tb else tb  # redact once, reused for both the persisted AND in-memory copies below
    with _get_job_lock(job_id):
        try:
            checkpoint = job_persistence.load_job_state(job_id) or {}
        except job_persistence.JobStateError:
            checkpoint = {}
        if diagnostics is not None:
            checkpoint["lastDiagnostics"] = diagnostics
        if tb:
            # Never returned by /status — app.py never reads this key.
            checkpoint["_debugTraceback"] = tb
        meta = dict(checkpoint.get("meta") or {})
        meta.update({"status": status, "stage": "done" if status == "done" else meta.get("stage"), "error": error})
        checkpoint["meta"] = meta
        checkpoint["jobId"] = job_id
        job_persistence.save_job_state(job_id, checkpoint)
    with _JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["status"] = status
            JOBS[job_id]["stage"] = meta["stage"]
            JOBS[job_id]["error"] = error
            JOBS[job_id]["diagnostics"] = diagnostics
            JOBS[job_id]["dataset"] = _dataset_from_checkpoint(checkpoint)
            if tb:
                JOBS[job_id]["traceback"] = tb


def _clear_pending_manual_retry(job_id, stage_name):
    """Best-effort cleanup of the pendingManualRetry reservation create_retry_job wrote
    atomically before enqueueing this attempt. Called from a finally block (see
    _run_retry_job) so it fires even if the attempt crashed unexpectedly before reaching
    its normal completion path — without this, an unhandled exception mid-retry would
    leave the stage permanently unretryable (a self-inflicted deadlock: every future
    check_manual_retry_allowed call would see the stale reservation and report
    retry_in_progress forever). A no-op (single read, no write) in the common case where
    the normal completion path already cleared it."""
    with _get_job_lock(job_id):
        try:
            checkpoint = job_persistence.load_job_state(job_id)
        except job_persistence.JobStateError:
            return
        if checkpoint is None:
            return
        section = checkpoint.get(stage_name)
        if section and section.get("pendingManualRetry"):
            section = dict(section)
            section["pendingManualRetry"] = False
            checkpoint[stage_name] = section
            job_persistence.save_job_state(job_id, checkpoint)


def _run_retry_job(job_id, action):
    """Dispatches one of the 5 manual, single-attempt retry_xxx() pipeline_runner
    functions, reading every input exclusively from the job's on-disk checkpoint (never
    from in-memory JOBS — that may not even exist any more if the process restarted
    since the original run). Appends this attempt to the stage's persisted attempt
    history (retries never erase earlier attempts — see build_attempt_record), updates
    the running cumulative usage/cost total, and — only on success — updates the stage's
    actual data fields. Always writes back to the SAME job_id's checkpoint. Wrapped in
    try/finally so the pendingManualRetry reservation is always cleared, even on an
    unexpected crash."""
    stage_name = RETRY_KIND_TO_STAGE[action]
    try:
        _run_retry_job_inner(job_id, stage_name)
    finally:
        _clear_pending_manual_retry(job_id, stage_name)


def _run_retry_job_inner(job_id, stage_name):
    checkpoint = job_persistence.load_job_state(job_id)
    if checkpoint is None:
        _fail_job(job_id, f"No job state found for {job_id} — cannot retry")
        return

    fetching = checkpoint.get("fetching_sources") or {}
    sources = fetching.get("sources", [])
    source_text_by_id = fetching.get("sourceTextById", {})
    existing_narrative = (checkpoint.get("regenerationInput") or checkpoint.get("jobInput") or {}).get("existingNarrative", "")
    progress_cb = lambda s: _set_stage(job_id, s)

    _set_stage(job_id, stage_name)
    started_at = now_iso()

    if stage_name == "strategic_foundation":
        result = retry_extract_foundation(sources, source_text_by_id, progress_cb=progress_cb)
        section_update = {"strategicFoundation": result["strategicFoundation"], "evidencePool": result["evidencePool"]}
    elif stage_name == "diagnosis":
        fs = checkpoint.get("strategic_foundation") or {}
        result = retry_diagnose(
            sources, source_text_by_id, fs.get("evidencePool", {}), fs.get("strategicFoundation", []),
            existing_narrative, progress_cb=progress_cb,
        )
        section_update = {"diagnosis": result["diagnosis"], "competitorContrasts": result["competitorContrasts"], "evidencePool": result["evidencePool"]}
    elif stage_name == "narrative_choices":
        fs = checkpoint.get("strategic_foundation") or {}
        diag = checkpoint.get("diagnosis") or {}
        foundation_summary = [{"id": c["id"], "type": c["type"], "statement": c["statement"], "statementType": c["statementType"]} for c in fs.get("strategicFoundation", [])]
        diagnosis_summary = [{"id": f["id"], "title": f["title"], "significance": f["significance"]} for f in diag.get("diagnosis", [])]
        result = retry_generate_candidates(diag.get("evidencePool", {}), foundation_summary, diagnosis_summary, progress_cb=progress_cb)
        section_update = {"candidates": result["candidates"]}
    elif stage_name == "critique":
        nc = checkpoint.get("narrative_choices") or {}
        result = retry_critique_candidates(nc.get("candidates", []), progress_cb=progress_cb)
        section_update = {"candidates": result["candidates"]}
    else:  # recommendation_and_map
        fs = checkpoint.get("strategic_foundation") or {}
        diag = checkpoint.get("diagnosis") or {}
        crit = checkpoint.get("critique") or {}
        foundation_summary = [{"id": c["id"], "type": c["type"], "statement": c["statement"], "statementType": c["statementType"]} for c in fs.get("strategicFoundation", [])]
        result = retry_recommendation_and_map(crit.get("candidates", []), diag.get("evidencePool", {}), foundation_summary, progress_cb=progress_cb)
        section_update = {"recommendation": result["recommendation"], "narrativeMap": result["narrativeMap"], "audiences": result["audiences"]}

    completed_at = now_iso()
    if result.get("debug_traceback"):
        print(f"[job {job_id}] manual retry error ({stage_name}):\n{result['debug_traceback']}", file=sys.stderr)

    # Everything from here on is a single read-modify-write against the checkpoint —
    # held under the job lock so it can never race a concurrent write from this same
    # job's own worker activity (there isn't any at this exact moment, since this IS the
    # worker) or, more importantly, from a Flask request thread's create_retry_job/
    # create_regenerate_job call for the SAME job_id (e.g. checking whether a NEW retry
    # is allowed while this one is still being recorded).
    with _get_job_lock(job_id):
        checkpoint = job_persistence.load_job_state(job_id) or checkpoint  # re-read in case usage/etc. was persisted mid-call
        prior_section = checkpoint.get(stage_name) or {"attempts": []}
        attempts = list(prior_section.get("attempts", []))
        attempt_usage = result["diagnostics"].get("attempt_usage")
        attempts.append(build_attempt_record(
            stage_name, len(attempts) + 1, True, started_at, completed_at,
            result["outcome"], result["diagnostics"].get("failure_reason"), attempt_usage,
        ))
        new_section = dict(prior_section)
        new_section["outcome"] = result["outcome"]
        new_section["attempts"] = attempts
        new_section["retryCount"] = len(attempts)
        new_section["pendingManualRetry"] = False  # the reservation create_retry_job wrote is now resolved
        if result["outcome"] in ("success", "no_candidate_passed"):
            new_section.update(section_update)
        checkpoint[stage_name] = new_section

        # A manual retry is always exactly one attempt = one API call, so
        # diagnostics["attempt_usage"] IS that call's own tokens — the same shared
        # _merge_usage helper _make_persist_cb's "usage" handling uses, kept as one
        # single place this arithmetic is ever done.
        if result["diagnostics"].get("attempt_usage"):
            checkpoint["usage"] = _merge_usage(checkpoint.get("usage"), {"latestCall": result["diagnostics"]["attempt_usage"]})
        checkpoint["lastDiagnostics"] = result["diagnostics"]
        if result.get("debug_traceback"):
            checkpoint["_debugTraceback"] = job_persistence.redact_traceback(result["debug_traceback"])

        if result["outcome"] in ("success", "no_candidate_passed"):
            status, error = "done", None
        else:
            status, error = "failed", result["diagnostics"].get("failure_reason") or f"{stage_name} retry failed"
        meta = dict(checkpoint.get("meta") or {})
        meta.update({"status": status, "stage": "done" if status == "done" else stage_name, "error": error})
        checkpoint["meta"] = meta
        checkpoint["jobId"] = job_id

        job_persistence.save_job_state(job_id, checkpoint)
    with _JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["status"] = status
            JOBS[job_id]["stage"] = meta["stage"]
            JOBS[job_id]["error"] = error
            JOBS[job_id]["diagnostics"] = result["diagnostics"]
            JOBS[job_id]["dataset"] = _dataset_from_checkpoint(checkpoint)
            if result.get("debug_traceback"):
                JOBS[job_id]["traceback"] = result["debug_traceback"]


def _worker_loop():
    while True:
        job_id, action = _QUEUE.get()
        try:
            _run_job(job_id, action)
        finally:
            _QUEUE.task_done()


def _run_cleanup_once():
    removed = job_persistence.cleanup_expired_jobs(max_age_seconds=JOB_RETENTION_SECONDS)
    if removed:
        print(f"[jobs] cleanup removed {len(removed)} expired job state director{'y' if len(removed) == 1 else 'ies'}", file=sys.stderr)
    return removed


def _cleanup_loop():
    while True:
        time.sleep(CLEANUP_INTERVAL_SECONDS)
        _run_cleanup_once()


def start_worker():
    """Idempotent-in-practice: call once at app startup. A second call would start
    duplicate worker/cleanup threads — app.py only calls this once, at import time."""
    _run_cleanup_once()
    thread = threading.Thread(target=_worker_loop, daemon=True, name="storymap-pipeline-worker")
    thread.start()
    cleanup_thread = threading.Thread(target=_cleanup_loop, daemon=True, name="storymap-cleanup-loop")
    cleanup_thread.start()
    return thread
