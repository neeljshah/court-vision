"""HONEST walk-forward eval of the UNIFIED v2 clock-conditioned player-line head.

This scores the v2 design from ``src/ingame/continuous_projection.py``
(``train_player_lines_v2`` / ``UnifiedPlayerLineProjector``): ONE XGBoost per
player-stat trained over ALL event-state rows from the training games, with the
game clock (``game_remaining_min``, ``period``, ``played_share``) AS A MODEL
FEATURE, plus the leak-free POSSESSION / PACE-STATE columns the featurizer now
emits (``poss_per_48_so_far``, ``sec_since_last_fg``, ``run_last*_margin``,
``exp_poss_remaining``, bonus-state, ...). A single model therefore conditions on
the moment-in-game instead of needing a separate ridge per grid-bucket (v1).

It compares, per (stat, game-time bucket), held-out walk-forward, against BOTH:
  (a) the PRODUCTION box-snapshot projector  scripts.predict_in_game.project_snapshot
      (the real bar — same `baseline_player_snapshot` v1 uses)
  (b) the v1 per-grid-bucket ridge            (re-trained inline, identical to
      scripts/ingame/eval_second_by_second.py)
plus the pregame-L5 reference (C).

To isolate whether the PACE features help, we train TWO v2 variants on identical
rows / folds:
  * v2_core : clock + box-so-far + prior-form  (NO pace/momentum columns)
  * v2_pace : v2_core + the PACE_STATE columns merged from the game row
A (stat, bucket) cell is a v2 WIN only if it beats the PRODUCTION snapshot on the
held-out set. We also report whether v2 >= v1 and whether v2_pace extends the
winning range vs v2_core.

LEAK DISCIPLINE (unchanged from v1; HARD HONESTY RULES):
  * Event-state at grid point t uses ONLY events <= t in THIS game
    (src.ingame.state_featurizer.featurize_game; truncation-invariant, tested).
  * Walk-forward: v2 heads (and the v1 ridge) train ONLY on games with
    game_date < min(test fold dates). A test game is NEVER trained on.
  * Prior-form (p_prior_*) + the L5 reference use only gamelog rows < game_date.
  * Pace columns are pure functions of events <= t (and an optional prior-season
    pace game-constant) -> no future leak.
  * Labels: team finals from PBP last event (orientation cross-checked vs
    season_games.home_win, drop on mismatch); player finals from gamelog by
    (pid, GAME_DATE); pid from boxscore_adv roster, same-name collisions dropped.

Run (GPU auto, CPU fallback; subsample for speed -- SAY SO in the report):
    set NBA_OFFLINE=1
    python scripts/ingame/eval_sbs_v2.py --max-games 400 --folds 3
Outputs:
    .planning/ingame/eval_curve_v2.json
    .planning/ingame/eval_curve_v2.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("NBA_OFFLINE", "1")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import numpy as np  # noqa: E402

# Reuse the v1 harness machinery verbatim so the comparison is confound-free:
# same record reconstruction, same grid, same baselines, same v1 ridge math.
from scripts.ingame.eval_second_by_second import (  # noqa: E402
    GamelogStore, load_season_games, build_game_record,
    baseline_player_snapshot, _parse_iso_date,
    GRID_SEC, GRID_LABELS, PLAYER_STATS, TEAM_FEATS, PLAYER_BASE_FEATS,
    _ridge_fit, _ridge_pred,
)
from src.ingame.state_featurizer import discover_game_ids  # noqa: E402
from src.ingame.continuous_projection import (  # noqa: E402
    train_player_lines_v2, UnifiedPlayerLineProjector, _select_device,
    is_live_usage_enabled, compute_live_usg_vs_prior, LIVE_USAGE_FEATURE,
)

PLAN_DIR = os.path.join(ROOT, ".planning", "ingame")
os.makedirs(PLAN_DIR, exist_ok=True)


# --------------------------------------------------------------------------- #
# v2 feature schema -> built from (player_row + its game_row + L5 prior).
# The featurizer emits player rows with names like `pts`, `min_so_far`,
# `game_remaining_sec`; the GAME row carries the clock/score/pace state. We merge
# them into ONE v2 feature dict per (event, player). We define explicit feature
# lists (rather than the full FEATURES_PLAYER schema) so we control exactly which
# columns each variant sees and can attribute the pace lift cleanly.
# --------------------------------------------------------------------------- #

# clock features (MUST be present so one model conditions on game-time)
V2_CLOCK = ["game_remaining_min", "period", "played_share"]

# player box-so-far (current accumulation) + a couple game-state scalars
V2_BOX = [
    "p_min_so_far",
    "p_pts_so_far", "p_reb_so_far", "p_ast_so_far", "p_fg3m_so_far",
    "p_stl_so_far", "p_blk_so_far", "p_tov_so_far", "p_pf_so_far",
    "p_fga_so_far", "p_fgm_so_far", "p_on_court",
    "score_margin", "total_so_far",
]

# leak-free prior-form (L5 mean of player's games strictly before this date)
V2_PRIOR = [
    "p_prior_pts", "p_prior_reb", "p_prior_ast", "p_prior_fg3m",
    "p_prior_stl", "p_prior_blk", "p_prior_tov", "p_prior_min",
]

# POSSESSION / PACE-STATE columns merged from the game row (the v2-pace add-on).
V2_PACE = [
    "pace_poss_per_min", "poss_per_48_so_far", "sec_per_poss_so_far",
    "sec_since_last_fg", "sec_since_last_score",
    "run_last10_margin", "run_last5_margin",
    "home_in_bonus", "away_in_bonus",
    "exp_poss_remaining",
    "home_efg", "away_efg", "home_tov_pct", "away_tov_pct",
]

FEATURES_V2_CORE = V2_CLOCK + V2_BOX + V2_PRIOR
FEATURES_V2_PACE = FEATURES_V2_CORE + V2_PACE

# CV_INGAME_LIVE_USAGE: when ON, a live-usage-vs-expected feature is appended
# to the v2 feature vectors and a separate v2_usage variant is trained/evaluated.
# When OFF (default), no usage column is added and the evaluation is byte-identical
# to the non-usage path.  The v2_usage column is always built in _build_v2_row but
# is only INCLUDED in the feature list / training when the flag is ON.
_V2_USAGE = [LIVE_USAGE_FEATURE]
FEATURES_V2_USAGE = FEATURES_V2_PACE + _V2_USAGE


def _build_v2_row(prow: Dict[str, Any], grow: Dict[str, Any],
                  l5: Optional[Dict[str, float]]) -> Dict[str, float]:
    """Map one (player_row, game_row, L5-prior) into the v2 feature namespace.

    Pure function of leak-free inputs: the player/game rows are state<=t and L5
    is from games < game_date. No future info enters here.
    """
    grem_sec = float(grow.get("game_remaining_sec", 0) or 0)
    row: Dict[str, float] = {
        # clock
        "game_remaining_min": grem_sec / 60.0,
        "period": float(grow.get("period", 1) or 1),
        "played_share": float(grow.get("played_share", 0.0) or 0.0),
        # box-so-far
        "p_min_so_far": float(prow.get("min_so_far", 0) or 0),
        "p_pts_so_far": float(prow.get("pts", 0) or 0),
        "p_reb_so_far": float(prow.get("reb", 0) or 0),
        "p_ast_so_far": float(prow.get("ast", 0) or 0),
        "p_fg3m_so_far": float(prow.get("fg3m", 0) or 0),
        "p_stl_so_far": float(prow.get("stl", 0) or 0),
        "p_blk_so_far": float(prow.get("blk", 0) or 0),
        "p_tov_so_far": float(prow.get("tov", 0) or 0),
        "p_pf_so_far": float(prow.get("pf", 0) or 0),
        "p_fga_so_far": float(prow.get("fga", 0) or 0),
        "p_fgm_so_far": float(prow.get("fgm", 0) or 0),
        "p_on_court": 1.0 if prow.get("on_court") else 0.0,
        "score_margin": float(grow.get("score_margin", 0) or 0),
        "total_so_far": float(grow.get("home_score", 0) or 0)
                        + float(grow.get("away_score", 0) or 0),
        # pace-state merged from the game row
        "pace_poss_per_min": float(grow.get("pace_poss_per_min", 0) or 0),
        "poss_per_48_so_far": float(grow.get("poss_per_48_so_far", 0) or 0),
        "sec_per_poss_so_far": float(grow.get("sec_per_poss_so_far", 0) or 0),
        "sec_since_last_fg": float(grow.get("sec_since_last_fg", 0) or 0),
        "sec_since_last_score": float(grow.get("sec_since_last_score", 0) or 0),
        "run_last10_margin": float(grow.get("run_last10_margin", 0) or 0),
        "run_last5_margin": float(grow.get("run_last5_margin", 0) or 0),
        "home_in_bonus": float(grow.get("home_in_bonus", 0) or 0),
        "away_in_bonus": float(grow.get("away_in_bonus", 0) or 0),
        "exp_poss_remaining": float(grow.get("exp_poss_remaining", 0) or 0),
        "home_efg": float(grow.get("home_efg", 0) or 0),
        "away_efg": float(grow.get("away_efg", 0) or 0),
        "home_tov_pct": float(grow.get("home_tov_pct", 0) or 0),
        "away_tov_pct": float(grow.get("away_tov_pct", 0) or 0),
    }
    # prior-form (L5)
    for s in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "min"):
        row[f"p_prior_{s}"] = float(l5[s]) if (l5 and s in l5) else 0.0
    # CV_INGAME_LIVE_USAGE: live usage vs expected feature (always computed,
    # included in the feature list only when the flag is ON so existing model
    # training is byte-identical when OFF).
    side = prow.get("side", "home")
    pfx = "home" if side == "home" else "away"
    team_fga = float(grow.get(f"{pfx}_fga", 0) or 0)
    team_fta = float(grow.get(f"{pfx}_fta", 0) or 0)
    team_tov = float(grow.get(f"{pfx}_tov", 0) or 0)
    p_prior_usage = float(l5.get("usage", 0.0) if l5 else 0.0)
    # Compute a prior usage approximation from L5 FGA rate when dedicated
    # usage not in gamelog.  Using pts/(pts+eps) * 0.28 is too noisy; instead
    # proxy prior usage as L5_pts_per_min / league_avg_pts_per_min (19.0 per 48).
    if p_prior_usage == 0.0:
        prior_pts = float(l5["pts"] if l5 else 0.0)
        prior_min = float(l5["min"] if l5 else 0.0)
        LEAGUE_USG_PER_MIN = 1.0 / 10.0  # ~0.10 per active player average
        p_prior_usage = LEAGUE_USG_PER_MIN * (prior_pts / max(prior_min, 0.01)) / (
            19.0 / 48.0)
        p_prior_usage = max(0.0, min(0.50, p_prior_usage))
    row[LIVE_USAGE_FEATURE] = compute_live_usg_vs_prior(
        fga_so_far=float(prow.get("fga", 0) or 0),
        fta_so_far=0.0,  # FTA not in PBP player row; omit from numerator
        tov_so_far=float(prow.get("tov", 0) or 0),
        team_fga=team_fga,
        team_fta=team_fta,
        team_tov=team_tov,
        p_prior_usage=p_prior_usage,
        p_prior_pts=float(l5["pts"] if l5 else 0.0),
        p_prior_min=float(l5["min"] if l5 else 0.0),
        pts_so_far=float(prow.get("pts", 0) or 0),
        min_so_far=float(prow.get("min_so_far", 0) or 0),
    )
    return row


# --------------------------------------------------------------------------- #
# Training-frame assembly: ALL grid-event rows from a set of records.
# v2 trains ONE model across ALL buckets (clock is a feature), so we pool every
# grid point of every train game into one frame per stat.
# --------------------------------------------------------------------------- #
def _assemble_player_frame(records: List[Dict[str, Any]]):
    """Build a list-of-dicts frame: one row per (record, grid-t, player) with
    v2 features + final_<stat> targets + game_date (for the WF split inside
    train_player_lines_v2, though we drive folds ourselves here)."""
    import pandas as pd
    rows: List[Dict[str, Any]] = []
    for r in records:
        store = r["store"]
        for t, gd in r["grids"].items():
            grow = gd["game"]
            for (_team, _ln), prow in gd["players"].items():
                pid = prow.get("player_id")
                if pid is None or pid not in r["player_finals"]:
                    continue
                lab = r["player_finals"][pid]
                if lab.get("min", 0) <= 0:
                    continue
                l5 = store.l5_prior(pid, r["game_date"])
                fr = _build_v2_row(prow, grow, l5)
                for s in PLAYER_STATS:
                    fr[f"final_{s}"] = float(lab[s])
                fr["game_date"] = str(r["game_date"])
                fr["_grid_t"] = t
                rows.append(fr)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Main eval
# --------------------------------------------------------------------------- #
def run(max_games: int, folds: int, seed: int, min_train: int,
        num_boost_round: int, device: str) -> Dict[str, Any]:
    season_games = load_season_games()
    store = GamelogStore()

    all_ids = [g for g in discover_game_ids() if g in season_games]
    all_ids = [g for g in all_ids
               if _parse_iso_date(season_games[g].get("game_date") or "")]
    all_ids.sort(key=lambda g: season_games[g]["game_date"])

    n_total = len(all_ids)
    if max_games and n_total > max_games:
        idx = np.linspace(0, n_total - 1, max_games).astype(int)
        sampled = [all_ids[i] for i in sorted(set(idx.tolist()))]
    else:
        sampled = all_ids
    print(f"[v2-eval] {n_total} dated PBP games available; using {len(sampled)} "
          f"(chronological-even subsample={max_games})")

    records: List[Dict[str, Any]] = []
    n_fail = 0
    for i, gid in enumerate(sampled):
        try:
            rec = build_game_record(gid, season_games[gid], store)
        except Exception as exc:
            rec = None
            n_fail += 1
            if n_fail <= 5:
                print(f"  [warn] {gid}: {exc!r}")
        if rec is not None:
            records.append(rec)
        if (i + 1) % 50 == 0:
            print(f"  ...reconstructed {i+1}/{len(sampled)} ({len(records)} usable)")
    records.sort(key=lambda r: r["game_date"])
    print(f"[v2-eval] {len(records)} usable game records ({n_fail} failed)")
    if len(records) < min_train + 10:
        raise SystemExit(f"too few usable games ({len(records)}) for WF eval")

    dates = [r["game_date"] for r in records]
    uniq = sorted(set(dates))
    chunks = np.array_split(np.array(uniq, dtype=object), folds + 1)
    fold_test_dates = [set(chunks[k].tolist()) for k in range(1, folds + 1)]

    # accumulators: pacc[bucket][method][stat] -> list of abs errors (pooled WF)
    pacc = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    fold_summaries = []

    dev = device if device != "auto" else _select_device("cuda")
    print(f"[v2-eval] xgboost device = {dev}")

    for fold_i, test_dates in enumerate(fold_test_dates):
        train_recs = [r for r in records if r["game_date"] < min(test_dates)]
        test_recs = [r for r in records if r["game_date"] in test_dates]
        if len(train_recs) < min_train or not test_recs:
            continue
        print(f"[fold {fold_i}] train={len(train_recs)} test={len(test_recs)} "
              f"(test {min(test_dates)}..{max(test_dates)})")

        # ===== train v2 (core + pace) on ALL train grid-rows, ONE model/stat ===
        df_tr = _assemble_player_frame(train_recs)
        print(f"  [v2] train player-rows: {len(df_tr)}")
        proj_core, _ = train_player_lines_v2(
            df_tr, features=FEATURES_V2_CORE, walk_forward=False,
            num_boost_round=num_boost_round, device=dev, save=False,
        )
        proj_pace, _ = train_player_lines_v2(
            df_tr, features=FEATURES_V2_PACE, walk_forward=False,
            num_boost_round=num_boost_round, device=dev, save=False,
        )
        # CV_INGAME_LIVE_USAGE: train usage-enhanced variant when flag ON.
        # Byte-identical path when OFF (proj_usage is None; no usage error recorded).
        _use_live_usage = is_live_usage_enabled()
        proj_usage = None
        if _use_live_usage:
            print(f"  [v2-usage] CV_INGAME_LIVE_USAGE=ON; training usage variant")
            proj_usage, _ = train_player_lines_v2(
                df_tr, features=FEATURES_V2_USAGE, walk_forward=False,
                num_boost_round=num_boost_round, device=dev, save=False,
            )

        # ===== train v1 per-grid-bucket ridge (identical to v1 harness) =======
        player_w: Dict[int, Dict[str, np.ndarray]] = {}
        for t in GRID_SEC:
            Xp_by_stat = defaultdict(list)
            yp_by_stat = defaultdict(list)
            for r in train_recs:
                if t not in r["grids"]:
                    continue
                for (_team, _ln), prow in r["grids"][t]["players"].items():
                    pid = prow.get("player_id")
                    if pid is None or pid not in r["player_finals"]:
                        continue
                    lab = r["player_finals"][pid]
                    if lab.get("min", 0) <= 0:
                        continue
                    fv = [float(prow.get(f, 0) or 0) for f in PLAYER_BASE_FEATS]
                    for s in PLAYER_STATS:
                        Xp_by_stat[s].append(fv)
                        yp_by_stat[s].append(lab[s])
            if Xp_by_stat["pts"] and len(Xp_by_stat["pts"]) >= 50:
                player_w[t] = {}
                for s in PLAYER_STATS:
                    Xp = np.array(Xp_by_stat[s], dtype=np.float64)
                    player_w[t][s] = _ridge_fit(Xp, np.array(yp_by_stat[s]))

        # ===== evaluate on TEST (held-out) =====================================
        for r in test_recs:
            store_r = r["store"]
            for t, gd in r["grids"].items():
                grow = gd["game"]
                bucket = GRID_LABELS[t]
                for (_team, _ln), prow in gd["players"].items():
                    pid = prow.get("player_id")
                    if pid is None or pid not in r["player_finals"]:
                        continue
                    lab = r["player_finals"][pid]
                    if lab.get("min", 0) <= 0:
                        continue
                    pf = float(prow.get("pf", 0) or 0)
                    snap = baseline_player_snapshot(prow, grow, pf)
                    l5 = store_r.l5_prior(pid, r["game_date"])
                    v2row = _build_v2_row(prow, grow, l5)
                    proj_core_out = proj_core.project(_to_state(v2row))
                    proj_pace_out = proj_pace.project(_to_state(v2row))
                    v1_fv = None
                    if t in player_w:
                        v1_fv = np.array([[float(prow.get(f, 0) or 0)
                                           for f in PLAYER_BASE_FEATS]])
                    proj_usage_out = (
                        proj_usage.project(_to_state(v2row))
                        if proj_usage is not None else None
                    )
                    for s in PLAYER_STATS:
                        truth = lab[s]
                        pacc[bucket]["snapshot"][s].append(abs(snap[s] - truth))
                        if l5 is not None:
                            pacc[bucket]["pregame_l5"][s].append(abs(l5[s] - truth))
                        if v1_fv is not None:
                            cur = float(prow.get(s, 0) or 0)
                            v1p = float(_ridge_pred(player_w[t][s], v1_fv)[0])
                            pacc[bucket]["v1_ridge"][s].append(abs(max(cur, v1p) - truth))
                        pacc[bucket]["v2_core"][s].append(abs(proj_core_out[s] - truth))
                        pacc[bucket]["v2_pace"][s].append(abs(proj_pace_out[s] - truth))
                        if proj_usage_out is not None:
                            pacc[bucket]["v2_usage"][s].append(
                                abs(proj_usage_out[s] - truth))

        fold_summaries.append({
            "fold": fold_i, "n_train": len(train_recs), "n_test": len(test_recs),
            "test_date_min": str(min(test_dates)), "test_date_max": str(max(test_dates)),
        })

    return _summarize(pacc, fold_summaries, len(records), n_total, dev,
                      num_boost_round)


def _to_state(v2row: Dict[str, float]) -> Dict[str, float]:
    """v2 .project() floors at p_<stat>_so_far; the projector reads that key.
    Our v2 rows already use p_<stat>_so_far, so the row IS the state row."""
    return v2row


def _mean(xs):
    return float(np.mean(xs)) if xs else None


def _summarize(pacc, fold_summaries, n_records, n_total, dev, nbr) -> Dict[str, Any]:
    player_curve = {}
    for bucket in GRID_LABELS.values():
        if bucket not in pacc:
            continue
        per_stat = {}
        for s in PLAYER_STATS:
            per_stat[s] = {
                "n": len(pacc[bucket]["snapshot"][s]),
                "snapshot": _mean(pacc[bucket]["snapshot"][s]),
                "pregame_l5": _mean(pacc[bucket]["pregame_l5"][s]),
                "v1_ridge": _mean(pacc[bucket]["v1_ridge"][s]),
                "v2_core": _mean(pacc[bucket]["v2_core"][s]),
                "v2_pace": _mean(pacc[bucket]["v2_pace"][s]),
                "v2_usage": _mean(pacc[bucket]["v2_usage"][s]),
            }
        player_curve[bucket] = per_stat
    return {
        "meta": {
            "n_total_dated_pbp_games": n_total,
            "n_usable_records": n_records,
            "folds": fold_summaries,
            "grid_labels": GRID_LABELS,
            "device": dev,
            "num_boost_round": nbr,
            "v2_design": "ONE XGBoost per stat over ALL grid-event rows; clock "
                         "(game_remaining_min/period/played_share) is a MODEL "
                         "feature; floored at p_<stat>_so_far.",
            "v2_core_features": FEATURES_V2_CORE,
            "v2_pace_features": FEATURES_V2_PACE,
            "v2_usage_features": FEATURES_V2_USAGE,
            "live_usage_flag_on": is_live_usage_enabled(),
            "baselines": {
                "snapshot": "scripts.predict_in_game.project_snapshot (pace+foul) "
                            "= PRODUCTION bar",
                "v1_ridge": "per-grid-bucket ridge on 12 box features "
                            "(scripts/ingame/eval_second_by_second.py)",
                "pregame_l5": "mean of 5 games < game_date from gamelog",
            },
            "honesty": "held-out only; walk-forward (train dates < test dates); "
                       "labels PBP+gamelog; orientation cross-checked vs home_win; "
                       "v2 trained on ALL train grid-rows pooled across buckets.",
        },
        "player_curve": player_curve,
    }


def _fmt(v, nd=3):
    return f"{v:.{nd}f}" if isinstance(v, (int, float)) else " n/a "


def write_markdown(summary: Dict[str, Any], path: str) -> None:
    m = summary["meta"]
    L = ["# In-Game v2 (unified, clock+pace) — Honest Walk-Forward Player-Line Curve\n"]
    L.append(f"- Dated PBP games: **{m['n_total_dated_pbp_games']}**; usable "
             f"records: **{m['n_usable_records']}**; xgb device: **{m['device']}**; "
             f"rounds: {m['num_boost_round']}")
    L.append(f"- Folds (expanding-window, chronological): {len(m['folds'])}")
    for f in m["folds"]:
        L.append(f"  - fold {f['fold']}: train={f['n_train']} test={f['n_test']} "
                 f"({f['test_date_min']}..{f['test_date_max']})")
    L.append("- " + m["honesty"])
    L.append("- **v2 design:** " + m["v2_design"])
    L.append("- **bar = snapshot** (production box-snapshot projector). A cell is "
             "a v2 WIN only if v2 < snapshot on held-out.\n")

    usage_on = m.get("live_usage_flag_on", False)
    L.append("## Player lines — per-stat MAE (lower = better)\n")
    L.append("Methods: **snap**=production snapshot (BAR), **L5**=pregame mean, "
             "**v1**=per-bucket ridge, **v2c**=v2 core (clock+box+prior), "
             "**v2p**=v2 core+pace"
             + (", **v2u**=v2 core+pace+usage (CV_INGAME_LIVE_USAGE=ON)" if usage_on else "")
             + ". `win?` = does v2_pace beat snapshot.\n")
    for b in GRID_LABELS.values():
        if b not in summary["player_curve"]:
            continue
        L.append(f"### {b}\n")
        hdr = "| stat | n | snap | L5 | v1 | v2c | v2p |"
        sep = "|---|---|---|---|---|---|---|"
        if usage_on:
            hdr += " v2u |"
            sep += "---|"
        hdr += " best | v2p<snap | v2p<=v1 |"
        sep += "---|---|---|"
        L.append(hdr)
        L.append(sep)
        for s in PLAYER_STATS:
            d = summary["player_curve"][b][s]
            cands = {k: d[k] for k in ("snapshot", "pregame_l5", "v1_ridge",
                                       "v2_core", "v2_pace", "v2_usage")
                     if d.get(k) is not None}
            best = min(cands, key=cands.get) if cands else "n/a"
            bm = {"snapshot": "snap", "pregame_l5": "L5", "v1_ridge": "v1",
                  "v2_core": "v2c", "v2_pace": "v2p", "v2_usage": "v2u"}
            win = (d["v2_pace"] is not None and d["snapshot"] is not None
                   and d["v2_pace"] < d["snapshot"])
            ge_v1 = (d["v2_pace"] is not None and d["v1_ridge"] is not None
                     and d["v2_pace"] <= d["v1_ridge"])
            usage_cell = (f" {_fmt(d.get('v2_usage'))} |" if usage_on else "")
            L.append(
                f"| {s} | {d['n']} | {_fmt(d['snapshot'])} | {_fmt(d['pregame_l5'])} | "
                f"{_fmt(d['v1_ridge'])} | {_fmt(d['v2_core'])} | {_fmt(d['v2_pace'])} |"
                f"{usage_cell} "
                f"{bm.get(best, best)} | {'Y' if win else '.'} | "
                f"{'Y' if ge_v1 else '.'} |")
        L.append("")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=400,
                    help="chronological-even subsample size (0=all)")
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min-train", type=int, default=40)
    ap.add_argument("--rounds", type=int, default=300)
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    args = ap.parse_args()

    summary = run(args.max_games, args.folds, args.seed, args.min_train,
                  args.rounds, args.device)
    json_path = os.path.join(PLAN_DIR, "eval_curve_v2.json")
    md_path = os.path.join(PLAN_DIR, "eval_curve_v2.md")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    write_markdown(summary, md_path)
    print(f"\n[v2-eval] wrote {json_path}")
    print(f"[v2-eval] wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
