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

JOB_STATE_SCHEMA_VERSION = 1
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


def load_job_state(job_id):
    """Returns the checkpoint dict, or None if no checkpoint exists yet for this job.
    Raises CorruptedJobStateError if the file exists but isn't valid JSON (or is missing
    schemaVersion), and IncompatibleJobStateError if it parses but carries a
    schemaVersion this code doesn't recognize — a caller must never silently proceed with
    a mismatched shape."""
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
    if data["schemaVersion"] != JOB_STATE_SCHEMA_VERSION:
        raise IncompatibleJobStateError(
            f"Job state file for {job_id!r} has schemaVersion {data['schemaVersion']}, "
            f"this code expects {JOB_STATE_SCHEMA_VERSION} — incompatible, cannot be loaded"
        )
    return data


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
