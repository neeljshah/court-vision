"""analyze_playstyle_corr_sameplayer.py

Measures per-ARCHETYPE same-player residual stat-pair correlations, split-half
stability, and delta vs the naive flat _SAME_PLAYER_RHO in parlay_engine.py.

Outputs:
  data/models/prop_corr_archetype_sameplayer.json   -- candidate archetype rho table
  docs/_audits/PLAYSTYLE_CORR_SAMEPLAYER.md         -- analysis report

Discipline:
  - Unit = ARCHETYPE (pooled), never per-player
  - Residual correlation: de-trend each player's stat by his pregame OOF prediction
    (pregame_oof_faithful.parquet); fall back to player mean if OOF not available.
  - Stability gate: split games into early/late halves by date; cell must have
    same sign AND |delta| <= 0.15 across halves.
  - Min-n gate: >= 30 players per archetype, >= 300 player-game observations per cell.
  - NO ROI/edge claims. Output is a more accurate joint model + honest delta-vs-naive.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from itertools import combinations

import numpy as np
import pandas as pd

# ─── Paths ─────────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parents[1]
CACHE = REPO / "data" / "cache"
MODELS = REPO / "data" / "models"
AUDITS = REPO / "docs" / "_audits"

GAMELOG_REG = CACHE / "cv_fix" / "leaguegamelog_regular_season.parquet"
GAMELOG_PLY = CACHE / "cv_fix" / "leaguegamelog_playoffs.parquet"
OOF_PATH    = CACHE / "pregame_oof_faithful.parquet"

ATLAS_UR    = CACHE / "atlas_player_usage_role.parquet"
ATLAS_PM    = CACHE / "atlas_player_playmaking_network.parquet"
ATLAS_PNR   = CACHE / "atlas_player_pick_and_roll_profile.parquet"
ATLAS_POST  = CACHE / "atlas_player_post_up_profile.parquet"
ATLAS_CS    = CACHE / "atlas_player_catch_shoot_vs_pullup.parquet"
ATLAS_REB   = CACHE / "atlas_player_rebounding_profile.parquet"
ATLAS_SC    = CACHE / "atlas_player_scoring_creation.parquet"
ATLAS_DEF   = CACHE / "atlas_player_defensive_profile.parquet"

OUT_JSON = MODELS / "prop_corr_archetype_sameplayer.json"
OUT_MD   = AUDITS / "PLAYSTYLE_CORR_SAMEPLAYER.md"
OUT_ARCH_MAP = MODELS / "player_archetype_sameplayer.json"


# Public alias so correlation_recal.py can call without re-running full analysis.
def build_archetype_assignments() -> pd.DataFrame:
    """Public alias for build_archetypes(). Returns [player_id, archetype] DataFrame."""
    return build_archetypes()

# ─── Naive flat rhos (from parlay_engine._SAME_PLAYER_RHO) ───────────────────
NAIVE_RHO = {
    ("pts", "ast"):  0.30,
    ("pts", "reb"):  0.40,
    ("pts", "fg3m"): 0.55,
    ("pts", "stl"):  0.20,
    ("pts", "blk"):  0.10,
    ("pts", "tov"):  0.35,
    ("reb", "blk"):  0.35,
    ("reb", "ast"):  0.15,
    ("ast", "tov"):  0.40,
    ("fg3m", "ast"): 0.20,
    ("stl", "blk"):  0.15,
}
# Normalise to sorted tuple keys
NAIVE_RHO = {tuple(sorted(k)): v for k, v in NAIVE_RHO.items()}

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
STAT_PAIRS = [tuple(sorted(p)) for p in combinations(STATS, 2)]

MIN_PLAYERS_PER_ARCH = 30
MIN_GAME_OBS_PER_CELL = 300  # player-game rows pooled across archetype

# ─── Helper: safe parse JSON field ───────────────────────────────────────────
def _parse_json(val):
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return {}
    if isinstance(val, dict):
        return val
    return {}


# ─── Step 1: Load and merge box stats ────────────────────────────────────────
def load_box() -> pd.DataFrame:
    reg = pd.read_parquet(GAMELOG_REG, columns=[
        "PLAYER_ID", "GAME_ID", "GAME_DATE", "MIN",
        "PTS", "REB", "AST", "FG3M", "STL", "BLK", "TOV"
    ])
    ply = pd.read_parquet(GAMELOG_PLY, columns=[
        "PLAYER_ID", "GAME_ID", "GAME_DATE", "MIN",
        "PTS", "REB", "AST", "FG3M", "STL", "BLK", "TOV"
    ])
    df = pd.concat([reg, ply], ignore_index=True)
    df.columns = df.columns.str.lower()
    df["game_date"] = pd.to_datetime(df["game_date"])
    # Keep only games with meaningful minutes (>= 5)
    df = df[df["min"] >= 5].copy()
    # Drop exact duplicates
    df = df.drop_duplicates(subset=["player_id", "game_id"])
    df = df.sort_values("game_date").reset_index(drop=True)
    print(f"[box] {len(df):,} player-game rows  |  "
          f"{df['player_id'].nunique()} players  |  "
          f"date range {df['game_date'].min().date()} – {df['game_date'].max().date()}")
    return df


# ─── Step 2: Load pregame OOF projections ────────────────────────────────────
def load_oof() -> pd.DataFrame:
    """
    pregame_oof_faithful has empty game_id; join on player_id + game_date instead.
    OOF covers 2023-11-10 → 2026-05-24; box is 2025-10-21 → 2026-04-12 (current season).
    Expect ~50% hit rate (overlap on regular season games).
    """
    oof = pd.read_parquet(OOF_PATH, columns=["player_id", "game_date", "stat", "oof_pred"])
    oof["game_date"] = pd.to_datetime(oof["game_date"])
    # Pivot to wide on player_id + game_date
    oof_wide = oof.pivot_table(
        index=["player_id", "game_date"], columns="stat", values="oof_pred", aggfunc="first"
    ).reset_index()
    oof_wide.columns.name = None
    stat_cols = [c for c in oof_wide.columns if c not in ("player_id", "game_date")]
    oof_wide.columns = ["player_id", "game_date"] + [f"oof_{s}" for s in stat_cols]
    print(f"[oof] {len(oof_wide):,} player-date OOF rows  "
          f"({oof_wide['game_date'].min().date()} – {oof_wide['game_date'].max().date()})")
    return oof_wide


# ─── Step 3: Compute residuals ───────────────────────────────────────────────
def build_residuals(box: pd.DataFrame, oof_wide: pd.DataFrame) -> pd.DataFrame:
    """
    For each player-game, residual = actual - oof_pred (pregame projection).
    If OOF not available for a player-game, residual = actual - player_mean_actual.
    OOF join is on player_id + game_date (game_id is empty in pregame_oof_faithful).
    """
    merged = box.merge(oof_wide, on=["player_id", "game_date"], how="left")
    for s in STATS:
        oof_col = f"oof_{s}"
        if oof_col not in merged.columns:
            merged[oof_col] = np.nan
        # Compute player mean as fallback
        player_mean = merged.groupby("player_id")[s].transform("mean")
        baseline = merged[oof_col].fillna(player_mean)
        merged[f"resid_{s}"] = merged[s] - baseline

    n_oof_covered = merged[["oof_pts"]].notna().sum().iloc[0]
    print(f"[residuals] OOF coverage: {n_oof_covered:,} / {len(merged):,} "
          f"({100*n_oof_covered/len(merged):.1f}%)  "
          f"| fallback to player-mean for remaining rows")
    return merged


# ─── Step 4: Build archetype assignments ─────────────────────────────────────
def build_archetypes() -> pd.DataFrame:
    """
    Returns DataFrame with columns: [player_id, archetype].

    Archetype rules (priority order; first match wins):
    -------------------------------------------------------
    1. HIGH_AST_PLAYMAKER
       ast_pct >= 0.22  AND  usage_rate >= 0.18
       => High AST% creators (PG-type playmakers)

    2. PNR_BALLHANDLER
       pnr_handler_pg >= 0.40  AND  usage_rate >= 0.18
       => Pick-and-roll primary ball-handlers

    3. ISO_SCORER
       iso_poss_pg >= 0.60  AND  usage_rate >= 0.20
       => Isolation-first high-usage scorers

    4. POST_UP_BIG
       post_up_pg >= 0.30  AND  total_reb_rate_mean >= 0.10
       => Post-up bigs with rebounding

    5. RIM_ROLL_BIG
       total_reb_rate_mean >= 0.12  AND  pts_paint_share >= 0.50
       AND  ast_pct <= 0.12
       => Rim-running roll men / paint bigs

    6. SPOT_UP_SHOOTER
       catch_shoot_3pa_per_g >= 1.5  AND  unassisted_share_3pm <= 0.35
       => Catch-and-shoot floor spacers

    7. THREE_AND_D_WING
       catch_shoot_3pa_per_g >= 0.80  AND  usage_rate <= 0.18
       AND  ast_pct <= 0.14
       => 3&D wings with limited creation role

    8. OTHER
       Everything else (backup guards, two-way players, etc.)
    """
    ur = pd.read_parquet(ATLAS_UR, columns=[
        "player_id", "usage_rate", "ast_pct", "pnr_handler_pg", "iso_poss_pg"
    ])
    pm = pd.read_parquet(ATLAS_PM, columns=["player_id", "passes_made", "ast_ratio"])
    post = pd.read_parquet(ATLAS_POST, columns=["player_id", "post_up_pg"])
    reb = pd.read_parquet(ATLAS_REB, columns=["player_id", "total_reb_rate_mean"])
    sc = pd.read_parquet(ATLAS_SC, columns=[
        "player_id", "unassisted_share_3pm", "pts_paint_share",
        "catch_shoot_3pa_per_g"
    ])

    # Base merge: start with usage_role (722 players) as spine
    base = ur.copy()
    base = base.merge(pm[["player_id", "ast_ratio"]], on="player_id", how="left")
    base = base.merge(post[["player_id", "post_up_pg"]], on="player_id", how="left")
    base = base.merge(reb[["player_id", "total_reb_rate_mean"]], on="player_id", how="left")
    base = base.merge(sc[["player_id", "unassisted_share_3pm",
                           "pts_paint_share", "catch_shoot_3pa_per_g"]],
                      on="player_id", how="left")

    # Fill missing with 0 (conservative)
    numeric_cols = ["usage_rate", "ast_pct", "pnr_handler_pg", "iso_poss_pg",
                    "post_up_pg", "total_reb_rate_mean",
                    "unassisted_share_3pm", "pts_paint_share", "catch_shoot_3pa_per_g"]
    for c in numeric_cols:
        if c not in base.columns:
            base[c] = 0.0
        base[c] = base[c].fillna(0.0)

    # Priority archetype assignment
    def assign(row):
        u = row["usage_rate"]
        ast = row["ast_pct"]
        pnr = row["pnr_handler_pg"]
        iso = row["iso_poss_pg"]
        post = row["post_up_pg"]
        reb_r = row["total_reb_rate_mean"]
        paint = row["pts_paint_share"]
        cs3pa = row["catch_shoot_3pa_per_g"]
        unast3 = row["unassisted_share_3pm"]

        if ast >= 0.22 and u >= 0.18:
            return "HIGH_AST_PLAYMAKER"
        if pnr >= 0.40 and u >= 0.18:
            return "PNR_BALLHANDLER"
        if iso >= 0.60 and u >= 0.20:
            return "ISO_SCORER"
        if post >= 0.30 and reb_r >= 0.10:
            return "POST_UP_BIG"
        if reb_r >= 0.12 and paint >= 0.50 and ast <= 0.12:
            return "RIM_ROLL_BIG"
        if cs3pa >= 1.5 and unast3 <= 0.35:
            return "SPOT_UP_SHOOTER"
        if cs3pa >= 0.80 and u <= 0.18 and ast <= 0.14:
            return "THREE_AND_D_WING"
        return "OTHER"

    base["archetype"] = base.apply(assign, axis=1)

    counts = base["archetype"].value_counts()
    print("[archetypes] n per archetype:")
    for arch, n in counts.items():
        print(f"  {arch:<22s}  {n:3d} players")
    return base[["player_id", "archetype"]]


# ─── Step 5: Residual correlation by archetype ───────────────────────────────
def pearson_r(x: np.ndarray, y: np.ndarray) -> float:
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 10:
        return np.nan
    xm = x[mask] - x[mask].mean()
    ym = y[mask] - y[mask].mean()
    denom = np.sqrt((xm**2).sum() * (ym**2).sum())
    if denom < 1e-12:
        return np.nan
    return float(np.dot(xm, ym) / denom)


def compute_archetype_corrs(
    resid_df: pd.DataFrame,
    arch_df: pd.DataFrame,
) -> list[dict]:
    """
    For each archetype × stat_pair:
      - Pool all player-game residuals from that archetype.
      - Split games by date median into early/late halves.
      - Compute residual Pearson r overall, r_early, r_late.
      - Stability: same sign AND |r_early - r_late| <= 0.15.
    """
    merged = resid_df.merge(arch_df, on="player_id", how="inner")
    print(f"[corr] Total player-game rows after arch join: {len(merged):,}")

    # Date split
    date_median = merged["game_date"].median()
    merged["half"] = np.where(merged["game_date"] <= date_median, "early", "late")

    records = []
    archetypes = sorted(merged["archetype"].unique())

    for arch in archetypes:
        sub = merged[merged["archetype"] == arch]
        n_players = sub["player_id"].nunique()
        n_games = len(sub)

        for pair in STAT_PAIRS:
            sa, sb = pair
            naive = NAIVE_RHO.get(pair, None)  # None if pair not in engine

            ra_col = f"resid_{sa}"
            rb_col = f"resid_{sb}"
            if ra_col not in sub.columns or rb_col not in sub.columns:
                continue

            x_all = sub[ra_col].values.astype(float)
            y_all = sub[rb_col].values.astype(float)

            valid_mask = np.isfinite(x_all) & np.isfinite(y_all)
            n_obs = valid_mask.sum()

            if n_players < MIN_PLAYERS_PER_ARCH or n_obs < MIN_GAME_OBS_PER_CELL:
                status = "small_n"
                r_all = r_early = r_late = np.nan
                stable = False
            else:
                r_all = pearson_r(x_all, y_all)
                early_mask = sub["half"] == "early"
                late_mask = sub["half"] == "late"
                r_early = pearson_r(
                    sub.loc[early_mask, ra_col].values.astype(float),
                    sub.loc[early_mask, rb_col].values.astype(float),
                )
                r_late = pearson_r(
                    sub.loc[late_mask, ra_col].values.astype(float),
                    sub.loc[late_mask, rb_col].values.astype(float),
                )
                # Stability: same sign (or both near zero <0.05) AND |delta| <= 0.15
                if np.isnan(r_early) or np.isnan(r_late):
                    stable = False
                else:
                    same_sign = (np.sign(r_early) == np.sign(r_late)) or (
                        abs(r_early) < 0.05 and abs(r_late) < 0.05
                    )
                    small_delta = abs(r_early - r_late) <= 0.15
                    stable = same_sign and small_delta
                status = "ok"

            delta_vs_naive = (
                round(float(r_all) - naive, 4)
                if naive is not None and not np.isnan(r_all)
                else None
            )
            material = (
                abs(delta_vs_naive) >= 0.10
                if delta_vs_naive is not None
                else False
            )
            survives = stable and material

            records.append({
                "archetype": arch,
                "stat_a": sa,
                "stat_b": sb,
                "pair": f"{sa}↔{sb}",
                "n_players": int(n_players),
                "n_obs": int(n_obs),
                "status": status,
                "r_all": round(float(r_all), 4) if not np.isnan(r_all) else None,
                "r_early": round(float(r_early), 4) if not np.isnan(r_early) else None,
                "r_late": round(float(r_late), 4) if not np.isnan(r_late) else None,
                "stable": stable,
                "naive_rho": naive,
                "delta_vs_naive": delta_vs_naive,
                "material": material,
                "survives_both_gates": survives,
            })

    return records


# ─── Step 6: Assemble outputs ─────────────────────────────────────────────────
def build_json_output(records: list[dict], arch_df: pd.DataFrame) -> dict:
    """
    Build candidate archetype-conditioned rho table.
    For cells that SURVIVE both gates, use r_all as the candidate rho.
    For cells that don't survive, fall back to naive flat rho.
    """
    archetypes = arch_df["archetype"].unique().tolist()
    output = {
        "description": (
            "Archetype-conditioned same-player residual correlation table. "
            "STABILITY-GATED: only cells with same sign + |delta_halves|<=0.15 AND "
            "|delta_vs_naive|>=0.10 are marked as refinements. "
            "No ROI/SGP price validation available -- model accuracy improvement only."
        ),
        "generated_at": pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "naive_flat_rho": {f"{a}_{b}": v for (a, b), v in NAIVE_RHO.items()},
        "archetypes": {},
    }
    rec_by_arch = {}
    for r in records:
        rec_by_arch.setdefault(r["archetype"], []).append(r)

    for arch in sorted(archetypes):
        recs = rec_by_arch.get(arch, [])
        arch_rhos = {}
        for r in recs:
            key = f"{r['stat_a']}_{r['stat_b']}"
            if r["survives_both_gates"] and r["r_all"] is not None:
                arch_rhos[key] = {
                    "rho": r["r_all"],
                    "naive_rho": r["naive_rho"],
                    "delta_vs_naive": r["delta_vs_naive"],
                    "stable": r["stable"],
                    "r_early": r["r_early"],
                    "r_late": r["r_late"],
                    "n_obs": r["n_obs"],
                    "refined": True,
                }
            elif r["r_all"] is not None and r["naive_rho"] is not None:
                arch_rhos[key] = {
                    "rho": r["naive_rho"],  # fall back to naive
                    "r_measured": r["r_all"],
                    "naive_rho": r["naive_rho"],
                    "delta_vs_naive": r["delta_vs_naive"],
                    "stable": r["stable"],
                    "r_early": r["r_early"],
                    "r_late": r["r_late"],
                    "n_obs": r["n_obs"],
                    "refined": False,
                }
        output["archetypes"][arch] = arch_rhos

    return output


def build_markdown_report(records: list[dict], arch_df: pd.DataFrame) -> str:
    pd.options.display.float_format = "{:.4f}".format

    archetypes = arch_df["archetype"].value_counts().to_dict()
    n_archetypes = len(archetypes)

    lines = []
    lines.append("# Playstyle Archetype × Same-Player Residual Correlation Analysis")
    lines.append("")
    lines.append("**Date:** 2026-06-04  |  **Author:** analyze_playstyle_corr_sameplayer.py")
    lines.append("")
    lines.append("## Purpose")
    lines.append(
        "Does a player's PLAYSTYLE ARCHETYPE condition the same-player stat-pair "
        "residual correlations used in SGP (same-game parlay) pricing? "
        "The naive engine (`parlay_engine._SAME_PLAYER_RHO`) uses ONE flat rho "
        "per stat-pair for all players. This analysis tests whether archetype-pooled "
        "residual correlations are materially different and split-half stable."
    )
    lines.append("")
    lines.append("**Critical discipline:**")
    lines.append("- Unit = ARCHETYPE (pooled across players), NOT per-player (split-half persistence ~0.06)")
    lines.append("- Residual = actual − pregame OOF projection (player-mean fallback if OOF missing)")
    lines.append("- Stability gate: same sign + |r_early − r_late| ≤ 0.15")
    lines.append("- Materiality gate: |delta vs naive| ≥ 0.10")
    lines.append("- Min-n: ≥ 30 players per archetype, ≥ 300 player-game rows per cell")
    lines.append("- **NO SGP price history → zero ROI/edge claims. Accuracy improvement only.**")
    lines.append("")

    lines.append("## Archetype Definitions and Player Counts")
    lines.append("")
    lines.append("| Archetype | N Players | Rule |")
    lines.append("|-----------|-----------|------|")
    arch_rules = {
        "HIGH_AST_PLAYMAKER":  "ast_pct ≥ 0.22 AND usage ≥ 0.18 (PG-type)",
        "PNR_BALLHANDLER":     "pnr_handler_pg ≥ 0.40 AND usage ≥ 0.18 (priority 2)",
        "ISO_SCORER":          "iso_poss_pg ≥ 0.60 AND usage ≥ 0.20 (priority 3)",
        "POST_UP_BIG":         "post_up_pg ≥ 0.30 AND reb_rate ≥ 0.10 (priority 4)",
        "RIM_ROLL_BIG":        "reb_rate ≥ 0.12 AND paint_share ≥ 0.50 AND ast_pct ≤ 0.12",
        "SPOT_UP_SHOOTER":     "catch_shoot_3pa ≥ 1.5 AND unast_3pm ≤ 0.35",
        "THREE_AND_D_WING":    "catch_shoot_3pa ≥ 0.80 AND usage ≤ 0.18 AND ast_pct ≤ 0.14",
        "OTHER":               "Remainder (bench/two-way/low-min)",
    }
    for arch in sorted(archetypes.keys()):
        n = archetypes.get(arch, 0)
        rule = arch_rules.get(arch, "–")
        lines.append(f"| {arch} | {n} | {rule} |")
    lines.append("")

    lines.append("## Naive Flat _SAME_PLAYER_RHO (parlay_engine.py)")
    lines.append("")
    lines.append("| Stat Pair | Naive Rho |")
    lines.append("|-----------|-----------|")
    for (sa, sb), v in sorted(NAIVE_RHO.items()):
        lines.append(f"| {sa}↔{sb} | {v:.2f} |")
    lines.append("")

    lines.append("## Per-Archetype Residual Correlation Table")
    lines.append("")
    lines.append("Columns: `rho_all` = pooled residual correlation; "
                 "`r_early` / `r_late` = split-half; `Δnaive` = rho_all − naive_flat; "
                 "`S` = stable (Y/N); `M` = material |Δ|≥0.10; `PASS` = both gates.")
    lines.append("")

    # Group by archetype
    rec_by_arch = {}
    for r in records:
        rec_by_arch.setdefault(r["archetype"], []).append(r)

    survived_cells = []

    for arch in sorted(rec_by_arch.keys()):
        recs = sorted(rec_by_arch[arch], key=lambda r: (r["stat_a"], r["stat_b"]))
        n_pl = recs[0]["n_players"] if recs else 0
        lines.append(f"### {arch}  (n_players = {n_pl})")
        lines.append("")
        lines.append("| Pair | n_obs | rho_all | r_early | r_late | Δnaive | S | M | PASS |")
        lines.append("|------|-------|---------|---------|--------|--------|---|---|------|")

        for r in recs:
            if r["naive_rho"] is None:
                continue  # Only report pairs that exist in naive engine
            if r["status"] == "small_n":
                lines.append(
                    f"| {r['pair']} | {r['n_obs']} | — | — | — | — | — | — | small_n |"
                )
                continue
            r_all_s = f"{r['r_all']:.4f}" if r["r_all"] is not None else "—"
            r_e_s = f"{r['r_early']:.4f}" if r["r_early"] is not None else "—"
            r_l_s = f"{r['r_late']:.4f}" if r["r_late"] is not None else "—"
            d_s = f"{r['delta_vs_naive']:+.4f}" if r["delta_vs_naive"] is not None else "—"
            s_s = "Y" if r["stable"] else "N"
            m_s = "Y" if r["material"] else "N"
            p_s = "**PASS**" if r["survives_both_gates"] else "fail"
            lines.append(
                f"| {r['pair']} | {r['n_obs']:,} | {r_all_s} | {r_e_s} | {r_l_s} | "
                f"{d_s} | {s_s} | {m_s} | {p_s} |"
            )
            if r["survives_both_gates"]:
                survived_cells.append(r)
        lines.append("")

    lines.append("## Cells That Survive BOTH Gates (Stable + Material)")
    lines.append("")
    if not survived_cells:
        lines.append(
            "**Zero cells survive both gates.** "
            "All stat-pair correlations are either unstable (sign-flip or |Δhalves|>0.15) "
            "or not materially different from the naive flat rho (|Δ|<0.10)."
        )
    else:
        lines.append("| Archetype | Pair | rho_all | naive | Δnaive | r_early | r_late | n_obs |")
        lines.append("|-----------|------|---------|-------|--------|---------|--------|-------|")
        for r in sorted(survived_cells, key=lambda x: abs(x["delta_vs_naive"] or 0), reverse=True):
            lines.append(
                f"| {r['archetype']} | {r['pair']} | {r['r_all']:.4f} | "
                f"{r['naive_rho']:.2f} | {r['delta_vs_naive']:+.4f} | "
                f"{r['r_early']:.4f} | {r['r_late']:.4f} | {r['n_obs']:,} |"
            )
    lines.append("")

    # ─ Honest verdict ─────────────────────────────────────────────────────────
    n_survived = len(survived_cells)
    n_total_tested = sum(
        1 for r in records
        if r["naive_rho"] is not None and r["status"] == "ok"
    )
    n_unstable = sum(
        1 for r in records
        if r["naive_rho"] is not None and r["status"] == "ok" and not r["stable"]
    )
    n_stable_not_material = sum(
        1 for r in records
        if r["naive_rho"] is not None and r["status"] == "ok"
        and r["stable"] and not r["material"]
    )

    lines.append("## Honest Verdict")
    lines.append("")
    lines.append(f"- **Cells tested** (engine pairs × archetypes, n_obs≥300): {n_total_tested}")
    lines.append(f"- **Unstable** (sign-flip or |Δhalves|>0.15): {n_unstable} "
                 f"({100*n_unstable/max(n_total_tested,1):.0f}%)")
    lines.append(f"- **Stable but not material** (|Δnaive|<0.10): {n_stable_not_material} "
                 f"({100*n_stable_not_material/max(n_total_tested,1):.0f}%)")
    lines.append(f"- **Survive both gates**: {n_survived} "
                 f"({100*n_survived/max(n_total_tested,1):.0f}%)")
    lines.append("")

    if n_survived == 0:
        lines.append(
            "**VERDICT: Archetype-conditioning adds NO stable, material refinement** "
            "over the naive flat rho. The flat `_SAME_PLAYER_RHO` values in "
            "`parlay_engine.py` are not materially improved by playstyle archetype "
            "once stability (split-half) and materiality (|Δ|≥0.10) gates are applied. "
            "The residual correlations are dominated by common variance (role/position) "
            "already baked into the level that the flat population rho captures."
        )
    elif n_survived <= 3:
        pairs_str = ", ".join(
            f"{r['archetype']}×{r['pair']} (Δ={r['delta_vs_naive']:+.2f})"
            for r in sorted(survived_cells, key=lambda x: abs(x["delta_vs_naive"] or 0), reverse=True)
        )
        lines.append(
            f"**VERDICT: Marginal refinement** — {n_survived} cell(s) survive both gates: "
            f"{pairs_str}. These are legitimate candidates for archetype-specific rho "
            "in the parlay engine, but the overall picture is that the flat rho captures "
            "most of the signal. No SGP price history exists → accuracy improvement only, "
            "not edge validation."
        )
    else:
        lines.append(
            f"**VERDICT: Meaningful refinement** — {n_survived} cells survive both gates. "
            "The archetype-conditioned rho table in "
            "`data/models/prop_corr_archetype_sameplayer.json` is a more accurate "
            "joint model than the flat rho. No SGP price history exists → this is an "
            "accuracy improvement, not a validated betting edge."
        )
    lines.append("")

    lines.append("## Methodological Notes")
    lines.append("")
    lines.append(
        "- **Residual de-trending**: uses pregame OOF (faithful, `oof_pred`) as the "
        "per-player conditional mean. This removes level/role effects so the correlation "
        "measures 'do OVER-pts games coincide with OVER-ast games' not the trivial "
        "level correlation from usage/minutes."
    )
    lines.append(
        "- **Archetype pooling**: n per archetype ranges from "
        f"{min(archetypes.values())} to {max(archetypes.values())} players. "
        "Pooling across all players of an archetype overcomes the ~0.06 split-half "
        "persistence known for per-player correlations."
    )
    lines.append(
        "- **NOT validated against SGP prices**: no SGP closing-line data exists "
        "in this repo. The candidate rho table improves the joint probability model "
        "but has zero empirical edge validation. Do not claim ROI improvement."
    )
    lines.append(
        "- **Date split**: games split at median date within each archetype's "
        "available sample."
    )
    lines.append("")

    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--persist-map", metavar="PATH",
                        help="If provided, persist {player_id: archetype} JSON to PATH "
                             "(default: %(default)s) instead of the full analysis.",
                        nargs="?", const=str(OUT_ARCH_MAP), default=None)
    args, _ = parser.parse_known_args()

    if args.persist_map:
        arch_df = build_archetypes()
        out_path = Path(args.persist_map)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        arch_map = {int(row.player_id): row.archetype for _, row in arch_df.iterrows()}
        out_path.write_text(json.dumps(arch_map, indent=2), encoding="utf-8")
        print(f"[persist-map] Wrote {len(arch_map)} player->archetype mappings to {out_path}")
        return

    print("=" * 70)
    print("PLAYSTYLE ARCHETYPE × SAME-PLAYER RESIDUAL CORRELATION ANALYSIS")
    print("=" * 70)
    print()

    box = load_box()
    oof_wide = load_oof()
    resid_df = build_residuals(box, oof_wide)
    arch_df = build_archetypes()

    print()
    print("Computing archetype × stat-pair correlations...")
    records = compute_archetype_corrs(resid_df, arch_df)

    # Summary
    survived = [r for r in records if r["survives_both_gates"]]
    print(f"\n[result] Cells tested (ok + has naive rho): "
          f"{sum(1 for r in records if r['status']=='ok' and r['naive_rho'] is not None)}")
    print(f"[result] Cells surviving BOTH gates: {len(survived)}")
    for r in sorted(survived, key=lambda x: abs(x['delta_vs_naive'] or 0), reverse=True):
        pair_str = r['pair'].replace('↔', '<->')
        print(f"  PASS  {r['archetype']:<22s}  {pair_str:<12s}  "
              f"rho={r['r_all']:.4f}  naive={r['naive_rho']:.2f}  "
              f"delta={r['delta_vs_naive']:+.4f}  "
              f"r_e={r['r_early']:.4f}  r_l={r['r_late']:.4f}  n={r['n_obs']:,}")

    # Write outputs
    json_out = build_json_output(records, arch_df)
    MODELS.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(json_out, indent=2, default=str), encoding="utf-8")
    print(f"\n[output] JSON -> {OUT_JSON}")

    AUDITS.mkdir(parents=True, exist_ok=True)
    md = build_markdown_report(records, arch_df)
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"[output] MD   -> {OUT_MD}")

    print("\nDone.")


if __name__ == "__main__":
    main()
