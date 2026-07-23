"""Tests for core/security_gate.py — tool whitelist, PII scrub, blocked args."""
from core.security_gate import ALLOWED_TOOLS, check_tool_call, scrub_pii


class TestScrubPII:
    def test_redacts_email(self):
        assert scrub_pii("reach me at scott@example.com") == "reach me at [REDACTED_EMAIL]"

    def test_redacts_phone(self):
        result = scrub_pii("call 604-555-1234 now")
        assert "[REDACTED_PHONE]" in result
        assert "604-555-1234" not in result

    def test_redacts_ssn(self):
        assert scrub_pii("SSN: 123-45-6789") == "SSN: [REDACTED_SSN]"

    def test_leaves_clean_text_alone(self):
        text = "The quick brown fox jumps over the lazy dog."
        assert scrub_pii(text) == text

    def test_handles_empty_string(self):
        assert scrub_pii("") == ""


class TestCheckToolCall:
    def test_rejects_unlisted_tool(self):
        ok, reason = check_tool_call("shell_exec", {"cmd": "ls"})
        assert not ok
        assert "not whitelisted" in reason

    def test_accepts_whitelisted_tool(self):
        ok, reason = check_tool_call("read_file", {"filepath": "data/workspace/x.txt"})
        assert ok
        assert reason == "ok"

    def test_blocks_rm_rf(self):
        ok, _ = check_tool_call("python_repl", {"code": "import os; os.system('rm -rf /')"})
        assert not ok

    def test_blocks_format_c(self):
        ok, _ = check_tool_call("python_repl", "os.system('format c: /y')")
        assert not ok

    def test_blocks_shell_injection_chaining(self):
        ok, _ = check_tool_call("web_search", "safe query; rm -rf /tmp")
        assert not ok

    def test_allows_safe_args(self):
        ok, _ = check_tool_call("python_repl", "print('hello world')")
        assert ok

    def test_all_whitelisted_tools_are_strings(self):
        assert all(isinstance(t, str) for t in ALLOWED_TOOLS)
