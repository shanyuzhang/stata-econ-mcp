"""Stata worker process.

Runs in its own OS process so that a hung or crashed Stata never takes down
the MCP server. Talks to the parent over a multiprocessing Pipe; everything
Stata prints is captured and returned, never written to the MCP stdio channel.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import sys
import traceback

_RC_RE = re.compile(r"r\((\d+)\);\s*$")

# Settings applied after Stata starts. The user's profile.do may abort in
# headless mode (GUI-only `window menu` commands), so re-apply what matters.
POST_INIT = """\
set more off
set linesize 120
set type double
capture set maxvar 30000
"""


def _capture_run(stata, code: str, echo: bool = True) -> dict:
    buf = io.StringIO()
    err_text = ""
    ok = True
    with contextlib.redirect_stdout(buf):
        try:
            stata.run(code, quietly=False, echo=echo)
        except SystemError as e:  # Stata error: message holds trailing output + r(xxx);
            ok = False
            err_text = str(e)
        except Exception as e:  # noqa: BLE001
            ok = False
            err_text = f"{type(e).__name__}: {e}"
    output = buf.getvalue()
    if err_text:
        output = output + ("\n" if output and not output.endswith("\n") else "") + err_text
    rc = 0
    if not ok:
        m = _RC_RE.search(err_text.strip())
        rc = int(m.group(1)) if m else -1
    return {"ok": ok, "rc": rc, "output": output}


def _results(stata, name: str | None) -> dict:
    from sfi import Matrix

    pre = []
    if name:
        r = _capture_run(stata, f"quietly estimates restore {name}", echo=False)
        if not r["ok"]:
            return {"ok": False, "error": r["output"]}
    r = _capture_run(stata, "quietly ereturn display", echo=False)
    if not r["ok"]:
        return {"ok": False, "error": "No active estimation results (run a model first).\n" + r["output"]}
    tbl = Matrix.get("r(table)")
    rows = Matrix.getRowNames("r(table)")
    cols = Matrix.getColNames("r(table)")
    try:
        eqs = Matrix.getColStripe("r(table)")[0]
    except Exception:  # noqa: BLE001
        eqs = None
    coefs = []
    for j, c in enumerate(cols):
        rec = {"term": c}
        if eqs and eqs[j] and eqs[j] != "_":
            rec["equation"] = eqs[j]
        for i, rn in enumerate(rows):
            if rn in ("b", "se", "t", "z", "pvalue", "ll", "ul"):
                v = tbl[i][j]
                rec[rn] = None if v is None or v != v or abs(v) > 8.98e307 else v
        if re.search(r"(^|#)\d*[bo]\.", c):
            rec["omitted_or_base"] = True
        coefs.append(rec)
    e = stata.get_ereturn()
    scalars, macros = {}, {}
    for k, v in e.items():
        key = k[2:-1] if k.startswith("e(") else k
        if isinstance(v, str):
            if key not in ("properties",) and len(v) < 2000:
                macros[key] = v
        elif isinstance(v, (int, float)):
            scalars[key] = None if v != v or abs(v) > 8.98e307 else v
    return {"ok": True, "coefficients": coefs, "scalars": scalars, "macros": macros, "notes": pre}


def _findfile(stata, fname: str) -> str | None:
    from sfi import Macro

    r = _capture_run(stata, f'quietly findfile "{fname}"', echo=False)
    if not r["ok"]:
        return None
    return Macro.getGlobal("r(fn)") or None


def main(conn, stata_dir: str, edition: str, workdir: str) -> None:
    # Make sure nothing native or Python-level ever reaches fd 1 of this process.
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    sys.path.insert(0, os.path.join(stata_dir, "utilities"))
    init_log = io.StringIO()
    try:
        with contextlib.redirect_stdout(init_log):
            from pystata import config

            # Stata's Python bridge (-pyexec) breaks on interpreter paths containing spaces
            # (e.g. a venv inside "Stata MCP/"). Hand it a space-free path to the same interpreter.
            exe = sys.executable
            if " " in exe:
                real = os.path.realpath(exe)
                if " " in real:
                    link_dir = os.path.expanduser("~/.cache/stata-econ-mcp")
                    os.makedirs(link_dir, exist_ok=True)
                    link = os.path.join(link_dir, "python")
                    if os.path.islink(link):
                        os.unlink(link)
                    os.symlink(real, link)
                    real = link
                config._get_executable_path = lambda: real
            config.init(edition, splash=False)
            if not getattr(config, "sfiinitialized", True):
                raise RuntimeError("Stata started but its Python bridge (sfi) failed to initialize.")
            from pystata import stata  # noqa: F401
    except Exception:  # noqa: BLE001
        conn.send({"ok": False, "output": init_log.getvalue() + traceback.format_exc()})
        return
    from pystata import stata

    post = _capture_run(stata, POST_INIT + f'cd "{workdir}"\n', echo=False)
    conn.send({"ok": True, "output": init_log.getvalue(), "post": post})

    while True:
        try:
            req = conn.recv()
        except EOFError:
            return
        op = req.get("op")
        try:
            if op == "run":
                res = _capture_run(stata, req["code"], echo=req.get("echo", True))
            elif op == "results":
                res = _results(stata, req.get("name"))
            elif op == "findfile":
                res = {"ok": True, "path": _findfile(stata, req["fname"])}
            elif op == "ping":
                res = {"ok": True}
            elif op == "quit":
                conn.send({"ok": True})
                return
            else:
                res = {"ok": False, "output": f"unknown op {op}"}
        except Exception:  # noqa: BLE001
            res = {"ok": False, "rc": -1, "output": traceback.format_exc()}
        conn.send(res)
