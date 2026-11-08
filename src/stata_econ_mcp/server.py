"""Stata Econ MCP server: drive the user's own local Stata from Claude.

Stata runs in a separate worker process (see worker.py) through the official
pystata interface that ships with Stata 17+. The session is persistent: data,
estimates and locals survive between tool calls until stata_restart.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import multiprocessing as mp
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from mcp.server.fastmcp import Context, FastMCP, Image

from . import worker

GUIDE_DIR = Path(__file__).parent / "guides"
OUTPUT_SUBDIR = os.environ.get("STATA_MCP_OUTPUT_SUBDIR", "stata_output")
DEFAULT_WORKDIR = Path(os.environ.get("STATA_MCP_DEFAULT_DIR", Path.home() / "Documents" / "Stata研究"))
DEFAULT_WAIT = int(os.environ.get("STATA_MCP_WAIT_SECONDS", "240"))
MAX_CHARS = int(os.environ.get("STATA_MCP_MAX_CHARS", "24000"))

RC_HINTS = {
    1: "Run was interrupted (break).",
    100: "Required varlist/argument missing.",
    109: "Type mismatch (string vs numeric). Check with `describe`; use destring/encode.",
    110: "Variable/name already defined. Use `replace`, or `capture drop` first.",
    111: "Variable or name not found. Check spelling with `describe`; abbreviations may be ambiguous.",
    198: "Invalid syntax. Check commas/options, `///` continuation, and quoting.",
    199: "Unrecognized command. If it is a community package, install it (e.g. `ssc install reghdfe`) after asking the user.",
    301: "Last estimates not found. Run the model or `estimates restore` first.",
    310: "Not possible because the data are not xtset/tsset correctly.",
    430: "Convergence not achieved. Rescale variables, change start values, or simplify the model.",
    451: "Panel/time variable issue (e.g. repeated time values within panel in xtset).",
    459: "Something in the data is inconsistent with the requested operation.",
    601: "File not found. Check the path relative to the working directory (`pwd`).",
    602: "File already exists. Add `, replace`.",
    603: "File could not be opened (permission or locked?).",
    2000: "No observations. Check `if` conditions and missing values.",
    2001: "Insufficient observations.",
    908: "maxvar too small. `clear all` then `set maxvar 30000`.",
}


def _find_stata() -> tuple[str, str]:
    """Return (stata_dir, edition)."""
    env_dir = os.environ.get("STATA_DIR")
    candidates = [Path(env_dir)] if env_dir else []
    candidates += [Path("/Applications/Stata"), Path("/Applications/StataNow")]
    candidates += sorted(Path("/Applications").glob("Stata*"))
    for d in candidates:
        if not (d / "utilities" / "pystata").is_dir():
            continue
        ed = os.environ.get("STATA_EDITION")
        if not ed:
            for name, e in (("StataMP.app", "mp"), ("StataSE.app", "se"), ("StataBE.app", "be"), ("StataIC.app", "be")):
                if (d / name).exists():
                    ed = e
                    break
        return str(d), ed or "mp"
    raise RuntimeError("Could not find a Stata 17+ installation with pystata. Set STATA_DIR (e.g. /Applications/Stata).")


def _bad_cwd(p: str) -> bool:
    home = str(Path.home())
    if p in ("/", home):
        return True
    return any(p == s or p.startswith(s + "/") for s in ("/Applications", "/System", "/Library", "/usr", "/opt", "/private", "/bin", "/sbin"))


def _sq(s: str) -> str:
    """Stata compound double quotes."""
    return '`"' + s + "\"'"


class Session:
    def __init__(self) -> None:
        self.proc: mp.process.BaseProcess | None = None
        self.conn = None
        self.workdir: Path | None = None
        self.stata_dir, self.edition = None, None
        self.busy: str | None = None  # description of the job still running after a timeout
        self.lock = asyncio.Lock()
        self.startup_note = ""

    # ---------- paths ----------
    @property
    def outdir(self) -> Path:
        assert self.workdir is not None
        return self.workdir / OUTPUT_SUBDIR

    def sub(self, name: str) -> Path:
        p = self.outdir / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    async def resolve_workdir(self, ctx: Context | None) -> Path:
        if self.workdir:
            return self.workdir
        env = os.environ.get("STATA_MCP_WORKDIR")
        if env and Path(env).is_dir():
            self.workdir = Path(env)
            return self.workdir
        if ctx is not None:
            try:
                res = await asyncio.wait_for(ctx.session.list_roots(), timeout=3)
                for r in res.roots:
                    u = urlparse(str(r.uri))
                    if u.scheme == "file" and Path(unquote(u.path)).is_dir():
                        self.workdir = Path(unquote(u.path))
                        return self.workdir
            except Exception:  # noqa: BLE001 - client may not support roots
                pass
        cwd = os.getcwd()
        if not _bad_cwd(cwd) and os.access(cwd, os.W_OK):
            self.workdir = Path(cwd)
        else:
            DEFAULT_WORKDIR.mkdir(parents=True, exist_ok=True)
            self.workdir = DEFAULT_WORKDIR
        return self.workdir

    # ---------- process ----------
    def alive(self) -> bool:
        return self.proc is not None and self.proc.is_alive()

    async def start(self, ctx: Context | None) -> str:
        if self.alive():
            return ""
        await self.resolve_workdir(ctx)
        self.stata_dir, self.edition = _find_stata()
        mctx = mp.get_context("spawn")
        parent, child = mctx.Pipe()
        proc = mctx.Process(
            target=worker.main,
            args=(child, self.stata_dir, self.edition, str(self.workdir)),
            daemon=True,
        )
        proc.start()
        child.close()
        ready = await asyncio.to_thread(parent.poll, 180)
        if not ready:
            proc.kill()
            raise RuntimeError("Stata did not start within 180s.")
        msg = parent.recv()
        if not msg.get("ok"):
            proc.kill()
            raise RuntimeError("Stata failed to start:\n" + msg.get("output", ""))
        self.proc, self.conn, self.busy = proc, parent, None
        note = f"Started Stata ({self.edition.upper()}) from {self.stata_dir}; working directory: {self.workdir}"
        if "r(" in msg.get("output", ""):
            note += "\n(Note: profile.do stopped early in headless mode — usually GUI-only `window menu` lines; core settings were re-applied.)"
        self.startup_note = note
        return note

    def kill(self) -> None:
        if self.proc is not None:
            try:
                self.proc.kill()
                self.proc.join(5)
            except Exception:  # noqa: BLE001
                pass
        self.proc, self.conn, self.busy = None, None, None

    async def _recv(self, timeout: float):
        try:
            ready = await asyncio.to_thread(self.conn.poll, timeout)
            if not ready:
                return None
            return self.conn.recv()
        except (EOFError, OSError, BrokenPipeError):
            self.kill()
            return {"ok": False, "rc": -1, "output": "Stata worker process died (crash or killed). It will restart on the next call; in-memory data were lost."}

    async def request(self, ctx: Context | None, req: dict, timeout: float = DEFAULT_WAIT, desc: str = "") -> dict:
        async with self.lock:
            note = await self.start(ctx)
            if self.busy:
                prev = await self._recv(0.5)
                if prev is None:
                    return {"ok": False, "rc": -2, "busy": True,
                            "output": f"Stata is still running a previous job: {self.busy}\nCall stata_wait to keep waiting, or stata_restart to kill it."}
                self.busy = None
            self.conn.send(req)
            res = await self._recv(timeout)
            if res is None:
                self.busy = desc or req.get("op", "job")
                return {"ok": False, "rc": -2, "busy": True,
                        "output": f"Still running after {int(timeout)}s (Stata keeps working in the background).\nCall stata_wait to collect the result, or stata_restart to abort."}
            if note:
                res["startup_note"] = note
            return res

    async def run(self, ctx: Context | None, code: str, timeout: float = DEFAULT_WAIT, echo: bool = True, record: bool = True) -> dict:
        res = await self.request(ctx, {"op": "run", "code": code, "echo": echo}, timeout, desc=code.strip().splitlines()[0][:120] if code.strip() else "")
        if record and self.workdir is not None and not res.get("busy"):
            self.record(code, res)
        return res

    def record(self, code: str, res: dict) -> None:
        """Append every command to a dated history do-file and its output to a dated log."""
        try:
            day = dt.date.today().isoformat()
            ts = dt.datetime.now().strftime("%H:%M:%S")
            status = "ok" if res.get("ok") else f"ERROR r({res.get('rc')})"
            with open(self.sub("logs") / f"history_{day}.do", "a", encoding="utf-8") as f:
                f.write(f"\n* ---- {ts}  [{status}] ----\n{code.rstrip()}\n")
            with open(self.sub("logs") / f"session_{day}.log", "a", encoding="utf-8") as f:
                f.write(f"\n==== {ts} [{status}] ====\n{res.get('output', '')}\n")
        except Exception:  # noqa: BLE001
            pass


S = Session()


def _fmt(res: dict, log_hint: str | None = None) -> str:
    out = res.get("output", "") or ""
    if len(out) > MAX_CHARS:
        head, tail = out[: MAX_CHARS // 4], out[-(MAX_CHARS * 3 // 4):]
        out = head + f"\n\n... [{len(out) - len(head) - len(tail)} characters truncated; full output in {log_hint or 'stata_output/logs/session_<date>.log'}] ...\n\n" + tail
    parts = []
    if res.get("startup_note"):
        parts.append(res["startup_note"])
    if res.get("busy"):
        parts.append("STATUS: RUNNING")
    elif res.get("ok"):
        parts.append("STATUS: OK (rc=0)")
    else:
        rc = res.get("rc")
        parts.append(f"STATUS: ERROR r({rc})")
        if rc in RC_HINTS:
            parts.append(f"Hint: {RC_HINTS[rc]}")
    parts.append(out.strip("\n"))
    return "\n".join(p for p in parts if p)


def _resolve(path: str, default_sub: str, ext: str) -> Path:
    p = Path(os.path.expanduser(path))
    if not p.suffix:
        p = p.with_suffix(ext)
    if not p.is_absolute():
        p = (S.sub(default_sub) / p) if len(p.parts) == 1 else (S.workdir / p)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


INSTRUCTIONS = f"""\
This server drives the user's OWN local Stata (official pystata engine, persistent session).
Data, estimates, globals persist across calls until stata_restart.

Working rules:
1. Before any econometric task, read stata_guide("workflow") and the topic guide
   (panel_fe, did, ddd, event_study, latex_tables, econ_standards). Follow them.
2. Inspect data first (stata_data: overview / describe / xtdescribe) before modelling.
3. Put real analysis in do-files via stata_do so it is reproducible; use stata_run for quick checks.
4. `estimates store` every model, then export publication tables with stata_table (LaTeX/booktabs).
5. Figures: build with Stata graph commands, then stata_graph to export PNG(+PDF) and show it.
6. Outputs go to <workdir>/{OUTPUT_SUBDIR}/ (do/, logs/, tables/, figures/). Every command is also
   appended to logs/history_<date>.do. Tell the user where files were saved.
7. Never run shell escapes (`!`, `shell`) or delete user files. Ask before `ssc install`.
Reply in the user's language.
"""

mcp = FastMCP("stata", instructions=INSTRUCTIONS)


@mcp.tool()
async def stata_run(code: str, ctx: Context, wait_seconds: int = DEFAULT_WAIT) -> str:
    """Run Stata code in the persistent session and return the output.

    `code` may be multi-line (supports `///`, comments, locals within the block).
    Use for quick checks/exploration. For real analysis prefer stata_do (saved do-file + log).
    If the job exceeds wait_seconds it keeps running; then call stata_wait.
    """
    return _fmt(await S.run(ctx, code, wait_seconds))


@mcp.tool()
async def stata_do(filename: str, ctx: Context, code: str | None = None, wait_seconds: int = DEFAULT_WAIT) -> str:
    """Save `code` as a do-file (if given) and execute it with a text log.

    filename: e.g. "01_clean" or "analysis/did_main.do". A bare name goes to stata_output/do/;
    a relative path with folders is relative to the working directory; absolute paths are allowed.
    If `code` is omitted, the existing do-file is run. Log is written to stata_output/logs/<name>.log.
    """
    await S.start(ctx)
    path = _resolve(filename, "do", ".do")
    if code is not None:
        path.write_text(code if code.endswith("\n") else code + "\n", encoding="utf-8")
    elif not path.exists():
        return f"Do-file not found: {path}"
    log = S.sub("logs") / (path.stem + ".log")
    wrapper = (
        "capture log close _mcpdo\n"
        f"log using {_sq(str(log))}, text replace name(_mcpdo)\n"
        f"do {_sq(str(path))}\n"
    )
    res = await S.run(ctx, wrapper, wait_seconds, echo=False, record=False)
    if not res.get("busy"):
        await S.run(ctx, "capture log close _mcpdo", 30, echo=False, record=False)
        S.record(f'do "{path}"', res)
    head = f"do-file: {path}\nlog: {log}\n"
    return head + _fmt(res, str(log))


@mcp.tool()
async def stata_wait(ctx: Context, wait_seconds: int = DEFAULT_WAIT) -> str:
    """Keep waiting for a long-running Stata job started earlier and return its output."""
    async with S.lock:
        if not S.busy or not S.alive():
            return "No job is running."
        res = await S._recv(wait_seconds)
        if res is None:
            return f"Still running: {S.busy}. Call stata_wait again or stata_restart to abort."
        S.busy = None
    return _fmt(res)


@mcp.tool()
async def stata_restart(ctx: Context) -> str:
    """Kill and restart the Stata session (clears data in memory). Use if Stata hangs."""
    S.kill()
    note = await S.start(ctx)
    return note or "Restarted."


@mcp.tool()
async def stata_set_workdir(path: str, ctx: Context) -> str:
    """Set the project folder. Outputs then go to <path>/stata_output and Stata `cd`s there.

    Use when the user names a project folder, or if the detected folder is wrong.
    """
    p = Path(os.path.expanduser(path)).resolve()
    if not p.is_dir():
        return f"Not a directory: {p}"
    S.workdir = p
    if S.alive() and not S.busy:
        res = await S.run(ctx, f"cd {_sq(str(p))}", 30, echo=False, record=False)
        if not res.get("ok"):
            return _fmt(res)
    return f"Working directory: {p}\nOutputs: {S.outdir}"


@mcp.tool()
async def stata_status(ctx: Context) -> str:
    """Show Stata install, working/output folders, and which key econometrics packages are installed."""
    await S.start(ctx)
    pkgs = ["reghdfe", "ftools", "ivreghdfe", "ppmlhdfe", "csdid", "drdid", "did_imputation",
            "eventstudyinteract", "did_multiplegt", "did_multiplegt_dyn", "jwdid", "bacondecomp",
            "estout", "coefplot", "boottest", "winsor2", "outreg2"]
    lines = [f"Stata: {S.stata_dir} ({S.edition})", f"Working directory: {S.workdir}", f"Outputs: {S.outdir}"]
    if S.busy:
        lines.append(f"BUSY: {S.busy}")
        return "\n".join(lines)
    have, missing = [], []
    for p in pkgs:
        r = await S.request(ctx, {"op": "findfile", "fname": f"{p}.ado"}, 30)
        (have if r.get("path") else missing).append(p)
    lines.append("Installed: " + ", ".join(have))
    lines.append("Not installed: " + ", ".join(missing) + "  (install with `ssc install <name>` only after asking the user)")
    return "\n".join(lines)


@mcp.tool()
async def stata_data(ctx: Context, action: str = "overview", varlist: str = "", condition: str = "", n: int = 20) -> str:
    """Inspect the dataset in memory.

    action: overview | describe | summarize | detail (summarize, detail) | codebook | list |
            tabulate | xtdescribe | missing | count
    varlist: optional Stata varlist; condition: optional Stata `if` expression (without the word if);
    n: rows for `list`.
    """
    v = varlist.strip()
    iff = f" if {condition}" if condition.strip() else ""
    cmds = {
        "overview": f"describe, short\ncapture noisily xtset\ncount{iff}\nsummarize {v}{iff}",
        "describe": f"describe {v}",
        "summarize": f"summarize {v}{iff}",
        "detail": f"summarize {v}{iff}, detail",
        "codebook": f"codebook {v}, compact",
        "list": f"preserve\nquietly keep{iff}\nlist {v} in 1/`=min({int(n)}, _N)', abbreviate(16) noobs\nrestore",
        "tabulate": f"tabulate {v}{iff}, missing",
        "xtdescribe": "xtset\nxtdescribe",
        "missing": f"misstable summarize {v}{iff}",
        "count": f"count{iff}",
    }
    if action not in cmds:
        return f"Unknown action. Use one of: {', '.join(cmds)}"
    return _fmt(await S.run(ctx, cmds[action], 120, record=False))


def _num(x, d=4):
    if x is None:
        return "."
    if abs(x) >= 1e5 or (abs(x) < 1e-3 and x != 0):
        return f"{x:.{d}e}"
    return f"{x:.{d}f}"


@mcp.tool()
async def stata_results(ctx: Context, name: str | None = None, include_base: bool = False) -> str:
    """Structured coefficients and statistics of the active (or a stored) estimation.

    name: optional `estimates store` name; if given it is restored first.
    Returns a coefficient table (b, se, t/z, p, CI) plus e() scalars and key macros (cmd, depvar,
    vce, clustvar, absvars...). Use this to read results precisely instead of parsing text output.
    """
    res = await S.request(ctx, {"op": "results", "name": name}, 60)
    if not res.get("ok"):
        return _fmt(res) if "output" in res else "ERROR: " + res.get("error", "")
    rows = []
    for c in res["coefficients"]:
        if c.get("omitted_or_base") and not include_base:
            continue
        stat = c.get("t", c.get("z"))
        term = (c["equation"] + ":" if c.get("equation") else "") + c["term"]
        rows.append(f"{term:<32} {_num(c.get('b')):>12} {_num(c.get('se')):>12} {_num(stat, 2):>8} {_num(c.get('pvalue'), 3):>7}  [{_num(c.get('ll'))}, {_num(c.get('ul'))}]")
    sc = res["scalars"]
    key_sc = {k: sc[k] for k in ("N", "N_clust", "N_g", "r2", "r2_a", "r2_within", "r2_a_within", "F", "df_r", "rmse", "ll", "chi2") if k in sc}
    mac = res["macros"]
    key_mac = {k: mac[k] for k in ("cmd", "cmdline", "depvar", "vce", "vcetype", "clustvar", "absvars", "title", "estimates_title") if k in mac}
    hdr = f"{'term':<32} {'b':>12} {'se':>12} {'t/z':>8} {'p':>7}  [95% CI]"
    return "\n".join([json.dumps(key_mac, ensure_ascii=False), hdr, *rows, json.dumps(key_sc)])


@mcp.tool()
async def stata_graph(filename: str, ctx: Context, graph_name: str | None = None, pdf: bool = True, width: int = 1800) -> list:
    """Export the current (or named) Stata graph to stata_output/figures and display it.

    Draw the graph first with stata_run/stata_do (e.g. coefplot, twoway, event-study plots).
    Saves <filename>.png (shown inline) and, if pdf=True, <filename>.pdf for LaTeX.
    """
    await S.start(ctx)
    png = _resolve(filename, "figures", ".png").with_suffix(".png")
    nm = f" name({graph_name})" if graph_name else ""
    code = f"graph export {_sq(str(png))}, replace width({int(width)}){nm}"
    if pdf:
        code += f"\ngraph export {_sq(str(png.with_suffix('.pdf')))}, replace{nm}"
    res = await S.run(ctx, code, 120, echo=False)
    if not res.get("ok"):
        return [_fmt(res)]
    msg = f"Saved: {png}" + (f"\nSaved: {png.with_suffix('.pdf')}" if pdf else "")
    return [msg, Image(path=str(png))]


def _tex_note(s: str) -> str:
    return s.replace("%", r"\%")


@mcp.tool()
async def stata_table(
    models: list[str],
    filename: str,
    ctx: Context,
    title: str = "",
    mtitles: list[str] | None = None,
    keep: str = "",
    order: str = "",
    coeflabels: dict[str, str] | None = None,
    fe_rows: dict[str, list[str]] | None = None,
    stats: list[str] | None = None,
    se_note: str = "Standard errors in parentheses.",
    notes: list[str] | None = None,
    decimals: int = 3,
    fragment: bool = False,
    label: bool = True,
    show_constant: bool = False,
) -> str:
    """Export stored models to a publication LaTeX table (esttab, booktabs) and return the .tex.

    models: names from `estimates store` (e.g. ["m1","m2","m3"]), in column order.
    filename: bare name -> stata_output/tables/<name>.tex.
    keep/order: Stata coefficient lists, e.g. "treat_post" or "1.treat#1.post".
    coeflabels: {"treat_post": "Treat $\\times$ Post"}; fe_rows: {"Firm FE": ["Yes","Yes","Yes"], ...}
    stats: from N, r2, r2_a, r2_within, N_clust, F, ymean (ymean must be added via estadd);
           default ["N","r2_a"] (use r2_within for reghdfe).
    se_note: describe the SEs, e.g. "Standard errors clustered at the county level in parentheses."
    Stars: * p<0.10, ** p<0.05, *** p<0.01. Requires estout (ssc install estout).
    """
    if not models:
        return "Provide at least one stored model name."
    stats = stats or ["N", "r2_a"]
    pre = []
    keys, labs, fmts = [], [], []
    for i, (lab, vals) in enumerate((fe_rows or {}).items(), 1):
        if len(vals) != len(models):
            return f"fe_rows['{lab}'] has {len(vals)} values but there are {len(models)} models."
        for m, val in zip(models, vals):
            pre.append(f"quietly estadd local fe{i} {_sq(val)} : {m}")
        keys.append(f"fe{i}"); labs.append(lab); fmts.append("%s")
    stat_lab = {"N": "Observations", "r2": r"\(R^{2}\)", "r2_a": r"Adjusted \(R^{2}\)", "r2_within": r"Within \(R^{2}\)",
                "r2_a_within": r"Adj. within \(R^{2}\)", "N_clust": "Clusters", "F": "F statistic", "ymean": "Mean of dep. var."}
    for s in stats:
        keys.append(s); labs.append(stat_lab.get(s, s)); fmts.append("%9.0fc" if s in ("N", "N_clust") else f"%9.{decimals}f")
    m = " ".join(models)
    star = "star(* 0.10 ** 0.05 *** 0.01)"
    common = f"b({decimals}) se({decimals}) {star} nogaps"
    if label:
        common += " label"
    if mtitles:
        common += " mtitles(" + " ".join(_sq(t) for t in mtitles) + ")"
    else:
        common += " nomtitles"
    if keep.strip():
        common += f" keep({keep})"
    elif not show_constant:
        common += " drop(_cons)"
    if order.strip():
        common += f" order({order})"
    if coeflabels:
        common += " coeflabels(" + " ".join(f"{k} {_sq(v)}" for k, v in coeflabels.items()) + ")"
    stats_opt = "stats(" + " ".join(keys) + ", labels(" + " ".join(_sq(x) for x in labs) + ") fmt(" + " ".join(fmts) + "))"
    tex = _resolve(filename, "tables", ".tex").with_suffix(".tex")
    note_list = [_tex_note(se_note), r"\sym{*} \(p<0.10\), \sym{**} \(p<0.05\), \sym{***} \(p<0.01\)"] + [_tex_note(n) for n in (notes or [])]
    tex_opts = f"{common} {stats_opt} booktabs replace nonotes addnotes(" + " ".join(_sq(n) for n in note_list) + ")"
    if title:
        tex_opts += f" title({_sq(title)})"
    if fragment:
        tex_opts += " fragment"
    code = "\n".join(pre + [f"quietly esttab {m} using {_sq(str(tex))}, {tex_opts}"])
    res = await S.run(ctx, code, 120, echo=False)
    if not res.get("ok"):
        return _fmt(res)
    res = await S.run(ctx, f"esttab {m}, {common} {stats_opt}", 60, echo=False, record=False)
    try:
        body = tex.read_text(encoding="utf-8")
    except OSError:
        body = ""
    return f"Saved LaTeX table: {tex}\n(Needs \\usepackage{{booktabs}}.)\n\n--- preview ---\n{res['output'].strip()}\n\n--- {tex.name} ---\n{body}"


def _strip_smcl(t: str) -> str:
    t = re.sub(r"\{\*[^}]*\}", "", t)
    t = re.sub(r"\{(?:hline|dup)[^}]*\}", "-" * 40, t)
    for _ in range(4):
        t = re.sub(r"\{[a-zA-Z_][\w ]*?(?: [^{}:]*)?:([^{}]*)\}", r"\1", t)
    t = re.sub(r"\{(?:opt|cmd|it|bf|hi|var|vars|help|helpb|manhelp|manhelpi|manlink|mansection|browse|ul|search|stata)\s+([^{}]*)\}", r"\1", t)
    t = re.sub(r"\{[^{}]*\}", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


@mcp.tool()
async def stata_help(command: str, ctx: Context, max_chars: int = 15000) -> str:
    """Read the official Stata help file for a command (also works for installed packages, e.g. reghdfe, csdid)."""
    name = command.strip().split()[0]
    res = await S.request(ctx, {"op": "findfile", "fname": f"{name}.sthlp"}, 30)
    path = res.get("path")
    if not path:
        res = await S.request(ctx, {"op": "findfile", "fname": f"{name}.hlp"}, 30)
        path = res.get("path")
    if not path:
        return f"No help file found for '{name}'. It may be an abbreviation (use the full name) or an uninstalled package."
    tmp = S.sub("logs") / ".help_tmp.txt"
    tr = await S.run(ctx, f"quietly translate {_sq(path)} {_sq(str(tmp))}, translator(smcl2txt) replace linesize(120)", 30, echo=False, record=False)
    if tr.get("ok") and tmp.exists():
        txt = tmp.read_text(encoding="utf-8", errors="replace").strip()
        tmp.unlink(missing_ok=True)
    else:
        txt = _strip_smcl(Path(path).read_text(encoding="utf-8", errors="replace"))
    if len(txt) > max_chars:
        txt = txt[:max_chars] + f"\n... [truncated; full file: {path}]"
    return f"{path}\n\n{txt}"


@mcp.tool()
def stata_guide(topic: str = "index") -> str:
    """Applied-econometrics playbook written for this server. Read before modelling.

    topics: index, workflow, panel_fe, did, ddd, event_study, latex_tables, econ_standards, stata_gotchas
    """
    p = GUIDE_DIR / f"{topic}.md"
    if not p.exists():
        avail = sorted(x.stem for x in GUIDE_DIR.glob("*.md"))
        return f"Unknown topic '{topic}'. Available: {', '.join(avail)}"
    return p.read_text(encoding="utf-8")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
