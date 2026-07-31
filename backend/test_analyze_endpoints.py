"""Endpoint tests for the background-job API — no network access, no Anthropic API calls.

CRITICAL SAFETY NOTE: the worker thread in jobs.py processes jobs asynchronously. A
`with patch("jobs.run_analysis", ...)` block that only wraps the POST request (not the
subsequent poll) can exit — unpatching back to the REAL run_analysis — before the
background thread actually dequeues and calls it. If a real ANTHROPIC_API_KEY happens to
be loaded (e.g. from backend/.env via app.py's load_dotenv()), that race lets a real,
unaccounted-for, paid API call slip through a "no cost" test suite. This happened once
during development. Fixed two ways, both required:
  1. ANTHROPIC_API_KEY is overwritten with a bogus value BEFORE importing app/jobs at all.
     python-dotenv's load_dotenv() does not override an already-set variable by default,
     so app.py's own load_dotenv() call becomes a no-op for this key in the test process.
  2. Every test that creates a job keeps its patch active for the job's entire lifecycle
     (setUp/tearDown-scoped patches, not a `with` block that exits before polling) and
     drains the job queue in tearDown before unpatching, so no job can ever be processed
     by an unpatched function even if scheduling is unlucky.

Run with: python3 -m unittest test_analyze_endpoints -v
"""
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, ANY

os.environ["ANTHROPIC_API_KEY"] = "sk-test-do-not-use-not-a-real-key"

import job_persistence
import jobs
from app import app
from pipeline_runner import PipelineError, check_manual_retry_allowed

_TEST_JOB_STATE_ROOT = None
_REAL_JOB_STATE_ROOT = job_persistence.JOB_STATE_ROOT


def setUpModule():
    # jobs.py's _run_job() writes a real on-disk checkpoint via job_persistence for every
    # job it processes (not just ones that reach a real API call) — redirect that to a
    # throwaway temp directory so this "no network, no API calls" suite never touches the
    # real backend/job_state/ directory or leaves files behind.
    global _TEST_JOB_STATE_ROOT
    _TEST_JOB_STATE_ROOT = tempfile.mkdtemp(prefix="storymap_test_job_state_")
    job_persistence.JOB_STATE_ROOT = _TEST_JOB_STATE_ROOT


def tearDownModule():
    # Restore the real root, not just delete the temp dir — otherwise a test module that
    # runs later in the same `discover` process (e.g. test_job_persistence.py, which
    # saves/restores whatever JOB_STATE_ROOT it finds) would inherit a pointer to a
    # directory that no longer exists.
    job_persistence.JOB_STATE_ROOT = _REAL_JOB_STATE_ROOT
    shutil.rmtree(_TEST_JOB_STATE_ROOT, ignore_errors=True)


def _poll_until_terminal(client, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/api/analyze-company/{job_id}/status")
        body = resp.get_json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.01)
    raise TimeoutError(f"Job {job_id} did not reach a terminal state within {timeout}s")


FAKE_SUCCESS_RESULT = {
    "dataset": {
        "caseContext": {"id": "live", "selectorLabel": "Analyze a company", "selectorDescription": "x", "company": {"name": "Acme", "oneLiner": ""}},
        "sources": [],
        "evidence": [],
        "strategicFoundation": [],
        "diagnosis": [],
        "candidates": [],
        "recommendation": {"candidateId": "cand1"},
        "narrativeMap": {"id": "map1"},
        "audiences": [],
        "competitorContrasts": [],
    },
    "diagnostics": {"critical_failure": None, "api_calls": [], "token_totals": {"input_tokens": 0, "output_tokens": 0}},
    "context": {"sources": [], "source_text_by_id": {}, "evidence_pool": {}},
}

WELL_FORMED_FOUNDATION_ITEM = {
    "id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact", "evidence": [],
}

# A real run_analysis()/regenerate_from() calls persist_cb once per stage as it goes —
# jobs.py's dataset is now ALWAYS reconstructed fresh from those persisted sections
# (never trusted as one static blob returned at the end), which is exactly what makes
# stale post-edit data structurally impossible to return. A bare
# `return_value=FAKE_SUCCESS_RESULT` mock bypasses persist_cb entirely, so any test that
# needs a realistic checkpoint (regenerate/retry preconditions, or the final dataset
# itself) must use this side_effect instead, which does both: seeds the sections a real
# run would have, and returns the fake result dict.
def _fake_run_with_sections(fake_result):
    def side_effect(*args, progress_cb=None, persist_cb=None, **kwargs):
        ds = fake_result["dataset"]
        if persist_cb is not None and ds is not None:
            persist_cb("fetching_sources", {"sources": ds.get("sources", []), "sourceTextById": {}, "fetchFailures": [], "caseContext": ds.get("caseContext")})
            persist_cb("strategic_foundation", {"outcome": "success", "strategicFoundation": ds.get("strategicFoundation", []), "evidencePool": {}})
            persist_cb("diagnosis", {"outcome": "success", "diagnosis": ds.get("diagnosis", []), "competitorContrasts": ds.get("competitorContrasts", []), "evidencePool": {}})
            persist_cb("narrative_choices", {"outcome": "success", "candidates": ds.get("candidates", [])})
            persist_cb("critique", {"outcome": "success", "candidates": ds.get("candidates", [])})
            persist_cb("recommendation_and_map", {"outcome": "success", "recommendation": ds.get("recommendation"), "narrativeMap": ds.get("narrativeMap"), "audiences": ds.get("audiences", [])})
        return fake_result
    return side_effect


FAKE_NO_CANDIDATE_RESULT = {
    "dataset": {
        "caseContext": {"id": "live", "selectorLabel": "Analyze a company", "selectorDescription": "x", "company": {"name": "Acme", "oneLiner": ""}},
        "sources": [], "evidence": [], "strategicFoundation": [{"id": "sf1"}], "diagnosis": [{"id": "d1"}],
        "candidates": [{"id": "cand1", "status": "rejected"}], "recommendation": None, "narrativeMap": None,
        "audiences": [], "competitorContrasts": [],
    },
    "diagnostics": {"critical_failure": "no_candidate_passed", "api_calls": [], "token_totals": {"input_tokens": 0, "output_tokens": 0}},
    "context": {"sources": [], "source_text_by_id": {}, "evidence_pool": {}},
}


class InputValidation(unittest.TestCase):
    """None of these should ever reach jobs.create_analyze_job — validation fails first —
    so no patching is needed, but the neutralized API key (module-level, above) still
    protects against a validation-logic bug accidentally letting one through."""

    def setUp(self):
        self.client = app.test_client()

    def test_missing_company_url_returns_400(self):
        resp = self.client.post("/api/analyze-company", json={})
        self.assertEqual(resp.status_code, 400)

    def test_too_many_supporting_urls_returns_400(self):
        resp = self.client.post("/api/analyze-company", json={
            "companyUrl": "https://example.com",
            "supportingUrls": [f"https://example.com/{i}" for i in range(6)],
        })
        self.assertEqual(resp.status_code, 400)

    def test_too_many_competitor_urls_returns_400(self):
        resp = self.client.post("/api/analyze-company", json={
            "companyUrl": "https://example.com",
            "competitorUrls": [f"https://example.com/{i}" for i in range(4)],
        })
        self.assertEqual(resp.status_code, 400)

    def test_unsafe_company_url_returns_400(self):
        resp = self.client.post("/api/analyze-company", json={"companyUrl": "http://localhost/"})
        self.assertEqual(resp.status_code, 400)

    def test_unsafe_metadata_ip_in_supporting_urls_returns_400(self):
        resp = self.client.post("/api/analyze-company", json={
            "companyUrl": "https://example.com",
            "supportingUrls": ["http://169.254.169.254/"],
        })
        self.assertEqual(resp.status_code, 400)

    def test_regenerate_missing_source_job_id_returns_400(self):
        resp = self.client.post("/api/regenerate", json={"editedFoundation": [{"id": "x"}]})
        self.assertEqual(resp.status_code, 400)

    def test_regenerate_unknown_source_job_returns_404(self):
        resp = self.client.post("/api/regenerate", json={
            "sourceJobId": "does-not-exist", "companyUrl": "https://example.com",
            "editedFoundation": [WELL_FORMED_FOUNDATION_ITEM],
        })
        self.assertEqual(resp.status_code, 404)

    def test_regenerate_missing_edited_foundation_returns_400(self):
        resp = self.client.post("/api/regenerate", json={"sourceJobId": "whatever", "companyUrl": "https://example.com"})
        self.assertEqual(resp.status_code, 400)

    def test_unknown_job_status_returns_404(self):
        resp = self.client.get("/api/analyze-company/does-not-exist/status")
        self.assertEqual(resp.status_code, 404)


class JobLifecycle(unittest.TestCase):
    """Every test here patches jobs.run_analysis/jobs.regenerate_from for its ENTIRE
    duration via setUp/tearDown (not a `with` block scoped only around the POST), and
    tearDown blocks on the queue draining before unpatching — see the module docstring
    for why the narrower pattern is unsafe with a background worker thread."""

    def setUp(self):
        self.client = app.test_client()
        self._patchers = []

    def tearDown(self):
        jobs._QUEUE.join()  # ensure the worker has finished processing before we unpatch
        for p in self._patchers:
            p.stop()

    def _patch(self, target, **kwargs):
        p = patch(target, **kwargs)
        p.start()
        self._patchers.append(p)

    def test_analyze_company_returns_202_and_job_id(self):
        self._patch("jobs.run_analysis", side_effect=_fake_run_with_sections(FAKE_SUCCESS_RESULT))
        resp = self.client.post("/api/analyze-company", json={"companyUrl": "https://example.com"})
        self.assertEqual(resp.status_code, 202)
        job_id = resp.get_json()["jobId"]
        self.assertIn("jobId", resp.get_json())
        _poll_until_terminal(self.client, job_id)  # wait for completion before tearDown drains the queue

    def test_successful_job_reaches_done_with_dataset(self):
        self._patch("jobs.run_analysis", side_effect=_fake_run_with_sections(FAKE_SUCCESS_RESULT))
        job_id = self.client.post("/api/analyze-company", json={"companyUrl": "https://example.com"}).get_json()["jobId"]
        final = _poll_until_terminal(self.client, job_id)
        self.assertEqual(final["status"], "done")
        self.assertIsNotNone(final["dataset"])
        self.assertEqual(final["dataset"]["recommendation"]["candidateId"], "cand1")

    def test_no_candidate_passed_is_done_not_failed(self):
        """A valid terminal state, not an error — the frontend must render 'StoryMap
        cannot yet recommend a direction,' not a generic failure screen. The dataset is
        NOT None — whatever succeeded (strategicFoundation, diagnosis, candidates) is
        still preserved and returned; only recommendation/narrativeMap are empty."""
        self._patch("jobs.run_analysis", side_effect=_fake_run_with_sections(FAKE_NO_CANDIDATE_RESULT))
        job_id = self.client.post("/api/analyze-company", json={"companyUrl": "https://example.com"}).get_json()["jobId"]
        final = _poll_until_terminal(self.client, job_id)
        self.assertEqual(final["status"], "done")
        self.assertIsNotNone(final["dataset"])
        self.assertIsNone(final["dataset"]["recommendation"])
        self.assertTrue(final["dataset"]["strategicFoundation"])
        self.assertEqual(final["diagnostics"]["critical_failure"], "no_candidate_passed")

    def test_pipeline_error_marks_job_failed(self):
        self._patch("jobs.run_analysis", side_effect=PipelineError("could not fetch company URL"))
        job_id = self.client.post("/api/analyze-company", json={"companyUrl": "https://example.com"}).get_json()["jobId"]
        final = _poll_until_terminal(self.client, job_id)
        self.assertEqual(final["status"], "failed")
        self.assertIn("could not fetch", final["error"])

    def test_unexpected_exception_marks_job_failed_not_crashes_worker(self):
        self._patch("jobs.run_analysis", side_effect=RuntimeError("boom"))
        job_id = self.client.post("/api/analyze-company", json={"companyUrl": "https://example.com"}).get_json()["jobId"]
        final = _poll_until_terminal(self.client, job_id)
        self.assertEqual(final["status"], "failed")
        jobs._QUEUE.join()
        for p in self._patchers:
            p.stop()
        self._patchers = []
        # The worker thread must still be alive and able to process a subsequent job.
        self._patch("jobs.run_analysis", side_effect=_fake_run_with_sections(FAKE_SUCCESS_RESULT))
        job_id2 = self.client.post("/api/analyze-company", json={"companyUrl": "https://example.com"}).get_json()["jobId"]
        final2 = _poll_until_terminal(self.client, job_id2)
        self.assertEqual(final2["status"], "done")

    def test_regenerate_reuses_stored_context_from_source_job(self):
        self._patch("jobs.run_analysis", side_effect=_fake_run_with_sections(FAKE_SUCCESS_RESULT))
        source_job_id = self.client.post("/api/analyze-company", json={"companyUrl": "https://example.com"}).get_json()["jobId"]
        _poll_until_terminal(self.client, source_job_id)

        mock_regen = patch("jobs.regenerate_from", return_value=FAKE_SUCCESS_RESULT)
        mock_regen_obj = mock_regen.start()
        self._patchers.append(mock_regen)

        resp = self.client.post("/api/regenerate", json={
            "sourceJobId": source_job_id, "companyUrl": "https://example.com",
            "editedFoundation": [WELL_FORMED_FOUNDATION_ITEM],
        })
        self.assertEqual(resp.status_code, 202)
        regen_job_id = resp.get_json()["jobId"]
        final = _poll_until_terminal(self.client, regen_job_id)
        self.assertEqual(final["status"], "done")
        mock_regen_obj.assert_called_once()

    def test_regenerate_missing_company_url_returns_400(self):
        """companyUrl is now required on /api/regenerate — the full original intake
        context must be resent, not just editedFoundation, so a partial request that
        silently drops a field (as existingNarrative was silently dropped before this
        validation existed) fails loudly instead of quietly losing data."""
        self._patch("jobs.run_analysis", side_effect=_fake_run_with_sections(FAKE_SUCCESS_RESULT))
        source_job_id = self.client.post("/api/analyze-company", json={"companyUrl": "https://example.com"}).get_json()["jobId"]
        _poll_until_terminal(self.client, source_job_id)

        resp = self.client.post("/api/regenerate", json={"sourceJobId": source_job_id, "editedFoundation": [{"id": "sf1"}]})
        self.assertEqual(resp.status_code, 400)

    def test_regenerate_preserves_existing_narrative(self):
        """The actual bug being fixed: existingNarrative was hardcoded to "" by the
        frontend on every regenerate call, silently discarding whatever the user typed
        into the intake screen. This verifies the backend threads whatever value is sent
        through to regenerate_from() unmodified — the frontend-side fix (remembering and
        resending it) is verified by code review, not an automated test, since this
        sandbox has no JS runtime."""
        self._patch("jobs.run_analysis", side_effect=_fake_run_with_sections(FAKE_SUCCESS_RESULT))
        source_job_id = self.client.post("/api/analyze-company", json={"companyUrl": "https://example.com"}).get_json()["jobId"]
        _poll_until_terminal(self.client, source_job_id)

        mock_regen = patch("jobs.regenerate_from", return_value=FAKE_SUCCESS_RESULT)
        mock_regen_obj = mock_regen.start()
        self._patchers.append(mock_regen)

        narrative_text = "Our current positioning is 'simple, powerful, reliable.'"
        resp = self.client.post("/api/regenerate", json={
            "sourceJobId": source_job_id,
            "companyUrl": "https://example.com",
            "supportingUrls": ["https://example.com/about"],
            "competitorUrls": ["https://rival.example.com"],
            "existingNarrative": narrative_text,
            "editedFoundation": [{**WELL_FORMED_FOUNDATION_ITEM, "statement": "edited"}],
        })
        self.assertEqual(resp.status_code, 202)
        regen_job_id = resp.get_json()["jobId"]
        _poll_until_terminal(self.client, regen_job_id)

        mock_regen_obj.assert_called_once()
        call_args = mock_regen_obj.call_args[0]
        # regenerate_from(sources, source_text_by_id, evidence_pool, edited_foundation, existing_narrative, progress_cb=...)
        self.assertEqual(call_args[4], narrative_text)


def _seed_checkpoint_job(**sections):
    """Creates a REAL in-memory job (so it's addressable via jobs.get_job()/the /status
    endpoint, exactly like a real analyze job) whose run_analysis is stubbed to fail
    immediately (never a real fetch or API call), then overwrites its on-disk checkpoint
    with exactly the sections this test wants — full control over the fixture without
    needing a real pipeline run to produce it. Module-level so any test class can build a
    precise checkpoint fixture, not just RetryEndpoints."""
    seed_patch = patch("jobs.run_analysis", side_effect=PipelineError("test fixture seed, not a real run"))
    seed_patch.start()
    job_id = jobs.create_analyze_job("https://example.com", [], [], "")
    jobs._QUEUE.join()
    seed_patch.stop()
    job_persistence.save_job_state(job_id, sections)
    return job_id


class RetryEndpoints(unittest.TestCase):
    """The 5 manual retry endpoints (POST /api/analyze-company/<job_id>/retry/<stage>) —
    not wired into the frontend yet, but must work standalone: validate before spending
    anything, dispatch through the real single-worker job queue exactly like an analyze
    job, and durably update the source job's checkpoint. Builds real checkpoints via
    job_persistence directly (redirected to the temp dir by setUpModule) rather than
    going through a full analyze run, and patches the underlying anthropic_pipeline stage
    functions (not jobs.run_analysis) since retry dispatch calls pipeline_runner's real
    retry_xxx() functions."""

    def setUp(self):
        self.client = app.test_client()
        self.addCleanup(patch.stopall)
        patch("anthropic_pipeline.get_client", return_value=object()).start()

    def _seed_checkpoint(self, **sections):
        return _seed_checkpoint_job(**sections)

    def _poll(self, job_id):
        return _poll_until_terminal(self.client, job_id)

    def test_unknown_retry_stage_returns_404(self):
        resp = self.client.post("/api/analyze-company/some-job/retry/not-a-real-stage")
        self.assertEqual(resp.status_code, 404)

    def test_unknown_job_id_returns_404(self):
        resp = self.client.post("/api/analyze-company/does-not-exist/retry/diagnosis")
        self.assertEqual(resp.status_code, 404)

    def test_missing_upstream_stage_returns_400_without_calling_the_api(self):
        mock_diagnose = patch("anthropic_pipeline.diagnose").start()
        job_id = self._seed_checkpoint(fetching_sources={"sources": []})  # no strategic_foundation yet
        resp = self.client.post(f"/api/analyze-company/{job_id}/retry/diagnosis")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("strategic_foundation", resp.get_json()["error"])
        mock_diagnose.assert_not_called()

    def test_upstream_stage_that_previously_failed_returns_400(self):
        job_id = self._seed_checkpoint(
            fetching_sources={"sources": []},
            strategic_foundation={"outcome": "stage_failed"},
        )
        resp = self.client.post(f"/api/analyze-company/{job_id}/retry/diagnosis")
        self.assertEqual(resp.status_code, 400)

    def test_retry_foundation_success_updates_checkpoint(self):
        sources = [{"id": "src1", "companyId": "live", "title": "Co", "publisher": "co.com",
                     "sourceType": "website", "url": "https://co.com", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"}]
        job_id = self._seed_checkpoint(
            jobInput={"existingNarrative": ""},
            fetching_sources={"sources": sources, "sourceTextById": {"src1": "The company serves manufacturing customers."}},
        )
        foundation_result = {
            "evidence": [{"id": "ev1", "sourceId": "src1", "excerpt": "The company serves manufacturing customers.",
                          "paraphrase": "p", "evidenceType": "statement", "strength": "moderate", "freshness": "current"}],
            "strategicFoundation": [{"id": "sf1", "type": "customer", "statement": "Serves manufacturing customers.",
                                      "statementType": "source_fact", "evidence": [{"evidenceId": "ev1", "relevance": "direct", "rationale": "r"}]}],
        }
        patch("anthropic_pipeline.extract_foundation", return_value=foundation_result).start()

        resp = self.client.post(f"/api/analyze-company/{job_id}/retry/foundation")
        self.assertEqual(resp.status_code, 202)
        retry_job_id = resp.get_json()["jobId"]
        final = self._poll(retry_job_id)
        self.assertEqual(final["status"], "done")
        self.assertEqual(len(final["dataset"]["strategicFoundation"]), 1)

        checkpoint = job_persistence.load_job_state(job_id)
        self.assertEqual(checkpoint["strategic_foundation"]["outcome"], "success")
        self.assertEqual(checkpoint["strategic_foundation"]["retryCount"], 1)

    def test_retry_diagnosis_success_reflects_on_original_job_status(self):
        sources = [{"id": "src1", "companyId": "live", "title": "Co", "publisher": "co.com",
                     "sourceType": "website", "url": "https://co.com", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"}]
        evidence_pool = {"ev1": {"id": "ev1", "sourceId": "src1", "excerpt": "x", "paraphrase": "p",
                                  "evidenceType": "statement", "strength": "moderate", "freshness": "current", "verified": True, "confidence": 0.95}}
        job_id = self._seed_checkpoint(
            jobInput={"existingNarrative": ""},
            fetching_sources={"sources": sources, "sourceTextById": {"src1": "text"}},
            strategic_foundation={
                "outcome": "success",
                "strategicFoundation": [{"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact"}],
                "evidencePool": evidence_pool,
            },
        )
        diagnose_result = {
            "evidence": [], "diagnosis": [{"id": "d1", "title": "t", "explanation": "e", "significance": "medium",
                                            "statementType": "source_fact", "evidence": [{"evidenceId": "ev1", "relevance": "direct", "rationale": "r"}]}],
            "competitorOverlapAssessed": False, "competitorOverlapNote": "", "competitorContrasts": [],
        }
        patch("anthropic_pipeline.diagnose", return_value=diagnose_result).start()

        resp = self.client.post(f"/api/analyze-company/{job_id}/retry/diagnosis")
        self.assertEqual(resp.status_code, 202)
        retry_job_id = resp.get_json()["jobId"]
        self._poll(retry_job_id)

        # The ORIGINAL job_id (not just the retry job's own id) must also reflect the fix.
        original_status = self.client.get(f"/api/analyze-company/{job_id}/status").get_json()
        self.assertEqual(original_status["status"], "done")
        self.assertEqual(len(original_status["dataset"]["diagnosis"]), 1)

    def test_retry_diagnosis_appends_a_new_attempt_to_history_not_overwrites(self):
        sources = [{"id": "src1", "companyId": "live", "title": "Co", "publisher": "co.com",
                     "sourceType": "website", "url": "https://co.com", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"}]
        job_id = self._seed_checkpoint(
            jobInput={"existingNarrative": ""},
            fetching_sources={"sources": sources, "sourceTextById": {"src1": "text"}},
            strategic_foundation={
                "outcome": "success",
                "strategicFoundation": [{"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact"}],
                "evidencePool": {},
            },
            # Simulates the 3 automatic attempts already exhausted during the original
            # run — none flagged manual, so none of them count against the manual cap.
            diagnosis={"outcome": "stage_failed", "attempts": [
                {"attempt": 1, "manual": False, "outcome": "failed", "validationFailure": "x", "stage": "diagnosis"},
                {"attempt": 2, "manual": False, "outcome": "failed", "validationFailure": "x", "stage": "diagnosis"},
                {"attempt": 3, "manual": False, "outcome": "failed", "validationFailure": "x", "stage": "diagnosis"},
            ]},
        )
        patch("anthropic_pipeline.diagnose", return_value={"diagnosis": []}).start()  # missing "evidence" -> fails
        resp = self.client.post(f"/api/analyze-company/{job_id}/retry/diagnosis")
        self.assertEqual(resp.status_code, 202)
        final = self._poll(resp.get_json()["jobId"])
        self.assertEqual(final["status"], "failed")

        checkpoint = job_persistence.load_job_state(job_id)
        self.assertEqual(checkpoint["diagnosis"]["retryCount"], 4)  # 3 automatic + 1 manual, none lost
        self.assertEqual(len(checkpoint["diagnosis"]["attempts"]), 4)
        last_attempt = checkpoint["diagnosis"]["attempts"][-1]
        self.assertTrue(last_attempt["manual"])
        self.assertIn("startedAt", last_attempt)
        self.assertIn("completedAt", last_attempt)
        self.assertEqual(last_attempt["stage"], "diagnosis")

    def test_manual_retry_limit_is_enforced_after_the_first_manual_attempt(self):
        """Exactly ONE manual retry is allowed per stage after automatic attempts are
        exhausted. A second manual retry request for the same stage must be rejected
        with 429 retry_limit_reached and must never call the API."""
        sources = [{"id": "src1", "companyId": "live", "title": "Co", "publisher": "co.com",
                     "sourceType": "website", "url": "https://co.com", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"}]
        job_id = self._seed_checkpoint(
            jobInput={"existingNarrative": ""},
            fetching_sources={"sources": sources, "sourceTextById": {"src1": "text"}},
            strategic_foundation={
                "outcome": "success",
                "strategicFoundation": [{"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact"}],
                "evidencePool": {},
            },
            diagnosis={"outcome": "stage_failed", "attempts": [
                {"attempt": 1, "manual": False, "outcome": "failed", "validationFailure": "x", "stage": "diagnosis"},
                {"attempt": 2, "manual": False, "outcome": "failed", "validationFailure": "x", "stage": "diagnosis"},
                {"attempt": 3, "manual": False, "outcome": "failed", "validationFailure": "x", "stage": "diagnosis"},
            ]},
        )
        diagnose_mock = patch("anthropic_pipeline.diagnose", return_value={"diagnosis": []}).start()  # always fails

        resp1 = self.client.post(f"/api/analyze-company/{job_id}/retry/diagnosis")
        self.assertEqual(resp1.status_code, 202)
        final1 = self._poll(resp1.get_json()["jobId"])
        self.assertEqual(final1["status"], "failed")
        self.assertEqual(diagnose_mock.call_count, 1)

        resp2 = self.client.post(f"/api/analyze-company/{job_id}/retry/diagnosis")
        self.assertEqual(resp2.status_code, 429)
        self.assertEqual(resp2.get_json()["error"], "retry_limit_reached")
        self.assertEqual(diagnose_mock.call_count, 1, "a blocked retry must never call the API")


class RestartSafety(unittest.TestCase):
    """The original job_id is always canonical, including across a backend restart.
    Simulates a restart by clearing jobs.JOBS (the in-memory cache) entirely mid-test —
    the on-disk checkpoint is left untouched, exactly like a real process restart would
    leave it. Everything here must work purely from the checkpoint, with zero reliance
    on JOBS still holding the job."""

    def setUp(self):
        self.client = app.test_client()
        self.addCleanup(patch.stopall)
        patch("anthropic_pipeline.get_client", return_value=object()).start()

    def _simulate_restart(self):
        with jobs._JOBS_LOCK:
            jobs.JOBS.clear()

    def test_status_of_a_completed_job_survives_restart(self):
        job_id = _seed_checkpoint_job(
            meta={"kind": "analyze", "status": "done", "stage": "done", "error": None, "createdAt": "2026-01-01T00:00:00Z"},
            fetching_sources={"sources": [], "sourceTextById": {}, "fetchFailures": [], "caseContext": {"id": "live"}},
            strategic_foundation={"outcome": "success", "strategicFoundation": [{"id": "sf1"}], "evidencePool": {}},
            recommendation_and_map={"outcome": "success", "recommendation": {"candidateId": "cand1"}, "narrativeMap": {"id": "map1"}, "audiences": []},
        )
        self._simulate_restart()
        self.assertNotIn(job_id, jobs.JOBS)  # sanity: the restart simulation actually took effect

        status = self.client.get(f"/api/analyze-company/{job_id}/status").get_json()
        self.assertEqual(status["status"], "done")
        self.assertEqual(status["dataset"]["recommendation"]["candidateId"], "cand1")

    def test_retry_after_restart_updates_the_same_canonical_job_id(self):
        sources = [{"id": "src1", "companyId": "live", "title": "Co", "publisher": "co.com",
                     "sourceType": "website", "url": "https://co.com", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"}]
        job_id = _seed_checkpoint_job(
            meta={"kind": "analyze", "status": "failed", "stage": "diagnosis", "error": "diagnosis_stage_failed: x", "createdAt": "2026-01-01T00:00:00Z"},
            fetching_sources={"sources": sources, "sourceTextById": {"src1": "text"}, "caseContext": {"id": "live"}},
            strategic_foundation={"outcome": "success", "strategicFoundation": [{"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact"}], "evidencePool": {}},
            diagnosis={"outcome": "stage_failed", "attempts": [{"attempt": 1, "manual": False, "outcome": "failed", "validationFailure": "x", "stage": "diagnosis"}]},
        )
        self._simulate_restart()

        diagnose_result = {
            "evidence": [], "diagnosis": [{"id": "d1", "title": "t", "explanation": "e", "significance": "medium", "statementType": "source_fact", "evidence": []}],
            "competitorOverlapAssessed": False, "competitorOverlapNote": "", "competitorContrasts": [],
        }
        patch("anthropic_pipeline.diagnose", return_value=diagnose_result).start()

        # No in-memory job at all right now — create_retry_job must work purely off disk.
        resp = self.client.post(f"/api/analyze-company/{job_id}/retry/diagnosis")
        self.assertEqual(resp.status_code, 202)
        returned_id = resp.get_json()["jobId"]
        self.assertEqual(returned_id, job_id, "the retry must never mint a new, disconnected job_id")

        # Simulate the restart a SECOND time, right after enqueueing but before polling —
        # proves the worker itself doesn't depend on JOBS having been populated by the
        # request handler that enqueued it (create_retry_job already rehydrates it).
        final = _poll_until_terminal(self.client, job_id)
        self.assertEqual(final["status"], "done")
        self.assertEqual(len(final["dataset"]["diagnosis"]), 1)

        # Polling the SAME original job_id (not a different one) reflects the retry.
        status_again = self.client.get(f"/api/analyze-company/{job_id}/status").get_json()
        self.assertEqual(status_again["status"], "done")
        self.assertEqual(status_again["dataset"]["diagnosis"][0]["id"], "d1")

    def test_retry_history_persists_on_disk_across_restart(self):
        sources = [{"id": "src1", "companyId": "live", "title": "Co", "publisher": "co.com",
                     "sourceType": "website", "url": "https://co.com", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"}]
        job_id = _seed_checkpoint_job(
            meta={"kind": "analyze", "status": "failed", "stage": "diagnosis", "error": "x", "createdAt": "2026-01-01T00:00:00Z"},
            fetching_sources={"sources": sources, "sourceTextById": {"src1": "text"}, "caseContext": {"id": "live"}},
            strategic_foundation={"outcome": "success", "strategicFoundation": [{"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact"}], "evidencePool": {}},
            diagnosis={"outcome": "stage_failed", "attempts": [
                {"attempt": 1, "manual": False, "outcome": "failed", "validationFailure": "x", "stage": "diagnosis",
                 "startedAt": "2026-01-01T00:00:00Z", "completedAt": "2026-01-01T00:00:01Z", "usage": {"input_tokens": 100, "output_tokens": 50}, "costUsd": 0.0007},
            ]},
        )
        patch("anthropic_pipeline.diagnose", return_value={"diagnosis": []}).start()  # fails again
        self.client.post(f"/api/analyze-company/{job_id}/retry/diagnosis")
        _poll_until_terminal(self.client, job_id)

        self._simulate_restart()

        # Read the persisted history directly (not through /status) to confirm every
        # required field survived the restart: stage, attempt number, start/completion
        # time, outcome, validation failure, token usage, cost.
        checkpoint = job_persistence.load_job_state(job_id)
        attempts = checkpoint["diagnosis"]["attempts"]
        self.assertEqual(len(attempts), 2)
        manual_attempt = attempts[-1]
        for field in ("stage", "attempt", "manual", "startedAt", "completedAt", "outcome", "validationFailure", "usage"):
            self.assertIn(field, manual_attempt)
        self.assertEqual(manual_attempt["stage"], "diagnosis")
        self.assertTrue(manual_attempt["manual"])
        self.assertEqual(manual_attempt["outcome"], "stage_failed")


class EditedFoundationValidation(unittest.TestCase):
    """A real gap the robustness audit found: /api/regenerate only checked
    isinstance(editedFoundation, list) and non-empty — a malformed ITEM inside that list
    would crash regenerate_from() uncaught (it reads item["id"]/["type"]/["statement"]/
    ["statementType"] directly, before any model call, since this is user-supplied input
    rather than model output). Now validated the same way filter_malformed_records
    validates model-generated array items."""

    def setUp(self):
        self.client = app.test_client()
        self.addCleanup(patch.stopall)

    def _seed_source_job(self):
        patch("jobs.run_analysis", side_effect=_fake_run_with_sections(FAKE_SUCCESS_RESULT)).start()
        job_id = self.client.post("/api/analyze-company", json={"companyUrl": "https://example.com"}).get_json()["jobId"]
        _poll_until_terminal(self.client, job_id)
        patch.stopall()
        return job_id

    def test_bare_string_item_in_edited_foundation_returns_400(self):
        source_job_id = self._seed_source_job()
        resp = self.client.post("/api/regenerate", json={
            "sourceJobId": source_job_id, "companyUrl": "https://example.com",
            "editedFoundation": [{"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact", "evidence": []}, "not an object"],
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("expected an object", resp.get_json()["error"])

    def test_item_missing_required_field_returns_400(self):
        source_job_id = self._seed_source_job()
        resp = self.client.post("/api/regenerate", json={
            "sourceJobId": source_job_id, "companyUrl": "https://example.com",
            "editedFoundation": [{"id": "sf1", "type": "customer"}],  # missing statement/statementType/evidence
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("missing required field", resp.get_json()["error"])

    def test_well_formed_edited_foundation_passes_validation(self):
        source_job_id = self._seed_source_job()
        mock_regen = patch("jobs.regenerate_from", return_value=FAKE_SUCCESS_RESULT).start()
        resp = self.client.post("/api/regenerate", json={
            "sourceJobId": source_job_id, "companyUrl": "https://example.com",
            "editedFoundation": [{"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact", "evidence": []}],
        })
        self.assertEqual(resp.status_code, 202)
        _poll_until_terminal(self.client, resp.get_json()["jobId"])


_ORIGINAL_FOUNDATION_ITEM = {
    "id": "sf1", "type": "customer", "statement": "Serves manufacturing customers.",
    "statementType": "source_fact", "evidence": [],
}
_EDITED_FOUNDATION_ITEM = {
    "id": "sf1", "type": "customer", "statement": "Serves enterprise customers exclusively (user-edited).",
    "statementType": "source_fact", "evidence": [],
}


class RegenerateInPlace(unittest.TestCase):
    """/api/regenerate amends the ORIGINAL job in place — it never mints a new job_id.
    Covers the specific failure mode the robustness pass was aimed at: an edit must
    become the new canonical foundation, everything downstream of it must be
    invalidated, the regeneration itself must be built from ONLY the edited foundation
    (never a cached pre-edit summary), and stale pre-edit downstream data must be
    structurally impossible to serve even if the regeneration run itself then fails."""

    def setUp(self):
        self.client = app.test_client()
        # addCleanup runs LIFO — registering patch.stopall FIRST and the queue-join LAST
        # means the join actually runs FIRST (draining the queue while patches are still
        # active), THEN patches are torn down. Several tests below don't poll to a
        # terminal state (they assert on the checkpoint immediately after the
        # synchronous create_regenerate_job() write), so without this the worker could
        # still be mid-flight when patches are torn down, letting it fall through to the
        # real (client=object()) call — see the module docstring's safety note.
        self.addCleanup(patch.stopall)
        self.addCleanup(jobs._QUEUE.join)
        patch("anthropic_pipeline.get_client", return_value=object()).start()

    def _seed_fully_succeeded_job(self):
        sources = [{"id": "src1", "companyId": "live", "title": "Co", "publisher": "co.com",
                     "sourceType": "website", "url": "https://co.com", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"}]
        return _seed_checkpoint_job(
            meta={"kind": "analyze", "status": "done", "stage": "done", "error": None, "createdAt": "2026-01-01T00:00:00Z"},
            fetching_sources={"sources": sources, "sourceTextById": {"src1": "The company serves manufacturing customers."}, "caseContext": {"id": "live"}},
            jobInput={"companyUrl": "https://co.com", "supportingUrls": [], "competitorUrls": [], "existingNarrative": "original narrative"},
            strategic_foundation={"outcome": "success", "strategicFoundation": [_ORIGINAL_FOUNDATION_ITEM], "evidencePool": {}, "attempts": []},
            diagnosis={"outcome": "success", "diagnosis": [{"id": "d1", "title": "old finding"}], "competitorContrasts": [], "evidencePool": {}},
            narrative_choices={"outcome": "success", "candidates": [{"id": "cand1", "name": "old candidate"}]},
            critique={"outcome": "success", "candidates": [{"id": "cand1", "name": "old candidate", "status": "candidate"}]},
            recommendation_and_map={"outcome": "success", "recommendation": {"candidateId": "cand1", "recommendedDecision": "old decision"}, "narrativeMap": {"id": "old_map"}, "audiences": []},
        )

    def test_regenerate_returns_the_same_canonical_job_id(self):
        job_id = self._seed_fully_succeeded_job()
        patch("jobs.regenerate_from", return_value=FAKE_SUCCESS_RESULT).start()
        resp = self.client.post("/api/regenerate", json={
            "sourceJobId": job_id, "companyUrl": "https://co.com", "editedFoundation": [_EDITED_FOUNDATION_ITEM],
        })
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.get_json()["jobId"], job_id)

    def test_edited_foundation_replaces_the_prior_foundation(self):
        job_id = self._seed_fully_succeeded_job()
        patch("jobs.regenerate_from", return_value=FAKE_SUCCESS_RESULT).start()
        self.client.post("/api/regenerate", json={
            "sourceJobId": job_id, "companyUrl": "https://co.com", "editedFoundation": [_EDITED_FOUNDATION_ITEM],
        })
        checkpoint = job_persistence.load_job_state(job_id)
        fs = checkpoint["strategic_foundation"]
        self.assertEqual(fs["strategicFoundation"], [_EDITED_FOUNDATION_ITEM])
        self.assertNotEqual(fs["strategicFoundation"], [_ORIGINAL_FOUNDATION_ITEM])
        self.assertTrue(fs["editedManually"])
        self.assertEqual(fs["attempts"], [])  # a fresh manual value starts a clean attempt history

    def test_regenerate_invalidates_every_downstream_stage(self):
        """Checked immediately after the request returns — invalidation happens
        synchronously in create_regenerate_job, before the actual regeneration is even
        queued, so this doesn't require waiting for the worker."""
        job_id = self._seed_fully_succeeded_job()
        patch("jobs.regenerate_from", return_value=FAKE_SUCCESS_RESULT).start()
        resp = self.client.post("/api/regenerate", json={
            "sourceJobId": job_id, "companyUrl": "https://co.com", "editedFoundation": [_EDITED_FOUNDATION_ITEM],
        })
        self.assertEqual(resp.status_code, 202)

        checkpoint = job_persistence.load_job_state(job_id)
        for stage in ("diagnosis", "narrative_choices", "critique", "recommendation_and_map"):
            self.assertEqual(checkpoint[stage]["outcome"], "invalidated", f"{stage} should be invalidated")
            self.assertNotIn("candidates", checkpoint[stage])  # old data fields must not survive invalidation
            self.assertNotIn("recommendation", checkpoint[stage])

    def test_regeneration_is_built_from_only_the_edited_foundation(self):
        """Captures exactly what diagnose() receives as its foundation summary — must
        match the EDITED statement, never the old cached one, and must not depend on any
        stale summary computed before the edit."""
        job_id = self._seed_fully_succeeded_job()
        captured = {}

        def fake_diagnose(client, usage, sources, foundation_summary, competitor_sources, existing_narrative, evidence_pool, prior_failure=None):
            captured["foundation_summary"] = foundation_summary
            return {
                "evidence": [], "diagnosis": [{"id": "d2", "title": "new finding", "explanation": "e", "significance": "medium", "statementType": "source_fact", "evidence": []}],
                "competitorOverlapAssessed": False, "competitorOverlapNote": "", "competitorContrasts": [],
            }

        patch("anthropic_pipeline.diagnose", side_effect=fake_diagnose).start()
        patch("anthropic_pipeline.generate_candidates", return_value={"candidates": _valid_candidates_for_regen()}).start()
        patch("anthropic_pipeline.critique_candidates", return_value={"critiques": _valid_critiques_for_regen()}).start()
        patch("anthropic_pipeline.recommend_and_map", side_effect=Exception("stop after critique for this test")).start()

        self.client.post("/api/regenerate", json={
            "sourceJobId": job_id, "companyUrl": "https://co.com", "editedFoundation": [_EDITED_FOUNDATION_ITEM],
        })
        _poll_until_terminal(self.client, job_id)

        self.assertEqual(len(captured["foundation_summary"]), 1)
        self.assertEqual(captured["foundation_summary"][0]["statement"], _EDITED_FOUNDATION_ITEM["statement"])
        self.assertNotEqual(captured["foundation_summary"][0]["statement"], _ORIGINAL_FOUNDATION_ITEM["statement"])

    def test_stale_downstream_data_is_impossible_even_if_regeneration_then_fails(self):
        """The critical case: the edit is accepted, but the very next model call
        (diagnose) fails validation. The job ends up "failed" — but candidates/
        recommendation/narrativeMap must NEVER show the old, pre-edit values; they must
        be empty, because the sections were invalidated up front, not merely "about to be
        overwritten if all goes well."""
        job_id = self._seed_fully_succeeded_job()
        patch("anthropic_pipeline.diagnose", return_value={"diagnosis": []}).start()  # missing "evidence" -> stage_failed

        resp = self.client.post("/api/regenerate", json={
            "sourceJobId": job_id, "companyUrl": "https://co.com", "editedFoundation": [_EDITED_FOUNDATION_ITEM],
        })
        self.assertEqual(resp.status_code, 202)
        final = _poll_until_terminal(self.client, job_id)

        self.assertEqual(final["status"], "failed")
        self.assertIsNotNone(final["dataset"])  # the edited foundation itself is still real, useful data
        self.assertEqual(final["dataset"]["strategicFoundation"], [_EDITED_FOUNDATION_ITEM])
        self.assertEqual(final["dataset"]["candidates"], [])
        self.assertIsNone(final["dataset"]["recommendation"])
        self.assertIsNone(final["dataset"]["narrativeMap"])
        # The literal old candidate name must not appear anywhere reachable from /status.
        self.assertNotIn("old candidate", str(final["dataset"]))
        self.assertNotIn("old decision", str(final["dataset"]))


def _valid_candidates_for_regen():
    return [
        {"id": f"cand{i}", "name": f"n{i}", "oneSentenceStory": "x", "sevenParts": {k: "x" for k in ["context", "tension", "belief", "role", "value", "proof", "direction"]},
         "strategicLogic": "x", "customerRelevance": "x", "differentiation": "x", "tradeoffs": "x", "risks": "x", "claims": []}
        for i in (1, 2, 3)
    ]


def _valid_critiques_for_regen():
    return [
        {"candidateId": f"cand{i}", "findings": ["ok"], "strategicFitGate": "meets", "differentiationGate": "meets", "evidenceSupportGate": "supported"}
        for i in (1, 2, 3)
    ]


class ConcurrentRetrySafety(unittest.TestCase):
    """The race the atomic-retry fix closes: two near-simultaneous manual retry requests
    for the SAME stage must never both be queued. jobs.create_retry_job serializes its
    check-then-reserve sequence under a per-job lock (jobs._get_job_lock), so this is
    deterministic given the right synchronization — not a timing-dependent flaky test."""

    def setUp(self):
        self.addCleanup(patch.stopall)
        patch("anthropic_pipeline.get_client", return_value=object()).start()

    def test_two_simultaneous_retry_requests_only_one_is_ever_queued(self):
        sources = [{"id": "src1", "companyId": "live", "title": "Co", "publisher": "co.com",
                     "sourceType": "website", "url": "https://co.com", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"}]
        job_id = _seed_checkpoint_job(
            jobInput={"existingNarrative": ""},
            fetching_sources={"sources": sources, "sourceTextById": {"src1": "text"}},
            strategic_foundation={
                "outcome": "success",
                "strategicFoundation": [{"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact"}],
                "evidencePool": {},
            },
            diagnosis={"outcome": "stage_failed", "attempts": [
                {"attempt": 1, "manual": False, "outcome": "failed", "validationFailure": "x", "stage": "diagnosis"},
                {"attempt": 2, "manual": False, "outcome": "failed", "validationFailure": "x", "stage": "diagnosis"},
                {"attempt": 3, "manual": False, "outcome": "failed", "validationFailure": "x", "stage": "diagnosis"},
            ]},
        )

        call_started = threading.Event()
        release_call = threading.Event()

        def slow_diagnose(*args, **kwargs):
            # Proves the first request's reservation is genuinely ACTIVE (the worker has
            # already started processing it) at the moment the second request fires —
            # this is what makes the outcome deterministically retry_in_progress rather
            # than a timing-dependent maybe-retry_limit_reached.
            call_started.set()
            release_call.wait(timeout=5)
            return {"diagnosis": []}  # malformed on purpose -- outcome doesn't matter for this test

        patch("anthropic_pipeline.diagnose", side_effect=slow_diagnose).start()

        responses = {}

        def fire_first():
            responses["first"] = app.test_client().post(f"/api/analyze-company/{job_id}/retry/diagnosis")

        t1 = threading.Thread(target=fire_first)
        t1.start()
        self.assertTrue(call_started.wait(timeout=5), "the first retry's diagnose call never started")

        # The first request's reservation is now active. Fire the second WHILE it's
        # still in flight.
        second_resp = app.test_client().post(f"/api/analyze-company/{job_id}/retry/diagnosis")

        release_call.set()
        t1.join(timeout=5)

        self.assertEqual(responses["first"].status_code, 202)
        self.assertEqual(second_resp.status_code, 429)
        self.assertEqual(second_resp.get_json()["error"], "retry_in_progress")

        # Drain the queue so the first request's job actually finishes before teardown
        # unpatches anthropic_pipeline.diagnose (see the module docstring's safety note).
        jobs._QUEUE.join()

        # And the reservation must be resolved afterward -- a stage that just finished
        # its one manual retry (successfully or not) is at the cap, not stuck
        # "in progress" forever.
        checkpoint = job_persistence.load_job_state(job_id)
        self.assertFalse(checkpoint["diagnosis"].get("pendingManualRetry"))
        allowed, reason = check_manual_retry_allowed(checkpoint, "diagnosis")
        self.assertFalse(allowed)
        self.assertEqual(reason, "retry_limit_reached")

    def test_pending_reservation_is_cleared_even_if_the_retry_crashes_unexpectedly(self):
        """The finally-block safety net: an unexpected exception mid-retry (not just a
        clean validation failure) must not leave the stage permanently stuck at
        retry_in_progress forever."""
        sources = [{"id": "src1", "companyId": "live", "title": "Co", "publisher": "co.com",
                     "sourceType": "website", "url": "https://co.com", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"}]
        job_id = _seed_checkpoint_job(
            jobInput={"existingNarrative": ""},
            fetching_sources={"sources": sources, "sourceTextById": {"src1": "text"}},
            strategic_foundation={
                "outcome": "success",
                "strategicFoundation": [{"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact"}],
                "evidencePool": {},
            },
            diagnosis={"outcome": "stage_failed", "attempts": [
                {"attempt": 1, "manual": False, "outcome": "failed", "validationFailure": "x", "stage": "diagnosis"},
            ]},
        )
        patch("anthropic_pipeline.diagnose", side_effect=RuntimeError("unexpected crash, not a validation failure")).start()

        client = app.test_client()
        resp = client.post(f"/api/analyze-company/{job_id}/retry/diagnosis")
        self.assertEqual(resp.status_code, 202)
        _poll_until_terminal(client, job_id)

        checkpoint = job_persistence.load_job_state(job_id)
        self.assertFalse(checkpoint["diagnosis"].get("pendingManualRetry"), "the reservation must be cleared even after an unexpected crash")


class SourceCoverageReporting(unittest.TestCase):
    """jobs._source_coverage_from_checkpoint / GET /status's new sourceCoverage field —
    always derived fresh from the checkpoint (never persisted), so it automatically
    reflects the CURRENT strategic_foundation regardless of which action produced it."""

    def setUp(self):
        self.addCleanup(patch.stopall)
        patch("anthropic_pipeline.get_client", return_value=object()).start()

    def test_null_before_strategic_foundation_succeeds(self):
        job_id = _seed_checkpoint_job(fetching_sources={"sources": []})
        job = jobs.get_job(job_id)
        self.assertIsNone(job["sourceCoverage"])

    def test_null_when_strategic_foundation_stage_failed(self):
        job_id = _seed_checkpoint_job(
            fetching_sources={"sources": []},
            strategic_foundation={"outcome": "stage_failed", "attempts": []},
        )
        job = jobs.get_job(job_id)
        self.assertIsNone(job["sourceCoverage"])

    def test_present_and_correctly_computed_once_foundation_succeeds(self):
        sources = [{"id": "src1", "sourceType": "website"}]
        job_id = _seed_checkpoint_job(
            fetching_sources={"sources": sources},
            strategic_foundation={
                "outcome": "success",
                "strategicFoundation": [{"id": "sf1", "type": "capability"}],
                "evidencePool": {},
            },
        )
        job = jobs.get_job(job_id)
        self.assertIsNotNone(job["sourceCoverage"])
        self.assertIn("capabilities", job["sourceCoverage"]["coveredDimensions"])
        self.assertFalse(job["sourceCoverage"]["sufficient"])  # only 1 source, 1 dimension

    def test_reflects_the_edited_foundation_after_regenerate_not_the_original(self):
        """The read-time design's whole point: coverage must track whatever the CURRENT
        strategic_foundation section says, even after a user-edited regenerate — never a
        stale value computed from the original model-generated foundation."""
        sources = [{"id": "src1", "sourceType": "website"}]
        job_id = _seed_checkpoint_job(
            fetching_sources={"sources": sources},
            strategic_foundation={
                "outcome": "success",
                "strategicFoundation": [{"id": "sf1", "type": "customer"}],  # original: only "customers" covered
                "evidencePool": {},
            },
        )
        before = jobs.get_job(job_id)["sourceCoverage"]
        self.assertIn("customers", before["coveredDimensions"])
        self.assertNotIn("capabilities", before["coveredDimensions"])

        # Simulate a regenerate's edit directly overwriting the section, matching how
        # jobs.create_regenerate_job actually replaces it (full section replacement).
        checkpoint = job_persistence.load_job_state(job_id)
        checkpoint["strategic_foundation"] = {
            "outcome": "success",
            "strategicFoundation": [{"id": "sf1", "type": "capability"}],
            "evidencePool": {}, "editedManually": True, "attempts": [],
        }
        job_persistence.save_job_state(job_id, checkpoint)

        after = jobs.get_job(job_id)["sourceCoverage"]
        self.assertIn("capabilities", after["coveredDimensions"])
        self.assertNotIn("customers", after["coveredDimensions"])

    def test_status_endpoint_returns_source_coverage(self):
        sources = [{"id": "src1", "sourceType": "website"}, {"id": "src2", "sourceType": "competitor"}]
        job_id = _seed_checkpoint_job(
            fetching_sources={"sources": sources},
            strategic_foundation={
                "outcome": "success",
                "strategicFoundation": [
                    {"id": "sf1", "type": "customer"}, {"id": "sf2", "type": "capability"},
                    {"id": "sf3", "type": "market"}, {"id": "sf4", "type": "proof"},
                ],
                "evidencePool": {},
            },
        )
        client = app.test_client()
        resp = client.get(f"/api/analyze-company/{job_id}/status")
        body = resp.get_json()
        self.assertTrue(body["sourceCoverage"]["sufficient"])

    def test_real_schneider_electric_job_is_correctly_flagged_insufficient(self):
        """End-to-end validation against the actual preserved paid run (read-only — no
        API call, no mutation) — confirms the gate flags exactly the run that motivated
        building it. Temporarily points JOB_STATE_ROOT at the REAL backend/job_state/
        (this suite normally redirects it to a throwaway temp dir — see setUpModule) for
        the duration of this one read-only lookup, then restores the redirect."""
        real_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "job_state")
        prior_root = job_persistence.JOB_STATE_ROOT
        job_persistence.JOB_STATE_ROOT = real_root
        try:
            job = jobs.get_job("bb673b9786d5486f99c359c9309760ed")
        finally:
            job_persistence.JOB_STATE_ROOT = prior_root
        if job is None:
            self.skipTest("preserved Schneider Electric job not present in this environment")
        self.assertIsNotNone(job["sourceCoverage"])
        self.assertFalse(job["sourceCoverage"]["sufficient"])
        self.assertIn("competitive_context", job["sourceCoverage"]["missingDimensions"])


class StageProgressReporting(unittest.TestCase):
    """jobs._stage_progress_from_checkpoint / GET /status's new stageProgress field —
    the durable per-stage retry history diagnostics alone can't provide, since
    diagnostics only reflects the most recent action's outcome."""

    def setUp(self):
        self.addCleanup(patch.stopall)
        patch("anthropic_pipeline.get_client", return_value=object()).start()

    def test_stage_not_reached_yet_reports_null_outcome(self):
        job_id = _seed_checkpoint_job(fetching_sources={"sources": []})
        job = jobs.get_job(job_id)
        self.assertEqual(job["stageProgress"]["diagnosis"], {"outcome": None, "attempts": 0, "lastFailureReason": None})

    def test_invalidated_section_has_no_attempts_key_and_does_not_crash(self):
        job_id = _seed_checkpoint_job(
            fetching_sources={"sources": []},
            diagnosis={"outcome": "invalidated", "invalidatedAt": "2026-01-01T00:00:00Z", "reason": "x"},
        )
        job = jobs.get_job(job_id)
        self.assertEqual(job["stageProgress"]["diagnosis"], {"outcome": "invalidated", "attempts": 0, "lastFailureReason": None})

    def test_multiple_failed_attempts_then_success_reports_last_failure_reason(self):
        job_id = _seed_checkpoint_job(
            fetching_sources={"sources": []},
            diagnosis={"outcome": "success", "attempts": [
                {"attempt": 1, "manual": False, "outcome": "failed", "validationFailure": "first reason", "stage": "diagnosis"},
                {"attempt": 2, "manual": False, "outcome": "failed", "validationFailure": "second reason", "stage": "diagnosis"},
                {"attempt": 3, "manual": False, "outcome": "success", "validationFailure": None, "stage": "diagnosis"},
            ]},
        )
        job = jobs.get_job(job_id)
        progress = job["stageProgress"]["diagnosis"]
        self.assertEqual(progress["outcome"], "success")
        self.assertEqual(progress["attempts"], 3)
        self.assertEqual(progress["lastFailureReason"], "second reason")

    def test_all_success_first_attempt_has_no_failure_reason(self):
        job_id = _seed_checkpoint_job(
            fetching_sources={"sources": []},
            strategic_foundation={"outcome": "success", "attempts": [
                {"attempt": 1, "manual": False, "outcome": "success", "validationFailure": None, "stage": "strategic_foundation"},
            ]},
        )
        job = jobs.get_job(job_id)
        self.assertIsNone(job["stageProgress"]["strategic_foundation"]["lastFailureReason"])

    def test_fetching_sources_is_excluded_from_stage_progress(self):
        job_id = _seed_checkpoint_job(fetching_sources={"sources": []})
        job = jobs.get_job(job_id)
        self.assertNotIn("fetching_sources", job["stageProgress"])

    def test_status_endpoint_returns_stage_progress_and_usage(self):
        job_id = _seed_checkpoint_job(
            fetching_sources={"sources": []},
            usage={"totals": {"input_tokens": 100, "output_tokens": 50}, "costUsd": 0.0007, "latestCall": {}},
        )
        client = app.test_client()
        resp = client.get(f"/api/analyze-company/{job_id}/status")
        body = resp.get_json()
        self.assertIn("stageProgress", body)
        self.assertEqual(body["usage"]["totals"], {"input_tokens": 100, "output_tokens": 50})


class UsageAccumulation(unittest.TestCase):
    """checkpoint["usage"] must be a TRUE lifetime-cumulative total across every action
    ever taken on a job — never overwritten by whichever action's own usage update
    happens to save last. Real bug found while building the usage/cost UI: on_usage_call
    (pipeline_runner.py) fires "totals" cumulative only WITHIN a single
    run_analysis/regenerate_from call, so persisting it directly discarded an earlier
    action's spend the moment a second action made its first API call."""

    def setUp(self):
        self.addCleanup(patch.stopall)

    def test_persist_cb_merges_usage_additively_not_overwrite(self):
        job_id = _seed_checkpoint_job(usage={
            "totals": {"input_tokens": 1000, "output_tokens": 200}, "costUsd": 0.004,
            "latestCall": {"label": "foundation", "input_tokens": 1000, "output_tokens": 200},
        })
        persist_cb = jobs._make_persist_cb(job_id)
        # Simulates a SECOND action's first on_usage_call: a small IN-RUN cumulative
        # total that, if simply overwritten, would silently discard the 1000/200
        # already spent by the first action.
        persist_cb("usage", {
            "latestCall": {"label": "diagnosis", "input_tokens": 500, "output_tokens": 100},
            "totals": {"input_tokens": 500, "output_tokens": 100}, "costUsd": 0.002,
        })
        checkpoint = job_persistence.load_job_state(job_id)
        self.assertEqual(checkpoint["usage"]["totals"], {"input_tokens": 1500, "output_tokens": 300})

    def test_multiple_calls_within_one_run_accumulate_correctly(self):
        job_id = _seed_checkpoint_job()
        persist_cb = jobs._make_persist_cb(job_id)
        persist_cb("usage", {"latestCall": {"label": "a", "input_tokens": 100, "output_tokens": 10}, "totals": {"input_tokens": 100, "output_tokens": 10}, "costUsd": 0.0})
        persist_cb("usage", {"latestCall": {"label": "b", "input_tokens": 200, "output_tokens": 20}, "totals": {"input_tokens": 300, "output_tokens": 30}, "costUsd": 0.0})
        checkpoint = job_persistence.load_job_state(job_id)
        self.assertEqual(checkpoint["usage"]["totals"], {"input_tokens": 300, "output_tokens": 30})

    def test_usage_survives_a_real_analyze_then_regenerate_sequence(self):
        """End-to-end: a real (mocked) analyze run followed by a real (mocked)
        regenerate must leave checkpoint["usage"]["totals"] as the SUM of both, not just
        the regenerate's own smaller total."""

        def fake_run_analysis(company_url, supporting_urls, competitor_urls, existing_narrative, progress_cb=None, persist_cb=None):
            if persist_cb:
                persist_cb("fetching_sources", {"sources": [], "sourceTextById": {}, "fetchFailures": [], "caseContext": None})
                persist_cb("strategic_foundation", {"outcome": "success", "strategicFoundation": [{"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact", "evidence": []}], "evidencePool": {}, "attempts": []})
                persist_cb("usage", {"latestCall": {"label": "foundation", "input_tokens": 1000, "output_tokens": 200}, "totals": {"input_tokens": 1000, "output_tokens": 200}, "costUsd": 0.004})
            return FAKE_SUCCESS_RESULT

        def fake_regenerate_from(sources, source_text_by_id, evidence_pool, edited_foundation, existing_narrative, progress_cb=None, persist_cb=None):
            if persist_cb:
                persist_cb("usage", {"latestCall": {"label": "diagnosis", "input_tokens": 500, "output_tokens": 100}, "totals": {"input_tokens": 500, "output_tokens": 100}, "costUsd": 0.002})
            return FAKE_SUCCESS_RESULT

        patch("anthropic_pipeline.get_client", return_value=object()).start()
        analyze_patch = patch("jobs.run_analysis", side_effect=fake_run_analysis)
        analyze_patch.start()
        self.addCleanup(analyze_patch.stop)
        self.addCleanup(jobs._QUEUE.join)

        client = app.test_client()
        job_id = client.post("/api/analyze-company", json={"companyUrl": "https://example.com"}).get_json()["jobId"]
        _poll_until_terminal(client, job_id)

        checkpoint = job_persistence.load_job_state(job_id)
        self.assertEqual(checkpoint["usage"]["totals"], {"input_tokens": 1000, "output_tokens": 200})

        analyze_patch.stop()
        regen_patch = patch("jobs.regenerate_from", side_effect=fake_regenerate_from)
        regen_patch.start()
        self.addCleanup(regen_patch.stop)

        resp = client.post("/api/regenerate", json={
            "sourceJobId": job_id, "companyUrl": "https://example.com",
            "editedFoundation": [{"id": "sf1", "type": "customer", "statement": "edited", "statementType": "source_fact", "evidence": []}],
        })
        self.assertEqual(resp.status_code, 202)
        _poll_until_terminal(client, job_id)

        checkpoint = job_persistence.load_job_state(job_id)
        self.assertEqual(checkpoint["usage"]["totals"], {"input_tokens": 1500, "output_tokens": 300},
                          "the regenerate run's usage must ADD to the analyze run's, never replace it")


class ExpandSourcesEndpoint(unittest.TestCase):
    """POST /api/analyze-company/<job_id>/expand-sources — genuinely new capability
    (adding URLs requires a real re-fetch, which /regenerate explicitly never does).
    Never mints a new job_id (same canonical-job architecture as retry/regenerate),
    validates companyUrl against the job's own stored value before doing anything, and
    is capped independently of /regenerate's MAX_FULL_REGENERATIONS. Not wired to any
    frontend UI yet — backend-only for this phase."""

    def setUp(self):
        self.client = app.test_client()
        self.addCleanup(patch.stopall)
        patch("anthropic_pipeline.get_client", return_value=object()).start()
        self.addCleanup(jobs._QUEUE.join)

    def _seed_expandable_job(self):
        sources = [{"id": "src1", "companyId": "live", "title": "Co", "publisher": "co.com",
                     "sourceType": "website", "url": "https://co.com", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"}]
        return _seed_checkpoint_job(
            meta={"kind": "analyze", "status": "done", "stage": "done", "error": None, "createdAt": "2026-01-01T00:00:00Z"},
            jobInput={"companyUrl": "https://co.com", "supportingUrls": [], "competitorUrls": [], "existingNarrative": ""},
            fetching_sources={"sources": sources, "sourceTextById": {"src1": "text"}, "caseContext": {"id": "live"}},
            strategic_foundation={
                "outcome": "success",
                "strategicFoundation": [{"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact", "evidence": []}],
                "evidencePool": {}, "attempts": [],
            },
        )

    def _fake_fetch_result(self, extra_source=True):
        sources = [{"id": "src1", "companyId": "live", "title": "Co", "publisher": "co.com",
                     "sourceType": "website", "url": "https://co.com", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"}]
        text_by_id = {"src1": "text"}
        if extra_source:
            sources.append({"id": "src2", "companyId": "live", "title": "Rival", "publisher": "rival.example.com",
                             "sourceType": "competitor", "url": "https://example.com/rival", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"})
            text_by_id["src2"] = "rival text"
        return (sources, text_by_id, [], {"id": "src1", "title": "Co", "publisher": "co.com"})

    def test_unknown_job_returns_404(self):
        resp = self.client.post("/api/analyze-company/does-not-exist/expand-sources", json={
            "companyUrl": "https://co.com", "competitorUrls": ["https://example.com/rival"],
        })
        self.assertEqual(resp.status_code, 404)

    def test_missing_company_url_returns_400(self):
        job_id = self._seed_expandable_job()
        resp = self.client.post(f"/api/analyze-company/{job_id}/expand-sources", json={"competitorUrls": ["https://example.com/rival"]})
        self.assertEqual(resp.status_code, 400)

    def test_no_urls_at_all_returns_400(self):
        job_id = self._seed_expandable_job()
        resp = self.client.post(f"/api/analyze-company/{job_id}/expand-sources", json={"companyUrl": "https://co.com"})
        self.assertEqual(resp.status_code, 400)

    def test_company_url_mismatch_is_rejected_before_any_fetch(self):
        job_id = self._seed_expandable_job()
        mock_fetch = patch("jobs.fetch_all_sources").start()
        resp = self.client.post(f"/api/analyze-company/{job_id}/expand-sources", json={
            "companyUrl": "https://a-totally-different-company.com", "competitorUrls": ["https://example.com/rival"],
        })
        self.assertEqual(resp.status_code, 400)
        mock_fetch.assert_not_called()

    def test_unsafe_new_url_is_rejected(self):
        job_id = self._seed_expandable_job()
        resp = self.client.post(f"/api/analyze-company/{job_id}/expand-sources", json={
            "companyUrl": "https://co.com", "competitorUrls": ["http://169.254.169.254/"],
        })
        self.assertEqual(resp.status_code, 400)

    def test_successful_expansion_returns_the_same_canonical_job_id(self):
        job_id = self._seed_expandable_job()
        patch("jobs.fetch_all_sources", return_value=self._fake_fetch_result()).start()
        patch("jobs.run_pipeline_from_sources", return_value=FAKE_SUCCESS_RESULT).start()

        resp = self.client.post(f"/api/analyze-company/{job_id}/expand-sources", json={
            "companyUrl": "https://co.com", "competitorUrls": ["https://example.com/rival"],
        })
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.get_json()["jobId"], job_id)
        _poll_until_terminal(self.client, job_id)

    def test_downstream_stages_invalidated_synchronously_before_the_worker_even_runs(self):
        job_id = self._seed_expandable_job()
        checkpoint = job_persistence.load_job_state(job_id)
        checkpoint["diagnosis"] = {"outcome": "success", "diagnosis": [{"id": "d1"}], "attempts": []}
        checkpoint["narrative_choices"] = {"outcome": "success", "candidates": [{"id": "cand1"}]}
        checkpoint["recommendation_and_map"] = {"outcome": "success", "recommendation": {"candidateId": "cand1"}, "attempts": []}
        job_persistence.save_job_state(job_id, checkpoint)

        # Block the worker so the checkpoint can be inspected before it does anything —
        # proves invalidation happens in create_expand_sources_job() itself (synchronous,
        # before the 202 response), not later in the worker.
        release = threading.Event()

        def blocking_fetch(*a, **k):
            release.wait(timeout=5)
            raise PipelineError("test: stop before any real work")

        patch("jobs.fetch_all_sources", side_effect=blocking_fetch).start()

        resp = self.client.post(f"/api/analyze-company/{job_id}/expand-sources", json={
            "companyUrl": "https://co.com", "competitorUrls": ["https://example.com/rival"],
        })
        self.assertEqual(resp.status_code, 202)

        checkpoint = job_persistence.load_job_state(job_id)
        self.assertEqual(checkpoint["diagnosis"]["outcome"], "invalidated")
        self.assertEqual(checkpoint["narrative_choices"]["outcome"], "invalidated")
        self.assertEqual(checkpoint["recommendation_and_map"]["outcome"], "invalidated")
        self.assertNotIn("candidates", checkpoint["narrative_choices"])
        self.assertNotIn("recommendation", checkpoint["recommendation_and_map"])

        release.set()

    def test_expand_sources_count_increments_and_caps_independently_of_regenerate(self):
        job_id = self._seed_expandable_job()
        patch("jobs.fetch_all_sources", return_value=self._fake_fetch_result()).start()
        patch("jobs.run_pipeline_from_sources", return_value=FAKE_SUCCESS_RESULT).start()

        r1 = self.client.post(f"/api/analyze-company/{job_id}/expand-sources", json={"companyUrl": "https://co.com", "competitorUrls": ["https://example.com/rival1"]})
        self.assertEqual(r1.status_code, 202)
        r2 = self.client.post(f"/api/analyze-company/{job_id}/expand-sources", json={"companyUrl": "https://co.com", "competitorUrls": ["https://example.com/rival2"]})
        self.assertEqual(r2.status_code, 202)
        r3 = self.client.post(f"/api/analyze-company/{job_id}/expand-sources", json={"companyUrl": "https://co.com", "competitorUrls": ["https://example.com/rival3"]})
        self.assertEqual(r3.status_code, 429)
        self.assertEqual(r3.get_json()["error"], "source_expansion_limit_reached")

        checkpoint = job_persistence.load_job_state(job_id)
        self.assertEqual(checkpoint["expandSourcesCount"], 2)
        self.assertNotIn("regenerationCount", checkpoint)  # untouched by expand-sources

    def test_dispatch_calls_run_pipeline_from_sources_not_run_analysis(self):
        """Confirms the worker actually routes through the refactored shared function,
        not a duplicate/divergent code path."""
        job_id = self._seed_expandable_job()
        patch("jobs.fetch_all_sources", return_value=self._fake_fetch_result()).start()
        mock_run_analysis = patch("jobs.run_analysis").start()
        mock_run_pipeline = patch("jobs.run_pipeline_from_sources", return_value=FAKE_SUCCESS_RESULT).start()

        resp = self.client.post(f"/api/analyze-company/{job_id}/expand-sources", json={
            "companyUrl": "https://co.com", "competitorUrls": ["https://example.com/rival"],
        })
        self.assertEqual(resp.status_code, 202)
        _poll_until_terminal(self.client, job_id)

        mock_run_pipeline.assert_called_once()
        mock_run_analysis.assert_not_called()

    def test_dataset_reflects_the_expanded_source_set_once_done(self):
        job_id = self._seed_expandable_job()
        patch("jobs.fetch_all_sources", return_value=self._fake_fetch_result()).start()
        expanded_result = {
            "dataset": {
                "caseContext": {"id": "live"}, "sources": [], "evidence": [], "strategicFoundation": [],
                "diagnosis": [], "candidates": [], "recommendation": {"candidateId": "cand1"},
                "narrativeMap": {"id": "map1"}, "audiences": [], "competitorContrasts": [],
            },
            "diagnostics": {"critical_failure": None, "api_calls": [], "token_totals": {"input_tokens": 0, "output_tokens": 0}},
        }

        def fake_run_pipeline(sources, source_text_by_id, existing_narrative, case_context, fetch_failures=(), progress_cb=None, persist_cb=None):
            if persist_cb:
                persist_cb("strategic_foundation", {"outcome": "success", "strategicFoundation": [{"id": "sf1", "type": "customer"}], "evidencePool": {}, "attempts": []})
                persist_cb("recommendation_and_map", {"outcome": "success", "recommendation": expanded_result["dataset"]["recommendation"], "narrativeMap": expanded_result["dataset"]["narrativeMap"], "audiences": []})
            return expanded_result

        patch("jobs.run_pipeline_from_sources", side_effect=fake_run_pipeline).start()

        resp = self.client.post(f"/api/analyze-company/{job_id}/expand-sources", json={
            "companyUrl": "https://co.com", "competitorUrls": ["https://example.com/rival"],
        })
        self.assertEqual(resp.status_code, 202)
        final = _poll_until_terminal(self.client, job_id)

        self.assertEqual(final["status"], "done")
        self.assertEqual(len(final["dataset"]["sources"]), 2)  # the NEW, expanded fetching_sources section
        self.assertEqual(final["dataset"]["recommendation"]["candidateId"], "cand1")

    def test_full_resend_preserves_existing_urls_alongside_new_ones(self):
        """The frontend fix requires the 'Add sources' form to submit the COMPLETE desired
        list (existing + newly typed), never just what's newly typed. This test verifies
        the backend half of that contract: given a full resend containing both an
        already-configured URL and a brand-new one, both are fetched and end up in the
        resulting source set — nothing is dropped just because it was 'already there'."""
        job_id = self._seed_expandable_job()
        mock_fetch = patch("jobs.fetch_all_sources", return_value=self._fake_fetch_result(extra_source=True)).start()
        patch("jobs.run_pipeline_from_sources", return_value=FAKE_SUCCESS_RESULT).start()

        resp = self.client.post(f"/api/analyze-company/{job_id}/expand-sources", json={
            "companyUrl": "https://co.com",
            "supportingUrls": ["https://example.com/existing-supporting"],
            "competitorUrls": ["https://example.com/rival"],
        })
        self.assertEqual(resp.status_code, 202)
        _poll_until_terminal(self.client, job_id)

        # fetch_all_sources(company_url, supporting_urls, competitor_urls, ...) — confirm
        # BOTH lists were forwarded intact, not truncated to only the newly-typed URL.
        mock_fetch.assert_called_once_with(
            "https://co.com",
            ["https://example.com/existing-supporting"],
            ["https://example.com/rival"],
            progress_cb=ANY,
        )

    def test_url_caps_are_enforced_on_the_combined_existing_plus_new_list(self):
        """URL caps (MAX_SUPPORTING_URLS=5, MAX_COMPETITOR_URLS=3) must hold across the
        FULL submitted list, not just newly-added URLs — since a correct frontend always
        resends existing URLs too, the cap naturally applies to existing+new combined.
        One over cap (as if 5 existing + 1 new were all resent) must be rejected for each
        list independently."""
        job_id = self._seed_expandable_job()
        mock_fetch = patch("jobs.fetch_all_sources").start()

        resp = self.client.post(f"/api/analyze-company/{job_id}/expand-sources", json={
            "companyUrl": "https://co.com",
            "supportingUrls": [f"https://example.com/s{i}" for i in range(6)],
        })
        self.assertEqual(resp.status_code, 400)
        mock_fetch.assert_not_called()

        resp2 = self.client.post(f"/api/analyze-company/{job_id}/expand-sources", json={
            "companyUrl": "https://co.com",
            "competitorUrls": [f"https://example.com/c{i}" for i in range(4)],
        })
        self.assertEqual(resp2.status_code, 400)
        mock_fetch.assert_not_called()

    def test_url_cap_boundary_exactly_at_the_max_is_accepted(self):
        """Exactly at the cap (5 supporting, 3 competitor combined across existing+new) is
        accepted — the boundary case adjacent to the over-cap rejections above."""
        job_id = self._seed_expandable_job()
        patch("jobs.fetch_all_sources", return_value=self._fake_fetch_result()).start()
        patch("jobs.run_pipeline_from_sources", return_value=FAKE_SUCCESS_RESULT).start()

        resp = self.client.post(f"/api/analyze-company/{job_id}/expand-sources", json={
            "companyUrl": "https://co.com",
            "supportingUrls": [f"https://example.com/s{i}" for i in range(5)],
            "competitorUrls": [f"https://example.com/c{i}" for i in range(3)],
        })
        self.assertEqual(resp.status_code, 202)
        _poll_until_terminal(self.client, job_id)

    def test_a_failed_expansion_leaves_the_prior_checkpoint_stages_invalidated_not_silently_reverted(self):
        """Documents the exact backend behavior the frontend's snapshot/rollback in
        live-analysis-service.js exists to compensate for: the backend invalidates
        downstream stages the MOMENT the request is accepted (see
        test_downstream_stages_invalidated_synchronously_before_the_worker_even_runs), and
        does NOT revert fetching_sources/strategic_foundation back to the pre-expansion
        state if the re-run subsequently fails. The backend never claims to restore prior
        state on failure — restoring 'the last validated analysis and the prior source
        list' on failure is a client-side (live-analysis-service.js) responsibility,
        which this test exists to make explicit rather than assumed."""
        job_id = self._seed_expandable_job()
        pre_checkpoint = job_persistence.load_job_state(job_id)
        self.assertEqual(pre_checkpoint["strategic_foundation"]["outcome"], "success")

        def failing_pipeline(*a, **k):
            return {
                "dataset": {"caseContext": {"id": "live"}, "sources": [], "evidence": [], "strategicFoundation": [],
                             "diagnosis": [], "candidates": [], "recommendation": None, "narrativeMap": None,
                             "audiences": [], "competitorContrasts": []},
                "diagnostics": {"critical_failure": "diagnosis", "api_calls": [], "token_totals": {"input_tokens": 0, "output_tokens": 0}},
            }

        patch("jobs.fetch_all_sources", return_value=self._fake_fetch_result()).start()
        patch("jobs.run_pipeline_from_sources", side_effect=failing_pipeline).start()

        resp = self.client.post(f"/api/analyze-company/{job_id}/expand-sources", json={
            "companyUrl": "https://co.com", "competitorUrls": ["https://example.com/rival"],
        })
        self.assertEqual(resp.status_code, 202)
        final = _poll_until_terminal(self.client, job_id)

        self.assertEqual(final["status"], "failed")
        post_checkpoint = job_persistence.load_job_state(job_id)
        # The PRE-expansion strategic_foundation success is gone — invalidated by the
        # expansion attempt and never restored by the backend itself.
        self.assertEqual(post_checkpoint["strategic_foundation"]["outcome"], "invalidated")


class RegenerationCap(unittest.TestCase):
    """MAX_FULL_REGENERATIONS (2) full regenerations are allowed per job. Persisted
    server-side (checkpoint["regenerationCount"]), checked and incremented atomically, a
    third attempt is rejected with 429 regeneration_limit_reached before any API call,
    and a validation failure of the submitted edit never consumes the allowance."""

    def setUp(self):
        self.client = app.test_client()
        self.addCleanup(patch.stopall)
        patch("anthropic_pipeline.get_client", return_value=object()).start()
        self.addCleanup(jobs._QUEUE.join)

    def _seed_regeneratable_job(self):
        sources = [{"id": "src1", "companyId": "live", "title": "Co", "publisher": "co.com",
                     "sourceType": "website", "url": "https://co.com", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"}]
        return _seed_checkpoint_job(
            meta={"kind": "analyze", "status": "done", "stage": "done", "error": None, "createdAt": "2026-01-01T00:00:00Z"},
            fetching_sources={"sources": sources, "sourceTextById": {"src1": "text"}, "caseContext": {"id": "live"}},
            jobInput={"companyUrl": "https://co.com", "supportingUrls": [], "competitorUrls": [], "existingNarrative": ""},
            strategic_foundation={"outcome": "success", "strategicFoundation": [{"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact", "evidence": []}], "evidencePool": {}, "attempts": []},
        )

    def _regenerate(self, job_id, statement="edited"):
        return self.client.post("/api/regenerate", json={
            "sourceJobId": job_id, "companyUrl": "https://co.com",
            "editedFoundation": [{"id": "sf1", "type": "customer", "statement": statement, "statementType": "source_fact", "evidence": []}],
        })

    def test_allows_up_to_two_regenerations_then_rejects_the_third(self):
        job_id = self._seed_regeneratable_job()
        patch("jobs.regenerate_from", return_value=FAKE_SUCCESS_RESULT).start()

        resp1 = self._regenerate(job_id, "first edit")
        self.assertEqual(resp1.status_code, 202)
        checkpoint = job_persistence.load_job_state(job_id)
        self.assertEqual(checkpoint["regenerationCount"], 1)

        resp2 = self._regenerate(job_id, "second edit")
        self.assertEqual(resp2.status_code, 202)
        checkpoint = job_persistence.load_job_state(job_id)
        self.assertEqual(checkpoint["regenerationCount"], 2)

        resp3 = self._regenerate(job_id, "third edit")
        self.assertEqual(resp3.status_code, 429)
        self.assertEqual(resp3.get_json()["error"], "regeneration_limit_reached")
        checkpoint = job_persistence.load_job_state(job_id)
        self.assertEqual(checkpoint["regenerationCount"], 2)  # unchanged by the rejected attempt

    def test_a_rejected_invalid_edit_does_not_consume_the_allowance(self):
        job_id = self._seed_regeneratable_job()
        resp = self.client.post("/api/regenerate", json={
            "sourceJobId": job_id, "companyUrl": "https://co.com",
            "editedFoundation": [{"id": "sf1", "type": "customer"}],  # missing required fields
        })
        self.assertEqual(resp.status_code, 400)
        checkpoint = job_persistence.load_job_state(job_id)
        self.assertNotIn("regenerationCount", checkpoint)

        # Two REAL regenerations must still both be available afterward.
        patch("jobs.regenerate_from", return_value=FAKE_SUCCESS_RESULT).start()
        self.assertEqual(self._regenerate(job_id, "edit one").status_code, 202)
        self.assertEqual(self._regenerate(job_id, "edit two").status_code, 202)
        self.assertEqual(self._regenerate(job_id, "edit three").status_code, 429)

    def test_regeneration_cap_is_checked_before_any_api_call(self):
        job_id = self._seed_regeneratable_job()
        mock_regen = patch("jobs.regenerate_from", return_value=FAKE_SUCCESS_RESULT).start()
        self._regenerate(job_id, "edit one")
        self._regenerate(job_id, "edit two")
        jobs._QUEUE.join()
        calls_before_third = mock_regen.call_count

        resp = self._regenerate(job_id, "edit three")
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(mock_regen.call_count, calls_before_third, "a rejected regeneration must never call regenerate_from")


class PeriodicCleanup(unittest.TestCase):
    """Cleanup runs at startup (jobs.start_worker(), already exercised once when this
    test module imports `from app import app` — not called again here to avoid spawning
    duplicate threads) and periodically via jobs._cleanup_loop() (a plain sleep loop
    around _run_cleanup_once(), called directly here rather than waiting on a real
    timer). Retention is configurable via the jobs.JOB_RETENTION_SECONDS module
    constant."""

    def setUp(self):
        self._orig_retention = jobs.JOB_RETENTION_SECONDS

    def tearDown(self):
        jobs.JOB_RETENTION_SECONDS = self._orig_retention

    def test_cleanup_preserves_a_freshly_saved_active_job(self):
        jobs.JOB_RETENTION_SECONDS = job_persistence.DEFAULT_MAX_AGE_SECONDS
        job_id = "active_job_" + os.urandom(4).hex()
        job_persistence.save_job_state(job_id, {"meta": {"status": "running"}})
        removed = jobs._run_cleanup_once()
        self.assertNotIn(job_id, removed)
        self.assertIsNotNone(job_persistence.load_job_state(job_id))

    def test_cleanup_removes_an_old_job_but_keeps_a_fresh_one_in_the_same_pass(self):
        """Never removes an active/recently-updated job: an old checkpoint (savedAt
        rewritten to simulate real elapsed time, since we can't sleep for real in a
        test) is removed, while a job saved moments ago in the SAME cleanup pass
        survives — proving cleanup discriminates on actual recency, not just "ran"."""
        jobs.JOB_RETENTION_SECONDS = 100
        old_job_id = "old_job_" + os.urandom(4).hex()
        fresh_job_id = "fresh_job_" + os.urandom(4).hex()
        job_persistence.save_job_state(old_job_id, {"meta": {"status": "done"}})
        job_persistence.save_job_state(fresh_job_id, {"meta": {"status": "running"}})

        old_checkpoint_path = job_persistence._checkpoint_path(old_job_id)
        with open(old_checkpoint_path) as f:
            data = json.load(f)
        data["savedAt"] -= 1000  # 1000s old, well past the 100s retention configured above
        with open(old_checkpoint_path, "w") as f:
            json.dump(data, f)

        removed = jobs._run_cleanup_once()
        self.assertIn(old_job_id, removed)
        self.assertNotIn(fresh_job_id, removed)
        self.assertIsNone(job_persistence.load_job_state(old_job_id))
        self.assertIsNotNone(job_persistence.load_job_state(fresh_job_id))

    def test_retention_period_is_configurable(self):
        self.assertIsInstance(jobs.JOB_RETENTION_SECONDS, int)
        jobs.JOB_RETENTION_SECONDS = 42
        job_id = "configurable_job_" + os.urandom(4).hex()
        job_persistence.save_job_state(job_id, {"meta": {"status": "done"}})
        checkpoint_path = job_persistence._checkpoint_path(job_id)
        with open(checkpoint_path) as f:
            data = json.load(f)
        data["savedAt"] -= 43  # just past the 42s retention just configured
        with open(checkpoint_path, "w") as f:
            json.dump(data, f)
        removed = jobs._run_cleanup_once()
        self.assertIn(job_id, removed)

    def test_periodic_cleanup_thread_is_running(self):
        """app.py's module-level jobs.start_worker() call (already fired when this test
        module imported `from app import app`) must have started a dedicated periodic
        cleanup thread, distinct from the pipeline worker thread — verified by name and
        liveness, not by waiting a real CLEANUP_INTERVAL_SECONDS."""
        cleanup_threads = [t for t in threading.enumerate() if t.name == "storymap-cleanup-loop"]
        self.assertTrue(cleanup_threads, "expected a running storymap-cleanup-loop thread")
        self.assertTrue(cleanup_threads[0].is_alive())
        self.assertTrue(cleanup_threads[0].daemon)


class TracebackHardening(unittest.TestCase):
    """Persisted tracebacks are redacted before they ever touch disk (job_persistence.
    redact_traceback, exercised end to end here — unit coverage for the function itself
    lives in test_job_persistence.py), never exposed through any endpoint, and subject
    to the exact same retention cleanup as the rest of a job's checkpoint."""

    def setUp(self):
        self.client = app.test_client()
        self.addCleanup(patch.stopall)
        patch("anthropic_pipeline.get_client", return_value=object()).start()

    def test_secret_in_a_real_failure_is_redacted_before_persistence(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-a-real-looking-secret-value-42"}):
            self._patch = patch(
                "jobs.run_analysis",
                side_effect=RuntimeError("call failed, x-api-key: sk-ant-a-real-looking-secret-value-42"),
            )
            self._patch.start()
            self.addCleanup(self._patch.stop)
            self.addCleanup(jobs._QUEUE.join)

            job_id = self.client.post("/api/analyze-company", json={"companyUrl": "https://example.com"}).get_json()["jobId"]
            _poll_until_terminal(self.client, job_id)

            checkpoint = job_persistence.load_job_state(job_id)
            self.assertIn("_debugTraceback", checkpoint)
            self.assertNotIn("sk-ant-a-real-looking-secret-value-42", checkpoint["_debugTraceback"])
            self.assertIn("REDACTED", checkpoint["_debugTraceback"])

    def test_status_endpoint_never_returns_traceback_field_at_all(self):
        self._patch = patch("jobs.run_analysis", side_effect=RuntimeError("boom, secret=sk-ant-should-never-leak-12345"))
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.addCleanup(jobs._QUEUE.join)

        job_id = self.client.post("/api/analyze-company", json={"companyUrl": "https://example.com"}).get_json()["jobId"]
        final = _poll_until_terminal(self.client, job_id)

        self.assertNotIn("traceback", final)
        self.assertNotIn("_debugTraceback", final)
        body_text = str(final)
        self.assertNotIn("sk-ant-should-never-leak-12345", body_text)

    def test_manual_retry_traceback_is_also_redacted(self):
        sources = [{"id": "src1", "companyId": "live", "title": "Co", "publisher": "co.com",
                     "sourceType": "website", "url": "https://co.com", "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved"}]
        job_id = _seed_checkpoint_job(
            jobInput={"existingNarrative": ""},
            fetching_sources={"sources": sources, "sourceTextById": {"src1": "text"}},
            strategic_foundation={
                "outcome": "success",
                "strategicFoundation": [{"id": "sf1", "type": "customer", "statement": "x", "statementType": "source_fact"}],
                "evidencePool": {},
            },
            diagnosis={"outcome": "stage_failed", "attempts": [
                {"attempt": 1, "manual": False, "outcome": "failed", "validationFailure": "x", "stage": "diagnosis"},
                {"attempt": 2, "manual": False, "outcome": "failed", "validationFailure": "x", "stage": "diagnosis"},
                {"attempt": 3, "manual": False, "outcome": "failed", "validationFailure": "x", "stage": "diagnosis"},
            ]},
        )
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-manual-retry-secret-999"}):
            patch("anthropic_pipeline.diagnose", side_effect=RuntimeError("network error, key sk-ant-manual-retry-secret-999")).start()
            resp = self.client.post(f"/api/analyze-company/{job_id}/retry/diagnosis")
            self.assertEqual(resp.status_code, 202)
            _poll_until_terminal(self.client, job_id)

        checkpoint = job_persistence.load_job_state(job_id)
        self.assertNotIn("sk-ant-manual-retry-secret-999", checkpoint.get("_debugTraceback", ""))

    def test_cleanup_removes_the_traceback_along_with_the_rest_of_an_expired_job(self):
        """No separate retention path for tracebacks to fall through — they live inside
        the SAME checkpoint file cleanup_expired_jobs already removes wholesale."""
        job_id = _seed_checkpoint_job(
            meta={"kind": "analyze", "status": "failed", "stage": "diagnosis", "error": "x", "createdAt": "2026-01-01T00:00:00Z"},
            _debugTraceback="some old traceback content",
        )
        checkpoint_path = job_persistence._checkpoint_path(job_id)
        with open(checkpoint_path) as f:
            data = json.load(f)
        data["savedAt"] -= 10 * 24 * 60 * 60  # 10 days old
        with open(checkpoint_path, "w") as f:
            json.dump(data, f)

        orig_retention = jobs.JOB_RETENTION_SECONDS
        jobs.JOB_RETENTION_SECONDS = job_persistence.DEFAULT_MAX_AGE_SECONDS  # 7 days
        try:
            removed = jobs._run_cleanup_once()
        finally:
            jobs.JOB_RETENTION_SECONDS = orig_retention

        self.assertIn(job_id, removed)
        self.assertIsNone(job_persistence.load_job_state(job_id))


class CorsHeaders(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_allowed_origin_gets_cors_header(self):
        resp = self.client.get("/api/health", headers={"Origin": "http://127.0.0.1:4173"})
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "http://127.0.0.1:4173")

    def test_disallowed_origin_gets_no_cors_header(self):
        resp = self.client.get("/api/health", headers={"Origin": "https://evil.example.com"})
        self.assertIsNone(resp.headers.get("Access-Control-Allow-Origin"))

    def test_no_origin_header_gets_no_cors_header(self):
        resp = self.client.get("/api/health")
        self.assertIsNone(resp.headers.get("Access-Control-Allow-Origin"))


if __name__ == "__main__":
    unittest.main()
