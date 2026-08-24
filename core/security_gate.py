"""
Security gate for tool_dispatcher: tool-name whitelist, blocked-arg pattern
detection, and PII scrubbing on tool outputs.

ponytail: scrub_pii is regex-only (no Presidio/NER) — covers common email,
NA-style phone, and SSN-shaped patterns but will miss non-US formats and
free-text PII. Upgrade path: swap the regex table below for a Presidio (or
similar NER) pipeline if false negatives become a real problem.
"""
from __future__ import annotations

import json
import re

# Tools tool_dispatcher is allowed to invoke. Mirrors the tool set actually
# wired in agents/tier1/__init__.py ToolDispatcherAgent.execute() (read_file,
# web_search, python_repl) plus the rest of the tools/ surface (list_dir) and
# near-term placeholders (calculator, file_search) called out for this gate.
ALLOWED_TOOLS = frozenset({
    "calculator",
    "file_search",
    "web_search",
    "python_repl",
    "read_file",
    "list_dir",
})

# The domain-label repetition is wrapped in an atomic group so the engine
# cannot re-partition dots between `(label.)+` and the TLD on backtracking —
# keeps matching linear-time on hostile input (CodeQL py/redos). Requires
# Python >= 3.11 (atomic groups).
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@(?>(?:[a-zA-Z0-9-]+\.)+)[a-zA-Z]{2,}")
_SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_PHONE_RE = re.compile(r"(?<!\d)(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)")

# Dangerous shell/command patterns that should never appear in tool args.
_BLOCKED_ARG_PATTERNS = [
    re.compile(r"rm\s+-rf", re.IGNORECASE),
    re.compile(r"format\s+[a-z]:", re.IGNORECASE),
    re.compile(r"del\s+/[sf]", re.IGNORECASE),
    re.compile(r"[;&|`]\s*(rm|del|format|shutdown)\b", re.IGNORECASE),  # shell chaining/injection
    re.compile(r"\$\([^)]*\)"),  # $(...) command substitution
    re.compile(r"`[^`]*`"),      # backtick command substitution
    re.compile(r">\s*/dev/(sd|null)", re.IGNORECASE),
]


def scrub_pii(text: str) -> str:
    """Redact emails, SSN-shaped digits, and phone numbers from text."""
    if not text:
        return text
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _SSN_RE.sub("[REDACTED_SSN]", text)
    text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    return text


def check_tool_call(tool: str, args: dict | str) -> tuple[bool, str]:
    """Validate a tool call against the whitelist and blocked-pattern list.

    Returns (ok, reason). `reason` is "ok" on success, or a short human-
    readable explanation of why the call was rejected.
    """
    if tool not in ALLOWED_TOOLS:
        return False, f"Tool '{tool}' is not whitelisted"

    arg_text = args if isinstance(args, str) else json.dumps(args, default=str)
    for pattern in _BLOCKED_ARG_PATTERNS:
        if pattern.search(arg_text):
            return False, f"Blocked pattern detected in tool args: {pattern.pattern}"

    return True, "ok"


if __name__ == "__main__":
    assert scrub_pii("contact me at a@b.com") == "contact me at [REDACTED_EMAIL]"
    assert scrub_pii("call 604-555-1234") == "call [REDACTED_PHONE]"
    assert scrub_pii("ssn is 123-45-6789") == "ssn is [REDACTED_SSN]"
    assert scrub_pii("nothing sensitive here") == "nothing sensitive here"
    assert scrub_pii("") == ""

    ok, _ = check_tool_call("read_file", {"filepath": "data/workspace/x.txt"})
    assert ok

    ok, reason = check_tool_call("shell_exec", {"cmd": "ls"})
    assert not ok and "not whitelisted" in reason

    ok, _ = check_tool_call("python_repl", {"code": "import os; os.system('rm -rf /')"})
    assert not ok

    ok, _ = check_tool_call("python_repl", "os.system('format c: /y')")
    assert not ok

    ok, _ = check_tool_call("python_repl", "print(1)")
    assert ok

    print("security_gate self-check: OK")
