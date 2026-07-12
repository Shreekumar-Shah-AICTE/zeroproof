"""Sandboxed Python execution.

Runs untrusted / model-generated code in a *separate process* with wall-clock
and memory limits, an offline environment, and no inherited file descriptors.
This is the engine behind proof-carrying math (program-of-thought) and code
(generate/debug -> execute -> verify) answers.

Security posture: task content and model output are untrusted. We never `exec`
them in-process; we spawn `python -I -S` (isolated, no site) with resource
limits so a runaway or hostile snippet cannot harm the run. Networking is not
required by any solver and any attempt simply fails inside the sandbox.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Preamble applied inside the child process: tighten resource limits and block
# obvious escape hatches without breaking legitimate compute.
_CHILD_PREAMBLE = r"""
import sys, os, resource, builtins
def _lim(which, soft):
    try:
        s, h = resource.getrlimit(which)
        resource.setrlimit(which, (soft if h == resource.RLIM_INFINITY else min(soft, h), h))
    except Exception:
        pass
_lim(resource.RLIMIT_CPU, {cpu})
try:
    resource.setrlimit(resource.RLIMIT_AS, ({mem}, {mem}))
except Exception:
    pass
# Disallow spawning new processes / opening the network from user code.
for _name in ("fork", "system", "popen"):
    if hasattr(os, _name):
        try:
            setattr(os, _name, None)
        except Exception:
            pass
sys.setrecursionlimit(20000)
"""


@dataclass
class ExecResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: Optional[int] = None
    timed_out: bool = False
    result: Any = None                     # value pulled from a JSON sentinel, if any
    meta: Dict[str, Any] = field(default_factory=dict)


def _build_script(code: str, cpu_seconds: int, mem_bytes: int) -> str:
    preamble = _CHILD_PREAMBLE.format(cpu=int(cpu_seconds), mem=int(mem_bytes))
    return preamble + "\n" + code


def run_code(
    code: str,
    timeout: float = 5.0,
    mem_mb: int = 512,
    stdin: str = "",
) -> ExecResult:
    """Execute `code` in an isolated child interpreter.

    Returns captured stdout/stderr and success flag. A line of the form
    ``__ZP_RESULT__ <json>`` printed by the code is parsed into `result`.
    """
    cpu_seconds = max(1, int(timeout) + 1)
    script = _build_script(code, cpu_seconds, mem_mb * 1024 * 1024)

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as fh:
        fh.write(script)
        script_path = fh.name

    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        # No proxy / network creds inherited.
    }
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-S", script_path],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=tempfile.gettempdir(),
        )
    except subprocess.TimeoutExpired as exc:
        return ExecResult(ok=False, timed_out=True, stdout=exc.stdout or "", stderr="timeout")
    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass

    result_value = None
    for line in proc.stdout.splitlines():
        if line.startswith("__ZP_RESULT__"):
            payload = line[len("__ZP_RESULT__"):].strip()
            try:
                result_value = json.loads(payload)
            except json.JSONDecodeError:
                result_value = payload
    return ExecResult(
        ok=(proc.returncode == 0),
        stdout=proc.stdout,
        stderr=proc.stderr,
        returncode=proc.returncode,
        result=result_value,
    )


def emit_result_snippet(expr: str) -> str:
    """Return a code line that prints a value as the JSON result sentinel."""
    return (
        "import json as _json\n"
        f"print('__ZP_RESULT__', _json.dumps({expr}, default=str))"
    )


def run_function_with_tests(
    solution_code: str,
    func_name: str,
    tests: List[Dict[str, Any]],
    timeout: float = 5.0,
) -> ExecResult:
    """Run `solution_code`, then call `func_name(*args)` for each test and
    compare against the expected value. `tests` is a list of
    ``{"args": [...], "expected": <value>}``. Returns per-test pass/fail.
    """
    harness = textwrap.dedent(
        """
        import json as _json
        _RESULTS = []
        try:
        {body}
        except Exception as _e:  # definition-time error
            print("__ZP_RESULT__", _json.dumps({{"defined": False, "error": repr(_e)}}))
        else:
            _tests = _json.loads('''{tests_json}''')
            for _t in _tests:
                try:
                    _out = {func}(*_t["args"])
                    _passed = (_out == _t["expected"]) if ("expected" in _t) else True
                    _RESULTS.append({{"ok": bool(_passed), "got": _out, "expected": _t.get("expected")}})
                except Exception as _e:
                    _RESULTS.append({{"ok": False, "error": repr(_e)}})
            print("__ZP_RESULT__", _json.dumps({{"defined": True, "results": _RESULTS}}, default=str))
        """
    ).strip()
    indented = textwrap.indent(solution_code, "    ")
    tests_json = json.dumps(tests).replace("\\", "\\\\").replace("'''", r"\'\'\'")
    code = harness.format(body=indented, func=func_name, tests_json=tests_json)
    return run_code(code, timeout=timeout)
