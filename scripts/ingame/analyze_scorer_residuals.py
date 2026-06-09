"""analyze_scorer_residuals.py — where does the in-game projector mis-project SCORERS?

READ-ONLY error analysis. Runs the *production* live engine projector
(`src.prediction.live_engine.project_from_snapshot`, same projector the
canonical `ingame_calib_eval.py` baselines) over the 954-game endQ1/Q2/Q3
quarter corpus and dumps per-player **pts / fg3m REMAINING residuals**:

    resid = proj_remaining - actual_remaining
          = (projected_final - current_so_far) - (actual_final - current_so_far)
          = projected_final - actual_final

(so the remaining residual equals the final residual; we slice on the
remaining-projection because that is the quantity any in-game adjustment
multiplies). Positive resid => the projector OVER-projects the rest of the game.

We slice the residual mean/MAE/n by:
  * period (endQ1/endQ2/endQ3)
  * |score margin| bucket at the snapshot
  * scorer foul state (pf)
  * minutes played so far
  * OPPONENT defensive scheme (atlas_team_defensive_scheme dominant_tag)
  * scorer-vs-opponent-scheme historical TS delta (atlas_player_vs_scheme_splits)
  * scorer matchup vs the reconstructed opponent on-court anchor defender
    (coverage_faced_matrix_2025-26 PPP-vs-baseline) — the opponent on-court 5
    at end-of-quarter is reconstructed LEAK-FREE from the NEXT quarter's box
    starters (the exact onoff-enricher precedent).

Everything is leak-free: the snapshot is built from prior quarters only, the
actual only enters the label, and every intelligence artifact is a season-level
descriptor committed before the game.

Output: docs/_audits/_scorer_residuals.json + a console table.

Run:
    set NBA_OFFLINE=1
    python scripts/ingame/analyze_scorer_residuals.py --max-games 600
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.environ.setdefault("NBA_OFFLINE", "1")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import retro_inplay_mae as rim  # noqa: E402
from src.prediction.live_engine import project_from_snapshot  # noqa: E402
from src.ingame.snapshot_onoff_tilt_enricher import (  # noqa: E402
    reconstruct_oncourt_pids,
)

CACHE = Path(ROOT) / "data" / "cache"
STATS = ("pts", "fg3m")


# --------------------------------------------------------------------------- #
# Intelligence loaders (season-level, leak-free descriptors)
# --------------------------------------------------------------------------- #
def load_team_scheme() -> Dict[str, str]:
    """team_tricode -> dominant defensive scheme tag."""
    p = CACHE / "atlas_team_defensive_scheme.parquet"
    if not p.exists():
        return {}
    df = pd.read_parquet(p)
    out: Dict[str, str] = {}
    for r in df.itertuples(index=False):
        try:
            cs = json.loads(r.coverage_scheme)
            out[str(r.team_tricode)] = str(cs.get("dominant_tag") or "")
        except Exception:
            continue
    return out


_SCHEME_KEY = {
    "DROP COVERAGE": "drop_coverage", "SWITCH HEAVY": "switch_heavy",
    "HELP DEFENSE": "help_defense", "PACE CONTROL": "pace_control",
    "PAINT-FIRST DEFENSE": "paint_first_defense", "BALANCED": "balanced",
    "PERIMETER DENIAL": "perimeter_denial", "ISO FORCE": "iso_force",
}


def load_player_vs_scheme() -> Dict[int, dict]:
    """player_id -> by_scheme dict (per-scheme pts_pg/ts_pct/min_pg)."""
    p = CACHE / "atlas_player_vs_scheme_splits.parquet"
    if not p.exists():
        return {}
    df = pd.read_parquet(p)
    out: Dict[int, dict] = {}
    for r in df.itertuples(index=False):
        try:
            out[int(r.player_id)] = json.loads(r.by_scheme)
        except Exception:
            continue
    return out


def load_coverage_anchor() -> Dict[Tuple[int, int], float]:
    """(off_pid, def_pid) -> off PPP (off_points / partial_possessions), 2025-26.

    Only retains pairs with >= a small possession floor so the PPP isn't noise.
    """
    p = CACHE / "coverage_faced_matrix_2025-26.parquet"
    if not p.exists():
        return {}
    df = pd.read_parquet(p)
    out: Dict[Tuple[int, int], float] = {}
    for r in df.itertuples(index=False):
        try:
            pp = float(r.partial_possessions)
            if pp < 4.0:
                continue
            out[(int(r.off_player_id), int(r.def_player_id))] = float(r.off_points) / pp
        except Exception:
            continue
    return out


def _margin_bucket(m: float) -> str:
    a = abs(m)
    if a <= 3:
        return "0-3"
    if a <= 8:
        return "4-8"
    if a <= 15:
        return "9-15"
    return "16+"


def _min_bucket(mp: float) -> str:
    for lo, hi in ((0, 12), (12, 20), (20, 28), (28, 100)):
        if lo <= mp < hi:
            return f"{lo}-{hi if hi < 100 else '+'}"
    return "?"


def _scheme_ts_delta(by_scheme: dict, opp_scheme: str) -> Optional[float]:
    """player's TS% vs opp_scheme minus their across-scheme mean TS%."""
    key = _SCHEME_KEY.get(opp_scheme)
    if not by_scheme or key not in by_scheme:
        return None
    vals = [v.get("ts_pct") for v in by_scheme.values()
            if isinstance(v, dict) and v.get("ts_pct") is not None]
    if len(vals) < 2:
        return None
    mean_ts = float(np.mean(vals))
    this = by_scheme[key].get("ts_pct")
    if this is None:
        return None
    return float(this) - mean_ts


def run(max_games: int) -> dict:
    qs = rim.load_quarter_stats()
    game_ids = sorted(qs["game_id"].unique().tolist())
    if max_games:
        game_ids = game_ids[:max_games]

    team_scheme = load_team_scheme()
    pvs = load_player_vs_scheme()
    cov = load_coverage_anchor()
    qb_dir = CACHE / "quarter_box"

    # slices[slice_key][stat] -> list of residuals
    slices: Dict[str, Dict[str, List[float]]] = defaultdict(
        lambda: defaultdict(list))
    # raw rows for split-half later (matchup component)
    cov_rows: List[dict] = []   # {pid, def_pid, ppp, resid_pts}
    scheme_rows: List[dict] = []  # {pid, ts_delta, resid_pts}

    def add(key: str, stat: str, resid: float):
        slices[key][stat].append(resid)

    n_ok = 0
    for gid in game_ids:
        gid_s = str(gid)
        actuals = rim.actuals_for_game(gid, qs)
        if not actuals:
            continue
        for point in ("endQ1", "endQ2", "endQ3"):
            snap = rim.build_snapshot(gid, point, qs)
            if snap is None:
                continue
            home, away = snap.get("home_team"), snap.get("away_team")
            margin_home = float(snap.get("home_score", 0)) - float(snap.get("away_score", 0))
            # per-player team + min map
            team_of = {int(p["player_id"]): p.get("team", "")
                       for p in snap.get("players") or [] if p.get("player_id") is not None}
            mp_map = {int(p["player_id"]): float(p.get("min") or 0.0)
                      for p in snap.get("players") or [] if p.get("player_id") is not None}
            pf_map = {int(p["player_id"]): float(p.get("pf") or 0.0)
                      for p in snap.get("players") or [] if p.get("player_id") is not None}
            # reconstruct opponent on-court 5 (next-quarter box starters) — leak-free
            oncourt = reconstruct_oncourt_pids(gid_s, point, qb_dir)  # {team: frozenset}
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
                    proj = float(r.get("projected_final", 0.0) or 0.0)
                except (TypeError, ValueError):
                    continue
                actual = actuals.get((pid_i, stat))
                if actual is None:
                    continue
                resid = proj - float(actual)   # remaining-resid == final-resid
                tm = team_of.get(pid_i, "")
                opp = away if tm == home else (home if tm == away else "")
                # scorer's signed margin (own team's lead at snapshot)
                signed_margin = margin_home if tm == home else -margin_home
                mp = mp_map.get(pid_i, 0.0)
                pf = pf_map.get(pid_i, 0.0)

                add("ALL", stat, resid)
                add(f"period={point}", stat, resid)
                add(f"absmargin={_margin_bucket(signed_margin)}", stat, resid)
                add(f"signedmargin={'lead' if signed_margin>3 else ('trail' if signed_margin<-3 else 'tied')}", stat, resid)
                add(f"pf={int(min(pf,5))}", stat, resid)
                add(f"min={_min_bucket(mp)}", stat, resid)
                opp_scheme = team_scheme.get(opp, "")
                if opp_scheme:
                    add(f"oppscheme={opp_scheme}", stat, resid)
                # scheme TS delta
                tsd = _scheme_ts_delta(pvs.get(pid_i, {}), opp_scheme)
                if tsd is not None:
                    band = "favorable" if tsd > 0.01 else ("unfavorable" if tsd < -0.01 else "neutral")
                    add(f"schemeTS={band}", stat, resid)
                    if stat == "pts":
                        scheme_rows.append({"pid": pid_i, "gid": gid_s, "point": point,
                                            "ts_delta": tsd, "resid": resid})
                # anchor defender matchup: best-PPP opponent on-court defender
                if opp and opp in oncourt:
                    best_ppp = None
                    best_def = None
                    for dpid in oncourt[opp]:
                        v = cov.get((pid_i, dpid))
                        if v is not None and (best_ppp is None or v < best_ppp):
                            best_ppp = v   # lowest PPP = the toughest cover faced
                            best_def = dpid
                    if best_ppp is not None:
                        band = ("tough" if best_ppp < 1.0 else
                                ("easy" if best_ppp > 1.2 else "mid"))
                        add(f"anchorPPP={band}", stat, resid)
                        if stat == "pts":
                            cov_rows.append({"pid": pid_i, "def_pid": best_def,
                                             "gid": gid_s, "point": point,
                                             "ppp": best_ppp, "resid": resid})
        n_ok += 1
        if n_ok % 150 == 0:
            print(f"  [{n_ok}/{len(game_ids)}] games", flush=True)

    # summarize
    def summ(xs):
        a = np.array(xs, dtype=float)
        return {"n": int(a.size), "mean_resid": float(a.mean()),
                "mae": float(np.abs(a).mean())}

    out: Dict[str, dict] = {}
    for key in sorted(slices.keys()):
        out[key] = {s: summ(slices[key][s]) for s in STATS if slices[key][s]}

    return {"slices": out, "cov_rows": cov_rows, "scheme_rows": scheme_rows,
            "n_games": n_ok}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=600)
    ap.add_argument("--json", default=os.path.join(
        ROOT, "docs", "_audits", "_scorer_residuals.json"))
    args = ap.parse_args()
    import warnings
    warnings.filterwarnings("ignore")
    res = run(args.max_games)

    print(f"\n=== SCORER REMAINING RESIDUALS (proj_remaining - actual_remaining) "
          f"over {res['n_games']} games ===")
    print(f"{'slice':28s} {'pts_n':>7s} {'pts_meanR':>10s} {'pts_mae':>8s} "
          f"{'f3_n':>6s} {'f3_meanR':>9s} {'f3_mae':>7s}")
    order = sorted(res["slices"].keys(),
                   key=lambda k: (k != "ALL", k.split("=")[0], k))
    for key in order:
        d = res["slices"][key]
        p = d.get("pts", {})
        f = d.get("fg3m", {})
        print(f"{key:28s} {p.get('n',0):>7d} {p.get('mean_resid',0):>+10.3f} "
              f"{p.get('mae',0):>8.3f} {f.get('n',0):>6d} "
              f"{f.get('mean_resid',0):>+9.3f} {f.get('mae',0):>7.3f}")

    os.makedirs(os.path.dirname(args.json), exist_ok=True)
    with open(args.json, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2, default=str)
    print(f"\n[resid] wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
