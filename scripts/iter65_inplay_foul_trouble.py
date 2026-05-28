"""
iter65_inplay_foul_trouble.py
─────────────────────────────
Iter-65: per-team foul totals + top-3-starter foul counts at endQ2 / endQ3.

Hypothesis: foul trouble carries Q4-margin signal not in current features.
If a team's top center has 4 PFs at endQ3, his Q4 minutes shrink — directly
hits paint defense / opp-side rebounding.

Reads PBP per-quarter JSON (`data/nba/pbp_<gid>_p{1..3}.json`) and parses
`event_type == 6` foul events. Player PF count is embedded in the description
(e.g. `Maxey P.FOUL (P2.T1)` → player's 2nd PF). Top-3 starter set is determined
from the boxscore (`data/nba/boxscore_<gid>.json`) by ranking players by total
minutes within each team and taking the top 3.

NEW FEATURES per snapshot (endQ2 and endQ3 only):
  • home_team_pfs_cum             team PFs through end of last completed Q
  • away_team_pfs_cum
  • home_max_player_pfs           highest PF count on any home player
  • away_max_player_pfs
  • home_starter_fouled_out_indicator  binary (any home player >= 5 PFs)
  • away_starter_fouled_out_indicator
  • pf_imbalance                  home - away team PFs (signed)

NOTE: spec called for top-3-starter foul counts but the boxscore cache covers
only ~1,200 games and barely overlaps the 2,519-game PBP cache (39 games).
We substitute `max_player_pfs` and "any player at ≥5 PFs" — both computable
from PBP alone — which carry the same foul-trouble signal (a 5-PF player on
*any* rotation slot has near-zero Q4 minutes, regardless of whether they
were a starter). Home/away team assignment is inferred from PBP team_abbrev
frequencies cross-referenced with `season_games[gid].home_team` /
`away_team`.

OUT: data/cache/inplay_foul_state.parquet
     (game_id, snapshot ∈ {endQ2, endQ3}, + 7 features)

MODELS:  data/models/inplay_winprob_endq{2,3}_v4_fouls.lgb + _meta.json
RESULTS: data/cache/iter65_inplay_foul_results.json

Baseline = Iter-68 v6_hp models (lr=0.03, num_leaves=15, min_child_samples:
  endQ2=40, endQ3=10). Compare against the same row ordering by refitting the
v6_hp feature set with v6_hp HPs on this same dataframe (apples-to-apples).

Ship gate (per snapshot):
  ≥3/4 WF folds improved AND mean Brier delta ≤ -0.002.
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
FOUL_PARQUET = os.path.join(DATA_CACHE, "inplay_foul_state.parquet")
OUT_JSON = os.path.join(DATA_CACHE, "iter65_inplay_foul_results.json")

os.makedirs(DATA_CACHE, exist_ok=True)

SNAPSHOTS = ["endQ2", "endQ3"]
N_FOLDS = 4
RANDOM_SEED = 42

# ── PBP foul parsing ──────────────────────────────────────────────────────────
# Player PF count embedded as `(P{N}...)` — N is cumulative PFs for the player
# AFTER this foul. We use it directly as the running game total.
PF_RE = re.compile(r"\(P(\d+)")


def parse_foul_event(ev: Dict) -> Optional[Tuple[str, str, int]]:
    """Return (player_name, team_abbrev, pf_count_after) for a foul event,
    or None if this is a non-player team/tech foul or unparsable.
    """
    if ev.get("event_type") != 6:
        return None
    desc = ev.get("event_desc", "") or ""
    team = ev.get("team_abbrev") or ""
    player = ev.get("player_name") or ""
    if not team or not player:
        return None
    # Skip team techs / coach techs: those have no `(P{N}` pattern
    m = PF_RE.search(desc)
    if not m:
        return None
    try:
        pf_after = int(m.group(1))
    except ValueError:
        return None
    return (player, team, pf_after)


def is_team_foul(ev: Dict) -> bool:
    """Team-foul (counts toward team PF total). All player fouls count; team
    techs / coach techs do NOT count toward the team-PF total in our schema.
    We use the `(P{N}` presence as the marker that this is a player PF.
    """
    if ev.get("event_type") != 6:
        return False
    desc = ev.get("event_desc", "") or ""
    return bool(PF_RE.search(desc))


def aggregate_foul_state_for_game(
    gid: str,
    home_team: str,
    away_team: str,
) -> Dict[int, Dict[str, float]]:
    """Build per-snapshot foul state for one game using PBP only.

    Returns dict: { period_completed (1..3): {feature_dict} }
    where features are the 7 new foul-state features.

    If PBP files for a needed period are missing, returns {}.
    """
    if not home_team or not away_team:
        return {}

    # Walk each quarter PBP. Maintain cumulative team PF total + per-player
    # latest PF count. After each quarter, snapshot the state.
    home_team_pfs = 0
    away_team_pfs = 0
    # Player → latest PF count seen (cumulative across game; PBP gives the
    # count AFTER each foul so the latest value IS the cumulative).
    # We key by (team, player_name) so that two players with the same surname
    # on different teams don't collide.
    home_player_pfs: Dict[str, int] = {}
    away_player_pfs: Dict[str, int] = {}

    out: Dict[int, Dict[str, float]] = {}
    for period in (1, 2, 3):
        path = os.path.join(NBA_CACHE, f"pbp_{gid}_p{period}.json")
        if not os.path.exists(path):
            return {}
        try:
            with open(path) as f:
                pbp = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

        for ev in pbp:
            parsed = parse_foul_event(ev)
            if parsed is None:
                continue
            player, team, pf_after = parsed
            if team == home_team:
                prev = home_player_pfs.get(player, 0)
                if pf_after > prev:
                    home_player_pfs[player] = pf_after
                home_team_pfs += 1
            elif team == away_team:
                prev = away_player_pfs.get(player, 0)
                if pf_after > prev:
                    away_player_pfs[player] = pf_after
                away_team_pfs += 1
            # ignore fouls credited to a team_abbrev we don't recognize

        # Snapshot AFTER processing this quarter (state at end of Q{period}).
        # `max_player_pfs` captures the worst foul-trouble player on each
        # team. The fouled-out indicator fires at 5+ PFs (a player at 5 PFs
        # plays very limited Q4 minutes; at 6 they're disqualified).
        home_max = max(home_player_pfs.values()) if home_player_pfs else 0
        away_max = max(away_player_pfs.values()) if away_player_pfs else 0
        home_fouled_out = int(home_max >= 5)
        away_fouled_out = int(away_max >= 5)
        out[period] = {
            "home_team_pfs_cum": float(home_team_pfs),
            "away_team_pfs_cum": float(away_team_pfs),
            "home_max_player_pfs": float(home_max),
            "away_max_player_pfs": float(away_max),
            "home_starter_fouled_out_indicator": float(home_fouled_out),
            "away_starter_fouled_out_indicator": float(away_fouled_out),
            "pf_imbalance": float(home_team_pfs - away_team_pfs),
        }
    return out


# ── foul-state cache build ────────────────────────────────────────────────────

FOUL_COLS = [
    "home_team_pfs_cum",
    "away_team_pfs_cum",
    "home_max_player_pfs",
    "away_max_player_pfs",
    "home_starter_fouled_out_indicator",
    "away_starter_fouled_out_indicator",
    "pf_imbalance",
]


def build_foul_state_cache(
    game_ids: List[str],
    season_games: Dict[str, Dict],
) -> pd.DataFrame:
    """Build the foul-state parquet. One row per (game_id, period) for periods
    {2, 3} — we only emit rows for periods we actually need (endQ2 / endQ3).

    If cache exists and covers all requested game_ids, reuse it. Otherwise
    rebuild from scratch.
    """
    if os.path.exists(FOUL_PARQUET):
        cached = pd.read_parquet(FOUL_PARQUET)
        cached["game_id"] = cached["game_id"].astype(str)
        wanted = set()
        for gid in game_ids:
            for p in (2, 3):
                wanted.add((gid, p))
        have = set(zip(cached["game_id"].tolist(),
                       cached["period"].astype(int).tolist()))
        missing = wanted - have
        if not missing:
            print(f"  foul-state cache hit: {len(cached)} rows", flush=True)
            return cached
        print(f"  cache exists ({len(cached)} rows) but missing "
              f"{len(missing)} (gid,period) tuples; rebuilding", flush=True)

    rows: List[Dict] = []
    n_parsed_games = 0
    n_missing_games = 0
    t0 = time.time()
    for i, gid in enumerate(game_ids):
        sg = season_games.get(gid, {})
        state = aggregate_foul_state_for_game(
            gid,
            sg.get("home_team", ""),
            sg.get("away_team", ""),
        )
        if not state:
            n_missing_games += 1
        else:
            n_parsed_games += 1
            for period in (2, 3):
                if period in state:
                    rec = {"game_id": gid, "period": period}
                    rec.update(state[period])
                    rows.append(rec)
        if (i + 1) % 500 == 0:
            print(f"    parsed {i+1}/{len(game_ids)} games  "
                  f"({n_parsed_games} ok, {n_missing_games} missing)  "
                  f"elapsed={time.time()-t0:.1f}s", flush=True)

    print(f"  parsed {n_parsed_games} games, missing {n_missing_games}, "
          f"in {time.time()-t0:.1f}s", flush=True)

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["game_id"] = df["game_id"].astype(str)
    df.to_parquet(FOUL_PARQUET, index=False)
    print(f"  wrote {FOUL_PARQUET} ({len(df)} rows)", flush=True)
    return df


# ── data loading (mirrors iter64 / oos_validate) ──────────────────────────────

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


def build_rows_with_fouls(
    linescores: Dict,
    season_games: Dict,
    qf_summaries: Dict[str, Dict[str, float]],
    foul_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build the snapshot-row table including foul features for endQ2 & endQ3."""
    foul_lookup: Dict[Tuple[str, int], Dict[str, float]] = {}
    if not foul_df.empty:
        for _, r in foul_df.iterrows():
            key = (str(r["game_id"]), int(r["period"]))
            foul_lookup[key] = {c: float(r[c]) for c in FOUL_COLS}

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

        # We only build endQ2 and endQ3 (snap_idx 1 and 2)
        for snap_idx, snapshot in [(1, "endQ2"), (2, "endQ3")]:
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
            q2_delta = (hq[1] - aq[1])
            q3_delta = (hq[2] - aq[2]) if n_qtrs >= 3 else np.nan
            last_q_margin = hq[n_qtrs - 1] - aq[n_qtrs - 1]

            foul = foul_lookup.get((str(gid), n_qtrs), {})

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
                "has_foul": int(bool(foul)),
            }
            for c in FOUL_COLS:
                rec[c] = foul.get(c, np.nan)
            records.append(rec)
    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    return df


# ── walk-forward CV ──────────────────────────────────────────────────────────

def load_v6_hp_meta(snapshot: str) -> Dict[str, Any]:
    path = os.path.join(MODELS_DIR,
                        f"inplay_winprob_{snapshot.lower()}_v6_hp_meta.json")
    with open(path) as f:
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
            learning_rate=float(hp.get("learning_rate", 0.03)),
            num_leaves=int(hp.get("num_leaves", 15)),
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
        learning_rate=float(hp.get("learning_rate", 0.03)),
        num_leaves=int(hp.get("num_leaves", 15)),
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

    out_lgb = os.path.join(MODELS_DIR,
                           f"inplay_winprob_{snapshot.lower()}_v4_fouls.lgb")
    out_meta = os.path.join(MODELS_DIR,
                            f"inplay_winprob_{snapshot.lower()}_v4_fouls_meta.json")
    booster = model.booster_
    booster.save_model(out_lgb)

    # pkl integrity check
    reloaded = lgb.Booster(model_file=out_lgb)
    probs_reload = reloaded.predict(X)
    max_diff = float(np.abs(probs - probs_reload).max())
    n_features_in = int(model.n_features_in_)
    booster_n_features = int(reloaded.num_feature())
    integrity_ok = (
        max_diff < 1e-6
        and n_features_in == len(feature_cols)
        and booster_n_features == len(feature_cols)
    )
    if not integrity_ok:
        try:
            os.remove(out_lgb)
        except OSError:
            pass
        raise RuntimeError(
            f"[INTEGRITY FAIL] {snapshot}: max_diff={max_diff:.6f} "
            f"n_features_in={n_features_in} booster_n_features={booster_n_features} "
            f"vs feature_cols_len={len(feature_cols)}"
        )

    meta = {
        "snapshot": snapshot,
        "variant": "v4_fouls",
        "iter": "iter65",
        "feature_cols": feature_cols,
        "categorical_cols": cat_cols,
        "n_train_rows": int(len(X)),
        "n_features_in_": n_features_in,
        "home_win_rate": float(y.mean()),
        "in_sample": in_sample,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "probe": "iter65_inplay_foul_trouble",
        "hyperparams": hp,
        "integrity": {
            "max_prob_diff_pkl_vs_inmemory": max_diff,
            "n_features_in": n_features_in,
            "booster_num_feature": booster_n_features,
            "ok": integrity_ok,
        },
    }
    with open(out_meta, "w") as f:
        json.dump(meta, f, indent=2, default=str)
    print(f"    saved {out_lgb}", flush=True)
    print(f"    saved {out_meta}", flush=True)
    print(f"    integrity OK: max_prob_diff={max_diff:.2e}, "
          f"n_features_in={n_features_in}", flush=True)
    return meta


# ── orchestrator ─────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=== iter65: foul-trouble features for inplay winprob (endQ2/Q3) ===",
          flush=True)
    print(f"  random_seed={RANDOM_SEED}", flush=True)

    print("\n[1] Loading data ...", flush=True)
    linescores = load_linescores()
    season_games = load_season_games()
    qf_summaries = load_quarter_features_summaries()
    print(f"    linescores={len(linescores)}, season_games={len(season_games)}, "
          f"qf_summaries={len(qf_summaries)}", flush=True)

    eligible_gids = [gid for gid in linescores if gid in season_games]
    print(f"    eligible game_ids: {len(eligible_gids)}", flush=True)

    print("\n[2] Building foul-state parquet ...", flush=True)
    foul_df = build_foul_state_cache(eligible_gids, season_games)
    print(f"    foul_df rows: {len(foul_df)}", flush=True)
    if not foul_df.empty:
        n_unique_games = foul_df["game_id"].nunique()
        print(f"    unique games with foul state: {n_unique_games}", flush=True)

    print("\n[3] Building snapshot table with fouls ...", flush=True)
    df = build_rows_with_fouls(linescores, season_games, qf_summaries, foul_df)

    # Restrict to games that have rows for both endQ2 AND endQ3 (parity)
    valid_games = (
        df.groupby("game_id")["snapshot"].apply(set)
        .reset_index(name="snaps")
    )
    valid_games = set(
        valid_games[valid_games["snaps"].apply(lambda s: {"endQ2", "endQ3"}.issubset(s))]["game_id"]
    )
    df = df[df["game_id"].isin(valid_games)].copy().reset_index(drop=True)
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)

    n_games_post_join = 0
    for gid, g in df.groupby("game_id"):
        if (g["has_foul"] == 1).all() and len(g) == 2:
            n_games_post_join += 1
    print(f"    total snapshot rows: {len(df)}", flush=True)
    print(f"    games with full foul-state on Q2+Q3: {n_games_post_join}",
          flush=True)
    print(f"    games total: {df['game_id'].nunique()}", flush=True)

    coverage_flag = "OK" if n_games_post_join >= 1500 else "INSUFFICIENT_COVERAGE"
    print(f"    coverage flag: {coverage_flag}", flush=True)

    results: Dict[str, Any] = {
        "iter": "iter65_inplay_foul_trouble",
        "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "random_seed": RANDOM_SEED,
        "n_folds": N_FOLDS,
        "coverage": {
            "n_games_full_foul_state": n_games_post_join,
            "n_games_total_in_train_set": int(df["game_id"].nunique()),
            "flag": coverage_flag,
            "n_foul_state_rows_cached": int(len(foul_df)),
        },
        "snapshots": {},
    }

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

    # Per-snapshot WF + train+save
    n_snaps_pass = 0
    for snapshot in SNAPSHOTS:
        print(f"\n[4] Snapshot {snapshot}", flush=True)
        v6_meta = load_v6_hp_meta(snapshot)
        base_features = list(v6_meta["feature_cols"])
        cat_cols = list(v6_meta.get("categorical_cols", []))
        hp = dict(v6_meta.get("hyperparams", {}))

        v4_features = base_features + FOUL_COLS
        print(f"    v6_hp baseline features ({len(base_features)}): {base_features}",
              flush=True)
        print(f"    v4_fouls features ({len(v4_features)}) = baseline + "
              f"{len(FOUL_COLS)} foul features", flush=True)
        print(f"    HPs: lr={hp.get('learning_rate')}, "
              f"num_leaves={hp.get('num_leaves')}, "
              f"min_child_samples={hp.get('min_child_samples')}",
              flush=True)

        sub = df[df["snapshot"] == snapshot].copy().reset_index(drop=True)
        # Filter to games with foul state present (has_foul==1)
        sub = sub[sub["has_foul"] == 1].copy().reset_index(drop=True)
        print(f"    snapshot rows (foul-covered only): {len(sub)}", flush=True)

        # Rebaseline: same row ordering, v6_hp feature set + v6_hp HPs
        print(f"    re-fitting BASELINE on this row ordering ...", flush=True)
        rebase_folds = walk_forward(sub, base_features, cat_cols, hp)
        rebase_briers = [f["brier"] for f in rebase_folds]
        rebase_mean = float(np.mean(rebase_briers)) if rebase_briers else float("nan")
        print(f"    BASELINE(refit) per-fold:  {[f'{b:.4f}' for b in rebase_briers]}",
              flush=True)
        print(f"    BASELINE(refit) mean:      {rebase_mean:.4f}", flush=True)

        print(f"    training V4_FOULS walk-forward ...", flush=True)
        v4_folds = walk_forward(sub, v4_features, cat_cols, hp)
        v4_briers = [f["brier"] for f in v4_folds]
        v4_mean = float(np.mean(v4_briers)) if v4_briers else float("nan")
        print(f"    V4_FOULS per-fold Brier:   {[f'{b:.4f}' for b in v4_briers]}",
              flush=True)
        print(f"    V4_FOULS mean Brier:       {v4_mean:.4f}", flush=True)

        deltas = [v - b for v, b in zip(v4_briers, rebase_briers)]
        mean_delta = float(np.mean(deltas)) if deltas else float("nan")
        improved = sum(1 for d in deltas if d < 0)
        print(f"    DELTA v4-rebase per-fold:  {[f'{d:+.4f}' for d in deltas]}",
              flush=True)
        print(f"    DELTA mean: {mean_delta:+.4f}  folds_improved={improved}/{len(deltas)}",
              flush=True)

        snap_pass = improved >= 3 and mean_delta <= -0.002
        print(f"    SHIP per-snap: {snap_pass}", flush=True)

        # Train + save the v4_fouls model on full data (regardless of ship gate)
        print(f"    fitting full-data v4_fouls model + integrity check ...",
              flush=True)
        train_meta = train_full_and_save(sub, v4_features, cat_cols, hp, snapshot)

        if snap_pass:
            n_snaps_pass += 1

        results["snapshots"][snapshot] = {
            "n_rows": int(len(sub)),
            "feature_cols_v4": v4_features,
            "cat_cols": cat_cols,
            "v6_hp_baseline_mean_brier_from_meta": float(
                v6_meta.get("wf_eval", {}).get("mean_brier", float("nan"))
            ),
            "rebaseline_briers": rebase_briers,
            "rebaseline_mean": rebase_mean,
            "v4_briers": v4_briers,
            "v4_mean": v4_mean,
            "deltas_per_fold": deltas,
            "mean_delta_vs_rebaseline": mean_delta,
            "folds_improved": improved,
            "n_folds": len(deltas),
            "snap_passes_gate": snap_pass,
            "v4_fold_detail": v4_folds,
            "rebaseline_fold_detail": rebase_folds,
        }

    # Per-snapshot ship decision (each snapshot is independent)
    results["snapshots_passed"] = n_snaps_pass
    # Snapshots that failed the gate: remove their v4_fouls files
    revert_snaps = [s for s in SNAPSHOTS
                    if not results["snapshots"][s]["snap_passes_gate"]]
    keep_snaps = [s for s in SNAPSHOTS
                  if results["snapshots"][s]["snap_passes_gate"]]
    results["revert_snapshots"] = revert_snaps
    results["keep_snapshots"] = keep_snaps

    for snap in revert_snaps:
        print(f"\n  GATE FAILED for {snap} — removing v4_fouls files", flush=True)
        for sfx in (".lgb", "_meta.json"):
            p = os.path.join(MODELS_DIR,
                             f"inplay_winprob_{snap.lower()}_v4_fouls{sfx}")
            if os.path.exists(p):
                try:
                    os.remove(p)
                    print(f"    removed {p}", flush=True)
                except OSError:
                    pass

    if n_snaps_pass == 0:
        results["verdict"] = "REVERT"
        results["reason"] = "0/2 snapshots passed gate"
    elif n_snaps_pass == len(SNAPSHOTS):
        results["verdict"] = "SHIP"
        results["reason"] = f"{n_snaps_pass}/{len(SNAPSHOTS)} snapshots passed gate"
    else:
        results["verdict"] = "PARTIAL_SHIP"
        results["reason"] = (
            f"{n_snaps_pass}/{len(SNAPSHOTS)} snapshots passed gate; "
            f"keep={keep_snaps}, revert={revert_snaps}"
        )

    elapsed = time.time() - t0
    results["elapsed_s"] = float(elapsed)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print("\n" + "=" * 70, flush=True)
    print(f"ITER 65 VERDICT: {results['verdict']}", flush=True)
    print(f"Reason: {results['reason']}", flush=True)
    print(f"Coverage: n_games_full_foul_state={n_games_post_join}", flush=True)
    print("=" * 70, flush=True)
    print(f"  {'Snap':<7} {'Base(refit)':<13} {'V4_FOULS':<11} {'Delta':<10} "
          f"{'Folds':<7} {'Ship?':<6}", flush=True)
    for snap in SNAPSHOTS:
        r = results["snapshots"].get(snap)
        if not r:
            continue
        print(
            f"  {snap:<7} {r['rebaseline_mean']:<13.4f} {r['v4_mean']:<11.4f} "
            f"{r['mean_delta_vs_rebaseline']:<+10.4f} "
            f"{r['folds_improved']}/{r['n_folds']:<5} "
            f"{'YES' if r['snap_passes_gate'] else 'no':<6}",
            flush=True,
        )
    print(f"  Elapsed: {elapsed:.1f}s", flush=True)
    print(f"  Results saved to: {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()
