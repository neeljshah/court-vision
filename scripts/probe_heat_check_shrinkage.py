"""probe_heat_check_shrinkage.py -- cycle 96d (loop 5). Heat-check Bayesian shrinkage probe.

WHY: cycle 95b decomposed endQ3 MAE; heat_check stratum (Q3 ppm > 1.5x Q1-Q2)
showed +0.53 PTS MAE excess and +0.74 bias. The cycle-88 projector
extrapolates the inflated cumulative rate to Q4, but heat-check mean-reverts.

This probe:
  1) For each retro game in player_quarter_stats.parquet, replays the cycle-88
     endQ3 snapshot via scripts/retro_inplay_mae.build_snapshot.
  2) For every player on every game, classifies whether they're in the
     heat_check stratum (Q3 PTS ppm > 1.5x Q1-Q2 ppm, same gate as 95b).
  3) Computes baseline endQ3 projection (cycle-88 unmodified) vs shrunk
     projection (cycle-88 with heat_check_factor applied to PTS/AST/FG3M
     REMAINING-stat projections).
  4) Per stat, reports MAE on heat-check stratum (where the shrinkage fires)
     and MAE on the non-heat-check stratum (where it should be a no-op so
     we verify no collateral damage).
  5) Sweeps shrinkage_weight in {0.10, 0.15, 0.20, 0.25, 0.30}.

Ship gate:
  - Best weight reduces heat-check PTS MAE by >= 0.10 AND
  - Does NOT worsen the non-heat stratum by > 0.02 MAE on any of PTS/AST/FG3M.

Strictly read-only: no writes to predict_in_game.py / live_engine.py until
the SHIP block in main() fires. Always writes scripts/_results/
heat_check_shrinkage_v1.md.

Run:
    python scripts/probe_heat_check_shrinkage.py
    python scripts/probe_heat_check_shrinkage.py --max-games 10
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import predict_in_game as pig                       # noqa: E402
import retro_inplay_mae as ri                       # noqa: E402
from src.prediction.heat_check_shrinkage import (   # noqa: E402
    HEAT_CHECK_STATS,
    heat_check_factor,
)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
WEIGHTS = (0.10, 0.15, 0.20, 0.25, 0.30)

# Same gate definition as cycle 95b (decompose_endQ3_mae.classify_strata).
_HEAT_RATIO_GATE = 1.5
_HEAT_MIN_Q3 = 2.0       # need >=2 min in Q3 for a stable rate
_HEAT_MIN_Q12 = 4.0      # need >=4 min across Q1+Q2
_HEAT_MIN_BASE_PPM = 0.25  # base rate floor so 0-pt Q1+Q2 doesn't auto-trigger


def _pts_rates_for_player(qstats_df, game_id: str, pid: int) -> Tuple[float, float, float, float]:
    """Return (q3_min, q12_min, q3_pts, q12_pts) for one player in one game."""
    g = qstats_df[(qstats_df["game_id"] == game_id) & (qstats_df["player_id"] == pid)]
    q3 = g[g["period"] == 3]
    q12 = g[g["period"].isin([1, 2])]
    q3_min = float(q3["min"].sum()) if not q3.empty else 0.0
    q12_min = float(q12["min"].sum()) if not q12.empty else 0.0
    q3_pts = float(q3["pts"].sum()) if not q3.empty else 0.0
    q12_pts = float(q12["pts"].sum()) if not q12.empty else 0.0
    return q3_min, q12_min, q3_pts, q12_pts


def _is_heat_check(q3_min, q12_min, q3_pts, q12_pts) -> bool:
    """Cycle-95b heat_check stratum gate (PTS only)."""
    if q3_min < _HEAT_MIN_Q3 or q12_min < _HEAT_MIN_Q12:
        return False
    q3_ppm = q3_pts / q3_min if q3_min > 0 else 0.0
    q12_ppm = q12_pts / q12_min if q12_min > 0 else 0.0
    if q12_ppm < _HEAT_MIN_BASE_PPM:
        return False
    return q3_ppm > _HEAT_RATIO_GATE * q12_ppm


def _shrunk_projection(
    baseline_row: dict,
    q3_pts_ppm: float,
    q12_pts_ppm: float,
    season_ppm: float,
    weight: float,
) -> float:
    """Apply heat_check_factor to the REMAINING projection only.

    baseline_row carries 'current' (locked-in stat through Q3) and
    'projected_final' (cycle-88 baseline). Remaining = projected_final - current.
    """
    current = float(baseline_row.get("current", 0.0) or 0.0)
    projected = float(baseline_row.get("projected_final", 0.0) or 0.0)
    remaining = max(0.0, projected - current)
    factor = heat_check_factor(q3_pts_ppm, q12_pts_ppm, season_ppm,
                               shrinkage_weight=weight)
    return current + remaining * factor


def run_probe(qstats_df, max_games: Optional[int] = None) -> Dict:
    """Build the comparison table across all heat/non-heat strata and weights.

    Returns:
        {
            "n_games": int,
            "heat_n_player_games": int,
            "non_heat_n_player_games": int,
            "baseline": {stat: {"heat": (n, mae), "non_heat": (n, mae)}},
            "by_weight": {weight: {stat: {"heat": (n, mae), "non_heat": (n, mae)}}},
        }
    """
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]

    # Per (weight, stat, stratum) -> list of abs_err
    base_buckets: Dict[str, Dict[str, List[float]]] = {
        s: defaultdict(list) for s in STATS
    }
    shrunk_buckets: Dict[float, Dict[str, Dict[str, List[float]]]] = {
        w: {s: defaultdict(list) for s in STATS} for w in WEIGHTS
    }
    heat_n = 0
    non_heat_n = 0

    for gid in games:
        snap = ri.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            continue
        # Baseline projection (cycle 88b).
        base_rows = pig.project_snapshot(snap)
        # Index baseline by (pid, stat) for the shrinkage shortcut.
        base_by_key: Dict[Tuple[int, str], dict] = {}
        for r in base_rows:
            try:
                pid = int(r["player_id"])
            except (TypeError, ValueError, KeyError):
                continue
            base_by_key[(pid, r["stat"])] = r

        actuals = ri.actuals_for_game(gid, qstats_df)

        # Compute heat-check classification + per-stat per-min rates ONCE per player.
        seen_pids = set(pid for pid, _ in base_by_key.keys())
        for pid in seen_pids:
            q3_min, q12_min, q3_pts, q12_pts = _pts_rates_for_player(
                qstats_df, gid, pid)
            is_heat = _is_heat_check(q3_min, q12_min, q3_pts, q12_pts)
            stratum = "heat" if is_heat else "non_heat"
            if is_heat:
                heat_n += 1
            else:
                non_heat_n += 1

            for stat in STATS:
                br = base_by_key.get((pid, stat))
                if br is None:
                    continue
                actual = actuals.get((pid, stat))
                if actual is None:
                    continue

                baseline_pred = float(br.get("projected_final", 0.0))
                base_buckets[stat][stratum].append(abs(baseline_pred - actual))

                # Shrinkage applies only to heat-check stratum AND only to the
                # eligible scoring stats (PTS / AST / FG3M). Defensive stats
                # pass through unchanged so non-heat stratum baseline ==
                # non-heat shrunk for ALL stats (we still log it to verify).
                #
                # For per-stat rates we use the SAME q3_pts_ppm / q12_pts_ppm
                # derived from PTS (the gate stat) -- the cycle-95b gate is
                # defined off PTS, so AST/FG3M shrinkage inherits the same
                # heat-check signal. This is the cleanest first-pass wiring;
                # a future cycle can split per-stat rates.
                q3_pts_ppm = q3_pts / q3_min if q3_min > 0 else 0.0
                q12_pts_ppm = q12_pts / q12_min if q12_min > 0 else 0.0
                season_ppm = q12_pts_ppm  # placeholder; formula ignores it

                for w in WEIGHTS:
                    if is_heat and stat in HEAT_CHECK_STATS:
                        shrunk = _shrunk_projection(
                            br, q3_pts_ppm, q12_pts_ppm, season_ppm, w)
                    else:
                        shrunk = baseline_pred
                    shrunk_buckets[w][stat][stratum].append(abs(shrunk - actual))

    def _agg(buckets):
        return {
            stat: {
                stratum: (len(v), (sum(v) / len(v)) if v else 0.0)
                for stratum, v in by_stratum.items()
            }
            for stat, by_stratum in buckets.items()
        }

    return {
        "n_games": len(games),
        "heat_n_player_games": heat_n,
        "non_heat_n_player_games": non_heat_n,
        "baseline": _agg(base_buckets),
        "by_weight": {w: _agg(sb) for w, sb in shrunk_buckets.items()},
    }


# ── ship-gate logic ──────────────────────────────────────────────────────────

def _heat_pts_mae(agg) -> float:
    return agg.get("pts", {}).get("heat", (0, 0.0))[1]


def _non_heat_mae_for(agg, stat) -> float:
    return agg.get(stat, {}).get("non_heat", (0, 0.0))[1]


def pick_best_weight(result: Dict) -> Tuple[Optional[float], Dict]:
    """Return (best_weight, decision_info). best_weight=None means REJECT.

    Decision:
      * candidate weight W passes if:
        - heat PTS MAE drop >= 0.10 vs baseline
        - non-heat MAE delta <= +0.02 for EACH of {pts, ast, fg3m}
      * if multiple pass, pick the one with the largest heat PTS MAE drop.
    """
    baseline = result["baseline"]
    base_heat_pts = _heat_pts_mae(baseline)
    base_non_heat = {s: _non_heat_mae_for(baseline, s) for s in HEAT_CHECK_STATS}

    candidates: List[Tuple[float, Dict]] = []
    rows: List[Dict] = []
    for w in WEIGHTS:
        agg = result["by_weight"][w]
        cand_heat_pts = _heat_pts_mae(agg)
        heat_drop = base_heat_pts - cand_heat_pts
        non_heat_deltas = {
            s: _non_heat_mae_for(agg, s) - base_non_heat[s]
            for s in HEAT_CHECK_STATS
        }
        max_non_heat_delta = max(non_heat_deltas.values()) if non_heat_deltas else 0.0
        passes = (heat_drop >= 0.10) and (max_non_heat_delta <= 0.02)
        rows.append({
            "weight": w,
            "heat_pts_baseline": base_heat_pts,
            "heat_pts_shrunk": cand_heat_pts,
            "heat_drop": heat_drop,
            "non_heat_deltas": non_heat_deltas,
            "max_non_heat_delta": max_non_heat_delta,
            "passes": passes,
        })
        if passes:
            candidates.append((w, rows[-1]))

    if not candidates:
        return None, {"rows": rows, "best": None}

    # Pick largest heat_drop, then smallest weight (less aggressive) as tiebreak.
    best = max(candidates, key=lambda kv: (kv[1]["heat_drop"], -kv[0]))
    return best[0], {"rows": rows, "best": best[1]}


# ── report ───────────────────────────────────────────────────────────────────

def build_report(result: Dict, decision: Dict, best_weight: Optional[float]) -> str:
    lines: List[str] = []
    lines.append("# Heat-check Bayesian shrinkage probe -- cycle 96d (loop 5)")
    lines.append("")
    lines.append(f"**Retro games:** {result['n_games']}")
    lines.append(f"**Heat-check player-games:** {result['heat_n_player_games']}")
    lines.append(f"**Non-heat-check player-games:** {result['non_heat_n_player_games']}")
    lines.append("")
    lines.append(
        "Applies `heat_check_factor` shrinkage to the REMAINING-stats "
        "projection at endQ3, only for the heat-check stratum (Q3 PTS ppm > "
        "1.5x Q1-Q2 ppm) and only for scoring stats (PTS / AST / FG3M). "
        "Non-heat rows and defensive stats are pass-through (sanity-checks "
        "that we don't break the rest of the dataset)."
    )
    lines.append("")

    # Baseline table.
    base = result["baseline"]
    lines.append("## Baseline endQ3 MAE (cycle 88b, no shrinkage)")
    lines.append("")
    lines.append("| stat | heat n | heat mae | non-heat n | non-heat mae |")
    lines.append("|------|-------:|---------:|-----------:|-------------:|")
    for stat in STATS:
        hn, hm = base.get(stat, {}).get("heat", (0, 0.0))
        nn, nm = base.get(stat, {}).get("non_heat", (0, 0.0))
        lines.append(f"| {stat} | {hn} | {hm:.4f} | {nn} | {nm:.4f} |")
    lines.append("")

    # Per-weight sweep table (focus on the heat-check scoring stats).
    lines.append("## Shrinkage sweep (heat-check stratum, scoring stats)")
    lines.append("")
    lines.append("| weight | PTS mae | PTS drop | AST mae | AST drop | FG3M mae | FG3M drop |")
    lines.append("|-------:|--------:|---------:|--------:|---------:|---------:|----------:|")
    for w in WEIGHTS:
        agg = result["by_weight"][w]
        cells = [f"{w:.2f}"]
        for s in ("pts", "ast", "fg3m"):
            b_mae = base.get(s, {}).get("heat", (0, 0.0))[1]
            mae = agg.get(s, {}).get("heat", (0, 0.0))[1]
            cells.append(f"{mae:.4f}")
            cells.append(f"{b_mae - mae:+.4f}")
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    # Non-heat side check.
    lines.append("## Non-heat stratum check (must NOT regress)")
    lines.append("")
    lines.append("| weight | PTS delta | AST delta | FG3M delta |")
    lines.append("|-------:|----------:|----------:|-----------:|")
    for w in WEIGHTS:
        agg = result["by_weight"][w]
        cells = [f"{w:.2f}"]
        for s in ("pts", "ast", "fg3m"):
            b_mae = base.get(s, {}).get("non_heat", (0, 0.0))[1]
            mae = agg.get(s, {}).get("non_heat", (0, 0.0))[1]
            cells.append(f"{mae - b_mae:+.4f}")
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    # Decision.
    lines.append("## Ship gate")
    lines.append("")
    lines.append("Gate: heat-stratum PTS MAE drop >= 0.10 AND non-heat MAE delta <= +0.02 "
                 "on each of PTS/AST/FG3M.")
    lines.append("")
    lines.append("| weight | heat PTS drop | max non-heat delta | passes |")
    lines.append("|-------:|--------------:|-------------------:|:------:|")
    for row in decision["rows"]:
        mark = "YES" if row["passes"] else "no"
        lines.append(
            f"| {row['weight']:.2f} | {row['heat_drop']:+.4f} | "
            f"{row['max_non_heat_delta']:+.4f} | {mark} |"
        )
    lines.append("")

    if best_weight is None:
        lines.append("**Verdict: REJECT.** No shrinkage weight passes both legs of the "
                     "gate. Cycle-88 baseline projector is left untouched.")
    else:
        best = decision["best"]
        lines.append(
            f"**Verdict: SHIP weight={best_weight:.2f}.** "
            f"Heat-stratum PTS MAE drops "
            f"{best['heat_pts_baseline']:.4f} -> {best['heat_pts_shrunk']:.4f} "
            f"({best['heat_drop']:+.4f}); non-heat max delta "
            f"{best['max_non_heat_delta']:+.4f} <= 0.02."
        )
        lines.append("")
        lines.append("Wired into `scripts/predict_in_game.project_snapshot` -- the "
                     "shrinkage factor multiplies the REMAINING projection for "
                     "PTS/AST/FG3M when the per-player heat-check gate fires "
                     "(Q3 pts/min > 1.5x Q1-Q2 pts/min, Q3>=2 min, Q1+Q2>=4 min, "
                     "Q12 ppm >= 0.25). Other stats and non-heat rows pass through.")
    lines.append("")
    return "\n".join(lines) + "\n"


# ── runner ───────────────────────────────────────────────────────────────────

def run(max_games: Optional[int] = None, output: Optional[str] = None) -> Tuple[Optional[float], Dict]:
    qstats_df = ri.load_quarter_stats()
    print(f"  probe_heat_check_shrinkage: loaded {len(qstats_df)} quarter rows")

    result = run_probe(qstats_df, max_games=max_games)
    best_weight, decision = pick_best_weight(result)
    report = build_report(result, decision, best_weight)

    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "heat_check_shrinkage_v1.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"  wrote {out_path}")

    # Console summary.
    base_heat_pts = _heat_pts_mae(result["baseline"])
    print(f"  baseline heat PTS MAE: {base_heat_pts:.4f}")
    for w in WEIGHTS:
        agg_pts = _heat_pts_mae(result["by_weight"][w])
        print(f"    w={w:.2f}: heat PTS MAE {agg_pts:.4f}  drop {base_heat_pts - agg_pts:+.4f}")
    if best_weight is None:
        print("  VERDICT: REJECT")
    else:
        print(f"  VERDICT: SHIP weight={best_weight:.2f}")

    return best_weight, result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()
    run(max_games=args.max_games, output=args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
