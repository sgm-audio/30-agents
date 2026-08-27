"""
Input validation for security-sensitive sinks (SSRF + path traversal).

- validate_public_http_url(): SSRF defense for outbound HTTP fetches.
  Requires an http(s) URL whose hostname resolves to public IPs only.
- resolve_allowed_path(): confines agent file reads to an allow-list of
  root directories (project root, cwd, user home; extend via the
  AGENT_ALLOWED_PATHS env var, os.pathsep-separated).

Both helpers exist to break taint flows between user-controlled input
(task/context fields, HTTP request bodies) and network/filesystem sinks.
Callers must use the *returned* value against the sink, after the check.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from pathlib import Path
from urllib.parse import urlparse

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_DEFAULT_PORTS = {"http": 80, "https": 443}

# Well-known non-public hostnames that should never be fetched on behalf of
# a user-supplied URL (checked before DNS; DNS results are then IP-filtered
# to catch decimal/hex IPs, DNS-rebinding, and internal DNS names).
_BLOCKED_HOSTNAMES = frozenset({
    "localhost",
    "localhost.localdomain",
    "broadcasthost",
})


# Networks Python's ipaddress doesn't universally flag as non-public but that
# must never be fetch targets (CGNAT is not routable on the public internet).
_EXTRA_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in ("100.64.0.0/10",)  # RFC 6598 CGNAT
)


def _is_public_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast \
            or ip.is_reserved or ip.is_unspecified:
        return False
    return not any(ip in net for net in _EXTRA_BLOCKED_NETWORKS)


def validate_public_http_url(url: str) -> str:
    """Validate that `url` is safe to fetch on behalf of a user.

    Enforces: http/https scheme, resolvable non-blocked hostname, and every
    resolved address is a public IP. Returns the URL unchanged; raises
    ValueError otherwise.

    Note: the initial target is validated. Callers using follow_redirects=True
    should be aware redirect hops are not re-validated.
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"URL scheme must be http or https, got {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise ValueError("URL has no hostname")
    if host.lower() in _BLOCKED_HOSTNAMES:
        raise ValueError(f"Hostname is not allowed: {host}")
    port = parsed.port or _DEFAULT_PORTS[parsed.scheme]  # parsed.port may raise ValueError
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as e:
        raise ValueError(f"Hostname does not resolve: {host}") from e
    if not infos:
        raise ValueError(f"Hostname does not resolve: {host}")
    for info in infos:
        if not _is_public_ip(info[4][0]):
            raise ValueError(f"URL host does not resolve to a public address: {host}")
    return url


def _allowed_roots(extra_roots: list[str | Path] | None = None) -> list[str]:
    roots: list[str | Path] = [
        Path(__file__).resolve().parent.parent,  # project root
        Path.cwd(),
        Path.home(),
    ]
    env = os.environ.get("AGENT_ALLOWED_PATHS", "")
    roots.extend(p for p in env.split(os.pathsep) if p)
    if extra_roots:
        roots.extend(extra_roots)
    # Normalize each root once so candidate-vs-root comparison is apples-to-apples.
    return [os.path.normcase(os.path.realpath(str(r))) for r in roots]


def resolve_allowed_path(raw_path: str, extra_roots: list[str | Path] | None = None) -> Path:
    """Normalize a user-supplied path and confine it to allowed roots.

    Returns the real, normalized path if it is inside one of the allowed
    roots; raises ValueError otherwise. `~` is expanded, relative paths are
    resolved against the cwd, and symlinks/junctions are resolved before the
    containment check.
    """
    p = Path(raw_path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    fullpath = os.path.normcase(os.path.realpath(str(p)))
    for root in _allowed_roots(extra_roots):
        if fullpath == root or fullpath.startswith(root + os.sep):
            return Path(fullpath)
    raise ValueError(f"Path is outside allowed roots: {raw_path}")
