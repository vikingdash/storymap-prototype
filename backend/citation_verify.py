"""Server-side citation verification.

A model can cite a source without actually quoting it — the whole point of the
evidence-integrity rules this app enforces is that a claim is only as good as its proof,
and a fabricated excerpt is proof of nothing. Every EvidenceItem['excerpt'] the model
produces is checked here against the literal fetched text of the source it claims to come
from, before that evidence item is trusted anywhere downstream (confidence computation,
narrative claims, the map). An excerpt that doesn't verify is not discarded silently — the
caller keeps it, marked unverified, so the failure is visible in the report rather than
swallowed.
"""
import re


def _normalize(text):
    """Collapse whitespace and smart-quote/dash variants so a verbatim-but-reformatted
    quote (line breaks, curly vs straight quotes) still matches, while an actually
    fabricated excerpt still fails."""
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def excerpt_is_verified(excerpt, source_text):
    """True if `excerpt` is a real (whitespace/quote-normalized) substring of
    `source_text`."""
    if not excerpt or not source_text:
        return False
    return _normalize(excerpt) in _normalize(source_text)


def verify_evidence_items(evidence_items, source_text_by_id):
    """Returns (verified_items, unverified_items) — unverified items are annotated with
    a `verified: False` flag rather than dropped, so a caller can report exactly what
    failed instead of just a count."""
    verified, unverified = [], []
    for item in evidence_items:
        source_text = source_text_by_id.get(item["sourceId"], "")
        ok = excerpt_is_verified(item["excerpt"], source_text)
        item["verified"] = ok
        (verified if ok else unverified).append(item)
    return verified, unverified
