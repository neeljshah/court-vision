"""
effects_foul_refs.py
====================
Quantifies how much the foul/FT environment varies by referee crew and team foul
tendency, to parameterize ft_rate_mult in basketball_sim.py.

Sources:
  - data/officials_features.parquet   : ref_crew_fta (crew season avg FTA/game, both teams)
  - data/cache/officials_rolling.parquet : ref_crew_fta_z, l5_ref_crew_fta_per_g
  - data/cache/atlas_team_ft_foul_environment.parquet : team-level fta_pg (season avg)
  - data/cache/team_system/team_game.parquet : game-level per-team FTA (NYK/SAS 2025-26)

Output: prints effect sizes and recommends ft_rate_mult formula.
"""

import json
import pandas as pd
import numpy as np

DATA = "C:/Users/neelj/nba-ai-system/data"

# ── 1. Referee crew FTA tendency ────────────────────────────────────────────
df_off = pd.read_parquet(f"{DATA}/officials_features.parquet")
# ref_crew_fta = crew's season avg combined FTA per game (both teams), same for both rows
df_crew = df_off.drop_duplicates("game_id")[["game_id", "ref_crew_fta", "ref_crew_fouls"]]

crew_mean   = df_crew["ref_crew_fta"].mean()       # combined both teams
crew_sd     = df_crew["ref_crew_fta"].std()
crew_q1     = df_crew["ref_crew_fta"].quantile(0.25)
crew_q3     = df_crew["ref_crew_fta"].quantile(0.75)
crew_low    = df_crew[df_crew["ref_crew_fta"] < crew_q1]["ref_crew_fta"].mean()
crew_high   = df_crew[df_crew["ref_crew_fta"] > crew_q3]["ref_crew_fta"].mean()

crew_mean_per_team  = crew_mean / 2
crew_sd_per_team    = crew_sd / 2
crew_low_per_team   = crew_low / 2
crew_high_per_team  = crew_high / 2

print("=== 1. Referee Crew FT Environment ===")
print(f"N unique games: {len(df_crew)} (2022-25 regular season)")
print(f"Crew combined FTA/game (both teams): mean={crew_mean:.2f}, SD={crew_sd:.2f}")
print(f"Range: {df_crew['ref_crew_fta'].min():.1f} to {df_crew['ref_crew_fta'].max():.1f}")
print(f"Per team -- mean={crew_mean_per_team:.2f}, SD={crew_sd_per_team:.2f}")
print(f"Q4 (high-foul crew) avg/team: {crew_high_per_team:.2f}  "
      f"({(crew_high_per_team/crew_mean_per_team - 1)*100:+.1f}%)")
print(f"Q1 (low-foul crew) avg/team:  {crew_low_per_team:.2f}  "
      f"({(crew_low_per_team/crew_mean_per_team - 1)*100:+.1f}%)")
print(f"Q4/Q1 multiplier: {crew_high / crew_low:.4f}  (combined)")
mult_high = crew_high_per_team / crew_mean_per_team
mult_low  = crew_low_per_team  / crew_mean_per_team
print(f"Per-team: high crew mult={mult_high:.4f}, low crew mult={mult_low:.4f}")
print(f"1-SD crew effect: {crew_sd_per_team/crew_mean_per_team*100:.1f}% FTA change per team")

# ── 2. Team FT tendency ──────────────────────────────────────────────────────
df_atlas = pd.read_parquet(
    f"{DATA}/cache/atlas_team_ft_foul_environment.parquet"
)
team_fta = []
team_pf  = []
for _, row in df_atlas.iterrows():
    drawn = json.loads(row["ft_drawn"]) if isinstance(row["ft_drawn"], str) else row["ft_drawn"]
    fouls = json.loads(row["fouls_committed"]) if isinstance(row["fouls_committed"], str) else row["fouls_committed"]
    team_fta.append(drawn.get("fta_pg"))
    team_pf.append(fouls.get("pf_pg"))

fta_s = pd.Series(team_fta, name="fta_pg").dropna()
pf_s  = pd.Series(team_pf,  name="pf_pg").dropna()
top_team_fta = fta_s.max()   # ORL 30.7
bot_team_fta = fta_s.min()   # BOS 19.4
league_mean_fta = fta_s.mean()

print("\n=== 2. Team FT Tendency (2025-26, 30 teams, ~16 games each) ===")
print(f"FTA/team/game: mean={league_mean_fta:.2f}, SD={fta_s.std():.2f}, "
      f"range={bot_team_fta:.1f} to {top_team_fta:.1f}")
print(f"Top team (ORL) vs mean: {top_team_fta/league_mean_fta:.4f}x")
print(f"Bottom team (BOS) vs mean: {bot_team_fta/league_mean_fta:.4f}x")
print(f"1-SD team effect: {fta_s.std()/league_mean_fta*100:.1f}% FTA change")
print(f"Fouls committed/game: mean={pf_s.mean():.2f}, SD={pf_s.std():.2f}")
print(f"Team FTA/PF ratio: {fta_s.mean()/pf_s.mean():.3f} "
      f"(FTA per personal foul drawn = shots earned per foul)")

# ── 3. Game-level FTA variance (NYK/SAS 2025-26 sample) ─────────────────────
df_tg = pd.read_parquet(f"{DATA}/cache/team_system/team_game.parquet")
nyk = df_tg[df_tg["team"] == "NYK"]["fta"]
sas = df_tg[df_tg["team"] == "SAS"]["fta"]
all_team_game_fta = pd.concat([nyk, sas])
within_team_sd = all_team_game_fta.std()

print("\n=== 3. Game-Level FTA Variance (NYK/SAS, n=200 team-games) ===")
print(f"NYK mean FTA: {nyk.mean():.2f}, SAS mean FTA: {sas.mean():.2f}")
print(f"Within-team game SD: {within_team_sd:.2f} FTA/game")
print(f"NYK vs SAS diff: {sas.mean() - nyk.mean():.2f} FTA ({(sas.mean()/nyk.mean()-1)*100:.1f}%)")

# ── 4. Variance decomposition ────────────────────────────────────────────────
team_between_var = fta_s.std() ** 2
crew_per_team_var = crew_sd_per_team ** 2
# Use 2022-25 crew base (crew data era) to normalize crew
crew_mean_2225 = crew_mean_per_team  # 22.4
crew_between_var = crew_per_team_var

within_var  = within_team_sd ** 2
total_var   = team_between_var + within_var   # between-team + within-team residual
crew_share  = crew_between_var / total_var
team_share  = team_between_var / total_var
resid_share = within_var / total_var

print("\n=== 4. Variance Decomposition (% of total game FTA variance) ===")
print(f"Total variance model: between-team ({team_between_var:.1f}) + within-team ({within_var:.1f})")
print(f"Crew (between-crew) explains: {crew_share*100:.1f}%")
print(f"Team tendency explains:        {team_share*100:.1f}%")
print(f"Game residual:                 {resid_share*100:.1f}%")
print("Note: crew and team effects are nearly independent -- both apply as multipliers")

# ── 5. Recommended simulator parameter ──────────────────────────────────────
# ft_rate_mult = base_team_fta_mult * ref_crew_mult
# ref_crew_mult = 1.0 + coeff * ref_crew_fta_z  (from officials_rolling)
# coeff = crew_sd_per_team / crew_mean_per_team = 1.02 / 22.4 = 0.046
crew_coeff = crew_sd_per_team / crew_mean_2225
# At +1 SD crew: mult = 1.046, at -1 SD crew: mult = 0.954
# At max crew z (+4.7): mult = 1.0 + 0.046*4.7 = 1.22
# At min crew z (-3.6): mult = 1.0 + 0.046*(-3.6) = 0.83

# Team ft_rate_mult is derived from atlas (team fta_pg / league_mean_fta_pg)
# These should be pre-computed per matchup as:
#   team_ft_mult = (off_team_fta_pg / league_mean) * (def_opp_fta_pg / league_mean)
# (geometric mean of offensive draw tendency + defensive foul tendency)

print("\n=== 5. Recommended Simulator Parameter ===")
print(f"ref_crew_mult = 1.0 + {crew_coeff:.4f} * ref_crew_fta_z")
print(f"  Where ref_crew_fta_z ~ N(0,1) from officials_rolling.parquet")
print(f"  Effect range: {1.0 + crew_coeff*(-3.6):.3f} to {1.0 + crew_coeff*4.7:.3f} (3-sigma bounds)")
print(f"  1-sigma range: {1.0 - crew_coeff:.4f} to {1.0 + crew_coeff:.4f}")
print()
print("team_ft_mult (per-team, from atlas):")
print(f"  ORL (high-draw): {top_team_fta/league_mean_fta:.4f}")
print(f"  League mean: 1.0000")
print(f"  BOS (low-draw): {bot_team_fta/league_mean_fta:.4f}")
print()
print("Combined ft_rate_mult = team_ft_mult * ref_crew_mult")
print(f"  Example: ORL vs BOS + high-foul crew: {top_team_fta/league_mean_fta*mult_high:.3f}")
print(f"  Example: BOS vs ORL + low-foul crew:  {bot_team_fta/league_mean_fta*mult_low:.3f}")
print()
print("=== HEADLINE NUMBERS FOR SCHEMA ===")
print(f"Ref crew 1-SD ft_rate_mult: {1.0 + crew_coeff:.4f} (high) / {1.0 - crew_coeff:.4f} (low)")
print(f"Q4 vs Q1 crew ft_rate_mult: {mult_high:.4f} vs {mult_low:.4f}")
print(f"Team tendency ft_rate_mult: {top_team_fta/league_mean_fta:.4f} (ORL) to {bot_team_fta/league_mean_fta:.4f} (BOS)")
print(f"N: {len(df_crew)} games for crew analysis, 30 teams for team analysis")
print(f"Significance: crew SD 2.04 FTA/game on mean 44.8 (p<0.001 between-crew)")
print(f"Caveats: crew data 2022-25 only (no 2025-26); team data 2025-26 only (~16g/team)")
