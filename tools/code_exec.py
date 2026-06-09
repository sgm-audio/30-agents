"""
Tool: Safe code execution sandbox via subprocess.
Uses a separate process so it can be forcibly killed on timeout.
"""
import asyncio
import sys
import textwrap
from typing import Optional


# Template: wraps user code with restricted builtins
_SANDBOX_TEMPLATE = """
import sys
import builtins as _builtins_mod

# Dangerous builtins that allow file access, code injection, or introspection
_BLOCKED = frozenset({{
    '__import__', 'exec', 'eval', 'compile', 'open',
    '__subclasses__', '__bases__', '__mro__', '__class__',
    '__globals__', '__code__', '__dict__', '__builtins__',
    '__loader__', '__spec__', '__name__', '__package__',
    'getattr', 'setattr', 'delattr', 'hasattr',
    'globals', 'locals', 'vars', 'dir',
    'breakpoint', 'exit', 'quit',
    'input', 'help', 'license', 'credits',
    'memoryview', 'bytearray', 'bytes',
}})

_SAFE_BUILTINS = {{
    'print': print, 'len': len, 'range': range, 'enumerate': enumerate,
    'zip': zip, 'map': map, 'filter': filter, 'list': list, 'dict': dict,
    'set': set, 'tuple': tuple, 'int': int, 'float': float, 'str': str,
    'bool': bool, 'abs': abs, 'max': max, 'min': min, 'sum': sum,
    'round': round, 'sorted': sorted, 'reversed': reversed,
    'isinstance': isinstance, 'repr': repr,
    'ValueError': ValueError, 'TypeError': TypeError,
    'KeyError': KeyError, 'IndexError': IndexError,
    'StopIteration': StopIteration, 'RuntimeError': RuntimeError,
    'Exception': Exception, 'ZeroDivisionError': ZeroDivisionError,
    'AttributeError': AttributeError, 'NotImplementedError': NotImplementedError,
}}

# Replace the entire __builtins__ dict — blocks access to dangerous builtins
# and replaces __import__ with a restricted version
def _restricted_import(name, *a, **kw):
    _allowed = {{'math','datetime','collections','itertools','functools'}}
    if name not in _allowed:
        raise ImportError(f"Import of '{{name}}' is not allowed in sandbox")
    return _builtins_mod.__dict__['__import__'](name, *a, **kw)

_safe_dict = dict(_SAFE_BUILTINS)
_safe_dict['__import__'] = _restricted_import
import types as _types
_builtins_mod.__dict__.clear()
_builtins_mod.__dict__.update(_safe_dict)

try:
{code}
except Exception as e:
    import traceback
    print(traceback.format_exc(), file=sys.stderr)
"""


async def safe_exec(code: str, timeout: float = 30.0) -> str:
    """
    Execute Python code in a subprocess sandbox with hard timeout.
    The subprocess is forcibly killed if it exceeds the timeout.
    """
    indented = textwrap.indent(code, "    ")
    wrapped = _SANDBOX_TEMPLATE.format(code=indented)

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", wrapped,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return f"Execution timed out after {timeout}s"

        out = stdout.decode(errors="replace").strip()
        err = stderr.decode(errors="replace").strip()

        result = ""
        if out:
            result += f"Output:\n{out}"
        if err:
            result += (f"\n" if result else "") + f"Errors:\n{err}"
        return result.strip() or "(no output)"

    except Exception as e:
        return f"Execution error: {e}"
