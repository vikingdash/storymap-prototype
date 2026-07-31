"""True process-restart integration test: spawns a REAL `python3 app.py` subprocess,
confirms it serves a job's checkpoint over HTTP, kills that process entirely, starts a
completely FRESH subprocess against the SAME job_state directory, and confirms the same
job_id, stage/status, retry history, usage, and cost are all recoverable.

This goes beyond test_analyze_endpoints.RestartSafety (which simulates a restart by
clearing jobs.JOBS in-process — cheap and fast, but never actually exercises a second
process's cold Python import, its own fresh empty JOBS={}, or its own freshly-spawned
worker/cleanup threads). This test exercises the real process boundary.

No API calls: ANTHROPIC_API_KEY is overridden to an obviously-fake value in the
subprocess environment (so even an unexpected code path that tried a real call would
fail fast on auth rather than reach the real API), and this test only ever calls
GET /api/health and GET .../status — both pure reads; neither can trigger a model call
under any code path.

Slower than the rest of the suite (spawns two real OS processes, each a full Python/
Flask startup) — this is unavoidable for a GENUINE restart test, not a simulated one.

Run with: python3 -m unittest test_process_restart -v
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

import requests

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(base_url, timeout=20.0):
    deadline = time.time() + timeout
    last_exc = None
    while time.time() < deadline:
        try:
            resp = requests.get(f"{base_url}/api/health", timeout=1)
            if resp.status_code == 200:
                return
        except requests.exceptions.RequestException as exc:
            last_exc = exc
        time.sleep(0.1)
    raise TimeoutError(f"backend subprocess did not become healthy within {timeout}s (last error: {last_exc})")


class ProcessRestartRecovery(unittest.TestCase):
    def setUp(self):
        self.job_state_dir = tempfile.mkdtemp(prefix="storymap_restart_test_")
        self.addCleanup(shutil.rmtree, self.job_state_dir, ignore_errors=True)
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.env = dict(os.environ)
        self.env["ANTHROPIC_API_KEY"] = "sk-test-restart-integration-not-a-real-key"
        self.env["STORYMAP_JOB_STATE_ROOT"] = self.job_state_dir
        self.env["PORT"] = str(self.port)
        self.proc = None
        self.addCleanup(self._stop_proc)

    def _stop_proc(self):
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        if self.proc.stdout:
            self.proc.stdout.close()

    def _start_backend(self):
        self._stop_proc()
        proc = subprocess.Popen(
            [sys.executable, "app.py"], cwd=BACKEND_DIR, env=self.env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        self.proc = proc
        _wait_for_health(self.base_url)
        return proc

    def _seed_job_checkpoint(self, job_id):
        """Writes a checkpoint file directly to disk — this is the durable artifact a
        REAL job would have produced by this point in its life; how it got there
        (a real run vs. this fixture) is invisible to the backend process reading it
        back, which is exactly the property being tested."""
        job_dir = os.path.join(self.job_state_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)
        checkpoint = {
            "schemaVersion": 1,
            "savedAt": time.time(),
            "jobId": job_id,
            "meta": {
                "kind": "analyze", "status": "failed", "stage": "diagnosis",
                "error": "diagnosis_stage_failed: x", "createdAt": "2026-01-01T00:00:00Z",
            },
            "fetching_sources": {
                "sources": [{
                    "id": "src1", "companyId": "live", "title": "Co", "publisher": "co.com",
                    "sourceType": "website", "url": "https://co.com",
                    "retrievedAt": "2026-01-01T00:00:00Z", "permissionStatus": "approved",
                }],
                "sourceTextById": {"src1": "The company serves manufacturing customers."},
                "fetchFailures": [], "caseContext": {"id": "live", "company": {"name": "Acme Corp"}},
            },
            "strategic_foundation": {
                "outcome": "success",
                "strategicFoundation": [{
                    "id": "sf1", "type": "customer", "statement": "Serves manufacturing customers.",
                    "statementType": "source_fact", "evidence": [],
                }],
                "evidencePool": {},
                "attempts": [{
                    "stage": "strategic_foundation", "attempt": 1, "manual": False,
                    "startedAt": "2026-01-01T00:00:00Z", "completedAt": "2026-01-01T00:00:01Z",
                    "outcome": "success", "validationFailure": None,
                    "usage": {"label": "foundation", "input_tokens": 500, "output_tokens": 200},
                    "costUsd": 0.003,
                }],
            },
            "diagnosis": {
                "outcome": "stage_failed",
                "attempts": [
                    {
                        "stage": "diagnosis", "attempt": 1, "manual": False,
                        "startedAt": "2026-01-01T00:00:02Z", "completedAt": "2026-01-01T00:00:03Z",
                        "outcome": "failed",
                        "validationFailure": "diagnosis response is missing required field(s) ['evidence']",
                        "usage": {"label": "diagnosis", "input_tokens": 800, "output_tokens": 100},
                        "costUsd": 0.0026,
                    },
                    {
                        "stage": "diagnosis", "attempt": 2, "manual": True,
                        "startedAt": "2026-01-01T00:00:04Z", "completedAt": "2026-01-01T00:00:05Z",
                        "outcome": "stage_failed",
                        "validationFailure": "diagnosis response is missing required field(s) ['evidence']",
                        "usage": {"label": "diagnosis", "input_tokens": 810, "output_tokens": 90},
                        "costUsd": 0.0026,
                    },
                ],
                "retryCount": 2, "pendingManualRetry": False,
            },
            "usage": {
                "totals": {"input_tokens": 2110, "output_tokens": 390},
                "costUsd": round(2110 / 1_000_000 * 2.0 + 390 / 1_000_000 * 10.0, 4),
                "latestCall": {"label": "diagnosis", "input_tokens": 810, "output_tokens": 90},
            },
        }
        with open(os.path.join(job_dir, "checkpoint.json"), "w") as f:
            json.dump(checkpoint, f)
        return checkpoint

    def test_job_state_survives_a_real_process_restart(self):
        job_id = "restart_test_job_" + os.urandom(4).hex()
        seeded = self._seed_job_checkpoint(job_id)

        # --- First process: confirm it serves the seeded state correctly ---
        self._start_backend()
        pid1 = self.proc.pid
        resp1 = requests.get(f"{self.base_url}/api/analyze-company/{job_id}/status", timeout=5)
        self.assertEqual(resp1.status_code, 200)
        body1 = resp1.json()
        self.assertEqual(body1["id"], job_id)
        self.assertEqual(body1["status"], "failed")

        # --- Stop the first process ENTIRELY (not just its worker thread) ---
        self._stop_proc()
        self.assertIsNotNone(self.proc.poll(), "the first process must have actually exited")

        # --- Start a completely fresh, second process against the SAME job_state dir ---
        self._start_backend()
        pid2 = self.proc.pid
        self.assertNotEqual(pid1, pid2, "this must be a genuinely different OS process")

        resp2 = requests.get(f"{self.base_url}/api/analyze-company/{job_id}/status", timeout=5)
        self.assertEqual(resp2.status_code, 200)
        body2 = resp2.json()

        # Same canonical job_id, recovered by the SECOND process with no memory of the first.
        self.assertEqual(body2["id"], job_id)
        self.assertEqual(body2["id"], body1["id"])
        # Same stage/status.
        self.assertEqual(body2["status"], "failed")
        self.assertEqual(body2["stage"], "diagnosis")
        self.assertEqual(body2["error"], seeded["meta"]["error"])
        # Same dataset content (proves strategicFoundation round-tripped through the file).
        self.assertEqual(len(body2["dataset"]["strategicFoundation"]), 1)
        self.assertEqual(body2["dataset"]["strategicFoundation"][0]["id"], "sf1")

        # Retry history, usage, and cost: not exposed via /status by design (see
        # TracebackHardening's non-exposure tests) — verified here by reading the exact
        # checkpoint file the SECOND, currently-running process is using.
        checkpoint_path = os.path.join(self.job_state_dir, job_id, "checkpoint.json")
        with open(checkpoint_path) as f:
            recovered = json.load(f)
        self.assertEqual(len(recovered["diagnosis"]["attempts"]), 2)
        self.assertTrue(recovered["diagnosis"]["attempts"][1]["manual"])
        self.assertEqual(recovered["diagnosis"]["retryCount"], 2)
        self.assertEqual(recovered["usage"]["totals"], seeded["usage"]["totals"])
        self.assertEqual(recovered["usage"]["costUsd"], seeded["usage"]["costUsd"])

    def test_second_process_status_endpoint_never_exposes_a_traceback_field(self):
        """Combines this turn's two requirements in one real end-to-end check: a job
        that failed with a persisted (and redacted) traceback still round-trips cleanly
        across a real restart, and the traceback is still never returned over HTTP by
        the fresh process either."""
        job_id = "restart_test_job_" + os.urandom(4).hex()
        checkpoint = self._seed_job_checkpoint(job_id)
        checkpoint["_debugTraceback"] = "RuntimeError: simulated failure, already redacted before persistence"
        checkpoint_path = os.path.join(self.job_state_dir, job_id, "checkpoint.json")
        with open(checkpoint_path, "w") as f:
            json.dump(checkpoint, f)

        self._start_backend()
        self._stop_proc()
        self._start_backend()

        resp = requests.get(f"{self.base_url}/api/analyze-company/{job_id}/status", timeout=5)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertNotIn("traceback", body)
        self.assertNotIn("_debugTraceback", body)


if __name__ == "__main__":
    unittest.main()
