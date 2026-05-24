"""Quick probe: do game-context features (pace_diff, net_rtg_diff, elo_diff,
own/opp net_rtg, is_home, total_pace) help prop_pergame PTS/REB/AST?

Reads game-context per (team, game_date) from cached season_games_*.json
files (already point-in-time after cycles 3+10 leak fixes) and re-builds
the prop dataset with these features appended. WF 4-fold comparison vs
the base dataset (no game-context).
"""
from __future__ import annotations

import glob
import json
import os
import sys
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    _BOX_COL, STATS, _LOG_TRANSFORM_STATS, _SQRT_HUBER_STATS,
    _MIN_PLAYED, _MLPSeedEnsemble,
    _num, _parse_date, _row_features, _opponent_from_matchup,
    build_opponent_defense, build_rest_travel, build_playtypes,
    build_bbref_advanced, build_contracts, feature_columns,
)
import xgboost as xgb
import lightgbm as lgb
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score


DEF_CTX = {
    "gc_own_pace": 99.0, "gc_opp_pace": 99.0,
    "gc_own_net_rtg": 0.0, "gc_opp_net_rtg": 0.0,
    "gc_elo_diff_own": 0.0, "gc_is_home": 0.5, "gc_total_pace": 99.0,
}
GC_KEYS = list(DEF_CTX.keys())


def build_ctx():
    ctx = {}
    for path in glob.glob(os.path.join(PROJECT_DIR, "data", "nba", "season_games_*.json")):
        d = json.load(open(path, encoding="utf-8"))
        rows = d["rows"] if isinstance(d, dict) else d
        for r in rows:
            gd = r.get("game_date", "")
            ht, at = r.get("home_team"), r.get("away_team")
            if not (gd and ht and at):
                continue
            hp = r.get("home_pace", 99.0); ap = r.get("away_pace", 99.0)
            total = (hp + ap) / 2
            ctx[(ht, gd)] = {
                "gc_own_pace": hp, "gc_opp_pace": ap,
                "gc_own_net_rtg": r.get("home_net_rtg", 0.0),
                "gc_opp_net_rtg": r.get("away_net_rtg", 0.0),
                "gc_elo_diff_own": r.get("elo_differential", 0.0),
                "gc_is_home": 1.0, "gc_total_pace": total,
            }
            ctx[(at, gd)] = {
                "gc_own_pace": ap, "gc_opp_pace": hp,
                "gc_own_net_rtg": r.get("away_net_rtg", 0.0),
                "gc_opp_net_rtg": r.get("home_net_rtg", 0.0),
                "gc_elo_diff_own": -r.get("elo_differential", 0.0),
                "gc_is_home": 0.0, "gc_total_pace": total,
            }
    return ctx


def build_dataset_with_ctx(ctx):
    """Mirrors build_pergame_dataset but appends GC_KEYS to each row."""
    base_cols = feature_columns()
    feature_cols = base_cols + GC_KEYS
    oppdef = build_opponent_defense(os.path.join(PROJECT_DIR, "data", "nba"))
    resttravel = build_rest_travel()
    playtypes = build_playtypes()
    bbref = build_bbref_advanced()
    contracts = build_contracts()

    rows_out = []
    for path in glob.glob(os.path.join(PROJECT_DIR, "data", "nba", "gamelog_*.json")):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list) or not games:
            continue
        parts = os.path.basename(path).split("_")
        try:
            file_player_id = int(parts[1])
            file_season = parts[-1].replace(".json", "")
        except Exception:
            continue
        dated = [(d, g) for g in games if (d := _parse_date(g.get("GAME_DATE"))) is not None]
        dated.sort(key=lambda x: x[0])
        prior = []
        for idx, (gdate, game) in enumerate(dated):
            played = _num(game.get("MIN")) >= _MIN_PLAYED
            if played:
                rest = 3.0
                if idx > 0:
                    rest = float(min(max((gdate - dated[idx-1][0]).days, 0), 10))
                raw_gap = 3.0
                if prior:
                    lp = _parse_date(prior[-1].get("GAME_DATE"))
                    if lp is not None:
                        raw_gap = float(max((gdate - lp).days, 0))
                matchup = str(game.get("MATCHUP", ""))
                is_home = 1 if " vs. " in matchup else 0
                team_abbrev = matchup.split()[0] if matchup.split() else ""
                feats = _row_features(prior, rest, is_home, len(prior),
                                      days_since_last_game=raw_gap)
                feats.update(oppdef.factors(_opponent_from_matchup(matchup), gdate))
                feats.update(resttravel.features(team_abbrev, gdate))
                feats.update(playtypes.features(file_player_id, file_season))
                feats.update(bbref.features(file_player_id, file_season))
                feats.update(contracts.features(file_player_id, file_season))
                gc = ctx.get((team_abbrev, gdate.date().isoformat()), DEF_CTX)
                for k in GC_KEYS:
                    feats[k] = gc.get(k, DEF_CTX[k])
                row = {c: feats.get(c, 0.0) for c in feature_cols}
                for stat in STATS:
                    row[f"target_{stat}"] = _num(game.get(_BOX_COL[stat]))
                row["date"] = gdate.isoformat()
                rows_out.append(row)
            if played:
                prior.append(game)
    return rows_out, feature_cols, base_cols


def train_one(stat, X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw):
    use_log = stat in _LOG_TRANSFORM_STATS
    use_sqrt = stat in _SQRT_HUBER_STATS
    if use_log:
        yt_tr, yt_val = np.log1p(y_tr), np.log1p(y_val)
        xgb_obj, lgb_obj = "reg:squarederror", "regression"
    elif use_sqrt:
        yt_tr, yt_val = np.sqrt(y_tr), np.sqrt(y_val)
        xgb_obj, lgb_obj = "reg:pseudohubererror", "huber"
    else:
        yt_tr, yt_val = y_tr, y_val
        xgb_obj, lgb_obj = "reg:squarederror", "regression"

    p = {
        "pts": dict(md=6, lr=0.025, mcw=20, rl=4.0, cs=0.9, ra=2.0, g=0.2, ne=800, ss=0.8),
        "reb": dict(md=3, lr=0.025, mcw=30, rl=4.0, cs=0.9, ra=0.5, g=0.3, ne=800, ss=0.7),
        "ast": dict(md=5, lr=0.025, mcw=20, rl=5.0, cs=0.8, ra=0.5, g=0.2, ne=800, ss=0.7),
    }[stat]
    xgb_m = xgb.XGBRegressor(
        n_estimators=p["ne"], max_depth=p["md"], learning_rate=p["lr"],
        subsample=p["ss"], colsample_bytree=p["cs"],
        min_child_weight=p["mcw"], reg_lambda=p["rl"], reg_alpha=p["ra"],
        gamma=p["g"], random_state=42, objective=xgb_obj,
        eval_metric="mae", early_stopping_rounds=40,
    ).fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw, verbose=False)
    lgb_m = lgb.LGBMRegressor(
        n_estimators=p["ne"], max_depth=p["md"], learning_rate=p["lr"],
        subsample=p["ss"], subsample_freq=1, colsample_bytree=p["cs"],
        min_child_samples=max(20, p["mcw"]*2), reg_lambda=p["rl"], reg_alpha=p["ra"],
        random_state=42, objective=lgb_obj, n_jobs=-1, verbosity=-1,
    ).fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw,
         callbacks=[lgb.early_stopping(40, verbose=False)])
    sc = StandardScaler()
    Xts, Xvs, Xhs = sc.fit_transform(X_tr), sc.transform(X_val), sc.transform(X_ho)
    mlp_m = _MLPSeedEnsemble().fit(Xts, yt_tr)

    def inv(v):
        if use_log:
            return np.clip(np.expm1(v), 0, None)
        if use_sqrt:
            return np.clip(v, 0, None) ** 2
        return v

    xv, lv, mv = inv(xgb_m.predict(X_val)), inv(lgb_m.predict(X_val)), inv(mlp_m.predict(Xvs))
    xh, lh, mh = inv(xgb_m.predict(X_ho)),  inv(lgb_m.predict(X_ho)),  inv(mlp_m.predict(Xhs))
    st = LinearRegression(positive=True, fit_intercept=False)
    st.fit(np.column_stack([xv, lv, mv]), y_val)
    w = st.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([1/3, 1/3, 1/3])
    blend = np.clip(w[0]*xh + w[1]*lh + w[2]*mh, 0.0, None)
    return mean_absolute_error(y_ho, blend), r2_score(y_ho, blend)


def main():
    ctx = build_ctx()
    print(f"ctx entries: {len(ctx)}", flush=True)
    rows, full_cols, base_cols = build_dataset_with_ctx(ctx)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    gc_cover = sum(1 for r in rows if r.get("gc_own_pace", 99.0) != 99.0)
    print(f"rows={n} base_cols={len(base_cols)} full_cols={len(full_cols)} "
          f"gc_cover={gc_cover} ({100*gc_cover/n:.1f}%)", flush=True)

    X_full = np.array([[r[c] for c in full_cols] for r in rows], dtype=float)
    base_idx = [full_cols.index(c) for c in base_cols]
    dates_all = [datetime.fromisoformat(r["date"]) for r in rows]
    fold_ends = [(i + 1) / 5 for i in range(4)]
    out = {s: {"d_mae": [], "d_r2": []} for s in ["pts", "reb", "ast"]}

    for fi, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        te_end = n if fi == 3 else int(n * fold_ends[fi+1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000:
            continue
        age = np.array([(max(dates_all[:tr_end]) - d).days / 365.0 for d in dates_all[:tr_end]])
        sw = np.exp(-0.5 * age)

        X_tr_full, X_val_full, X_ho_full = X_full[:tr_end], X_full[tr_end:va_end], X_full[va_end:te_end]
        X_tr_base = X_tr_full[:, base_idx]
        X_val_base = X_val_full[:, base_idx]
        X_ho_base  = X_ho_full[:, base_idx]
        for stat in ["pts", "reb", "ast"]:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            y_tr, y_val, y_ho = y[:tr_end], y[tr_end:va_end], y[va_end:te_end]
            b_mae, b_r2 = train_one(stat, X_tr_base, y_tr, X_val_base, y_val, X_ho_base, y_ho, sw)
            a_mae, a_r2 = train_one(stat, X_tr_full, y_tr, X_val_full, y_val, X_ho_full, y_ho, sw)
            out[stat]["d_mae"].append(a_mae - b_mae)
            out[stat]["d_r2"].append(a_r2 - b_r2)
            print(f"  fold {fi+1} {stat.upper()}: base mae={b_mae:.4f} r2={b_r2:.4f}  "
                  f"aug mae={a_mae:.4f} r2={a_r2:.4f}  "
                  f"d_mae={a_mae-b_mae:+.4f} d_r2={a_r2-b_r2:+.4f}", flush=True)

    print()
    for stat in ["pts", "reb", "ast"]:
        dm = out[stat]["d_mae"]; dr = out[stat]["d_r2"]
        if not dm:
            continue
        pf = " ".join(f"{x:+.4f}" for x in dm)
        print(f"  {stat.upper()} 4-fold d_mae={np.mean(dm):+.4f}+-{np.std(dm):.4f}  "
              f"d_r2={np.mean(dr):+.4f}+-{np.std(dr):.4f}  per-fold mae=[{pf}]")


if __name__ == "__main__":
    main()
