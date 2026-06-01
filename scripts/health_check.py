"""Operator health check for the live NBA betting system.

Cycle 105e (loop 5): single-command status report. Reports OK/WARN/ERROR
for each subsystem with remediation hints. Offseason-aware: missing daemons
and stale predictions only WARN, never ERROR.

Usage:
    python scripts/health_check.py             # human-readable
    python scripts/health_check.py --json      # parseable
    python scripts/health_check.py --strict    # exit 1 on any WARN/ERROR
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Tuple

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OK, WARN, ERROR = "OK", "WARN", "ERROR"


def _record(results: List[Dict[str, Any]], status: str, name: str,
            detail: str, fix: str = "") -> None:
    results.append({"status": status, "name": name, "detail": detail, "fix": fix})


# ---------------------------------------------------------------------------
# 1. Data freshness
# ---------------------------------------------------------------------------
def check_data_freshness(results: List[Dict[str, Any]], now: float | None = None) -> None:
    now = now or time.time()
    today = date.today().isoformat()

    pred = DATA / "predictions" / f"{today}.csv"
    if pred.exists():
        age_h = (now - pred.stat().st_mtime) / 3600
        if age_h > 6:
            _record(results, WARN, f"predictions/{today}.csv",
                    f"stale ({age_h:.1f}h old)",
                    f"python scripts/predict_slate.py --date {today}")
        else:
            _record(results, OK, f"predictions/{today}.csv",
                    f"fresh ({age_h:.1f}h old)")
    else:
        _record(results, WARN, f"predictions/{today}.csv",
                "missing (no pregame predictions for today)",
                f"python scripts/predict_slate.py --date {today}")

    live_dir = DATA / "live"
    if live_dir.exists():
        live_files = sorted(live_dir.glob("*.json"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        if live_files:
            newest = live_files[0]
            age_min = (now - newest.stat().st_mtime) / 60
            if age_min < 10:
                _record(results, OK, "data/live snapshots",
                        f"newest {newest.name} ({age_min:.1f}m old)")
            else:
                _record(results, WARN, "data/live snapshots",
                        f"newest is {age_min:.0f}m old "
                        f"(expect <10m during games; OK if offseason)",
                        "nohup python scripts/live_inplay_daemon.py --interval-min 5 &")
        else:
            _record(results, WARN, "data/live snapshots", "no snapshot files",
                    "Start live_inplay_daemon during a game")
    else:
        _record(results, WARN, "data/live/", "directory missing",
                "mkdir data/live")

    lines_dir = DATA / "lines"
    if lines_dir.exists():
        lf = list(lines_dir.glob(f"{today}*.csv"))
        if lf:
            age_h = (now - max(p.stat().st_mtime for p in lf)) / 3600
            tag = OK if age_h < 1 else WARN
            _record(results, tag, f"lines/{today}_*.csv",
                    f"{len(lf)} files, newest {age_h:.1f}h old")
        else:
            _record(results, WARN, f"lines/{today}_*.csv",
                    "no line snapshots today (OK if offseason / no slate)",
                    "nohup python scripts/fetch_live_prop_lines.py --interval-min 10 &")
    else:
        _record(results, WARN, "data/lines/", "directory missing")


# ---------------------------------------------------------------------------
# 2. Daemon health
# ---------------------------------------------------------------------------
def _process_running(needle: str) -> bool:
    try:
        if os.name == "nt":
            out = subprocess.check_output(
                ["wmic", "process", "get", "CommandLine"],
                stderr=subprocess.DEVNULL, timeout=5).decode(errors="ignore")
        else:
            out = subprocess.check_output(["ps", "-eo", "args"],
                                          stderr=subprocess.DEVNULL,
                                          timeout=5).decode(errors="ignore")
    except Exception:
        return False
    return needle in out


def check_daemons(results: List[Dict[str, Any]]) -> None:
    for script, fix in [
        ("live_inplay_daemon.py",
         "nohup python scripts/live_inplay_daemon.py --interval-min 5 --trigger-alerts &"),
        ("fetch_live_prop_lines.py",
         "nohup python scripts/fetch_live_prop_lines.py --interval-min 10 &"),
    ]:
        if _process_running(script):
            _record(results, OK, f"daemon: {script}", "running")
        else:
            _record(results, WARN, f"daemon: {script}",
                    "not running (OK during offseason / non-game-time)", fix)


# ---------------------------------------------------------------------------
# 3. Storage
# ---------------------------------------------------------------------------
def check_storage(results: List[Dict[str, Any]]) -> None:
    try:
        total, used, free = shutil.disk_usage(str(DATA))
        pct = used / total * 100
        if pct > 90:
            _record(results, ERROR, "disk usage", f"{pct:.1f}% full",
                    "Free space on data drive — archive old snapshots")
        elif pct > 80:
            _record(results, WARN, "disk usage", f"{pct:.1f}% full",
                    "Consider archiving data/live/*.json older than 7d")
        else:
            _record(results, OK, "disk usage",
                    f"{pct:.1f}% used, {free/1e9:.1f} GB free")
    except Exception as exc:
        _record(results, WARN, "disk usage", f"could not stat: {exc}")

    ledger = DATA / "pnl_ledger.csv"
    if ledger.exists() and ledger.stat().st_size > 0:
        _record(results, OK, "pnl_ledger.csv",
                f"present ({ledger.stat().st_size} bytes)")
    elif ledger.exists():
        _record(results, WARN, "pnl_ledger.csv", "empty",
                "Will be populated by place_bet.py on first bet")
    else:
        _record(results, ERROR, "pnl_ledger.csv", "missing",
                "python -c \"from src.betting.pnl_ledger import PnLLedger; "
                "PnLLedger().save()\"")


# ---------------------------------------------------------------------------
# 4. API endpoints
# ---------------------------------------------------------------------------
def _ping(url: str, timeout: float = 5.0) -> Tuple[bool, str, float]:
    t0 = time.time()
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 health-check"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"{resp.status} OK", time.time() - t0
    except (socket.timeout, TimeoutError):
        return False, "timeout", time.time() - t0
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}", time.time() - t0


def check_api_endpoints(results: List[Dict[str, Any]],
                        skip_network: bool = False) -> None:
    endpoints = [
        ("NBA stats live boxscore",
         "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"),
        ("ESPN scoreboard",
         "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"),
        ("DK eventgroup (NBA)",
         "https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/42648"),
        ("FD events",
         "https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page?page=SPORT&sport=BASKETBALL"),
    ]
    if skip_network:
        for name, _ in endpoints:
            _record(results, OK, name, "skipped (network disabled)")
        return
    for name, url in endpoints:
        ok, msg, dt = _ping(url)
        if ok:
            _record(results, OK, name, f"{msg} in {dt:.2f}s")
        elif "timeout" in msg.lower():
            _record(results, WARN, name, f"transient: {msg} ({dt:.2f}s)",
                    "Retry in a few seconds; check internet connectivity")
        else:
            _record(results, WARN, name, msg,
                    "Endpoint may have changed schema; check live_engine.py")


# ---------------------------------------------------------------------------
# 5. Module imports
# ---------------------------------------------------------------------------
def check_imports(results: List[Dict[str, Any]]) -> None:
    targets = [
        ("src.prediction.live_engine", "project_from_snapshot"),
        ("src.prediction.live_factors", "foul_trouble_factor"),
        ("src.prediction.minute_trajectory_foul_residual", None),
        ("src.prediction.blowout_residual", None),
        ("src.prediction.heat_check_shrinkage_residual", None),
    ]
    for mod_name, attr in targets:
        try:
            mod = importlib.import_module(mod_name)
            if attr and not hasattr(mod, attr):
                _record(results, ERROR, f"import {mod_name}",
                        f"missing attribute '{attr}'",
                        f"Check {mod_name.replace('.', '/')}.py exports")
            else:
                _record(results, OK, f"import {mod_name}",
                        "importable" + (f" ({attr})" if attr else ""))
        except Exception as exc:
            _record(results, ERROR, f"import {mod_name}",
                    f"{type(exc).__name__}: {exc}",
                    f"Fix syntax / missing deps in {mod_name}")


# ---------------------------------------------------------------------------
# 6. Model artifacts
# ---------------------------------------------------------------------------
def check_model_artifacts(results: List[Dict[str, Any]]) -> None:
    artifacts = [
        "minute_trajectory.lgb",
        "minute_trajectory_foul_residual.lgb",
        "blowout_residual.lgb",
        "heat_check_shrinkage_residual.lgb",
    ]
    for name in artifacts:
        p = DATA / "models" / name
        if p.exists() and p.stat().st_size > 0:
            _record(results, OK, f"models/{name}",
                    f"present ({p.stat().st_size/1024:.1f} KB)")
        elif p.exists():
            _record(results, ERROR, f"models/{name}", "empty file",
                    f"Retrain via the corresponding train_*.py script")
        else:
            _record(results, ERROR, f"models/{name}", "missing",
                    "Retrain via the corresponding train_*.py script")


# ---------------------------------------------------------------------------
# 7. Config
# ---------------------------------------------------------------------------
def check_config(results: List[Dict[str, Any]]) -> None:
    if os.environ.get("SLACK_ALERT_WEBHOOK") or os.environ.get("DISCORD_ALERT_WEBHOOK"):
        _record(results, OK, "alert webhook",
                "configured (Slack or Discord)")
    else:
        _record(results, WARN, "alert webhook",
                "neither SLACK_ALERT_WEBHOOK nor DISCORD_ALERT_WEBHOOK set",
                "export SLACK_ALERT_WEBHOOK=https://hooks.slack.com/...")

    bankroll_files = [DATA / "bankroll.json", DATA / "bankroll.csv",
                      ROOT / "bankroll.json"]
    if any(p.exists() for p in bankroll_files):
        _record(results, OK, "bankroll", "registered")
    else:
        _record(results, WARN, "bankroll",
                "no bankroll file found",
                'create data/bankroll.json (e.g. {"bankroll": 1000})')


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def run_all(skip_network: bool = False) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for fn in (check_data_freshness, check_daemons, check_storage,
               check_imports, check_model_artifacts, check_config):
        try:
            fn(results)
        except Exception as exc:  # never let a check crash the whole report
            _record(results, ERROR, fn.__name__,
                    f"check crashed: {type(exc).__name__}: {exc}")
    try:
        check_api_endpoints(results, skip_network=skip_network)
    except Exception as exc:
        _record(results, ERROR, "check_api_endpoints",
                f"check crashed: {type(exc).__name__}: {exc}")
    return results


def format_human(results: List[Dict[str, Any]]) -> str:
    lines = []
    for r in results:
        lines.append(f"[{r['status']:<5}] {r['name']} — {r['detail']}")
        if r["status"] in (WARN, ERROR) and r["fix"]:
            lines.append(f"        FIX: {r['fix']}")
    ok = sum(1 for r in results if r["status"] == OK)
    warn = sum(1 for r in results if r["status"] == WARN)
    err = sum(1 for r in results if r["status"] == ERROR)
    lines.append("")
    lines.append(f"SUMMARY: {ok} OK, {warn} WARN, {err} ERROR")
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any WARN or ERROR")
    ap.add_argument("--skip-network", action="store_true",
                    help="skip outbound API pings (for offline test)")
    args = ap.parse_args(argv)

    results = run_all(skip_network=args.skip_network)

    if args.json:
        ok = sum(1 for r in results if r["status"] == OK)
        warn = sum(1 for r in results if r["status"] == WARN)
        err = sum(1 for r in results if r["status"] == ERROR)
        print(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "summary": {"ok": ok, "warn": warn, "error": err},
            "checks": results,
        }, indent=2))
    else:
        print(format_human(results))

    if args.strict:
        bad = any(r["status"] in (WARN, ERROR) for r in results)
        return 1 if bad else 0
    has_error = any(r["status"] == ERROR for r in results)
    return 1 if has_error else 0


if __name__ == "__main__":
    sys.exit(main())
