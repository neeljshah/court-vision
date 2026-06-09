"""INT-17: Archetype x Defensive Scheme Interaction Matrix

Joins INT-1 player archetypes with INT-12 defensive scheme classifications to
identify systematic matchup advantages/disadvantages by player TYPE x opponent
SCHEME.  Sportsbooks haven't priced this because they require joining two
CV-derived atlases that don't exist in standard data feeds.

Inputs
------
  data/intelligence/player_fingerprints.parquet  -- INT-1 archetypes
  data/intelligence/defensive_schemes.parquet    -- INT-12 scheme tags + 6-axis scores
  data/nba/gamelog_<player_id>_<season>.json     -- raw stat outcomes + MATCHUP field

Outputs
-------
  data/intelligence/archetype_scheme_interactions.parquet
  data/intelligence/archetype_scheme_advantages.json
  vault/Intelligence/Archetype_Scheme_Matrix.md
"""

import json
import os
import re
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path("C:/Users/neelj/nba-ai-system")
NBA_CACHE = ROOT / "data" / "nba"
INTEL_DIR = ROOT / "data" / "intelligence"
VAULT_INTEL = ROOT / "vault" / "Intelligence"

sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Step 1 — Load atlases
# ---------------------------------------------------------------------------

def load_atlases() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load INT-1 player fingerprints and INT-12 defensive schemes."""
    fingerprints = pd.read_parquet(INTEL_DIR / "player_fingerprints.parquet")
    # index = player_id (int64)
    print(f"  Fingerprints: {len(fingerprints)} players, "
          f"{fingerprints['archetype_name'].value_counts().to_dict()}")

    schemes = pd.read_parquet(INTEL_DIR / "defensive_schemes.parquet")
    print(f"  Schemes: {len(schemes)} teams, dominant_tags: "
          f"{schemes['dominant_tag'].value_counts().to_dict()}")

    return fingerprints, schemes


# ---------------------------------------------------------------------------
# Step 2 — Build a player_id → opp_team → season_avg lookup from gamelogs
# ---------------------------------------------------------------------------

def _parse_opp_from_matchup(matchup: str, player_team: str) -> str:
    """Extract opponent abbreviation from MATCHUP string.

    Formats observed:
      'SAS vs. TOR'  -> home game, opp = TOR
      'SAS @ LAL'    -> away game, opp = LAL
    """
    parts = re.split(r"\s+(?:vs\.|@)\s+", matchup)
    if len(parts) == 2:
        # parts[0] is player's team, parts[1] is opponent
        return parts[1].strip()
    return ""


def _season_from_filename(fpath: str) -> str:
    """Extract '2024-25' from 'gamelog_123456_2024-25.json'."""
    m = re.search(r"gamelog_\d+_(\d{4}-\d{2})\.json$", fpath)
    return m.group(1) if m else "unknown"


def build_game_rows(fingerprints: pd.DataFrame) -> pd.DataFrame:
    """Read all gamelog files for players present in fingerprints.

    Returns a DataFrame with columns:
      player_id, opp_team, season,
      pts, reb, ast, min
    """
    fp_ids = set(fingerprints.index.astype(int).tolist())
    gamelog_files = list(NBA_CACHE.glob("gamelog_*.json"))
    print(f"  Found {len(gamelog_files)} gamelog files; "
          f"filtering to {len(fp_ids)} fingerprinted players...")

    rows = []
    seasons_seen = ["2022-23", "2023-24", "2024-25", "2025-26"]

    for fpath in gamelog_files:
        fname = fpath.name
        m = re.search(r"gamelog_(\d+)_(\d{4}-\d{2})\.json$", fname)
        if not m:
            continue
        pid = int(m.group(1))
        season = m.group(2)
        if pid not in fp_ids:
            continue
        if season not in seasons_seen:
            continue

        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        if not isinstance(data, list) or not data:
            continue

        for game in data:
            matchup = game.get("MATCHUP", "")
            opp = _parse_opp_from_matchup(matchup, "")
            if not opp:
                continue
            # MIN can be float or missing
            min_played = game.get("MIN", 0) or 0
            if min_played < 5:
                continue  # skip DNP / garbage time < 5 min

            rows.append({
                "player_id": pid,
                "opp_team": opp,
                "season": season,
                "pts": float(game.get("PTS") or 0),
                "reb": float(game.get("REB") or 0),
                "ast": float(game.get("AST") or 0),
                "min": float(min_played),
            })

    df = pd.DataFrame(rows)
    print(f"  Game rows collected: {len(df)}")
    return df


# ---------------------------------------------------------------------------
# Step 3 — Compute per-player season baseline and per-game deviation
# ---------------------------------------------------------------------------

def add_baselines(game_rows: pd.DataFrame) -> pd.DataFrame:
    """Add season-level baseline (mean) and game-level deviation per player.

    Uses the FULL season mean as the baseline (conservative — all in-sample,
    but this is intelligence analysis not prediction, so the goal is to
    understand systematic patterns, not build a leak-free predictor).
    """
    base = (
        game_rows
        .groupby(["player_id", "season"])[["pts", "reb", "ast"]]
        .transform("mean")
        .rename(columns={"pts": "base_pts", "reb": "base_reb", "ast": "base_ast"})
    )
    df = pd.concat([game_rows, base], axis=1)
    df["dev_pts"] = df["pts"] - df["base_pts"]
    df["dev_reb"] = df["reb"] - df["base_reb"]
    df["dev_ast"] = df["ast"] - df["base_ast"]
    return df


# ---------------------------------------------------------------------------
# Step 4 — Join archetypes + scheme tags
# ---------------------------------------------------------------------------

def join_atlas(
    game_rows: pd.DataFrame,
    fingerprints: pd.DataFrame,
    schemes: pd.DataFrame,
) -> pd.DataFrame:
    """Attach player archetype and opponent scheme to every game row."""
    # Archetype lookup
    arch_map = fingerprints[["archetype_name"]].copy()
    arch_map.index.name = "player_id"
    df = game_rows.merge(arch_map, on="player_id", how="left")

    # Scheme lookup (opp_team -> dominant_tag)
    scheme_map = schemes.set_index("team")[["dominant_tag"] + [
        "drop_score", "paint_protection_score", "perimeter_denial_score",
        "pace_control_score", "iso_force_score", "closeout_score",
    ]].copy()
    df = df.merge(
        scheme_map.rename(columns={c: f"opp_{c}" for c in scheme_map.columns}),
        left_on="opp_team",
        right_index=True,
        how="left",
    )

    before = len(df)
    df = df.dropna(subset=["archetype_name", "opp_dominant_tag"])
    after = len(df)
    print(f"  Rows after join (dropped {before - after} missing archetype/scheme): {after}")
    return df


# ---------------------------------------------------------------------------
# Step 5 — Aggregate by (archetype, scheme) cell
# ---------------------------------------------------------------------------

def aggregate_cells(df: pd.DataFrame) -> pd.DataFrame:
    """Group by (player_archetype, opp_dominant_tag) and compute stats."""
    results = []
    for stat in ["pts", "reb", "ast"]:
        dev_col = f"dev_{stat}"
        grp = df.groupby(["archetype_name", "opp_dominant_tag"])[dev_col]
        agg = grp.agg(
            n_games="count",
            mean_dev="mean",
            std_dev="std",
        ).reset_index()
        # t-stat: mean / (std / sqrt(n))
        agg["t_stat"] = agg.apply(
            lambda r: (r["mean_dev"] / (r["std_dev"] / np.sqrt(r["n_games"])))
            if r["n_games"] > 1 and r["std_dev"] > 0 else 0.0,
            axis=1,
        )
        agg["p_value"] = agg.apply(
            lambda r: float(2 * stats.t.sf(abs(r["t_stat"]), df=r["n_games"] - 1))
            if r["n_games"] > 1 else 1.0,
            axis=1,
        )
        agg["stat"] = stat
        agg["significant"] = (agg["n_games"] >= 30) & (agg["t_stat"].abs() >= 2.0)
        results.append(agg)

    cells = pd.concat(results, ignore_index=True)
    cells.columns = [
        "archetype_name", "opp_scheme", "n_games",
        "mean_dev", "std_dev", "t_stat", "p_value", "stat", "significant",
    ]
    return cells


# ---------------------------------------------------------------------------
# Step 6 — Build advantages/disadvantages JSON
# ---------------------------------------------------------------------------

def build_advantages(cells: pd.DataFrame) -> Dict:
    """Extract statistically significant matchup advantages/disadvantages."""
    out = {}
    for stat in ["pts", "reb", "ast"]:
        sub = cells[(cells["stat"] == stat) & (cells["significant"])].copy()
        sub_sorted = sub.reindex(
            sub["t_stat"].abs().sort_values(ascending=False).index
        )

        advs = []
        disadvs = []
        for _, row in sub_sorted.iterrows():
            direction = "OVER bias" if row["mean_dev"] > 0 else "UNDER bias"
            entry = {
                "archetype": row["archetype_name"],
                "scheme": row["opp_scheme"],
                "n_games": int(row["n_games"]),
                "mean_dev": round(float(row["mean_dev"]), 3),
                "t_stat": round(float(row["t_stat"]), 2),
                "p_value": round(float(row["p_value"]), 4),
                "recommendation": f"{direction} when this matchup occurs",
            }
            if row["mean_dev"] > 0:
                advs.append(entry)
            else:
                disadvs.append(entry)

        out[stat] = {
            "advantages": advs,
            "disadvantages": disadvs,
        }
    return out


# ---------------------------------------------------------------------------
# Step 7 — Validate against basketball theory
# ---------------------------------------------------------------------------

def validate_theory(cells: pd.DataFrame) -> List[Dict]:
    """Check whether the matrix aligns with basketball intuition."""
    hypotheses = [
        {
            "description": "Paint bigs vs DROP COVERAGE should over-perform PTS (drop allows post-ups / paint touches)",
            "archetype_contains": "Post-Heavy",
            "scheme": "DROP COVERAGE",
            "stat": "pts",
            "expected_sign": +1,
        },
        {
            "description": "Perimeter shooters vs PERIMETER DENIAL should under-perform FG3M / PTS",
            "archetype_contains": "Perimeter Shooter",
            "scheme": "PERIMETER DENIAL",
            "stat": "pts",
            "expected_sign": -1,
        },
        {
            "description": "High-Motor Cutter vs PAINT-FIRST DEFENSE should under-perform (paint clogged)",
            "archetype_contains": "High-Motor Cutter",
            "scheme": "PAINT-FIRST DEFENSE",
            "stat": "pts",
            "expected_sign": -1,
        },
        {
            "description": "Ball-handlers / shooters vs SWITCH HEAVY should increase AST (switches create iso opportunities for kick-out passes)",
            "archetype_contains": "Perimeter Shooter",
            "scheme": "SWITCH HEAVY",
            "stat": "ast",
            "expected_sign": +1,
        },
        {
            "description": "Low-CV-Activity players: expect weak effects regardless of scheme",
            "archetype_contains": "Low-CV-Activity",
            "scheme": None,
            "stat": "pts",
            "expected_sign": 0,  # ~zero
        },
    ]

    results = []
    for hyp in hypotheses:
        mask = cells["archetype_name"].str.contains(hyp["archetype_contains"], na=False)
        mask &= (cells["stat"] == hyp["stat"])
        if hyp["scheme"]:
            mask &= (cells["opp_scheme"] == hyp["scheme"])

        subset = cells[mask]
        if subset.empty:
            results.append({**hyp, "status": "NO_DATA", "actual_mean_dev": None, "n_games": 0})
            continue

        row = subset.iloc[0]
        actual_sign = np.sign(row["mean_dev"]) if abs(row["mean_dev"]) > 0.05 else 0

        if hyp["expected_sign"] == 0:
            # Expect weak absolute effect
            validated = abs(row["mean_dev"]) < 0.5
            status = "VALIDATED (weak effect as expected)" if validated else "UNEXPECTED STRONG EFFECT"
        elif actual_sign == hyp["expected_sign"]:
            status = "VALIDATED"
        elif actual_sign == 0:
            status = "NEUTRAL (weak signal)"
        else:
            status = "CONTRADICTS THEORY"

        results.append({
            **hyp,
            "status": status,
            "actual_mean_dev": round(float(row["mean_dev"]), 3),
            "t_stat": round(float(row["t_stat"]), 2),
            "n_games": int(row["n_games"]),
        })

    return results


# ---------------------------------------------------------------------------
# Step 8 — Render pivot table for markdown
# ---------------------------------------------------------------------------

def pivot_table_md(cells: pd.DataFrame, stat: str) -> str:
    """Return markdown table of mean_dev per (archetype, scheme) cell."""
    sub = cells[cells["stat"] == stat].copy()
    archetypes = sorted(sub["archetype_name"].unique())
    schemes = sorted(sub["opp_scheme"].unique())

    # Header
    header = "| Archetype | " + " | ".join(schemes) + " |"
    sep = "|---|" + "|".join(["---"] * len(schemes)) + "|"
    lines = [header, sep]

    for arch in archetypes:
        row_vals = []
        for sch in schemes:
            match = sub[
                (sub["archetype_name"] == arch) & (sub["opp_scheme"] == sch)
            ]
            if match.empty:
                row_vals.append("—")
            else:
                r = match.iloc[0]
                val = f"{r['mean_dev']:+.1f}"
                if r["significant"]:
                    val += f" (t={r['t_stat']:+.1f})*"
                row_vals.append(val)
        # Truncate archetype name
        short_arch = arch.replace(" / ", "/").replace("Profile", "").strip()
        lines.append("| " + short_arch + " | " + " | ".join(row_vals) + " |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 9 — Write vault markdown atlas
# ---------------------------------------------------------------------------

def write_vault_atlas(
    cells: pd.DataFrame,
    advantages: Dict,
    validation: List[Dict],
    n_joined: int,
    n_total_game_rows: int,
) -> None:
    """Write INT-17 atlas to vault/Intelligence/Archetype_Scheme_Matrix.md."""

    n_cells_per_stat = 24  # 4 archetypes x 6 scheme tags (approximate)
    cells_sufficient = cells[cells["n_games"] >= 30]
    n_sufficient = len(cells_sufficient["archetype_name"].unique()) * len(
        cells_sufficient["opp_scheme"].unique()
    )  # rough
    cells_significant = cells[cells["significant"]]
    n_significant = len(cells_significant)

    val_pass = sum(1 for v in validation if "VALIDATED" in v.get("status", ""))
    val_total = len(validation)

    top5_adv = {
        stat: advantages.get(stat, {}).get("advantages", [])[:5]
        for stat in ["pts", "reb", "ast"]
    }
    top5_dis = {
        stat: advantages.get(stat, {}).get("disadvantages", [])[:5]
        for stat in ["pts", "reb", "ast"]
    }

    def fmt_top(items: List[Dict]) -> str:
        if not items:
            return "_No significant cells_\n"
        lines = []
        for i, it in enumerate(items, 1):
            lines.append(
                f"{i}. **{it['archetype']}** vs **{it['scheme']}**: "
                f"{it['mean_dev']:+.2f} avg over baseline, n={it['n_games']}, "
                f"t={it['t_stat']:+.2f}, p={it['p_value']:.4f} — "
                f"_{it['recommendation']}_"
            )
        return "\n".join(lines) + "\n"

    def fmt_val(items: List[Dict]) -> str:
        lines = []
        for v in items:
            status_icon = "VALIDATED" if "VALIDATED" in v["status"] else ("?" if "NEUTRAL" in v["status"] else "CONTRADICTS")
        # use plain text icons
        icons = {"VALIDATED": "✓", "?": "~", "CONTRADICTS": "✗", "NO_DATA": "—"}
        for v in items:
            if "VALIDATED" in v["status"]:
                icon = "PASS"
            elif "NEUTRAL" in v["status"] or "weak" in v["status"].lower():
                icon = "NEUTRAL"
            elif "NO_DATA" in v["status"]:
                icon = "NO DATA"
            else:
                icon = "FAIL"
            dev_str = f"actual_dev={v['actual_mean_dev']:+.3f}" if v.get("actual_mean_dev") is not None else "n/a"
            lines.append(
                f"- [{icon}] {v['description']}  \n"
                f"  n={v.get('n_games', 0)}, {dev_str}, t={v.get('t_stat', 'n/a')}"
            )
        return "\n".join(lines) + "\n"

    content = f"""# Archetype x Defensive Scheme Interaction Matrix

> INT-17 | Built: 2026-05-28

## Methodology

Joining INT-1 player archetypes (CV-derived) with INT-12 defensive scheme
classifications (CV-derived) to identify systematic matchup advantages.

For each player-game row: look up the player's archetype from the CV fingerprint
atlas, look up the opponent's dominant defensive scheme, then measure deviation
from the player's season mean.  Aggregate by (archetype, scheme) bucket.
Statistical significance gate: n >= 30 games AND |t| > 2.0.

**This is signal bookmakers haven't priced** because it requires joining two
CV-derived atlases that don't exist in standard sportsbook data pipelines.

## Coverage

- Players with CV fingerprints: {len(pd.read_parquet(INTEL_DIR / 'player_fingerprints.parquet'))}
- Game rows joined with both archetype + scheme: {n_joined:,} (of {n_total_game_rows:,} total)
- (archetype, scheme) cells with n >= 30: {len(cells[cells['n_games'] >= 30]):,}
- Statistically significant cells (|t| > 2, n >= 30): {n_significant}

---

## PTS Interaction Matrix

{pivot_table_md(cells, 'pts')}

_(* = statistically significant cell: n >= 30, |t| > 2)_

---

## REB Interaction Matrix

{pivot_table_md(cells, 'reb')}

---

## AST Interaction Matrix

{pivot_table_md(cells, 'ast')}

---

## Top Systematic PTS Advantages

{fmt_top(top5_adv['pts'])}

## Top Systematic PTS Disadvantages

{fmt_top(top5_dis['pts'])}

## Top Systematic REB Advantages

{fmt_top(top5_adv['reb'])}

## Top Systematic REB Disadvantages

{fmt_top(top5_dis['reb'])}

## Top Systematic AST Advantages

{fmt_top(top5_adv['ast'])}

## Top Systematic AST Disadvantages

{fmt_top(top5_dis['ast'])}

---

## Validation Against Basketball Theory

{fmt_val(validation)}
**{val_pass} of {val_total} intuitive matchups validated as expected.**

---

## How to Use

- **Pre-game prep**: check player_archetype x opp_dominant_scheme matrix for
  expected stat tilt before setting Kelly stake.
- **Most actionable**: cells with n >= 50 and |t| > 2.5 (strongest signal).
- **Apply as overlay**: combine with INT-16 per-player confidence multipliers
  to scale the deviation estimate.
- Bookmakers don't have either atlas (CV-derived archetypes or schemes), so
  this is unadjusted alpha as of 2026.

---

## Honest Caveats

- ~44% of players land in "Low-CV-Activity Profile" — their archetype is
  unreliable because the CV tracker saw too few frames for them.
- Scheme classification covers all 30 NBA teams but has known quality variance
  (teams with `confidence=low` in INT-12 are unreliable).
- Many (archetype, scheme) cells have small n (< 30) — excluded from
  significance claims but visible in the matrix as point estimates.
- Season-mean baseline is computed in-sample — this is intelligence analysis,
  not a leak-free prediction.  Don't wire directly into model features without
  a proper shifted baseline.
- Cross-season scale issues (BUG 9 from CV_Pipeline_Bug_Roadmap) may affect
  CV-derived archetype stability across seasons.

---

## Related

- [[Player_Atlas]] — INT-1 archetype definitions and coverage
- [[Defensive_Schemes]] — INT-12 scheme tags and 6-axis scores
- [[Matchup_Atlas]] — INT-3 per-player-opponent CV deviations
- [[CV_Pipeline_Bug_Roadmap]] — known CV data quality issues
"""

    outpath = VAULT_INTEL / "Archetype_Scheme_Matrix.md"
    outpath.write_text(content, encoding="utf-8")
    print(f"  Atlas written: {outpath}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== INT-17: Archetype x Scheme Interaction Matrix ===\n")

    # Step 1 — Load atlases
    print("[1] Loading INT-1 and INT-12 atlases...")
    fingerprints, schemes = load_atlases()

    # Step 2 — Build game rows from gamelogs
    print("\n[2] Building game rows from player gamelogs...")
    game_rows = build_game_rows(fingerprints)
    n_total_game_rows = len(game_rows)

    # Step 3 — Add baselines and deviations
    print("\n[3] Adding season baselines and per-game deviations...")
    game_rows = add_baselines(game_rows)

    # Step 4 — Join archetypes + schemes
    print("\n[4] Joining archetype and scheme labels...")
    joined = join_atlas(game_rows, fingerprints, schemes)
    n_joined = len(joined)

    # Step 5 — Aggregate cells
    print("\n[5] Aggregating (archetype, scheme) cells...")
    cells = aggregate_cells(joined)
    print(f"  Total cells: {len(cells)}")
    print(f"  Cells with n >= 30: {len(cells[cells['n_games'] >= 30])}")
    sig_cells = cells[cells["significant"]]
    print(f"  Significant cells (|t|>2, n>=30): {len(sig_cells)}")
    if len(sig_cells):
        print("\n  Significant cells preview:")
        cols_show = ["archetype_name", "opp_scheme", "stat", "n_games", "mean_dev", "t_stat", "p_value"]
        print(sig_cells[cols_show].sort_values("t_stat", key=abs, ascending=False).head(20).to_string(index=False))

    # Step 6 — Build advantages JSON
    print("\n[6] Building advantages/disadvantages dictionary...")
    advantages = build_advantages(cells)
    for stat in ["pts", "reb", "ast"]:
        advs = advantages[stat]["advantages"]
        diss = advantages[stat]["disadvantages"]
        print(f"  {stat}: {len(advs)} advantages, {len(diss)} disadvantages")

    # Step 7 — Validate against basketball theory
    print("\n[7] Validating against basketball intuition...")
    validation = validate_theory(cells)
    for v in validation:
        dev_str = f"dev={v['actual_mean_dev']:+.3f}" if v.get("actual_mean_dev") is not None else ""
        print(f"  [{v['status']}] {v['description'][:70]} | {dev_str}")

    # Save parquet
    print("\n[8] Saving outputs...")
    parquet_path = INTEL_DIR / "archetype_scheme_interactions.parquet"
    cells.to_parquet(parquet_path, index=False)
    print(f"  Parquet: {parquet_path}")

    # Save JSON
    json_path = INTEL_DIR / "archetype_scheme_advantages.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(advantages, f, indent=2, ensure_ascii=False)
    print(f"  JSON: {json_path}")

    # Write vault atlas
    write_vault_atlas(cells, advantages, validation, n_joined, n_total_game_rows)

    # ---------------------------------------------------------------------------
    # Final Report
    # ---------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("INT-17 Archetype x Scheme Interaction — Final Report")
    print("=" * 70)

    print(f"\nCoverage")
    print(f"  Rows joined with both archetype + scheme: {n_joined:,} (of {n_total_game_rows:,})")
    print(f"  (archetype, scheme) cells with n >= 30: {len(cells[cells['n_games'] >= 30])}")
    print(f"  Statistically significant cells (|t| > 2): {len(sig_cells)}")

    for stat in ["pts", "reb", "ast"]:
        print(f"\nTop 5 Systematic {stat.upper()} Advantages:")
        for it in advantages[stat]["advantages"][:5]:
            print(f"  {it['archetype'][:35]:35s} vs {it['scheme']:20s}  "
                  f"n={it['n_games']:3d}  dev={it['mean_dev']:+.2f}  t={it['t_stat']:+.2f}")
        print(f"\nTop 5 Systematic {stat.upper()} Disadvantages:")
        for it in advantages[stat]["disadvantages"][:5]:
            print(f"  {it['archetype'][:35]:35s} vs {it['scheme']:20s}  "
                  f"n={it['n_games']:3d}  dev={it['mean_dev']:+.2f}  t={it['t_stat']:+.2f}")

    val_pass = sum(1 for v in validation if "VALIDATED" in v.get("status", ""))
    print(f"\nValidation: {val_pass} of {len(validation)} intuitive matchups validated")

    print(f"\nFiles:")
    print(f"  scripts/build_archetype_scheme_matrix.py")
    print(f"  vault/Intelligence/Archetype_Scheme_Matrix.md")
    print(f"  data/intelligence/archetype_scheme_interactions.parquet")
    print(f"  data/intelligence/archetype_scheme_advantages.json")

    print(f"\nHow to use this:")
    print("  Pre-game prep: player_archetype x opp_dominant_scheme -> expected stat tilt")
    print("  This is signal BOOKMAKERS HAVEN'T PRICED (no CV archetypes/schemes in market data)")
    print("  Most actionable: n >= 50, |t| > 2.5 cells")

    print(f"\nHonest caveats:")
    print("  44% of players are Low-CV-Activity (unreliable archetype)")
    print("  Scheme confidence varies (low-confidence teams: BKN, PHX, TOR)")
    print("  Most (archetype, scheme) cells have n < 30 — limited sample")
    print("  Baseline = in-season mean (not leakage-free rolling) — analysis only, not features")


if __name__ == "__main__":
    os.chdir(str(ROOT))
    main()
