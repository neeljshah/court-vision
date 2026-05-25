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
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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
class ReadinessReport:
    layers: dict[str, list[CheckResult]]
    summary: dict[str, int]   # pass, fail, skip, n_a, layers
    generated_at: str

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


def check_paper_default(layer: str, module_path: Path) -> CheckResult:
    src = _read_source(module_path)
    if src is None:
        return CheckResult(layer, "paper_default", "SKIP", "source unreadable")
    if not _RE_LIVE.search(src):
        return CheckResult(layer, "paper_default", "N/A", "no live/paper tokens found")
    if (
        _RE_PAPER_CONST.search(src)
        or _RE_PAPER_FALLBACK.search(src)
        or _RE_LIVE_GATE.search(src)
        or re.search(r"MODE GATING", src, re.IGNORECASE)
    ):
        return CheckResult(layer, "paper_default", "PASS", "paper/safe default present")
    return CheckResult(layer, "paper_default", "FAIL", "live tokens found but no paper default detected")


def check_atomic_writes(layer: str, module_path: Path) -> CheckResult:
    src = _read_source(module_path)
    if src is None:
        return CheckResult(layer, "atomic_writes", "SKIP", "source unreadable")
    lines = src.splitlines()
    write_lines = [i for i, ln in enumerate(lines, 1) if _RE_WRITE.search(ln)]
    if not write_lines:
        return CheckResult(layer, "atomic_writes", "PASS", "no write call sites found")
    bad = [
        ln for ln in write_lines
        if not _RE_ATOMIC.search("\n".join(lines[max(0, ln - 6): min(len(lines), ln + 5)]))
    ]
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


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Audit L1-L40 execute_loop layers for production readiness.")
    sub = parser.add_subparsers(dest="cmd")
    audit_p = sub.add_parser("audit", help="Run all checks and print report")
    audit_p.add_argument("--json", metavar="OUT", help="Write JSON report to file")
    audit_p.add_argument("--strict", action="store_true", help="Exit 1 if any FAIL found")
    args = parser.parse_args()
    if args.cmd != "audit":
        parser.print_help()
        return
    data_dir_env = os.environ.get("L42_DATA_DIR")
    strict = args.strict or os.environ.get("L42_STRICT", "") == "1"
    checker = ReadinessChecker(
        layers_dir=_HERE,
        state_json_path=_HERE / "state.json",
        data_dir=Path(data_dir_env) if data_dir_env else None,
    )
    report = checker.run_all_checks()
    if args.json:
        out = Path(args.json)
        out.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        print(f"JSON report written to {out}")
    else:
        print(report.to_markdown())
    if strict and report.summary["fail"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    _cli()
