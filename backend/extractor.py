"""Readable-text extraction from fetched HTML.

Prefers trafilatura (purpose-built for stripping nav/ads/cookie-banner/footer
boilerplate from real web pages). Falls back to a plain BeautifulSoup text dump when
trafilatura returns nothing usable — e.g. a page shaped in a way its heuristics don't
recognize. The fallback is intentionally crude (it will include more boilerplate) so a
weak extraction is visibly weak rather than silently empty.
"""
import trafilatura
from bs4 import BeautifulSoup

MAX_EXTRACTED_CHARS = 15000  # per-page cap agreed in the architecture plan


def _bs4_fallback_text(html):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_title(html):
    soup = BeautifulSoup(html, "lxml")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return None


def extract_readable_text(html, url):
    """Returns {title, text, word_count, method, truncated}."""
    extracted = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    method = "trafilatura"

    if not extracted or len(extracted.strip()) < 40:
        extracted = _bs4_fallback_text(html)
        method = "bs4_fallback"

    extracted = (extracted or "").strip()
    truncated = len(extracted) > MAX_EXTRACTED_CHARS
    if truncated:
        extracted = extracted[:MAX_EXTRACTED_CHARS]

    return {
        "title": _extract_title(html),
        "text": extracted,
        "word_count": len(extracted.split()),
        "method": method,
        "truncated": truncated,
    }
