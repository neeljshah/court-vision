"""
iter63_inplay_quarter_efficiency.py
====================================
Iter 63 — Backfill quarter-box derived efficiency features into the inplay
winprob models for endQ1/Q2/Q3.

Hypothesis: at each endQ snapshot, per-team cumulative shooting efficiency
(TS%, eFG%), TOV rate, OREB%, and FT rate are leading indicators of
subsequent quarters' outcomes beyond raw point totals. The current endQ1
model has zero quality-of-scoring signal (only score margin, total_pts,
pace, q1_delta, last_q_margin, pregame_wp, home_team_id, season).

New features per snapshot (one row per game per snapshot):
  - home_ts_pct_cum, away_ts_pct_cum   = PTS / (2 * (FGA + 0.44*FTA))
  - home_efg_pct_cum, away_efg_pct_cum = (FGM + 0.5*3PM) / FGA
  - home_tov_per_poss_cum, away_tov_per_poss_cum = TO / approx possessions
  - home_ft_rate_cum, away_ft_rate_cum = FTA / FGA
  - home_oreb_pct_cum, away_oreb_pct_cum = OREB / (OREB + opp_DREB)

Cumulative through end of last completed quarter at the snapshot
(endQ1 = Q1 only, endQ2 = Q1+Q2, endQ3 = Q1+Q2+Q3).

Method:
  1) Build qbox_efficiency parquet (one row per game per snapshot, 10 new cols).
  2) Join into the same training rows the OOS validator uses (linescores +
     season_games + quarter_features).
  3) Train v2_qbox LightGBM models with [existing feature_cols + 10 new cols]
     and same hyperparams from existing _meta.json.
  4) 4-fold expanding WF on game_date order. Report per-fold Brier delta vs
     the existing v1 model.

Ship gate:
  - >=3/4 WF folds improved (lower Brier on same snapshot) AND
  - mean Brier delta <= -0.002 on that snapshot
  - Coverage gate: post-join n_games >= 1500 (else flag INSUFFICIENT_COVERAGE)

DO NOT TOUCH the existing .lgb / _meta.json files. Save new artifacts as
inplay_winprob_endq{1,2,3}_v2_qbox.lgb (+ _meta.json).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

NBA_CACHE = PROJECT / "data" / "nba"
DATA_CACHE = PROJECT / "data" / "cache"
MODELS_DIR = PROJECT / "data" / "models"
QUARTER_BOX_DIR = DATA_CACHE / "quarter_box"

QBOX_PARQUET = DATA_CACHE / "inplay_qbox_efficiency.parquet"
OUT_JSON = DATA_CACHE / "iter63_inplay_qbox_results.json"

DATA_CACHE.mkdir(parents=True, exist_ok=True)

MINUTES_PER_QUARTER = 12.0
SNAPSHOTS = ["endQ1", "endQ2", "endQ3"]
N_FOLDS = 4
RANDOM_SEED = 42
COVERAGE_MIN = 1500

NEW_FEATS = [
    "home_ts_pct_cum", "away_ts_pct_cum",
    "home_efg_pct_cum", "away_efg_pct_cum",
    "home_tov_per_poss_cum", "away_tov_per_poss_cum",
    "home_ft_rate_cum", "away_ft_rate_cum",
    "home_oreb_pct_cum", "away_oreb_pct_cum",
]


# ── data loaders ─────────────────────────────────────────────────────────────

def load_meta(snapshot: str) -> Dict[str, Any]:
    path = MODELS_DIR / f"inplay_winprob_{snapshot.lower()}_meta.json"
    with open(path) as f:
        return json.load(f)


def load_linescores() -> Dict[str, Dict]:
    with open(NBA_CACHE / "linescores_all.json") as f:
        return json.load(f)


def load_season_games() -> Dict[str, Dict]:
    seasons = ["2022-23", "2023-24", "2024-25"]
    all_rows: Dict[str, Dict] = {}
    for s in seasons:
        path = NBA_CACHE / f"season_games_{s}.json"
        if not path.exists():
            print(f"  [WARN] missing {path}", flush=True)
            continue
        with open(path) as f:
            data = json.load(f)
        for row in data.get("rows", []):
            all_rows[row["game_id"]] = row
    return all_rows


def load_quarter_features_summaries() -> Dict[str, Dict[str, float]]:
    path = DATA_CACHE / "quarter_features.parquet"
    if not path.exists():
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


# ── quarter_box efficiency builder ───────────────────────────────────────────

def load_quarter_json(gid: str, q: int) -> Dict | None:
    p = QUARTER_BOX_DIR / f"{gid}_q{q}.json"
    if not p.exists():
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _team_stat(team_row: Dict, key: str) -> float:
    v = team_row.get(key, 0)
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _possessions(fga: float, fta: float, oreb: float, to: float) -> float:
    return max(fga + 0.44 * fta - oreb + to, 1.0)


def build_efficiency_parquet(home_team_lookup: Dict[str, int]) -> pd.DataFrame:
    """For every (game_id, snapshot), compute home/away cumulative efficiency."""
    records: List[Dict] = []
    all_q1_paths = sorted(QUARTER_BOX_DIR.glob("*_q1.json"))
    print(f"  Scanning {len(all_q1_paths)} quarter_box games ...", flush=True)

    missing_home_match = 0
    parse_errors = 0

    for q1_path in all_q1_paths:
        gid = q1_path.name.replace("_q1.json", "")
        # Load up to 3 quarters
        qdata: Dict[int, Dict] = {}
        for q in (1, 2, 3):
            d = load_quarter_json(gid, q)
            if d is None:
                break
            qdata[q] = d
        if not qdata:
            parse_errors += 1
            continue

        # Get team rows from q1 (teams persist across quarters)
        teams_q1 = qdata[1].get("teams", [])
        if len(teams_q1) != 2:
            parse_errors += 1
            continue

        # Determine home team via linescore lookup; fallback: skip
        home_tid = home_team_lookup.get(gid)
        if home_tid is None:
            missing_home_match += 1
            continue

        team_ids = [int(t["team_id"]) for t in teams_q1]
        if home_tid not in team_ids:
            missing_home_match += 1
            continue
        away_tid = [t for t in team_ids if t != home_tid][0]

        # Per quarter team rows
        def team_row_q(tid: int, q: int) -> Dict | None:
            if q not in qdata:
                return None
            for t in qdata[q].get("teams", []):
                if int(t["team_id"]) == tid:
                    return t
            return None

        # Build cumulative through n_qtrs for n in 1..max(qdata.keys())
        max_q_available = max(qdata.keys())

        for n_qtrs in range(1, max_q_available + 1):
            snapshot = f"endQ{n_qtrs}"

            cum: Dict[str, Dict[str, float]] = {"home": {}, "away": {}}
            valid = True
            for side, tid in (("home", home_tid), ("away", away_tid)):
                fga = fgm = fg3m = fta = ftm = oreb = dreb = to = pts = 0.0
                for q in range(1, n_qtrs + 1):
                    tr = team_row_q(tid, q)
                    if tr is None:
                        valid = False
                        break
                    fga += _team_stat(tr, "fga")
                    fgm += _team_stat(tr, "fgm")
                    fg3m += _team_stat(tr, "fg3m")
                    fta += _team_stat(tr, "fta")
                    ftm += _team_stat(tr, "ftm")
                    oreb += _team_stat(tr, "oreb")
                    dreb += _team_stat(tr, "dreb")
                    to += _team_stat(tr, "to")
                    pts += _team_stat(tr, "pts")
                if not valid:
                    break
                cum[side] = dict(
                    fga=fga, fgm=fgm, fg3m=fg3m, fta=fta, ftm=ftm,
                    oreb=oreb, dreb=dreb, to=to, pts=pts,
                )

            if not valid:
                continue

            def safe_div(num: float, den: float) -> float:
                return float(num / den) if den > 0 else 0.0

            row = {
                "game_id": gid,
                "snapshot": snapshot,
            }
            for side in ("home", "away"):
                c = cum[side]
                opp = cum["away" if side == "home" else "home"]
                ts_den = 2.0 * (c["fga"] + 0.44 * c["fta"])
                row[f"{side}_ts_pct_cum"] = safe_div(c["pts"], ts_den)
                row[f"{side}_efg_pct_cum"] = safe_div(
                    c["fgm"] + 0.5 * c["fg3m"], c["fga"]
                )
                poss = _possessions(c["fga"], c["fta"], c["oreb"], c["to"])
                row[f"{side}_tov_per_poss_cum"] = safe_div(c["to"], poss)
                row[f"{side}_ft_rate_cum"] = safe_div(c["fta"], c["fga"])
                row[f"{side}_oreb_pct_cum"] = safe_div(
                    c["oreb"], c["oreb"] + opp["dreb"]
                )

            records.append(row)

    df = pd.DataFrame(records)
    print(
        f"  Built efficiency parquet: {len(df)} rows, "
        f"{df['game_id'].nunique() if len(df) else 0} games. "
        f"Skipped (no home match): {missing_home_match}, "
        f"parse errors: {parse_errors}",
        flush=True,
    )
    return df


# ── inplay training rows (mirror oos_validate_inplay_2026_05_27) ─────────────

def build_inplay_rows(
    linescores: Dict,
    season_games: Dict,
    qf_summaries: Dict[str, Dict[str, float]],
) -> pd.DataFrame:
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
            records.append({
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
            })

    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    return df


# ── WF train + eval (v1 baseline AND v2_qbox model in parallel) ──────────────

def walk_forward_compare(
    df_snap: pd.DataFrame,
    feat_cols_v1: List[str],
    feat_cols_v2: List[str],
    cat_cols: List[str],
    hyperparams: Dict[str, Any],
    n_folds: int = N_FOLDS,
) -> Tuple[List[Dict], List[Dict]]:
    """Run WF for both v1 (baseline) and v2 (v1 + NEW_FEATS) using same folds."""
    import lightgbm as lgb
    from sklearn.metrics import (accuracy_score, brier_score_loss,
                                 log_loss, roc_auc_score)

    n = len(df_snap)
    min_train = int(n * 0.60)
    test_size = (n - min_train) // n_folds

    v1_folds: List[Dict] = []
    v2_folds: List[Dict] = []

    for fold in range(n_folds):
        train_end = min_train + fold * test_size
        test_start = train_end
        test_end = test_start + test_size if fold < n_folds - 1 else n
        if train_end < 30 or test_start >= n:
            continue
        if test_end - test_start < 10:
            continue

        y_tr = df_snap["home_team_won"].iloc[:train_end]
        y_te = df_snap["home_team_won"].iloc[test_start:test_end]
        y_te_arr = y_te.values

        for tag, feat_cols, target_list in (
            ("v1", feat_cols_v1, v1_folds),
            ("v2", feat_cols_v2, v2_folds),
        ):
            X_tr = df_snap[feat_cols].iloc[:train_end].copy()
            X_te = df_snap[feat_cols].iloc[test_start:test_end].copy()
            active_cats = [c for c in cat_cols if c in X_tr.columns]
            for c in active_cats:
                X_tr[c] = X_tr[c].astype("category")
                X_te[c] = X_te[c].astype("category")

            model = lgb.LGBMClassifier(
                n_estimators=int(hyperparams.get("n_estimators", 300)),
                learning_rate=float(hyperparams.get("learning_rate", 0.05)),
                num_leaves=int(hyperparams.get("num_leaves", 31)),
                min_child_samples=int(hyperparams.get("min_child_samples", 20)),
                subsample=float(hyperparams.get("subsample", 0.8)),
                colsample_bytree=float(hyperparams.get("colsample_bytree", 0.8)),
                reg_alpha=float(hyperparams.get("reg_alpha", 0.1)),
                reg_lambda=float(hyperparams.get("reg_lambda", 1.0)),
                random_state=int(hyperparams.get("random_state", RANDOM_SEED)),
                n_jobs=4,
                verbose=-1,
            )
            model.fit(X_tr, y_tr, categorical_feature=active_cats if active_cats else "auto")
            probs = model.predict_proba(X_te)[:, 1]
            preds = (probs >= 0.5).astype(int)
            probs_safe = np.clip(probs, 1e-6, 1.0 - 1e-6)
            try:
                auc = float(roc_auc_score(y_te_arr, probs))
            except ValueError:
                auc = float("nan")
            target_list.append({
                "fold": fold,
                "tag": tag,
                "train_n": int(len(X_tr)),
                "test_n": int(len(X_te)),
                "brier": float(brier_score_loss(y_te_arr, probs)),
                "log_loss": float(log_loss(y_te_arr, probs_safe)),
                "auc": auc,
                "accuracy": float(accuracy_score(y_te_arr, preds)),
            })

        print(
            f"    fold {fold}: train={train_end} test={test_end - test_start} "
            f"v1 Brier={v1_folds[-1]['brier']:.4f} "
            f"v2 Brier={v2_folds[-1]['brier']:.4f} "
            f"delta={v2_folds[-1]['brier'] - v1_folds[-1]['brier']:+.4f}",
            flush=True,
        )

    return v1_folds, v2_folds


# ── fit FULL model + save (only if ship) ─────────────────────────────────────

def fit_and_save_full(
    df_snap: pd.DataFrame,
    feat_cols_v2: List[str],
    cat_cols: List[str],
    hyperparams: Dict[str, Any],
    snapshot: str,
    in_sample_metrics_v1: Dict[str, float],
) -> Tuple[Path, Path]:
    import lightgbm as lgb
    from sklearn.metrics import (accuracy_score, brier_score_loss,
                                 log_loss, roc_auc_score)

    X = df_snap[feat_cols_v2].copy()
    y = df_snap["home_team_won"]
    active_cats = [c for c in cat_cols if c in X.columns]
    for c in active_cats:
        X[c] = X[c].astype("category")

    model = lgb.LGBMClassifier(
        n_estimators=int(hyperparams.get("n_estimators", 300)),
        learning_rate=float(hyperparams.get("learning_rate", 0.05)),
        num_leaves=int(hyperparams.get("num_leaves", 31)),
        min_child_samples=int(hyperparams.get("min_child_samples", 20)),
        subsample=float(hyperparams.get("subsample", 0.8)),
        colsample_bytree=float(hyperparams.get("colsample_bytree", 0.8)),
        reg_alpha=float(hyperparams.get("reg_alpha", 0.1)),
        reg_lambda=float(hyperparams.get("reg_lambda", 1.0)),
        random_state=int(hyperparams.get("random_state", RANDOM_SEED)),
        n_jobs=4,
        verbose=-1,
    )
    model.fit(X, y, categorical_feature=active_cats if active_cats else "auto")

    probs = model.predict_proba(X)[:, 1]
    preds = (probs >= 0.5).astype(int)
    probs_safe = np.clip(probs, 1e-6, 1 - 1e-6)
    in_sample = {
        "auc": float(roc_auc_score(y, probs)),
        "brier": float(brier_score_loss(y, probs)),
        "log_loss": float(log_loss(y, probs_safe)),
        "accuracy": float(accuracy_score(y, preds)),
    }

    lgb_path = MODELS_DIR / f"inplay_winprob_{snapshot.lower()}_v2_qbox.lgb"
    meta_path = MODELS_DIR / f"inplay_winprob_{snapshot.lower()}_v2_qbox_meta.json"

    booster = model.booster_
    booster.save_model(str(lgb_path))

    # pkl integrity check
    n_feat_booster = booster.num_feature()
    n_feat_meta = len(feat_cols_v2)
    assert n_feat_booster == n_feat_meta, (
        f"pkl integrity fail: booster.num_feature()={n_feat_booster} "
        f"!= meta.feature_cols len={n_feat_meta}"
    )

    meta = {
        "snapshot": snapshot,
        "feature_cols": feat_cols_v2,
        "categorical_cols": active_cats,
        "n_train_rows": int(len(X)),
        "home_win_rate": float(y.mean()),
        "in_sample": in_sample,
        "in_sample_v1_reference": in_sample_metrics_v1,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "probe": "iter63_inplay_qbox_efficiency",
        "based_on": f"inplay_winprob_{snapshot.lower()}",
        "added_features": NEW_FEATS,
        "hyperparams": hyperparams,
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    return lgb_path, meta_path


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=== Iter 63: inplay v2_qbox quarter-efficiency features ===", flush=True)

    print("\n[1] Load metas ...", flush=True)
    metas = {snap: load_meta(snap) for snap in SNAPSHOTS}

    print("\n[2] Load data ...", flush=True)
    linescores = load_linescores()
    season_games = load_season_games()
    qf_summaries = load_quarter_features_summaries()
    print(
        f"  linescores={len(linescores)}, season_games={len(season_games)}, "
        f"qf_summaries={len(qf_summaries)}",
        flush=True,
    )

    # Build home_team_lookup gid -> home_team_id
    home_team_lookup: Dict[str, int] = {}
    for gid, ls in linescores.items():
        htid = ls.get("home_team_id")
        if htid is not None:
            try:
                home_team_lookup[gid] = int(htid)
            except (TypeError, ValueError):
                pass

    print("\n[3] Build efficiency parquet from quarter_box ...", flush=True)
    eff_df = build_efficiency_parquet(home_team_lookup)
    if len(eff_df) == 0:
        print("  [ERROR] no efficiency rows", flush=True)
        sys.exit(1)
    eff_df.to_parquet(QBOX_PARQUET, index=False, engine="pyarrow")
    print(f"  saved -> {QBOX_PARQUET}", flush=True)

    print("\n[4] Build inplay training rows ...", flush=True)
    df = build_inplay_rows(linescores, season_games, qf_summaries)
    valid_games = set(df[df["snapshot"] == "endQ3"]["game_id"].tolist())
    df = df[df["game_id"].isin(valid_games)].copy()
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    print(f"  inplay rows: {len(df)}, games: {df['game_id'].nunique()}", flush=True)

    print("\n[5] Join efficiency features ...", flush=True)
    df = df.merge(eff_df, on=["game_id", "snapshot"], how="left")
    # Coverage
    coverage_per_snap = {}
    for snap in SNAPSHOTS:
        sub = df[df["snapshot"] == snap]
        n_total = len(sub)
        n_with_qbox = int(sub["home_ts_pct_cum"].notna().sum())
        coverage_per_snap[snap] = {
            "rows_total": n_total,
            "rows_with_qbox": n_with_qbox,
            "coverage_pct": float(n_with_qbox / max(1, n_total)),
        }
        print(
            f"  {snap}: {n_with_qbox}/{n_total} qbox-covered "
            f"({100*n_with_qbox/max(1,n_total):.1f}%)",
            flush=True,
        )

    # Fill missing efficiency features with 0 so we can still train (treat as
    # "no signal available"); but for coverage gate we count games whose ROW
    # has qbox.
    for f in NEW_FEATS:
        df[f] = df[f].fillna(0.0)

    # Limit to rows where qbox covers all 3 snapshots? Per spec we apply
    # coverage gate per snapshot. We keep all rows but track coverage. The
    # model gets meaningful signal only on qbox-covered rows; uncovered rows
    # contribute zero-imputed features (effectively just adds noise to that
    # row's prediction).
    # Following the existing pattern in oos_validate_inplay (it does NOT drop
    # rows with missing q1_usg_avg etc — they're left as NaN and LGB handles
    # them), we do the same here. But our 0-fill could bias things, so let's
    # instead use NaN — LGB handles NaN natively.
    for f in NEW_FEATS:
        df[f] = df[f].replace(0.0, np.nan)
        # Actually we just fillna(0) above then replaced — bug-prone. Re-merge.
    # Redo: re-merge cleanly.
    df = df.drop(columns=NEW_FEATS, errors="ignore")
    df = df.merge(eff_df, on=["game_id", "snapshot"], how="left")
    # leave NaN as-is (LightGBM handles missing)

    print("\n[6] WF compare v1 vs v2_qbox per snapshot ...", flush=True)
    per_snap: Dict[str, Dict] = {}
    for snap in SNAPSHOTS:
        print(f"\n--- {snap} ---", flush=True)
        meta = metas[snap]
        feat_v1 = list(meta["feature_cols"])
        cat_cols = list(meta.get("categorical_cols", []))
        hyperparams = dict(meta.get("hyperparams", {}))
        feat_v2 = feat_v1 + NEW_FEATS

        sub = df[df["snapshot"] == snap].copy().reset_index(drop=True)
        n_games_snap = sub["game_id"].nunique()
        # Coverage gate based on rows that have qbox features
        n_with_qbox = int(sub["home_ts_pct_cum"].notna().sum())
        coverage_ok = n_with_qbox >= COVERAGE_MIN

        print(
            f"  n_rows={len(sub)}, n_games={n_games_snap}, "
            f"qbox-covered={n_with_qbox}, coverage_ok={coverage_ok}",
            flush=True,
        )
        print(f"  feat_v1 ({len(feat_v1)}): {feat_v1}", flush=True)
        print(f"  feat_v2 ({len(feat_v2)}): added {len(NEW_FEATS)} qbox feats",
              flush=True)

        v1_folds, v2_folds = walk_forward_compare(
            sub, feat_v1, feat_v2, cat_cols, hyperparams, n_folds=N_FOLDS,
        )

        per_fold_delta = [
            v2_folds[i]["brier"] - v1_folds[i]["brier"]
            for i in range(len(v1_folds))
        ]
        folds_improved = sum(1 for d in per_fold_delta if d < 0)
        mean_v1 = float(np.mean([f["brier"] for f in v1_folds]))
        mean_v2 = float(np.mean([f["brier"] for f in v2_folds]))
        mean_delta = float(np.mean(per_fold_delta)) if per_fold_delta else float("nan")

        ship_brier = folds_improved >= 3 and mean_delta <= -0.002
        flags: List[str] = []
        if not coverage_ok:
            flags.append("INSUFFICIENT_COVERAGE")
        ship = ship_brier and coverage_ok

        print(
            f"  RESULT: v1_mean={mean_v1:.4f}, v2_mean={mean_v2:.4f}, "
            f"delta={mean_delta:+.4f}, folds_improved={folds_improved}/4, "
            f"ship={ship} {flags}",
            flush=True,
        )

        snap_res = {
            "snapshot": snap,
            "n_rows": int(len(sub)),
            "n_games": int(n_games_snap),
            "n_with_qbox": n_with_qbox,
            "coverage_ok": coverage_ok,
            "feat_v1": feat_v1,
            "feat_v2": feat_v2,
            "v1_folds": v1_folds,
            "v2_folds": v2_folds,
            "v1_mean_brier": mean_v1,
            "v2_mean_brier": mean_v2,
            "mean_brier_delta": mean_delta,
            "per_fold_delta": per_fold_delta,
            "folds_improved": folds_improved,
            "ship": ship,
            "flags": flags,
        }

        if ship:
            print(f"  [7] SHIP {snap}: fitting full v2_qbox model + saving ...",
                  flush=True)
            in_sample_v1 = meta.get("in_sample", {})
            lgb_path, meta_path = fit_and_save_full(
                sub, feat_v2, cat_cols, hyperparams, snap, in_sample_v1,
            )
            print(f"    saved {lgb_path.name}", flush=True)
            print(f"    saved {meta_path.name}", flush=True)
            snap_res["saved_model"] = str(lgb_path)
            snap_res["saved_meta"] = str(meta_path)
        else:
            print(f"  REVERT {snap}: gate failed", flush=True)

        per_snap[snap] = snap_res

    elapsed = time.time() - t0
    result = {
        "iter": "iter63_inplay_qbox_efficiency",
        "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "random_seed": RANDOM_SEED,
        "n_folds": N_FOLDS,
        "coverage_min_gate": COVERAGE_MIN,
        "new_features": NEW_FEATS,
        "snapshots": per_snap,
        "elapsed_s": float(elapsed),
    }
    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nSaved results -> {OUT_JSON}", flush=True)

    # final summary table
    print("\n=== FINAL ===", flush=True)
    print(f"{'Snap':<7} {'v1 Brier':<10} {'v2 Brier':<10} {'Delta':<10} "
          f"{'Folds':<7} {'Ship':<6} Flags", flush=True)
    for snap in SNAPSHOTS:
        r = per_snap[snap]
        print(
            f"{snap:<7} {r['v1_mean_brier']:<10.4f} {r['v2_mean_brier']:<10.4f} "
            f"{r['mean_brier_delta']:<+10.4f} "
            f"{r['folds_improved']}/4    "
            f"{str(r['ship']):<6} {','.join(r['flags']) if r['flags'] else '-'}",
            flush=True,
        )
    print(f"Elapsed: {elapsed:.1f}s", flush=True)


if __name__ == "__main__":
    main()
