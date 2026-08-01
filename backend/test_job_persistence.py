"""Tests for job_persistence.py — the atomic, file-based, directory-per-job checkpoint
store. Every test runs against a throwaway temp directory (job_persistence.JOB_STATE_ROOT
is redirected in setUp/tearDown) — never the real backend/job_state/.

Run with: python3 -m unittest test_job_persistence -v
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import job_persistence


class JobPersistenceTestCase(unittest.TestCase):
    def setUp(self):
        self._real_root = job_persistence.JOB_STATE_ROOT
        self._tmp_root = tempfile.mkdtemp(prefix="storymap_test_job_state_")
        job_persistence.JOB_STATE_ROOT = self._tmp_root

    def tearDown(self):
        job_persistence.JOB_STATE_ROOT = self._real_root
        shutil.rmtree(self._tmp_root, ignore_errors=True)


class RoundTrip(JobPersistenceTestCase):
    def test_save_then_load_returns_equivalent_state(self):
        job_persistence.save_job_state("job1", {"stage": "diagnosis", "foo": [1, 2, 3]})
        loaded = job_persistence.load_job_state("job1")
        self.assertEqual(loaded["stage"], "diagnosis")
        self.assertEqual(loaded["foo"], [1, 2, 3])

    def test_stamps_schema_version_and_saved_at(self):
        job_persistence.save_job_state("job1", {"x": 1})
        loaded = job_persistence.load_job_state("job1")
        self.assertEqual(loaded["schemaVersion"], job_persistence.JOB_STATE_SCHEMA_VERSION)
        self.assertIn("savedAt", loaded)

    def test_each_job_gets_its_own_directory(self):
        job_persistence.save_job_state("job1", {"x": 1})
        job_persistence.save_job_state("job2", {"x": 2})
        self.assertTrue(os.path.isdir(os.path.join(self._tmp_root, "job1")))
        self.assertTrue(os.path.isdir(os.path.join(self._tmp_root, "job2")))
        self.assertEqual(job_persistence.load_job_state("job1")["x"], 1)
        self.assertEqual(job_persistence.load_job_state("job2")["x"], 2)

    def test_overwriting_replaces_prior_state(self):
        job_persistence.save_job_state("job1", {"stage": "foundation"})
        job_persistence.save_job_state("job1", {"stage": "diagnosis"})
        loaded = job_persistence.load_job_state("job1")
        self.assertEqual(loaded["stage"], "diagnosis")

    def test_write_is_atomic_no_temp_file_left_behind(self):
        job_persistence.save_job_state("job1", {"x": 1})
        job_dir = os.path.join(self._tmp_root, "job1")
        leftovers = [f for f in os.listdir(job_dir) if f.startswith(".tmp_")]
        self.assertEqual(leftovers, [])


class MissingCorruptedIncompatible(JobPersistenceTestCase):
    def test_missing_job_returns_none(self):
        self.assertIsNone(job_persistence.load_job_state("never-saved"))

    def test_corrupted_json_raises_corrupted_error(self):
        job_dir = os.path.join(self._tmp_root, "job1")
        os.makedirs(job_dir)
        with open(os.path.join(job_dir, job_persistence.CHECKPOINT_FILENAME), "w") as f:
            f.write("{not valid json,,,")
        with self.assertRaises(job_persistence.CorruptedJobStateError):
            job_persistence.load_job_state("job1")

    def test_json_missing_schema_version_raises_corrupted_error(self):
        job_dir = os.path.join(self._tmp_root, "job1")
        os.makedirs(job_dir)
        with open(os.path.join(job_dir, job_persistence.CHECKPOINT_FILENAME), "w") as f:
            json.dump({"stage": "diagnosis"}, f)  # valid JSON, but no schemaVersion
        with self.assertRaises(job_persistence.CorruptedJobStateError):
            job_persistence.load_job_state("job1")

    def test_json_array_instead_of_object_raises_corrupted_error(self):
        job_dir = os.path.join(self._tmp_root, "job1")
        os.makedirs(job_dir)
        with open(os.path.join(job_dir, job_persistence.CHECKPOINT_FILENAME), "w") as f:
            json.dump([1, 2, 3], f)
        with self.assertRaises(job_persistence.CorruptedJobStateError):
            job_persistence.load_job_state("job1")

    def test_incompatible_schema_version_raises_incompatible_error(self):
        job_dir = os.path.join(self._tmp_root, "job1")
        os.makedirs(job_dir)
        with open(os.path.join(job_dir, job_persistence.CHECKPOINT_FILENAME), "w") as f:
            json.dump({"schemaVersion": 999, "stage": "diagnosis"}, f)
        with self.assertRaises(job_persistence.IncompatibleJobStateError):
            job_persistence.load_job_state("job1")

    def test_corrupted_error_is_not_silently_swallowed_as_none(self):
        """A corrupted checkpoint must never be indistinguishable from 'no checkpoint
        exists yet' — a caller needs to know the difference to decide whether a retry is
        even possible."""
        job_dir = os.path.join(self._tmp_root, "job1")
        os.makedirs(job_dir)
        with open(os.path.join(job_dir, job_persistence.CHECKPOINT_FILENAME), "w") as f:
            f.write("garbage")
        with self.assertRaises(job_persistence.JobStateError):
            result = job_persistence.load_job_state("job1")
            self.assertIsNone(result)  # unreachable if raised correctly


class SchemaMigrationV1ToV2(JobPersistenceTestCase):
    """Governing spec Phase 1: JOB_STATE_SCHEMA_VERSION bumped 1 -> 2 for the canonical
    candidate status vocabulary (pending/viable/rejected, replacing the overloaded
    "candidate"/"recommended") and the explicit recommendation{outcome,
    selectedCandidateId, failureReason, missingEvidence, leadershipDecisions, createdAt}
    object. Every test here writes a raw v1-shaped file directly to disk (bypassing
    save_job_state, which always stamps the CURRENT version) so load_job_state's
    migration path is exercised exactly as a real pre-existing checkpoint would hit it."""

    def _write_v1(self, job_id, body):
        job_dir = os.path.join(self._tmp_root, job_id)
        os.makedirs(job_dir, exist_ok=True)
        with open(os.path.join(job_dir, job_persistence.CHECKPOINT_FILENAME), "w") as f:
            json.dump({"schemaVersion": 1, "savedAt": 1234.0, **body}, f)

    def test_v1_checkpoint_loads_without_raising(self):
        self._write_v1("job1", {"meta": {"status": "running"}})
        loaded = job_persistence.load_job_state("job1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["schemaVersion"], 2)
        self.assertEqual(loaded["schemaMigratedFrom"], 1)
        self.assertIn("schemaMigratedAt", loaded)

    def test_migration_never_overwrites_the_original_file_on_disk(self):
        """'no automatic overwrite of the original version-1 checkpoint' — load_job_state
        must be read-only with respect to the file; only an explicit later save_job_state
        call for this job_id is allowed to persist the migrated shape."""
        self._write_v1("job1", {"meta": {"status": "running"}})
        path = os.path.join(self._tmp_root, "job1", job_persistence.CHECKPOINT_FILENAME)
        with open(path) as f:
            before = f.read()
        job_persistence.load_job_state("job1")
        with open(path) as f:
            after = f.read()
        self.assertEqual(before, after)

    def test_unmigrated_sections_pass_through_unchanged(self):
        self._write_v1("job1", {"meta": {"status": "running"}, "fetching_sources": {"sources": [{"id": "s1"}]}})
        loaded = job_persistence.load_job_state("job1")
        self.assertEqual(loaded["fetching_sources"], {"sources": [{"id": "s1"}]})

    def test_narrative_choices_candidate_status_migrates_to_pending(self):
        self._write_v1("job1", {
            "meta": {"status": "running"},
            "narrative_choices": {"outcome": "success", "candidates": [{"id": "c1", "status": "candidate"}]},
        })
        loaded = job_persistence.load_job_state("job1")
        cand = loaded["narrative_choices"]["candidates"][0]
        self.assertEqual(cand["status"], "pending")
        self.assertEqual(cand["gateResults"], [])
        self.assertEqual(cand["rejectionReasons"], [])
        self.assertEqual(cand["statusEvaluatedAtStage"], "narrative_choices")

    def test_critique_candidate_status_candidate_migrates_to_viable(self):
        self._write_v1("job1", {
            "meta": {"status": "done"},
            "critique": {"outcome": "success", "candidates": [
                {"id": "c1", "status": "candidate", "scores": {"Strategic fit": 4, "Differentiation": 4, "Evidence strength": 3}},
            ]},
        })
        loaded = job_persistence.load_job_state("job1")
        cand = loaded["critique"]["candidates"][0]
        self.assertEqual(cand["status"], "viable")
        self.assertEqual(cand["statusEvaluatedAtStage"], "critique")
        gate_ids = {g["gateId"] for g in cand["gateResults"]}
        self.assertEqual(gate_ids, {"strategic_fit", "differentiation", "evidence_strength"})

    def test_critique_candidate_status_recommended_also_migrates_to_viable(self):
        """The old third status value ("recommended", written only by
        process_recommend_and_map_response on success) no longer exists — a selected
        candidate is structurally "viable"; selection lives only in
        recommendation.selectedCandidateId (decision 1)."""
        self._write_v1("job1", {
            "meta": {"status": "done"},
            "critique": {"outcome": "success", "candidates": [
                {"id": "c1", "status": "recommended", "scores": {"Strategic fit": 4, "Differentiation": 4, "Evidence strength": 4}},
            ]},
        })
        loaded = job_persistence.load_job_state("job1")
        self.assertEqual(loaded["critique"]["candidates"][0]["status"], "viable")

    def test_critique_candidate_status_rejected_stays_rejected_with_synthesized_reasons(self):
        self._write_v1("job1", {
            "meta": {"status": "done"},
            "critique": {"outcome": "success", "candidates": [
                {"id": "c1", "status": "rejected", "scores": {"Strategic fit": 1, "Differentiation": 3, "Evidence strength": 3}},
            ]},
        })
        loaded = job_persistence.load_job_state("job1")
        cand = loaded["critique"]["candidates"][0]
        self.assertEqual(cand["status"], "rejected")
        self.assertTrue(cand["rejectionReasons"])
        self.assertEqual(cand["rejectionReasons"][0]["gateId"], "strategic_fit")

    def test_borderline_score_of_exactly_threshold_migrates_to_borderline_pass(self):
        self._write_v1("job1", {
            "meta": {"status": "done"},
            "critique": {"outcome": "success", "candidates": [
                {"id": "c1", "status": "candidate", "scores": {"Strategic fit": 3, "Differentiation": 4, "Evidence strength": 4}},
            ]},
        })
        loaded = job_persistence.load_job_state("job1")
        by_id = {g["gateId"]: g for g in loaded["critique"]["candidates"][0]["gateResults"]}
        self.assertEqual(by_id["strategic_fit"]["outcome"], "borderline_pass")

    def test_successful_recommendation_migrates_to_canonical_shape(self):
        self._write_v1("job1", {
            "meta": {"status": "done"},
            "recommendation_and_map": {
                "outcome": "success",
                "recommendation": {"candidateId": "c1", "whyItWins": "x", "missingEvidence": ["needs a customer study"]},
                "narrativeMap": {"unresolvedQuestions": ["Should we reposition?"], "createdAt": "2026-01-01T00:00:00Z"},
            },
        })
        loaded = job_persistence.load_job_state("job1")
        rec = loaded["recommendation_and_map"]["recommendation"]
        self.assertEqual(rec["outcome"], "success")
        self.assertEqual(rec["selectedCandidateId"], "c1")
        self.assertIsNone(rec["failureReason"])
        self.assertEqual(rec["missingEvidence"], ["needs a customer study"])
        self.assertEqual(rec["leadershipDecisions"], ["Should we reposition?"])
        self.assertEqual(rec["detail"]["whyItWins"], "x")
        self.assertNotIn("candidateId", rec["detail"])

    def test_stage_failed_recommendation_migrates_with_failure_reason_from_last_attempt(self):
        self._write_v1("job1", {
            "meta": {"status": "failed", "error": "recommendation_and_map_stage_failed: bad narrativeMap"},
            "recommendation_and_map": {
                "outcome": "stage_failed",
                "attempts": [
                    {"outcome": "failed", "validationFailure": "attempt 1 failed"},
                    {"outcome": "failed", "validationFailure": 'recommendation_and_map response field "narrativeMap" must be dict, got str'},
                ],
            },
        })
        loaded = job_persistence.load_job_state("job1")
        rec = loaded["recommendation_and_map"]["recommendation"]
        self.assertEqual(rec["outcome"], "stage_failed")
        self.assertIsNone(rec["selectedCandidateId"])
        self.assertIn("narrativeMap", rec["failureReason"])
        self.assertIsNone(rec["detail"])

    def test_terminal_job_with_all_rejected_and_no_recommendation_section_synthesizes_no_candidate_passed(self):
        """v1 never called persist_cb for recommendation_and_map on a genuine
        no_candidate_passed outcome — the exact ambiguity this schema exists to fix.
        A terminal (done/failed) job whose critique succeeded with zero viable survivors
        is unambiguously that case, reconstructed here purely from already-migrated data."""
        self._write_v1("job1", {
            "meta": {"status": "done"},
            "critique": {"outcome": "success", "candidates": [
                {"id": "c1", "status": "rejected", "scores": {"Strategic fit": 1, "Differentiation": 1, "Evidence strength": 1}},
                {"id": "c2", "status": "rejected", "scores": {"Strategic fit": 1, "Differentiation": 1, "Evidence strength": 1}},
                {"id": "c3", "status": "rejected", "scores": {"Strategic fit": 1, "Differentiation": 1, "Evidence strength": 1}},
            ]},
            # no "recommendation_and_map" key at all — exactly the v1 no_candidate_passed shape
        })
        loaded = job_persistence.load_job_state("job1")
        self.assertIn("recommendation_and_map", loaded)
        rec = loaded["recommendation_and_map"]["recommendation"]
        self.assertEqual(rec["outcome"], "no_candidate_passed")
        self.assertIsNone(rec["selectedCandidateId"])

    def test_non_terminal_job_with_no_recommendation_section_is_left_alone(self):
        """A job still running (critique succeeded, recommendation_and_map genuinely not
        reached yet) must NOT have no_candidate_passed synthesized — that would be wrong
        (the stage just hasn't run yet, distinct from having run and found nothing)."""
        self._write_v1("job1", {
            "meta": {"status": "running"},
            "critique": {"outcome": "success", "candidates": [
                {"id": "c1", "status": "rejected", "scores": {"Strategic fit": 1, "Differentiation": 1, "Evidence strength": 1}},
            ]},
        })
        loaded = job_persistence.load_job_state("job1")
        self.assertNotIn("recommendation_and_map", loaded)

    def test_terminal_job_with_a_viable_survivor_and_no_recommendation_section_is_left_alone(self):
        """Defensive: if there's a viable candidate but somehow no recommendation_and_map
        section, this is NOT the no_candidate_passed shape — never fabricate an outcome
        that isn't supported by the data."""
        self._write_v1("job1", {
            "meta": {"status": "done"},
            "critique": {"outcome": "success", "candidates": [
                {"id": "c1", "status": "candidate", "scores": {"Strategic fit": 4, "Differentiation": 4, "Evidence strength": 4}},
            ]},
        })
        loaded = job_persistence.load_job_state("job1")
        self.assertNotIn("recommendation_and_map", loaded)

    def test_real_hps_stage_failed_fixture_migrates_to_viable_candidates_with_stage_failed_recommendation(self):
        """The permanent regression fixture: job 3c82acbfff4c4c5f9f3b5f6f9a3857a9's real
        checkpoint from the 2026-07-31 HPS run, copied byte-for-byte (never read from or
        written back to the real backend/job_state/ directory — this test only ever
        touches its own isolated temp root)."""
        real_fixture_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "job_state", "3c82acbfff4c4c5f9f3b5f6f9a3857a9", "checkpoint.json",
        )
        if not os.path.exists(real_fixture_path):
            self.skipTest("real HPS fixture checkpoint not present on this machine")
        with open(real_fixture_path) as f:
            real_checkpoint = json.load(f)
        self.assertEqual(real_checkpoint["schemaVersion"], 1, "fixture is expected to still be a v1 checkpoint on disk")

        job_dir = os.path.join(self._tmp_root, "hps_fixture")
        os.makedirs(job_dir)
        with open(os.path.join(job_dir, job_persistence.CHECKPOINT_FILENAME), "w") as f:
            json.dump(real_checkpoint, f)

        loaded = job_persistence.load_job_state("hps_fixture")
        self.assertEqual(loaded["schemaVersion"], 2)

        candidates = loaded["critique"]["candidates"]
        self.assertEqual(len(candidates), 3)
        statuses = {c["status"] for c in candidates}
        self.assertEqual(statuses, {"viable", "rejected"})
        self.assertTrue(any(c["status"] == "viable" for c in candidates))

        rec = loaded["recommendation_and_map"]["recommendation"]
        self.assertEqual(rec["outcome"], "stage_failed")
        self.assertIsNone(rec["selectedCandidateId"])
        self.assertIn("missingEvidence", rec["failureReason"])

        # The real file on disk is untouched by this read.
        with open(real_fixture_path) as f:
            still_v1 = json.load(f)
        self.assertEqual(still_v1["schemaVersion"], 1)


class DeleteAndCleanup(JobPersistenceTestCase):
    def test_delete_removes_the_job_directory(self):
        job_persistence.save_job_state("job1", {"x": 1})
        job_persistence.delete_job_state("job1")
        self.assertIsNone(job_persistence.load_job_state("job1"))
        self.assertFalse(os.path.isdir(os.path.join(self._tmp_root, "job1")))

    def test_delete_on_nonexistent_job_does_not_raise(self):
        job_persistence.delete_job_state("never-existed")  # must not raise

    def test_cleanup_with_max_age_zero_removes_everything(self):
        job_persistence.save_job_state("job1", {"x": 1})
        job_persistence.save_job_state("job2", {"x": 2})
        removed = job_persistence.cleanup_expired_jobs(max_age_seconds=0, now=job_persistence.time.time() + 100)
        self.assertEqual(set(removed), {"job1", "job2"})
        self.assertIsNone(job_persistence.load_job_state("job1"))
        self.assertIsNone(job_persistence.load_job_state("job2"))

    def test_cleanup_keeps_fresh_jobs_under_the_max_age(self):
        job_persistence.save_job_state("job1", {"x": 1})
        removed = job_persistence.cleanup_expired_jobs(max_age_seconds=job_persistence.DEFAULT_MAX_AGE_SECONDS)
        self.assertEqual(removed, [])
        self.assertIsNotNone(job_persistence.load_job_state("job1"))

    def test_cleanup_removes_corrupted_checkpoints_regardless_of_age(self):
        job_dir = os.path.join(self._tmp_root, "job1")
        os.makedirs(job_dir)
        with open(os.path.join(job_dir, job_persistence.CHECKPOINT_FILENAME), "w") as f:
            f.write("not json")
        removed = job_persistence.cleanup_expired_jobs(max_age_seconds=job_persistence.DEFAULT_MAX_AGE_SECONDS)
        self.assertEqual(removed, ["job1"])

    def test_cleanup_removes_directories_with_no_checkpoint_file_at_all(self):
        os.makedirs(os.path.join(self._tmp_root, "orphan_dir"))
        removed = job_persistence.cleanup_expired_jobs(max_age_seconds=job_persistence.DEFAULT_MAX_AGE_SECONDS)
        self.assertEqual(removed, ["orphan_dir"])

    def test_cleanup_on_missing_root_directory_returns_empty_list(self):
        shutil.rmtree(self._tmp_root)
        removed = job_persistence.cleanup_expired_jobs()
        self.assertEqual(removed, [])


class SafeJobId(JobPersistenceTestCase):
    def test_path_traversal_job_id_is_sanitized(self):
        job_persistence.save_job_state("../../etc/passwd", {"x": 1})
        # Must land inside JOB_STATE_ROOT, never escape it via path traversal.
        for entry in os.listdir(self._tmp_root):
            full = os.path.join(self._tmp_root, entry)
            self.assertTrue(os.path.commonpath([full, self._tmp_root]) == self._tmp_root)

    def test_empty_job_id_raises(self):
        with self.assertRaises(ValueError):
            job_persistence.save_job_state("../../../", {"x": 1})


class TracebackRedaction(unittest.TestCase):
    """redact_traceback() — applied once, right before jobs.py ever writes a traceback
    to disk. No network, no real secrets: patches os.environ so the "real" secret value
    being redacted is a fake test value the assertions themselves control."""

    def test_none_and_empty_are_returned_unchanged(self):
        self.assertIsNone(job_persistence.redact_traceback(None))
        self.assertEqual(job_persistence.redact_traceback(""), "")

    def test_text_with_no_secrets_is_unchanged(self):
        text = "Traceback (most recent call last):\n  File \"x.py\", line 1\nValueError: bad shape"
        self.assertEqual(job_persistence.redact_traceback(text), text)

    def test_literal_env_var_secret_value_is_redacted(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-api03-totally-real-secret-value-xyz"}):
            text = "AuthenticationError: invalid x-api-key header value sk-ant-api03-totally-real-secret-value-xyz"
            redacted = job_persistence.redact_traceback(text)
            self.assertNotIn("sk-ant-api03-totally-real-secret-value-xyz", redacted)
            self.assertIn("[REDACTED]", redacted)

    def test_non_secret_env_vars_are_never_touched(self):
        with patch.dict(os.environ, {"PORT": "5055", "STORYMAP_ALLOWED_ORIGINS": "http://localhost:4173"}):
            text = "Traceback mentioning port 5055 and http://localhost:4173 in a URL"
            self.assertEqual(job_persistence.redact_traceback(text), text)

    def test_short_env_values_are_never_redacted(self):
        """A short value (e.g. a boolean flag "1") is never treated as a secret, even if
        its var name matches — redacting it would mangle unrelated numbers/text."""
        with patch.dict(os.environ, {"SOME_AUTH_FLAG": "1"}):
            text = "retry attempt 1 of 3"
            self.assertEqual(job_persistence.redact_traceback(text), text)

    def test_api_key_shaped_token_is_redacted_even_without_matching_env_var(self):
        """A key-shaped string embedded directly in an error message (never read from
        os.environ in this process) is still caught by the shape-based backstop."""
        text = "response included token sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234 in the body"
        redacted = job_persistence.redact_traceback(text)
        self.assertNotIn("sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_authorization_header_line_is_redacted(self):
        text = "  File \"requests.py\"\nAuthorization: Bearer eyJhbGciOiJIUzI1NiJ9.somesecrettoken.here"
        redacted = job_persistence.redact_traceback(text)
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9.somesecrettoken.here", redacted)
        self.assertIn("Authorization:", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_x_api_key_header_line_is_redacted(self):
        text = "x-api-key: sk-ant-real-value-that-should-never-be-stored"
        redacted = job_persistence.redact_traceback(text)
        self.assertNotIn("sk-ant-real-value-that-should-never-be-stored", redacted)

    def test_long_embedded_file_content_is_redacted_not_just_truncated_partially(self):
        """A fetched webpage's raw HTML ending up inside an exception message (e.g. from
        a str(response)[:...] repr) is the "file contents" case — replaced with a fixed
        marker, never a partial preview of the real content."""
        long_html = "<html><body>" + ("secret page content " * 30) + "</body></html>"
        text = f"TypeError: string indices must be integers: {long_html!r}"
        redacted = job_persistence.redact_traceback(text)
        self.assertNotIn("secret page content", redacted)
        self.assertIn("REDACTED", redacted)

    def test_short_quoted_strings_are_left_alone(self):
        """Only suspiciously LONG embedded content is redacted — an ordinary short
        quoted value in an exception message (e.g. a field name) must survive intact,
        since that's normal, useful debugging context, not a leak."""
        text = "StageResponseError: missing required field 'evidence'"
        self.assertEqual(job_persistence.redact_traceback(text), text)

    def test_redaction_is_idempotent_and_safe_to_apply_to_already_redacted_text(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-real-secret-value-123456"}):
            text = "key was sk-ant-real-secret-value-123456"
            once = job_persistence.redact_traceback(text)
            twice = job_persistence.redact_traceback(once)
            self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
