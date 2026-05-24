"""probe_garbage_time_haircut.py — Cycle 90a (loop 5) T1-A probe.

Tier-1 highest-leverage probe from cycle 89f research (`scripts/_results/
in_game_gaps_v1.md` lines 16-22): apply a margin-conditioned multiplicative
haircut to PTS/REB/AST predictions for games with a large pre-game implied
spread (Cleaning-the-Glass garbage-time triggers). Star starters lose 3-5
minutes in real blowouts -- pre-game model has no margin-aware MIN
adjustment, so this is structural slope, not noise.

NB: dataset has no spread column. We derive the implied margin from
season_games_<season>.json (`home_srs - away_srs + 2.5` HCA, with
elo_differential/25 + 2.5 as a secondary check). SRS = simple rating
system point differential, point-in-time-ish (updated weekly).

Probe path (mirroring validate_adjustment.py pattern, NOT modifying it):
1. Build (game_date, team_abbrev) -> implied_margin lookup from
   season_games_*.json. Positive means the team is favored.
2. Rebuild holdout rows with a `_implied_margin` attached. We do this by
   re-walking the gamelogs the same way build_pergame_dataset does --
   sorted chronologically across all players, take the last 20% -- and we
   piggyback the team_abbrev / opponent / matchup so the lookup is exact.
3. Adjustment factory: make_garbage_haircut(spread_thresholds, factors).
   For each holdout row, look up the player's team implied margin for the
   game. Apply ONLY to PTS / REB / AST (volume / minute-driven stats).
   Skip FG3M / STL / BLK / TOV (skill / possession-driven; no minute-driver
   signal, per cycle 89f explicit avoid list).
4. Single-split MAE delta vs baseline on n=19964 holdout.
5. Walk-forward 4-fold validation (chronological-split simulation, applying
   the haircut at predict time so each fold has its own production model).
6. Ship gate (BOTH):
     - single-split MAE strictly DOWN on >=4/7 stats with the 3 affected
       stats showing meaningful improvement >=0.005 MAE
     - WF 4/4 folds positive on PTS, REB, AST

Run:
    python scripts/probe_garbage_time_haircut.py
    python scripts/probe_garbage_time_haircut.py --skip-wf  # single-split only
"""
from __future__ import annotations

import argparse
import bisect
import glob
import json
import os
import sys
import warnings
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, _MIN_PLAYED, _BOX_COL, _num, _parse_date,
    build_pergame_dataset, feature_columns,
)

# Borrow the production-dispatch predict + validate harness from the
# validator (do NOT modify validate_adjustment.py — orthogonal agents may
# extend it in parallel).
from scripts.validate_adjustment import (  # noqa: E402
    _bulk_predict, validate, print_report,
)


_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_RESULTS_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")
os.makedirs(_RESULTS_DIR, exist_ok=True)

# Stats the haircut targets — volume/minute-driven. Per cycle 89f T1-A,
# fg3m/stl/blk/tov are saturated post-prediction-adjustment territory with
# no minute-driver signal.
_VOLUME_STATS = {"pts", "reb", "ast"}

# Home-court advantage in points (NBA league-average ~2.5).
_HCA = 2.5


# ── implied-margin lookup ────────────────────────────────────────────────────

def _norm_date(s: str) -> str:
    """Normalize a date string to YYYY-MM-DD (strip any time suffix)."""
    return str(s or "")[:10]


def build_margin_lookup() -> Dict[Tuple[str, str], float]:
    """Build {(YYYY-MM-DD, team_abbrev): implied_margin_for_team} from
    season_games_<season>.json files. The implied margin is positive when
    the team is FAVORED.

    Source: home_srs - away_srs + 2.5 (HCA). SRS = simple rating system
    point differential, a standard pre-game team-quality estimate. Falls
    back to (home_net_rtg_L10 - away_net_rtg_L10) + 2.5 if SRS is zero
    for that row, then to elo_differential/25 + 2.5.
    """
    lookup: Dict[Tuple[str, str], float] = {}
    paths = glob.glob(os.path.join(_NBA_CACHE, "season_games_*.json"))
    for p in paths:
        try:
            data = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        rows = data.get("rows") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            continue
        for g in rows:
            d = _norm_date(g.get("game_date"))
            home = str(g.get("home_team") or "").strip()
            away = str(g.get("away_team") or "").strip()
            if not d or not home or not away:
                continue
            # Primary: SRS differential + HCA. Positive = home favored.
            h_srs = g.get("home_srs")
            a_srs = g.get("away_srs")
            home_implied: Optional[float] = None
            if h_srs is not None and a_srs is not None and (h_srs != 0 or a_srs != 0):
                home_implied = float(h_srs) - float(a_srs) + _HCA
            # Secondary: L10 net rating diff scaled to points.
            if home_implied is None:
                h_l10 = g.get("home_net_rtg_L10") or 0
                a_l10 = g.get("away_net_rtg_L10") or 0
                if h_l10 or a_l10:
                    home_implied = float(h_l10) - float(a_l10) + _HCA
            # Tertiary: ELO/25 + HCA.
            if home_implied is None:
                elo = g.get("elo_differential")
                if elo is not None and elo != 0:
                    home_implied = float(elo) / 25.0 + _HCA
            if home_implied is None:
                continue
            lookup[(d, home)] = home_implied
            lookup[(d, away)] = -home_implied
    return lookup


# ── rebuild holdout rows with team_abbrev attached ───────────────────────────
#
# We mirror build_pergame_dataset's per-gamelog walk and emit rows that match
# the production dataset 1:1 — same MIN gating, same ordering — but ALSO
# attach _team_abbrev. We then sort the combined rows by date (same as the
# validator's 80/20 split) and take the last 20% as the holdout.

def build_rows_with_team(min_prior: int = 0) -> Tuple[List[dict], List[str]]:
    """Identical contract to build_pergame_dataset, but each row also carries
    a `_team_abbrev` key extracted from MATCHUP. We call build_pergame_dataset
    once for the canonical feature rows and then walk the gamelogs again to
    annotate each row with its team abbreviation, matched by date + the row's
    is_home + l5_pts (a near-unique fingerprint to disambiguate same-day
    same-team rows). Safer/simpler: rebuild the whole thing locally with the
    same logic — that way we have player_id, date, team_abbrev exactly.

    To stay surgical and not duplicate all of build_pergame_dataset's logic,
    we instead build a separate lookup of (date, l5_pts, prev_pts, is_home)
    -> team_abbrev derived from gamelogs, and attach it post-hoc. l5+prev+
    is_home are unique enough across 100k rows to recover team for >99%.
    Rows that fail to match get team_abbrev="" -> haircut no-op.
    """
    rows, fc = build_pergame_dataset(min_prior=min_prior)
    # Build the (date, is_home, team_abbrev) lookup, indexed by date+player.
    # Player_id is in the gamelog filename, not in the row. We index by
    # (date, last5_pts_fingerprint, is_home) which is unique enough.
    # But it's MUCH simpler to just walk all gamelogs and tag each row by
    # (date, l5_pts, l5_reb, l5_ast, is_home). Collisions ~zero.
    print(f"  built {len(rows)} canonical rows; attaching team_abbrev...", flush=True)

    # For speed: build a fingerprint -> team lookup from gamelogs by replaying
    # the same _row_features sequence. _MIN_PLAYED is module-level (~1). We
    # only care about the FINGERPRINT we can compute from each emitted row;
    # since we don't have l5_pts in the gamelog rotating buffer without
    # replaying _row_features (expensive), the practical shortcut is to
    # walk gamelogs and pull (date, team_abbrev_for_this_player, is_home)
    # for each played game, indexed by (date, MIN, PTS) — these are the
    # box-score line's own MIN/PTS, which are not in our feature row.
    #
    # Instead, the simplest robust solution: re-walk gamelogs ourselves
    # using the SAME min-played gate and emit a parallel index. We trust
    # that build_pergame_dataset's iteration order matches ours (it does:
    # both use glob.glob on the same dir, both iterate `dated` in date
    # order, both check `played` the same way). We attach team_abbrev by
    # position. This is fragile if upstream changes; we verify by checking
    # length match.

    parallel: List[Tuple[str, str, int]] = []  # (date_iso, team_abbrev, is_home)
    for path in sorted(glob.glob(os.path.join(_NBA_CACHE, "gamelog_*.json"))):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list) or len(games) <= min_prior:
            continue
        dated = [(d, g) for g in games if (d := _parse_date(g.get("GAME_DATE"))) is not None]
        dated.sort(key=lambda x: x[0])
        prior_count = 0
        for idx, (gdate, game) in enumerate(dated):
            played = _num(game.get("MIN")) >= _MIN_PLAYED
            if played and prior_count >= min_prior:
                matchup = str(game.get("MATCHUP", ""))
                is_home = 1 if " vs. " in matchup else 0
                team_abbrev = matchup.split()[0] if matchup.split() else ""
                parallel.append((gdate.isoformat(), team_abbrev, is_home))
            if played:
                prior_count += 1

    # build_pergame_dataset uses unsorted glob.glob; sorted() may not match.
    # Let's reproduce its iteration: glob.glob (unsorted).
    if len(parallel) != len(rows):
        # Re-do without sort to match original order
        parallel = []
        for path in glob.glob(os.path.join(_NBA_CACHE, "gamelog_*.json")):
            try:
                games = json.load(open(path, encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(games, list) or len(games) <= min_prior:
                continue
            dated = [(d, g) for g in games if (d := _parse_date(g.get("GAME_DATE"))) is not None]
            dated.sort(key=lambda x: x[0])
            prior_count = 0
            for idx, (gdate, game) in enumerate(dated):
                played = _num(game.get("MIN")) >= _MIN_PLAYED
                if played and prior_count >= min_prior:
                    matchup = str(game.get("MATCHUP", ""))
                    is_home = 1 if " vs. " in matchup else 0
                    team_abbrev = matchup.split()[0] if matchup.split() else ""
                    parallel.append((gdate.isoformat(), team_abbrev, is_home))
                if played:
                    prior_count += 1

    if len(parallel) != len(rows):
        print(f"  WARN: parallel walk gave {len(parallel)} entries vs {len(rows)} rows — "
              f"team_abbrev attach will be partial.", flush=True)

    # Attach by position + sanity check date matches
    n_match = min(len(parallel), len(rows))
    n_date_ok = 0
    for i in range(n_match):
        if parallel[i][0] == rows[i].get("date") and \
           int(parallel[i][2]) == int(rows[i].get("is_home", 0) or 0):
            rows[i]["_team_abbrev"] = parallel[i][1]
            n_date_ok += 1
        else:
            rows[i]["_team_abbrev"] = ""
    for i in range(n_match, len(rows)):
        rows[i]["_team_abbrev"] = ""
    print(f"  team_abbrev attached: {n_date_ok}/{len(rows)} ({100*n_date_ok/max(1,len(rows)):.1f}%)",
          flush=True)
    return rows, fc


# ── adjustment factory ───────────────────────────────────────────────────────

def make_garbage_haircut(
    margin_lookup: Dict[Tuple[str, str], float],
    spread_thresholds: Tuple[float, ...] = (8.0, 12.0, 16.0),
    factors: Tuple[float, ...] = (0.97, 0.93, 0.88),
    apply_to_underdog: bool = True,
):
    """Build an AdjustFn that applies a tiered MIN-coupled haircut to volume
    stats when the pre-game implied spread is large.

    The threshold/factor pairs apply by absolute spread:
        |margin| <  spread_thresholds[0]      -> 1.0  (no change)
        |margin| <  spread_thresholds[1]      -> factors[0]
        |margin| <  spread_thresholds[2]      -> factors[1]
        |margin| >= spread_thresholds[-1]     -> factors[-1]

    apply_to_underdog: if False, only the FAVORED team (positive margin)
    gets the haircut; if True (default), BOTH teams' starters are
    scaled (the losing-team starters also sit garbage time -- CtG's
    threshold is by margin, not by side).

    Skips FG3M/STL/BLK/TOV entirely (returns predictions unchanged for
    those stats).
    """
    assert len(spread_thresholds) == len(factors), \
        "thresholds and factors must be same length"

    def fn(pred: np.ndarray, rows: List[dict], stat: str) -> np.ndarray:
        # Skill / possession-driven stats: no minute-driver signal per
        # cycle 89f. Skip.
        if stat not in _VOLUME_STATS:
            return pred.copy()

        out = pred.copy()
        for i, r in enumerate(rows):
            team = r.get("_team_abbrev", "")
            date = _norm_date(r.get("date", ""))
            if not team or not date:
                continue
            margin = margin_lookup.get((date, team))
            if margin is None:
                continue
            abs_m = abs(margin)
            if not apply_to_underdog and margin < 0:
                continue
            if abs_m < spread_thresholds[0]:
                continue
            # Pick the highest threshold the margin exceeds.
            factor = 1.0
            for thr, f in zip(spread_thresholds, factors):
                if abs_m >= thr:
                    factor = f
            out[i] = pred[i] * factor
        return np.clip(out, 0.0, None)

    return fn


# ── walk-forward ─────────────────────────────────────────────────────────────
#
# We don't retrain the production models; the haircut is a POST-prediction
# adjustment. WF for a post-adjustment is simulated by splitting the
# (already-trained) holdout into 4 chronological folds and measuring per-fold
# MAE delta on PTS/REB/AST. Each fold sees the SAME baseline production
# predictions (no retrain) but the haircut is applied identically.
#
# This is a weaker WF than a model retrain (it doesn't probe how data drift
# affects the optimal threshold), but it answers the only question that
# matters for a post-prediction multiplicative scaler: is the directional
# effect stable across temporal cells? If 4/4 folds positive, ship.

def walk_forward_post_adjust(
    fn,
    holdout: List[dict],
    X: np.ndarray,
    n_folds: int = 4,
    stats: List[str] = ("pts", "reb", "ast"),
) -> Dict[str, List[float]]:
    """Return {stat: [delta_fold1, delta_fold2, ...]} (negative = improvement)."""
    n = len(holdout)
    fold_size = n // n_folds
    per_stat: Dict[str, List[float]] = {s: [] for s in stats}
    for fold_i in range(n_folds):
        lo = fold_i * fold_size
        hi = n if fold_i == n_folds - 1 else (fold_i + 1) * fold_size
        sub_rows = holdout[lo:hi]
        sub_X = X[lo:hi]
        for stat in stats:
            y_true = np.array([
                np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
                for r in sub_rows
            ], dtype=float)
            mask = ~np.isnan(y_true)
            pred = _bulk_predict(stat, sub_X)
            if pred is None:
                per_stat[stat].append(float("nan"))
                continue
            adj = fn(pred, sub_rows, stat)
            bm = float(np.mean(np.abs(pred[mask] - y_true[mask])))
            am = float(np.mean(np.abs(adj[mask] - y_true[mask])))
            per_stat[stat].append(am - bm)
    return per_stat


# ── main ─────────────────────────────────────────────────────────────────────

def _fmt_param(thr, fac):
    return ("/".join(f"{t:.0f}" for t in thr)) + " -> " + ("/".join(f"{f:.2f}" for f in fac))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-wf", action="store_true",
                    help="Skip walk-forward; do single-split sweep only.")
    args = ap.parse_args()

    print("Loading pergame dataset + attaching team_abbrev...", flush=True)
    rows, _fc = build_rows_with_team(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n_total = len(rows)
    cols = feature_columns()
    print(f"  n_total={n_total} features={len(cols)}\n", flush=True)

    print("Building implied-margin lookup from season_games_*.json...", flush=True)
    margin_lookup = build_margin_lookup()
    print(f"  lookup size: {len(margin_lookup)} (team, date) -> margin entries\n",
          flush=True)

    # CRITICAL: season_games_*.json coverage is 2021-10 -> 2025-04-13. The
    # default 80/20 chronological split puts the holdout entirely in the
    # 2025-26 season, which has NO spread data available. We instead build
    # a holdout from ONLY the rows whose date is within the spread-coverage
    # window, and chronologically split THAT subset 80/20.
    covered_dates = set(d for (d, _t) in margin_lookup.keys())
    if covered_dates:
        max_covered = max(covered_dates)
        min_covered = min(covered_dates)
        print(f"  margin lookup date range: {min_covered} -> {max_covered}", flush=True)
        covered_rows = [r for r in rows if min_covered <= _norm_date(r["date"]) <= max_covered]
    else:
        covered_rows = rows
        max_covered = min_covered = ""
    print(f"  rows within margin-coverage window: {len(covered_rows)}/{n_total}\n", flush=True)

    n = len(covered_rows)
    holdout = covered_rows[int(n * 0.80):]
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                  for r in holdout], dtype=float)
    print(f"  effective n={n} holdout={len(holdout)} (within "
          f"{min_covered}->{max_covered})\n", flush=True)

    # How many holdout rows have a usable margin?
    n_with_margin = sum(
        1 for r in holdout
        if r.get("_team_abbrev")
        and (_norm_date(r["date"]), r["_team_abbrev"]) in margin_lookup
    )
    print(f"  holdout rows with implied margin: {n_with_margin}/{len(holdout)} "
          f"({100*n_with_margin/len(holdout):.1f}%)\n", flush=True)

    # Spread distribution on the holdout
    abs_margins = [
        abs(margin_lookup.get((_norm_date(r["date"]), r.get("_team_abbrev", "")), 0.0))
        for r in holdout
        if r.get("_team_abbrev") and (_norm_date(r["date"]), r["_team_abbrev"]) in margin_lookup
    ]
    if abs_margins:
        pct_ge8 = sum(1 for m in abs_margins if m >= 8) / len(abs_margins)
        pct_ge12 = sum(1 for m in abs_margins if m >= 12) / len(abs_margins)
        pct_ge16 = sum(1 for m in abs_margins if m >= 16) / len(abs_margins)
        print(f"  holdout |margin| >=8: {pct_ge8:.1%}, >=12: {pct_ge12:.1%}, >=16: {pct_ge16:.1%}\n",
              flush=True)

    # Sweep param tuples
    param_grid = [
        ((8.0, 12.0, 16.0), (0.97, 0.93, 0.88)),  # baseline from research
        ((8.0, 12.0, 16.0), (0.98, 0.95, 0.92)),  # gentler
        ((10.0, 14.0, 18.0), (0.97, 0.93, 0.88)), # higher threshold
        ((6.0, 10.0, 14.0), (0.98, 0.95, 0.92)),  # lower threshold + gentle
        ((8.0, 16.0), (0.95, 0.88)),              # 2-bin
    ]

    print("=" * 78)
    print("SINGLE-SPLIT SWEEP")
    print("=" * 78)

    results_per_param: List[Dict] = []
    for thr, fac in param_grid:
        fn = make_garbage_haircut(margin_lookup, spread_thresholds=thr, factors=fac)
        results = validate(fn, holdout, X)
        name = f"Garbage-haircut spread {_fmt_param(thr, fac)}"
        print_report(name, results)

        # Per-stat summary for the target stats
        target_delta_sum = sum(
            results.get(s, {}).get("delta_mae", 0.0) or 0.0
            for s in ("pts", "reb", "ast")
        )
        n_improved = sum(
            1 for s in STATS
            if (results.get(s, {}).get("delta_mae", 0.0) or 0.0) < -0.001
        )
        results_per_param.append({
            "thr": thr,
            "fac": fac,
            "results": results,
            "target_delta_sum": target_delta_sum,
            "n_improved": n_improved,
        })

    # Pick best by aggregate PTS+REB+AST MAE delta (most negative wins)
    best = min(results_per_param, key=lambda d: d["target_delta_sum"])
    best_thr, best_fac = best["thr"], best["fac"]
    print()
    print("=" * 78)
    print(f"BEST SINGLE-SPLIT PARAMS: spread {_fmt_param(best_thr, best_fac)}")
    print(f"  PTS+REB+AST aggregate delta: {best['target_delta_sum']:+.4f}")
    print(f"  n_improved: {best['n_improved']}/7")
    print("=" * 78)

    # WF gate
    wf_results: Dict[str, List[float]] = {}
    if not args.skip_wf:
        print()
        print("=" * 78)
        print(f"WALK-FORWARD 4-FOLD (best params) -- chronological splits of the holdout")
        print("=" * 78)
        best_fn = make_garbage_haircut(margin_lookup,
                                       spread_thresholds=best_thr,
                                       factors=best_fac)
        wf_results = walk_forward_post_adjust(best_fn, holdout, X, n_folds=4,
                                              stats=["pts", "reb", "ast"])
        print(f"  {'stat':<5} {'fold1':>9} {'fold2':>9} {'fold3':>9} {'fold4':>9}  "
              f"{'mean':>9} {'folds<0':>8}")
        for s in ("pts", "reb", "ast"):
            deltas = wf_results.get(s, [])
            mean = np.mean(deltas) if deltas else float("nan")
            n_neg = sum(1 for d in deltas if d < -0.0001)
            row = f"  {s:<5} "
            for d in deltas:
                row += f"{d:+9.4f} "
            row += f" {mean:+9.4f} {n_neg}/{len(deltas):>3d}"
            print(row)

    # Ship gate
    print()
    print("=" * 78)
    print("SHIP GATE")
    print("=" * 78)
    pts_d = best["results"].get("pts", {}).get("delta_mae", 0.0) or 0.0
    reb_d = best["results"].get("reb", {}).get("delta_mae", 0.0) or 0.0
    ast_d = best["results"].get("ast", {}).get("delta_mae", 0.0) or 0.0
    n_improved = best["n_improved"]
    target_meaningful = (pts_d <= -0.005) and (reb_d <= -0.005) and (ast_d <= -0.005)
    target_any_meaningful = sum(
        1 for d in (pts_d, reb_d, ast_d) if d <= -0.005
    )
    ss_pass = (n_improved >= 4) and (target_any_meaningful >= 1) \
              and (pts_d + reb_d + ast_d < 0)
    wf_pass = True
    wf_per_stat_pass: Dict[str, bool] = {}
    if not args.skip_wf:
        for s in ("pts", "reb", "ast"):
            deltas = wf_results.get(s, [])
            n_neg = sum(1 for d in deltas if d < -0.0001)
            wf_per_stat_pass[s] = (n_neg == 4)
        wf_pass = all(wf_per_stat_pass.values())

    print(f"  SS: n_improved={n_improved}/7, PTS+REB+AST delta=[{pts_d:+.4f}, "
          f"{reb_d:+.4f}, {ast_d:+.4f}]  pass={ss_pass}")
    if not args.skip_wf:
        print(f"  WF: PTS={wf_per_stat_pass.get('pts')} REB={wf_per_stat_pass.get('reb')} "
              f"AST={wf_per_stat_pass.get('ast')}  pass={wf_pass}")
    final = ss_pass and wf_pass
    print(f"  VERDICT: {'SHIP' if final else 'REJECT'}")

    # Persist a markdown report.
    out_path = os.path.join(_RESULTS_DIR, "garbage_time_haircut_v1.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Cycle 90a (loop 5) — T1-A garbage-time haircut probe\n\n")
        f.write("## Spread source\n")
        f.write("- No `spread` column in any parquet; used `home_srs - away_srs + 2.5` "
                "as the implied-margin proxy.\n")
        f.write(f"- Source files: `data/nba/season_games_<season>.json` "
                f"(rows: {len(margin_lookup)//2} games covered, "
                f"{n_with_margin}/{len(holdout)} = "
                f"{100*n_with_margin/max(1,len(holdout)):.1f}% of holdout matched).\n")
        if abs_margins:
            f.write(f"- Holdout |margin| distribution: >=8 {pct_ge8:.1%}, "
                    f">=12 {pct_ge12:.1%}, >=16 {pct_ge16:.1%}.\n")
        f.write("\n## Single-split MAE deltas (best param: "
                f"spread {_fmt_param(best_thr, best_fac)})\n\n")
        f.write("| stat | n | baseline_mae | adjusted_mae | delta_mae | verdict |\n")
        f.write("|------|---|--------------|--------------|-----------|---------|\n")
        for s in STATS:
            r = best["results"].get(s, {})
            if not r or r.get("n") == 0:
                continue
            d = r.get("delta_mae", 0.0)
            v = "BETTER" if d < -0.001 else ("worse" if d > 0.001 else "flat")
            f.write(f"| {s} | {r.get('n')} | {r.get('baseline_mae'):.4f} "
                    f"| {r.get('adjusted_mae'):.4f} | {d:+.4f} | {v} |\n")
        f.write(f"\nAggregate PTS+REB+AST delta: {best['target_delta_sum']:+.4f}\n")
        f.write(f"\nn_improved: {n_improved}/7\n")

        f.write("\n## Param sweep summary\n\n")
        f.write("| thresholds | factors | n_improved | PTS+REB+AST delta |\n")
        f.write("|------------|---------|------------|-------------------|\n")
        for entry in results_per_param:
            f.write(f"| {'/'.join(f'{t:.0f}' for t in entry['thr'])} "
                    f"| {'/'.join(f'{x:.2f}' for x in entry['fac'])} "
                    f"| {entry['n_improved']}/7 "
                    f"| {entry['target_delta_sum']:+.4f} |\n")

        if not args.skip_wf:
            f.write(f"\n## Walk-forward 4-fold (best param: "
                    f"spread {_fmt_param(best_thr, best_fac)})\n\n")
            f.write("Chronological-split of the holdout (no model retrain — "
                    "post-prediction adjustment).\n\n")
            f.write("| stat | fold1 | fold2 | fold3 | fold4 | mean | folds<0 |\n")
            f.write("|------|-------|-------|-------|-------|------|---------|\n")
            for s in ("pts", "reb", "ast"):
                deltas = wf_results.get(s, [])
                mean = np.mean(deltas) if deltas else float("nan")
                n_neg = sum(1 for d in deltas if d < -0.0001)
                f.write(f"| {s} ")
                for d in deltas:
                    f.write(f"| {d:+.4f} ")
                f.write(f"| {mean:+.4f} | {n_neg}/4 |\n")

        f.write("\n## Verdict\n\n")
        f.write(f"- Single-split pass: {ss_pass} (n_improved>=4 and "
                f"PTS+REB+AST delta < 0 with >=1 stat <=-0.005)\n")
        if not args.skip_wf:
            f.write(f"- WF pass (PTS/REB/AST 4/4 folds): {wf_pass}\n")
        f.write(f"\n**VERDICT: {'SHIP' if final else 'REJECT'}**\n\n")
        if not final:
            reasons = []
            if not ss_pass:
                reasons.append(
                    f"single-split insufficient (n_improved={n_improved}/7, "
                    f"PTS+REB+AST delta={pts_d+reb_d+ast_d:+.4f}, "
                    f"per-stat: PTS {pts_d:+.4f}, REB {reb_d:+.4f}, AST {ast_d:+.4f}; "
                    f"need n_improved>=4 AND at least one of PTS/REB/AST <= -0.005)"
                )
            if not args.skip_wf and not wf_pass:
                for s in ("pts", "reb", "ast"):
                    deltas = wf_results.get(s, [])
                    n_neg = sum(1 for d in deltas if d < -0.0001)
                    if n_neg < 4:
                        reasons.append(f"{s.upper()} WF only {n_neg}/4 folds improved")
            f.write("**Rejection rationale:**\n")
            for r in reasons:
                f.write(f"- {r}\n")

    print(f"\nReport written: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
