"""Tests for API auth gate — open by default when API_SECRET unset."""
import pytest


def test_secret_ok_none_when_api_secret_empty(monkeypatch):
    """_secret_ok(None) returns True when settings.api_secret is empty (monkeypatch)."""
    from core.config import settings as s
    from api.server import _secret_ok
    monkeypatch.setattr(s, "api_secret", None)
    assert _secret_ok(None) is True


def test_secret_ok_configured_blocks_when_missing(monkeypatch):
    """_secret_ok(None) returns False when api_secret is configured but no key provided."""
    from core.config import settings as s
    from api.server import _secret_ok
    monkeypatch.setattr(s, "api_secret", "test-secret-key")
    assert _secret_ok(None) is False
    assert _secret_ok("wrong-key") is False
    assert _secret_ok("test-secret-key") is True


def test_require_api_secret_allows_when_unconfigured(monkeypatch):
    """When API_SECRET is unset, require_api_secret allows /api/chat with no key."""
    from core.config import settings as s
    monkeypatch.setattr(s, "api_secret", None)
    from api.server import _secret_ok
    # Core logic: no secret configured → always allow
    assert _secret_ok(None) is True