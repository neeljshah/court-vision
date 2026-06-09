"""
INT-16: CV-Volatility-Aware Kelly Confidence Intervals
=======================================================
For each player with sufficient CV history, derive Kelly-multiplier recommendations
by combining INT-4 anomaly/CV volatility with per-game stat output volatility.

Output files:
  data/intelligence/per_player_confidence.parquet
  data/intelligence/confidence_curves.json
  vault/Intelligence/Confidence_Atlas.md
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
INTEL = DATA / "intelligence"
VAULT = ROOT / "vault" / "Intelligence"
INTEL.mkdir(parents=True, exist_ok=True)
VAULT.mkdir(parents=True, exist_ok=True)

# ── Step 1: Load INT-4 volatility data ────────────────────────────────────────
print("[INT-16] Loading INT-4 anomaly_log.parquet ...")
anomaly = pd.read_parquet(INTEL / "anomaly_log.parquet")
print(f"  anomaly_log: {anomaly.shape[0]:,} rows, {anomaly['player_id'].nunique()} players")

volatility = (
    anomaly.groupby(["player_id", "player_name"])["max_abs_z"]
    .agg(["mean", "std", "count"])
    .rename(columns={
        "mean":  "cv_volatility_mean",
        "std":   "cv_volatility_std",
        "count": "n_cv_games",
    })
    .reset_index()
)
# Fill NaN std (only 1 game) with 0
volatility["cv_volatility_std"] = volatility["cv_volatility_std"].fillna(0.0)
print(f"  Volatility table: {len(volatility)} players")
print(f"  cv_volatility_mean p25/p50/p75: "
      f"{volatility['cv_volatility_mean'].quantile(0.25):.2f} / "
      f"{volatility['cv_volatility_mean'].quantile(0.50):.2f} / "
      f"{volatility['cv_volatility_mean'].quantile(0.75):.2f}")

# ── Step 2: Load stat output history from quarter_stats ───────────────────────
print("\n[INT-16] Loading player_quarter_stats.parquet ...")
qs = pd.read_parquet(DATA / "player_quarter_stats.parquet")
print(f"  quarter_stats: {len(qs):,} rows")

# Aggregate quarters to per-game totals
by_game = (
    qs.groupby(["player_id", "game_id"])
    .agg(
        pts=("pts",  "sum"),
        reb=("reb",  "sum"),
        ast=("ast",  "sum"),
        fg3m=("fg3m","sum"),
        stl=("stl",  "sum"),
        blk=("blk",  "sum"),
        tov=("tov",  "sum"),
    )
    .reset_index()
)
print(f"  Per-game totals: {len(by_game):,} rows, {by_game['player_id'].nunique()} players")

# Per-player stat summary
stat_stats = (
    by_game.groupby("player_id")
    .agg(
        pts_mean=("pts",  "mean"), pts_std=("pts",  "std"),
        reb_mean=("reb",  "mean"), reb_std=("reb",  "std"),
        ast_mean=("ast",  "mean"), ast_std=("ast",  "std"),
        fg3m_mean=("fg3m","mean"), fg3m_std=("fg3m","std"),
        stl_mean=("stl",  "mean"), stl_std=("stl",  "std"),
        blk_mean=("blk",  "mean"), blk_std=("blk",  "std"),
        tov_mean=("tov",  "mean"), tov_std=("tov",  "std"),
        n_games_stat=("pts", "count"),
    )
    .reset_index()
)
# Fill NaN std (0-game edge cases) with 0
for stat in ["pts","reb","ast","fg3m","stl","blk","tov"]:
    stat_stats[f"{stat}_std"] = stat_stats[f"{stat}_std"].fillna(0.0)

print(f"  Stat stats table: {len(stat_stats)} players")

# ── Step 3: Join tables ────────────────────────────────────────────────────────
print("\n[INT-16] Joining volatility + stat tables ...")
joined = volatility.merge(stat_stats, on="player_id", how="inner")
print(f"  Joined: {len(joined)} players with both CV and stat history")

# ── Step 4: Apply data-sufficiency gate ────────────────────────────────────────
# Require: n_cv_games >= 3 AND n_games_stat >= 10
eligible = joined[(joined["n_cv_games"] >= 3) & (joined["n_games_stat"] >= 10)].copy()
print(f"  After gate (n_cv_games>=3, n_games_stat>=10): {len(eligible)} players")

# ── Step 5: Compute per-stat confidence multipliers ───────────────────────────
print("\n[INT-16] Computing confidence multipliers ...")

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

for stat in STATS:
    mean_col = f"{stat}_mean"
    std_col  = f"{stat}_std"
    cv_col   = f"{stat}_cv"
    mult_col = f"{stat}_confidence_mult"

    # Coefficient of variation: std / max(mean, 1.0)  →  ~0–1 range
    eligible[cv_col] = eligible[std_col] / eligible[mean_col].clip(lower=1.0)

    # Uncertainty = blend of stat CV and normalised CV volatility
    # cv_volatility_mean: observed range ~0.6–16.4, normalise by /10 to get ~0–1
    uncertainty = 0.5 * eligible[cv_col] + 0.5 * (eligible["cv_volatility_mean"] / 10.0)

    # Confidence multiplier: 1.5 - uncertainty, clipped to [0.25, 1.5]
    eligible[mult_col] = np.clip(1.5 - uncertainty, 0.25, 1.5)

# Primary multiplier = average across PTS / REB / AST (the 3 most-bet props)
eligible["overall_confidence_mult"] = eligible[
    ["pts_confidence_mult", "reb_confidence_mult", "ast_confidence_mult"]
].mean(axis=1)

# ── Step 6: Segment players ────────────────────────────────────────────────────
# Tight: cv_volatility_mean < 5 AND pts_cv < 0.25 → confidence-bet
# Loose: cv_volatility_mean > 10 OR pts_cv > 0.5 → reduce Kelly
tight_mask = (eligible["cv_volatility_mean"] < 5) & (eligible["pts_cv"] < 0.25)
loose_mask = (eligible["cv_volatility_mean"] > 10) | (eligible["pts_cv"] > 0.5)
eligible["segment"] = "medium"
eligible.loc[tight_mask, "segment"] = "tight"
eligible.loc[loose_mask, "segment"] = "loose"

tight_players = eligible[eligible["segment"] == "tight"].sort_values("overall_confidence_mult", ascending=False)
loose_players = eligible[eligible["segment"] == "loose"].sort_values("overall_confidence_mult", ascending=True)
medium_players = eligible[eligible["segment"] == "medium"]

print(f"  Tight (high confidence): {len(tight_players)} players")
print(f"  Loose (low confidence):  {len(loose_players)} players")
print(f"  Medium:                  {len(medium_players)} players")

# ── Step 7: Save per_player_confidence.parquet ────────────────────────────────
print("\n[INT-16] Saving per_player_confidence.parquet ...")
output_cols = [
    "player_id", "player_name",
    "n_cv_games", "cv_volatility_mean", "cv_volatility_std",
    "n_games_stat",
    "pts_cv",  "pts_confidence_mult",
    "reb_cv",  "reb_confidence_mult",
    "ast_cv",  "ast_confidence_mult",
    "fg3m_cv", "fg3m_confidence_mult",
    "stl_cv",  "stl_confidence_mult",
    "blk_cv",  "blk_confidence_mult",
    "tov_cv",  "tov_confidence_mult",
    "overall_confidence_mult",
    "segment",
]
out_df = eligible[output_cols].reset_index(drop=True)
out_df.to_parquet(INTEL / "per_player_confidence.parquet", index=False)
print(f"  Saved {len(out_df)} rows -> data/intelligence/per_player_confidence.parquet")

# ── Step 8: Save confidence_curves.json ───────────────────────────────────────
print("\n[INT-16] Saving confidence_curves.json ...")

# Distribution of multipliers (for pts)
bins = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5]
labels = ["[0.25,0.5)", "[0.5,0.75)", "[0.75,1.0)", "[1.0,1.25)", "[1.25,1.5]"]
dist_counts = pd.cut(
    eligible["pts_confidence_mult"], bins=bins, labels=labels, include_lowest=True
).value_counts().sort_index()

mult_distribution = {label: int(cnt) for label, cnt in dist_counts.items()}

# Per-player card data
player_cards = []
for _, row in eligible.sort_values("n_games_stat", ascending=False).head(30).iterrows():
    card = {
        "player_id":            int(row["player_id"]),
        "player_name":          str(row["player_name"]),
        "n_cv_games":           int(row["n_cv_games"]),
        "n_stat_games":         int(row["n_games_stat"]),
        "cv_volatility_mean":   round(float(row["cv_volatility_mean"]), 3),
        "segment":              str(row["segment"]),
        "multipliers": {
            "pts":  round(float(row["pts_confidence_mult"]),  3),
            "reb":  round(float(row["reb_confidence_mult"]),  3),
            "ast":  round(float(row["ast_confidence_mult"]),  3),
            "fg3m": round(float(row["fg3m_confidence_mult"]), 3),
            "stl":  round(float(row["stl_confidence_mult"]),  3),
            "blk":  round(float(row["blk_confidence_mult"]),  3),
            "tov":  round(float(row["tov_confidence_mult"]),  3),
        },
        "stat_cv": {
            "pts":  round(float(row["pts_cv"]),  3),
            "reb":  round(float(row["reb_cv"]),  3),
            "ast":  round(float(row["ast_cv"]),  3),
        },
        "overall_confidence_mult": round(float(row["overall_confidence_mult"]), 3),
    }
    player_cards.append(card)

# Uncertainty sensitivity: how multiplier changes with uncertainty input
uncertainty_range = np.linspace(0.0, 1.25, 26)
sensitivity_curve = {
    "uncertainty_inputs": [round(float(u), 3) for u in uncertainty_range],
    "multiplier_outputs": [round(float(np.clip(1.5 - u, 0.25, 1.5)), 3) for u in uncertainty_range],
    "formula": "multiplier = clip(1.5 - (0.5 * stat_cv + 0.5 * cv_volatility_mean / 10.0), 0.25, 1.5)",
    "stat_cv_formula": "stat_std / max(stat_mean, 1.0)",
}

curves_payload = {
    "generated_at": pd.Timestamp.now().isoformat(),
    "n_eligible_players": int(len(eligible)),
    "gate": {"min_cv_games": 3, "min_stat_games": 10},
    "formula": sensitivity_curve["formula"],
    "sensitivity_curve": sensitivity_curve,
    "pts_multiplier_distribution": mult_distribution,
    "player_cards": player_cards,
    "segment_counts": {
        "tight":  int(len(tight_players)),
        "medium": int(len(medium_players)),
        "loose":  int(len(loose_players)),
    },
}

with open(INTEL / "confidence_curves.json", "w") as f:
    json.dump(curves_payload, f, indent=2)
print(f"  Saved -> data/intelligence/confidence_curves.json")

# ── Step 9: Build Confidence Atlas markdown ────────────────────────────────────
print("\n[INT-16] Writing Confidence_Atlas.md ...")

top25 = eligible.sort_values("overall_confidence_mult", ascending=False).head(25)
bot25 = eligible.sort_values("overall_confidence_mult", ascending=True).head(25)

# Distribution table string
dist_lines = ["| range | n_players |", "| --- | --- |"]
for label, cnt in dist_counts.items():
    dist_lines.append(f"| {label} | {cnt} |")

# Per-player card section (top 20 by n_games_stat)
top20_by_games = eligible.sort_values("n_games_stat", ascending=False).head(20)
card_lines = []
for _, row in top20_by_games.iterrows():
    vol_level = (
        "extreme" if row["cv_volatility_mean"] > 10 else
        "high"    if row["cv_volatility_mean"] > 7  else
        "moderate" if row["cv_volatility_mean"] > 4  else
        "low"
    )
    mult = row["pts_confidence_mult"]
    direction = f"bet {abs(mult-1)*100:.0f}% {'larger' if mult > 1 else 'smaller'}"
    card_lines.append(
        f"- **{row['player_name']}**: CV volatility={row['cv_volatility_mean']:.2f} "
        f"({vol_level}), pts_cv={row['pts_cv']:.2f}, "
        f"**pts_confidence_mult={mult:.2f}** ({direction})"
    )

# Top 25 table
def make_table(df, label):
    lines = [
        f"### {label}",
        "| player | cv_volatility | pts_cv | reb_cv | ast_cv | overall_mult |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for _, row in df.iterrows():
        lines.append(
            f"| {row['player_name']} "
            f"| {row['cv_volatility_mean']:.2f} "
            f"| {row['pts_cv']:.2f} "
            f"| {row['reb_cv']:.2f} "
            f"| {row['ast_cv']:.2f} "
            f"| **{row['overall_confidence_mult']:.2f}** |"
        )
    return "\n".join(lines)

top25_table = make_table(top25, "Top 25 most confident players (largest Kelly OK)")
bot25_table = make_table(bot25, "Bottom 25 least confident players (smallest Kelly)")

atlas_md = f"""# CV-Volatility-Aware Confidence Atlas

*Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}*
*INT-16 — Wires INT-4 anomaly volatility scores into Kelly bet-sizing decisions.*

---

## Methodology

Combines two independent uncertainty signals:

1. **CV Volatility Score** (from INT-4 `anomaly_log.parquet`): Each game's `max_abs_z` measures
   how anomalous the player's CV-derived movement/spacing features are vs their baseline. The
   player-level mean of this score captures how "noisy" their physical profile is — a proxy for
   whether their effort/role is predictable game-to-game.

2. **Stat Output Volatility** (`stat_cv = stat_std / max(stat_mean, 1.0)`): Coefficient of
   variation of raw box-score output per stat. High CV = unpredictable game-to-game output.

**Joint uncertainty formula:**
```
stat_cv         = stat_std / max(stat_mean, 1.0)
uncertainty     = 0.5 * stat_cv + 0.5 * (cv_volatility_mean / 10.0)
confidence_mult = clip(1.5 - uncertainty, 0.25, 1.5)
```

Multiplier range: `[0.25, 1.5]`
- > 1.0 → bet **larger** than baseline Kelly (stable, predictable player)
- < 1.0 → bet **smaller** (uncertain, volatile player)

**Data gate:** n_cv_games ≥ 3 AND n_stat_games ≥ 10
**Eligible players:** {len(eligible)}

---

## Per-Player Confidence Cards (top 20 by games played)

{chr(10).join(card_lines)}

---

{top25_table}

---

{bot25_table}

---

## Distribution of PTS confidence multipliers

{chr(10).join(dist_lines)}

---

## Segment Summary

| segment | criteria | n_players | implication |
| --- | --- | --- | --- |
| **tight** | cv_volatility < 5 AND pts_cv < 0.25 | {len(tight_players)} | High confidence — up-size Kelly |
| **medium** | neither tight nor loose | {len(medium_players)} | Baseline Kelly |
| **loose** | cv_volatility > 10 OR pts_cv > 0.5 | {len(loose_players)} | Low confidence — down-size Kelly |

### Tight players (confidence-bet candidates)
{chr(10).join(f"- {r['player_name']} (mult={r['overall_confidence_mult']:.2f}, cv_vol={r['cv_volatility_mean']:.2f}, pts_cv={r['pts_cv']:.2f})" for _,r in tight_players.iterrows())}

### Loose players (bet-down candidates)
{chr(10).join(f"- {r['player_name']} (mult={r['overall_confidence_mult']:.2f}, cv_vol={r['cv_volatility_mean']:.2f}, pts_cv={r['pts_cv']:.2f})" for _,r in loose_players.iterrows())}

---

## How to use in production

1. For each prop bet decision:
   - Look up player in `data/intelligence/per_player_confidence.parquet` by `player_id`
   - Multiply standard Kelly fraction by their `{{stat}}_confidence_mult` for that stat
   - Example: If Kelly says bet 3% of bankroll on Curry PTS, and `pts_confidence_mult=1.40`, bet 4.2%.
   - Example: If Kelly says bet 3% on Nembhard PTS, and `pts_confidence_mult=0.35`, bet 1.05%.

2. Stars like Curry get up-sized; volatile role players get down-sized.

3. This is **independent of edge magnitude** — it adjusts confidence in the edge, not the edge itself.

4. Can combine with segment filter: only auto-approve `tight` bets; require manual review for `loose`.

---

## Validation hooks (future work)

- Track CLV by `segment` bucket — do `tight` bets actually close better vs the line?
- Track CLV by `overall_confidence_mult` decile — should be monotonically positive
- Re-fit the 0.5/0.5 blend weights using logistic regression on historical bet outcomes when N>200
- Consider per-stat weighting (PTS vs REB vs AST have different variance regimes)
- Add opponent-adjusted stat_cv (home vs away, vs top-5 defense splits)

---

## Source data
- `data/intelligence/anomaly_log.parquet` — INT-4 per-game CV volatility (812 game-player rows)
- `data/player_quarter_stats.parquet` — per-quarter box scores, aggregated to per-game (20,587 game-player rows)

## Output files
- `data/intelligence/per_player_confidence.parquet` — {len(out_df)} players, all stat multipliers
- `data/intelligence/confidence_curves.json` — sensitivity curve + player cards
"""

atlas_path = VAULT / "Confidence_Atlas.md"
atlas_path.write_text(atlas_md, encoding="utf-8")
print(f"  Saved -> vault/Intelligence/Confidence_Atlas.md")

# ── Step 10: Final report ──────────────────────────────────────────────────────
print()
print("=" * 70)
print("## INT-16 CV-Volatility Confidence Atlas - Final Report")
print("=" * 70)

print(f"""
### Coverage
- Players with both CV volatility + stat history: {len(eligible)}
- Tight (high confidence — Kelly up-size): {len(tight_players)} players
- Loose (low confidence — Kelly down-size): {len(loose_players)} players
- Medium (baseline Kelly): {len(medium_players)} players

### Top 5 confidence (Kelly up-sized)
""")
for _, r in top25.head(5).iterrows():
    print(f"  {r['player_name']}: overall_mult={r['overall_confidence_mult']:.2f}, "
          f"cv_vol={r['cv_volatility_mean']:.2f}, pts_cv={r['pts_cv']:.2f}")

print(f"""
### Bottom 5 confidence (Kelly down-sized)
""")
for _, r in bot25.head(5).iterrows():
    print(f"  {r['player_name']}: overall_mult={r['overall_confidence_mult']:.2f}, "
          f"cv_vol={r['cv_volatility_mean']:.2f}, pts_cv={r['pts_cv']:.2f}")

print(f"""
### Most actionable findings
""")
# Identify specific (player, stat) strong recommendations
recommendations = []
for _, row in eligible.iterrows():
    for stat in ["pts", "reb", "ast"]:
        mult = row[f"{stat}_confidence_mult"]
        if mult >= 1.35:
            recommendations.append((row["player_name"], stat.upper(), mult, "up-size"))
        elif mult <= 0.40:
            recommendations.append((row["player_name"], stat.upper(), mult, "down-size"))

recommendations.sort(key=lambda x: abs(x[2] - 1.0), reverse=True)
for name, stat, mult, direction in recommendations[:6]:
    print(f"  {name} {stat}: mult={mult:.2f} -> {direction} Kelly by {abs(mult-1)*100:.0f}%")

print(f"""
### Multiplier distribution (PTS)
""")
for label, cnt in dist_counts.items():
    print(f"  {label}: {cnt} players")

print(f"""
### Files
  scripts/build_confidence_intervals.py
  vault/Intelligence/Confidence_Atlas.md
  data/intelligence/per_player_confidence.parquet
  data/intelligence/confidence_curves.json

### How user can use this
  - Per-bet Kelly modifier: kelly_fraction * player_stat_confidence_mult
  - Lookup: per_player_confidence.parquet[player_id][stat_confidence_mult]
  - Tighter sizing for volatile players (e.g., Andrew Nembhard 0.25-0.35x)
  - Bigger sizing for stable stars (e.g., Curry, Banchero, Porzingis ~1.4x)
  - Pre-game lookup before placing any prop bet

### Honest caveats
  - Multiplier formula (0.5/0.5 blend, /10 normalisation) is heuristic — needs
    ROI/CLV validation when sample grows beyond current 50 eligible players
  - Players with <3 CV games OR <10 stat games excluded (below data gate)
  - stat_cv assumes per-player games are approximately i.i.d. (matchup varies)
  - CV volatility denominator of 10 is empirical (observed max ~16, p75 ~6)
""")
