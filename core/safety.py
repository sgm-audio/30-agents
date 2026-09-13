"""Security helpers for URL and workspace-path validation.

URL validation lives in exactly one place — `core.validation` — so the DNS
decisions made by pre-flight checks and by the pinning transports in
`core.pinned_http` can never drift. This module re-exports that
implementation for the call sites written against the `core.safety` path;
workspace confinement below is unchanged.
"""
from __future__ import annotations

import os
from pathlib import Path

from core.validation import resolve_public_ips, validate_public_http_url

__all__ = [
    "WORKSPACE_ROOT",
    "resolve_public_ips",
    "resolve_workspace_path",
    "validate_public_http_url",
]


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
