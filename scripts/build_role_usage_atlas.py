"""
Build Role / Usage-Efficiency Atlas from per-game advanced stats.
Activates dormant data/player_adv_stats.parquet.

Outputs:
  data/intelligence/role_usage_atlas.parquet   -- player-game rolling priors + role tier
  data/intelligence/role_usage_summary.parquet -- per-player aggregates + role

All priors are LEAK-FREE: shift(1).expanding().mean() -- only uses data
from games BEFORE the current game_date.
"""
import pandas as pd
import numpy as np
import os

# =========================================================
# 0. Load
# =========================================================
print("=== Loading player_adv_stats.parquet ===")
df = pd.read_parquet("data/player_adv_stats.parquet")
df["game_date"] = pd.to_datetime(df["game_date"])
df = df.sort_values(["player_id", "game_date"]).reset_index(drop=True)
print(f"Loaded: {df.shape[0]} rows, {df['player_id'].nunique()} players")

# =========================================================
# 1. Leak-free rolling priors
# =========================================================
print("\n=== Building leak-free rolling priors ===")

PRIOR_COLS = {
    "usagepercentage": "usage_prior",
    "trueshootingpercentage": "ts_prior",
    "assistpercentage": "ast_pct_prior",
    "reboundpercentage": "reb_pct_prior",
    "defensiverating": "def_rating_prior",
    "offensiverating": "off_rating_prior",
    "pie": "pie_prior",
    "minutes": "minutes_prior",
    "netrating": "net_rating_prior",
    "effectivefieldgoalpercentage": "efg_prior",
    "assisttoturnover": "ast_tov_prior",
    "turnoverratio": "tov_ratio_prior",
    "possessions": "possessions_prior",
}

prior_dfs = []

for pid, grp in df.groupby("player_id"):
    grp = grp.sort_values("game_date").copy()
    n = len(grp)
    row_priors = {
        "player_id": grp["player_id"].values,
        "game_id": grp["game_id"].values,
        "game_date": grp["game_date"].values,
        "games_played_prior": np.arange(n),
    }

    for src_col, dst_col in PRIOR_COLS.items():
        vals = grp[src_col].values.astype(float)
        priors = np.full(n, np.nan)
        for i in range(1, n):
            priors[i] = np.nanmean(vals[:i])
        row_priors[dst_col] = priors

    prior_dfs.append(pd.DataFrame(row_priors))

print("Concatenating per-player priors...")
atlas = pd.concat(prior_dfs, ignore_index=True)
print(f"Atlas shape: {atlas.shape}")

# =========================================================
# 2. Role tier classification from final (most-informed) priors
# =========================================================
print("\n=== Computing role thresholds ===")

MIN_GAMES = 15
player_last = atlas.groupby("player_id").last().reset_index()
player_games = df.groupby("player_id").size().reset_index(name="total_games")
player_last = player_last.merge(player_games, on="player_id")
qualified = player_last[player_last["total_games"] >= MIN_GAMES].copy()
print(f"Qualified players (>= {MIN_GAMES} games): {len(qualified)}")

# Thresholds from distribution of qualified players
u_p75 = qualified["usage_prior"].quantile(0.75)
u_p50 = qualified["usage_prior"].quantile(0.50)
u_p30 = qualified["usage_prior"].quantile(0.30)
m_p35 = qualified["minutes_prior"].quantile(0.35)
m_p60 = qualified["minutes_prior"].quantile(0.60)

print(f"Usage thresholds: P30={u_p30:.4f}, P50={u_p50:.4f}, P75={u_p75:.4f}")
print(f"Minutes thresholds: P35={m_p35:.1f}, P60={m_p60:.1f}")


def assign_role(row):
    u = row["usage_prior"]
    m = row["minutes_prior"]
    if pd.isna(u) or pd.isna(m):
        return "UNKNOWN"
    if u >= u_p75:
        return "PRIMARY_OPTION"
    elif u >= u_p50:
        return "SECONDARY"
    elif u >= u_p30 and m >= m_p35:
        return "ROLE_PLAYER"
    else:
        return "BENCH"


qualified["role_tier"] = qualified.apply(assign_role, axis=1)

print("\nRole tier counts:")
print(qualified["role_tier"].value_counts())

# =========================================================
# 3. Merge role into atlas and persist
# =========================================================
print("\n=== Merging role tiers into atlas ===")
role_map = qualified.set_index("player_id")["role_tier"]
atlas["role_tier"] = atlas["player_id"].map(role_map).fillna("INSUFFICIENT_DATA")

os.makedirs("data/intelligence", exist_ok=True)

atlas_out = atlas[[
    "player_id", "game_id", "game_date", "games_played_prior",
    "usage_prior", "ts_prior", "ast_pct_prior", "reb_pct_prior",
    "def_rating_prior", "off_rating_prior", "net_rating_prior",
    "pie_prior", "efg_prior", "ast_tov_prior", "tov_ratio_prior",
    "possessions_prior", "minutes_prior", "role_tier",
]]
atlas_out.to_parquet("data/intelligence/role_usage_atlas.parquet", index=False)
print(f"Saved role_usage_atlas.parquet: {atlas_out.shape}")

summary_rename = {
    "usage_prior": "usage_prior_final",
    "ts_prior": "ts_prior_final",
    "ast_pct_prior": "ast_pct_prior_final",
    "reb_pct_prior": "reb_pct_prior_final",
    "def_rating_prior": "def_rating_prior_final",
    "off_rating_prior": "off_rating_prior_final",
    "net_rating_prior": "net_rating_prior_final",
    "pie_prior": "pie_prior_final",
    "efg_prior": "efg_prior_final",
    "ast_tov_prior": "ast_tov_prior_final",
    "minutes_prior": "minutes_prior_final",
}
summary_cols = ["player_id", "total_games"] + list(summary_rename.keys()) + ["role_tier"]
summary = qualified[summary_cols].rename(columns=summary_rename)
summary.to_parquet("data/intelligence/role_usage_summary.parquet", index=False)
print(f"Saved role_usage_summary.parquet: {summary.shape}")

# =========================================================
# 4. Face validation
# =========================================================
print("\n=== Face validation ===")
try:
    from nba_api.stats.static import players as nba_players
    all_players = nba_players.get_players()
    id_to_name = {p["id"]: p["full_name"] for p in all_players}
    has_names = True
    print(f"Loaded {len(id_to_name)} player names from nba_api")
except Exception as e:
    print(f"nba_api unavailable: {e}")
    has_names = False

top_usage = summary.nlargest(10, "usage_prior_final")[[
    "player_id", "usage_prior_final", "ts_prior_final", "pie_prior_final", "role_tier"
]].copy()
top_pie = summary.nlargest(10, "pie_prior_final")[[
    "player_id", "usage_prior_final", "ts_prior_final", "pie_prior_final", "role_tier"
]].copy()

if has_names:
    top_usage["name"] = top_usage["player_id"].map(id_to_name)
    top_pie["name"] = top_pie["player_id"].map(id_to_name)

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)
print("\nTOP 10 BY USAGE_PRIOR_FINAL:")
print(top_usage.to_string(index=False))
print("\nTOP 10 BY PIE_PRIOR_FINAL:")
print(top_pie.to_string(index=False))

print("\nRole tier distribution (qualified players):")
tier_counts = qualified["role_tier"].value_counts()
for tier, cnt in tier_counts.items():
    pct = 100.0 * cnt / len(qualified)
    avg_u = qualified[qualified["role_tier"] == tier]["usage_prior"].mean()
    avg_m = qualified[qualified["role_tier"] == tier]["minutes_prior"].mean()
    print(f"  {tier}: n={cnt} ({pct:.1f}%) | avg_usage={avg_u:.4f} | avg_min={avg_m:.1f}")

print(f"\nThresholds (derived from qualified-player distribution):")
print(f"  PRIMARY_OPTION : usage_prior >= {u_p75:.4f}  (P75)")
print(f"  SECONDARY      : usage_prior in [{u_p50:.4f}, {u_p75:.4f})  (P50-P75)")
print(f"  ROLE_PLAYER    : usage_prior in [{u_p30:.4f}, {u_p50:.4f}) AND minutes_prior >= {m_p35:.1f}  (P30-P50 + min >= P35)")
print(f"  BENCH          : usage_prior < {u_p30:.4f} OR minutes_prior < {m_p35:.1f}")

print("\n=== BUILD COMPLETE ===")
