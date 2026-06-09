"""ingame_calib_eval.py — canonical leak-free in-game CALIBRATION VALIDATION wrapper.

Thin A/B harness on top of the existing canonical retro pipeline
(`scripts/retro_inplay_mae.py`). It exists so an overnight agent can validate
ANY in-game wiring / calibration change (an env flag ON vs OFF, or a shrink-curve
param) with one command and a clear accept/reject rule.

WHAT IT MEASURES (all leak-free)
--------------------------------
For every game in data/player_quarter_stats.parquet (954 with all 4 quarters):
  * Reconstruct the snapshot at endQ1/endQ2/endQ3 from ONLY the prior quarters
    (rim.build_snapshot — no future-quarter leakage into the snapshot).
  * Project finals via either projector:
      - "pig"    : scripts.predict_in_game.project_snapshot  (linear extrapolation)
      - "engine" : src.prediction.live_engine.project_from_snapshot (period heads
                   + foul/blowout/heat overrides + win-prob)  [default]
  * Optionally BLEND the live projection with a leak-free pregame prior using a
    minutes-based shrink curve:  shrunk = w(mp)*live + (1-w(mp))*pregame .
    Pregame prior = pregame_oof.parquet oof_pred (out-of-fold => leak-free),
    joined by (game_id, player_id, stat). Falls back to no-blend for keys the
    OOF doesn't cover.
  * Ground truth = full-game Q1+Q2+Q3+Q4 sums from the same parquet. The actual
    only ever enters the LABEL, never the snapshot => no leakage.

Reports per-stat MAE by snapshot point AND by minutes bucket, plus a win-prob
Brier score per period (engine projector only). With --candidate-* it runs a
SECOND pass and prints the per-stat MAE / Brier DELTA (candidate - baseline).

SHRINK CURVES (--shrink / --candidate-shrink)
---------------------------------------------
  none                      -> w=1 always (pure live, no pregame blend)
  sigmoid:CENTER:SCALE      -> w = 1/(1+exp(-(mp-CENTER)/SCALE))   [prod = 14:4]
  linear:T                  -> w = min(1, mp/T)
  prod                      -> alias for sigmoid:14:4 (current api router curve)

ACCEPTANCE RULE (for overnight agents)
--------------------------------------
Accept the candidate ONLY IF, on the held-out corpus:
  * mean per-stat MAE improves (delta < 0) and NO core stat (pts/reb/ast)
    regresses by more than +0.5% relative, AND
  * win-prob Brier does not regress, AND
  * with the candidate's flag OFF the projector output is byte-identical to
    baseline (run with --verify-flag-off).
Small-n stats (n<200 in a bucket) are advisory only; never ship on them alone.

CLI
---
  # baseline only (per-stat MAE + Brier), pure live:
  python scripts/ingame_calib_eval.py
  # baseline = production shrink (sigmoid 14:4) blended with OOF pregame:
  python scripts/ingame_calib_eval.py --shrink prod
  # A/B a candidate shrink vs baseline:
  python scripts/ingame_calib_eval.py --shrink prod --candidate-shrink sigmoid:10:4
  # grid search the shrink curve (writes JSON):
  python scripts/ingame_calib_eval.py --grid --json scripts/_results/shrink_grid.json
  # flag A/B (set the env flag externally for the candidate run):
  python scripts/ingame_calib_eval.py --max-games 200 --by-bucket
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae as rim  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
CORE_STATS = ("pts", "reb", "ast")
SNAPSHOT_POINTS = ("endQ1", "endQ2", "endQ3")
# minutes-played buckets for the shrink curve diagnosis
MIN_BUCKETS = ((0, 6), (6, 12), (12, 18), (18, 24), (24, 100))

_OOF_PATH = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
_OOF_FAITHFUL_PATH = os.path.join(
    PROJECT_DIR, "data", "cache", "pregame_oof_faithful.parquet"
)


def _faithful_anchor_enabled() -> bool:
    """Return True iff CV_CALIB_FAITHFUL_ANCHOR is set to a truthy value.

    Truthy: "1", "true", "yes", "on" (case-insensitive).
    Everything else (unset, "0", "false", "off", "") returns False.
    Default: OFF — harness behaviour is byte-identical to the pre-flag baseline.
    """
    val = os.environ.get("CV_CALIB_FAITHFUL_ANCHOR", "").strip().lower()
    return val in ("1", "true", "yes", "on")


# ── shrink curves ───────────────────────────────────────────────────────────

def make_shrink(spec: str) -> Callable[[float], float]:
    """Parse a shrink spec into w(mp) in [0,1]."""
    spec = (spec or "none").strip().lower()
    if spec in ("none", "live", "1"):
        return lambda mp: 1.0
    if spec == "prod":
        spec = "sigmoid:14:4"
    if spec.startswith("sigmoid:"):
        _, c, s = spec.split(":")
        center, scale = float(c), float(s)

        def _w(mp: float, center=center, scale=scale) -> float:
            if mp is None or mp <= 0:
                return 0.0
            return 1.0 / (1.0 + math.exp(-(float(mp) - center) / scale))
        return _w
    if spec.startswith("linear:"):
        _, t = spec.split(":")
        T = float(t)

        def _wl(mp: float, T=T) -> float:
            if mp is None or mp <= 0:
                return 0.0
            return min(1.0, float(mp) / T)
        return _wl
    raise ValueError(f"unknown shrink spec: {spec!r}")


# ── game_id -> game_date lookup (for faithful join) ─────────────────────────

def _build_gid_to_date() -> Dict[str, str]:
    """Build a {game_id: 'YYYY-MM-DD'} map from season_games_*.json files.

    The faithful parquet has empty game_id values (build_pergame_dataset does
    not populate game_id into row dicts), so the faithful anchor must join on
    (game_date, player_id, stat) and then re-key to (game_id, player_id, stat)
    using this lookup.  The legacy parquet already has real game_ids.
    """
    import json
    import glob
    gid_to_date: Dict[str, str] = {}
    for pattern in (
        os.path.join(PROJECT_DIR, "data", "nba", "season_games_*.json"),
        os.path.join(PROJECT_DIR, "data", "cache", "season_games_*.json"),
    ):
        for fpath in glob.glob(pattern):
            try:
                with open(fpath, encoding="utf-8") as fh:
                    data = json.load(fh)
                rows = data.get("rows", [])
                for row in rows:
                    if isinstance(row, dict):
                        gid = str(row.get("game_id", "")).strip()
                        gdate = str(row.get("game_date", ""))[:10].strip()
                        if gid and gdate:
                            gid_to_date[gid] = gdate
            except Exception:
                continue
    return gid_to_date


# ── pregame prior (leak-free OOF) ───────────────────────────────────────────

def load_oof_prior() -> Dict[Tuple[str, int, str], float]:
    """{(game_id, player_id, stat): oof_pred} loaded from the appropriate source.

    CV_CALIB_FAITHFUL_ANCHOR=0 (default, byte-identical):
        Loads pregame_oof.parquet oof_pred — the legacy 3-way NNLS blend for all
        7 stats.  This is the pre-flag baseline; all existing numbers reproduce
        exactly when this flag is OFF.

    CV_CALIB_FAITHFUL_ANCHOR=1 (faithful mode):
        Loads pregame_oof_faithful.parquet oof_pred — the SERVED dispatch:
          * pts, ast  → 3-way blend (served_head='blend')
          * reb, fg3m, stl, blk, tov → q50 quantile head (served_head='q50')
        This is byte-identical to what predict_pergame actually serves to the
        live page, so the in-game MAE now validates against the real pregame
        anchor, not the stale blend-for-all-stats proxy.

        Because the faithful parquet has empty game_id values (the dataset
        builder does not populate game_id), the join is done on
        (game_date, player_id, stat) using a game_id→game_date lookup built
        from data/nba/season_games_*.json, then re-keyed to (game_id, ...).

    In both cases the returned dict keys are (game_id, player_id, stat) and
    oof_pred is OUT-OF-FOLD (target game's actual never trained the model).
    """
    import pandas as pd

    if not _faithful_anchor_enabled():
        # ── LEGACY MODE (default, byte-identical to all prior runs) ──────────
        if not os.path.exists(_OOF_PATH):
            return {}
        df = pd.read_parquet(_OOF_PATH,
                             columns=["game_id", "player_id", "stat", "oof_pred"])
        df = df[df["stat"].isin(STATS)]
        out: Dict[Tuple[str, int, str], float] = {}
        for r in df.itertuples(index=False):
            try:
                out[(str(r.game_id), int(r.player_id), str(r.stat))] = float(r.oof_pred)
            except (TypeError, ValueError):
                continue
        print(f"[load_oof_prior] loaded {len(out):,} prior entries  "
              f"[legacy blend / stale anchor]", flush=True)
        return out

    # ── FAITHFUL MODE (CV_CALIB_FAITHFUL_ANCHOR=1) ────────────────────────
    if not os.path.exists(_OOF_FAITHFUL_PATH):
        print(f"[load_oof_prior] WARNING: {_OOF_FAITHFUL_PATH} not found — "
              f"falling back to no-blend for faithful mode", flush=True)
        return {}

    # Step 1: build (game_date, player_id, stat) -> oof_pred from faithful parquet.
    df = pd.read_parquet(
        _OOF_FAITHFUL_PATH,
        columns=["game_date", "player_id", "stat", "oof_pred"],
    )
    df = df[df["stat"].isin(STATS)]
    date_idx: Dict[Tuple[str, int, str], float] = {}
    for r in df.itertuples(index=False):
        try:
            gdate = str(r.game_date)[:10]
            date_idx[(gdate, int(r.player_id), str(r.stat))] = float(r.oof_pred)
        except (TypeError, ValueError):
            continue

    # Step 2: build game_id -> game_date from season_games JSON files.
    gid_to_date = _build_gid_to_date()

    # Step 3: re-key to (game_id, player_id, stat) — the key the collect() loop uses.
    out = {}
    n_miss = 0
    # We don't know all game_ids upfront; instead invert: for each game_id whose
    # date we know, look up entries from the date-indexed faithful dict.
    # More efficient: build a reverse (player_id, stat) -> list of (gdate, val)
    # then iterate caller's game_ids. But we don't have caller's game_ids here.
    # Simplest correct approach: iterate all known game_ids from the lookup and
    # produce entries for any (player_id, stat) present in faithful on that date.
    date_to_gids: Dict[str, List[str]] = {}
    for gid, gdate in gid_to_date.items():
        date_to_gids.setdefault(gdate, []).append(gid)

    # Collect all (player_id, stat) keys per date from faithful.
    from collections import defaultdict as _dd
    date_player_stat: Dict[str, Dict[Tuple[int, str], float]] = _dd(dict)
    for (gdate, pid, stat), val in date_idx.items():
        date_player_stat[gdate][(pid, stat)] = val

    for gdate, pid_stat_map in date_player_stat.items():
        gids_for_date = date_to_gids.get(gdate, [])
        if not gids_for_date:
            n_miss += 1
            continue
        for gid in gids_for_date:
            for (pid, stat), val in pid_stat_map.items():
                out[(gid, pid, stat)] = val

    print(
        f"[load_oof_prior] loaded {len(out):,} prior entries  "
        f"[faithful (served dispatch)]  "
        f"({len(date_idx):,} faithful rows, {len(gid_to_date):,} gid->date pairs, "
        f"{n_miss} unmatched dates)",
        flush=True,
    )
    return out


# ── projector dispatch ──────────────────────────────────────────────────────

def get_projector(kind: str):
    if kind == "pig":
        import predict_in_game as pig
        return pig.project_snapshot
    if kind == "engine":
        from src.prediction.live_engine import project_from_snapshot
        return project_from_snapshot
    raise ValueError(f"unknown projector: {kind!r}")


# ── core collection ─────────────────────────────────────────────────────────

def collect(
    projector_kind: str = "engine",
    max_games: int = 0,
    points: Tuple[str, ...] = SNAPSHOT_POINTS,
) -> Tuple[list, list]:
    """Run every game/point through the projector ONCE.

    Returns:
      records: list of dicts with raw building blocks for any shrink curve:
          {point, game_id, player_id, stat, live, pregame, actual, mp}
      wp_records: list of (point, home_win_prob_inplay, home_won) for Brier
    Both are leak-free. The projector pass is the expensive part; shrink curves
    are then evaluated on `records` in-memory (cheap), so A/B and grid search
    don't re-run the model.
    """
    project = get_projector(projector_kind)
    oof = load_oof_prior()
    qs = rim.load_quarter_stats()
    game_ids = sorted(qs["game_id"].unique().tolist())
    if max_games:
        game_ids = game_ids[:max_games]

    records: List[dict] = []
    wp_records: List[Tuple[str, float, int]] = []
    n_ok = 0
    for gid in game_ids:
        gid_s = str(gid)
        actuals = rim.actuals_for_game(gid, qs)
        if not actuals:
            continue
        # final score for win-prob label
        snap_final = rim.build_snapshot(gid, "endQ3", qs)  # used only for team map
        for point in points:
            snap = rim.build_snapshot(gid, point, qs)
            if snap is None:
                continue
            # per-player minutes-played at this snapshot
            mp_map = {int(p["player_id"]): float(p.get("min") or 0.0)
                      for p in snap.get("players") or []
                      if p.get("player_id") is not None}
            try:
                rows = project(snap)
            except Exception:
                continue
            wp_logged = False
            for r in rows:
                pid = r.get("player_id")
                stat = r.get("stat")
                if pid is None or stat not in STATS:
                    continue
                try:
                    pid_i = int(pid)
                    live = float(r.get("projected_final", 0.0) or 0.0)
                except (TypeError, ValueError):
                    continue
                actual = actuals.get((pid_i, stat))
                if actual is None:
                    continue
                pre = oof.get((gid_s, pid_i, stat))
                records.append({
                    "point": point,
                    "game_id": gid_s,
                    "player_id": pid_i,
                    "stat": stat,
                    "live": live,
                    "pregame": pre,            # may be None => no blend
                    "actual": float(actual),
                    "mp": mp_map.get(pid_i, 0.0),
                })
                # win-prob: log once per game/point (engine only emits it)
                if not wp_logged and "home_win_prob_inplay" in r:
                    hwp = r.get("home_win_prob_inplay")
                    if hwp is not None and snap.get("home_team"):
                        won = _home_won(gid, qs, snap.get("home_team"),
                                        snap.get("away_team"))
                        if won is not None:
                            wp_records.append((point, float(hwp), int(won)))
                            wp_logged = True
        n_ok += 1
        if n_ok % 100 == 0:
            print(f"  [{n_ok}/{len(game_ids)}] games projected", flush=True)
    return records, wp_records


def _home_won(gid, qs, home_team, away_team) -> Optional[int]:
    """Return 1 if home team won the full game, 0 if lost, None if undecidable."""
    pid_to_team, home, away = rim.load_team_map(str(gid))
    if not home:
        home = home_team
    g = qs[qs["game_id"] == gid]
    if g.empty:
        return None
    # sum PTS per team over all periods
    team_pts = defaultdict(float)
    for r in g.itertuples(index=False):
        t = pid_to_team.get(int(r.player_id))
        if t:
            team_pts[t] += float(r.pts)
    hp = team_pts.get(home_team or home, 0.0)
    ap = team_pts.get(away_team or away, 0.0)
    if hp == ap:
        return None
    return 1 if hp > ap else 0


# ── MAE evaluation for a given shrink curve ─────────────────────────────────

def eval_mae(records: list, shrink: Callable[[float], float],
             by_bucket: bool = False) -> dict:
    """Compute per-(point, stat) MAE under a shrink curve.

    blended = w(mp)*live + (1-w(mp))*pregame   (pregame present => blend; else live)
    """
    # buckets[(point, stat)] -> list[abs err];   bbuck[(point,stat,bucket)] -> list
    abs_err: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    bbuck: Dict[Tuple[str, str, str], List[float]] = defaultdict(list)
    for rec in records:
        live = rec["live"]
        pre = rec["pregame"]
        mp = rec["mp"]
        if pre is None:
            blended = live
        else:
            w = shrink(mp)
            blended = w * live + (1.0 - w) * pre
        err = abs(blended - rec["actual"])
        abs_err[(rec["point"], rec["stat"])].append(err)
        if by_bucket:
            bk = _bucket_label(mp)
            bbuck[(rec["point"], rec["stat"], bk)].append(err)

    out: Dict[str, dict] = {"by_point_stat": {}, "by_stat": {}, "overall": {}}
    per_stat: Dict[str, List[float]] = defaultdict(list)
    for (point, stat), errs in abs_err.items():
        out["by_point_stat"][f"{point}/{stat}"] = {
            "n": len(errs), "mae": sum(errs) / len(errs)}
        per_stat[stat].extend(errs)
    all_err: List[float] = []
    for stat, errs in per_stat.items():
        out["by_stat"][stat] = {"n": len(errs), "mae": sum(errs) / len(errs)}
        all_err.extend(errs)
    out["overall"] = {"n": len(all_err),
                      "mae": (sum(all_err) / len(all_err)) if all_err else 0.0}
    if by_bucket:
        out["by_bucket"] = {}
        for (point, stat, bk), errs in bbuck.items():
            out["by_bucket"][f"{point}/{stat}/{bk}"] = {
                "n": len(errs), "mae": sum(errs) / len(errs)}
    return out


def _bucket_label(mp: float) -> str:
    for lo, hi in MIN_BUCKETS:
        if lo <= mp < hi:
            return f"{lo}-{hi if hi < 100 else '+'}"
    return "?"


def eval_brier(wp_records: list) -> dict:
    """Per-point win-prob Brier score."""
    by_point: Dict[str, List[float]] = defaultdict(list)
    for point, p, won in wp_records:
        by_point[point].append((p - won) ** 2)
    out: Dict[str, dict] = {}
    all_b: List[float] = []
    for point, vals in by_point.items():
        out[point] = {"n": len(vals), "brier": sum(vals) / len(vals)}
        all_b.extend(vals)
    out["overall"] = {"n": len(all_b),
                      "brier": (sum(all_b) / len(all_b)) if all_b else 0.0}
    return out


# ── report formatting ───────────────────────────────────────────────────────

def fmt_mae(label: str, res: dict) -> str:
    lines = [f"=== MAE [{label}] overall={res['overall']['mae']:.4f} "
             f"(n={res['overall']['n']:,}) ==="]
    lines.append(f"  {'stat':5s} {'n':>7s} {'mae':>9s}")
    for stat in STATS:
        e = res["by_stat"].get(stat)
        if e:
            lines.append(f"  {stat:5s} {e['n']:>7,d} {e['mae']:>9.4f}")
    return "\n".join(lines)


def fmt_delta(base: dict, cand: dict, base_lbl: str, cand_lbl: str) -> str:
    lines = [f"=== A/B  base[{base_lbl}]  vs  cand[{cand_lbl}] ===",
             f"  {'stat':5s} {'base_mae':>9s} {'cand_mae':>9s} "
             f"{'delta':>9s} {'rel%':>8s}"]
    regressions = []
    for stat in STATS:
        b = base["by_stat"].get(stat)
        c = cand["by_stat"].get(stat)
        if not b or not c:
            continue
        d = c["mae"] - b["mae"]
        rel = (d / b["mae"] * 100.0) if b["mae"] else 0.0
        flag = ""
        if stat in CORE_STATS and rel > 0.5:
            flag = "  <-- CORE REGRESSION"
            regressions.append(stat)
        lines.append(f"  {stat:5s} {b['mae']:>9.4f} {c['mae']:>9.4f} "
                     f"{d:>+9.4f} {rel:>+7.2f}%{flag}")
    bo, co = base["overall"]["mae"], cand["overall"]["mae"]
    lines.append(f"  {'OVER':5s} {bo:>9.4f} {co:>9.4f} {co-bo:>+9.4f} "
                 f"{((co-bo)/bo*100 if bo else 0):>+7.2f}%")
    verdict = "ACCEPT" if (co < bo and not regressions) else "REJECT"
    lines.append(f"  VERDICT: {verdict}"
                 + (f"  (core regressions: {regressions})" if regressions else ""))
    return "\n".join(lines)


# ── grid search ─────────────────────────────────────────────────────────────

def grid_search(records: list) -> dict:
    """Grid the shrink curve per the protocol: sigmoid {center}x{scale} +
    linear {T}, plus pure-live. Returns ranked overall + per-stat MAE."""
    specs: List[str] = ["none"]
    for c in (8, 10, 12, 14):
        for s in (3, 4, 6):
            specs.append(f"sigmoid:{c}:{s}")
    for t in (12, 18, 24):
        specs.append(f"linear:{t}")
    rows = []
    for spec in specs:
        w = make_shrink(spec)
        res = eval_mae(records, w)
        row = {"spec": spec, "overall_mae": res["overall"]["mae"],
               "n": res["overall"]["n"]}
        for stat in STATS:
            e = res["by_stat"].get(stat)
            row[f"mae_{stat}"] = round(e["mae"], 4) if e else None
        rows.append(row)
    rows.sort(key=lambda r: r["overall_mae"])
    return {"ranked": rows, "best": rows[0] if rows else None}


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--projector", choices=("engine", "pig"), default="engine")
    ap.add_argument("--max-games", type=int, default=0, help="0 = all")
    ap.add_argument("--shrink", default="none",
                    help="baseline shrink curve (none|prod|sigmoid:C:S|linear:T)")
    ap.add_argument("--candidate-shrink", default=None,
                    help="candidate shrink curve to A/B vs --shrink")
    ap.add_argument("--by-bucket", action="store_true",
                    help="also report MAE by minutes-played bucket")
    ap.add_argument("--grid", action="store_true",
                    help="grid-search the shrink curve (overrides A/B)")
    ap.add_argument("--points", default="endQ1,endQ2,endQ3")
    ap.add_argument("--json", default=None, help="write full result JSON here")
    args = ap.parse_args()

    import warnings
    warnings.filterwarnings("ignore")

    points = tuple(p.strip() for p in args.points.split(",") if p.strip())
    anchor_mode = "faithful (CV_CALIB_FAITHFUL_ANCHOR=1)" if _faithful_anchor_enabled() \
        else "legacy-blend (CV_CALIB_FAITHFUL_ANCHOR=0, default)"
    print(f"[eval] projector={args.projector} points={points} "
          f"max_games={args.max_games or 'ALL'}  anchor={anchor_mode}", flush=True)
    records, wp = collect(args.projector, args.max_games, points)
    print(f"[eval] collected {len(records):,} player-stat records, "
          f"{len(wp):,} win-prob points", flush=True)

    payload: dict = {"config": vars(args), "n_records": len(records)}

    if args.grid:
        g = grid_search(records)
        print("\n=== SHRINK-CURVE GRID (ranked by overall MAE) ===")
        print(f"  {'spec':16s} {'overall':>9s} {'pts':>7s} {'reb':>7s} "
              f"{'ast':>7s} {'fg3m':>7s}")
        for r in g["ranked"]:
            print(f"  {r['spec']:16s} {r['overall_mae']:>9.4f} "
                  f"{r['mae_pts'] or 0:>7.3f} {r['mae_reb'] or 0:>7.3f} "
                  f"{r['mae_ast'] or 0:>7.3f} {r['mae_fg3m'] or 0:>7.3f}")
        print(f"\n  BEST: {g['best']['spec']}  overall MAE={g['best']['overall_mae']:.4f}")
        payload["grid"] = g
    else:
        base_w = make_shrink(args.shrink)
        base = eval_mae(records, base_w, by_bucket=args.by_bucket)
        print("\n" + fmt_mae(args.shrink, base))
        payload["baseline"] = base
        if wp:
            brier = eval_brier(wp)
            print("\n=== WIN-PROB BRIER (by period) ===")
            for point in points + ("overall",):
                e = brier.get(point)
                if e:
                    print(f"  {point:8s} n={e['n']:>5,d}  brier={e['brier']:.4f}")
            payload["brier"] = brier
        if args.by_bucket:
            print("\n=== MAE BY MINUTES-PLAYED BUCKET (pts/reb/ast) ===")
            for stat in CORE_STATS:
                cells = []
                for lo, hi in MIN_BUCKETS:
                    bk = f"{lo}-{hi if hi < 100 else '+'}"
                    tot_n = 0
                    tot_e = 0.0
                    for point in points:
                        e = base.get("by_bucket", {}).get(f"{point}/{stat}/{bk}")
                        if e:
                            tot_n += e["n"]
                            tot_e += e["mae"] * e["n"]
                    mae = (tot_e / tot_n) if tot_n else 0.0
                    cells.append(f"{bk}:{mae:.2f}(n={tot_n})")
                print(f"  {stat:5s} " + "  ".join(cells))
        if args.candidate_shrink:
            cand_w = make_shrink(args.candidate_shrink)
            cand = eval_mae(records, cand_w)
            print("\n" + fmt_mae(args.candidate_shrink, cand))
            print("\n" + fmt_delta(base, cand, args.shrink, args.candidate_shrink))
            payload["candidate"] = cand

    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)
        print(f"\n[eval] wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
