"""L38_health_dashboard.py — System Health Dashboard (execute_loop layer 38).

Runs a registry of named checks against live system resources and produces a
HealthReport with overall HEALTHY / DEGRADED / FAILED status.

Public API
----------
    HealthCheck     dataclass
    HealthReport    dataclass
    run_all_checks() -> HealthReport
    get_latest_health() -> HealthReport  # 60-second in-process cache
    run_check(name) -> HealthCheck       # single named check

CLI
---
    python L38_health_dashboard.py check [--name <check>]
    python L38_health_dashboard.py serve [--port 9876]
    python L38_health_dashboard.py once   # exit 0/1/2 = HEALTHY/DEGRADED/FAILED

Environment Variables
---------------------
    HEALTH_FILE     — Override path for system_health.json persistence file.
                      Default: <project_root>/data/ledger/system_health.json
    HEALTH_CACHE_TTL — In-process cache TTL in seconds before re-reading disk.
                      Default: 60
    HEALTH_PORT     — Default HTTP server port when --port is not given.
                      Default: 9876
"""
from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable, Dict, List, Optional

# ── project root ─────────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

log = logging.getLogger(__name__)

# ── optional tabulate ─────────────────────────────────────────────────────────
try:
    from tabulate import tabulate as _tabulate
    _HAS_TABULATE = True
except ImportError:
    _HAS_TABULATE = False

# ── ANSI helpers ──────────────────────────────────────────────────────────────
_USE_COLOR = sys.stdout.isatty()
_GREEN = "\033[92m" if _USE_COLOR else ""
_YELLOW = "\033[93m" if _USE_COLOR else ""
_RED = "\033[91m" if _USE_COLOR else ""
_RESET = "\033[0m" if _USE_COLOR else ""

_COLOR = {"PASS": _GREEN, "WARN": _YELLOW, "FAIL": _RED}


def _color(status: str, text: str) -> str:
    return f"{_COLOR.get(status, '')}{text}{_RESET}"


# ── persistence path ──────────────────────────────────────────────────────────
_HEALTH_FILE = Path(
    os.environ.get("HEALTH_FILE",
                   str(PROJECT_DIR / "data" / "ledger" / "system_health.json"))
)

# ── in-process cache ──────────────────────────────────────────────────────────
_CACHE: Optional["HealthReport"] = None
_CACHE_TS: float = 0.0
_CACHE_TTL = float(os.environ.get("HEALTH_CACHE_TTL", "60"))


# =============================================================================
# Atomic I/O helpers
# =============================================================================

def _atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write *content* to *path* atomically via a sibling temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent),
                               prefix=path.name + ".",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(content)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_write_json(path: Path, payload: object, indent: int = 2) -> None:
    """Serialize *payload* as JSON and write atomically to *path*."""
    _atomic_write_text(path, json.dumps(payload, indent=indent))


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class HealthCheck:
    name: str
    status: str          # "PASS" | "WARN" | "FAIL"
    latency_ms: float
    last_data_ts: Optional[str]
    days_stale: float
    details: str
    severity: str        # "info" | "warning" | "critical"


@dataclass
class HealthReport:
    timestamp: str
    overall_status: str  # "HEALTHY" | "DEGRADED" | "FAILED"
    checks: List[HealthCheck]


# =============================================================================
# Check registry
# =============================================================================

_REGISTRY: Dict[str, Callable[[], HealthCheck]] = {}


def register(name: str, severity: str):
    """Decorator — register a zero-arg function as a named health check."""
    def _dec(fn: Callable[[], HealthCheck]):
        def _wrapper() -> HealthCheck:
            t0 = time.perf_counter()
            try:
                result = fn()
            except Exception:
                latency_ms = (time.perf_counter() - t0) * 1000
                tb = traceback.format_exc()[-800:]
                return HealthCheck(
                    name=name,
                    status="FAIL",
                    latency_ms=round(latency_ms, 1),
                    last_data_ts=None,
                    days_stale=0.0,
                    details=f"Traceback:\n{tb}",
                    severity=severity,
                )
            # Patch latency if inner fn didn't set it
            if result.latency_ms == 0.0:
                result.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            return result
        _REGISTRY[name] = _wrapper
        return _wrapper
    return _dec


def _mtime_days(path: Path) -> tuple[Optional[str], float]:
    """Return (iso_ts, days_since_mtime) for a path; (None, 0) if missing."""
    if not path.exists():
        return None, 0.0
    mt = path.stat().st_mtime
    ts = datetime.fromtimestamp(mt, tz=timezone.utc).isoformat()
    days = (time.time() - mt) / 86400
    return ts, round(days, 2)


# =============================================================================
# Individual checks
# =============================================================================

@register("nba_api_up", "critical")
def _check_nba_api() -> HealthCheck:
    import urllib.request
    url = (
        "https://stats.nba.com/stats/scoreboardv2"
        "?DayOffset=0&LeagueID=00&gameDate=01%2F01%2F2025"
    )
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.nba.com/",
        "Accept": "application/json",
    }
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=8):
        pass
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    status = "WARN" if latency_ms > 5000 else "PASS"
    return HealthCheck(
        name="nba_api_up",
        status=status,
        latency_ms=latency_ms,
        last_data_ts=None,
        days_stale=0.0,
        details=f"HTTP 200 in {latency_ms:.0f}ms",
        severity="critical",
    )


@register("pp_snapshots", "critical")
def _check_pp_snapshots() -> HealthCheck:
    snap_dir = PROJECT_DIR / "scripts" / "validation" / "real_lines_check" / "snapshots"
    if not snap_dir.exists():
        return HealthCheck("pp_snapshots", "FAIL", 0.0, None, 0.0,
                           "snapshots/ dir missing", "critical")
    cutoff = time.time() - 86400
    recent = [f for f in snap_dir.iterdir() if f.is_file() and f.stat().st_mtime > cutoff]
    n = len(recent)
    status = "PASS" if n >= 12 else ("WARN" if n > 0 else "FAIL")
    return HealthCheck("pp_snapshots", status, 0.0, None, 0.0,
                       f"{n} snapshot(s) modified in last 24h", "critical")


@register("ledger_writable", "critical")
def _check_ledger_writable() -> HealthCheck:
    ledger_dir = PROJECT_DIR / "data" / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    test_path = ledger_dir / ".health_test"
    test_path.write_text("ok")
    test_path.unlink()
    return HealthCheck("ledger_writable", "PASS", 0.0, None, 0.0,
                       "write+delete succeeded", "critical")


@register("prop_models", "critical")
def _check_prop_models() -> HealthCheck:
    stats = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
    missing = []
    for s in stats:
        p = PROJECT_DIR / "data" / "models" / f"prop_{s}_v3_lgb.txt"
        if not p.exists():
            missing.append(s)
    if missing:
        return HealthCheck("prop_models", "FAIL", 0.0, None, 0.0,
                           f"missing: {missing}", "critical")
    return HealthCheck("prop_models", "PASS", 0.0, None, 0.0,
                       "all 7 v3 LGB models present", "critical")


@register("quantile_calibration", "warning")
def _check_quantile_calibration() -> HealthCheck:
    p = PROJECT_DIR / "data" / "models" / "quantile_calibration.json"
    if not p.exists():
        return HealthCheck("quantile_calibration", "FAIL", 0.0, None, 0.0,
                           "quantile_calibration.json missing", "warning")
    data = json.loads(p.read_text())
    required = {"pts", "reb", "ast", "fg3m", "stl", "blk", "tov"}
    found = set(data.keys())
    missing = required - found
    ts, days = _mtime_days(p)
    status = "FAIL" if missing else ("WARN" if days > 14 else "PASS")
    detail = f"keys OK, {days:.1f}d stale" if not missing else f"missing keys: {missing}"
    return HealthCheck("quantile_calibration", status, 0.0, ts, days, detail, "warning")


@register("win_prob_models", "warning")
def _check_win_prob() -> HealthCheck:
    p = PROJECT_DIR / "data" / "models" / "winprob_walk_forward_results.json"
    if not p.exists():
        return HealthCheck("win_prob_models", "FAIL", 0.0, None, 0.0,
                           "winprob_walk_forward_results.json missing", "warning")
    ts, days = _mtime_days(p)
    status = "WARN" if days > 14 else "PASS"
    return HealthCheck("win_prob_models", status, 0.0, ts, days,
                       f"{days:.1f}d since last walk-forward run", "warning")


@register("live_engine", "critical")
def _check_live_engine() -> HealthCheck:
    try:
        importlib.import_module("src.prediction.live_engine")
        return HealthCheck("live_engine", "PASS", 0.0, None, 0.0,
                           "import OK", "critical")
    except ImportError as e:
        return HealthCheck("live_engine", "WARN", 0.0, None, 0.0,
                           f"ImportError: {e}", "critical")
    except Exception as e:
        return HealthCheck("live_engine", "FAIL", 0.0, None, 0.0,
                           f"Exception: {e}", "critical")


@register("disk_space", "warning")
def _check_disk_space() -> HealthCheck:
    usage = shutil.disk_usage(str(PROJECT_DIR))
    free_gb = usage.free / (1024 ** 3)
    status = "PASS" if free_gb >= 10 else ("WARN" if free_gb >= 2 else "FAIL")
    return HealthCheck("disk_space", status, 0.0, None, 0.0,
                       f"{free_gb:.1f} GB free", "warning")


@register("conda_env", "info")
def _check_conda_env() -> HealthCheck:
    ok = "basketball_ai" in sys.executable
    return HealthCheck("conda_env", "PASS" if ok else "WARN", 0.0, None, 0.0,
                       f"executable: {sys.executable}", "info")


@register("open_positions", "info")
def _check_open_positions() -> HealthCheck:
    try:
        import pandas as pd
        csv = PROJECT_DIR / "data" / "ledger" / "bets.csv"
        parquet = PROJECT_DIR / "data" / "ledger" / "bets.parquet"
        if parquet.exists():
            df = pd.read_parquet(parquet)
        elif csv.exists():
            df = pd.read_csv(csv, dtype=str)
        else:
            return HealthCheck("open_positions", "PASS", 0.0, None, 0.0,
                               "0 open (no ledger file)", "info")
        n = int((df.get("status", df.get("STATUS", pd.Series(dtype=str))) == "OPEN").sum())
        return HealthCheck("open_positions", "PASS", 0.0, None, 0.0,
                           f"{n} open position(s)", "info")
    except Exception as e:
        return HealthCheck("open_positions", "PASS", 0.0, None, 0.0,
                           f"0 open (read error: {e})", "info")


@register("drift_window", "warning")
def _check_drift_window() -> HealthCheck:
    edges_dir = PROJECT_DIR / "data" / "edges"
    if not edges_dir.exists():
        return HealthCheck("drift_window", "WARN", 0.0, None, 0.0,
                           "edges/ dir missing", "warning")
    reports = sorted(edges_dir.glob("clv_report_*.json"), key=lambda p: p.stat().st_mtime)
    if not reports:
        return HealthCheck("drift_window", "WARN", 0.0, None, 0.0,
                           "no clv_report_*.json found", "warning")
    latest = reports[-1]
    data = json.loads(latest.read_text())
    # Accept either a list of records or a dict with a key; fall back gracefully
    rows = data if isinstance(data, list) else data.get("rows", [])
    cutoff = time.time() - 7 * 86400
    recent = [r for r in rows if isinstance(r, dict)
              and r.get("clv_pp") is not None
              and _iso_to_ts(r.get("date", "")) > cutoff]
    if not recent:
        return HealthCheck("drift_window", "WARN", 0.0, None, 0.0,
                           "no 7-day CLV rows in latest report", "warning")
    mean_clv = sum(r["clv_pp"] for r in recent) / len(recent)
    status = "WARN" if mean_clv < -1 else "PASS"
    return HealthCheck("drift_window", status, 0.0, None, 0.0,
                       f"7d mean CLV/pp={mean_clv:.2f} ({len(recent)} rows)", "warning")


def _iso_to_ts(s: str) -> float:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


@register("bot_loop_active", "warning")
def _check_bot_loop() -> HealthCheck:
    import subprocess
    try:
        out = subprocess.check_output(
            ["git", "-C", str(PROJECT_DIR), "log", "-1",
             "--format=%at", "--author=Claude Opus"],
            stderr=subprocess.DEVNULL, timeout=10,
        ).decode().strip()
        if not out:
            return HealthCheck("bot_loop_active", "WARN", 0.0, None, 0.0,
                               "no Claude Opus commits found", "warning")
        last_ts = float(out)
        hours = (time.time() - last_ts) / 3600
        status = "WARN" if hours > 24 else "PASS"
        return HealthCheck("bot_loop_active", status, 0.0, None, 0.0,
                           f"last commit {hours:.1f}h ago", "warning")
    except Exception as e:
        return HealthCheck("bot_loop_active", "WARN", 0.0, None, 0.0,
                           f"git error: {e}", "warning")


@register("kalshi_api", "info")
def _check_kalshi() -> HealthCheck:
    try:
        import urllib.request
        urllib.request.urlopen("https://trading-api.kalshi.com/trade-api/v2/exchange/status",
                               timeout=5)
        return HealthCheck("kalshi_api", "PASS", 0.0, None, 0.0, "reachable", "info")
    except Exception:
        return HealthCheck("kalshi_api", "PASS", 0.0, None, 0.0,
                           "unreachable (optional)", "info")


@register("polymarket_api", "info")
def _check_polymarket() -> HealthCheck:
    try:
        import urllib.request
        urllib.request.urlopen("https://clob.polymarket.com/", timeout=5)
        return HealthCheck("polymarket_api", "PASS", 0.0, None, 0.0, "reachable", "info")
    except Exception:
        return HealthCheck("polymarket_api", "PASS", 0.0, None, 0.0,
                           "unreachable (optional)", "info")


# =============================================================================
# Public API
# =============================================================================

def _overall(checks: List[HealthCheck]) -> str:
    for c in checks:
        if c.status == "FAIL" and c.severity == "critical":
            return "FAILED"
    for c in checks:
        if c.status in ("FAIL", "WARN") and c.severity != "info":
            return "DEGRADED"
    return "HEALTHY"


def run_all_checks() -> HealthReport:
    results = [fn() for fn in _REGISTRY.values()]
    report = HealthReport(
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
        overall_status=_overall(results),
        checks=results,
    )
    _persist(report)
    global _CACHE, _CACHE_TS
    _CACHE, _CACHE_TS = report, time.monotonic()
    return report


def get_latest_health() -> HealthReport:
    global _CACHE, _CACHE_TS
    if _CACHE is not None and (time.monotonic() - _CACHE_TS) < _CACHE_TTL:
        return _CACHE
    if _HEALTH_FILE.exists():
        data = json.loads(_HEALTH_FILE.read_text())
        checks = [HealthCheck(**c) for c in data["checks"]]
        report = HealthReport(timestamp=data["timestamp"],
                              overall_status=data["overall_status"],
                              checks=checks)
        _CACHE, _CACHE_TS = report, time.monotonic()
        return report
    return run_all_checks()


def run_check(name: str) -> HealthCheck:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown check: {name!r}. Known: {list(_REGISTRY)}")
    return _REGISTRY[name]()


def _persist(report: HealthReport) -> None:
    payload = {
        "timestamp": report.timestamp,
        "overall_status": report.overall_status,
        "checks": [asdict(c) for c in report.checks],
    }
    _atomic_write_json(_HEALTH_FILE, payload)


# =============================================================================
# Console output
# =============================================================================

def _print_report(report: HealthReport) -> None:
    rows = [
        [_color(c.status, c.status), c.name, c.severity,
         f"{c.latency_ms:.0f}ms", f"{c.days_stale:.1f}d", c.details[:80]]
        for c in report.checks
    ]
    headers = ["Status", "Check", "Severity", "Latency", "Stale", "Details"]
    if _HAS_TABULATE:
        print(_tabulate(rows, headers=headers, tablefmt="simple"))
    else:
        fmt = "{:<6}  {:<28}  {:<8}  {:<8}  {:<6}  {}"
        print(fmt.format(*headers))
        print("-" * 80)
        for r in rows:
            print(fmt.format(*r))
    overall_color = _GREEN if report.overall_status == "HEALTHY" else (
        _YELLOW if report.overall_status == "DEGRADED" else _RED)
    print(f"\nOverall: {overall_color}{report.overall_status}{_RESET}  "
          f"({report.timestamp})")


# =============================================================================
# HTTP server
# =============================================================================

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):  # silence default request logging
        pass

    def do_GET(self):
        if self.path == "/healthz":
            report = get_latest_health()
            code = 200 if report.overall_status == "HEALTHY" else 503
            self.send_response(code)
            self.end_headers()
            self.wfile.write(report.overall_status.encode())
        elif self.path == "/health":
            report = run_all_checks()
            body = json.dumps(
                {"timestamp": report.timestamp,
                 "overall_status": report.overall_status,
                 "checks": [asdict(c) for c in report.checks]},
                indent=2,
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


# =============================================================================
# CLI
# =============================================================================

def main(argv=None):
    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="NBA AI system health dashboard")
    sub = parser.add_subparsers(dest="cmd")

    p_check = sub.add_parser("check", help="Run checks and print table")
    p_check.add_argument("--name", help="Run a single named check")

    p_serve = sub.add_parser("serve", help="HTTP health server")
    p_serve.add_argument("--port", type=int, default=9876)

    sub.add_parser("once", help="Exit 0/1/2 = HEALTHY/DEGRADED/FAILED")

    args = parser.parse_args(argv)

    if args.cmd == "check":
        if args.name:
            c = run_check(args.name)
            _print_report(HealthReport(
                timestamp=datetime.now(tz=timezone.utc).isoformat(),
                overall_status=_overall([c]),
                checks=[c],
            ))
        else:
            _print_report(run_all_checks())

    elif args.cmd == "serve":
        server = HTTPServer(("0.0.0.0", args.port), _Handler)
        print(f"Serving on http://0.0.0.0:{args.port}  (GET /health  GET /healthz)")
        server.serve_forever()

    elif args.cmd == "once":
        report = run_all_checks()
        _print_report(report)
        code = {"HEALTHY": 0, "DEGRADED": 1, "FAILED": 2}.get(report.overall_status, 1)
        sys.exit(code)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
