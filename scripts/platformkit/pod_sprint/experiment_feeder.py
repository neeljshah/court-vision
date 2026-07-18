"""scripts.platformkit.pod_sprint.experiment_feeder -- closes the self-
improving loop: reads verdict/benchmark artifacts already on disk and
APPENDS deterministic, deduped follow-up rows to experiment_queue.jsonl (the
file experiment_loop.sh drains -- see that script's docstring). A verdict
that lands now feeds the pod's own work queue instead of sitting inert.

Three sources scanned, each producing zero or more candidate rows:

  1. data/cache/benchmarks/ingame_nba_newsprior_verdict.json (if it exists)
     -- per-checkpoint verdict_vs_market (the market-facing verdict; that is
     the "gap" the module's own docstring is about):
       CLOSES_GAP        -> replicate on the OTHER train_frac split (same
                             max_games), to check the result isn't a
                             single-split artifact.
       NO_CHANGE/WORSENS -> a feature-ablation candidate row. NOTE: no
                             --drop-features flag exists on
                             ingame_nba_newsprior.py yet (out of this lane's
                             ownership to add) -- the queued cmd is an
                             honest placeholder that will fail fast until
                             that flag is built; the "note" field says so.
       UNDERPOWERED      -> skipped (nothing actionable yet).

  2. scripts/platformkit/benchmarks/crps_market/last_run_state_lag_sensitivity.json
     -- if ANY threshold bucket's paired_delta_mean flips sign vs that
     checkpoint's unfiltered bucket, queue ONE full-1600-game-corpus
     replication row. The finding key is checkpoint/threshold-agnostic
     (just "a flip happened somewhere"), so the id is stable across re-runs
     even as exact magnitudes drift -- "idempotent", never re-queued once
     it's in the queue or ledger.

  3. data/cache/prediction_eval/prediction_eval.json -- any scoreboard
     sport with validated=false -> queue that sport's recalibration
     benchmark: calibration_grid.<sport>_grid for nba/mlb/soccer (the
     modules that exist); tennis has no calibration_grid module, so it
     falls back to the tennis GBM challenger (gbm_tennis_match).

IDs are sha1(source_path|finding_key)[:10], prefixed by a human label --
never embeds a volatile numeric value, so the SAME finding always produces
the SAME id. Dedup checks both the live queue and the done ledger (ledger
path is a CLI param, not hardcoded to the pod's /workspace layout). Max 5
new rows per invocation; each row carries a one-line "note" reason.

CLI:
    python -m scripts.platformkit.pod_sprint.experiment_feeder --dry-run
    python -m scripts.platformkit.pod_sprint.experiment_feeder [--queue PATH] [--ledger PATH] [--max-rows N]
Tests: python -m pytest scripts/platformkit/pod_sprint/test_experiment_feeder.py -q
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

REPO_ROOT = Path(__file__).resolve().parents[3]

_NEWSPRIOR_VERDICT = REPO_ROOT / "data" / "cache" / "benchmarks" / "ingame_nba_newsprior_verdict.json"
_NEWSPRIOR_MODULE = "scripts.platformkit.benchmarks.crps_market.ingame_nba_newsprior"

_STATE_LAG_FILE = (REPO_ROOT / "scripts" / "platformkit" / "benchmarks" / "crps_market"
                    / "last_run_state_lag_sensitivity.json")
_STATE_LAG_MODULE = "scripts.platformkit.benchmarks.crps_market.state_lag_sensitivity"

_PRED_EVAL = REPO_ROOT / "data" / "cache" / "prediction_eval" / "prediction_eval.json"
_CALIB_GRID_SPORTS = {"nba", "mlb", "soccer"}  # scripts.platformkit.calibration_grid.<sport>_grid exists
_RECAL_FALLBACK_MODULE = {"tennis": "scripts.platformkit.models.gbm_tennis_match"}
_RECAL_TIMEOUT_S = {"nba": 14400, "mlb": 21600, "soccer": 14400, "tennis": 14400}

_QUEUE = REPO_ROOT / "scripts" / "platformkit" / "pod_sprint" / "experiment_queue.jsonl"
_DEFAULT_LEDGER = Path(os.environ.get("SPRINT_LOGS", "/workspace/sprint_logs")) / "experiments" / "experiments_done.jsonl"


def _stable_id(label: str, source: str, finding: str) -> str:
    h = hashlib.sha1(f"{source}|{finding}".encode("utf-8")).hexdigest()[:10]
    return f"{label}_{h}"


def _row(id_: str, cmd: str, timeout_s: int, note: str) -> Dict[str, Any]:
    return {"id": id_, "cmd": cmd, "timeout_s": timeout_s, "note": note}


def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _existing_ids(*paths: Path) -> Set[str]:
    """ids already present in the queue and/or the done ledger (jsonl,
    one object per line) -- either path may not exist yet, treated as empty."""
    ids: Set[str] = set()
    for p in paths:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ids.add(json.loads(line)["id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return ids


def _sign(x: float) -> int:
    return 1 if x > 0 else (-1 if x < 0 else 0)


def _find_newsprior_rows(path: Path = _NEWSPRIOR_VERDICT) -> List[Dict[str, Any]]:
    doc = _load_json(path)
    if not doc:
        return []
    train_frac = doc.get("train_frac")
    n_games = doc.get("n_games_considered")
    rows: List[Dict[str, Any]] = []
    for label, cp in doc.get("checkpoints", {}).items():
        verdict = cp.get("verdict_vs_market")
        if verdict == "CLOSES_GAP" and train_frac is not None:
            other = round(1.0 - float(train_frac), 2)
            if other == train_frac:
                other = 0.5
            cmd = f"python -m {_NEWSPRIOR_MODULE}"
            if n_games:
                cmd += f" --max-games {int(n_games)}"
            cmd += f" --train-frac {other}"
            rows.append(_row(
                _stable_id("newsprior_replicate", str(path), f"replicate|{label}|{other}"),
                cmd, 21600,
                f"newsprior CLOSES_GAP vs market at {label} (train_frac={train_frac}) -- "
                f"replicate on train_frac={other} to rule out a single-split artifact",
            ))
        elif verdict in ("NO_CHANGE", "WORSENS"):
            cmd = (f"python -m {_NEWSPRIOR_MODULE} --drop-features "
                   "star_out_home,star_out_away,n_starters_changed_home,n_starters_changed_away")
            rows.append(_row(
                _stable_id("newsprior_ablate", str(path), f"ablate|{label}"),
                cmd, 21600,
                f"newsprior {verdict} vs market at {label} -- ablate noisy actual-played-proxy "
                "features vs clean schedule features; --drop-features flag not yet built on "
                "ingame_nba_newsprior.py, this row is a placeholder until it lands",
            ))
    return rows


def _find_state_lag_rows(path: Path = _STATE_LAG_FILE) -> List[Dict[str, Any]]:
    doc = _load_json(path)
    if not doc:
        return []
    flipped = False
    for cp in doc.get("checkpoints", {}).values():
        base = cp.get("unfiltered", {}).get("paired_delta_mean")
        if base is None or _sign(base) == 0:
            continue
        for bucket in cp.get("excluding_lag_over_threshold", {}).values():
            d = bucket.get("paired_delta_mean")
            if d is not None and _sign(d) != 0 and _sign(d) != _sign(base):
                flipped = True
                break
        if flipped:
            break
    if not flipped:
        return []
    return [_row(
        _stable_id("state_lag_full_corpus", str(path), "sign_flip_detected"),
        f"python -m {_STATE_LAG_MODULE} --max-games 1600", 21600,
        "state_lag_sensitivity: a threshold bucket flips the unfiltered paired-delta sign -- "
        "replicate at the full 1600-game corpus to rule out a small-n artifact",
    )]


def _recal_cmd(sport: str) -> Optional[str]:
    if sport in _CALIB_GRID_SPORTS:
        return f"python -m scripts.platformkit.calibration_grid.{sport}_grid --model-per-bucket 12"
    module = _RECAL_FALLBACK_MODULE.get(sport)
    return f"python -m {module}" if module else None


def _find_prediction_eval_rows(path: Path = _PRED_EVAL) -> List[Dict[str, Any]]:
    doc = _load_json(path)
    if not doc:
        return []
    rows: List[Dict[str, Any]] = []
    for entry in doc.get("scoreboard", []):
        if entry.get("validated") is not False:
            continue
        sport = entry.get("sport")
        cmd = _recal_cmd(sport) if sport else None
        if not cmd:
            continue
        rows.append(_row(
            _stable_id(f"recal_{sport}", str(path), "validated_false"),
            cmd, _RECAL_TIMEOUT_S.get(sport, 14400),
            f"prediction_eval: {sport} validated=false (value={entry.get('value')} vs "
            f"reference={entry.get('reference')}) -- queue recalibration benchmark",
        ))
    return rows


def find_new_rows(
    existing_ids: Set[str],
    max_rows: int = 5,
    newsprior_path: Path = _NEWSPRIOR_VERDICT,
    state_lag_path: Path = _STATE_LAG_FILE,
    pred_eval_path: Path = _PRED_EVAL,
) -> List[Dict[str, Any]]:
    candidates = (
        _find_newsprior_rows(newsprior_path)
        + _find_state_lag_rows(state_lag_path)
        + _find_prediction_eval_rows(pred_eval_path)
    )
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for row in candidates:
        if row["id"] in existing_ids or row["id"] in seen:
            continue
        seen.add(row["id"])
        out.append(row)
        if len(out) >= max_rows:
            break
    return out


def append_rows(rows: List[Dict[str, Any]], queue_path: Path) -> None:
    if not rows:
        return
    with queue_path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Append follow-up experiment rows from verdict artifacts")
    ap.add_argument("--queue", type=Path, default=_QUEUE)
    ap.add_argument("--ledger", type=Path, default=_DEFAULT_LEDGER)
    ap.add_argument("--max-rows", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true", help="print candidate rows, do not append")
    args = ap.parse_args(argv)

    existing = _existing_ids(args.queue, args.ledger)
    rows = find_new_rows(existing, args.max_rows)
    for row in rows:
        print(json.dumps(row, ensure_ascii=True))
    if not args.dry_run:
        append_rows(rows, args.queue)
    print(f"# {len(rows)} row(s) {'would be' if args.dry_run else ''} appended".replace("  ", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
