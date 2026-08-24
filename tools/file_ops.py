"""
Tool: File operations (read, write, list)
Restricted to workspace directory for safety.
"""
from pathlib import Path

from core.safety import WORKSPACE_ROOT, resolve_workspace_path

# All file operations are restricted to this workspace
# Set WORKSPACE_OVERRIDE env var to bypass (for testing)
WORKSPACE = WORKSPACE_ROOT
WORKSPACE.mkdir(parents=True, exist_ok=True)


def _validate_path(filepath: str) -> tuple[Path | None, str | None]:
    """Validate that filepath is within the workspace. Returns (path, error)."""
    path = resolve_workspace_path(filepath)
    workspace = WORKSPACE.resolve()
    if path is None:
        return None, f"Access denied: {filepath} is outside workspace {workspace}"
    return path, None


def read_file(filepath: str, max_chars: int = 8000) -> str:
    """Read a file and return its content. Restricted to workspace."""
    path, err = _validate_path(filepath)
    if err:
        return f"Error: {err}"
    if not path.exists():
        return f"Error: File not found: {filepath}"
    if not path.is_file():
        return f"Error: Not a file: {filepath}"
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n... [truncated at {max_chars} chars]"
        return content
    except Exception as e:
        return f"Error reading {filepath}: {e}"


def write_file(filepath: str, content: str) -> str:
    """Write content to a file (creates parent dirs if needed). Restricted to workspace."""
    path, err = _validate_path(filepath)
    if err:
        return f"Error: {err}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Written {len(content)} chars to {filepath}"
    except Exception as e:
        return f"Error writing {filepath}: {e}"


def list_directory(dirpath: str, pattern: str = "*") -> str:
    """List files in a directory matching a pattern. Restricted to workspace."""
    path, err = _validate_path(dirpath)
    if err:
        return f"Error: {err}"
    if not path.exists():
        return f"Error: Directory not found: {dirpath}"
    try:
        files = sorted(path.glob(pattern))
        lines = []
        for f in files[:100]:
            size = f.stat().st_size if f.is_file() else 0
            kind = "DIR" if f.is_dir() else "FILE"
            lines.append(f"[{kind}] {f.name} ({size:,} bytes)")
        return "\n".join(lines) or "Empty directory"
    except Exception as e:
        return f"Error listing {dirpath}: {e}"
