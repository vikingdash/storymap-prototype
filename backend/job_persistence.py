"""Local, file-based checkpoint store for job state — a safety net against losing
validated partial results (and spent cost) if the whole process crashes, not just a
single exception caught internally by pipeline_runner.py. In-memory-only state (the
JOBS dict in jobs.py) doesn't survive a process restart; this does.

Never stores the API key as a payload field (it is never part of any checkpoint payload
passed in — this module has no knowledge of it). A raw traceback CAN be persisted (under
checkpoint["_debugTraceback"], written by jobs.py — see its module docstring) so a crash
can still be diagnosed after a restart, but only ever through redact_traceback() first —
see that function's docstring. A persisted traceback is still never returned by any API
endpoint (app.py's /status handler never reads that key) and is subject to the exact
same retention/cleanup policy as the rest of the job's checkpoint (cleanup_expired_jobs
removes the whole directory, traceback included — there's no separate retention path for
it to fall through).

Each job gets its own directory under backend/job_state/ (gitignored — these can contain
real fetched company content and generated analysis, which must never be committed). The
directory (not a bare file) is the atomic unit for cleanup and leaves room for future
per-job artifacts without cluttering a flat namespace.
"""
import json
import os
import re
import shutil
import tempfile
import time
from datetime import datetime, timezone

JOB_STATE_SCHEMA_VERSION = 2
# Overridable via env var (read once, at import time) so a real subprocess — e.g. a
# process-restart integration test that spawns actual `python3 app.py` instances — can
# point an isolated instance at a throwaway directory without ever touching the real
# backend/job_state/. In-process tests instead reassign this module attribute directly
# after import (see test_*.py's setUpModule patterns); both approaches work because every
# function in this module reads the CURRENT value of the global at call time.
JOB_STATE_ROOT = os.environ.get("STORYMAP_JOB_STATE_ROOT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "job_state")
DEFAULT_MAX_AGE_SECONDS = 7 * 24 * 60 * 60  # 7 days — a local single-user dev tool doesn't need long retention
CHECKPOINT_FILENAME = "checkpoint.json"

# Env var NAMEs matching this are treated as secret — any of THEIR CURRENT VALUES found
# literally inside a traceback gets redacted. Broad on purpose (KEY/SECRET/TOKEN/
# PASSWORD/AUTH/CREDENTIAL) — this is a local dev tool where false positives (redacting
# a non-secret env var that happens to have "KEY" in its name) cost nothing, but a missed
# real secret costs everything.
_SECRET_ENV_NAME_PATTERN = re.compile(r"(KEY|SECRET|TOKEN|PASSWORD|PASSWD|AUTH|CREDENTIAL)", re.IGNORECASE)
_MIN_SECRET_VALUE_LENGTH = 6  # never redact trivially short values (e.g. "1", "true") — not secrets, and redacting them would mangle unrelated text

# Catches API-key-shaped tokens even if the env var that issued them isn't literally
# present in this process's environment at redaction time (e.g. a key embedded directly
# in an error message string, not read from os.environ).
_API_KEY_SHAPED_PATTERN = re.compile(r"\b(sk|pk)-(ant-)?[A-Za-z0-9_-]{10,}\b")
_AUTH_HEADER_PATTERN = re.compile(r"(?im)^(.*\b(?:authorization|x-api-key)\s*[:=]\s*)\S.*$")
_MIN_EMBEDDED_CONTENT_LENGTH = 200  # a quoted string at least this long is very unlikely to be a normal short exception message


def redact_traceback(text):
    """Scrubs a traceback string before it is EVER persisted to disk — applied once,
    inside jobs.py's checkpoint-write path, so no traceback origin (pipeline_runner.py's
    _attempt_stage_once, jobs.py's own except blocks) can bypass it. Three redaction
    passes, in order:
      1. Literal env var VALUES: for every currently-set environment variable whose NAME
         looks sensitive (KEY/SECRET/TOKEN/PASSWORD/AUTH/CREDENTIAL), replace any literal
         occurrence of its CURRENT VALUE — this catches ANTHROPIC_API_KEY specifically,
         and any other real secret, without needing to guess its shape.
      2. API-key-shaped tokens (sk-.../pk-...) and Authorization/x-api-key header lines —
         a shape-based backstop for keys that never went through os.environ (e.g. typed
         directly into an error message).
      3. Long embedded quoted content (>= 200 chars) — a fetched webpage's raw HTML/JSON
         ending up inside an exception message is exactly the kind of "file contents"
         that shouldn't be persisted verbatim; replaced with a fixed marker, not a
         partial preview (a truncated-but-still-long secret is still a leak).
    Returns the input unchanged if it's empty/None.
    """
    if not text:
        return text
    redacted = text

    for name, value in os.environ.items():
        if value and len(value) >= _MIN_SECRET_VALUE_LENGTH and _SECRET_ENV_NAME_PATTERN.search(name):
            redacted = redacted.replace(value, "[REDACTED]")

    redacted = _API_KEY_SHAPED_PATTERN.sub("[REDACTED]", redacted)
    redacted = _AUTH_HEADER_PATTERN.sub(lambda m: m.group(1) + "[REDACTED]", redacted)

    redacted = re.sub(r"'[^'\n]{%d,}'" % _MIN_EMBEDDED_CONTENT_LENGTH, "'[REDACTED - long content omitted]'", redacted)
    redacted = re.sub(r'"[^"\n]{%d,}"' % _MIN_EMBEDDED_CONTENT_LENGTH, '"[REDACTED - long content omitted]"', redacted)

    return redacted


class JobStateError(Exception):
    pass


class CorruptedJobStateError(JobStateError):
    """The checkpoint file exists but isn't valid, readable JSON, or is missing the
    schemaVersion marker entirely (so it can't even be version-checked)."""
    pass


class IncompatibleJobStateError(JobStateError):
    """The checkpoint parsed fine but carries a schemaVersion this code doesn't
    recognize — never silently proceed with a shape that might not match what this
    version of the code expects to find."""
    pass


def _safe_job_id(job_id):
    safe = "".join(c for c in job_id if c.isalnum() or c in ("-", "_"))
    if not safe:
        raise ValueError(f"Invalid job_id: {job_id!r}")
    return safe


def _job_dir(job_id):
    return os.path.join(JOB_STATE_ROOT, _safe_job_id(job_id))


def _checkpoint_path(job_id):
    return os.path.join(_job_dir(job_id), CHECKPOINT_FILENAME)


def upload_dir(job_id):
    """Where a job's uploaded internal-document files live — a subdirectory of the job's
    own directory, so it inherits the exact same guarantees for free: covered by the
    same backend/job_state/ gitignore rule (never committed), and removed by the exact
    same delete_job_state()/cleanup_expired_jobs() shutil.rmtree() of the whole job
    directory (no separate deletion path to keep in sync)."""
    return os.path.join(_job_dir(job_id), "uploads")


def save_uploaded_file(job_id, source_id, raw_bytes):
    """Writes the ORIGINAL uploaded file's bytes to this job's uploads/ subdirectory —
    purely an audit artifact; the pipeline itself only ever reads the already-extracted
    text/structure persisted in the checkpoint (see document_extractor.py), never
    re-opens this file. Requires the job's directory to already exist (i.e. call after
    create_analyze_job, which creates it via save_job_state)."""
    directory = upload_dir(job_id)
    os.makedirs(directory, exist_ok=True)
    safe_id = _safe_job_id(source_id)  # same alnum/-/_ sanitizer already used for job_id — a source_id is equally caller-influenced (derived from a filename)
    path = os.path.join(directory, f"{safe_id}.docx")
    with open(path, "wb") as f:
        f.write(raw_bytes)
    return path


def save_job_state(job_id, state):
    """Atomic write: temp file created in the SAME directory as the real target (so
    os.replace is guaranteed to be an atomic rename on the same filesystem, not a
    cross-device copy), then swapped into place — a crash mid-write can never leave a
    corrupted, half-written checkpoint for a later load to trip over. Creates the job's
    own directory on first use.
    """
    job_dir = _job_dir(job_id)
    os.makedirs(job_dir, exist_ok=True)
    payload = {"schemaVersion": JOB_STATE_SCHEMA_VERSION, "savedAt": time.time(), **state}
    fd, tmp_path = tempfile.mkstemp(dir=job_dir, prefix=".tmp_")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_path, _checkpoint_path(job_id))
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


# --- Schema migration (governing spec Phase 1) --------------------------------------------
# v1 -> v2 introduces the canonical candidate status vocabulary (pending/viable/rejected,
# replacing the overloaded "candidate"/"recommended") and the explicit
# recommendation{outcome, selectedCandidateId, failureReason, missingEvidence,
# leadershipDecisions, createdAt} object — see pipeline_runner.py's
# build_recommendation_state/build_candidate_scores_and_status. Every v1 checkpoint on
# disk (including the permanent HPS stage_failed and Schneider Electric success
# regression fixtures) predates both.
#
# Migration is READ-TIME ONLY: load_job_state() returns the migrated dict in memory but
# never writes it back itself — the original v1 file on disk is untouched until some
# later, explicitly-requested action (a retry, a regenerate — anything that legitimately
# calls save_job_state for this job_id again) saves the checkpoint, at which point it is
# naturally persisted as v2 going forward. This is what satisfies "no automatic overwrite
# of the original version-1 checkpoint" and "explicit controlled save only when later
# requested" without needing a separate opt-in flag anywhere.
def _iso_now():
    return datetime.now(timezone.utc).isoformat()


# Kept self-contained (no import of pipeline_runner's constants) — this module has never
# depended on pipeline_runner and a migration helper is not a good reason to start.
_MIGRATION_CANDIDATE_STATUS_MAP_NARRATIVE_CHOICES = {"candidate": "pending"}
_MIGRATION_CANDIDATE_STATUS_MAP_CRITIQUE = {"candidate": "viable", "recommended": "viable", "rejected": "rejected"}
_MIGRATION_GATE_CRITERIA = ["Strategic fit", "Differentiation", "Evidence strength"]
_MIGRATION_GATE_THRESHOLD = 3


def _migrate_candidate_v1_to_v2(cand, evaluated_at_stage, status_map, migrated_at):
    """Normalizes one candidate dict from its v1 shape. gateResults/rejectionReasons never
    existed in v1, so they're reconstructed from the numeric scores that DID exist
    (scores were already deterministically derived from the same categorical gates by
    GATE_TO_SCORE — see pipeline_runner.py) — an honest reconstruction from the same
    underlying facts, never a fabrication. Borderline scores (== threshold) are labeled
    "borderline_pass", matching build_candidate_scores_and_status's live behavior, so
    migrated and freshly-computed gateResults stay visibly consistent with each other."""
    cand = dict(cand)
    old_status = cand.get("status")
    cand["status"] = status_map.get(old_status, old_status)
    cand.setdefault("statusEvaluatedAtStage", evaluated_at_stage)
    cand.setdefault("statusUpdatedAt", migrated_at)
    if "gateResults" not in cand:
        scores = cand.get("scores") or {}
        gate_results = []
        for criterion in _MIGRATION_GATE_CRITERIA:
            if criterion not in scores:
                continue
            score = scores[criterion]
            outcome = "pass" if score > _MIGRATION_GATE_THRESHOLD else ("borderline_pass" if score == _MIGRATION_GATE_THRESHOLD else "fail")
            gate_results.append({
                "gateId": criterion.lower().replace(" ", "_"),
                "criterion": criterion,
                "outcome": outcome,
                "score": score,
                "threshold": _MIGRATION_GATE_THRESHOLD,
                "margin": score - _MIGRATION_GATE_THRESHOLD,
                "explanation": f"Reconstructed from a schema-version-1 checkpoint's {criterion} score during migration.",
                "evaluatedAtStage": evaluated_at_stage,
            })
        cand["gateResults"] = gate_results
    if "rejectionReasons" not in cand:
        rejection_reasons = []
        if cand["status"] == "rejected":
            failing = [gr for gr in cand["gateResults"] if gr["outcome"] == "fail"]
            if failing:
                rejection_reasons = [{"code": f'{gr["gateId"]}_failed', "gateId": gr["gateId"], "explanation": gr["explanation"]} for gr in failing]
            else:
                rejection_reasons = [{"code": "rejected_pre_migration", "gateId": None, "explanation": "This candidate was rejected before structured gate results were tracked (migrated from schema version 1)."}]
        cand["rejectionReasons"] = rejection_reasons
    return cand


def _migrate_recommendation_section_v1_to_v2(rec_section, migrated_at):
    rec_section = dict(rec_section)
    if rec_section.get("outcome") == "success":
        old_rec = rec_section.get("recommendation") or {}
        narrative_map = rec_section.get("narrativeMap") or {}
        rec_section["recommendation"] = {
            "outcome": "success",
            "selectedCandidateId": old_rec.get("candidateId"),
            "failureReason": None,
            "missingEvidence": old_rec.get("missingEvidence") or [],
            "leadershipDecisions": narrative_map.get("unresolvedQuestions") or [],
            "createdAt": narrative_map.get("createdAt") or migrated_at,
            "detail": {k: v for k, v in old_rec.items() if k != "candidateId"} or None,
        }
    elif rec_section.get("outcome") == "stage_failed":
        last_failure = None
        for attempt in reversed(rec_section.get("attempts") or []):
            if attempt.get("outcome") != "success":
                last_failure = attempt.get("validationFailure")
                break
        rec_section["recommendation"] = {
            "outcome": "stage_failed",
            "selectedCandidateId": None,
            "failureReason": last_failure,
            "missingEvidence": [],
            "leadershipDecisions": [],
            "createdAt": migrated_at,
            "detail": None,
        }
    return rec_section


def _synthesized_no_candidate_passed_section(migrated_at):
    return {
        "outcome": "no_candidate_passed",
        "attempts": [],
        "recommendation": {
            "outcome": "no_candidate_passed",
            "selectedCandidateId": None,
            "failureReason": None,
            "missingEvidence": [],
            "leadershipDecisions": [],
            "createdAt": migrated_at,
            "detail": None,
        },
    }


def migrate_checkpoint_v1_to_v2(data):
    """Pure function: takes a parsed v1 checkpoint dict, returns a new v2-shaped dict.
    Never mutates its input, never touches disk. See this section's module-level comment
    for the read-time-only write policy."""
    migrated_at = _iso_now()
    data = dict(data)

    nc = data.get("narrative_choices")
    if isinstance(nc, dict) and isinstance(nc.get("candidates"), list):
        nc = dict(nc)
        nc["candidates"] = [
            _migrate_candidate_v1_to_v2(c, "narrative_choices", _MIGRATION_CANDIDATE_STATUS_MAP_NARRATIVE_CHOICES, migrated_at)
            for c in nc["candidates"]
        ]
        data["narrative_choices"] = nc

    crit = data.get("critique")
    if isinstance(crit, dict) and isinstance(crit.get("candidates"), list):
        crit = dict(crit)
        crit["candidates"] = [
            _migrate_candidate_v1_to_v2(c, "critique", _MIGRATION_CANDIDATE_STATUS_MAP_CRITIQUE, migrated_at)
            for c in crit["candidates"]
        ]
        data["critique"] = crit

    rec_section = data.get("recommendation_and_map")
    meta = data.get("meta") or {}
    job_terminal = meta.get("status") in ("done", "failed")

    if isinstance(rec_section, dict) and rec_section.get("outcome") in ("success", "stage_failed"):
        data["recommendation_and_map"] = _migrate_recommendation_section_v1_to_v2(rec_section, migrated_at)
    elif rec_section is None and job_terminal and isinstance(crit, dict) and crit.get("outcome") == "success":
        # v1 never called persist_cb for recommendation_and_map on a genuine
        # no_candidate_passed outcome (the exact bug this schema exists to fix) — a
        # terminal job whose critique succeeded with zero viable survivors is
        # unambiguously that case, reconstructible purely from already-migrated data,
        # never a guess.
        migrated_candidates = crit["candidates"]
        if migrated_candidates and all(c.get("status") == "rejected" for c in migrated_candidates):
            data["recommendation_and_map"] = _synthesized_no_candidate_passed_section(migrated_at)

    data["schemaVersion"] = JOB_STATE_SCHEMA_VERSION
    data["schemaMigratedFrom"] = 1
    data["schemaMigratedAt"] = migrated_at
    return data


def load_job_state(job_id):
    """Returns the checkpoint dict, or None if no checkpoint exists yet for this job.
    Raises CorruptedJobStateError if the file exists but isn't valid JSON (or is missing
    schemaVersion), and IncompatibleJobStateError if it parses but carries a schemaVersion
    this code has no migration path for — a caller must never silently proceed with a
    mismatched shape. A v1 checkpoint is migrated to v2 in memory (see
    migrate_checkpoint_v1_to_v2) and returned already-normalized; the file on disk is left
    exactly as it was until something explicitly saves this job_id again."""
    path = _checkpoint_path(job_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise CorruptedJobStateError(f"Job state file for {job_id!r} is corrupted: {exc}") from exc
    if not isinstance(data, dict) or "schemaVersion" not in data:
        raise CorruptedJobStateError(
            f"Job state file for {job_id!r} is missing a schemaVersion — malformed or from an incompatible source"
        )
    version = data["schemaVersion"]
    if version == JOB_STATE_SCHEMA_VERSION:
        return data
    if version == 1 and JOB_STATE_SCHEMA_VERSION == 2:
        return migrate_checkpoint_v1_to_v2(data)
    raise IncompatibleJobStateError(
        f"Job state file for {job_id!r} has schemaVersion {version}, "
        f"this code expects {JOB_STATE_SCHEMA_VERSION} and has no migration path from {version} — incompatible, cannot be loaded"
    )


def delete_job_state(job_id):
    job_dir = _job_dir(job_id)
    if os.path.isdir(job_dir):
        shutil.rmtree(job_dir)


def cleanup_expired_jobs(max_age_seconds=DEFAULT_MAX_AGE_SECONDS, now=None):
    """Deletes any job directory whose checkpoint is older than max_age_seconds, or whose
    checkpoint is missing/corrupted (nothing useful to keep in either case). `now` is
    injectable for deterministic testing. Returns the list of removed job_id strings.
    Called once at backend startup (jobs.py) — this is a local single-user tool with no
    scheduler, so "cleanup rules" are enforced opportunistically rather than on a timer.
    """
    if now is None:
        now = time.time()
    removed = []
    if not os.path.isdir(JOB_STATE_ROOT):
        return removed
    for entry in os.listdir(JOB_STATE_ROOT):
        job_dir = os.path.join(JOB_STATE_ROOT, entry)
        if not os.path.isdir(job_dir):
            continue
        checkpoint_path = os.path.join(job_dir, CHECKPOINT_FILENAME)
        should_remove = not os.path.exists(checkpoint_path)
        if not should_remove:
            try:
                with open(checkpoint_path) as f:
                    data = json.load(f)
                saved_at = data.get("savedAt", 0)
                should_remove = (now - saved_at) > max_age_seconds
            except (json.JSONDecodeError, OSError):
                should_remove = True  # corrupted — nothing useful to keep
        if should_remove:
            shutil.rmtree(job_dir, ignore_errors=True)
            removed.append(entry)
    return removed
