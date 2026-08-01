"""Local-only backend for the 'Analyze a company' live flow.

Exposes the background-job API the frontend polls for stage-by-stage progress
(jobs.py), plus the dev-only /api/fetch-test endpoint kept from the fetch/extract-layer
validation step. Binds to 127.0.0.1 by default — this process is not deployed publicly;
the public GitHub Pages build has no backend at all and degrades gracefully in the
frontend when this server isn't reachable.

For temporary same-Wi-Fi testing from a second device, set STORYMAP_HOST=0.0.0.0 (still
never deployed publicly — this only reaches devices on the same local network/router,
same as any other LAN service) and pass that device's frontend origin in
STORYMAP_ALLOWED_ORIGINS (e.g. "http://10.0.0.104:4173") so CORS stays scoped to exactly
that origin rather than opening up to any origin. The Anthropic API key never leaves this
process either way — it's read once into the Anthropic SDK client (anthropic_pipeline.py)
and never appears in any response body.

Run with: python3 app.py (from inside backend/, with backend/.env holding
ANTHROPIC_API_KEY — see README). The frontend (served separately by ../serve.py) calls
this over CORS since the two run on different local ports.
"""
import json
import os

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, request

import document_extractor
import job_persistence
import jobs
from extractor import extract_readable_text
from fetcher import FetchError, fetch_url
from pipeline_runner import (
    MAX_COMPETITOR_URLS,
    MAX_SUPPORTING_URLS,
    RegenerationLimitReachedError,
    RetryLimitReachedError,
    SourceExpansionLimitReachedError,
    now_iso,
)
from schema_constants import DOCUMENT_ROLES
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

# The frontend/backend wire contract as a whole — distinct from job_persistence's
# JOB_STATE_SCHEMA_VERSION (that one's about checkpoint shape specifically). Bumped only
# on a genuinely breaking change to what /status or any other endpoint returns, so an
# already-open browser tab running stale frontend code has something to detect a mismatch
# against (governing spec §9/§6's "stale frontend assets" gap — Phase 2 adds detection
# only; no UI is wired to this yet, per the approved Phase 2 scope).
API_CONTRACT_VERSION = 1

MAX_URL_LENGTH = 2048
MAX_NARRATIVE_LENGTH = 20000
MAX_INTERNAL_DOCUMENTS = 5
# Hard ceiling on the whole multipart request body — bounds worst-case memory use before
# any per-file logic even runs, regardless of MAX_INTERNAL_DOCUMENTS or
# document_extractor.MAX_FILE_BYTES. 5 files x 20MB + generous multipart/JSON overhead.
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

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


@app.errorhandler(413)
def request_too_large(_exc):
    """Werkzeug enforces app.config["MAX_CONTENT_LENGTH"] before any view function runs —
    without this handler that would surface as Werkzeug's default HTML error page instead
    of the same JSON error shape every other rejection in this API uses. Still passes
    through add_cors_headers (a registered Flask error handler's response goes through
    the normal after_request pipeline), so a rejected oversized upload doesn't also look
    like a CORS failure to the frontend."""
    return jsonify({"error": "Upload exceeds the total request size limit."}), 413


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


def _uploaded_files_from_request():
    """Internal-document files arrive as indexed multipart parts (internalDocument_0,
    internalDocument_1, ...) rather than repeated same-name parts, so file order is never
    ambiguous — sorted numerically here, matching the order the paired
    internalDocumentRoles list (in the "meta" JSON field) was built in on the frontend."""
    indexed = []
    for key in request.files:
        if key.startswith("internalDocument_"):
            try:
                idx = int(key[len("internalDocument_"):])
            except ValueError:
                continue
            indexed.append((idx, request.files[key]))
    return [f for _, f in sorted(indexed, key=lambda pair: pair[0])]


def _process_uploaded_documents(payload):
    """Validates + extracts every uploaded internal document SYNCHRONOUSLY, before any
    job is created — same convention as URL validation just above. Returns
    (uploaded_documents, error_response_or_None). Never reads document content into a log
    line or error message; document_extractor's exceptions already guarantee that (see
    its module docstring)."""
    upload_files = _uploaded_files_from_request()
    document_roles = payload.get("internalDocumentRoles") or []

    if len(upload_files) > MAX_INTERNAL_DOCUMENTS:
        return None, (jsonify({"error": f"At most {MAX_INTERNAL_DOCUMENTS} internal documents are allowed."}), 400)
    if len(document_roles) != len(upload_files):
        return None, (jsonify({"error": "Each uploaded internal document requires exactly one documentRole."}), 400)

    uploaded_documents = []
    used_ids = set()
    for file_storage, role in zip(upload_files, document_roles):
        filename = file_storage.filename or "document.docx"
        if role not in DOCUMENT_ROLES:
            return None, (jsonify({"error": f'"{filename}": unknown documentRole "{role}". Must be one of {DOCUMENT_ROLES}.'}), 400)
        raw_bytes = file_storage.read()
        try:
            extracted = document_extractor.validate_and_extract(filename, raw_bytes)
        except document_extractor.DocumentUploadError as exc:
            return None, (jsonify({"error": str(exc)}), 400)

        base_id = document_extractor.slugify_filename(filename)
        source_id = f"src_upload_{base_id}"
        n = 2
        while source_id in used_ids:
            source_id = f"src_upload_{base_id}_{n}"
            n += 1
        used_ids.add(source_id)

        uploaded_documents.append({
            "id": source_id,
            "title": filename,
            "documentRole": role,
            "flatText": extracted["flatText"],
            "structureBlocks": extracted["structureBlocks"],
            "wordCount": extracted["wordCount"],
            "truncated": extracted["truncated"],
            "retrievedAt": now_iso(),
            "_rawBytes": raw_bytes,  # stripped before this dict is ever persisted to a checkpoint — see analyze_company()
        })
    return uploaded_documents, None


@app.post("/api/analyze-company")
def analyze_company():
    is_multipart = (request.content_type or "").startswith("multipart/form-data")
    if is_multipart:
        try:
            payload = json.loads(request.form.get("meta") or "{}")
        except json.JSONDecodeError:
            return jsonify({"error": '"meta" field must be valid JSON'}), 400
    else:
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

    uploaded_documents = []
    if is_multipart:
        uploaded_documents, error_response = _process_uploaded_documents(payload)
        if error_response is not None:
            return error_response

    # Strip raw bytes out of what gets persisted to the checkpoint (JSON-only, no file
    # content) — kept only in this local list, written straight to disk right after the
    # job (and its directory) exist, never round-tripped through job_persistence's
    # checkpoint mechanism at all.
    raw_bytes_by_id = {doc["id"]: doc.pop("_rawBytes") for doc in uploaded_documents}

    job_id = jobs.create_analyze_job(
        company_url, supporting_urls, competitor_urls, existing_narrative,
        uploaded_documents=uploaded_documents or None,
    )
    for source_id, raw_bytes in raw_bytes_by_id.items():
        job_persistence.save_uploaded_file(job_id, source_id, raw_bytes)

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
    # apiContractVersion is additive — the existing {"status": "ok"} shape is unchanged,
    # and checkBackendAvailable() (live-analysis-service.js) only ever checked res.ok, so
    # no existing caller is affected by this field's presence.
    return jsonify({"status": "ok", "apiContractVersion": API_CONTRACT_VERSION})


jobs.start_worker()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5055))
    # Defaults to loopback-only, matching this module's own docstring. Only ever becomes
    # 0.0.0.0 (reachable from other devices on the same local network) when an operator
    # explicitly opts in via STORYMAP_HOST for a temporary same-Wi-Fi test — never a
    # public deployment, and never the default.
    host = os.environ.get("STORYMAP_HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=False, threaded=True)
