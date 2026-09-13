"""
Pinned HTTP clients — SSRF defense against DNS-rebinding TOCTOU.

`validate_public_http_url()` resolves and checks DNS *before* connecting, but a
hostile hostname can resolve to a public IP at check time and to an internal
IP (169.254.169.254, 127.0.0.1, ...) at connect time. These transports close
that gap:

1. On every request they resolve the hostname themselves via
   `core.validation.resolve_public_ips()`, which raises unless ALL resolved
   addresses are public.
2. They pin the connection to the first validated IP by rewriting the request
   URL host to the IP literal. TCP can then only ever go to a validated
   address, no matter what DNS does afterwards.
3. The original hostname is preserved in the `Host` header (so virtual hosting
   keeps working) and, for https, passed as the `sni_hostname` request
   extension so httpcore validates the server certificate against the real
   hostname instead of the IP literal.

Redirects are NEVER followed automatically (`follow_redirects=False` on every
client built here). Use `fetch_public()` / `afetch_public()`, which re-resolve
and re-validate every hop through this same transport.

Proxies and `trust_env` are disabled on pinned clients: an attacker who can
influence the environment could otherwise route requests around the transport.
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urljoin

import httpx

from core.validation import resolve_public_ips, validate_public_http_url

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_DEFAULT_PORTS = {"http": 80, "https": 443}


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def pin_request(request: httpx.Request) -> httpx.Request:
    """Pin `request` to a validated IP. Mutates and returns the request.

    Raises ValueError if the URL is not a public http(s) target. IP-literal
    hosts are validated and passed through untouched (nothing to pin).
    """
    url = request.url
    if url.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme must be http or https, got {url.scheme!r}")
    host = url.host
    if not host:
        raise ValueError("URL has no hostname")

    port = url.port or _DEFAULT_PORTS[url.scheme]
    ips = resolve_public_ips(host, port)
    if _is_ip_literal(host):
        return request  # already an IP literal — validated, nothing to pin.

    pinned = ips[0]
    request.url = url.copy_with(host=pinned)

    # Preserve the original authority for virtual hosting. An explicit
    # non-default port is kept; the default port is elided per RFC 7230.
    host_header = host if port == _DEFAULT_PORTS[url.scheme] else f"{host}:{port}"
    request.headers["host"] = host_header

    if url.scheme == "https":
        # httpcore uses this for SNI *and* certificate hostname verification,
        # while TCP connects to the pinned IP in the rewritten URL.
        request.extensions["sni_hostname"] = host
    return request


class PinnedSyncTransport(httpx.HTTPTransport):
    """Sync transport that pins every request to a validated public IP."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return super().handle_request(pin_request(request))


class PinnedAsyncTransport(httpx.AsyncHTTPTransport):
    """Async transport that pins every request to a validated public IP."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await super().handle_async_request(pin_request(request))


def pinned_client(
    *,
    timeout: float = 10.0,
    headers: dict[str, str] | None = None,
) -> httpx.Client:
    """Build a sync client with pinning, no auto-redirects, no proxies."""
    return httpx.Client(
        transport=PinnedSyncTransport(),
        follow_redirects=False,
        trust_env=False,
        timeout=timeout,
        headers=headers,
    )


def pinned_async_client(
    *,
    timeout: float = 10.0,
    headers: dict[str, str] | None = None,
) -> httpx.AsyncClient:
    """Build an async client with pinning, no auto-redirects, no proxies."""
    return httpx.AsyncClient(
        transport=PinnedAsyncTransport(),
        follow_redirects=False,
        trust_env=False,
        timeout=timeout,
        headers=headers,
    )


def _next_hop(current: str, location: str) -> str:
    """Resolve a redirect Location against the current URL and pre-validate it.

    Raises ValueError if the next hop is not a public http(s) target. (The
    transport re-validates on send regardless — this is for clear errors.)
    """
    return validate_public_http_url(urljoin(current, location))


def fetch_public(
    url: str,
    *,
    timeout: float = 10.0,
    max_redirects: int = 3,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """GET a user-derived URL over a pinned connection (sync).

    Every redirect hop is re-resolved and re-validated. Raises ValueError for
    blocked targets or redirect abuse; other httpx errors propagate.
    """
    current = validate_public_http_url(url)
    with pinned_client(timeout=timeout, headers=headers) as client:
        for _ in range(max_redirects + 1):
            resp = client.get(current)
            if resp.status_code not in _REDIRECT_STATUSES:
                return resp
            location = resp.headers.get("location", "")
            if not location:
                return resp
            current = _next_hop(current, location)
    raise ValueError(f"Too many redirects for URL: {url[:120]}")


async def afetch_public(
    url: str,
    *,
    timeout: float = 10.0,
    max_redirects: int = 3,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """GET a user-derived URL over a pinned connection (async).

    Every redirect hop is re-resolved and re-validated. Raises ValueError for
    blocked targets or redirect abuse; other httpx errors propagate.
    """
    current = validate_public_http_url(url)
    async with pinned_async_client(timeout=timeout, headers=headers) as client:
        for _ in range(max_redirects + 1):
            resp = await client.get(current)
            if resp.status_code not in _REDIRECT_STATUSES:
                return resp
            location = resp.headers.get("location", "")
            if not location:
                return resp
            current = _next_hop(current, location)
    raise ValueError(f"Too many redirects for URL: {url[:120]}")
