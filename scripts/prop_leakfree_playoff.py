"""prop_leakfree_playoff.py — honest leak-free PLAYOFF re-measure of the prod prop models.

Evaluates the EXISTING production per-game prop models (src.prediction.prop_pergame
.predict_pergame — q50 heads / NNLS blend / calibration / haircut / residual heads, all
loaded from data/models/*) on the 2025-26 PLAYOFF games WITHOUT retraining.

Leakage discipline
------------------
build_pergame_dataset() computes every feature strictly from a player's PRIOR played
games (l5/l10/ewma/std + opp-defence to-date + rest/travel). The target is THAT game's
realised box line. predict_pergame() therefore never sees the game it predicts. We simply
run the prod models over those rows and bucket by date.

Playoff definition
-------------------
The 2025-26 NBA regular season ended 2026-04-12. Gamelog JSONs carry GAME_DATE but not
game_id, so the game_id-prefix-004 filter is realised via date: a row is a PLAYOFF row when
its game_date >= 2026-04-13 (this also sweeps in the play-in week; we additionally report a
strict >= 2026-04-19 conference-round cut so the play-in inflation is visible).

Role-change blindness
---------------------
A row is a ROLE-CHANGE game when the player's ACTUAL minutes that game jumped >= 30% above
their prior L10 minutes (l10_min from the leak-free feature row). This is exactly what L5/L10
form features cannot see pre-game (McCain 10->20, Caruso 7->22, Champagnie 11->22 promotions).
We report PTS MAE on role-change rows vs stable rows.

Output: data/cache/intel_game7/prop_honest_remeasure.json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, predict_pergame, _BOX_COL, _parse_date, _num,
)
import glob  # noqa: E402

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_OUT_DIR = os.path.join(PROJECT_DIR, "data", "cache", "intel_game7")
_OUT_PATH = os.path.join(_OUT_DIR, "prop_honest_remeasure.json")

# 2025-26 regular season ended 2026-04-12 (memory note Bug 47).
_PLAYOFF_CUT = datetime(2026, 4, 13)        # includes play-in week
_CONF_ROUND_CUT = datetime(2026, 4, 19)     # strict: 1st round onward (play-in over)
_RS_2025_26_START = datetime(2025, 10, 1)   # regular-season-only comparison bucket

_ROLE_CHANGE_THRESHOLD = 0.30               # >= +30% minutes vs prior L10


def _mae(pairs):
    if not pairs:
        return None
    return sum(abs(p - t) for p, t in pairs) / len(pairs)


def _build_actual_min_map():
    """(player_id, date_iso) -> actual MIN that game, read straight from gamelogs.

    Needed for role-change detection — the dataset rows carry the leak-free
    prior L10 minutes (l10_min) but not the realised minutes of the target game.
    """
    amap = {}
    for path in glob.glob(os.path.join(_NBA_CACHE, "gamelog_*_2025-26.json")):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list):
            continue
        try:
            pid = int(os.path.basename(path).split("_")[1])
        except Exception:
            continue
        for g in games:
            d = _parse_date(g.get("GAME_DATE"))
            if d is None:
                continue
            amap[(pid, d.date().isoformat())] = _num(g.get("MIN"))
    return amap


def main():
    print("Building leak-free per-game dataset (this reads all gamelogs)...", flush=True)
    rows, fc = build_pergame_dataset(min_prior=0)
    print(f"  total rows={len(rows)}  features={len(fc)}", flush=True)

    amap = _build_actual_min_map()

    # Bucket rows by date.
    playoff_rows, confround_rows, rs_rows = [], [], []
    for r in rows:
        try:
            d = datetime.fromisoformat(r["date"])
        except Exception:
            continue
        if d >= _PLAYOFF_CUT:
            playoff_rows.append(r)
            if d >= _CONF_ROUND_CUT:
                confround_rows.append(r)
        elif d >= _RS_2025_26_START:
            rs_rows.append(r)

    print(f"  2025-26 playoff rows (>=04-13): {len(playoff_rows)}", flush=True)
    print(f"  2025-26 conf-round rows (>=04-19): {len(confround_rows)}", flush=True)
    print(f"  2025-26 regular-season rows: {len(rs_rows)}", flush=True)

    def eval_bucket(bucket, name):
        """Return {stat: {mae, n}} predicting every row with the prod models."""
        out = {}
        for stat in STATS:
            pairs = []
            for r in bucket:
                pred = predict_pergame(stat, r)
                if pred is None:
                    continue
                pairs.append((float(pred), float(r[f"target_{stat}"])))
            out[stat] = {"mae": _mae(pairs), "n": len(pairs)}
            m = out[stat]["mae"]
            print(f"    [{name}] {stat.upper():4s} MAE={m:.4f}  n={len(pairs)}"
                  if m is not None else f"    [{name}] {stat.upper()} no preds", flush=True)
        return out

    print("\nEvaluating 2025-26 PLAYOFF bucket (all 7 stats)...", flush=True)
    playoff_metrics = eval_bucket(playoff_rows, "PO")

    print("\nEvaluating 2025-26 CONF-ROUND bucket (PTS only for speed)...", flush=True)
    confround_pts = []
    for r in confround_rows:
        p = predict_pergame("pts", r)
        if p is not None:
            confround_pts.append((float(p), float(r["target_pts"])))
    confround_pts_mae = _mae(confround_pts)
    print(f"    [CONF] PTS MAE={confround_pts_mae:.4f}  n={len(confround_pts)}"
          if confround_pts_mae is not None else "    [CONF] PTS no preds", flush=True)

    # Regular-season 2025-26 PTS MAE (same models, in-distribution baseline).
    print("\nEvaluating 2025-26 REGULAR-SEASON PTS (baseline)...", flush=True)
    rs_pts = []
    for r in rs_rows:
        p = predict_pergame("pts", r)
        if p is not None:
            rs_pts.append((float(p), float(r["target_pts"])))
    rs_pts_mae = _mae(rs_pts)
    print(f"    [RS] PTS MAE={rs_pts_mae:.4f}  n={len(rs_pts)}"
          if rs_pts_mae is not None else "    [RS] PTS no preds", flush=True)

    # ── Role-change blindness (playoff bucket) ──────────────────────────────
    print("\nRole-change split on PLAYOFF rows (actual min jump >= +30% vs L10)...", flush=True)
    role_change, stable = [], []
    missing_min = 0
    for r in playoff_rows:
        pid = r.get("player_id")
        d = datetime.fromisoformat(r["date"]).date().isoformat()
        actual_min = amap.get((pid, d))
        l10_min = float(r.get("l10_min", 0.0) or 0.0)
        if actual_min is None or l10_min < 1.0:
            missing_min += 1
            stable.append(r)  # treat unknown/no-baseline as stable (conservative)
            continue
        jump = (actual_min - l10_min) / l10_min
        (role_change if jump >= _ROLE_CHANGE_THRESHOLD else stable).append(r)

    def pts_mae_of(bucket):
        pairs = []
        for r in bucket:
            p = predict_pergame("pts", r)
            if p is not None:
                pairs.append((float(p), float(r["target_pts"])))
        return _mae(pairs), len(pairs)

    rc_mae, rc_n = pts_mae_of(role_change)
    st_mae, st_n = pts_mae_of(stable)
    print(f"    ROLE-CHANGE PTS MAE={rc_mae}  n={rc_n}", flush=True)
    print(f"    STABLE      PTS MAE={st_mae}  n={st_n}", flush=True)
    print(f"    (rows with no actual-min lookup, folded into stable: {missing_min})", flush=True)

    # Also report REB/AST role-change MAE (role changes drive all counting stats).
    role_change_other = {}
    for stat in ("reb", "ast"):
        rc_pairs, st_pairs = [], []
        for r in role_change:
            p = predict_pergame(stat, r)
            if p is not None:
                rc_pairs.append((float(p), float(r[f"target_{stat}"])))
        for r in stable:
            p = predict_pergame(stat, r)
            if p is not None:
                st_pairs.append((float(p), float(r[f"target_{stat}"])))
        role_change_other[stat] = {
            "role_change_mae": _mae(rc_pairs), "role_change_n": len(rc_pairs),
            "stable_mae": _mae(st_pairs), "stable_n": len(st_pairs),
        }

    result = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "method": (
            "Leak-free: build_pergame_dataset computes prior-only L5/L10/EWMA form + "
            "opp-defence-to-date; predict_pergame runs the prod q50/blend/calib/haircut/"
            "residual stack from data/models/*. No retraining. Playoff = game_date>=2026-04-13."
        ),
        "regular_season_claim_pts_mae": 4.62,
        "buckets": {
            "playoff_2025_26": {
                "definition": "game_date >= 2026-04-13 (incl play-in)",
                "per_stat": playoff_metrics,
            },
            "conf_round_2025_26": {
                "definition": "game_date >= 2026-04-19 (1st round onward, play-in excluded)",
                "pts_mae": confround_pts_mae,
                "pts_n": len(confround_pts),
            },
            "regular_season_2025_26": {
                "definition": "2025-10-01 <= game_date < 2026-04-13 (in-distribution baseline)",
                "pts_mae": rs_pts_mae,
                "pts_n": len(rs_pts),
            },
        },
        "role_change_blindness": {
            "definition": "actual game minutes >= +30% vs prior L10 minutes (model can't see it)",
            "threshold": _ROLE_CHANGE_THRESHOLD,
            "scope": "2025-26 playoff rows",
            "pts": {
                "role_change_mae": rc_mae, "role_change_n": rc_n,
                "stable_mae": st_mae, "stable_n": st_n,
            },
            "reb_ast": role_change_other,
            "rows_no_actual_min": missing_min,
        },
    }

    os.makedirs(_OUT_DIR, exist_ok=True)
    with open(_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nWrote {_OUT_PATH}", flush=True)
    return result


if __name__ == "__main__":
    main()
