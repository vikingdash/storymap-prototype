"""SSRF protection for the 'Analyze a company' live flow.

A user-supplied URL is only safe to fetch if every address it resolves to is a normal,
public, routable address. Without this check, a URL could point the server at itself
(localhost), at another machine on the same private network, or at a cloud metadata
endpoint (169.254.169.254 on AWS/Azure/GCP) — all of which are unreachable from a real
browser but reachable from this backend process, which is exactly what makes an
unguarded "fetch this URL for me" endpoint a network probe in disguise.

This module provides two layers, used together by fetcher.py:
  1. assert_safe_url() — a fast pre-check with a clear error message, run before any
     network connection is attempted.
  2. guarded_dns() — a context manager that filters socket.getaddrinfo() results for the
     duration of the actual HTTP connection, so a DNS answer that changes between the
     pre-check and the real connect (DNS rebinding) is still caught at connect time, not
     just at check time.
"""
import ipaddress
import socket
from contextlib import contextmanager
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}


class UnsafeUrlError(Exception):
    pass


def _is_public_ip(ip_str):
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # covers 169.254.169.254 cloud metadata on AWS/Azure/GCP
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def assert_safe_url(url):
    """Raises UnsafeUrlError if the URL is not safe to fetch. Returns the resolved
    (hostname, [ip, ...]) pair on success."""
    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"URL scheme must be http or https, got: {parsed.scheme!r}")
    if not parsed.hostname:
        raise UnsafeUrlError("URL has no hostname")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URL must not contain embedded credentials")

    hostname = parsed.hostname

    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Could not resolve hostname {hostname!r}: {exc}") from exc

    resolved_ips = sorted({info[4][0] for info in addr_infos})
    if not resolved_ips:
        raise UnsafeUrlError(f"No addresses resolved for hostname {hostname!r}")

    for ip_str in resolved_ips:
        if not _is_public_ip(ip_str):
            raise UnsafeUrlError(
                f"Hostname {hostname!r} resolves to a blocked address ({ip_str}) — "
                "private, loopback, link-local, multicast and reserved ranges are not fetchable"
            )

    return hostname, resolved_ips


@contextmanager
def guarded_dns():
    """Filters DNS results at the exact moment a connection is made, closing the gap
    between assert_safe_url()'s check and the real TCP connect. Process-global by
    necessity (it patches socket.getaddrinfo), so the caller must not run fetches
    concurrently on multiple threads while this is active — fetcher.py enforces that by
    running the Flask dev server unthreaded."""
    original_getaddrinfo = socket.getaddrinfo

    def guarded_getaddrinfo(host, *args, **kwargs):
        results = original_getaddrinfo(host, *args, **kwargs)
        safe_results = [r for r in results if _is_public_ip(r[4][0])]
        if not safe_results:
            raise socket.gaierror(
                f"All addresses for {host!r} were blocked as unsafe (SSRF guard, connect-time check)"
            )
        return safe_results

    socket.getaddrinfo = guarded_getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo
