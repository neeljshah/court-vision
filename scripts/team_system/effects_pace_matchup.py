"""
effects_pace_matchup.py
-----------------------
Measures how two teams' season-average paces predict realized game pace.
Key question: is realized pace the simple average, or does one team dominate?

Data source: data/team_advanced_stats.parquet
  - per-game rows (2 per game, one per team), 2022-23 through 2024-25
  - 'pace' column = game-level realized pace (identical for both teams in same game)
  - We compute each team's rolling prior-game season pace avg as the "team tendency"

Methodology:
  1. For each team-game, compute rolling mean of pace for PRIOR games in the same season
     (excludes current game to avoid leakage).
  2. Pair the two teams' rolling season paces per game.
  3. Compute: avg_pace = (pace_A + pace_B) / 2, diff_pace = |faster - slower|
  4. Regress realized_pace ~ intercept + coef_fast * pace_faster + coef_slow * pace_slower
  5. Test: if coef_fast == coef_slow == 0.5, realized = simple average.
     If coef_fast > coef_slow, faster team "pulls" the game pace more.
  6. Also bin by pace_diff quintile and show realized vs predicted simple-avg.
"""

import pandas as pd
import numpy as np
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

def main():
    df = pd.read_parquet(REPO / "data/team_advanced_stats.parquet")
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(["team_tricode", "game_date"]).reset_index(drop=True)

    # Season label from game_id
    df["season"] = df["game_id"].str[3:5].astype(int) + 2000

    print(f"Total team-game rows: {len(df)}, unique games: {df['game_id'].nunique()}")
    print(f"Seasons: {sorted(df['season'].unique())}")
    print(f"Realized pace: mean={df['pace'].mean():.2f}, std={df['pace'].std():.2f}, "
          f"min={df['pace'].min():.1f}, max={df['pace'].max():.1f}\n")

    # --- Rolling season-average pace (prior games only) ---
    # For each (team, season), shift(1) then expanding mean
    df["prior_pace"] = (
        df.groupby(["team_tricode", "season"])["pace"]
        .transform(lambda s: s.shift(1).expanding().mean())
    )

    # Drop first game of each team-season (no prior data)
    df_valid = df.dropna(subset=["prior_pace"]).copy()
    print(f"After dropping first game per team-season: {len(df_valid)} rows")

    # --- Pair teams per game ---
    # Each game appears twice; merge on game_id for team A vs team B
    left = df_valid[["game_id", "game_date", "season", "team_tricode", "pace", "prior_pace"]].copy()
    left.columns = ["game_id", "game_date", "season", "team_A", "realized_pace", "prior_A"]

    right = df_valid[["game_id", "team_tricode", "prior_pace"]].copy()
    right.columns = ["game_id", "team_B", "prior_B"]

    paired = left.merge(right, on="game_id")
    # Remove self-pairs
    paired = paired[paired["team_A"] != paired["team_B"]].copy()
    # Deduplicate: keep only one row per game (A < B alphabetically)
    paired = paired[paired["team_A"] < paired["team_B"]].copy()

    print(f"Unique game pairs: {len(paired)}\n")

    # --- Key derived columns ---
    paired["avg_prior"] = (paired["prior_A"] + paired["prior_B"]) / 2.0
    paired["faster_prior"] = paired[["prior_A", "prior_B"]].max(axis=1)
    paired["slower_prior"] = paired[["prior_A", "prior_B"]].min(axis=1)
    paired["pace_diff"] = paired["faster_prior"] - paired["slower_prior"]

    # Residual: realized vs simple average of priors
    paired["residual_vs_avg"] = paired["realized_pace"] - paired["avg_prior"]

    # --- Summary stats ---
    print("=== Basic correlations ===")
    for col in ["avg_prior", "faster_prior", "slower_prior"]:
        r = paired["realized_pace"].corr(paired[col])
        print(f"  corr(realized_pace, {col}) = {r:.4f}")

    # --- OLS regression: realized ~ alpha + beta_fast * faster + beta_slow * slower ---
    # Use numpy lstsq
    X = np.column_stack([
        np.ones(len(paired)),
        paired["faster_prior"].values,
        paired["slower_prior"].values,
    ])
    y = paired["realized_pace"].values

    coefs, residuals, rank, sv = np.linalg.lstsq(X, y, rcond=None)
    alpha, beta_fast, beta_slow = coefs

    # Compute R^2
    y_hat = X @ coefs
    ss_res = np.sum((y - y_hat) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot

    # Bootstrap SE for coefficient confidence
    np.random.seed(42)
    n_boot = 2000
    boot_coefs = []
    n = len(X)
    for _ in range(n_boot):
        idx = np.random.randint(0, n, n)
        Xb, yb = X[idx], y[idx]
        c, *_ = np.linalg.lstsq(Xb, yb, rcond=None)
        boot_coefs.append(c)
    boot_coefs = np.array(boot_coefs)
    se_alpha = boot_coefs[:, 0].std()
    se_fast = boot_coefs[:, 1].std()
    se_slow = boot_coefs[:, 2].std()

    print("\n=== OLS: realized_pace ~ alpha + beta_fast*faster_prior + beta_slow*slower_prior ===")
    print(f"  alpha     = {alpha:.4f} (SE={se_alpha:.4f})")
    print(f"  beta_fast = {beta_fast:.4f} (SE={se_fast:.4f})")
    print(f"  beta_slow = {beta_slow:.4f} (SE={se_slow:.4f})")
    print(f"  R^2 = {r2:.4f}")
    print(f"  Note: if pure average, both betas should be 0.50 and alpha=0")

    # --- Simple model: realized ~ a + b * avg_prior ---
    X2 = np.column_stack([np.ones(len(paired)), paired["avg_prior"].values])
    c2, *_ = np.linalg.lstsq(X2, y, rcond=None)
    alpha2, beta_avg = c2
    y_hat2 = X2 @ c2
    r2_2 = 1 - np.sum((y - y_hat2)**2) / ss_tot

    print("\n=== OLS: realized_pace ~ alpha + beta * avg_prior ===")
    print(f"  alpha    = {alpha2:.4f}")
    print(f"  beta_avg = {beta_avg:.4f}")
    print(f"  R^2 = {r2_2:.4f}")

    # --- Binned analysis by pace_diff ---
    print("\n=== Realized vs avg_prior by pace_diff quintile ===")
    paired["diff_q"] = pd.qcut(paired["pace_diff"], q=5, labels=False)
    grouped = paired.groupby("diff_q").agg(
        n=("realized_pace", "size"),
        avg_diff=("pace_diff", "mean"),
        realized=("realized_pace", "mean"),
        avg_prior_mean=("avg_prior", "mean"),
        resid=("residual_vs_avg", "mean"),
        faster=("faster_prior", "mean"),
        slower=("slower_prior", "mean"),
    ).reset_index()
    for _, row in grouped.iterrows():
        print(f"  Q{int(row['diff_q'])+1}: n={row['n']}, pace_diff={row['avg_diff']:.2f}, "
              f"realized={row['realized']:.2f}, avg_prior={row['avg_prior_mean']:.2f}, "
              f"resid={row['resid']:+.3f}, "
              f"faster={row['faster']:.2f}, slower={row['slower']:.2f}")

    # --- Overall bias ---
    bias = paired["residual_vs_avg"].mean()
    std_resid = paired["residual_vs_avg"].std()
    n_games = len(paired)
    se_bias = std_resid / np.sqrt(n_games)
    print(f"\n=== Overall bias (realized - avg_prior) ===")
    print(f"  Mean residual = {bias:+.4f} poss/game (SE={se_bias:.4f}, n={n_games})")
    print(f"  Std of residuals = {std_resid:.4f}")

    # --- Headline: pace_mult for simulator ---
    print("\n=== KEY FINDING for basketball_sim pace_mult ===")
    print(f"  Baseline avg_prior (avg of two teams' season pace): {paired['avg_prior'].mean():.2f} poss")
    print(f"  Realized mean pace: {paired['realized_pace'].mean():.2f} poss")
    print(f"  beta_fast={beta_fast:.4f}, beta_slow={beta_slow:.4f} (sum={beta_fast+beta_slow:.4f})")
    print(f"  Ratio faster/slower influence: {beta_fast:.4f} vs {beta_slow:.4f}")

    # Compute the implied pace_mult for a high-pace vs low-pace matchup
    # E.g., one team at 104 (fast) vs one at 96 (slow): avg=100
    ex_fast, ex_slow = 104.0, 96.0
    ex_avg = (ex_fast + ex_slow) / 2
    ex_realized_model = alpha + beta_fast * ex_fast + beta_slow * ex_slow
    ex_realized_naive = ex_avg
    pace_mult_fast = ex_realized_model / ex_realized_naive
    print(f"\n  Example: fast=104, slow=96, avg=100")
    print(f"  Model predicts realized pace: {ex_realized_model:.2f}")
    print(f"  Simple avg predicts:          {ex_realized_naive:.2f}")
    print(f"  Implied pace_mult vs naive avg: {pace_mult_fast:.4f}")

    print("\n=== Simulation recommendation ===")
    print(f"  Use: realized_pace = {alpha:.2f} + {beta_fast:.4f}*pace_fast + {beta_slow:.4f}*pace_slow")
    print(f"  OR equivalently: avg_pace * {beta_avg:.4f} + {alpha2:.2f} (R^2={r2_2:.4f})")
    print(f"  pace_mult in sim: scale base possessions by (realized / league_avg)")
    print(f"  League avg pace in data: {paired['realized_pace'].mean():.2f}")


if __name__ == "__main__":
    main()
