"""Security helpers for URL and workspace-path validation."""
from __future__ import annotations

import ipaddress
import os
import socket
from pathlib import Path
from urllib.parse import urlparse


_DEFAULT_WORKSPACE = Path(__file__).parent.parent / "data" / "workspace"
WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_OVERRIDE", _DEFAULT_WORKSPACE)).resolve()


def resolve_workspace_path(user_path: str) -> Path | None:
    """Resolve a user-provided path and require it to stay within WORKSPACE_ROOT."""
    if not isinstance(user_path, str):
        return None

    user_path = user_path.strip()
    if not user_path:
        return None
    if "\x00" in user_path:
        return None

    candidate = Path(user_path)
    if candidate.is_absolute():
        return None
    candidate = WORKSPACE_ROOT / candidate

    try:
        resolved = candidate.resolve()
    except Exception:
        return None

    workspace_root = WORKSPACE_ROOT.resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError:
        return None
    return resolved


def validate_public_http_url(url: str) -> str | None:
    """Allow only http(s) URLs that resolve to public (non-local/private) IPs.

    This is a best-effort preflight check; callers should still treat outbound fetches
    as untrusted network operations.
    """
    if not isinstance(url, str):
        return None

    candidate = url.strip()
    if not candidate or len(candidate) > 2048:
        return None

    parsed = urlparse(candidate)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None

    try:
        addrinfos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        return None

    for info in addrinfos:
        ip_text = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            return None
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return None

    return candidate
