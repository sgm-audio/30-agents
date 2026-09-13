"""Tests for core/pinned_http.py (DNS-pinning SSRF transport).

All tests are hermetic: DNS resolution is stubbed and the underlying
httpcore transport is monkeypatched, so no network access occurs — except
IP-literal checks, which the OS resolver answers locally without DNS.
"""
import httpx
import pytest

import core.pinned_http as ph
from core.pinned_http import (
    PinnedAsyncTransport,
    PinnedSyncTransport,
    afetch_public,
    fetch_public,
    pin_request,
)
from core.validation import resolve_public_ips


def _stub_resolve(monkeypatch):
    """Stub DNS: names resolve to a canned public IP, literals are checked.

    Stubs both `resolve_public_ips` (used by the transport) and
    `validate_public_http_url` (used for pre-flight/redirect checks) so tests
    never touch the network.
    """
    import ipaddress
    from urllib.parse import urlparse

    from core.validation import _is_public_ip

    def _fake_resolve(host, port):
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return ["93.184.216.34"]  # pretend DNS resolved to a public IP
        if not _is_public_ip(host):
            raise ValueError(f"URL host does not resolve to a public address: {host}")
        return [host]

    def _fake_validate(url):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"URL scheme must be http or https, got {parsed.scheme!r}")
        if not parsed.hostname:
            raise ValueError("URL has no hostname")
        _fake_resolve(parsed.hostname, parsed.port or 443)
        return url

    monkeypatch.setattr(ph, "resolve_public_ips", _fake_resolve)
    monkeypatch.setattr(ph, "validate_public_http_url", _fake_validate)


class TestResolvePublicIps:
    @pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1"])
    def test_accepts_public_ip_literals(self, ip):
        assert resolve_public_ips(ip, 443) == [ip]

    @pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "0.0.0.0"])
    def test_rejects_non_public_ip_literals(self, ip):
        with pytest.raises(ValueError):
            resolve_public_ips(ip, 443)

    def test_rejects_blocked_hostname_without_dns(self):
        with pytest.raises(ValueError):
            resolve_public_ips("localhost", 80)


class TestPinRequest:
    def test_rewrites_host_preserves_authority_and_sni(self, monkeypatch):
        _stub_resolve(monkeypatch)
        req = pin_request(httpx.Request("GET", "https://example.com:8443/a?b=c"))
        assert str(req.url) == "https://93.184.216.34:8443/a?b=c"
        assert req.headers["host"] == "example.com:8443"
        assert req.extensions["sni_hostname"] == "example.com"

    def test_default_port_elided_from_host(self, monkeypatch):
        _stub_resolve(monkeypatch)
        req = pin_request(httpx.Request("GET", "https://example.com/a"))
        assert str(req.url) == "https://93.184.216.34/a"
        assert req.headers["host"] == "example.com"

    def test_http_gets_host_but_no_sni(self, monkeypatch):
        _stub_resolve(monkeypatch)
        req = pin_request(httpx.Request("GET", "http://example.com/a"))
        assert str(req.url) == "http://93.184.216.34/a"
        assert req.headers["host"] == "example.com"
        assert "sni_hostname" not in req.extensions

    def test_ip_literal_passes_through_untouched(self):
        req = pin_request(httpx.Request("GET", "https://8.8.8.8/a"))
        assert str(req.url) == "https://8.8.8.8/a"
        assert "sni_hostname" not in req.extensions

    def test_private_target_raises_before_connect(self, monkeypatch):
        _stub_resolve(monkeypatch)
        with pytest.raises(ValueError):
            pin_request(httpx.Request("GET", "http://169.254.169.254/latest"))

    def test_non_http_scheme_raises(self, monkeypatch):
        _stub_resolve(monkeypatch)
        with pytest.raises(ValueError):
            pin_request(httpx.Request("GET", "file:///etc/passwd"))


class TestPinnedTransports:
    def test_sync_transport_pins(self, monkeypatch):
        _stub_resolve(monkeypatch)
        captured = {}

        def _fake_handle(self, request):
            captured["url"] = str(request.url)
            captured["host"] = request.headers.get("host")
            captured["sni"] = request.extensions.get("sni_hostname")
            return httpx.Response(200, text="ok")

        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _fake_handle)
        resp = PinnedSyncTransport().handle_request(httpx.Request("GET", "https://example.com/"))
        assert resp.status_code == 200
        assert captured["url"] == "https://93.184.216.34/"
        assert captured["host"] == "example.com"
        assert captured["sni"] == "example.com"

    async def test_async_transport_pins(self, monkeypatch):
        _stub_resolve(monkeypatch)
        captured = {}

        async def _fake_handle(self, request):
            captured["url"] = str(request.url)
            captured["sni"] = request.extensions.get("sni_hostname")
            return httpx.Response(200, text="ok")

        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _fake_handle)
        resp = await PinnedAsyncTransport().handle_async_request(httpx.Request("GET", "https://example.com/"))
        assert resp.status_code == 200
        assert captured["url"] == "https://93.184.216.34/"
        assert captured["sni"] == "example.com"


class TestFetchPublic:
    def _redirect_chain(self, monkeypatch, locations):
        """Queue of redirect hops; final hop returns 200."""
        _stub_resolve(monkeypatch)
        calls = []

        def _fake_handle(self, request):
            calls.append(str(request.url))
            if locations:
                return httpx.Response(302, headers={"location": locations.pop(0)})
            return httpx.Response(200, text="done")

        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _fake_handle)
        return calls

    def test_follows_public_redirects(self, monkeypatch):
        calls = self._redirect_chain(monkeypatch, ["https://8.8.8.8/next"])
        resp = fetch_public("https://example.com/")
        assert resp.status_code == 200
        assert calls[0] == "https://93.184.216.34/"
        assert calls[1] == "https://8.8.8.8/next"

    def test_blocked_redirect_hop_raises(self, monkeypatch):
        self._redirect_chain(monkeypatch, ["http://169.254.169.254/x"])
        with pytest.raises(ValueError):
            fetch_public("https://example.com/")

    def test_too_many_redirects_raises(self, monkeypatch):
        self._redirect_chain(monkeypatch, ["https://8.8.8.8/1"] * 5)
        with pytest.raises(ValueError, match="Too many redirects"):
            fetch_public("https://example.com/")

    def test_private_target_blocked_without_network(self):
        with pytest.raises(ValueError):
            fetch_public("http://127.0.0.1/")

    async def test_async_blocked_redirect_hop_raises(self, monkeypatch):
        _stub_resolve(monkeypatch)

        async def _fake_handle(self, request):
            return httpx.Response(302, headers={"location": "http://10.0.0.1/x"})

        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _fake_handle)
        with pytest.raises(ValueError):
            await afetch_public("https://example.com/")
