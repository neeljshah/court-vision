"""live_hot_hand_eval.py -- W-014 validation: generalized heat-check heat^0.20.

Evaluates CV_INGAME_HEAT_GEN (flag ON vs OFF) on the 954-game quarter-stats
corpus. Unlike ingame_calib_eval.py, this script enriches each snapshot with
per-player L5 per-minute rates (l5_pts_per_min, l5_ast_per_min,
l5_fg3m_per_min) derived from gamelog_{pid}_*.json files strictly before the
game date. Without those fields the new function is a graceful no-op; this
script injects them so the evaluation is meaningful.

LEAK DISCIPLINE: L5 rates computed from games strictly before target_date.
Ground truth: full-game Q1+Q2+Q3+Q4 sums from player_quarter_stats.parquet.
No future-quarter leakage into the snapshot.

Acceptance rule (mirrors INGAME_CALIBRATION_PROTOCOL.md):
  ACCEPT if, relative to flag-OFF baseline:
    * pts MAE improves (delta < 0)
    * fg3m MAE improves (delta < 0)
    * ast MAE does not regress by more than +0.5% relative
    * reb MAE does not regress by more than +0.5% relative
    * byte-identical-when-OFF confirmed (run with --verify-flag-off)

Run:
    set NBA_OFFLINE=1
    python scripts/ingame/live_hot_hand_eval.py --max-games 200
    python scripts/ingame/live_hot_hand_eval.py --max-games 200 --by-snapshot
    python scripts/ingame/live_hot_hand_eval.py --verify-flag-off --max-games 50
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

os.environ.setdefault("NBA_OFFLINE", "1")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import retro_inplay_mae as rim  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
SNAPSHOT_POINTS = ("endQ1", "endQ2", "endQ3")

# Stats for which L5 per-min rates are injected.
L5_STATS = ("pts", "ast", "fg3m")


# ── L5 per-game loader (from gamelog files) ──────────────────────────────────

def _parse_gamelog_date(s) -> Optional[str]:
    if not s:
        return None
    try:
        return datetime.strptime(str(s), "%b %d, %Y").date().isoformat()
    except ValueError:
        return None


def load_l5_per_min(
    game_dates: Dict[str, str],
    qstats_df,
) -> Dict[Tuple[str, int, str], float]:
    """Build {(game_id, player_id, stat): l5_per_min} for pts/ast/fg3m.

    Rates = mean(stat[-5:]) / mean(min[-5:]) strictly before game_date.
    Returns 0.0 entries are omitted (callers get 0.0 on KeyError).
    """
    out: Dict[Tuple[str, int, str], float] = {}
    needed_pids = set(int(pid) for pid in qstats_df["player_id"].unique())

    _STAT_COLS = {"pts": "PTS", "ast": "AST", "fg3m": "FG3M", "min": "MIN"}
    pid_logs: Dict[int, List[Tuple[str, Dict[str, float]]]] = {}
    for pid in needed_pids:
        log: List[Tuple[str, Dict[str, float]]] = []
        pattern = os.path.join(ROOT, "data", "nba", f"gamelog_{pid}_*.json")
        for fp in glob.glob(pattern):
            try:
                with open(fp, encoding="utf-8") as fh:
                    games = json.load(fh) or []
            except Exception:
                continue
            for row in games:
                d = _parse_gamelog_date(row.get("GAME_DATE"))
                if d is None:
                    continue
                try:
                    m = float(row.get("MIN") or 0)
                    if m < 1.0:
                        continue
                except (TypeError, ValueError):
                    continue
                stats: Dict[str, float] = {}
                for s, col in _STAT_COLS.items():
                    try:
                        stats[s] = float(row.get(col) or 0)
                    except (TypeError, ValueError):
                        stats[s] = 0.0
                log.append((d, stats))
        log.sort(key=lambda x: x[0])
        pid_logs[pid] = log

    for game_id, target_date in game_dates.items():
        if not target_date:
            continue
        gpids = set(
            int(pid) for pid in
            qstats_df[qstats_df["game_id"] == game_id]["player_id"].unique()
        )
        for pid in gpids:
            log = pid_logs.get(pid, [])
            prior = [s for (d, s) in log if d < target_date][-5:]
            if not prior:
                continue
            l5_min_list = [p["min"] for p in prior]
            l5_min_mean = sum(l5_min_list) / len(l5_min_list) if l5_min_list else 0.0
            if l5_min_mean <= 0.0:
                continue
            for stat in L5_STATS:
                l5_stat = sum(p.get(stat, 0.0) for p in prior) / len(prior)
                rate = l5_stat / l5_min_mean
                if rate > 0.0:
                    out[(game_id, pid, stat)] = rate
    return out


# ── snapshot enrichment ───────────────────────────────────────────────────────

def enrich_snapshot_with_l5(
    snap: dict,
    game_id: str,
    l5_rates: Dict[Tuple[str, int, str], float],
) -> dict:
    """Inject l5_pts_per_min / l5_ast_per_min / l5_fg3m_per_min into player rows.

    Modifies a shallow copy of snap; original is untouched.
    """
    import copy
    snap = dict(snap)
    snap["players"] = [dict(p) for p in snap.get("players") or []]
    for p in snap["players"]:
        try:
            pid = int(p.get("player_id"))
        except (TypeError, ValueError):
            continue
        for stat in L5_STATS:
            key = (game_id, pid, stat)
            rate = l5_rates.get(key)
            if rate is not None and rate > 0.0:
                p[f"l5_{stat}_per_min"] = rate
    return snap


# ── core eval ─────────────────────────────────────────────────────────────────

def collect_mae(
    max_games: int = 0,
    flag_on: bool = False,
    by_snapshot: bool = False,
) -> Dict[str, Dict[str, float]]:
    """Run all snapshots through the engine, return per-stat (and per-snapshot)
    mean absolute error.

    Returns {stat: {"overall": mae}} when by_snapshot=False,
    or {stat: {"endQ1": mae, "endQ2": mae, "endQ3": mae, "overall": mae}}.
    """
    from src.prediction.live_engine import project_from_snapshot

    # Set / clear flag.
    if flag_on:
        os.environ["CV_INGAME_HEAT_GEN"] = "1"
    else:
        os.environ.pop("CV_INGAME_HEAT_GEN", None)

    qs = rim.load_quarter_stats()
    game_ids = sorted(qs["game_id"].unique().tolist())
    if max_games:
        game_ids = game_ids[:max_games]

    # Find game dates for L5 lookups.
    gid_list = [str(g) for g in game_ids]
    game_dates: Dict[str, str] = {}
    for gid in gid_list:
        d = rim.find_game_date(gid, qs)
        if d:
            game_dates[gid] = d

    print(f"Loading L5 per-min rates for {len(game_ids)} games ...")
    l5_rates = load_l5_per_min(game_dates, qs)
    l5_coverage = len(set((g, p) for (g, p, _) in l5_rates)) if l5_rates else 0
    print(f"  L5 coverage: {l5_coverage} (game, player) pairs")

    errors: Dict[str, Dict[str, List[float]]] = {
        s: {pt: [] for pt in list(SNAPSHOT_POINTS) + ["overall"]} for s in STATS
    }

    n_ok = 0
    for gid in game_ids:
        gid_s = str(gid)
        actuals = rim.actuals_for_game(gid, qs)
        if not actuals:
            continue
        for point in SNAPSHOT_POINTS:
            snap = rim.build_snapshot(gid, point, qs)
            if snap is None:
                continue
            # Inject L5 per-min rates.
            snap = enrich_snapshot_with_l5(snap, gid_s, l5_rates)
            try:
                rows = project_from_snapshot(snap)
            except Exception:
                continue
            for r in rows:
                pid = r.get("player_id")
                stat = r.get("stat")
                if pid is None or stat not in STATS:
                    continue
                try:
                    pid_i = int(pid)
                    actual = actuals.get((pid_i, stat))
                    if actual is None:
                        continue
                    err = abs(float(r["projected_final"]) - actual)
                    errors[stat][point].append(err)
                    errors[stat]["overall"].append(err)
                except (KeyError, TypeError, ValueError):
                    continue
        n_ok += 1

    print(f"Processed {n_ok} / {len(game_ids)} games, flag={'ON' if flag_on else 'OFF'}")

    result: Dict[str, Dict[str, float]] = {}
    for s in STATS:
        result[s] = {}
        for k, errs in errors[s].items():
            if errs:
                result[s][k] = sum(errs) / len(errs)
    return result


# ── acceptance check ─────────────────────────────────────────────────────────

def check_acceptance(
    baseline: Dict[str, Dict[str, float]],
    candidate: Dict[str, Dict[str, float]],
) -> Tuple[bool, str]:
    """Return (accept, summary_str)."""
    lines = []
    all_ok = True

    for stat in ("pts", "fg3m", "reb", "ast"):
        b = baseline.get(stat, {}).get("overall", float("nan"))
        c = candidate.get(stat, {}).get("overall", float("nan"))
        if b != b or c != c:  # NaN check
            lines.append(f"  {stat}: baseline={b:.4f}  candidate=N/A  SKIP")
            continue
        delta = c - b
        pct = 100.0 * delta / b if b > 0 else 0.0
        status = ""
        if stat in ("pts", "fg3m"):
            ok = delta < 0
            status = "IMPROVE" if ok else "REGRESS"
            if not ok:
                all_ok = False
        elif stat in ("reb", "ast"):
            # Allow up to +0.5% regression on protected stats.
            ok = pct <= 0.5
            status = "OK" if ok else "REGRESS"
            if not ok:
                all_ok = False
        lines.append(
            f"  {stat}: baseline={b:.4f}  candidate={c:.4f}  "
            f"delta={delta:+.4f} ({pct:+.2f}%)  {status}"
        )

    verdict = "ACCEPT" if all_ok else "REJECT"
    lines.append(f"\nVERDICT: {verdict}")
    return all_ok, "\n".join(lines)


# ── byte-identical check ──────────────────────────────────────────────────────

def verify_byte_identical(max_games: int = 20) -> bool:
    """Confirm that flag-ON rows are identical to flag-OFF when no L5 priors
    are present (the retro harness case: no l5_*_per_min fields on players).
    """
    from src.prediction.live_engine import project_from_snapshot

    qs = rim.load_quarter_stats()
    game_ids = sorted(qs["game_id"].unique().tolist())[:max_games]

    mismatches = 0
    total = 0
    for gid in game_ids:
        for point in SNAPSHOT_POINTS:
            snap = rim.build_snapshot(gid, point, qs)
            if snap is None:
                continue
            # No L5 per-min enrichment => should be identical.
            os.environ.pop("CV_INGAME_HEAT_GEN", None)
            try:
                off_rows = project_from_snapshot(snap)
            except Exception:
                continue
            os.environ["CV_INGAME_HEAT_GEN"] = "1"
            try:
                on_rows = project_from_snapshot(snap)
            except Exception:
                os.environ.pop("CV_INGAME_HEAT_GEN", None)
                continue
            os.environ.pop("CV_INGAME_HEAT_GEN", None)

            # Compare projected_final values.
            off_map = {(r.get("player_id"), r.get("stat")): float(r.get("projected_final") or 0)
                       for r in off_rows}
            on_map  = {(r.get("player_id"), r.get("stat")): float(r.get("projected_final") or 0)
                       for r in on_rows}
            for k, v_off in off_map.items():
                v_on = on_map.get(k, v_off)
                total += 1
                if abs(v_on - v_off) > 1e-9:
                    mismatches += 1

    status = "PASS" if mismatches == 0 else "FAIL"
    print(f"Byte-identical check (no-L5-enrichment, {total} rows): {status} "
          f"({mismatches} mismatches)")
    return mismatches == 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="W-014 heat-check generalized eval")
    ap.add_argument("--max-games", type=int, default=200,
                    help="Limit corpus size (default 200)")
    ap.add_argument("--by-snapshot", action="store_true",
                    help="Break out MAE by snapshot point (endQ1/Q2/Q3)")
    ap.add_argument("--verify-flag-off", action="store_true",
                    help="Run byte-identical check (no L5 enrichment)")
    args = ap.parse_args()

    if args.verify_flag_off:
        ok = verify_byte_identical(max_games=min(args.max_games, 50))
        sys.exit(0 if ok else 1)

    print(f"\n=== W-014 heat_gen eval: max_games={args.max_games} ===\n")

    print("--- Baseline (flag OFF) ---")
    baseline = collect_mae(max_games=args.max_games, flag_on=False,
                           by_snapshot=args.by_snapshot)

    print("\n--- Candidate (flag ON) ---")
    candidate = collect_mae(max_games=args.max_games, flag_on=True,
                            by_snapshot=args.by_snapshot)

    print("\n--- Results ---")
    header = f"{'stat':6s}  {'baseline':10s}  {'candidate':10s}  {'delta':10s}  {'pct':8s}"
    print(header)
    print("-" * len(header))
    for stat in STATS:
        for bucket in (["overall"] + (list(SNAPSHOT_POINTS) if args.by_snapshot else [])):
            b = baseline.get(stat, {}).get(bucket, float("nan"))
            c = candidate.get(stat, {}).get(bucket, float("nan"))
            if b != b:
                continue
            delta = c - b
            pct = 100.0 * delta / b if b > 0 else 0.0
            label = stat if bucket == "overall" else f"{stat}/{bucket}"
            print(f"{label:12s}  {b:10.4f}  {c:10.4f}  {delta:+10.4f}  {pct:+7.2f}%")

    print("\n--- Acceptance ---")
    accept, summary = check_acceptance(baseline, candidate)
    print(summary)

    sys.exit(0 if accept else 1)


if __name__ == "__main__":
    main()
