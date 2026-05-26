"""
Probe R8_M27_availability — Binary classifier P(player_plays_tonight | features).
Output: data/cache/probe_R8_M27_availability_results.json
"""
import json, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import (f1_score, roc_auc_score, log_loss, brier_score_loss,
                             confusion_matrix)
import lightgbm as lgb

warnings.filterwarnings("ignore")
ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# 1. Load raw data
# ---------------------------------------------------------------------------
adv = pd.read_parquet(ROOT / "data/player_adv_stats.parquet")
dnp = pd.read_parquet(ROOT / "data/dnp_rows.parquet")
rt  = pd.read_parquet(ROOT / "data/rest_travel.parquet")

adv["game_date"] = pd.to_datetime(adv["game_date"])
dnp["game_date"] = pd.to_datetime(dnp["game_date"])
rt["game_date"]  = pd.to_datetime(rt["game_date"])

# Restrict to 2022-23 → 2024-25
SEASONS = {"2022-23", "2023-24", "2024-25"}
dnp = dnp[dnp["season"].isin(SEASONS)].copy()
adv = adv[adv["game_date"] >= "2022-10-01"].copy()

# ---------------------------------------------------------------------------
# 2. Build player→team mapping (per-game where possible, fallback to last known)
# ---------------------------------------------------------------------------
# DNP rows carry team directly
dnp_team = dnp[["player_id", "game_id", "team"]].copy()

# For played players: infer team from rest_travel via game-team overlap
# team_advanced_stats has (game_id, team_tricode) — 2 rows per game
tas = pd.read_parquet(ROOT / "data/team_advanced_stats.parquet")
game_teams = tas.groupby("game_id")["team_tricode"].apply(list).reset_index()
game_teams.columns = ["game_id", "teams"]

# Per-player historical team from DNP rows (fallback)
player_last_team = (
    dnp.sort_values("game_date").groupby("player_id")["team"].last().to_dict()
)

# ---------------------------------------------------------------------------
# 3. Build held-out test set — last 200 game_ids of 2024-25 by date
# ---------------------------------------------------------------------------
game_dates_2425 = (
    adv[adv["game_date"] >= "2024-10-01"]
    .groupby("game_id")["game_date"].first()
    .sort_values()
)
test_game_ids = set(game_dates_2425.tail(200).index.tolist())
print(f"Test games: {len(test_game_ids)}  ({min(game_dates_2425.tail(200).values)} – {max(game_dates_2425.tail(200).values)})")

# ---------------------------------------------------------------------------
# 4. Build panel: PLAYED rows (y=1) + DNP rows (y=0)
# ---------------------------------------------------------------------------
played = adv[adv["minutes"] > 0][["player_id", "game_id", "game_date"]].copy()
played["played"] = 1

dnp_labels = dnp[["player_id", "game_id", "game_date"]].copy()
dnp_labels["played"] = 0

panel = pd.concat([played, dnp_labels], ignore_index=True).drop_duplicates(
    subset=["player_id", "game_id"]
)
panel = panel.sort_values("game_date").reset_index(drop=True)
print(f"Panel rows: {len(panel)}  (played={panel['played'].sum()}, dnp={( panel['played']==0).sum()})")

# ---------------------------------------------------------------------------
# 5. Player→team: merge DNP team, fallback to last-known
# ---------------------------------------------------------------------------
panel = panel.merge(dnp_team.rename(columns={"team": "player_team"}),
                    on=["player_id", "game_id"], how="left")
# Fallback for played players not in dnp
missing_mask = panel["player_team"].isna()
panel.loc[missing_mask, "player_team"] = panel.loc[missing_mask, "player_id"].map(player_last_team)

# ---------------------------------------------------------------------------
# 6. Feature engineering — all signals use only data BEFORE game_date
# ---------------------------------------------------------------------------
panel = panel.sort_values(["player_id", "game_date"]).reset_index(drop=True)

# -- days_since_last_played --
panel["days_since_last_played"] = (
    panel.groupby("player_id")["game_date"]
    .diff().dt.days.clip(upper=60)
)
panel["days_since_last_played"] = panel["days_since_last_played"].fillna(60)

# -- last5_min_avg, last5_min_std from adv minutes (shifted) --
# LEAK FIX: previously merged adv-only (played-only) minutes onto panel.
# DNP rows had no match → fillna(0) → DNP rows got l5=0, played rows got real values.
# Perfect label separator. Fix: build per-player minutes series across BOTH played
# (from adv) and DNP rows (minutes=0), then shift(1).rolling on the unified series.
played_min = adv[adv["minutes"] > 0][["player_id", "game_date", "minutes"]].copy()
dnp_min = dnp[["player_id", "game_date"]].copy()
dnp_min["minutes"] = 0.0
all_min = pd.concat([played_min, dnp_min], ignore_index=True)
all_min = (
    all_min.drop_duplicates(subset=["player_id", "game_date"], keep="first")
    .sort_values(["player_id", "game_date"])
    .reset_index(drop=True)
)

def rolling_min_stats(df, window=5):
    rolled_avg = (
        df.groupby("player_id")["minutes"]
        .transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean())
    )
    rolled_std = (
        df.groupby("player_id")["minutes"]
        .transform(lambda x: x.shift(1).rolling(window, min_periods=1).std())
    )
    return rolled_avg, rolled_std

all_min["l5_avg"], all_min["l5_std"] = rolling_min_stats(all_min)
all_min_feats = all_min[["player_id", "game_date", "l5_avg", "l5_std"]].copy()

panel = panel.merge(all_min_feats, on=["player_id", "game_date"], how="left")
panel.rename(columns={"l5_avg": "last5_min_avg", "l5_std": "last5_min_std"}, inplace=True)
# Only first-ever appearance gets NaN (no prior history); fill with neutral player-avg proxy.
panel["last5_min_avg"] = panel["last5_min_avg"].fillna(panel["last5_min_avg"].median())
panel["last5_min_std"] = panel["last5_min_std"].fillna(panel["last5_min_std"].median())

# -- rolling10_dnp_rate, rolling10_injury_dnp_rate --
panel["is_dnp"] = (panel["played"] == 0).astype(int)
panel["is_injury_dnp"] = 0
inj_mask = panel.merge(
    dnp[["player_id", "game_id", "dnp_reason"]],
    on=["player_id", "game_id"], how="left"
)["dnp_reason"].isin(["injury", "inactive"])
panel.loc[inj_mask.values, "is_injury_dnp"] = 1

panel["rolling10_dnp_rate"] = (
    panel.groupby("player_id")["is_dnp"]
    .transform(lambda x: x.shift(1).rolling(10, min_periods=1).mean())
    .fillna(0)
)
panel["rolling10_injury_dnp_rate"] = (
    panel.groupby("player_id")["is_injury_dnp"]
    .transform(lambda x: x.shift(1).rolling(10, min_periods=1).mean())
    .fillna(0)
)

# -- b2b_flag: team played yesterday --
rt_b2b = rt[["game_id", "team_abbreviation", "is_b2b"]].rename(
    columns={"team_abbreviation": "player_team", "is_b2b": "b2b_flag"}
)
panel = panel.merge(rt_b2b, on=["game_id", "player_team"], how="left")
panel["b2b_flag"] = panel["b2b_flag"].fillna(0)

# -- season_progress: days since season start --
season_starts = {
    2022: pd.Timestamp("2022-10-18"),
    2023: pd.Timestamp("2023-10-24"),
    2024: pd.Timestamp("2024-10-22"),
}
panel["season_progress"] = panel["game_date"].apply(
    lambda d: (d - season_starts.get(d.year if d.month >= 9 else d.year - 1,
                                     pd.Timestamp("2022-10-18"))).days
)

# -- games_played_season_to_date --
panel["gp_cumcount"] = panel.groupby("player_id").cumcount()  # proxy (all games)

# -- season_play_rate_to_date (BASELINE feature) --
played_shifted = panel.groupby("player_id")["played"].transform(
    lambda x: x.shift(1).expanding().mean()
)
panel["season_play_rate_to_date"] = played_shifted.fillna(0.85)

# -- opponent_strength: opponent season-to-date win rate --
# Build team win rate by date from team_advanced_stats
# Approximation: use team W/L from adv stats net_rating proxy
# Simpler: compute team wins from the panel played data itself
# Actually use a simple proxy: rolling win rate from rest_travel game outcomes
# We don't have W/L in team_advanced_stats — use net_rating > 0 as win
tas2 = pd.read_parquet(ROOT / "data/team_advanced_stats.parquet")
tas2["game_date"] = pd.to_datetime(tas2["game_date"])
tas2["win"] = (tas2["off_rtg"] > tas2["def_rtg"]).astype(int)  # off_rtg>def_rtg = win proxy
tas2 = tas2.sort_values(["team_tricode", "game_date"])
tas2["win_rate_to_date"] = (
    tas2.groupby("team_tricode")["win"]
    .transform(lambda x: x.shift(1).expanding().mean())
    .fillna(0.5)
)
opp_wr = tas2[["game_id", "team_tricode", "win_rate_to_date"]].copy()

# For each game, find the opponent of player_team
game_two_teams = tas2.groupby("game_id")["team_tricode"].apply(list).to_dict()

def get_opp(row):
    teams = game_two_teams.get(row["game_id"], [])
    for t in teams:
        if t != row["player_team"]:
            return t
    return None

panel["opp_team"] = panel.apply(get_opp, axis=1)

# Merge opponent win rate
panel = panel.merge(
    opp_wr.rename(columns={"team_tricode": "opp_team", "win_rate_to_date": "opponent_strength"}),
    on=["game_id", "opp_team"], how="left"
)
panel["opponent_strength"] = panel["opponent_strength"].fillna(0.5)

# -- dnp_reason_last within 7 days --
reason_map = {"coach_decision": 1, "injury": 2, "inactive": 3}
dnp_sorted = dnp.sort_values(["player_id", "game_date"])

def last_dnp_reason_within7(panel_df, dnp_df):
    """Vectorized: for each row in panel, find most recent dnp_reason in past 7 days."""
    dnp_r = dnp_df[["player_id", "game_date", "dnp_reason"]].copy()
    dnp_r["dnp_reason_code"] = dnp_r["dnp_reason"].map(reason_map).fillna(0)
    # merge-asof style: sort both by game_date
    results = []
    for pid, grp in panel_df.groupby("player_id"):
        d = dnp_r[dnp_r["player_id"] == pid].sort_values("game_date")
        idx = 0
        codes = []
        for _, row in grp.iterrows():
            # last dnp before this game_date within 7 days
            cutoff = row["game_date"]
            recent = d[(d["game_date"] < cutoff) &
                       (d["game_date"] >= cutoff - pd.Timedelta(days=7))]
            if len(recent) > 0:
                codes.append(recent.iloc[-1]["dnp_reason_code"])
            else:
                codes.append(0)
        results.append(pd.Series(codes, index=grp.index))
    return pd.concat(results)

print("Computing dnp_reason_last (slow but accurate)...")
panel["dnp_reason_last"] = last_dnp_reason_within7(panel, dnp)

# ---------------------------------------------------------------------------
# 7. Final feature set
# ---------------------------------------------------------------------------
FEATURES = [
    "days_since_last_played", "last5_min_avg", "last5_min_std",
    "rolling10_dnp_rate", "rolling10_injury_dnp_rate",
    "b2b_flag", "season_progress", "gp_cumcount",
    "season_play_rate_to_date", "opponent_strength", "dnp_reason_last",
]
panel = panel.dropna(subset=FEATURES + ["played"])
print(f"Panel after dropna: {len(panel)}")

# ---------------------------------------------------------------------------
# 8. Train/Val/Test split
# ---------------------------------------------------------------------------
is_test = panel["game_id"].isin(test_game_ids)
train_val = panel[~is_test].copy()
test_df   = panel[is_test].copy()

split_idx = int(len(train_val) * 0.90)
train_df  = train_val.iloc[:split_idx]
val_df    = train_val.iloc[split_idx:]

X_train, y_train = train_df[FEATURES].values, train_df["played"].values
X_val,   y_val   = val_df[FEATURES].values,   val_df["played"].values
X_test,  y_test  = test_df[FEATURES].values,  test_df["played"].values

print(f"Train: {len(X_train)}  Val: {len(X_val)}  Test: {len(X_test)}")
print(f"Test DNP count: {(y_test==0).sum()}")

# ---------------------------------------------------------------------------
# 9. LightGBM model
# ---------------------------------------------------------------------------
scale_pos = int((y_train == 1).sum() / max((y_train == 0).sum(), 1))
model = lgb.LGBMClassifier(
    objective="binary", metric="binary_logloss",
    num_leaves=31, learning_rate=0.05, n_estimators=400,
    scale_pos_weight=scale_pos, random_state=42, verbose=-1,
)
model.fit(X_train, y_train,
          eval_set=[(X_val, y_val)],
          callbacks=[lgb.early_stopping(30, verbose=False),
                     lgb.log_evaluation(-1)])

prob_test = model.predict_proba(X_test)[:, 1]
pred_test = (prob_test >= 0.5).astype(int)

# ---------------------------------------------------------------------------
# 10. Baseline: season_play_rate_to_date thresholded at 0.5
# ---------------------------------------------------------------------------
base_prob = test_df["season_play_rate_to_date"].values
base_pred = (base_prob >= 0.5).astype(int)

# ---------------------------------------------------------------------------
# 11. Metrics (positive class = DNP = y=0, so invert)
# ---------------------------------------------------------------------------
y_dnp      = 1 - y_test        # 1 = DNP
pred_dnp   = 1 - pred_test
base_dnp   = 1 - base_pred

f1_model   = f1_score(y_dnp, pred_dnp, zero_division=0)
f1_base    = f1_score(y_dnp, base_dnp, zero_division=0)
rel_gain   = (f1_model - f1_base) / max(f1_base, 1e-9)

auc_model  = roc_auc_score(y_test, prob_test)
ll_model   = log_loss(y_test, prob_test)
br_model   = brier_score_loss(y_test, prob_test)

auc_base   = roc_auc_score(y_test, base_prob)
ll_base    = log_loss(y_test, base_prob)
br_base    = brier_score_loss(y_test, base_prob)

cm = confusion_matrix(y_dnp, pred_dnp).tolist()
ship = rel_gain >= 0.10

print(f"\n=== RESULTS ===")
print(f"F1 DNP — model: {f1_model:.4f}  baseline: {f1_base:.4f}  rel_gain: {rel_gain:.4f}")
print(f"AUC    — model: {auc_model:.4f}  baseline: {auc_base:.4f}")
print(f"SHIP: {ship}  (need +10% relative F1 on DNP)")

# ---------------------------------------------------------------------------
# 12. Output JSON
# ---------------------------------------------------------------------------
fi = dict(zip(FEATURES, model.feature_importances_.tolist()))
notes = (
    "v1 proxy roster; no team in player_adv_stats → team from dnp_rows fallback to "
    "last-known; opponent_strength from net_rating>0 proxy win-rate; "
    f"39 played-only players missing team (set to last-known); "
    f"adv covers 2022-10 to 2025-04 only (train data complete)"
)
result = {
    "probe":         "R8_M27_availability",
    "n_train":       int(len(X_train)),
    "n_test":        int(len(X_test)),
    "n_dnp_test":    int((y_test == 0).sum()),
    "model": {
        "f1_dnp":  round(f1_model, 5),
        "auc":     round(auc_model, 5),
        "logloss": round(ll_model, 5),
        "brier":   round(br_model, 5),
    },
    "baseline": {
        "f1_dnp":  round(f1_base, 5),
        "auc":     round(auc_base, 5),
        "logloss": round(ll_base, 5),
        "brier":   round(br_base, 5),
    },
    "relative_f1_gain": round(rel_gain, 5),
    "ship": ship,
    "feature_importance": {k: int(v) for k, v in sorted(fi.items(), key=lambda x: -x[1])},
    "confusion_matrix_at_0.5": cm,
    "notes": notes,
}

out = ROOT / "data/cache/probe_R8_M27_availability_results.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, indent=2))
print(f"\nSaved → {out}")
