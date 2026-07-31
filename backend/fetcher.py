"""SSRF-safe HTTP fetcher for the 'Analyze a company' live flow.

Redirects are followed manually (not by requests' allow_redirects=True) so every hop —
not just the first URL — passes the same SSRF check. A URL that starts safe but 302s to
a private address is rejected, not silently followed.
"""
import charset_normalizer
import requests

from ssrf_guard import assert_safe_url, guarded_dns, UnsafeUrlError


def _charset_from_content_type(content_type):
    """requests' response.encoding falls back to ISO-8859-1 per the HTTP spec whenever a
    text/* response has no explicit charset= parameter — but most real sites are UTF-8
    without declaring it, and trusting that fallback silently corrupts every non-ASCII
    character (curly quotes, accented names) into mojibake. Only trust an explicitly
    declared charset here; everything else is resolved by decode order in fetch_url."""
    if not content_type:
        return None
    for part in content_type.split(";")[1:]:
        if "=" in part:
            key, _, value = part.partition("=")
            if key.strip().lower() == "charset":
                return value.strip().strip('"').strip("'")
    return None

USER_AGENT = "StoryMap-Analysis-Bot/0.1 (local prototype, single-user; not deployed publicly)"
CONNECT_TIMEOUT_SECONDS = 8
READ_TIMEOUT_SECONDS = 12
MAX_RESPONSE_BYTES = 3 * 1024 * 1024  # 3MB — far more than a marketing page's HTML needs
MAX_REDIRECTS = 5
REDIRECT_STATUS_CODES = (301, 302, 303, 307, 308)


class FetchError(Exception):
    pass


def fetch_url(url):
    """Fetch a single URL, returning {url, final_url, status_code, content_type, html}.
    Raises FetchError for anything unsafe, oversized, non-HTML, or network-failed."""
    current_url = url
    hops = 0

    while True:
        try:
            assert_safe_url(current_url)
        except UnsafeUrlError as exc:
            raise FetchError(f"Blocked unsafe URL: {exc}") from exc

        try:
            with guarded_dns():
                response = requests.get(
                    current_url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
                    allow_redirects=False,
                    stream=True,
                )
        except requests.RequestException as exc:
            raise FetchError(f"Request failed for {current_url}: {exc}") from exc

        if response.status_code in REDIRECT_STATUS_CODES:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise FetchError(f"Redirect from {current_url} had no Location header")
            hops += 1
            if hops > MAX_REDIRECTS:
                raise FetchError(f"Too many redirects starting from {url} (max {MAX_REDIRECTS})")
            current_url = requests.compat.urljoin(current_url, location)
            continue

        if response.status_code >= 400:
            response.close()
            raise FetchError(f"{current_url} returned HTTP {response.status_code}")

        content_type = response.headers.get("Content-Type", "")
        if "html" not in content_type.lower():
            response.close()
            raise FetchError(
                f"Refusing non-HTML content at {current_url} (Content-Type: {content_type or 'unknown'})"
            )

        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=65536):
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                response.close()
                raise FetchError(f"Response from {current_url} exceeded {MAX_RESPONSE_BYTES} byte cap")
            chunks.append(chunk)
        response.close()

        html_bytes = b"".join(chunks)
        html = None
        declared_charset = _charset_from_content_type(content_type)
        # response.apparent_encoding can't be used here — it reads response.content
        # internally, which is already consumed by the manual iter_content loop above.
        # Detect directly from the bytes we already collected instead.
        sniffed = charset_normalizer.from_bytes(html_bytes).best()
        sniffed_encoding = sniffed.encoding if sniffed else None
        for candidate in (declared_charset, "utf-8", sniffed_encoding):
            if not candidate:
                continue
            try:
                html = html_bytes.decode(candidate)
                break
            except (LookupError, UnicodeDecodeError, TypeError):
                continue
        if html is None:
            html = html_bytes.decode("utf-8", errors="replace")

        return {
            "url": url,
            "final_url": current_url,
            "status_code": response.status_code,
            "content_type": content_type,
            "html": html,
        }
