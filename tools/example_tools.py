"""Example custom tools registered with the dynamic ToolRegistry.

Import this module to activate both tools:
  - python_repl: execute arbitrary Python code in a subprocess
  - grep_tool: search files for a regex pattern

These are registered at import time via the @registry.tool decorator.
"""

import asyncio
from pathlib import Path

from tools.registry import registry
from config import TASK_TIMEOUT_SECONDS

# ---------------------------------------------------------------------------
# python_repl
# ---------------------------------------------------------------------------

_PYTHON_REPL_SCHEMA = {
    "type": "object",
    "properties": {
        "code": {
            "type": "string",
            "description": "Python source code to execute.",
        },
        "timeout": {
            "type": "integer",
            "description": "Max execution time in seconds.",
            "default": TASK_TIMEOUT_SECONDS,
        },
    },
    "required": ["code"],
}


@registry.tool(
    "python_repl",
    "Run Python code in an isolated subprocess and return stdout/stderr.",
    _PYTHON_REPL_SCHEMA,
)
async def python_repl(inputs: dict, scratchpad: dict) -> dict:
    """Execute Python code in a subprocess.

    Returns dict with keys: output (str), success (bool), error (str|None).
    """
    code: str = inputs.get("code", "")
    timeout: int = int(inputs.get("timeout", TASK_TIMEOUT_SECONDS))

    if not code.strip():
        return {"output": "", "success": False, "error": "No code provided."}

    try:
        proc = await asyncio.create_subprocess_exec(
            "python3", "-c", code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        success = proc.returncode == 0
        return {
            "output": stdout.decode(),
            "success": success,
            "error": stderr.decode() if not success else None,
        }
    except asyncio.TimeoutError:
        return {
            "output": "",
            "success": False,
            "error": f"Python execution timed out after {timeout}s.",
        }
    except Exception as exc:
        return {"output": "", "success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# grep_tool
# ---------------------------------------------------------------------------

_GREP_SCHEMA = {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": "Regular-expression pattern to search for.",
        },
        "path": {
            "type": "string",
            "description": "File or directory to search in.",
            "default": ".",
        },
        "recursive": {
            "type": "boolean",
            "description": "Search recursively through directories.",
            "default": True,
        },
        "case_insensitive": {
            "type": "boolean",
            "description": "Perform case-insensitive matching.",
            "default": False,
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of matching lines to return.",
            "default": 200,
        },
    },
    "required": ["pattern"],
}


@registry.tool(
    "grep_tool",
    "Search files for a regex pattern using grep; returns matching lines with file:line context.",
    _GREP_SCHEMA,
)
async def grep_tool(inputs: dict, scratchpad: dict) -> dict:
    """Run grep to find pattern matches in files.

    Returns dict with keys: output (str), success (bool), error (str|None).
    """
    pattern: str = inputs.get("pattern", "")
    path: str = inputs.get("path", ".")
    recursive: bool = bool(inputs.get("recursive", True))
    case_insensitive: bool = bool(inputs.get("case_insensitive", False))
    max_results: int = int(inputs.get("max_results", 200))

    if not pattern:
        return {"output": "", "success": False, "error": "No pattern provided."}

    # Validate path exists
    if not Path(path).exists():
        return {"output": "", "success": False, "error": f"Path does not exist: {path}"}

    cmd = ["grep", "-n", "--include=*"]  # -n = line numbers
    if recursive:
        cmd.append("-r")
    if case_insensitive:
        cmd.append("-i")
    cmd += [pattern, path]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=TASK_TIMEOUT_SECONDS
        )
        lines = stdout.decode().splitlines()
        truncated = len(lines) > max_results
        output_lines = lines[:max_results]
        output = "\n".join(output_lines)
        if truncated:
            output += f"\n... (truncated to {max_results} results)"

        # grep exit code 1 means no matches (not an error), 2+ is a real error
        if proc.returncode == 2:
            return {"output": "", "success": False, "error": stderr.decode()}

        return {
            "output": output,
            "success": True,
            "error": None,
            "match_count": len(lines),
        }
    except asyncio.TimeoutError:
        return {
            "output": "",
            "success": False,
            "error": f"grep timed out after {TASK_TIMEOUT_SECONDS}s.",
        }
    except Exception as exc:
        return {"output": "", "success": False, "error": str(exc)}
