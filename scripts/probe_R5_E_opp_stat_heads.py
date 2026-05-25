"""scripts/probe_R5_E_opp_stat_heads.py -- R5-E opponent stat-specific allowed rates probe.

Treatment logic:
  1. Load opp_l5_per_stat.parquet into module-level cache.
  2. For each snap: get BASELINE(snap) (includes R2_F wired corrections).
  3. For each (pid, stat): compute the 21-feature vector (14 base + 7 opp-allowed L5),
     predict the v5 residual head, then swap: undo R2_F correction, apply v5 prediction.
  4. If a v5 head wasn't saved (failed WF gate), keep BASELINE value unchanged.

Heads live at:  data/models/residual_heads_v5_oppstat/{stat}.lgb
R2_F heads at:  data/models/residual_heads/{stat}.lgb

Usage:
    from scripts.probe_R5_E_opp_stat_heads import treatment
    from scripts.improve_loop.scaffold import run_endq3_probe
    run_endq3_probe("R5_E_opp_stat_heads", treatment)

CLI:
    python scripts/probe_R5_E_opp_stat_heads.py
    python scripts/probe_R5_E_opp_stat_heads.py --max-games 100
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from scripts.improve_loop.scaffold import run_endq3_probe, BASELINE  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

V5_HEAD_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_v5_oppstat")
R2F_HEAD_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads")
OPP_L5_PATH  = os.path.join(PROJECT_DIR, "data", "opp_l5_per_stat.parquet")

FEATURE_NAMES = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m",
    "cur_stl", "cur_blk", "cur_tov", "cur_pf",
    "min_through_q3", "score_margin_abs", "is_leading",
    "pos_C", "pos_F", "pos_G",
    "opp_l5_pts_allowed", "opp_l5_reb_allowed", "opp_l5_ast_allowed",
    "opp_l5_fg3m_allowed", "opp_l5_stl_allowed", "opp_l5_blk_allowed",
    "opp_l5_tov_allowed",
]

# Module-level caches (populated on first call)
_v5_heads: Dict[str, object] = {}
_r2f_heads: Dict[str, object] = {}
_positions: Optional[Dict[int, str]] = None
_opp_l5_index: Optional[Dict[Tuple[str, str], Dict[str, float]]] = None
_snap_date_cache: Dict[str, Optional[str]] = {}
_qstats_df = None


def _ensure_loaded() -> None:
    """Lazy-load all caches on first call to treatment()."""
    global _v5_heads, _r2f_heads, _positions, _opp_l5_index, _qstats_df

    if not _v5_heads:
        import lightgbm as lgb
        for stat in STATS:
            path = os.path.join(V5_HEAD_DIR, f"{stat}.lgb")
            if os.path.exists(path):
                try:
                    _v5_heads[stat] = lgb.Booster(model_file=path)
                except Exception as exc:
                    print(f"  WARN: could not load v5 {path}: {exc}")
        print(f"  [R5-E] loaded {len(_v5_heads)} v5 head(s)")

    if not _r2f_heads:
        import lightgbm as lgb
        for stat in STATS:
            path = os.path.join(R2F_HEAD_DIR, f"{stat}.lgb")
            if os.path.exists(path):
                try:
                    _r2f_heads[stat] = lgb.Booster(model_file=path)
                except Exception as exc:
                    print(f"  WARN: could not load R2_F {path}: {exc}")

    if _positions is None:
        from scripts.train_minute_trajectory import load_positions
        _positions = load_positions()

    if _opp_l5_index is None:
        import pandas as pd
        _opp_l5_index = {}
        if os.path.exists(OPP_L5_PATH):
            df = pd.read_parquet(OPP_L5_PATH)
            for _, row in df.iterrows():
                key = (str(row["team_abbreviation"]), str(row["game_date"]))
                _opp_l5_index[key] = {
                    s: float(row[f"opp_l5_{s}_allowed"])
                    for s in STATS
                    if f"opp_l5_{s}_allowed" in row.index
                }
        else:
            print(f"  WARN: {OPP_L5_PATH} not found — opp features will be zero")

    if _qstats_df is None:
        import retro_inplay_mae as v1
        _qstats_df = v1.load_quarter_stats()


def _get_game_date(game_id: str) -> Optional[str]:
    """Retrieve game_date for a game_id (cached)."""
    if game_id in _snap_date_cache:
        return _snap_date_cache[game_id]
    try:
        from train_minute_trajectory import load_player_gamelog_minutes, find_game_date_for_game
        import retro_inplay_mae as v1
        _ensure_loaded()  # ensure _qstats_df is ready
        pid_log = load_player_gamelog_minutes()
        d = find_game_date_for_game(game_id, _qstats_df, pid_log)
    except Exception:
        d = None
    _snap_date_cache[game_id] = d
    return d


def _pos_flags(pos_str: str) -> Tuple[float, float, float]:
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1.0, 0.0, 0.0
    if "F" in p and "C" not in p and "G" not in p:
        return 0.0, 1.0, 0.0
    if "G" in p and "F" not in p and "C" not in p:
        return 0.0, 0.0, 1.0
    return 0.0, 0.0, 0.0


def treatment(snap: dict) -> Dict[Tuple[int, str], float]:
    """Apply v5 opp-stat residual corrections on top of BASELINE projections.

    For each (pid, stat): if v5 head exists, undo R2_F correction and apply
    v5 prediction using the 21-feature vector. Falls back to BASELINE when
    no v5 head is available for that stat.
    """
    import numpy as np

    _ensure_loaded()

    base = BASELINE(snap)
    out: Dict[Tuple[int, str], float] = dict(base)

    if not _v5_heads:
        return out  # no heads trained yet

    home_pts  = float(snap.get("home_score", 0))
    away_pts  = float(snap.get("away_score", 0))
    margin    = abs(home_pts - away_pts)
    home_team = str(snap.get("home_team", ""))
    away_team = str(snap.get("away_team", ""))
    game_id   = str(snap.get("game_id", ""))
    game_date = _get_game_date(game_id)

    for player in snap.get("players", []):
        try:
            pid = int(player["player_id"])
        except (TypeError, ValueError):
            continue

        team = str(player.get("team", ""))
        if team == home_team:
            raw_margin = home_pts - away_pts
            opp_team   = away_team
        elif team == away_team:
            raw_margin = away_pts - home_pts
            opp_team   = home_team
        else:
            raw_margin = 0.0
            opp_team   = ""

        pos_c, pos_f, pos_g = _pos_flags((_positions or {}).get(pid, ""))

        # Opp L5 lookup
        opp_key   = (opp_team, game_date) if (opp_team and game_date) else None
        opp_feats = (_opp_l5_index or {}).get(opp_key, {}) if opp_key else {}

        # 14-feature base vector (same as R2_F training)
        base_vals = [
            float(player.get("pts",  0)),
            float(player.get("reb",  0)),
            float(player.get("ast",  0)),
            float(player.get("fg3m", 0)),
            float(player.get("stl",  0)),
            float(player.get("blk",  0)),
            float(player.get("tov",  0)),
            float(player.get("pf",   0)),
            float(player.get("min",  0)),
            margin,
            float(raw_margin > 0),
            pos_c, pos_f, pos_g,
        ]
        # 21-feature vector for v5 heads (14 base + 7 opp-allowed)
        feat_v5 = np.array([base_vals + [
            opp_feats.get("pts",  0.0),
            opp_feats.get("reb",  0.0),
            opp_feats.get("ast",  0.0),
            opp_feats.get("fg3m", 0.0),
            opp_feats.get("stl",  0.0),
            opp_feats.get("blk",  0.0),
            opp_feats.get("tov",  0.0),
        ]], dtype=np.float32)
        # 14-feature vector for R2_F undo step
        feat_r2f = np.array([base_vals], dtype=np.float32)

        for stat in STATS:
            v5_head = _v5_heads.get(stat)
            if v5_head is None:
                continue

            key = (pid, stat)
            baseline_val = base.get(key)
            if baseline_val is None:
                continue

            r2f_head = _r2f_heads.get(stat)
            cur_stat = float(player.get(stat, 0))

            # R2_F correction already baked into BASELINE — undo it (14 features)
            r2f_pred = float(r2f_head.predict(feat_r2f)[0]) if r2f_head is not None else 0.0

            # v5 correction (21 features)
            v5_pred  = float(v5_head.predict(feat_v5)[0])

            # Swap: baseline - r2f_pred + v5_pred
            adjusted = baseline_val - r2f_pred + v5_pred

            # Clip: non-negative, at most 2× original baseline
            lo = max(0.0, cur_stat)
            hi = max(0.0, 2.0 * baseline_val)
            adjusted = max(lo, min(hi, adjusted))
            adjusted = max(0.0, adjusted)

            out[key] = adjusted

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="R5-E opp-stat residual heads probe.")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    n_heads = sum(
        1 for s in STATS
        if os.path.exists(os.path.join(V5_HEAD_DIR, f"{s}.lgb"))
    )
    if n_heads == 0:
        print("  No v5 opp-stat heads found. Run train_residual_heads_v5_oppstat.py first.")
        return 1

    print(f"  {n_heads} v5 head(s) found. Running probe ...")
    run_endq3_probe(
        "R5_E_opp_stat_heads",
        treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
