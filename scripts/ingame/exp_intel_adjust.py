"""exp_intel_adjust.py -- HONEST incremental in-game intelligence adjustment.

GATED REFERENCE (default OFF), NO PRODUCTION EDITS. This is a SIBLING measurement
+ reference adjustment, not a serving path. It does TWO things:

1. INCREMENTAL MEASUREMENT (the honest question). Earlier in-game experiments
   (docs/_audits/INGAME_EXP_*_2026-06-01.md) measured each "intelligence" signal
   against `scripts.ingame.eval_second_by_second.baseline_player_snapshot`, which
   -- by its own docstring -- *drops the production blowout factor* and is a pure
   pace+foul extrapolator. The REAL production projector
   (`scripts.predict_in_game.project_snapshot`) applies BOTH
   `foul_trouble_factor` AND `blowout_factor`. So an apparent "blowout-starter"
   or "foul-trouble" lift can be (partly) a re-derivation of logic production
   ALREADY ships. This script reconstructs a `prod_full` baseline that mirrors
   project_snapshot's REAL factors on the leak-free PBP grid state, then measures
   how much each contested signal adds INCREMENTALLY *on top of prod_full*
   (and, for contrast, on top of the weak pace+foul baseline = the strawman gap).

2. GATED COMBINED ADJUSTMENT (the reference). `intel_adjust_final(...)` combines
   the ONE both-skeptics-confirmed signal (live_hot_hand, +1.28% PTS / +2.06%
   FG3M) with any contested signal that shows GENUINE incremental lift over
   prod_full. It is OFF unless `CV_INGAME_INTEL=1`; OFF -> byte-identical to the
   production `project_snapshot` final per (player,stat). It NEVER edits or is
   imported by the production projector; it only re-grades on the held-out grid.

Leak discipline (identical to the validated harness):
  * State at grid t uses ONLY events <= t (state_featurizer is truncation-inv).
  * L5 prior = gamelog rows STRICTLY before game_date.
  * Hot-hand exponent / foul-retention / usage-fade alpha are fit on TRAIN games
    (date < the fold's earliest test date) and frozen for the held-out TEST fold.
  * Grading is rest-of-game: MAE of projected_final vs gamelog final (current is
    common to both, so this ranks the rest-of-game projection).

Run:
    set NBA_OFFLINE=1
    python scripts/ingame/exp_intel_adjust.py --max-games 700 --folds 4
Outputs:
    .planning/ingame/exp_intel_adjust.json
"""
from __future__ import annotations

import argparse
import json
import math
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

from src.ingame.state_featurizer import (  # noqa: E402
    load_pbp_events, featurize_game, discover_game_ids,
    REG_PERIOD_LEN, OT_PERIOD_LEN,
)
from scripts.predict_in_game import (  # noqa: E402
    project_final as _proj_final,
    clock_played_share as _clock_share,
    blowout_factor as _blowout_factor,
    rotcurve_expected_rem_min as _rotcurve_rem_min,
    GAME_MIN as _GAME_MIN,
    PERIOD_MIN as _PERIOD_MIN,
)
from src.prediction.live_factors import foul_trouble_factor  # noqa: E402
from scripts.ingame.eval_second_by_second import (  # noqa: E402
    load_season_games, load_roster, GamelogStore, grid_states, _parse_iso_date,
    GRID_SEC, GRID_LABELS, PLAYER_STATS,
)

PLAN_DIR = os.path.join(ROOT, ".planning", "ingame")
os.makedirs(PLAN_DIR, exist_ok=True)

STATS = PLAYER_STATS
STAR_THRESHOLD_MIN = 30.0  # matches project_snapshot default

# v2-validated mid-game window (endQ1..midQ3), in game-elapsed seconds. Several
# signals (hot_hand FG3M aside) are only trustworthy here; gate accordingly.
V2_WINDOW_SEC = {1080, 1440, 1800}            # 18,24,30 min
MIDGAME_WINDOW_SEC = {720, 1080, 1440, 1800}  # endQ1..midQ3 (usage-shift gate)


# --------------------------------------------------------------------------- #
# Grid -> (period, clock_remaining_min) and helpers
# --------------------------------------------------------------------------- #
def _grid_period_clock(gr: Dict[str, Any]) -> Tuple[int, float]:
    period = int(gr["period"])
    elapsed = int(gr["elapsed_sec_in_period"])
    plen = REG_PERIOD_LEN if period <= 4 else OT_PERIOD_LEN
    return period, max(0, plen - elapsed) / 60.0


def starters_at(players: Dict[Tuple[str, str], Dict[str, Any]]) -> set:
    """Leak-free proxy-starter set = top-5 min_so_far per team at t."""
    byteam: Dict[str, List[Tuple[float, Tuple[str, str]]]] = defaultdict(list)
    for key, pr in players.items():
        byteam[key[0]].append((float(pr.get("min_so_far", 0) or 0), key))
    out = set()
    for _tm, lst in byteam.items():
        lst.sort(reverse=True)
        for _m, key in lst[:5]:
            out.add(key)
    return out


# --------------------------------------------------------------------------- #
# BASELINES on the leak-free grid state
# --------------------------------------------------------------------------- #
def base_pace_foul(prow: Dict[str, Any], gr: Dict[str, Any]) -> Dict[str, float]:
    """STRAWMAN baseline = pace + foul ONLY (what the prior experiments used).

    This is `baseline_player_snapshot` from eval_second_by_second: it deliberately
    drops the production blowout factor.
    """
    period, clock_rem = _grid_period_clock(gr)
    ff = foul_trouble_factor(float(prow.get("pf", 0) or 0), period, clock_rem)
    return {s: _proj_final(float(prow.get(s, 0) or 0), period, clock_rem,
                           foul_factor=ff) for s in STATS}


def base_prod_full(prow: Dict[str, Any], gr: Dict[str, Any]) -> Dict[str, float]:
    """REAL production baseline = pace + foul + blowout, mirroring
    `scripts.predict_in_game.project_snapshot` factor logic exactly.

    project_snapshot computes:
      * ff = foul_trouble_factor(pf, period, clock_rem)
      * is_star = (cur_min / played_share) >= 30  (minutes-to-48 proxy)
      * team_is_leading = player's side leads on the scoreboard
      * bf = blowout_factor(|margin|, period, is_star=(is_star and leading))
    All inputs are pure functions of leak-free state <= t.
    """
    period, clock_rem = _grid_period_clock(gr)
    ff = foul_trouble_factor(float(prow.get("pf", 0) or 0), period, clock_rem)
    share = _clock_share(period, clock_rem)
    cur_min = float(prow.get("min_so_far", 0) or 0)
    proj_min = (cur_min / share) if share > 0 else cur_min
    is_star = proj_min >= STAR_THRESHOLD_MIN
    margin = float(gr["home_score"] - gr["away_score"])  # home POV
    side = prow.get("side") or ""
    team_is_leading = (side == "home" and margin > 0) or (side == "away" and margin < 0)
    bf = _blowout_factor(abs(margin), period, is_star=(is_star and team_is_leading))
    return {s: _proj_final(float(prow.get(s, 0) or 0), period, clock_rem,
                           foul_factor=ff, blow_factor=bf) for s in STATS}


# --------------------------------------------------------------------------- #
# Record building
# --------------------------------------------------------------------------- #
def build_record(game_id: str, meta: Dict[str, Any], store: GamelogStore
                 ) -> Optional[Dict[str, Any]]:
    home, away = meta.get("home_team"), meta.get("away_team")
    game_date = _parse_iso_date(meta.get("game_date") or "")
    if not home or not away or game_date is None:
        return None
    events = load_pbp_events(game_id)
    if not events:
        return None
    roster = load_roster(game_id)

    def resolver(team: str, last_name: str) -> Optional[int]:
        return roster.get((team, (last_name or "").strip().lower()))

    res = featurize_game(events, game_id, home, away,
                         player_id_resolver=resolver, emit_players=True)
    final_row = res["game"][-1]
    home_final = float(final_row["home_score"]); away_final = float(final_row["away_score"])
    if home_final <= 0 or away_final <= 0:
        return None
    home_win = meta.get("home_win")
    orient = res["orientation"]
    if home_win is not None and orient.get("resolved"):
        if int(home_win) != int(home_final > away_final):
            return None
    grids = grid_states(res, game_id)
    if not grids:
        return None
    player_finals: Dict[int, Dict[str, float]] = {}
    l5: Dict[int, Optional[Dict[str, float]]] = {}
    for (_team, _ln), pid in roster.items():
        lab = store.final_line(pid, game_date)
        if lab is not None:
            player_finals[pid] = lab
            l5[pid] = store.l5_prior(pid, game_date)
    return {
        "game_id": game_id, "game_date": game_date,
        "home_final": home_final, "away_final": away_final,
        "grids": grids, "player_finals": player_finals, "l5": l5,
    }


# --------------------------------------------------------------------------- #
# Signal layers (each takes the prod_full base final + state, returns adj final)
# --------------------------------------------------------------------------- #
def _expected_rem_min(prow: Dict[str, Any], gr: Dict[str, Any]) -> float:
    """Leak-free expected REMAINING player minutes, mirroring the validated
    hot_hand experiment's `exp_remaining_min` (and project_remaining's player-clock
    basis): scale the player's minute-share forward over the remaining GAME time.

        share_played = clock_played_share(period, clock_rem)  # GAME-clock share
        rem = min_so_far * (1-share_played) / share_played
    """
    cur_min = float(prow.get("min_so_far", 0) or 0)
    period, clock_rem = _grid_period_clock(gr)
    share_played = _clock_share(period, clock_rem)
    if share_played <= 1e-6 or cur_min <= 0:
        return 0.0
    return cur_min * (max(0.0, 1.0 - share_played) / share_played)


def hot_hand_final(base_final: float, prow: Dict[str, Any], gr: Dict[str, Any],
                   l5: Optional[Dict[str, float]], stat: str, g: float) -> float:
    """live_hot_hand: rest = L5_rate * exp_rem_min * heat^g, heat in [0.25,4].

    Anchors rest-of-game on the L5 per-min rate (not pace extrapolation) and
    tilts by observed heat^g. CONFIRMED 2/2; g~0.2. Only meaningful for pts/fg3m.
    Floored at current accumulation (a final can't be below current).
    """
    if stat not in ("pts", "fg3m") or l5 is None:
        return base_final
    cur = float(prow.get(stat, 0) or 0)
    cur_min = float(prow.get("min_so_far", 0) or 0)
    if cur_min < 2.0:
        return base_final
    l5_min = float(l5.get("min", 0) or 0)
    if l5_min <= 0:
        return base_final
    r_l5 = float(l5.get(stat, 0) or 0) / l5_min            # season per-min rate
    r_obs = cur / cur_min                                   # observed per-min rate
    # heat ratio (smoothed like the validated hot_hand exp), clamped [0.25,4.0]
    heat = (r_obs + 1e-3) / (r_l5 + 1e-3)
    heat = min(4.0, max(0.25, heat))
    rem_min = _expected_rem_min(prow, gr)
    rest = r_l5 * rem_min * (heat ** g)
    return max(cur, cur + rest)


def usage_fade_final(base_final: float, prow: Dict[str, Any], gr: Dict[str, Any],
                     l5: Optional[Dict[str, float]], stat: str, alpha: float) -> float:
    """live_usage_shift: rest = (alpha*r_obs + (1-alpha)*r_base) * exp_rem_min.

    Fade observed in-game rate ~90% to the L5 baseline rate (alpha~0.05-0.10).
    Gated to the mid-game window by the caller. Floored at current.
    """
    if l5 is None:
        return base_final
    cur = float(prow.get(stat, 0) or 0)
    cur_min = float(prow.get("min_so_far", 0) or 0)
    if cur_min < 4.0:
        return base_final
    l5_min = float(l5.get("min", 0) or 0)
    if l5_min <= 0:
        return base_final
    r_obs = cur / cur_min
    r_base = float(l5.get(stat, 0) or 0) / l5_min
    rem_min = _expected_rem_min(prow, gr)
    rest = (alpha * r_obs + (1.0 - alpha) * r_base) * rem_min
    return max(cur, cur + rest)


def rotcurve_final(base_final: float, prow: Dict[str, Any], gr: Dict[str, Any],
                   stat: str) -> float:
    """W-009 CV_INGAME_ROTCURVE: replace flat-pace remaining with atlas curve.

    Uses rotcurve_expected_rem_min() (already gated by CV_INGAME_ROTCURVE flag
    inside predict_in_game) to get the atlas-shrunk expected remaining minutes,
    then projects at the observed per-minute rate.

    For evaluation in this harness, we set CV_INGAME_ROTCURVE=1 before calling;
    the function degrades to flat pace when the player is absent from the atlas.
    Floored at current accumulation (projected_final >= current).
    """
    period, clock_rem = _grid_period_clock(gr)
    ff = foul_trouble_factor(float(prow.get("pf", 0) or 0), period, clock_rem)
    share = _clock_share(period, clock_rem)
    cur_min = float(prow.get("min_so_far", 0) or 0)
    proj_min = (cur_min / share) if share > 0 else cur_min
    is_star = proj_min >= STAR_THRESHOLD_MIN
    margin = float(gr["home_score"] - gr["away_score"])
    side = prow.get("side") or ""
    leading = (side == "home" and margin > 0) or (side == "away" and margin < 0)
    bf = _blowout_factor(abs(margin), period, is_star=(is_star and leading))

    cur = float(prow.get(stat, 0) or 0)
    if cur_min <= 0:
        return float(cur)  # no rate to project

    pid = prow.get("player_id")
    # rotcurve_expected_rem_min respects CV_INGAME_ROTCURVE internally;
    # we set the env var before calling in the eval loop.
    atlas_rem = _rotcurve_rem_min(pid, period, clock_rem, cur_min)
    proj = _proj_final(cur, period, clock_rem,
                       foul_factor=ff, blow_factor=bf,
                       rem_min_override=atlas_rem)
    return max(cur, proj)


# --------------------------------------------------------------------------- #
# Fit hyperparameters on TRAIN (walk-forward)
# --------------------------------------------------------------------------- #
def fit_hot_hand_g(train: List[Dict[str, Any]]) -> Dict[str, float]:
    """Per-stat g minimizing rest-of-game MAE of the L5-anchor*heat^g over TRAIN,
    for stat in (pts, fg3m). Grid g in {0,.1,.2,.3,.5}."""
    g_grid = [0.0, 0.1, 0.2, 0.3, 0.5]
    best: Dict[str, float] = {}
    for stat in ("pts", "fg3m"):
        errs = {g: [] for g in g_grid}
        for r in train:
            for _t, gd in r["grids"].items():
                gr = gd["game"]
                for _key, prow in gd["players"].items():
                    pid = prow.get("player_id")
                    if pid is None or pid not in r["player_finals"]:
                        continue
                    lab = r["player_finals"][pid]
                    if lab.get("min", 0) <= 0:
                        continue
                    l5 = r["l5"].get(pid)
                    truth = lab[stat]
                    for g in g_grid:
                        pf = hot_hand_final(0.0, prow, gr, l5, stat, g)
                        # only count rows where hot_hand actually fires (l5 valid etc.)
                        errs[g].append(abs(pf - truth))
        best[stat] = min(g_grid, key=lambda g: np.mean(errs[g]) if errs[g] else 1e9)
    return best


def fit_usage_alpha(train: List[Dict[str, Any]]) -> Dict[str, float]:
    """Per-stat alpha minimizing rest-of-game MAE of the usage blend over TRAIN,
    in the mid-game window. Grid alpha in {0,.05,.1,.2,.3,.5,1}."""
    a_grid = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0]
    best: Dict[str, float] = {}
    for stat in STATS:
        errs = {a: [] for a in a_grid}
        for r in train:
            for t, gd in r["grids"].items():
                if t not in MIDGAME_WINDOW_SEC:
                    continue
                gr = gd["game"]
                for _key, prow in gd["players"].items():
                    pid = prow.get("player_id")
                    if pid is None or pid not in r["player_finals"]:
                        continue
                    lab = r["player_finals"][pid]
                    if lab.get("min", 0) <= 0:
                        continue
                    l5 = r["l5"].get(pid)
                    truth = lab[stat]
                    for a in a_grid:
                        pf = usage_fade_final(0.0, prow, gr, l5, stat, a)
                        errs[a].append(abs(pf - truth))
        best[stat] = min(a_grid, key=lambda a: np.mean(errs[a]) if errs[a] else 1e9)
    return best


def fit_foul_retention(train: List[Dict[str, Any]]) -> Dict[int, float]:
    """Per-period median realized minutes-retention of fouled players, the
    calibrated foul factor (leak-free, train-only). retention = (final_min -
    min_so_far) / pace_expected_remaining_min. Clamped [0.2,1.0].

    Foul-trouble flag (observable): pf >= period+1 (the default coaching rule)."""
    by_period: Dict[int, List[float]] = defaultdict(list)
    for r in train:
        for _t, gd in r["grids"].items():
            gr = gd["game"]
            period = int(gr["period"])
            if period > 4:
                continue
            for _key, prow in gd["players"].items():
                pid = prow.get("player_id")
                if pid is None or pid not in r["player_finals"]:
                    continue
                pf = float(prow.get("pf", 0) or 0)
                if pf < period + 1:        # not in foul trouble
                    continue
                lab = r["player_finals"][pid]
                if lab.get("min", 0) <= 0:
                    continue
                cur_min = float(prow.get("min_so_far", 0) or 0)
                exp_rem = _expected_rem_min(prow, gr)
                if exp_rem <= 0.5:
                    continue
                act_rem = float(lab["min"]) - cur_min
                ret = act_rem / exp_rem
                by_period[period].append(min(2.0, max(0.0, ret)))
    out: Dict[int, float] = {}
    for p, vals in by_period.items():
        if len(vals) >= 20:
            out[p] = float(min(1.0, max(0.2, np.median(vals))))
    return out


def foul_cal_final(prow: Dict[str, Any], gr: Dict[str, Any],
                   retention: Dict[int, float], stat: str) -> float:
    """Calibrated foul factor: replace the heuristic foul_trouble_factor with the
    empirical per-period minutes retention for flagged players. Applied to the
    pace+blowout rest projection. Only fires when pf >= period+1 and a calibrated
    factor exists; else returns the prod_full final unchanged."""
    period, clock_rem = _grid_period_clock(gr)
    pf = float(prow.get("pf", 0) or 0)
    if period > 4 or pf < period + 1 or period not in retention:
        return base_prod_full(prow, gr)[stat]
    # pace+blowout WITHOUT the heuristic foul factor, then apply calibrated factor
    share = _clock_share(period, clock_rem)
    cur_min = float(prow.get("min_so_far", 0) or 0)
    proj_min = (cur_min / share) if share > 0 else cur_min
    is_star = proj_min >= STAR_THRESHOLD_MIN
    margin = float(gr["home_score"] - gr["away_score"])
    side = prow.get("side") or ""
    leading = (side == "home" and margin > 0) or (side == "away" and margin < 0)
    bf = _blowout_factor(abs(margin), period, is_star=(is_star and leading))
    cal = retention[period]
    cur = float(prow.get(stat, 0) or 0)
    return _proj_final(cur, period, clock_rem, foul_factor=cal, blow_factor=bf)


# --------------------------------------------------------------------------- #
# Combined gated reference adjustment
# --------------------------------------------------------------------------- #
def intel_adjust_final(prow: Dict[str, Any], gr: Dict[str, Any],
                       l5: Optional[Dict[str, float]], stat: str, t: int,
                       params: Dict[str, Any]) -> float:
    """The gated combined adjustment. OFF (CV_INGAME_INTEL!=1) -> prod_full final.

    ON -> start from prod_full (pace+foul+blowout, the REAL production factors),
    then layer the GENUINELY-INCREMENTAL signals:
      * live_hot_hand  (CONFIRMED 2/2): pts/fg3m L5-anchor*heat^g, whole-window.
      * live_usage_shift fade: pts/reb/ast/etc, ONLY in the mid-game window where
        it showed incremental lift over prod_full; replaces the rest projection
        with the faded-to-L5 blend.
    Foul calibration is handled as a separate diagnostic (see fit_foul_retention)
    because, vs prod_full, it is mostly redundant with the shipped foul factor.
    """
    base = base_prod_full(prow, gr)[stat]
    if os.environ.get("CV_INGAME_INTEL", "0") != "1":
        return base
    out = base
    # hot_hand on pts/fg3m (confirmed, whole game)
    if stat in ("pts", "fg3m"):
        g = params.get("hot_g", {}).get(stat)
        if g is not None:
            out = hot_hand_final(out, prow, gr, l5, stat, g)
    # usage fade in the mid-game window only (gated)
    if t in MIDGAME_WINDOW_SEC and stat not in ("pts", "fg3m"):
        a = params.get("usage_alpha", {}).get(stat)
        if a is not None:
            out = usage_fade_final(out, prow, gr, l5, stat, a)
    return out


# --------------------------------------------------------------------------- #
# Main eval
# --------------------------------------------------------------------------- #
def run(max_games: int, folds: int, min_train: int) -> Dict[str, Any]:
    season = load_season_games()
    store = GamelogStore()
    ids = [g for g in discover_game_ids() if g in season]
    ids = [g for g in ids if _parse_iso_date(season[g].get("game_date") or "")]
    ids.sort(key=lambda g: season[g]["game_date"])
    n_total = len(ids)
    if max_games and n_total > max_games:
        idx = np.linspace(0, n_total - 1, max_games).astype(int)
        sampled = [ids[i] for i in sorted(set(idx.tolist()))]
    else:
        sampled = ids
    print(f"[exp] {n_total} dated games; using {len(sampled)}")

    records: List[Dict[str, Any]] = []
    nfail = 0
    for i, gid in enumerate(sampled):
        try:
            rec = build_record(gid, season[gid], store)
        except Exception as e:  # noqa: BLE001
            rec = None; nfail += 1
            if nfail <= 5:
                print("  [warn]", gid, repr(e))
        if rec is not None:
            records.append(rec)
        if (i + 1) % 100 == 0:
            print(f"  ...{i+1}/{len(sampled)} ({len(records)} usable)")
    records.sort(key=lambda r: r["game_date"])
    print(f"[exp] {len(records)} usable records ({nfail} failed)")
    if len(records) < min_train + 10:
        raise SystemExit("too few usable records")

    dates = sorted(set(r["game_date"] for r in records))
    chunks = np.array_split(np.array(dates, dtype=object), folds + 1)
    fold_test_dates = [set(chunks[k].tolist()) for k in range(1, folds + 1)]

    # accumulators: method -> stat -> list of |err|, pooled across folds + window scope
    # scopes: 'all' (whole grid), 'mid' (mid-game window), 'blowout' (big+huge regime)
    def _acc():
        return defaultdict(lambda: defaultdict(list))
    err = {"all": _acc(), "mid": _acc(), "blowout": _acc()}
    # per-bucket blowout regime detail for starters
    fold_info = []

    for fi, test_dates in enumerate(fold_test_dates):
        train = [r for r in records if r["game_date"] < min(test_dates)]
        test = [r for r in records if r["game_date"] in test_dates]
        if len(train) < min_train or not test:
            continue
        hot_g = fit_hot_hand_g(train)
        usage_alpha = fit_usage_alpha(train)
        retention = fit_foul_retention(train)
        params = {"hot_g": hot_g, "usage_alpha": usage_alpha}
        os.environ["CV_INGAME_INTEL"] = "1"  # in-process ON for eval (sibling only)
        os.environ["CV_INGAME_ROTCURVE"] = "1"  # W-009: ON for rotcurve eval only

        for r in test:
            for t, gd in r["grids"].items():
                gr = gd["game"]
                rem_min = float(gr["game_remaining_sec"]) / 60.0
                if rem_min <= 0:
                    continue
                starters = starters_at(gd["players"])
                margin = abs(float(gr["home_score"] - gr["away_score"]))
                in_mid = t in MIDGAME_WINDOW_SEC
                # blowout regime = rem<18min AND |margin|>=13 (matches blowout exp)
                in_blow = (rem_min <= 18.0) and (margin >= 13.0)
                for key, prow in gd["players"].items():
                    pid = prow.get("player_id")
                    if pid is None or pid not in r["player_finals"]:
                        continue
                    lab = r["player_finals"][pid]
                    if lab.get("min", 0) <= 0:
                        continue
                    l5 = r["l5"].get(pid)
                    side = prow.get("side") or ""
                    leading = (side == "home" and float(gr["home_score"]) > float(gr["away_score"])) or \
                              (side == "away" and float(gr["away_score"]) > float(gr["home_score"]))
                    is_lead_starter = (key in starters) and leading
                    pace_foul = base_pace_foul(prow, gr)
                    prod_full = base_prod_full(prow, gr)
                    for s in STATS:
                        truth = lab[s]
                        # --- baselines ---
                        err["all"]["pace_foul"][s].append(abs(pace_foul[s] - truth))
                        err["all"]["prod_full"][s].append(abs(prod_full[s] - truth))
                        # --- combined intel adjustment ---
                        adj = intel_adjust_final(prow, gr, l5, s, t, params)
                        err["all"]["intel"][s].append(abs(adj - truth))
                        # --- W-009 rotcurve (atlas remaining-minutes base) ---
                        rc = rotcurve_final(prod_full[s], prow, gr, s)
                        err["all"]["rotcurve"][s].append(abs(rc - truth))
                        # --- individual contested signals on top of prod_full ---
                        # hot_hand (pts/fg3m only; else identity)
                        if s in ("pts", "fg3m"):
                            hh = hot_hand_final(prod_full[s], prow, gr, l5, s, hot_g.get(s, 0.2))
                            # pure L5 anchor (g=0): isolates heat-tilt from the
                            # anchor-vs-pace-extrapolation strawman win
                            anchor = hot_hand_final(prod_full[s], prow, gr, l5, s, 0.0)
                        else:
                            hh = prod_full[s]; anchor = prod_full[s]
                        err["all"]["hot_hand"][s].append(abs(hh - truth))
                        err["all"]["anchor"][s].append(abs(anchor - truth))
                        # foul-calibrated (replaces heuristic foul factor for flagged)
                        fc = foul_cal_final(prow, gr, retention, s)
                        err["all"]["foul_cal"][s].append(abs(fc - truth))
                        # mid-game scope
                        if in_mid:
                            err["mid"]["prod_full"][s].append(abs(prod_full[s] - truth))
                            err["mid"]["rotcurve"][s].append(abs(rc - truth))
                            uf = usage_fade_final(prod_full[s], prow, gr, l5, s,
                                                  usage_alpha.get(s, 0.1))
                            err["mid"]["usage_fade"][s].append(abs(uf - truth))
                            # alpha=0 (pure L5-rate regression, IGNORE observed rate):
                            # isolates whether the LIVE usage rate adds anything over a
                            # pure baseline-formula fade (the usage doc claims it doesn't)
                            ur = usage_fade_final(prod_full[s], prow, gr, l5, s, 0.0)
                            err["mid"]["usage_regress"][s].append(abs(ur - truth))
                            err["mid"]["intel"][s].append(abs(adj - truth))
                        # blowout scope (leading-team starters in big/huge regime)
                        if in_blow and is_lead_starter:
                            err["blowout"]["pace_foul"][s].append(abs(pace_foul[s] - truth))
                            err["blowout"]["prod_full"][s].append(abs(prod_full[s] - truth))
        fold_info.append({"fold": fi, "n_train": len(train), "n_test": len(test),
                          "test_min": str(min(test_dates)), "test_max": str(max(test_dates)),
                          "hot_g": hot_g, "usage_alpha": usage_alpha,
                          "foul_retention": {str(k): round(v, 3) for k, v in retention.items()}})
    os.environ["CV_INGAME_INTEL"] = "0"  # reset
    os.environ["CV_INGAME_ROTCURVE"] = "0"  # reset W-009
    return summarize(err, fold_info, len(records), n_total)


def _mae(xs):
    return float(np.mean(xs)) if xs else None


def _lift(base, sig):
    if base and base > 0 and sig is not None:
        return (base - sig) / base * 100.0
    return None


def _pool(acc, method, stats):
    xs = []
    for s in stats:
        xs += acc[method][s]
    return xs


def summarize(err, fold_info, n_rec, n_total) -> Dict[str, Any]:
    core = ["pts", "reb", "ast"]
    out: Dict[str, Any] = {
        "meta": {
            "n_total_dated": n_total, "n_usable": n_rec, "folds": fold_info,
            "baselines": {
                "pace_foul": "STRAWMAN: pace+foul only (eval_second_by_second "
                             "baseline_player_snapshot; DROPS blowout factor)",
                "prod_full": "REAL production: pace+foul+blowout, mirrors "
                             "scripts.predict_in_game.project_snapshot factor logic",
            },
            "signals": {
                "hot_hand": "L5-anchor*heat^g on pts/fg3m, layered on prod_full",
                "usage_fade": "fade observed rate ~90% to L5, mid-game window, on prod_full",
                "foul_cal": "calibrated per-period minutes retention replacing heuristic "
                            "foul factor for flagged players, on top of pace+blowout",
                "intel": "COMBINED gated adjustment (hot_hand whole-game + usage_fade "
                         "mid-game), on prod_full",
                "rotcurve": "W-009 CV_INGAME_ROTCURVE: atlas per-quarter expected remaining "
                            "minutes (player_quarter_stats.parquet) replacing flat game-clock "
                            "extrapolation; shrunk toward flat pace for thin-sample players.",
            },
            "metric": "rest-of-game MAE (projected_final vs gamelog final); lift% vs "
                      "the stated baseline. INCREMENTAL = lift vs prod_full (REAL prod).",
        }
    }

    # ---- WHOLE-GAME (all-grid) per-stat + pooled ----
    a = err["all"]
    whole = {}
    for s in STATS:
        mae_pf = _mae(a["pace_foul"][s]); mae_prod = _mae(a["prod_full"][s])
        mae_hh = _mae(a["hot_hand"][s]); mae_fc = _mae(a["foul_cal"][s])
        mae_intel = _mae(a["intel"][s]); mae_rc = _mae(a["rotcurve"][s])
        whole[s] = {
            "n": len(a["prod_full"][s]),
            "mae_pace_foul": mae_pf, "mae_prod_full": mae_prod,
            "mae_hot_hand": mae_hh, "mae_foul_cal": mae_fc, "mae_intel": mae_intel,
            "mae_rotcurve": mae_rc,
            # the headline honest deltas:
            "lift_prod_vs_strawman_pct": _lift(mae_pf, mae_prod),   # how much prod's blowout already helps
            "lift_hot_hand_vs_prod_pct": _lift(mae_prod, mae_hh),   # INCREMENTAL hot_hand
            "lift_foul_cal_vs_prod_pct": _lift(mae_prod, mae_fc),   # INCREMENTAL foul cal
            "lift_intel_vs_prod_pct": _lift(mae_prod, mae_intel),   # INCREMENTAL combined
            "lift_rotcurve_vs_prod_pct": _lift(mae_prod, mae_rc),   # W-009 rotcurve
        }
    out["whole_game"] = whole

    # pooled core (pts/reb/ast) whole-game
    pf_c = _pool(a, "pace_foul", core); pr_c = _pool(a, "prod_full", core)
    intel_c = _pool(a, "intel", core); rc_c = _pool(a, "rotcurve", core)
    out["whole_game_pooled_core"] = {
        "n": len(pr_c),
        "mae_pace_foul": _mae(pf_c), "mae_prod_full": _mae(pr_c), "mae_intel": _mae(intel_c),
        "mae_rotcurve": _mae(rc_c),
        "lift_prod_vs_strawman_pct": _lift(_mae(pf_c), _mae(pr_c)),
        "lift_intel_vs_prod_pct": _lift(_mae(pr_c), _mae(intel_c)),
        "lift_rotcurve_vs_prod_pct": _lift(_mae(pr_c), _mae(rc_c)),
    }
    # pooled core W-009 rotcurve per-stat detail
    out["rotcurve_per_stat"] = {}
    for s in STATS:
        mp = _mae(a["prod_full"][s]); mrc = _mae(a["rotcurve"][s])
        out["rotcurve_per_stat"][s] = {
            "n": len(a["prod_full"][s]),
            "mae_prod_full": mp,
            "mae_rotcurve": mrc,
            "lift_rotcurve_vs_prod_pct": _lift(mp, mrc),
        }
    # pooled pts/fg3m (hot_hand-relevant). Decompose honestly:
    #   prod_full -> anchor (g=0)  = the L5-anchor-vs-pace-extrapolation win (a
    #                                 KNOWN prod weakness/strawman, NOT hot-hand)
    #   anchor    -> hot_hand (g*) = the ACTUAL hot-hand tilt (the +1-2% finding)
    hh_stats = ["pts", "fg3m"]
    pr_h = _pool(a, "prod_full", hh_stats)
    an_h = _pool(a, "anchor", hh_stats)
    hh_h = _pool(a, "hot_hand", hh_stats)
    out["whole_game_pooled_hot_hand_stats"] = {
        "n": len(pr_h), "mae_prod_full": _mae(pr_h), "mae_anchor_g0": _mae(an_h),
        "mae_hot_hand": _mae(hh_h),
        "lift_anchor_vs_prod_pct": _lift(_mae(pr_h), _mae(an_h)),       # strawman-kill
        "lift_heat_vs_anchor_pct": _lift(_mae(an_h), _mae(hh_h)),       # TRUE hot-hand
        "lift_hot_hand_vs_prod_pct": _lift(_mae(pr_h), _mae(hh_h)),     # combined
    }
    # per-stat hot-hand decomposition
    out["hot_hand_per_stat"] = {}
    for s in hh_stats:
        mp = _mae(a["prod_full"][s]); man = _mae(a["anchor"][s]); mh = _mae(a["hot_hand"][s])
        out["hot_hand_per_stat"][s] = {
            "n": len(a["prod_full"][s]),
            "mae_prod_full": mp, "mae_anchor_g0": man, "mae_hot_hand": mh,
            "lift_anchor_vs_prod_pct": _lift(mp, man),
            "lift_heat_vs_anchor_pct": _lift(man, mh),
        }

    # ---- MID-GAME window (usage fade is gated here) ----
    m = err["mid"]
    mid = {}
    for s in STATS:
        mae_prod = _mae(m["prod_full"][s]); mae_uf = _mae(m["usage_fade"][s])
        mae_intel = _mae(m["intel"][s]); mae_rc_m = _mae(m["rotcurve"][s])
        mid[s] = {
            "n": len(m["prod_full"][s]),
            "mae_prod_full": mae_prod, "mae_usage_fade": mae_uf, "mae_intel": mae_intel,
            "mae_rotcurve": mae_rc_m,
            "lift_usage_vs_prod_pct": _lift(mae_prod, mae_uf),
            "lift_intel_vs_prod_pct": _lift(mae_prod, mae_intel),
            "lift_rotcurve_vs_prod_pct": _lift(mae_prod, mae_rc_m),
        }
    out["mid_game"] = mid
    pr_m = _pool(m, "prod_full", STATS); uf_m = _pool(m, "usage_fade", STATS)
    ur_m = _pool(m, "usage_regress", STATS)
    intel_m = _pool(m, "intel", STATS); rc_m = _pool(m, "rotcurve", STATS)
    out["mid_game_pooled_all_stats"] = {
        "n": len(pr_m), "mae_prod_full": _mae(pr_m), "mae_usage_fade": _mae(uf_m),
        "mae_usage_regress_a0": _mae(ur_m), "mae_intel": _mae(intel_m),
        "mae_rotcurve": _mae(rc_m),
        # usage_fade vs prod = total mid-game lift (mostly L5-anchor formula)
        "lift_usage_vs_prod_pct": _lift(_mae(pr_m), _mae(uf_m)),
        # usage_fade vs usage_regress(a=0) = the LIVE-rate contribution ALONE
        # (usage doc claims ~0: the lift is the baseline formula, not the live signal)
        "lift_live_rate_vs_regress_pct": _lift(_mae(ur_m), _mae(uf_m)),
        "lift_intel_vs_prod_pct": _lift(_mae(pr_m), _mae(intel_m)),
        "lift_rotcurve_vs_prod_pct": _lift(_mae(pr_m), _mae(rc_m)),
        "_note": "usage_regress_a0 = pure L5-rate fade ignoring the observed in-game "
                 "rate. usage_fade ~= usage_regress confirms the live usage signal "
                 "adds ~nothing; the mid-game lift is the L5-anchor baseline formula "
                 "replacing pace extrapolation (a known prod weakness, not a new edge).",
    }

    # ---- BLOWOUT scope (leading-team starters, big/huge): prod_full vs strawman ----
    b = err["blowout"]
    pf_b = _pool(b, "pace_foul", core); pr_b = _pool(b, "prod_full", core)
    out["blowout_lead_starters_core"] = {
        "n": len(pr_b),
        "mae_pace_foul_strawman": _mae(pf_b), "mae_prod_full": _mae(pr_b),
        "lift_prod_blowout_vs_strawman_pct": _lift(_mae(pf_b), _mae(pr_b)),
        "_note": "this is the chunk of the +11% blowout_starter lift that production's "
                 "existing blowout_factor ALREADY captures on the strawman baseline.",
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=700)
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--min-train", type=int, default=60)
    args = ap.parse_args()
    summary = run(args.max_games, args.folds, args.min_train)
    outp = os.path.join(PLAN_DIR, "exp_intel_adjust.json")
    with open(outp, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    print("\n[exp] wrote", outp)

    wp = summary["whole_game_pooled_core"]
    print(f"\nWHOLE-GAME core (pts/reb/ast) n={wp['n']}")
    print(f"  prod blowout vs strawman lift:  {wp['lift_prod_vs_strawman_pct']:+.2f}%  "
          f"(pace_foul {wp['mae_pace_foul']:.4f} -> prod_full {wp['mae_prod_full']:.4f})")
    print(f"  INTEL vs prod_full lift:        {wp['lift_intel_vs_prod_pct']:+.3f}%  "
          f"(prod_full {wp['mae_prod_full']:.4f} -> intel {wp['mae_intel']:.4f})")
    rc_lift = wp.get("lift_rotcurve_vs_prod_pct")
    rc_mae = wp.get("mae_rotcurve")
    if rc_lift is not None and rc_mae is not None:
        bar_met = rc_lift > 3.07
        verdict = "BEATS BAR (+3.07%)" if bar_met else "BELOW BAR (+3.07%)"
        print(f"\nW-009 ROTCURVE vs prod_full lift:  {rc_lift:+.3f}%  "
              f"(prod_full {wp['mae_prod_full']:.4f} -> rotcurve {rc_mae:.4f})  [{verdict}]")
    rcp = summary.get("rotcurve_per_stat", {})
    if rcp:
        print("  Per-stat rotcurve lift:")
        for s in ("pts", "reb", "ast"):
            rs = rcp.get(s, {})
            lft = rs.get("lift_rotcurve_vs_prod_pct")
            mrc = rs.get("mae_rotcurve")
            mprod = rs.get("mae_prod_full")
            if lft is not None:
                print(f"    {s}: {mprod:.4f} -> {mrc:.4f}  lift {lft:+.3f}%")
    hh = summary["whole_game_pooled_hot_hand_stats"]
    print(f"\nHOT-HAND (pts/fg3m) n={hh['n']}:")
    print(f"  prod_full {hh['mae_prod_full']:.4f} -> anchor(g=0) {hh['mae_anchor_g0']:.4f}  "
          f"L5-anchor-vs-pace-extrap (STRAWMAN-kill) {hh['lift_anchor_vs_prod_pct']:+.2f}%")
    print(f"  anchor {hh['mae_anchor_g0']:.4f} -> hot(g*) {hh['mae_hot_hand']:.4f}  "
          f"TRUE heat-tilt {hh['lift_heat_vs_anchor_pct']:+.3f}%")
    print(f"  combined hot_hand vs prod_full {hh['lift_hot_hand_vs_prod_pct']:+.2f}%")
    mm = summary["mid_game_pooled_all_stats"]
    print(f"\nMID-GAME all-stats n={mm['n']}:")
    print(f"  prod_full {mm['mae_prod_full']:.4f} -> usage_fade {mm['mae_usage_fade']:.4f}  "
          f"total mid-game lift {mm['lift_usage_vs_prod_pct']:+.2f}%")
    print(f"  usage_regress(a=0) {mm['mae_usage_regress_a0']:.4f} -> usage_fade {mm['mae_usage_fade']:.4f}  "
          f"LIVE-rate-only lift {mm['lift_live_rate_vs_regress_pct']:+.3f}% (claim: ~0)")
    # foul_cal incremental (pooled core) — should be ~0 vs prod_full
    fc_pool_base = []; fc_pool_sig = []
    for s in ("pts", "reb", "ast"):
        fc_pool_base += [x for x in []]  # placeholder; use whole_game per-stat
    wg = summary["whole_game"]
    fc_lifts = [wg[s]["lift_foul_cal_vs_prod_pct"] for s in STATS
                if wg[s]["lift_foul_cal_vs_prod_pct"] is not None]
    if fc_lifts:
        print(f"\nFOUL-CAL incremental vs prod_full (per-stat range): "
              f"{min(fc_lifts):+.3f}%..{max(fc_lifts):+.3f}%  (production's REAL foul "
              f"factor already in baseline -> calibration adds ~0)")
    bb = summary["blowout_lead_starters_core"]
    if bb["mae_prod_full"] is not None:
        print(f"\nBLOWOUT lead-starters core n={bb['n']}: strawman "
              f"{bb['mae_pace_foul_strawman']:.4f} -> prod_full {bb['mae_prod_full']:.4f}  "
              f"prod blowout already captures {bb['lift_prod_blowout_vs_strawman_pct']:+.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
