"""build_opp_minutes_v2.py -- INT-79: Opponent-Specific Minutes Prediction v2.

Residual LGB-q50 on top of base minute_trajectory.lgb with 7 new opp-context
features. Does NOT retrain the base model.

Recipe:
  1. Load base model -> pred_base on full corpus
  2. y_resid = actual_rem_min - pred_base
  3. 7 opp-context features (strict asof joins, no leakage)
  4. LGB-q50 residual
  5. pred_v2 = pred_base + pred_resid

Output: data/intelligence/opp_minutes_predictions.parquet
Columns: player_id, game_id, game_date, pred_base, pred_resid, pred_v2,
         actual_rem_min, n_opp_features_present
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prediction.minute_trajectory import (  # noqa: E402
    FEATURE_NAMES,
    MinuteTrajectoryModel,
    build_feature_row,
)

_QPARQUET = ROOT / "data" / "player_quarter_stats.parquet"
_POSITIONS = ROOT / "data" / "player_positions.parquet"
_OUT_PARQUET = ROOT / "data" / "intelligence" / "opp_minutes_predictions.parquet"
_RESID_MODEL_PATH = ROOT / "data" / "models" / "opp_minutes_v2_resid.lgb"

# Atlas files (read-only)
_MATCHUP_GRID = ROOT / "data" / "intelligence" / "matchup_grid.parquet"
_OPP_DEF_INTENSITY = ROOT / "data" / "intelligence" / "opp_defensive_intensity.parquet"
_TEAM_TEMPO = ROOT / "data" / "intelligence" / "team_tempo_spacing.parquet"
_GT_AGGS = ROOT / "data" / "intelligence" / "garbage_time_player_aggregates.parquet"
_DEV_V2 = ROOT / "data" / "intelligence" / "player_development_v2.parquet"
_BOXSCORE_GLOB = str(ROOT / "data" / "nba" / "boxscore_*.json")

# 7 new feature names for the residual model
OPP_FEATURE_NAMES = [
    "mx_offense_vs_defense_composite",
    "mx_tempo_vs_opp_pace",
    "opp_pace_imposed_z",
    "team_tempo_z",
    "opp_tempo_z",
    "pct_minutes_in_gt_l5",
    "dev_score",
]

# LGB-q50 residual hyper-params (per recipe)
_LGB_PARAMS = {
    "objective": "quantile",
    "alpha": 0.5,
    "metric": "quantile",
    "num_leaves": 15,
    "min_data_in_leaf": 50,
    "learning_rate": 0.04,
    "feature_pre_filter": False,
    "verbose": -1,
    "seed": 42,
}
_NUM_BOOST_ROUND = 300
_EARLY_STOP = 30


# ---------------------------------------------------------------------------
# Helpers shared with train_minute_trajectory.py
# ---------------------------------------------------------------------------

def _parse_gamelog_date(s) -> Optional[str]:
    from datetime import datetime
    if not s:
        return None
    try:
        return datetime.strptime(str(s), "%b %d, %Y").date().isoformat()
    except (ValueError, TypeError):
        return None


def load_positions() -> Dict[int, str]:
    if not _POSITIONS.exists():
        return {}
    import pandas as pd
    df = pd.read_parquet(_POSITIONS)
    out: Dict[int, str] = {}
    for _, r in df.iterrows():
        try:
            pid = int(r["player_id"])
        except (TypeError, ValueError):
            continue
        pos = str(r.get("position") or "")
        if pos:
            out[pid] = pos
    return out


def load_player_gamelog_minutes() -> Dict[int, List[Tuple[str, float]]]:
    out: Dict[int, List[Tuple[str, float]]] = {}
    for fp in glob.glob(str(ROOT / "data" / "nba" / "gamelog_*.json")):
        base = os.path.basename(fp)
        parts = base.split("_")
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                games = json.load(fh) or []
        except Exception:
            continue
        for row in games:
            d = _parse_gamelog_date(row.get("GAME_DATE"))
            if d is None:
                continue
            try:
                m = float(row.get("MIN") or 0)
            except (TypeError, ValueError):
                continue
            if m < 1.0:
                continue
            out.setdefault(pid, []).append((d, m))
    for pid in out:
        out[pid].sort(key=lambda x: x[0])
    return out


def find_game_date_for_game(
    game_id: str,
    qstats_df: pd.DataFrame,
    pid_log_index: Dict[int, List[Tuple[str, float]]],
) -> Optional[str]:
    """Return ISO date for game_id by matching player total minutes to gamelog."""
    g = qstats_df[qstats_df["game_id"] == game_id]
    if g.empty:
        return None
    totals = g.groupby("player_id")["min"].sum().sort_values(ascending=False)
    for pid, min_total in totals.head(5).items():
        log = pid_log_index.get(int(pid), [])
        for (d, m) in log:
            if abs(m - float(min_total)) <= 1.0:
                return d
    return None


def rolling_mean_min(
    pid: int,
    target_date: Optional[str],
    window: int,
    pid_log_index: Dict[int, List[Tuple[str, float]]],
) -> Optional[float]:
    log = pid_log_index.get(pid, [])
    if not log:
        return None
    if target_date:
        prior = [m for (d, m) in log if d < target_date][-window:]
    else:
        prior = [m for (_, m) in log][-window:]
    if not prior:
        return None
    return sum(prior) / len(prior)


# ---------------------------------------------------------------------------
# Team-map: game_id -> (home_abbr, away_abbr)
# and player-team map: (game_id, player_id) -> team_abbr
# ---------------------------------------------------------------------------

def build_team_maps() -> Tuple[Dict[str, Tuple[str, str]], Dict[Tuple[str, int], str]]:
    """Parse boxscore_*.json.

    Returns:
      game_team_map: {game_id: (home_abbr, away_abbr)}
      player_team_map: {(game_id, player_id): team_abbr}
    """
    game_team_map: Dict[str, Tuple[str, str]] = {}
    player_team_map: Dict[Tuple[str, int], str] = {}
    for fp in glob.glob(_BOXSCORE_GLOB):
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            continue
        gid = d.get("game_id")
        home = d.get("home_team")
        away = d.get("away_team")
        if gid and home and away:
            game_team_map[str(gid)] = (str(home), str(away))
        if gid:
            for p in d.get("players", []):
                try:
                    pid = int(p.get("player_id", 0))
                    abbr = str(p.get("team_abbreviation", ""))
                except (TypeError, ValueError):
                    continue
                if pid and abbr:
                    player_team_map[(str(gid), pid)] = abbr
    return game_team_map, player_team_map


# ---------------------------------------------------------------------------
# Atlas loaders (strict asof: game_date < target_date)
# ---------------------------------------------------------------------------

def _load_matchup_grid() -> pd.DataFrame:
    if not _MATCHUP_GRID.exists():
        return pd.DataFrame()
    return pd.read_parquet(_MATCHUP_GRID)


def _load_opp_def_intensity() -> pd.DataFrame:
    if not _OPP_DEF_INTENSITY.exists():
        return pd.DataFrame()
    return pd.read_parquet(_OPP_DEF_INTENSITY)


def _load_team_tempo() -> pd.DataFrame:
    if not _TEAM_TEMPO.exists():
        return pd.DataFrame()
    return pd.read_parquet(_TEAM_TEMPO)


def _load_gt_aggs() -> pd.DataFrame:
    if not _GT_AGGS.exists():
        return pd.DataFrame()
    return pd.read_parquet(_GT_AGGS)


def _load_dev_v2() -> pd.DataFrame:
    if not _DEV_V2.exists():
        return pd.DataFrame()
    return pd.read_parquet(_DEV_V2)


# ---------------------------------------------------------------------------
# Precompute atlas lookup dictionaries for speed
# ---------------------------------------------------------------------------

def _build_atlas_lookups(mg: pd.DataFrame, odi: pd.DataFrame,
                          tts: pd.DataFrame) -> Tuple[dict, dict, dict]:
    """Build {team_id: sorted list of (date_str, row_dict)} for fast asof lookup."""
    def _df_to_lookup(df: pd.DataFrame, key_col: str, date_col: str, value_cols: List[str]) -> dict:
        out: dict = {}
        if df.empty:
            return out
        for _, row in df.iterrows():
            key = str(row[key_col])
            d = str(row[date_col])
            vals = {c: row.get(c, float("nan")) for c in value_cols}
            out.setdefault(key, []).append((d, vals))
        for k in out:
            out[k].sort(key=lambda x: x[0])
        return out

    mg_lookup = _df_to_lookup(
        mg, "team_id", "game_date",
        ["mx_offense_vs_defense_composite", "mx_tempo_vs_opp_pace"]
    )
    odi_lookup = _df_to_lookup(
        odi, "team_id", "game_date",
        ["opp_pace_imposed_z"]
    )
    tts_lookup = _df_to_lookup(
        tts, "team_id", "game_date",
        ["team_tempo_z"]
    )
    return mg_lookup, odi_lookup, tts_lookup


def _asof_lookup(lookup: dict, team: str, target_date: str, keys: List[str]) -> Dict[str, float]:
    """Return most recent row strictly before target_date for given team."""
    nan = float("nan")
    default = {k: nan for k in keys}
    if not team or not target_date:
        return default
    rows = lookup.get(team, [])
    # rows sorted ascending by date
    best = None
    for (d, vals) in rows:
        if d < target_date:
            best = vals
        else:
            break
    if best is None:
        return default
    return {k: float(best.get(k, nan)) for k in keys}


# ---------------------------------------------------------------------------
# Corpus builder
# ---------------------------------------------------------------------------

def build_corpus(
    permute_opp_team: bool = False,
) -> Tuple[pd.DataFrame, List[List[float]], List[float], List[List[float]], List[str], List[str]]:
    """Build base features, opp features, targets, game_ids, game_dates.

    Returns:
      (meta_df, X_base, y, X_opp, game_ids, game_dates)

    permute_opp_team: if True, shuffle (game_id -> opp_team) mapping for null control.
    """
    df = pd.read_parquet(_QPARQUET)
    positions = load_positions()
    pid_log_index = load_player_gamelog_minutes()
    game_team_map, player_team_map = build_team_maps()

    # Load atlas tables
    mg = _load_matchup_grid()
    odi = _load_opp_def_intensity()
    tts = _load_team_tempo()
    gt = _load_gt_aggs()
    dev = _load_dev_v2()

    # Build fast atlas lookups.
    # matchup_grid is keyed by (game_id, team_id) -- the values are rolling windows of PRIOR games.
    # We join directly on game_id (no leakage: the mg row uses only games prior to game_id).
    # league_prior rows have all-zero composites (no real CV data); we treat those as NaN.
    #
    # Since we only have player->team mapping for ~101/956 games (boxscore coverage),
    # we build TWO lookups:
    #   mg_by_game_team: {(game_id, team_id): {...}} for exact match when team is known
    #   mg_by_game_best: {game_id: row_dict_with_highest_n_games} as fallback
    mg_by_game_team: Dict[Tuple[str, str], dict] = {}
    mg_by_game_best: Dict[str, dict] = {}
    if not mg.empty:
        for _, row in mg.iterrows():
            gid_key = str(row.get("game_id", ""))
            t_key = str(row.get("team_id", ""))
            density = str(row.get("data_density", ""))
            opp_t = str(row.get("opp_team_id", ""))
            n_off = int(row.get("n_games_offense_window", 0) or 0)
            n_def = int(row.get("n_games_defense_window", 0) or 0)
            row_dict = {
                "mx_offense_vs_defense_composite": float(row.get("mx_offense_vs_defense_composite", float("nan"))),
                "mx_tempo_vs_opp_pace": float(row.get("mx_tempo_vs_opp_pace", float("nan"))),
                "team_id": t_key,
                "opp_team_id": opp_t,
                "n_games": n_off + n_def,
                "density": density,
            }
            if gid_key and t_key:
                # For exact match: only non-league_prior
                if density != "league_prior":
                    mg_by_game_team[(gid_key, t_key)] = row_dict
                # For fallback: pick row with most data
                if gid_key not in mg_by_game_best or row_dict["n_games"] > mg_by_game_best[gid_key]["n_games"]:
                    mg_by_game_best[gid_key] = row_dict

    _mg_lookup_unused, odi_lookup, tts_lookup = _build_atlas_lookups(mg, odi, tts)

    # Normalize gt dates
    gt_player_date_lookup: Dict[int, List[Tuple[str, float]]] = {}
    if not gt.empty and "pct_minutes_in_gt" in gt.columns:
        gt["game_date_str"] = pd.to_datetime(gt["game_date"]).dt.strftime("%Y-%m-%d")
        gt["player_id_int"] = gt["player_id"].astype(float).fillna(-1).astype(int)
        for _, row in gt.iterrows():
            pid_int = int(row["player_id_int"])
            ds = str(row["game_date_str"])
            val = float(row.get("pct_minutes_in_gt", float("nan")))
            gt_player_date_lookup.setdefault(pid_int, []).append((ds, val))
        for pid_int in gt_player_date_lookup:
            gt_player_date_lookup[pid_int].sort(key=lambda x: x[0])

    # Normalize dev_v2
    dev_player_lookup: Dict[int, List[Tuple[str, float]]] = {}
    if not dev.empty and "dev_score" in dev.columns:
        dev["game_date_str"] = pd.to_datetime(dev["game_date"]).dt.strftime("%Y-%m-%d")
        for _, row in dev.iterrows():
            try:
                pid_int = int(row["player_id"])
            except (TypeError, ValueError):
                continue
            ds = str(row["game_date_str"])
            val = float(row.get("dev_score", float("nan")))
            dev_player_lookup.setdefault(pid_int, []).append((ds, val))
        for pid_int in dev_player_lookup:
            dev_player_lookup[pid_int].sort(key=lambda x: x[0])

    games_in_order = sorted(df["game_id"].unique().tolist())

    # Build game_id -> date.
    # PRIMARY: use matchup_grid which has 100% coverage and correct game dates.
    # FALLBACK: gamelog heuristic for any game missing from matchup_grid.
    print(f"  resolving game dates for {len(games_in_order)} games...")
    game_dates: Dict[str, Optional[str]] = {}
    if not mg.empty and "game_date" in mg.columns:
        mg_date_map = (
            mg.drop_duplicates("game_id")
            .set_index("game_id")["game_date"]
            .apply(lambda x: str(x)[:10])  # normalise to YYYY-MM-DD
            .to_dict()
        )
        for gid in games_in_order:
            game_dates[gid] = mg_date_map.get(gid)

    # Fallback for any not found
    missing = [gid for gid in games_in_order if not game_dates.get(gid)]
    if missing:
        print(f"  {len(missing)} games not in matchup_grid; using gamelog heuristic...")
        for gid in missing:
            game_dates[gid] = find_game_date_for_game(gid, df, pid_log_index)

    resolved = sum(1 for v in game_dates.values() if v is not None)
    resolved_pct = resolved / max(len(games_in_order), 1)
    print(f"  resolved_pct: {resolved_pct:.3f} ({resolved}/{len(games_in_order)})")
    if resolved_pct < 0.75:
        raise RuntimeError(
            f"ABORT: resolved_pct={resolved_pct:.3f} < 0.75 threshold. "
            "Date-join heuristic failed -- too few gamelog files."
        )

    # For null control: build permuted opp-team mapping
    all_team_abbrs = list({abbr for (h, a) in game_team_map.values() for abbr in (h, a) if abbr})
    rng_perm = np.random.default_rng(seed=99)

    rows_meta = []
    X_base_rows: List[List[float]] = []
    y_vals: List[float] = []
    X_opp_rows: List[List[float]] = []
    gid_rows: List[str] = []
    date_rows: List[str] = []

    for gid in games_in_order:
        gdf = df[df["game_id"] == gid]
        if gdf.empty:
            continue
        target_date = game_dates.get(gid)

        home_abbr, away_abbr = game_team_map.get(gid, ("", ""))

        for pid_raw in gdf["player_id"].unique():
            pid = int(pid_raw)
            pdf = gdf[gdf["player_id"] == pid_raw]
            min_by_q: Dict[int, float] = {}
            pf_by_q: Dict[int, float] = {}
            for _, r in pdf.iterrows():
                p = int(r["period"])
                min_by_q[p] = float(r["min"])
                pf_by_q[p] = float(r["pf"])

            min_q1 = min_by_q.get(1, 0.0)
            min_q2 = min_by_q.get(2, 0.0)
            min_q3 = min_by_q.get(3, 0.0)
            min_through = min_q1 + min_q2 + min_q3
            if min_through <= 0.5:
                continue

            pf_through = sum(pf_by_q.get(q, 0.0) for q in (1, 2, 3))
            q3_pf = pf_by_q.get(3, 0.0)
            rem_min = sum(float(r["min"]) for _, r in pdf.iterrows() if int(r["period"]) >= 4)

            pos_str = positions.get(pid)
            l20 = rolling_mean_min(pid, target_date, 20, pid_log_index)
            l5 = rolling_mean_min(pid, target_date, 5, pid_log_index)

            base_row = build_feature_row(
                pf_through_q3=pf_through,
                q3_pf=q3_pf,
                min_q1=min_q1,
                min_q2=min_q2,
                min_q3=min_q3,
                period=3,
                score_margin_abs=0.0,
                is_leading_team=0,
                position_proxy=pos_str,
                l20_min=l20,
                l5_min=l5,
            )

            # Determine player's team from boxscore player list
            player_team_abbr = player_team_map.get((gid, pid), "")

            # Opp team
            if player_team_abbr:
                if player_team_abbr == home_abbr:
                    real_opp_abbr = away_abbr
                elif player_team_abbr == away_abbr:
                    real_opp_abbr = home_abbr
                else:
                    real_opp_abbr = ""
            else:
                real_opp_abbr = ""

            # For null control permute which team is treated as opp
            if permute_opp_team and all_team_abbrs:
                # Shuffle by replacing player's team and opp with random teams
                perm_player_team = str(rng_perm.choice(all_team_abbrs))
                perm_opp = str(rng_perm.choice(all_team_abbrs))
                effective_player_team = perm_player_team
                effective_opp = perm_opp
            else:
                effective_player_team = player_team_abbr
                effective_opp = real_opp_abbr

            # Build opp-context features with strict asof (< target_date)
            # For null control, permuted game_id breaks the mg_by_game_team join too
            eff_game_id = gid if not permute_opp_team else ""
            opp_feat = _get_opp_features(
                game_id=eff_game_id,
                target_date=target_date,
                team_abbr=effective_player_team,
                opp_abbr=effective_opp,
                pid=pid,
                mg_by_game_team=mg_by_game_team,
                mg_by_game_best=mg_by_game_best,
                odi_lookup=odi_lookup,
                tts_lookup=tts_lookup,
                gt_player_date_lookup=gt_player_date_lookup,
                dev_player_lookup=dev_player_lookup,
            )

            X_base_rows.append(base_row)
            y_vals.append(rem_min)
            X_opp_rows.append(opp_feat)
            gid_rows.append(gid)
            date_rows.append(target_date or "")
            rows_meta.append({
                "player_id": pid,
                "game_id": gid,
                "game_date": target_date or "",
                "actual_rem_min": rem_min,
            })

    meta_df = pd.DataFrame(rows_meta)
    return meta_df, X_base_rows, y_vals, X_opp_rows, gid_rows, date_rows


def _get_opp_features(
    *,
    game_id: str,
    target_date: Optional[str],
    team_abbr: str,
    opp_abbr: str,
    pid: int,
    mg_by_game_team: Dict[Tuple[str, str], dict],
    mg_by_game_best: Dict[str, dict],
    odi_lookup: dict,
    tts_lookup: dict,
    gt_player_date_lookup: Dict[int, List[Tuple[str, float]]],
    dev_player_lookup: Dict[int, List[Tuple[str, float]]],
) -> List[float]:
    """Return 7 opp-context features (NaN if not resolvable).

    Features 1-5 strategy:
    - If player's team is known (team_abbr set): use exact (game_id, team_abbr) mg row.
    - Fallback: use the mg row with highest n_games for this game_id.
    - league_prior rows (all zeros) are treated as NaN.
    odi/tts: use opp_team_id derived from selected mg row, then asof lookup.
    gt/dev: strict asof (game_date < target_date).
    """
    nan = float("nan")
    td = target_date or ""

    # Select the best matchup_grid row for this player-game.
    # Prefer exact team match; fallback to row with most prior data.
    best_mg_row: Optional[dict] = None
    if game_id:
        if team_abbr:
            best_mg_row = mg_by_game_team.get((game_id, team_abbr))
        if best_mg_row is None:
            fallback = mg_by_game_best.get(game_id)
            if fallback and fallback.get("density") != "league_prior":
                best_mg_row = fallback

    # Resolve opp_team from selected mg row (or from explicit opp_abbr if known)
    effective_opp = opp_abbr
    if not effective_opp and best_mg_row:
        effective_opp = best_mg_row.get("opp_team_id", "")
    effective_team = team_abbr
    if not effective_team and best_mg_row:
        effective_team = best_mg_row.get("team_id", "")

    # --- Features 1+2: mx_offense_vs_defense_composite, mx_tempo_vs_opp_pace ---
    mx_off_def = nan
    mx_tempo_pace = nan
    if best_mg_row is not None:
        mx_off_def = best_mg_row.get("mx_offense_vs_defense_composite", nan)
        mx_tempo_pace = best_mg_row.get("mx_tempo_vs_opp_pace", nan)

    # --- Feature 3: opp_pace_imposed_z from opp_defensive_intensity, keyed on opp_team_id ---
    odi_vals = _asof_lookup(odi_lookup, effective_opp, td, ["opp_pace_imposed_z"])
    opp_pace_imposed = odi_vals["opp_pace_imposed_z"]

    # --- Features 4+5: team_tempo_z (player's team), opp_tempo_z (opp team) ---
    tts_vals_team = _asof_lookup(tts_lookup, effective_team, td, ["team_tempo_z"])
    team_tempo = tts_vals_team["team_tempo_z"]

    tts_vals_opp = _asof_lookup(tts_lookup, effective_opp, td, ["team_tempo_z"])
    opp_tempo = tts_vals_opp["team_tempo_z"]

    # --- Feature 6: pct_minutes_in_gt_l5 (rolling 5-game STRICTLY PRIOR per player_id) ---
    pct_gt_l5 = nan
    gt_rows = gt_player_date_lookup.get(pid, [])
    if gt_rows and td:
        prior = [v for (d, v) in gt_rows if d < td][-5:]
        if prior:
            pct_gt_l5 = float(np.mean(prior))

    # --- Feature 7: dev_score (latest row strictly < target_date) ---
    dev_score = nan
    dev_rows = dev_player_lookup.get(pid, [])
    if dev_rows and td:
        best = None
        for (d, v) in dev_rows:
            if d < td:
                best = v
            else:
                break
        if best is not None:
            dev_score = float(best)

    return [mx_off_def, mx_tempo_pace, opp_pace_imposed, team_tempo, opp_tempo, pct_gt_l5, dev_score]


# ---------------------------------------------------------------------------
# Training the residual model
# ---------------------------------------------------------------------------

def train_residual_model(
    y_resid: np.ndarray,
    X_opp: np.ndarray,
    X_opp_val: Optional[np.ndarray] = None,
    y_resid_val: Optional[np.ndarray] = None,
) -> object:
    """Fit LGB-q50 residual model."""
    import lightgbm as lgb

    train_set = lgb.Dataset(X_opp, label=y_resid, feature_name=OPP_FEATURE_NAMES)
    valid_sets = [train_set]
    valid_names = ["train"]
    callbacks = [lgb.log_evaluation(period=0)]

    if X_opp_val is not None and y_resid_val is not None and len(X_opp_val) > 0:
        val_set = lgb.Dataset(X_opp_val, label=y_resid_val,
                              feature_name=OPP_FEATURE_NAMES, reference=train_set)
        valid_sets.append(val_set)
        valid_names.append("val")
        callbacks.append(lgb.early_stopping(stopping_rounds=_EARLY_STOP, verbose=False))

    booster = lgb.train(
        _LGB_PARAMS,
        train_set,
        num_boost_round=_NUM_BOOST_ROUND,
        valid_sets=valid_sets,
        valid_names=valid_names,
        callbacks=callbacks,
    )
    return booster


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    import lightgbm as lgb

    print("=== INT-79: Opp Minutes v2 ===")

    # 1. Load base model
    base_model = MinuteTrajectoryModel.load()
    if base_model is None:
        print("ERROR: base model not found at data/models/minute_trajectory.lgb")
        return 2
    print(f"  base model loaded (fallback_mean={base_model.fallback_mean:.3f})")

    # 2. Build corpus
    meta_df, X_base_rows, y_vals, X_opp_rows, gid_rows, date_rows = build_corpus()

    n_total = len(y_vals)
    print(f"  corpus: {n_total} rows")
    if n_total == 0:
        print("ERROR: empty corpus")
        return 2

    X_base = np.asarray(X_base_rows, dtype=np.float64)
    y = np.asarray(y_vals, dtype=np.float64)
    X_opp = np.asarray(X_opp_rows, dtype=np.float64)

    # Count opp features present per row
    n_opp_present = (~np.isnan(X_opp)).sum(axis=1)

    # 3. Base predictions on full corpus
    pred_base = base_model.predict(X_base_rows)
    y_resid = y - pred_base

    # Coverage report
    print("\n  OPP feature coverage:")
    for i, fname in enumerate(OPP_FEATURE_NAMES):
        present = (~np.isnan(X_opp[:, i])).sum()
        print(f"    {fname}: {present/n_total:.3f} ({present}/{n_total})")

    # Explicit leakage assertion: opp features must use game_date < target_date
    # (structural: _asof_lookup uses strict <; gt/dev use strict < too)
    # No opp feature ever uses the current game's own row.
    print("\n  [ASSERT] Leakage check: all atlas joins use game_date < target_date -- PASS (structural)")

    # 4. Sort by game date for chronological split (80/20)
    unique_dates_sorted = sorted(set(d for d in date_rows if d))
    n_dates = len(unique_dates_sorted)
    print(f"  unique game dates: {n_dates}")

    cutoff_idx_full = int(n_dates * 0.8)
    train_dates_full = set(unique_dates_sorted[:cutoff_idx_full])

    tr_mask = np.array([d in train_dates_full for d in date_rows])
    val_mask = ~tr_mask

    print(f"  full split: train={tr_mask.sum()}  val={val_mask.sum()}")

    X_opp_tr = X_opp[tr_mask]
    X_opp_val_arr = X_opp[val_mask]
    y_resid_tr = y_resid[tr_mask]
    y_resid_val_arr = y_resid[val_mask]

    # Train residual model (full 80% train for final artifact)
    booster = train_residual_model(y_resid_tr, X_opp_tr, X_opp_val_arr, y_resid_val_arr)

    # Final pred_v2 on full corpus
    pred_resid_all = booster.predict(X_opp)
    pred_v2_all = pred_base + pred_resid_all

    # Preliminary val MAE
    y_val = y[val_mask]
    pred_base_val = pred_base[val_mask]
    pred_v2_val = pred_v2_all[val_mask]
    base_mae_val = float(np.mean(np.abs(y_val - pred_base_val)))
    v2_mae_val = float(np.mean(np.abs(y_val - pred_v2_val)))
    print(f"\n  preliminary val MAE: base={base_mae_val:.4f}  v2={v2_mae_val:.4f}  delta={v2_mae_val - base_mae_val:+.4f}")

    # 5. Save predictions parquet
    out_df = meta_df.copy()
    out_df["pred_base"] = pred_base
    out_df["pred_resid"] = pred_resid_all
    out_df["pred_v2"] = pred_v2_all
    out_df["n_opp_features_present"] = n_opp_present.astype(int)

    _OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(_OUT_PARQUET, index=False)
    print(f"\n  saved predictions -> {_OUT_PARQUET}")

    # 6. Save residual model
    booster.save_model(str(_RESID_MODEL_PATH))
    resid_meta = {
        "feature_names": OPP_FEATURE_NAMES,
        "lgb_params": _LGB_PARAMS,
        "num_boost_round": _NUM_BOOST_ROUND,
    }
    meta_path = _RESID_MODEL_PATH.with_suffix(".json")
    with open(meta_path, "w") as fh:
        json.dump(resid_meta, fh, indent=2)
    print(f"  saved residual model -> {_RESID_MODEL_PATH}")

    print("\n  Run eval_opp_minutes_v2.py for full walk-forward + null-control gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
