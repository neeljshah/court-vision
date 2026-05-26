"""L42_production_readiness.py — Production Readiness Checker for L1-L40.

Read-only: never modifies any audited module or data file.

Environment variables:
    L42_DATA_DIR   Override project data/ path (default: PROJECT_ROOT/data/)
    L42_STRICT     Set to "1" to exit 1 if any FAIL found (same as --strict CLI flag)
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import stat
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set

_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parents[1]
_DEFAULT_DATA_DIR = _PROJECT_ROOT / "data"

_COMMON_ENV_VARS = frozenset({
    "PATH", "HOME", "USERPROFILE", "TZ", "USER", "PYTHONPATH",
    "CONDA_PREFIX", "VIRTUAL_ENV", "TEMP", "TMP", "APPDATA",
})


@dataclass(frozen=True)
class CheckResult:
    layer: str
    check: str    # "paper_default" | "atomic_writes" | "env_var_docs" | "file_perms"
    status: str   # "PASS" | "FAIL" | "SKIP" | "N/A"
    detail: str
    evidence: tuple[str, ...] = ()


@dataclass
class LayerKPI:
    layer: str
    name: str                   # human-readable name from state.json
    checks_total: int           # non-SKIP, non-N/A checks
    checks_pass: int
    checks_fail: int
    stability_score: float      # 0.0 – 100.0
    v1_tests: str               # e.g. "10/10" from first ship in state.json
    v2_tests: Optional[str]     # e.g. "12/12" from last v2 ship; None if no v2
    ships: int                  # number of ship entries in state.json

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReadinessReport:
    layers: dict[str, list[CheckResult]]
    summary: dict[str, int]   # pass, fail, skip, n_a, layers
    generated_at: str

    # ------------------------------------------------------------------
    # KPI helpers
    # ------------------------------------------------------------------

    def compute_layer_kpis(self, state_json_path: Path) -> dict[str, LayerKPI]:
        """Return a LayerKPI per layer (including 'global') keyed by layer name."""
        state = json.loads(state_json_path.read_text(encoding="utf-8"))
        state_layers: dict = state.get("layers", {})

        kpis: dict[str, LayerKPI] = {}
        for layer, results in self.layers.items():
            # Tally checks (exclude SKIP and N/A)
            n_pass = sum(1 for r in results if r.status == "PASS")
            n_fail = sum(1 for r in results if r.status == "FAIL")
            total = n_pass + n_fail
            score = (100.0 * n_pass / total) if total > 0 else 100.0

            # Pull data from state.json (skip for 'global' pseudo-layer)
            layer_info = state_layers.get(layer, {})
            layer_name = layer_info.get("name", layer)
            ships_list: list[dict] = layer_info.get("ships", [])
            n_ships = len(ships_list)

            # v1_tests: first ship's tests field
            v1_tests = ships_list[0].get("tests", "") if ships_list else ""

            # v2_tests: last ship that has a "version" field
            v2_ship = None
            for s in reversed(ships_list):
                if "version" in s:
                    v2_ship = s
                    break
            v2_tests: Optional[str] = v2_ship.get("tests") if v2_ship else None

            kpis[layer] = LayerKPI(
                layer=layer,
                name=layer_name,
                checks_total=total,
                checks_pass=n_pass,
                checks_fail=n_fail,
                stability_score=round(score, 1),
                v1_tests=v1_tests,
                v2_tests=v2_tests,
                ships=n_ships,
            )
        return kpis

    def kpi_summary_markdown(self, kpis: dict[str, LayerKPI]) -> str:
        """Render a markdown table of per-layer KPI data."""
        lines: list[str] = [
            "# L42 Layer KPI Summary",
            f"Generated: {self.generated_at}", "",
            "| Layer | Name | Stability | Pass | Fail | Tests (v1→v2) | Ships | Notes |",
            "|-------|------|----------:|-----:|-----:|---------------|------:|-------|",
        ]
        for layer, kpi in sorted(kpis.items(), key=lambda kv: _sort_key(kv[0])):
            tests_col = kpi.v1_tests
            if kpi.v2_tests and kpi.v2_tests != kpi.v1_tests:
                tests_col = f"{kpi.v1_tests}→{kpi.v2_tests}"
            note = ""
            if kpi.checks_fail > 0:
                note = f"{kpi.checks_fail} FAIL(s) need attention"
            elif kpi.checks_total == 0:
                note = "all SKIP/N/A"
            lines.append(
                f"| {layer} | {kpi.name} | {kpi.stability_score:.1f}% "
                f"| {kpi.checks_pass} | {kpi.checks_fail} "
                f"| {tests_col} | {kpi.ships} | {note} |"
            )
        return "\n".join(lines)

    def to_markdown(self) -> str:
        lines: list[str] = [
            "# L42 Production Readiness Report",
            f"Generated: {self.generated_at}", "",
            "## Summary",
            f"- Layers audited: {self.summary['layers']}",
            f"- PASS: {self.summary['pass']}  FAIL: {self.summary['fail']}"
            f"  SKIP: {self.summary['skip']}  N/A: {self.summary['n_a']}", "",
            "## Results",
        ]
        for layer, results in sorted(self.layers.items(), key=lambda kv: _sort_key(kv[0])):
            lines.append(f"\n### {layer}")
            for r in results:
                icon = {"PASS": "OK", "FAIL": "FAIL", "SKIP": "SKIP", "N/A": "N/A"}.get(r.status, r.status)
                lines.append(f"  [{icon}] {r.check}: {r.detail}")
                for ev in r.evidence:
                    lines.append(f"         {ev}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "summary": self.summary,
            "layers": {k: [asdict(r) for r in v] for k, v in self.layers.items()},
        }


def _sort_key(name: str) -> int:
    m = re.search(r"\d+", name)
    return int(m.group()) if m else 9999


_RE_PAPER_CONST = re.compile(r"PAPER_MODE\s*=\s*True", re.IGNORECASE)
_RE_PAPER_FALLBACK = re.compile(r'os\.environ\.get\([^)]*,\s*["\']paper["\']', re.IGNORECASE)
_RE_LIVE = re.compile(r"\blive\b", re.IGNORECASE)
_RE_LIVE_GATE = re.compile(
    r'os\.environ(?:\.get)?\(["\'][A-Z_]*LIVE[A-Z_]*["\']\)\s*(?:==\s*["\']1["\']|!=\s*["\'])',
    re.IGNORECASE,
)
_RE_WRITE = re.compile(
    r"(\.to_parquet\s*\(|\.to_csv\s*\(|json\.dump\s*\(|\.write\s*\(|open\s*\([^)]+['\"]w['\"])"
)
_RE_ATOMIC = re.compile(r"(os\.replace|os\.rename|\.rename\(|\.replace\(|\.tmp)")
_RE_ENV = re.compile(
    r'os\.environ(?:\.get\(["\']|\.?\[["\'])([A-Z][A-Z0-9_]+)["\']'
    r"|os\.getenv\([\"']([A-Z][A-Z0-9_]+)[\"']"
)

# Regex to detect atomic-helper function definitions by name pattern
_RE_ATOMIC_HELPER_DEF = re.compile(
    r"(?i)(atomic_write|_atomic_write|_safe_write|_safe_dump|_write_lock_atomic)"
)

# Regex for write call sites that are always exempt (not file writes)
_RE_EXEMPT_WRITE = re.compile(
    r"""
    self\.wfile\.write\s*\(          # HTTP response writes
    | sys\.stdout\.write\s*\(        # stdout
    | sys\.stderr\.write\s*\(        # stderr
    | io\.(StringIO|BytesIO)\(\)\.write\s*\(  # buffer writes
    """,
    re.VERBOSE,
)


def _read_source(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _docstring(source: str) -> str:
    try:
        ds = ast.get_docstring(ast.parse(source))
        return ds or ""
    except SyntaxError:
        return ""


# ---------------------------------------------------------------------------
# AST helpers for atomic-write detection
# ---------------------------------------------------------------------------

def _collect_atomic_helper_names(source: str) -> Set[str]:
    """Return names of top-level functions whose bodies call os.replace/os.rename.

    Also includes functions whose names match the atomic-helper naming pattern
    AND contain os.replace or os.rename in their body.
    """
    helpers: Set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return helpers

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # Only include if name matches helper pattern OR body contains os.replace/rename
        name_matches = bool(_RE_ATOMIC_HELPER_DEF.search(node.name))
        body_has_atomic = _ast_body_has_os_replace(node)
        if body_has_atomic or name_matches:
            # Require that the body ACTUALLY has os.replace/rename
            if body_has_atomic:
                helpers.add(node.name)
    return helpers


def _ast_body_has_os_replace(func_node) -> bool:
    """Return True if the function body contains an os.replace or os.rename call."""
    for child in ast.walk(func_node):
        if not isinstance(child, ast.Call):
            continue
        fn = child.func
        # os.replace(...)  or  os.rename(...)
        if (
            isinstance(fn, ast.Attribute)
            and fn.attr in ("replace", "rename")
            and isinstance(fn.value, ast.Name)
            and fn.value.id == "os"
        ):
            return True
        # path.replace(...)  path.rename(...)  — Path method calls
        if isinstance(fn, ast.Attribute) and fn.attr in ("replace", "rename"):
            return True
    return False


def _get_write_call_names_at_line(line: str) -> list[str]:
    """Extract the function/method names being called in a write-matching line."""
    names = []
    # Match simple patterns like `_atomic_write_json(...)`, `helper_name(...)`
    for m in re.finditer(r"(\w+)\s*\(", line):
        names.append(m.group(1))
    return names


def _line_calls_atomic_helper(line: str, helpers: Set[str]) -> bool:
    """Return True if *line* contains a call to one of the known atomic helpers."""
    for name in helpers:
        if re.search(r"\b" + re.escape(name) + r"\s*\(", line):
            return True
    return False


def _line_is_exempt_write(line: str) -> bool:
    """Return True if the write on this line is always exempt (non-file write)."""
    return bool(_RE_EXEMPT_WRITE.search(line))


# ---------------------------------------------------------------------------
# AST helpers for paper_default (docstring vs code 'live' token analysis)
# ---------------------------------------------------------------------------

def _collect_docstring_line_ranges(source: str) -> Set[int]:
    """Return set of 1-based line numbers that are part of a docstring."""
    ranges: Set[int] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ranges
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef, ast.Module)):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            for lineno in range(first.lineno, first.end_lineno + 1):
                ranges.add(lineno)
    return ranges


def _live_appears_only_in_prose(source: str) -> bool:
    """Return True if every 'live' token in *source* lives in a docstring or comment.

    If ANY 'live' token appears in executable code (outside docstrings/comments),
    returns False — the caller should perform the full live-mode gate check.
    """
    lines = source.splitlines()
    ds_lines = _collect_docstring_line_ranges(source)

    for i, line in enumerate(lines, 1):
        if not _RE_LIVE.search(line):
            continue
        stripped = line.strip()
        # Pure comment line
        if stripped.startswith("#"):
            continue
        # Inside a docstring
        if i in ds_lines:
            continue
        # 'live' appears in actual code
        return False
    return True


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_paper_default(layer: str, module_path: Path) -> CheckResult:
    src = _read_source(module_path)
    if src is None:
        return CheckResult(layer, "paper_default", "SKIP", "source unreadable")
    if not _RE_LIVE.search(src):
        return CheckResult(layer, "paper_default", "N/A", "no live/paper tokens found")

    # Fast-path positive: well-known safe patterns
    if (
        _RE_PAPER_CONST.search(src)
        or _RE_PAPER_FALLBACK.search(src)
        or _RE_LIVE_GATE.search(src)
        or re.search(r"MODE GATING", src, re.IGNORECASE)
    ):
        return CheckResult(layer, "paper_default", "PASS", "paper/safe default present")

    # Tightening rule: if 'live' appears ONLY in docstrings/comments (prose),
    # it is documentation text, not a live-mode toggle — treat as N/A.
    if _live_appears_only_in_prose(src):
        return CheckResult(
            layer, "paper_default", "N/A",
            "live token(s) in prose only — no runtime live-mode toggle"
        )

    return CheckResult(layer, "paper_default", "FAIL",
                       "live tokens found but no paper default detected")


def check_atomic_writes(layer: str, module_path: Path) -> CheckResult:
    src = _read_source(module_path)
    if src is None:
        return CheckResult(layer, "atomic_writes", "SKIP", "source unreadable")

    # Discover atomic-helper functions defined in this module
    atomic_helpers = _collect_atomic_helper_names(src)

    lines = src.splitlines()
    write_lines = [i for i, ln in enumerate(lines, 1) if _RE_WRITE.search(ln)]
    if not write_lines:
        return CheckResult(layer, "atomic_writes", "PASS", "no write call sites found")

    bad = []
    for ln in write_lines:
        line_text = lines[ln - 1]

        # Exempt: non-file writes (HTTP response, stdout, stderr, buffer)
        if _line_is_exempt_write(line_text):
            continue

        # Exempt: this line calls one of the module's own atomic helpers
        if atomic_helpers and _line_calls_atomic_helper(line_text, atomic_helpers):
            continue

        # Standard check: nearby os.replace/rename in surrounding ±10 lines
        context = "\n".join(lines[max(0, ln - 6): min(len(lines), ln + 5)])
        if _RE_ATOMIC.search(context):
            continue

        bad.append(ln)

    if not bad:
        return CheckResult(layer, "atomic_writes", "PASS", "all writes paired with atomic rename")
    evidence = tuple(f"line {ln}: {lines[ln-1].strip()[:80]}" for ln in bad[:5])
    return CheckResult(layer, "atomic_writes", "FAIL",
                       f"{len(bad)} write(s) without nearby atomic rename", evidence)


def check_env_var_documentation(layer: str, module_path: Path) -> CheckResult:
    src = _read_source(module_path)
    if src is None:
        return CheckResult(layer, "env_var_docs", "SKIP", "source unreadable")
    ds = _docstring(src)
    used: set[str] = set()
    for m in _RE_ENV.finditer(src):
        name = m.group(1) or m.group(2)
        if name and name not in _COMMON_ENV_VARS:
            used.add(name)
    if not used:
        return CheckResult(layer, "env_var_docs", "N/A", "no custom env vars referenced")
    # Case-sensitive: avoids false positive on lowercase "env vars" in prose
    if re.search(r"(Environment variables:|ENV:|MODE GATING)", ds):
        return CheckResult(layer, "env_var_docs", "PASS", "env section found in docstring")
    missing = [v for v in sorted(used) if v not in ds]
    if not missing:
        return CheckResult(layer, "env_var_docs", "PASS", "all env vars appear in docstring")
    return CheckResult(layer, "env_var_docs", "FAIL",
                       f"{len(missing)} env var(s) not documented in module docstring",
                       tuple(missing[:8]))


def check_file_perms(data_dir: Path) -> list[CheckResult]:
    if os.name == "nt":
        return [CheckResult("global", "file_perms", "SKIP", "POSIX perm check skipped on Windows")]
    results: list[CheckResult] = []
    for subdir in ("ledger", "exchange_seed"):
        target = data_dir / subdir
        if not target.exists():
            results.append(CheckResult("global", "file_perms", "SKIP", f"dir absent: {target}"))
            continue
        bad = []
        for p in target.rglob("*"):
            if p.is_file():
                try:
                    depth = len(p.relative_to(target).parts)
                    if depth <= 3 and p.stat().st_mode & stat.S_IWOTH:
                        bad.append(str(p))
                except (OSError, ValueError):
                    pass
        if bad:
            results.append(CheckResult("global", "file_perms", "FAIL",
                                       f"{len(bad)} world-writable file(s) in {subdir}",
                                       tuple(bad[:5])))
        else:
            results.append(CheckResult("global", "file_perms", "PASS",
                                       f"no world-writable files in data/{subdir}"))
    return results


class ReadinessChecker:
    def __init__(self, layers_dir: Path, state_json_path: Path, data_dir: Optional[Path] = None):
        self.layers_dir = Path(layers_dir)
        self.state_json_path = Path(state_json_path)
        self.data_dir = Path(data_dir) if data_dir else _DEFAULT_DATA_DIR

    def _discover_layers(self) -> list[tuple[str, Path]]:
        state = json.loads(self.state_json_path.read_text(encoding="utf-8"))
        found: list[tuple[str, Path]] = []
        for name, info in state.get("layers", {}).items():
            if info.get("status") != "shipped":
                continue
            num = re.search(r"\d+", name)
            if not num:
                continue
            n = int(num.group())
            matches = list(self.layers_dir.glob(f"L{n:02d}_*.py")) or list(self.layers_dir.glob(f"L{n}_*.py"))
            if matches:
                found.append((name, matches[0]))
        found.sort(key=lambda t: _sort_key(t[0]))
        return found

    def run_all_checks(self) -> ReadinessReport:
        shipped = self._discover_layers()
        layers_results: dict[str, list[CheckResult]] = {
            layer: [
                check_paper_default(layer, path),
                check_atomic_writes(layer, path),
                check_env_var_documentation(layer, path),
            ]
            for layer, path in shipped
        }
        layers_results["global"] = check_file_perms(self.data_dir)
        counts: dict[str, int] = {"pass": 0, "fail": 0, "skip": 0, "n_a": 0}
        for results in layers_results.values():
            for r in results:
                key = r.status.lower()
                if key == "n/a":
                    counts["n_a"] += 1
                elif key in counts:
                    counts[key] += 1
        counts["layers"] = len(shipped)
        return ReadinessReport(
            layers=layers_results,
            summary=counts,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )


def _cli(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Audit L1-L40 execute_loop layers for production readiness.")
    sub = parser.add_subparsers(dest="cmd")

    audit_p = sub.add_parser("audit", help="Run all checks and print report")
    audit_p.add_argument("--json", metavar="OUT", help="Write JSON report to file")
    audit_p.add_argument("--strict", action="store_true", help="Exit 1 if any FAIL found")

    kpi_p = sub.add_parser("kpi", help="Print per-layer KPI stability scores")
    kpi_p.add_argument("--top", metavar="N", type=int, default=0,
                        help="Show only top-N highest-stability layers")
    kpi_p.add_argument("--bottom", metavar="N", type=int, default=0,
                        help="Show only bottom-N lowest-stability layers")
    kpi_p.add_argument("--json", metavar="OUT", dest="json_out",
                        help="Write KPI dict as JSON to file")

    args = parser.parse_args(argv)

    data_dir_env = os.environ.get("L42_DATA_DIR")
    state_json = _HERE / "state.json"
    checker = ReadinessChecker(
        layers_dir=_HERE,
        state_json_path=state_json,
        data_dir=Path(data_dir_env) if data_dir_env else None,
    )

    if args.cmd == "audit":
        strict = args.strict or os.environ.get("L42_STRICT", "") == "1"
        report = checker.run_all_checks()
        if args.json:
            out = Path(args.json)
            out.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
            print(f"JSON report written to {out}")
        else:
            print(report.to_markdown())
        if strict and report.summary["fail"] > 0:
            raise SystemExit(1)

    elif args.cmd == "kpi":
        report = checker.run_all_checks()
        kpis = report.compute_layer_kpis(state_json)

        # Apply --top / --bottom filters
        sorted_layers = sorted(kpis.items(), key=lambda kv: kpis[kv[0]].stability_score)
        if args.top and args.bottom:
            parser.error("Use --top or --bottom, not both")
        elif args.bottom > 0:
            selected = dict(sorted_layers[: args.bottom])
        elif args.top > 0:
            selected = dict(sorted_layers[-args.top :])
        else:
            selected = kpis

        if args.json_out:
            out = Path(args.json_out)
            payload = {k: v.to_dict() for k, v in selected.items()}
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"KPI JSON written to {out}")
        else:
            print(report.kpi_summary_markdown(selected))

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
