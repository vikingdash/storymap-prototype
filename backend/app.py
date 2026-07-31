"""Local-only backend for the 'Analyze a company' live flow.

Exposes the background-job API the frontend polls for stage-by-stage progress
(jobs.py), plus the dev-only /api/fetch-test endpoint kept from the fetch/extract-layer
validation step. Binds to 127.0.0.1 only — this process is never exposed on the network
and is not deployed publicly; the public GitHub Pages build has no backend at all and
degrades gracefully in the frontend when this server isn't reachable.

Run with: python3 app.py (from inside backend/, with backend/.env holding
ANTHROPIC_API_KEY — see README). The frontend (served separately by ../serve.py) calls
this over CORS since the two run on different local ports.
"""
import os

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, request

import jobs
from extractor import extract_readable_text
from fetcher import FetchError, fetch_url
from pipeline_runner import (
    MAX_COMPETITOR_URLS,
    MAX_SUPPORTING_URLS,
    RegenerationLimitReachedError,
    RetryLimitReachedError,
    SourceExpansionLimitReachedError,
)
from ssrf_guard import UnsafeUrlError, assert_safe_url

# Maps the public retry endpoint's <stage> path segment to jobs.py's internal retry job
# "kind" strings (which in turn map 1:1 to pipeline_runner's 5 stage names) — see
# jobs.RETRY_KIND_TO_STAGE. Kept as an explicit allowlist rather than accepting an
# arbitrary stage name directly in the URL.
RETRY_STAGE_TO_KIND = {
    "foundation": "retry_foundation",
    "diagnosis": "retry_diagnosis",
    "candidates": "retry_candidates",
    "critique": "retry_critique",
    "recommendation": "retry_recommendation",
}

app = Flask(__name__)

MAX_URL_LENGTH = 2048
MAX_NARRATIVE_LENGTH = 20000

ALLOWED_ORIGINS = {
    o.strip()
    for o in os.environ.get(
        "STORYMAP_ALLOWED_ORIGINS",
        "http://127.0.0.1:4173,http://localhost:4173",
    ).split(",")
    if o.strip()
}


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Vary"] = "Origin"
    return response


@app.route("/api/<path:_unused>", methods=["OPTIONS"])
def cors_preflight(_unused):
    return ("", 204)


def _clean_url_list(value, max_count, field_name):
    if value is None:
        return [], None
    if not isinstance(value, list):
        return None, f'"{field_name}" must be an array of strings'
    if len(value) > max_count:
        return None, f'"{field_name}" may contain at most {max_count} URLs'
    cleaned = []
    for item in value:
        if not isinstance(item, str):
            return None, f'"{field_name}" entries must be strings'
        item = item.strip()
        if not item:
            continue
        if len(item) > MAX_URL_LENGTH:
            return None, f'"{field_name}" entry exceeds {MAX_URL_LENGTH} characters'
        cleaned.append(item)
    return cleaned, None


@app.post("/api/analyze-company")
def analyze_company():
    payload = request.get_json(silent=True) or {}
    company_url = (payload.get("companyUrl") or "").strip()
    existing_narrative = (payload.get("existingNarrative") or "").strip()

    if not company_url:
        return jsonify({"error": 'Missing required field: "companyUrl"'}), 400
    if len(company_url) > MAX_URL_LENGTH:
        return jsonify({"error": f"companyUrl exceeds {MAX_URL_LENGTH} characters"}), 400
    if len(existing_narrative) > MAX_NARRATIVE_LENGTH:
        return jsonify({"error": f"existingNarrative exceeds {MAX_NARRATIVE_LENGTH} characters"}), 400

    supporting_urls, err = _clean_url_list(payload.get("supportingUrls"), MAX_SUPPORTING_URLS, "supportingUrls")
    if err:
        return jsonify({"error": err}), 400
    competitor_urls, err = _clean_url_list(payload.get("competitorUrls"), MAX_COMPETITOR_URLS, "competitorUrls")
    if err:
        return jsonify({"error": err}), 400

    try:
        assert_safe_url(company_url)
    except UnsafeUrlError as exc:
        return jsonify({"error": f"companyUrl: {exc}"}), 400
    for url in supporting_urls + competitor_urls:
        try:
            assert_safe_url(url)
        except UnsafeUrlError as exc:
            return jsonify({"error": f"{url}: {exc}"}), 400

    job_id = jobs.create_analyze_job(company_url, supporting_urls, competitor_urls, existing_narrative)
    return jsonify({"jobId": job_id}), 202


@app.post("/api/regenerate")
def regenerate():
    """Amends an EXISTING job in place (jobs.create_regenerate_job never mints a new
    job_id — the original sourceJobId remains canonical; poll it, not a different id).
    Expects the full original intake context resent alongside the edit — companyUrl,
    supportingUrls, competitorUrls, existingNarrative, editedFoundation — even though
    only existingNarrative and editedFoundation actually feed the pipeline here (nothing
    is re-fetched: the job's checkpoint already has sources/evidence pool). Requiring the
    full bundle keeps a regenerate request a complete, self-describing "redo this
    analysis with an edit," not a partial one that's easy to silently drop a field from
    (existingNarrative was dropped exactly this way before this validation existed).

    Shape AND semantic validation of editedFoundation (required keys, plus the same
    statement-type consistency rules a model-generated choice has to pass) happens
    inside jobs.create_regenerate_job via pipeline_runner.validate_edited_foundation —
    a single validator shared with anything else that ever needs to accept a foundation
    edit, rather than a duplicate ad hoc check living here.

    A job may be regenerated at most pipeline_runner.MAX_FULL_REGENERATIONS (2) times —
    checked, and the persisted count incremented, atomically under jobs.create_regenerate_job's
    per-job lock, before any validation or API call. A validation failure of the
    submitted edit never consumes the allowance."""
    payload = request.get_json(silent=True) or {}
    source_job_id = (payload.get("sourceJobId") or "").strip()
    edited_foundation = payload.get("editedFoundation")
    existing_narrative = (payload.get("existingNarrative") or "").strip()
    company_url = (payload.get("companyUrl") or "").strip()

    if not source_job_id:
        return jsonify({"error": 'Missing required field: "sourceJobId"'}), 400
    if not company_url:
        return jsonify({"error": 'Missing required field: "companyUrl" (resend the original intake context)'}), 400
    if edited_foundation is None:
        return jsonify({"error": 'Missing required field: "editedFoundation"'}), 400

    supporting_urls, err = _clean_url_list(payload.get("supportingUrls"), MAX_SUPPORTING_URLS, "supportingUrls")
    if err:
        return jsonify({"error": err}), 400
    competitor_urls, err = _clean_url_list(payload.get("competitorUrls"), MAX_COMPETITOR_URLS, "competitorUrls")
    if err:
        return jsonify({"error": err}), 400

    try:
        job_id = jobs.create_regenerate_job(source_job_id, edited_foundation, existing_narrative)
    except KeyError:
        return jsonify({"error": f"Unknown sourceJobId: {source_job_id}"}), 404
    except RegenerationLimitReachedError as exc:
        return jsonify({"error": "regeneration_limit_reached", "detail": str(exc)}), 429
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"jobId": job_id}), 202


@app.post("/api/analyze-company/<job_id>/expand-sources")
def expand_sources(job_id):
    """Amends an EXISTING job in place (jobs.create_expand_sources_job never mints a new
    job_id — job_id in the URL remains canonical; poll it, not a different id) by
    re-fetching with an EXPANDED source set and rerunning the full pipeline from
    strategic_foundation onward. This is genuinely different from /api/regenerate: adding
    new URLs requires a real re-fetch, which regenerate explicitly never does.

    Full resend, same philosophy as /regenerate: companyUrl, supportingUrls,
    competitorUrls. companyUrl is required and validated server-side against the job's
    ORIGINAL company URL — the server always re-fetches its own stored URL, never a
    client-resent one, so a request can never silently repurpose an existing job's
    identity to a different company via the same job_id (jobs.create_expand_sources_job
    rejects a mismatch with 400). At least one supporting or competitor URL is required —
    an empty resend would just re-fetch nothing new and waste one of the two allowed
    expansions for no benefit.

    A job may have its sources expanded at most pipeline_runner.MAX_SOURCE_EXPANSIONS (2)
    times — checked, and the persisted count incremented, atomically under
    jobs.create_expand_sources_job's per-job lock, before any fetch or API call. Tracked
    entirely independently of /regenerate's MAX_FULL_REGENERATIONS cap (see
    MAX_SOURCE_EXPANSIONS's docstring for why the two are never shared)."""
    payload = request.get_json(silent=True) or {}
    company_url = (payload.get("companyUrl") or "").strip()

    if not company_url:
        return jsonify({"error": 'Missing required field: "companyUrl" (resend the original intake context)'}), 400
    if len(company_url) > MAX_URL_LENGTH:
        return jsonify({"error": f"companyUrl exceeds {MAX_URL_LENGTH} characters"}), 400

    supporting_urls, err = _clean_url_list(payload.get("supportingUrls"), MAX_SUPPORTING_URLS, "supportingUrls")
    if err:
        return jsonify({"error": err}), 400
    competitor_urls, err = _clean_url_list(payload.get("competitorUrls"), MAX_COMPETITOR_URLS, "competitorUrls")
    if err:
        return jsonify({"error": err}), 400
    if not supporting_urls and not competitor_urls:
        return jsonify({"error": 'At least one "supportingUrls" or "competitorUrls" entry is required to add sources.'}), 400

    for url in supporting_urls + competitor_urls:
        try:
            assert_safe_url(url)
        except UnsafeUrlError as exc:
            return jsonify({"error": f"{url}: {exc}"}), 400

    try:
        result_job_id = jobs.create_expand_sources_job(job_id, company_url, supporting_urls, competitor_urls)
    except KeyError:
        return jsonify({"error": f"Unknown job id: {job_id}"}), 404
    except SourceExpansionLimitReachedError as exc:
        return jsonify({"error": "source_expansion_limit_reached", "detail": str(exc)}), 429
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"jobId": result_job_id}), 202


@app.get("/api/analyze-company/<job_id>/status")
def job_status(job_id):
    """usage/stageProgress are additive fields — a client that hasn't been updated to
    read them keeps working unchanged; every other key's shape/meaning is unmodified.
    .get() with a default handles the (practically unreachable, but real) narrow window
    where jobs.get_job() falls back to the raw in-memory JOBS entry for a job whose
    first checkpoint write hasn't landed yet — that record predates both fields."""
    job = jobs.get_job(job_id)
    if job is None:
        return jsonify({"error": f"Unknown job id: {job_id}"}), 404
    return jsonify({
        "id": job["id"],
        "kind": job["kind"],
        "status": job["status"],
        "stage": job["stage"],
        "dataset": job["dataset"],
        "diagnostics": job["diagnostics"],
        "error": job["error"],
        "usage": job.get("usage"),
        "stageProgress": job.get("stageProgress"),
        "sourceCoverage": job.get("sourceCoverage"),
    })


@app.post("/api/analyze-company/<job_id>/retry/<stage>")
def retry_stage(job_id, stage):
    """Manually, deliberately retries exactly one failed stage of an existing job — one
    attempt, real API call, real cost. Not wired into the frontend yet; this endpoint
    exists to be called directly (curl/Postman) until the frontend flow is built.

    <stage> is one of foundation|diagnosis|candidates|critique|recommendation. Confirms,
    before spending anything and ATOMICALLY under a per-job lock (jobs._get_job_lock):
    the job's checkpoint exists (404 if not); every stage the requested one depends on
    already succeeded (400 if not); the stage hasn't already used its one allowed manual
    retry (429 retry_limit_reached if it has — see pipeline_runner.MAX_MANUAL_RETRIES);
    the stage doesn't already have a manual retry in flight from a concurrent request
    (429 retry_in_progress); and, for foundation specifically, that it wasn't manually
    edited via /api/regenerate (400 if it was — retrying it would silently discard that
    edit). job_id is ALWAYS the original, canonical job — this never mints a separate
    id; poll the same job_id you retried to see the corrected result, including across a
    backend restart.
    """
    retry_kind = RETRY_STAGE_TO_KIND.get(stage)
    if retry_kind is None:
        return jsonify({"error": f"Unknown retry stage: {stage!r}. Must be one of {sorted(RETRY_STAGE_TO_KIND)}"}), 404
    try:
        jobs.create_retry_job(retry_kind, job_id)
    except KeyError:
        return jsonify({"error": f"Unknown job id: {job_id}"}), 404
    except RetryLimitReachedError as exc:
        return jsonify({"error": exc.code, "detail": str(exc)}), 429
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"jobId": job_id}), 202


@app.post("/api/fetch-test")
def fetch_test():
    """Dev-only endpoint for the fetch+extract layer in isolation, kept from the earlier
    build step. Not used by the production 'Analyze a company' flow."""
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()

    if not url:
        return jsonify({"error": "Missing required field: url"}), 400
    if len(url) > MAX_URL_LENGTH:
        return jsonify({"error": f"URL exceeds {MAX_URL_LENGTH} characters"}), 400

    try:
        assert_safe_url(url)
    except UnsafeUrlError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        fetched = fetch_url(url)
    except FetchError as exc:
        return jsonify({"error": str(exc)}), 502

    extracted = extract_readable_text(fetched["html"], fetched["final_url"])

    return jsonify(
        {
            "requested_url": fetched["url"],
            "final_url": fetched["final_url"],
            "status_code": fetched["status_code"],
            "title": extracted["title"],
            "extraction_method": extracted["method"],
            "word_count": extracted["word_count"],
            "truncated": extracted["truncated"],
            "text": extracted["text"],
        }
    )


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


jobs.start_worker()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5055))
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
