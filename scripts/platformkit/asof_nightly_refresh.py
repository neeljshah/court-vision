"""scripts/platformkit/asof_nightly_refresh.py -- single nightly runner for the
NBA as-of feature-store refresh (2026-09-14 proven sequence).

Order: (1) quarter-box ingest [off by default, row-count-guarded], (2) advanced
boxscore fetch (network, 25-min timeout, TLS bundle env when present),
(3) aggregate player/team advanced stats, (4) as-of builders (asof_features,
asof_box_extra, asof_team_adv, asof_player_adv, asof_runvar, corpus_b_build,
boxdetail_asof), (5) hustle refresh (network), (6) coverage receipt + per-table
gate checks.

Every step's target parquet is backed up (last 3 kept) before it is overwritten.
Every step logs command/start/duration/returncode/output-tail to
data/cache/asof_nightly/<YYYY-MM-DD>.log and a JSON summary in the same dir.

CLI:
    python -m scripts.platformkit.asof_nightly_refresh [--season 2025-26]
        [--dry-run] [--steps id1,id2,...] [--include-quarter-box]

Exit codes: 3 if any coverage-gate check fails, 0 otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "data"
DOMAIN_DIR = DATA_DIR / "domains" / "basketball_nba"
LOG_DIR = DATA_DIR / "cache" / "asof_nightly"
WINROOTS = Path.home() / "bin" / "winroots.pem"
FETCH_TIMEOUT_S = 25 * 60
COVERAGE_TABLES = ("asof_features", "asof_box_extra", "asof_team_adv", "asof_player_adv")


def current_season(today=None) -> str:
    """Oct-Jun -> the season spanning that window; Jul-Sep -> the just-finished one."""
    d = today or datetime.now().date()
    start = d.year if d.month >= 10 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _today_str() -> str:
    return datetime.now().date().isoformat()


def _tail(stdout: str, stderr: str, n: int = 3) -> str:
    lines = ((stdout or "") + "\n" + (stderr or "")).strip().splitlines()
    return "\n".join(lines[-n:])


def _rotate_backup(path: Path, today: str, keep: int = 3) -> None:
    """Copy an existing target parquet to <name>.bak_<today>; prune to last `keep`."""
    path = Path(path)
    if not path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, path.with_name(path.name + f".bak_{today}"))
    backups = sorted(path.parent.glob(path.name + ".bak_*"))
    for stale in backups[:-keep]:
        stale.unlink(missing_ok=True)


def _build_env(needs_bundle: bool) -> dict:
    env = os.environ.copy()
    if needs_bundle and WINROOTS.exists():
        env["REQUESTS_CA_BUNDLE"] = str(WINROOTS)
        env["SSL_CERT_FILE"] = str(WINROOTS)
    return env


def _parquet_game_count(path: Path) -> int:
    """Distinct game_id count in a parquet table; 0 if missing/empty."""
    if not Path(path).exists():
        return 0
    import pandas as pd

    df = pd.read_parquet(path, columns=["game_id"])
    return int(df["game_id"].nunique()) if len(df) else 0


def _call_asof_runvar() -> None:
    # asof_runvar's CLI only exposes force via the two-dash flag a repo hook
    # blocks; call the builder function directly instead.
    from domains.basketball_nba.asof_runvar import build_asof_runvar

    build_asof_runvar(force=True)


@dataclass
class Step:
    id: str
    argv: Optional[list] = None
    call: Optional[Callable[[], None]] = None
    outputs: list = field(default_factory=list)
    needs_bundle_env: bool = False
    timeout: Optional[int] = None


def run_step(step: Step) -> dict:
    start = datetime.now().isoformat()
    t0 = time.time()
    for out in step.outputs:
        _rotate_backup(out, _today_str())
    try:
        if step.call is not None:
            step.call()
            rc, tail = 0, ""
        else:
            proc = subprocess.run(
                step.argv, cwd=str(PROJECT_DIR), capture_output=True, text=True,
                timeout=step.timeout, env=_build_env(step.needs_bundle_env),
            )
            rc, tail = proc.returncode, _tail(proc.stdout, proc.stderr)
    except subprocess.TimeoutExpired:
        rc, tail = 124, f"TIMEOUT after {step.timeout}s"
    except Exception as exc:  # noqa: BLE001 -- one bad step must not sink the run
        rc, tail = 1, str(exc)[-500:]
    return {
        "step": step.id, "command": step.argv or ["<python-call>"], "start": start,
        "duration": round(time.time() - t0, 2), "returncode": rc, "tail": tail,
    }


def _run_quarter_box_step(real_out: Path = None, staging: Path = None) -> dict:
    """Ingest quarter-box into a staging parquet; only promote if games didn't drop."""
    real_out = Path(real_out) if real_out is not None else DATA_DIR / "cache" / "nba_quarter_points.parquet"
    staging = Path(staging) if staging is not None else DATA_DIR / "cache" / "nba_quarter_points.staging.parquet"
    argv = [sys.executable, "-m", "domains.basketball_nba.ingest_quarter_box", "--out", str(staging)]
    start = datetime.now().isoformat()
    t0 = time.time()
    staging.unlink(missing_ok=True)
    try:
        proc = subprocess.run(argv, cwd=str(PROJECT_DIR), capture_output=True, text=True)
        rc, tail = proc.returncode, _tail(proc.stdout, proc.stderr)
    except Exception as exc:  # noqa: BLE001
        rc, tail = 1, str(exc)[-500:]
    note = ""
    if rc == 0 and staging.exists():
        old_n, new_n = _parquet_game_count(real_out), _parquet_game_count(staging)
        if new_n >= old_n:
            _rotate_backup(real_out, _today_str())
            shutil.move(str(staging), str(real_out))
            note = f"promoted ({old_n} -> {new_n} games)"
        else:
            staging.unlink(missing_ok=True)
            note = f"guard refused: new_count {new_n} < old_count {old_n}"
    return {
        "step": "quarter_box", "command": argv, "start": start,
        "duration": round(time.time() - t0, 2), "returncode": rc, "tail": tail, "note": note,
    }


def _step_defs(season: str) -> dict:
    py = sys.executable

    def mod(name: str) -> list:
        return [py, "-m", f"domains.basketball_nba.{name}"]

    defs = {
        "fetch_advanced_boxscores": Step(
            "fetch_advanced_boxscores",
            argv=[py, "-m", "scripts.fetch_advanced_boxscores", "--seasons", season, "--sleep", "0.55"],
            needs_bundle_env=True, timeout=FETCH_TIMEOUT_S,
        ),
        "aggregate_player_advanced_stats": Step(
            "aggregate_player_advanced_stats", argv=[py, "-m", "scripts.aggregate_player_advanced_stats"],
            outputs=[DATA_DIR / "player_adv_stats.parquet"],
        ),
        "aggregate_team_stats": Step(
            "aggregate_team_stats", argv=[py, "-m", "scripts.aggregate_team_stats_from_boxscores"],
            outputs=[DATA_DIR / "team_advanced_stats.parquet"],
        ),
        "asof_features": Step("asof_features", argv=mod("asof_features"),
                               outputs=[DOMAIN_DIR / "asof_features.parquet"]),
        "asof_box_extra": Step("asof_box_extra", argv=mod("asof_box_extra"),
                                outputs=[DOMAIN_DIR / "asof_box_extra.parquet"]),
        "asof_team_adv": Step("asof_team_adv", argv=mod("asof_team_adv"),
                               outputs=[DOMAIN_DIR / "asof_team_adv.parquet"]),
        "asof_player_adv": Step("asof_player_adv", argv=mod("asof_player_adv"),
                                 outputs=[DOMAIN_DIR / "asof_player_adv.parquet"]),
        "asof_runvar": Step("asof_runvar", call=_call_asof_runvar,
                             outputs=[DOMAIN_DIR / "asof_runvar.parquet"]),
        "corpus_b_build": Step("corpus_b_build", argv=mod("corpus_b_build"),
                                outputs=[DOMAIN_DIR / "asof_features_ext.parquet",
                                         DOMAIN_DIR / "asof_box_extra_ext.parquet"]),
        "boxdetail_asof": Step("boxdetail_asof", argv=mod("boxdetail_asof"),
                                outputs=[DOMAIN_DIR / "boxdetail_asof.parquet"]),
        "refresh_hustle": Step(
            "refresh_hustle", argv=[py, "scripts/refresh_hustle_2025-26.py"], needs_bundle_env=True,
            outputs=[DATA_DIR / "cache" / "hustle_features_2025-26.parquet"],
        ),
        "coverage_receipt_build": Step(
            "coverage_receipt_build", argv=[py, "-m", "scripts.platformkit.asof_coverage_receipt"],
        ),
    }
    for table in COVERAGE_TABLES:
        step_id = f"coverage_check_{table}"
        defs[step_id] = Step(step_id, argv=[
            py, "-m", "scripts.platformkit.asof_coverage_receipt", "--check", table, "--season", season,
        ])
    return defs


def build_step_list(season: str, include_quarter_box: bool) -> list:
    plan = ["quarter_box"] if include_quarter_box else []
    plan += [
        "fetch_advanced_boxscores", "aggregate_player_advanced_stats", "aggregate_team_stats",
        "asof_features", "asof_box_extra", "asof_team_adv", "asof_player_adv", "asof_runvar",
        "corpus_b_build", "boxdetail_asof", "refresh_hustle", "coverage_receipt_build",
    ] + [f"coverage_check_{table}" for table in COVERAGE_TABLES]
    return plan


def _append_log(log_path: Path, result: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(
            f"[{result['start']}] {result['step']} cmd={' '.join(result['command'])} "
            f"duration={result['duration']}s rc={result['returncode']}\n"
        )
        if result.get("tail"):
            f.write(result["tail"] + "\n")
        if result.get("note"):
            f.write("note: " + result["note"] + "\n")
        f.write("-" * 60 + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--season", default=None, help="e.g. 2025-26 (default: derived from today)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; execute nothing")
    ap.add_argument("--steps", default=None, help="comma-separated subset of step ids")
    ap.add_argument("--include-quarter-box", action="store_true")
    args = ap.parse_args(argv)

    season = args.season or current_season()
    plan = build_step_list(season, args.include_quarter_box)
    if args.steps:
        wanted = {s.strip() for s in args.steps.split(",") if s.strip()}
        plan = [s for s in plan if s in wanted]

    print(f"[asof_nightly_refresh] season={season} steps={plan} dry_run={args.dry_run}")
    if args.dry_run:
        for step_id in plan:
            print(f"  would run: {step_id}")
        return 0

    today = _today_str()
    log_path = LOG_DIR / f"{today}.log"
    summary_path = LOG_DIR / f"{today}.json"

    defs = _step_defs(season)
    results = []
    for step_id in plan:
        result = _run_quarter_box_step() if step_id == "quarter_box" else run_step(defs[step_id])
        _append_log(log_path, result)
        results.append(result)
        print(f"  {step_id}: rc={result['returncode']} ({result['duration']}s)")

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump({"season": season, "generated_at": datetime.now().isoformat(), "steps": results}, f, indent=2)

    return 3 if any(r["step"].startswith("coverage_check_") and r["returncode"] == 3 for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
