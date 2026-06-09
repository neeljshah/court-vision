"""
iter64_inplay_pbp_microstructure.py
───────────────────────────────────
Iter-64: tap the 10k+ untapped per-quarter PBP files to inject *microstructure*
features into the end-of-quarter inplay winprob models. Two endQ states with
identical (score_margin, total_pts) but different *trajectories within the last
4 min* (12-2 closing run vs 5-9 lull) carry different win signals. The
production model has zero microstructure beyond `last_q_margin`.

NEW FEATURES per snapshot (computed from `data/nba/pbp_<gid>_p<period>.json`,
where period = snap_idx+1):
  • home_run_last_240s          largest consecutive scoring run home logged in
                                last 4 min of the just-completed quarter
  • away_run_last_240s          same for away
  • home_pts_last_120s          home pts in last 2 min of just-completed quarter
  • away_pts_last_120s          away pts in last 2 min of just-completed quarter
  • home_to_last_quarter        home turnovers (event_type==5) for whole quarter
  • away_to_last_quarter        away turnovers for whole quarter
  • home_ft_trips_last_quarter  distinct home FT trips (group by clock-bucket+player)
  • away_ft_trips_last_quarter  distinct away FT trips
  • lead_changes_last_quarter   # of sign flips of score_margin during quarter
  • last_event_type_scoring     1 if last event before period-end was a made FG/FT

OUT: data/cache/inplay_pbp_microstructure.parquet (one row per game_id/period)
     joined into the standard inplay row builder.

MODELS:  data/models/inplay_winprob_endq{1,2,3}_v3_pbp.lgb + _meta.json
RESULTS: data/cache/iter64_inplay_pbp_results.json

Ship gate
  ≥3/4 WF folds improved on AT LEAST 2 of 3 snapshots
  AND mean Brier delta ≤ -0.003 on those snapshots
  AND post-join coverage ≥ 1,500 games.

Never modifies the existing `_meta.json` or `.lgb` files (READ-ONLY).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ── paths ─────────────────────────────────────────────────────────────────────
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
MODELS_DIR = os.path.join(PROJECT, "data", "models")
MICRO_PARQUET = os.path.join(DATA_CACHE, "inplay_pbp_microstructure.parquet")
OUT_JSON = os.path.join(DATA_CACHE, "iter64_inplay_pbp_results.json")

os.makedirs(DATA_CACHE, exist_ok=True)

SNAPSHOTS = ["endQ1", "endQ2", "endQ3"]
N_FOLDS = 4
RANDOM_SEED = 42

# ── PBP parsing ───────────────────────────────────────────────────────────────

# event_type codes inferred from the data:
#   0 = period start / generic
#   1 = made FG
#   2 = missed FG
#   3 = free throw (made if " PTS)" pattern in desc; miss if startswith "MISS ")
#   4 = rebound
#   5 = turnover
#   6 = foul
#   8 = substitution
#  13 = end of period
QUARTER_LEN_SEC = 720  # 12 minutes


def _parse_score(score_str: str) -> Optional[Tuple[int, int]]:
    """Parse 'home-away' score, return (home_pts, away_pts) or None."""
    if not score_str or "-" not in score_str:
        return None
    try:
        h_str, a_str = score_str.split("-", 1)
        return int(h_str), int(a_str)
    except (ValueError, AttributeError):
        return None


def _is_made_ft(desc: str) -> bool:
    """Made FT: contains '(.. PTS)' or no leading MISS."""
    if not desc:
        return False
    if desc.lstrip().startswith("MISS"):
        return False
    # Must mention "Free Throw" + " PTS)" total reference => made
    return ("Free Throw" in desc) and (" PTS)" in desc)


def _is_made_fg(desc: str) -> bool:
    """Made FG: desc has '(.. PTS)' and is NOT 'Free Throw' and NOT 'MISS'."""
    if not desc:
        return False
    if desc.lstrip().startswith("MISS"):
        return False
    if "Free Throw" in desc:
        return False
    return " PTS)" in desc


def _ft_trip_key(ev: Dict) -> Optional[Tuple[str, int]]:
    """Identify the FT trip an event belongs to. A 'trip' = one player at one
    clock instant with a sequence of '1 of N', '2 of N', etc.
    """
    desc = ev.get("event_desc", "") or ""
    if "Free Throw" not in desc:
        return None
    player = ev.get("player_name") or ""
    clock = int(ev.get("game_clock_sec", 0) or 0)
    # bucket clock into 8s blocks so consecutive FTs at the same dead-ball clock
    # (which often share the same `game_clock_sec`) all share a key.
    return (player, clock // 8)


def extract_pbp_features(pbp: List[Dict]) -> Dict[str, float]:
    """Compute the 10 microstructure features from a single quarter's PBP list.

    Score format: 'home-away' where margin = home - away.
    """
    feat = {
        "home_run_last_240s": 0.0,
        "away_run_last_240s": 0.0,
        "home_pts_last_120s": 0.0,
        "away_pts_last_120s": 0.0,
        "home_to_last_quarter": 0.0,
        "away_to_last_quarter": 0.0,
        "home_ft_trips_last_quarter": 0.0,
        "away_ft_trips_last_quarter": 0.0,
        "lead_changes_last_quarter": 0.0,
        "last_event_type_scoring": 0.0,
    }
    if not pbp:
        return feat

    # Identify home/away team_abbrev. We can't get it directly from a single
    # quarter PBP, so we infer from score deltas: when home pts ticks up we
    # see the team_abbrev of the scoring event. Build a frequency map of
    # team_abbrev associated with positive home-pts deltas vs positive
    # away-pts deltas.
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    prev_score: Tuple[int, int] = (0, 0)
    team_home_votes: Dict[str, int] = {}
    team_away_votes: Dict[str, int] = {}

    for ev in pbp:
        s = _parse_score(ev.get("score", ""))
        if s is None:
            continue
        h_now, a_now = s
        ta = ev.get("team_abbrev") or ""
        if ta:
            if h_now > prev_score[0]:
                team_home_votes[ta] = team_home_votes.get(ta, 0) + (h_now - prev_score[0])
            if a_now > prev_score[1]:
                team_away_votes[ta] = team_away_votes.get(ta, 0) + (a_now - prev_score[1])
        prev_score = s

    if team_home_votes:
        home_team = max(team_home_votes.items(), key=lambda kv: kv[1])[0]
    if team_away_votes:
        away_team = max(team_away_votes.items(), key=lambda kv: kv[1])[0]

    # Now make a second pass to compute features.
    # Track running run for each team. A "run" is consecutive points scored
    # by one team without the other team scoring. Reset when the OTHER team
    # scores.
    home_run = 0
    away_run = 0
    max_home_run_in_240s = 0
    max_away_run_in_240s = 0
    pts_home_120s = 0
    pts_away_120s = 0
    home_tos = 0
    away_tos = 0
    home_ft_trips: set = set()
    away_ft_trips: set = set()
    lead_changes = 0
    prev_margin_sign: Optional[int] = None
    prev_score = (0, 0)
    last_scoring_idx_clock: Optional[int] = None

    # Pass through events in CHRONOLOGICAL order (game_clock_sec ascending).
    # The files appear already in chronological order based on the sample.
    for ev in pbp:
        et = ev.get("event_type", -1)
        clock = int(ev.get("game_clock_sec", 0) or 0)
        ta = ev.get("team_abbrev") or ""
        s = _parse_score(ev.get("score", ""))
        if s is None:
            continue
        h_now, a_now = s
        h_delta = h_now - prev_score[0]
        a_delta = a_now - prev_score[1]

        # Update runs based on which team scored
        if h_delta > 0:
            home_run += h_delta
            away_run = 0
        if a_delta > 0:
            away_run += a_delta
            home_run = 0

        # Track max run inside the last 240s window (clock 480..720 in our coords
        # where clock_sec=0 is start of quarter and 720 is end).
        if clock >= QUARTER_LEN_SEC - 240:
            if home_run > max_home_run_in_240s:
                max_home_run_in_240s = home_run
            if away_run > max_away_run_in_240s:
                max_away_run_in_240s = away_run
            # Last-2-min points
            if clock >= QUARTER_LEN_SEC - 120:
                if h_delta > 0:
                    pts_home_120s += h_delta
                if a_delta > 0:
                    pts_away_120s += a_delta

        # Lead-change count for the whole quarter
        margin = h_now - a_now
        if margin > 0:
            sign = 1
        elif margin < 0:
            sign = -1
        else:
            sign = 0
        if prev_margin_sign is not None and sign != 0 and prev_margin_sign != 0 and sign != prev_margin_sign:
            lead_changes += 1
        if sign != 0:
            prev_margin_sign = sign

        # Turnovers
        if et == 5:
            if home_team and ta == home_team:
                home_tos += 1
            elif away_team and ta == away_team:
                away_tos += 1

        # FT trips
        if et == 3 and ta:
            key = _ft_trip_key(ev)
            if key is not None:
                if home_team and ta == home_team:
                    home_ft_trips.add(key)
                elif away_team and ta == away_team:
                    away_ft_trips.add(key)

        # Is this a scoring event? (made FG or made FT)
        is_score = (et == 1) or (et == 3 and _is_made_ft(ev.get("event_desc", "")))
        if is_score:
            last_scoring_idx_clock = clock

        prev_score = (h_now, a_now)

    feat["home_run_last_240s"] = float(max_home_run_in_240s)
    feat["away_run_last_240s"] = float(max_away_run_in_240s)
    feat["home_pts_last_120s"] = float(pts_home_120s)
    feat["away_pts_last_120s"] = float(pts_away_120s)
    feat["home_to_last_quarter"] = float(home_tos)
    feat["away_to_last_quarter"] = float(away_tos)
    feat["home_ft_trips_last_quarter"] = float(len(home_ft_trips))
    feat["away_ft_trips_last_quarter"] = float(len(away_ft_trips))
    feat["lead_changes_last_quarter"] = float(lead_changes)

    # last_event_type_scoring — the LAST scoring event in the quarter must be
    # within the last ~5s before end-of-quarter to count as "the last event
    # before snapshot". We use the looser: any scoring event at clock >= 680
    # (last 40s) -- to be a strict "buzzer beater" signal. We'll keep it as
    # the strict 'is the absolute last meaningful event a make'.
    # Approach: walk events backward, ignoring substitutions / period-end /
    # rebounds / fouls. First non-administrative event = the last play.
    feat["last_event_type_scoring"] = 0.0
    for ev in reversed(pbp):
        et = ev.get("event_type", -1)
        if et in (0, 8, 13):  # start/sub/end of period
            continue
        desc = ev.get("event_desc", "") or ""
        if et == 1:
            feat["last_event_type_scoring"] = 1.0
        elif et == 3 and _is_made_ft(desc):
            feat["last_event_type_scoring"] = 1.0
        # otherwise it's a miss/rebound/foul/TO — leave at 0
        break

    return feat


# ── microstructure cache build ────────────────────────────────────────────────

def build_microstructure_cache(game_ids: List[str]) -> pd.DataFrame:
    """Build / load the microstructure parquet for the given list of game_ids.

    Caches at MICRO_PARQUET. If cache exists and covers all game_ids, reuse it.
    Otherwise, compute missing ones and write a fresh cache.

    Output: one row per (game_id, period) for period in {1,2,3}, with the
    microstructure features. Period 4 isn't used (we model endQ1..3 only).
    """
    cached: pd.DataFrame
    if os.path.exists(MICRO_PARQUET):
        cached = pd.read_parquet(MICRO_PARQUET)
        cached["game_id"] = cached["game_id"].astype(str)
        # check if all requested (gid, period) tuples present
        wanted = set()
        for gid in game_ids:
            for p in (1, 2, 3):
                wanted.add((gid, p))
        have = set(zip(cached["game_id"].tolist(), cached["period"].tolist()))
        missing = wanted - have
        if not missing:
            print(f"  microstructure cache hit: {len(cached)} rows", flush=True)
            return cached
        print(f"  cache exists ({len(cached)} rows) but missing {len(missing)} tuples; rebuilding", flush=True)
    else:
        cached = pd.DataFrame()

    rows: List[Dict] = []
    n_parsed = 0
    n_missing = 0
    t0 = time.time()
    for i, gid in enumerate(game_ids):
        for period in (1, 2, 3):
            path = os.path.join(NBA_CACHE, f"pbp_{gid}_p{period}.json")
            if not os.path.exists(path):
                n_missing += 1
                continue
            try:
                with open(path) as f:
                    pbp = json.load(f)
            except (json.JSONDecodeError, OSError):
                n_missing += 1
                continue
            feat = extract_pbp_features(pbp)
            feat["game_id"] = gid
            feat["period"] = period
            rows.append(feat)
            n_parsed += 1
        if (i + 1) % 500 == 0:
            print(f"    parsed {i+1}/{len(game_ids)} games  "
                  f"({n_parsed} qtr-files, {n_missing} missing)  "
                  f"elapsed={time.time()-t0:.1f}s", flush=True)

    print(f"  parsed {n_parsed} quarter-PBP files, missing {n_missing}, "
          f"in {time.time()-t0:.1f}s", flush=True)

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["game_id"] = df["game_id"].astype(str)
    df.to_parquet(MICRO_PARQUET, index=False)
    print(f"  wrote {MICRO_PARQUET} ({len(df)} rows)", flush=True)
    return df


# ── data loading (mirror oos_validate script) ─────────────────────────────────

def load_linescores() -> Dict[str, Dict]:
    with open(os.path.join(NBA_CACHE, "linescores_all.json")) as f:
        return json.load(f)


def load_season_games() -> Dict[str, Dict]:
    seasons = ["2022-23", "2023-24", "2024-25"]
    all_rows: Dict[str, Dict] = {}
    for s in seasons:
        path = os.path.join(NBA_CACHE, f"season_games_{s}.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            data = json.load(f)
        for row in data.get("rows", []):
            all_rows[row["game_id"]] = row
    return all_rows


def load_quarter_features_summaries() -> Dict[str, Dict[str, float]]:
    path = os.path.join(DATA_CACHE, "quarter_features.parquet")
    if not os.path.exists(path):
        return {}
    df = pd.read_parquet(path)
    df["game_id"] = df["game_id"].astype(str)
    df["team_id"] = pd.to_numeric(df["team_id"], errors="coerce")
    summaries: Dict[str, Dict[str, float]] = {}
    for (gid, tid), grp in df.groupby(["game_id", "team_id"]):
        key = f"{gid}_{int(tid)}"
        summaries[key] = {
            "q1_usg_avg": float(grp["q1_usg"].mean()),
            "halftime_pace_shift": float(grp["halftime_pace_shift"].mean()),
            "trailing_team_q4_usg_hhi": float(
                grp["trailing_team_q4_usg_concentration"].mean()
                if grp["trailing_team_q4_usg_concentration"].notna().any()
                else np.nan
            ),
        }
    return summaries


def _pregame_wp_from_sg(sg: Dict) -> float:
    wp = sg.get("sim_win_prob")
    if wp is not None:
        return float(wp)
    hca = 65.0
    home_elo = sg.get("home_elo")
    away_elo = sg.get("away_elo")
    if home_elo is None or away_elo is None:
        return 0.55
    try:
        diff = float(home_elo) - float(away_elo) + hca
        return float(1.0 / (1.0 + 10.0 ** (-diff / 400.0)))
    except (TypeError, ValueError):
        return 0.55


MINUTES_PER_QUARTER = 12.0


def build_rows_with_micro(
    linescores: Dict,
    season_games: Dict,
    qf_summaries: Dict[str, Dict[str, float]],
    micro_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build the snapshot-row table including micro features."""
    # index micro_df for fast lookup
    micro_lookup: Dict[Tuple[str, int], Dict[str, float]] = {}
    if not micro_df.empty:
        for _, r in micro_df.iterrows():
            key = (str(r["game_id"]), int(r["period"]))
            micro_lookup[key] = {
                c: float(r[c]) for c in micro_df.columns
                if c not in ("game_id", "period")
            }

    records: List[Dict] = []
    for gid, ls in linescores.items():
        sg = season_games.get(gid)
        if sg is None:
            continue
        required_qs = ["home_q1", "home_q2", "home_q3", "home_q4",
                       "away_q1", "away_q2", "away_q3", "away_q4"]
        if any(ls.get(k) is None for k in required_qs):
            continue
        hq = [ls["home_q1"], ls["home_q2"], ls["home_q3"], ls["home_q4"]]
        aq = [ls["away_q1"], ls["away_q2"], ls["away_q3"], ls["away_q4"]]
        home_total = sum(hq)
        away_total = sum(aq)
        home_team_won = int(home_total > away_total)
        game_date = sg.get("game_date", "1900-01-01")
        home_team_id = ls.get("home_team_id", 0) or sg.get("home_team", "UNK")
        season = sg.get("season", "unknown")
        pregame_wp = _pregame_wp_from_sg(sg)
        try:
            htid_int = int(home_team_id)
        except (TypeError, ValueError):
            htid_int = 0
        qf_row = qf_summaries.get(f"{gid}_{htid_int}", {})
        q1_usg_avg = qf_row.get("q1_usg_avg", np.nan)
        halftime_pace_shift = qf_row.get("halftime_pace_shift", np.nan)
        trailing_team_q4_usg_hhi = qf_row.get("trailing_team_q4_usg_hhi", np.nan)

        for snap_idx, snapshot in enumerate(SNAPSHOTS):
            n_qtrs = snap_idx + 1
            minutes_played = n_qtrs * MINUTES_PER_QUARTER
            h_cum = sum(hq[:n_qtrs])
            a_cum = sum(aq[:n_qtrs])
            total_pts = h_cum + a_cum
            if snapshot == "endQ3" and total_pts < 60:
                continue
            score_margin = h_cum - a_cum
            pace_so_far = total_pts / minutes_played
            q1_delta = hq[0] - aq[0]
            q2_delta = (hq[1] - aq[1]) if n_qtrs >= 2 else np.nan
            q3_delta = (hq[2] - aq[2]) if n_qtrs >= 3 else np.nan
            last_q_margin = hq[n_qtrs - 1] - aq[n_qtrs - 1]

            micro = micro_lookup.get((str(gid), n_qtrs), {})

            rec = {
                "game_id": gid,
                "game_date": game_date,
                "snapshot": snapshot,
                "home_team_id": home_team_id,
                "season": season,
                "score_margin": score_margin,
                "total_pts": total_pts,
                "pace_so_far": pace_so_far,
                "q1_delta": q1_delta,
                "q2_delta": q2_delta,
                "q3_delta": q3_delta,
                "last_q_margin": last_q_margin,
                "pregame_win_prob": pregame_wp,
                "home_team_won": home_team_won,
                "q1_usg_avg": q1_usg_avg,
                "halftime_pace_shift": halftime_pace_shift,
                "trailing_team_q4_usg_hhi": trailing_team_q4_usg_hhi,
                # micro features (NaN if missing)
                "home_run_last_240s": micro.get("home_run_last_240s", np.nan),
                "away_run_last_240s": micro.get("away_run_last_240s", np.nan),
                "home_pts_last_120s": micro.get("home_pts_last_120s", np.nan),
                "away_pts_last_120s": micro.get("away_pts_last_120s", np.nan),
                "home_to_last_quarter": micro.get("home_to_last_quarter", np.nan),
                "away_to_last_quarter": micro.get("away_to_last_quarter", np.nan),
                "home_ft_trips_last_quarter":
                    micro.get("home_ft_trips_last_quarter", np.nan),
                "away_ft_trips_last_quarter":
                    micro.get("away_ft_trips_last_quarter", np.nan),
                "lead_changes_last_quarter":
                    micro.get("lead_changes_last_quarter", np.nan),
                "last_event_type_scoring":
                    micro.get("last_event_type_scoring", np.nan),
                "has_micro": int(bool(micro)),
            }
            records.append(rec)
    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    return df


# ── walk-forward CV ──────────────────────────────────────────────────────────

def load_meta(snapshot: str) -> Dict[str, Any]:
    with open(os.path.join(MODELS_DIR,
                           f"inplay_winprob_{snapshot.lower()}_meta.json")) as f:
        return json.load(f)


def walk_forward(
    df_snap: pd.DataFrame,
    feature_cols: List[str],
    cat_cols: List[str],
    hp: Dict[str, Any],
) -> List[Dict[str, Any]]:
    import lightgbm as lgb
    from sklearn.metrics import (accuracy_score, brier_score_loss,
                                 log_loss, roc_auc_score)
    n = len(df_snap)
    min_train = int(n * 0.60)
    test_size = (n - min_train) // N_FOLDS
    out: List[Dict[str, Any]] = []
    for fold in range(N_FOLDS):
        train_end = min_train + fold * test_size
        test_start = train_end
        test_end = test_start + test_size if fold < N_FOLDS - 1 else n
        if train_end < 30 or test_start >= n:
            continue
        X_tr = df_snap[feature_cols].iloc[:train_end].copy()
        y_tr = df_snap["home_team_won"].iloc[:train_end]
        X_te = df_snap[feature_cols].iloc[test_start:test_end].copy()
        y_te = df_snap["home_team_won"].iloc[test_start:test_end]
        if len(X_te) < 10:
            continue
        active_cats = [c for c in cat_cols if c in X_tr.columns]
        for c in active_cats:
            X_tr[c] = X_tr[c].astype("category")
            X_te[c] = X_te[c].astype("category")
        model = lgb.LGBMClassifier(
            n_estimators=int(hp.get("n_estimators", 300)),
            learning_rate=float(hp.get("learning_rate", 0.05)),
            num_leaves=int(hp.get("num_leaves", 31)),
            min_child_samples=int(hp.get("min_child_samples", 20)),
            subsample=float(hp.get("subsample", 0.8)),
            colsample_bytree=float(hp.get("colsample_bytree", 0.8)),
            reg_alpha=float(hp.get("reg_alpha", 0.1)),
            reg_lambda=float(hp.get("reg_lambda", 1.0)),
            random_state=int(hp.get("random_state", RANDOM_SEED)),
            n_jobs=4,
            verbose=-1,
        )
        model.fit(X_tr, y_tr,
                  categorical_feature=active_cats if active_cats else "auto")
        probs = model.predict_proba(X_te)[:, 1]
        preds = (probs >= 0.5).astype(int)
        probs_safe = np.clip(probs, 1e-6, 1 - 1e-6)
        y_arr = y_te.values
        try:
            auc = float(roc_auc_score(y_arr, probs))
        except ValueError:
            auc = float("nan")
        out.append({
            "fold": fold,
            "train_n": int(len(X_tr)),
            "test_n": int(len(X_te)),
            "brier": float(brier_score_loss(y_arr, probs)),
            "log_loss": float(log_loss(y_arr, probs_safe)),
            "auc": auc,
            "accuracy": float(accuracy_score(y_arr, preds)),
        })
    return out


# ── final-model training (full data) + integrity check ────────────────────────

def train_full_and_save(
    df_snap: pd.DataFrame,
    feature_cols: List[str],
    cat_cols: List[str],
    hp: Dict[str, Any],
    snapshot: str,
) -> Dict[str, Any]:
    import lightgbm as lgb
    from sklearn.metrics import (accuracy_score, brier_score_loss,
                                 log_loss, roc_auc_score)
    X = df_snap[feature_cols].copy()
    y = df_snap["home_team_won"]
    active_cats = [c for c in cat_cols if c in X.columns]
    for c in active_cats:
        X[c] = X[c].astype("category")
    model = lgb.LGBMClassifier(
        n_estimators=int(hp.get("n_estimators", 300)),
        learning_rate=float(hp.get("learning_rate", 0.05)),
        num_leaves=int(hp.get("num_leaves", 31)),
        min_child_samples=int(hp.get("min_child_samples", 20)),
        subsample=float(hp.get("subsample", 0.8)),
        colsample_bytree=float(hp.get("colsample_bytree", 0.8)),
        reg_alpha=float(hp.get("reg_alpha", 0.1)),
        reg_lambda=float(hp.get("reg_lambda", 1.0)),
        random_state=int(hp.get("random_state", RANDOM_SEED)),
        n_jobs=4,
        verbose=-1,
    )
    model.fit(X, y, categorical_feature=active_cats if active_cats else "auto")
    probs = model.predict_proba(X)[:, 1]
    preds = (probs >= 0.5).astype(int)
    probs_safe = np.clip(probs, 1e-6, 1 - 1e-6)
    in_sample = {
        "auc": float(roc_auc_score(y, probs)) if len(np.unique(y)) > 1 else float("nan"),
        "brier": float(brier_score_loss(y, probs)),
        "log_loss": float(log_loss(y, probs_safe)),
        "accuracy": float(accuracy_score(y, preds)),
    }

    # Save booster
    out_lgb = os.path.join(MODELS_DIR,
                           f"inplay_winprob_{snapshot.lower()}_v3_pbp.lgb")
    out_meta = os.path.join(MODELS_DIR,
                            f"inplay_winprob_{snapshot.lower()}_v3_pbp_meta.json")
    booster = model.booster_
    booster.save_model(out_lgb)

    # ── pkl integrity check ───
    # Reload the saved booster, run a forward pass on the SAME X, compare
    # probabilities. Any divergence => abort writing the meta.
    reloaded = lgb.Booster(model_file=out_lgb)
    # booster predict returns positive-class prob for binary
    probs_reload = reloaded.predict(X)
    max_diff = float(np.abs(probs - probs_reload).max())
    n_features_in = int(model.n_features_in_)
    integrity_ok = (max_diff < 1e-6) and (n_features_in == len(feature_cols))
    if not integrity_ok:
        # remove the partial booster to be safe
        try:
            os.remove(out_lgb)
        except OSError:
            pass
        raise RuntimeError(
            f"[INTEGRITY FAIL] {snapshot}: max_diff={max_diff:.6f} "
            f"n_features_in={n_features_in} vs feature_cols_len={len(feature_cols)}"
        )

    meta = {
        "snapshot": snapshot,
        "feature_cols": feature_cols,
        "categorical_cols": cat_cols,
        "n_train_rows": int(len(X)),
        "home_win_rate": float(y.mean()),
        "in_sample": in_sample,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "probe": "iter64_inplay_pbp_microstructure",
        "hyperparams": hp,
        "integrity": {
            "max_prob_diff_pkl_vs_inmemory": max_diff,
            "n_features_in": n_features_in,
            "ok": integrity_ok,
        },
    }
    with open(out_meta, "w") as f:
        json.dump(meta, f, indent=2, default=str)
    print(f"    saved {out_lgb}", flush=True)
    print(f"    saved {out_meta}", flush=True)
    print(f"    integrity OK: max_prob_diff={max_diff:.2e}, n_features_in={n_features_in}", flush=True)
    return meta


# ── orchestrator ─────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=== iter64: PBP microstructure features for inplay winprob ===", flush=True)
    print(f"  random_seed={RANDOM_SEED}", flush=True)

    print("\n[1] Loading data ...", flush=True)
    linescores = load_linescores()
    season_games = load_season_games()
    qf_summaries = load_quarter_features_summaries()
    print(f"    linescores={len(linescores)}, season_games={len(season_games)}, "
          f"qf_summaries={len(qf_summaries)}", flush=True)

    # The training universe is the intersection of linescores & season_games
    eligible_gids = [gid for gid in linescores if gid in season_games]
    print(f"    eligible game_ids: {len(eligible_gids)}", flush=True)

    print("\n[2] Building microstructure parquet ...", flush=True)
    micro_df = build_microstructure_cache(eligible_gids)
    print(f"    micro_df rows: {len(micro_df)}", flush=True)
    if not micro_df.empty:
        n_unique_games = micro_df["game_id"].nunique()
        print(f"    unique games with at least 1 quarter parsed: {n_unique_games}",
              flush=True)

    print("\n[3] Building snapshot table with micro ...", flush=True)
    df = build_rows_with_micro(linescores, season_games, qf_summaries, micro_df)
    valid_games = set(df[df["snapshot"] == "endQ3"]["game_id"].tolist())
    df = df[df["game_id"].isin(valid_games)].copy().reset_index(drop=True)
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)

    # Post-join coverage: how many games have full micro coverage for all 3 snapshots?
    n_games_post_join = 0
    for gid, g in df.groupby("game_id"):
        if (g["has_micro"] == 1).sum() == 3:
            n_games_post_join += 1
    print(f"    total snapshot rows: {len(df)}", flush=True)
    print(f"    games with full micro on endQ1+Q2+Q3: {n_games_post_join}", flush=True)
    print(f"    games total: {df['game_id'].nunique()}", flush=True)

    coverage_flag = "OK" if n_games_post_join >= 1500 else "INSUFFICIENT_COVERAGE"
    print(f"    coverage flag: {coverage_flag}", flush=True)

    # ── per-snapshot WF + train+save ──────────────────────────────────────
    MICRO_COLS = [
        "home_run_last_240s", "away_run_last_240s",
        "home_pts_last_120s", "away_pts_last_120s",
        "home_to_last_quarter", "away_to_last_quarter",
        "home_ft_trips_last_quarter", "away_ft_trips_last_quarter",
        "lead_changes_last_quarter", "last_event_type_scoring",
    ]

    results: Dict[str, Any] = {
        "iter": "iter64_inplay_pbp_microstructure",
        "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "random_seed": RANDOM_SEED,
        "n_folds": N_FOLDS,
        "coverage": {
            "n_games_full_micro": n_games_post_join,
            "n_games_total_in_train_set": int(df["game_id"].nunique()),
            "flag": coverage_flag,
            "n_pbp_quarter_files_parsed": int(len(micro_df)),
        },
        "snapshots": {},
    }

    # Load baseline OOS Briers (we read them from inplay_oos_validation_2026_05_27.json)
    baseline_path = os.path.join(DATA_CACHE, "inplay_oos_validation_2026_05_27.json")
    baseline = json.load(open(baseline_path))

    if coverage_flag == "INSUFFICIENT_COVERAGE":
        results["verdict"] = "REVERT"
        results["reason"] = (
            f"post-join coverage {n_games_post_join} < 1500 — features not "
            "broadly enough available to ship"
        )
        with open(OUT_JSON, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n  REVERT: insufficient coverage. Results saved to {OUT_JSON}",
              flush=True)
        return

    n_snaps_pass = 0
    snap_meta_by_name: Dict[str, Dict[str, Any]] = {}
    for snapshot in SNAPSHOTS:
        print(f"\n[4] Snapshot {snapshot}", flush=True)
        meta = load_meta(snapshot)
        base_features = list(meta["feature_cols"])
        cat_cols = list(meta.get("categorical_cols", []))
        hp = dict(meta.get("hyperparams", {}))

        v3_features = base_features + MICRO_COLS
        print(f"    base_features ({len(base_features)}): {base_features}", flush=True)
        print(f"    v3_features ({len(v3_features)}) = base + {len(MICRO_COLS)} micro",
              flush=True)

        sub = df[df["snapshot"] == snapshot].copy().reset_index(drop=True)
        print(f"    snapshot rows: {len(sub)}", flush=True)

        # baseline OOS Brier per fold (from the validation JSON, NOT recomputed)
        base_folds = baseline["snapshots"][snapshot]["model_folds_detail"]
        base_briers = [f["brier"] for f in base_folds]
        base_mean = float(np.mean(base_briers))
        print(f"    BASELINE per-fold Brier: {[f'{b:.4f}' for b in base_briers]}",
              flush=True)
        print(f"    BASELINE mean Brier:     {base_mean:.4f}", flush=True)

        # NOTE: we MUST recompute baseline on the SAME row ordering as v3 to be
        # apples-to-apples (the baseline used the same row build, so order
        # matches: build_rows_with_micro mirrors the validation build but adds
        # an explicit (game_date, game_id) sort. Re-do baseline here to be safe).
        print(f"    re-fitting BASELINE on this row ordering (apples-to-apples) ...",
              flush=True)
        rebase_folds = walk_forward(sub, base_features, cat_cols, hp)
        rebase_briers = [f["brier"] for f in rebase_folds]
        rebase_mean = float(np.mean(rebase_briers)) if rebase_briers else float("nan")
        print(f"    BASELINE(refit) per-fold:  {[f'{b:.4f}' for b in rebase_briers]}",
              flush=True)
        print(f"    BASELINE(refit) mean:      {rebase_mean:.4f}", flush=True)

        print(f"    training V3_PBP walk-forward ...", flush=True)
        v3_folds = walk_forward(sub, v3_features, cat_cols, hp)
        v3_briers = [f["brier"] for f in v3_folds]
        v3_mean = float(np.mean(v3_briers)) if v3_briers else float("nan")
        print(f"    V3_PBP   per-fold Brier:  {[f'{b:.4f}' for b in v3_briers]}",
              flush=True)
        print(f"    V3_PBP   mean Brier:      {v3_mean:.4f}", flush=True)

        # Per-fold delta vs the rebaseline (same row ordering)
        deltas = [v - b for v, b in zip(v3_briers, rebase_briers)]
        mean_delta = float(np.mean(deltas)) if deltas else float("nan")
        improved = sum(1 for d in deltas if d < 0)
        print(f"    DELTA v3-rebase per-fold:  {[f'{d:+.4f}' for d in deltas]}",
              flush=True)
        print(f"    DELTA mean: {mean_delta:+.4f}  folds_improved={improved}/{len(deltas)}",
              flush=True)

        snap_pass = improved >= 3 and mean_delta <= -0.003
        print(f"    SHIP per-snap: {snap_pass}", flush=True)

        # Train + save v3 model on full data (regardless of per-snap ship —
        # the final ship decision is across all snapshots; if the OVERALL
        # gate fails, we DELETE the v3 files at the end.)
        print(f"    fitting full-data v3_pbp model + integrity check ...", flush=True)
        train_meta = train_full_and_save(sub, v3_features, cat_cols, hp, snapshot)
        snap_meta_by_name[snapshot] = train_meta

        if snap_pass:
            n_snaps_pass += 1

        results["snapshots"][snapshot] = {
            "n_rows": int(len(sub)),
            "feature_cols_v3": v3_features,
            "cat_cols": cat_cols,
            "baseline_briers_from_validation": base_briers,
            "baseline_mean_from_validation": base_mean,
            "rebaseline_briers": rebase_briers,
            "rebaseline_mean": rebase_mean,
            "v3_briers": v3_briers,
            "v3_mean": v3_mean,
            "deltas_per_fold": deltas,
            "mean_delta_vs_rebaseline": mean_delta,
            "folds_improved": improved,
            "n_folds": len(deltas),
            "snap_passes_gate": snap_pass,
            "v3_fold_detail": v3_folds,
            "rebaseline_fold_detail": rebase_folds,
        }

    # ── overall ship decision ───────────────────────────────────────────────
    overall_ship = n_snaps_pass >= 2
    results["snapshots_passed"] = n_snaps_pass
    results["verdict"] = "SHIP" if overall_ship else "REVERT"
    results["reason"] = (
        f"{n_snaps_pass}/3 snapshots improved (need >=2 with >=3/4 folds improved "
        f"AND mean delta <= -0.003)"
    )

    if not overall_ship:
        # Remove the v3 files we just wrote — gate failed, keep WORM
        print(f"\n  GATE FAILED — removing v3_pbp model files", flush=True)
        for snap in SNAPSHOTS:
            for sfx in (".lgb", "_meta.json"):
                p = os.path.join(MODELS_DIR,
                                 f"inplay_winprob_{snap.lower()}_v3_pbp{sfx}")
                if os.path.exists(p):
                    try:
                        os.remove(p)
                        print(f"    removed {p}", flush=True)
                    except OSError:
                        pass

    elapsed = time.time() - t0
    results["elapsed_s"] = float(elapsed)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # ── summary print ──
    print("\n" + "=" * 70, flush=True)
    print(f"ITER 64 VERDICT: {results['verdict']}", flush=True)
    print(f"Reason: {results['reason']}", flush=True)
    print(f"Coverage: n_games_full_micro={n_games_post_join}", flush=True)
    print("=" * 70, flush=True)
    print(f"  {'Snap':<7} {'Base(refit)':<13} {'V3_PBP':<11} {'Delta':<10} "
          f"{'Folds':<7} {'Ship?':<6}", flush=True)
    for snap in SNAPSHOTS:
        r = results["snapshots"].get(snap)
        if not r:
            continue
        print(
            f"  {snap:<7} {r['rebaseline_mean']:<13.4f} {r['v3_mean']:<11.4f} "
            f"{r['mean_delta_vs_rebaseline']:<+10.4f} "
            f"{r['folds_improved']}/{r['n_folds']:<5} "
            f"{'YES' if r['snap_passes_gate'] else 'no':<6}",
            flush=True,
        )
    print(f"  Elapsed: {elapsed:.1f}s", flush=True)
    print(f"  Results saved to: {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()
