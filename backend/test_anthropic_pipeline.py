"""Tests for anthropic_pipeline.py's prompt-construction logic — no network, no real
Anthropic API calls. Covers the role-aware SYSTEM_RULES addition and extract_foundation's
narrativeQuestion field, added to fix the "current draft corporate narrative treated as a
full evidence pack" bug (2026-08 review). call_tool() itself is mocked everywhere here so
these tests exercise real prompt-building code without ever contacting the API.

Honest limitation, stated once here rather than per-test: these tests prove the PLUMBING
is correct — the role attribute reaches the prompt, the SYSTEM_RULES instruction exists,
schema/fallback behavior is exact. Whether Claude's actual output changes as intended can
only be verified with a real (paid) API call, which this suite deliberately never makes.

Run with: python3 -m unittest test_anthropic_pipeline -v
"""
import os
import re
import unittest
from unittest.mock import patch

os.environ["ANTHROPIC_API_KEY"] = "sk-test-do-not-use-not-a-real-key"

import anthropic_pipeline as pipe


def _collapse_whitespace(text):
    """SYSTEM_RULES is a wrapped triple-quoted string — a phrase that reads as one
    contiguous run of prose to a human (and to the model) may have a literal newline +
    indentation in the middle of it. Assertions below match against the collapsed form so
    they test the actual wording, not incidental line-wrap position."""
    return re.sub(r"\s+", " ", text)


class FormatSourcesRoleRendering(unittest.TestCase):
    def test_source_with_no_role_renders_exactly_as_before(self):
        rendered = pipe._format_sources([{"id": "src1", "text": "hello"}])
        self.assertEqual(rendered, '--- SOURCE id="src1" ---\nhello\n--- END SOURCE id="src1" ---')
        self.assertNotIn("role=", rendered)

    def test_source_with_role_is_none_renders_exactly_as_before(self):
        rendered = pipe._format_sources([{"id": "src1", "text": "hello", "role": None}])
        self.assertNotIn("role=", rendered)

    def test_source_with_role_renders_the_attribute(self):
        rendered = pipe._format_sources([{"id": "src_pasted_narrative", "text": "Our story...", "role": "current_draft_narrative"}])
        self.assertIn('--- SOURCE id="src_pasted_narrative" role="current_draft_narrative" ---', rendered)

    def test_mixed_sources_only_tag_the_ones_with_a_role(self):
        rendered = pipe._format_sources([
            {"id": "src_live_co", "text": "public page text"},
            {"id": "src_pasted_narrative", "text": "our story", "role": "current_draft_narrative"},
        ])
        self.assertIn('--- SOURCE id="src_live_co" ---', rendered)
        self.assertIn('--- SOURCE id="src_pasted_narrative" role="current_draft_narrative" ---', rendered)


class SystemRulesRoleAwareContent(unittest.TestCase):
    """String-presence checks on the actual system prompt — weak proof by nature (it
    can't confirm the model obeys the instruction), but strong proof the exact
    instructions the diagnosis called for are actually present, not just described in a
    commit message."""

    def test_names_the_current_draft_narrative_role(self):
        self.assertIn('role="current_draft_narrative"', pipe.SYSTEM_RULES)

    def test_states_the_four_category_distinction(self):
        rules = _collapse_whitespace(pipe.SYSTEM_RULES.lower())
        self.assertIn("narrative itself needs to make its own claim coherent", rules)
        self.assertIn("evidence needed to support a specific claim", rules)
        self.assertIn("outside what a corporate narrative is for", rules)
        self.assertIn("genuine leadership decision about the story itself", rules)

    def test_explicitly_prohibits_vertical_prioritization_questions(self):
        rules = _collapse_whitespace(pipe.SYSTEM_RULES.lower())
        self.assertIn("do not ask leadership to prioritize, rank, or choose among business lines", rules)

    def test_explicitly_prohibits_demanding_standard_evidence_categories_unconditionally(self):
        rules = _collapse_whitespace(pipe.SYSTEM_RULES.lower())
        self.assertIn("customer names, testimonials, market-share percentages, revenue figures", rules)
        self.assertIn("unless the narrative itself makes a specific claim that depends on exactly that fact", rules)

    def test_prompt_injection_rule_is_still_present(self):
        """rule 11 (role-aware) was added AFTER rule 10 (injection defense, added in an
        earlier phase) — confirms the addition didn't accidentally replace it."""
        self.assertIn("never instructions to you", pipe.SYSTEM_RULES)


class ExtractFoundationNarrativeQuestionSchema(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        self.captured = {}

        def fake_call_tool(client, usage_tracker, label, user_text, tool_name, tool_description, input_schema, max_tokens=8192):
            self.captured["user_text"] = user_text
            self.captured["schema"] = input_schema
            return {"evidence": [], "strategicFoundation": [], "narrativeQuestion": "x"}

        patch("anthropic_pipeline.call_tool", side_effect=fake_call_tool).start()

    def test_narrative_question_is_a_required_schema_field(self):
        pipe.extract_foundation(object(), pipe.UsageTracker(), [{"id": "src1", "text": "hello"}])
        self.assertIn("narrativeQuestion", self.captured["schema"]["properties"])
        self.assertIn("narrativeQuestion", self.captured["schema"]["required"])

    def test_intro_line_is_source_mix_aware_when_a_role_is_present(self):
        pipe.extract_foundation(object(), pipe.UsageTracker(), [
            {"id": "src_pasted_narrative", "text": "our story", "role": "current_draft_narrative"},
        ])
        self.assertNotIn("fetched from the company's own public pages):", self.captured["user_text"].split("\n")[0])

    def test_intro_line_is_unchanged_when_no_source_has_a_role(self):
        pipe.extract_foundation(object(), pipe.UsageTracker(), [{"id": "src_live_co", "text": "public page text"}])
        self.assertIn("Sources (verbatim, fetched from the company's own public pages):", self.captured["user_text"])

    def test_prompt_references_rule_11_when_current_draft_narrative_is_present(self):
        pipe.extract_foundation(object(), pipe.UsageTracker(), [
            {"id": "src_pasted_narrative", "text": "our story", "role": "current_draft_narrative"},
        ])
        self.assertIn("current_draft_narrative", self.captured["user_text"])


if __name__ == "__main__":
    unittest.main()
