"""Shared response-envelope validator for every Anthropic-backed pipeline stage.

Real failure history motivates this file:
  - 2026-07-30: recommend_and_map returned "narrativeMap" as a bare string — caught only
    by an ad hoc isinstance check added after the fact at that one call site.
  - 2026-07-31: diagnose() returned a response missing the "evidence" key entirely — an
    unhandled KeyError crashed the whole run, because only recommend_and_map had any
    validation at the time; the other four stages had none.

Both are the same class of bug: code assumed a raw model response was a well-formed
object and read `response["key"]` directly. validate_stage_response() is now the single
place that assumption is ever made — called immediately after every API response is
received, before any other code touches it. It checks the top-level envelope only
(presence and type of each required field); per-item validation of array contents
(filter_malformed_records) and stage-specific deep checks (validate_narrative_map_shape)
remain separate, since those really are stage-unique — this file only owns the generic,
identical-in-shape "is this even a valid response envelope" question.
"""


class StageResponseError(ValueError):
    """Raised by validate_stage_response. Carries the stage name and the exact offending
    field (when known) so a caller can build a structured stage-failure report without
    re-parsing the error message."""

    def __init__(self, stage_name, message, field=None):
        self.stage_name = stage_name
        self.field = field
        super().__init__(message)


def validate_stage_response(stage_name, response, required_schema):
    """required_schema: {field_name: expected_type} where expected_type is one of
    dict, list, str, bool. Never coerces or guesses — raises StageResponseError with the
    exact reason on the first violation found (None response, wrong envelope type,
    missing field, or wrong field type), always before returning.
    """
    if response is None:
        raise StageResponseError(stage_name, f"{stage_name} returned no response (None)")
    if not isinstance(response, dict):
        raise StageResponseError(
            stage_name,
            f"{stage_name} response must be an object, got {type(response).__name__}: {str(response)[:160]!r}",
        )
    missing = [k for k in required_schema if k not in response]
    if missing:
        raise StageResponseError(
            stage_name, f"{stage_name} response is missing required field(s) {missing}", field=missing[0]
        )
    for key, expected_type in required_schema.items():
        value = response[key]
        # bool is a subclass of int in Python but never of str/list/dict, so a plain
        # isinstance check is safe here without a special case.
        if not isinstance(value, expected_type):
            raise StageResponseError(
                stage_name,
                f'{stage_name} response field "{key}" must be {expected_type.__name__}, got {type(value).__name__}: {str(value)[:120]!r}',
                field=key,
            )
    return response


FOUNDATION_RESPONSE_SCHEMA = {
    "evidence": list,
    "strategicFoundation": list,
}

DIAGNOSIS_RESPONSE_SCHEMA = {
    "evidence": list,
    "diagnosis": list,
    "competitorOverlapAssessed": bool,
    "competitorOverlapNote": str,
    "competitorContrasts": list,
}

CANDIDATES_RESPONSE_SCHEMA = {
    "candidates": list,
}

CRITIQUE_RESPONSE_SCHEMA = {
    "critiques": list,
}

RECOMMEND_AND_MAP_RESPONSE_SCHEMA = {
    "recommendedCandidateId": str,
    "recommendedDecision": str,
    "whyItWins": str,
    "whyCustomersCare": str,
    "whyCredible": str,
    "howDifferent": str,
    "missingEvidence": list,
    "tradeoffs": list,
    "leadershipDecisionsRequired": list,
    "whyOthersNotSelected": dict,
    "audiences": list,
    "narrativeMap": dict,
}
