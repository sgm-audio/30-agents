"""Tests for core/validation.py (SSRF guard + path confinement),
core/discord_webhook.py URL allowlist, tools/file_ops.py workspace
confinement, and the security_gate PII regex (ReDoS regression).

URL tests use IP literals so no network/DNS access is required.
"""
import os
from pathlib import Path

import pytest

from core.discord_webhook import is_allowed_webhook_url
from core.security_gate import scrub_pii
from core.validation import resolve_allowed_path, validate_public_http_url
from tools import file_ops


class TestValidatePublicHttpUrl:
    @pytest.mark.parametrize("url", [
        "https://8.8.8.8/",
        "http://1.1.1.1/path?q=1",
        "https://8.8.8.8:8443/x",
    ])
    def test_allows_public_ip_literals(self, url):
        assert validate_public_http_url(url) == url

    @pytest.mark.parametrize("url", [
        # non-http schemes
        "file:///etc/passwd",
        "ftp://8.8.8.8/x",
        "gopher://example.com/x",
        # loopback
        "http://localhost/",
        "http://localhost.localdomain/",
        "http://127.0.0.1:8000/",
        "http://127.13.37.1/",
        "http://[::1]/",
        "http://0.0.0.0/",
        # link-local / cloud metadata endpoint
        "http://169.254.169.254/latest/meta-data",
        "http://[fe80::1]/",
        # RFC1918 / CGNAT / reserved
        "http://10.0.0.5/internal",
        "http://192.168.1.1/router",
        "http://172.16.0.1/x",
        "http://100.64.0.1/",
        "http://192.0.0.1/",
        # not URLs
        "not-a-url",
        "",
        "//example.com/evil",
    ])
    def test_rejects_non_public_or_non_http(self, url):
        with pytest.raises(ValueError):
            validate_public_http_url(url)

    def test_rejects_unresolvable_host(self):
        with pytest.raises(ValueError):
            validate_public_http_url("http://nonexistent.invalid.xx/")


class TestResolveAllowedPath:
    def test_allows_file_under_cwd(self):
        p = resolve_allowed_path("pytest.ini")
        assert p.name == "pytest.ini"

    def test_allows_absolute_path_under_cwd(self):
        target = str((Path(__file__).parent / "conftest.py").resolve())
        assert resolve_allowed_path(target).name == "conftest.py"

    def test_allows_traversal_that_stays_inside_root(self):
        # tests/.. resolves back to the project root, which is allowed.
        assert resolve_allowed_path("tests/../pytest.ini").name == "pytest.ini"

    def test_rejects_system_paths(self):
        if os.name == "nt":
            outside = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "win.ini")
        else:
            outside = "/etc/passwd"
        with pytest.raises(ValueError):
            resolve_allowed_path(outside)

    def test_env_override_adds_root(self, monkeypatch):
        fake_root = r"D:\nonexistent_root_xyz_30agents" if os.name == "nt" else "/nonexistent_root_xyz_30agents"
        with pytest.raises(ValueError):
            resolve_allowed_path(os.path.join(fake_root, "a.txt"))
        monkeypatch.setenv("AGENT_ALLOWED_PATHS", fake_root)
        p = resolve_allowed_path(os.path.join(fake_root, "a.txt"))
        assert p.name == "a.txt"


class TestFileOpsWorkspaceConfinement:
    @pytest.fixture
    def ws(self, tmp_path, monkeypatch):
        monkeypatch.setattr(file_ops, "WORKSPACE", tmp_path)
        return tmp_path

    def test_write_read_roundtrip(self, ws):
        assert file_ops.write_file("notes/hello.txt", "hi").startswith("Written")
        assert file_ops.read_file("notes/hello.txt") == "hi"

    def test_absolute_path_inside_workspace_allowed(self, ws):
        target = os.path.join(str(ws), "direct.txt")
        file_ops.write_file(target, "x")
        assert file_ops.read_file(target) == "x"

    def test_relative_traversal_blocked(self, ws):
        assert file_ops.write_file("../evil.txt", "x").startswith("Error: Access denied")
        assert file_ops.read_file("../evil.txt").startswith("Error: Access denied")
        assert file_ops.list_directory("../..").startswith("Error: Access denied")

    def test_absolute_path_outside_workspace_blocked(self, ws):
        if os.name == "nt":
            outside = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "win.ini")
        else:
            outside = "/etc/passwd"
        assert file_ops.read_file(outside).startswith("Error: Access denied")


class TestWebhookUrlAllowlist:
    @pytest.mark.parametrize("url", [
        "https://discord.com/api/webhooks/123/abc",
        "https://discordapp.com/api/webhooks/123/abc",
        "https://canary.discord.com/api/webhooks/123/abc",
    ])
    def test_allows_discord_hosts(self, url):
        assert is_allowed_webhook_url(url)

    @pytest.mark.parametrize("url", [
        "http://discord.com/api/webhooks/1/x",      # non-https
        "https://evil.com/api/webhooks/1/x",
        "https://discord.com.evil.com/",            # suffix spoof
        "https://127.0.0.1/api/webhooks/1/x",
        "not-a-url",
        "",
    ])
    def test_rejects_non_discord(self, url):
        assert not is_allowed_webhook_url(url)


class TestEmailRegexReDoS:
    def test_adversarial_input_terminates(self):
        # Would hang a polynomial/exponential backtracking engine.
        scrub_pii("a." * 50_000)

    def test_still_redacts_common_emails(self):
        assert scrub_pii("mail me at a@b.com") == "mail me at [REDACTED_EMAIL]"
        assert scrub_pii("x: user.name+tag@mail.example.co.uk!") == "x: [REDACTED_EMAIL]!"

    def test_does_not_over_redact(self):
        text = "paths like a.b/c.d and versions 1.2.3 are fine"
        assert scrub_pii(text) == text
