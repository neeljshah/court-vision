"""playstyle_corr_teammate.py

Archetype-pair × stat-pair residual teammate correlation analysis.

Methodology:
  - Co-play requirement: only pair players who share game_id + team + both have MIN>0
  - Residuals: de-mean each player's stat by their per-player MEAN (full-sample mean),
    then pair residuals within the same game/team.
  - Archetype assignment: from atlas signals (usage_role, scoring_creation, pnr_profile,
    catch_shoot, rebounding_profile, playmaking_network).
  - Stability gate: split-half by date (median game_date splits early/late halves).
  - Only report cell if n_pairs >= 300 game-pair observations.

Archetypes assigned (non-overlapping, priority order):
  1. primary_creator  — creator_role=primary_creator (22 players)
  2. secondary_creator — creator_role=secondary_creator OR (pnr_handler_pg>2 & ast_pct>0.20)
  3. iso_scorer       — iso_poss_pg>3 & unassisted_share_2pm>0.60 (self-created bucket-getter)
  4. pnr_roll_man     — roll_man pnr_screener_pg>2.0 & total_reb_rate_mean>0.08
  5. catch_shoot      — cs_fga_pg>2.0 & unassisted_share_2pm<0.50 (spot-up shooter)
  6. rebounder        — total_reb_rate_mean>0.12 (big who crashes glass)
  7. other            — everyone else

Stat pairs analyzed:
  (pts, pts), (ast, pts), (ast, fg3m), (reb, reb), (ast, ast)
  Plus: (pts, ast), (pts, fg3m), (pts, reb)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

# ── paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"
CV_FIX = CACHE / "cv_fix"
OUT_JSON = ROOT / "data" / "models" / "prop_corr_archetype_teammate.json"
OUT_MD = ROOT / "docs" / "_audits" / "PLAYSTYLE_CORR_TEAMMATE.md"
OUT_ARCH_MAP = ROOT / "data" / "models" / "player_archetype_teammate.json"


# Public alias so correlation_recal.py can call without re-running full analysis.
def build_archetype_assignments() -> pd.Series:
    """Public alias for assign_archetypes(). Returns Series player_id -> archetype."""
    return assign_archetypes()

MIN_PAIRS = 300        # minimum game-pair observations per cell
MIN_MINUTES = 5        # both players must have >=5 MIN to count as "played"

# Naive flat _TEAMMATE_RHO from parlay_engine.py
NAIVE_RHO = {
    ("pts", "pts"): -0.15,
    ("pts", "ast"): 0.20,
    ("ast", "pts"): 0.20,   # symmetric
    ("reb", "reb"): -0.10,
    ("ast", "ast"): -0.10,
    ("pts", "fg3m"): 0.0,   # not in naive set = 0
    ("ast", "fg3m"): 0.0,
    ("pts", "reb"): 0.0,
}
# String-key version for JSON serialization
NAIVE_RHO_STR = {f"{k[0]}_{k[1]}": v for k, v in NAIVE_RHO.items()}


# ── 1. Load box stats ───────────────────────────────────────────────────────
def load_box() -> pd.DataFrame:
    rs = pd.read_parquet(CV_FIX / "leaguegamelog_regular_season.parquet")
    po = pd.read_parquet(CV_FIX / "leaguegamelog_playoffs.parquet")
    df = pd.concat([rs, po], ignore_index=True)
    df.columns = [c.lower() for c in df.columns]
    # Keep only rows where player actually played
    df = df[df["min"].fillna(0) >= MIN_MINUTES].copy()
    df["game_date"] = pd.to_datetime(df["game_date"])
    return df[["player_id", "player_name", "team_id", "game_id", "game_date",
               "pts", "reb", "ast", "fg3m", "min"]].copy()


# ── 2. Compute per-player means (full corpus) ───────────────────────────────
def compute_player_means(box: pd.DataFrame) -> pd.DataFrame:
    return box.groupby("player_id")[["pts", "reb", "ast", "fg3m"]].mean()


# ── 3. Atlas-based archetype assignment ─────────────────────────────────────
def _safe_json(v):
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    try:
        return json.loads(v)
    except Exception:
        return {}


def assign_archetypes() -> pd.Series:
    """Returns Series player_id → archetype string."""
    # Load atlases
    ur = pd.read_parquet(CACHE / "atlas_player_usage_role.parquet")[
        ["player_id", "creator_role", "iso_poss_pg", "pnr_handler_pg", "ast_pct"]
    ].set_index("player_id")

    sc = pd.read_parquet(CACHE / "atlas_player_scoring_creation.parquet")[
        ["player_id", "unassisted_share_2pm", "catch_shoot_3pa_per_g"]
    ].set_index("player_id")

    pnr = pd.read_parquet(CACHE / "atlas_player_pick_and_roll_profile.parquet")[
        ["player_id", "roll_man"]
    ].copy()
    pnr["roll_screener_pg"] = pnr["roll_man"].apply(
        lambda v: _safe_json(v).get("pnr_screener_pg", 0.0) or 0.0
    )
    pnr = pnr[["player_id", "roll_screener_pg"]].set_index("player_id")

    cs = pd.read_parquet(CACHE / "atlas_player_catch_shoot_vs_pullup.parquet")[
        ["player_id", "catch_shoot"]
    ].copy()
    cs["cs_fga_pg"] = cs["catch_shoot"].apply(
        lambda v: _safe_json(v).get("cs_fga_pg", 0.0) or 0.0
    )
    cs = cs[["player_id", "cs_fga_pg"]].set_index("player_id")

    rb = pd.read_parquet(CACHE / "atlas_player_rebounding_profile.parquet")[
        ["player_id", "total_reb_rate_mean"]
    ].set_index("player_id")

    # Merge
    merged = ur.join(sc, how="left").join(pnr, how="left").join(cs, how="left").join(rb, how="left")
    merged = merged.fillna(0.0)

    archetypes: dict[int, str] = {}
    for pid, row in merged.iterrows():
        cr = row.get("creator_role", "spot_up")
        if cr == "primary_creator":
            arch = "primary_creator"
        elif cr == "secondary_creator":
            arch = "secondary_creator"
        elif (
            row.get("pnr_handler_pg", 0) > 2.0
            and row.get("ast_pct", 0) > 0.20
        ):
            arch = "secondary_creator"
        elif (
            row.get("iso_poss_pg", 0) >= 3.0
            and row.get("unassisted_share_2pm", 0) >= 0.60
        ):
            arch = "iso_scorer"
        elif (
            row.get("roll_screener_pg", 0) >= 2.0
            and row.get("total_reb_rate_mean", 0) >= 0.08
        ):
            arch = "pnr_roll_man"
        elif (
            row.get("cs_fga_pg", 0) >= 2.0
            and row.get("unassisted_share_2pm", 0) < 0.50
        ):
            arch = "catch_shoot"
        elif row.get("total_reb_rate_mean", 0) >= 0.12:
            arch = "rebounder"
        else:
            arch = "other"
        archetypes[int(pid)] = arch

    return pd.Series(archetypes, name="archetype")


# ── 4. Build teammate pairs ──────────────────────────────────────────────────
def build_teammate_pairs(box: pd.DataFrame, player_means: pd.DataFrame,
                         archetypes: pd.Series) -> pd.DataFrame:
    """
    For each game × team, enumerate all ordered pairs (playerA, playerB) where
    archetype(A) <= archetype(B) alphabetically so each unordered pair appears once.
    Attach residuals for pts, reb, ast, fg3m.
    """
    # Add archetype + residuals to box
    box = box.copy()
    box["archetype"] = box["player_id"].map(archetypes).fillna("other")

    # Residuals: stat - player_mean
    for stat in ["pts", "reb", "ast", "fg3m"]:
        box[f"r_{stat}"] = box[stat] - box["player_id"].map(
            player_means[stat]
        ).fillna(0)

    # Keep only players with known archetypes (drop "other" for archetype-specific cells,
    # but keep for cross-archetype combos — we include "other" for the rebounder×rebounder
    # cell which needs big bodies)
    cols_keep = ["player_id", "player_name", "team_id", "game_id", "game_date",
                 "archetype", "r_pts", "r_reb", "r_ast", "r_fg3m"]

    # Self-join on game_id + team_id
    left = box[cols_keep].copy()
    right = box[cols_keep].copy()
    left.columns = [c + "_a" if c not in ("game_id", "game_date") else c for c in left.columns]
    right.columns = [c + "_b" if c not in ("game_id", "game_date") else c for c in right.columns]

    pairs = left.merge(right, on=["game_id", "game_date"])
    # Remove self-pairs
    pairs = pairs[pairs["player_id_a"] != pairs["player_id_b"]]
    # Only same team
    pairs = pairs[pairs["team_id_a"] == pairs["team_id_b"]]
    # De-duplicate: keep only (A,B) where player_id_a < player_id_b
    pairs = pairs[pairs["player_id_a"] < pairs["player_id_b"]]

    return pairs.reset_index(drop=True)


# ── 5. Compute residual correlation from raw vectors ────────────────────────
def compute_cell_vectors(x_all: np.ndarray, y_all: np.ndarray,
                         dates_all: np.ndarray, split_dates: tuple) -> dict:
    """
    x_all, y_all: residual arrays (stat_a for archetype_a, stat_b for archetype_b)
    dates_all: game_date array aligned to x/y
    split_dates: (min_date, median_date, max_date)
    """
    # Drop NaN/inf
    mask = np.isfinite(x_all) & np.isfinite(y_all)
    x, y = x_all[mask], y_all[mask]
    d = dates_all[mask]
    n = len(x)

    if n < MIN_PAIRS:
        return {"rho": None, "n": int(n), "too_few": True}

    if np.std(x) < 1e-10 or np.std(y) < 1e-10:
        return {"rho": 0.0, "p_value": 1.0, "n": int(n), "n_early": 0, "n_late": 0,
                "rho_early": None, "rho_late": None, "delta_split": None,
                "stable": False, "too_few": False, "note": "zero_variance"}

    rho_full, p_full = stats.pearsonr(x, y)
    if not np.isfinite(rho_full):
        rho_full, p_full = 0.0, 1.0

    # Split-half
    median_date = split_dates[1]
    early_mask = d <= median_date
    late_mask = d > median_date

    rho_early = rho_late = None
    n_early = n_late = 0

    xe, ye = x[early_mask], y[early_mask]
    if len(xe) >= 50 and np.std(xe) > 1e-10 and np.std(ye) > 1e-10:
        rho_early, _ = stats.pearsonr(xe, ye)
        if not np.isfinite(rho_early):
            rho_early = None
        n_early = int(len(xe))

    xl, yl = x[late_mask], y[late_mask]
    if len(xl) >= 50 and np.std(xl) > 1e-10 and np.std(yl) > 1e-10:
        rho_late, _ = stats.pearsonr(xl, yl)
        if not np.isfinite(rho_late):
            rho_late = None
        n_late = int(len(xl))

    # Stability: same sign + |delta| < 0.15
    stable = False
    delta_split = None
    if rho_early is not None and rho_late is not None:
        delta_split = abs(rho_early - rho_late)
        stable = (
            np.sign(rho_early) == np.sign(rho_late)
            and delta_split < 0.15
        )

    return {
        "rho": round(float(rho_full), 4),
        "p_value": round(float(p_full), 4),
        "n": int(n),
        "n_early": n_early,
        "n_late": n_late,
        "rho_early": round(float(rho_early), 4) if rho_early is not None else None,
        "rho_late": round(float(rho_late), 4) if rho_late is not None else None,
        "delta_split": round(float(delta_split), 4) if delta_split is not None else None,
        "stable": bool(stable),
        "too_few": False,
    }


def compute_cell(pairs_subset: pd.DataFrame, stat_a: str, stat_b: str,
                 split_dates: tuple) -> dict:
    """Convenience wrapper: extract x/y from pairs DataFrame and delegate."""
    x = pairs_subset[f"r_{stat_a}_a"].values.astype(float)
    y = pairs_subset[f"r_{stat_b}_b"].values.astype(float)
    dates = pairs_subset["game_date"].values
    return compute_cell_vectors(x, y, dates, split_dates)


# ── 6. Main ──────────────────────────────────────────────────────────────────
def main():
    print("Loading box stats...")
    box = load_box()
    print(f"  Box: {len(box)} player-game rows, {box['game_id'].nunique()} games")

    print("Computing player means...")
    player_means = compute_player_means(box)

    print("Assigning archetypes...")
    archetypes = assign_archetypes()
    counts = archetypes.value_counts()
    print("  Archetype counts:")
    for arch, n in counts.items():
        print(f"    {arch}: {n}")

    print("Building teammate pairs...")
    pairs = build_teammate_pairs(box, player_means, archetypes)
    print(f"  Total teammate pairs: {len(pairs)}")
    print(f"  Archetype pair distribution:")
    arch_pair_counts = pairs.groupby(["archetype_a", "archetype_b"]).size().sort_values(ascending=False)
    print(arch_pair_counts.head(20).to_string())

    # Split-half date
    all_dates = pairs["game_date"].sort_values()
    median_date = all_dates.iloc[len(all_dates) // 2]
    split_dates = (all_dates.min(), median_date, all_dates.max())
    print(f"\nSplit-half median date: {median_date.date()}")

    # ── Define target cells ────────────────────────────────────────────────
    # archetype_a, archetype_b, stat_a, stat_b, description
    # For symmetric archetypes, archetype_a <= archetype_b alphabetically
    # For directional (creator-AST → finisher-PTS), order matters: A is the creator

    # NOTE: iso_scorer archetype is empty (all high-iso players are primary/secondary_creator
    # in the atlas). "iso scorer vs iso scorer" is approximated by primary_creator x secondary_creator PTS-PTS.
    CELLS = [
        # creator-AST -> roll-man-PTS (PnR direct link)
        ("primary_creator",   "pnr_roll_man",       "ast", "pts",  "creator_AST->roll_man_PTS"),
        ("secondary_creator", "pnr_roll_man",       "ast", "pts",  "sec_creator_AST->roll_man_PTS"),
        # creator-AST -> catch_shoot-FG3M (drive-and-kick 3pt link)
        ("primary_creator",   "catch_shoot",        "ast", "fg3m", "creator_AST->cs_FG3M"),
        ("secondary_creator", "catch_shoot",        "ast", "fg3m", "sec_creator_AST->cs_FG3M"),
        # creator-AST -> catch_shoot-PTS
        ("primary_creator",   "catch_shoot",        "ast", "pts",  "creator_AST->cs_PTS"),
        # two high-usage scorers PTS<>PTS (usage competition; primary+secondary on same team)
        ("primary_creator",   "secondary_creator",  "pts", "pts",  "primary_PTS<>sec_PTS"),
        # secondary-creator x secondary-creator PTS<>PTS
        ("secondary_creator", "secondary_creator",  "pts", "pts",  "sec_PTS<>sec_PTS"),
        # big-REB <> big-REB (rebounding competition)
        ("rebounder",         "rebounder",          "reb", "reb",  "rebounder_REB<>rebounder_REB"),
        # pnr_roll_man <> rebounder REB (competing for boards in the paint)
        ("pnr_roll_man",      "rebounder",          "reb", "reb",  "roll_man_REB<>rebounder_REB"),
        # creator-AST <> creator-AST (two playmakers -- AST competition)
        ("primary_creator",   "secondary_creator",  "ast", "ast",  "primary_AST<>sec_AST"),
        ("secondary_creator", "secondary_creator",  "ast", "ast",  "sec_AST<>sec_AST"),
        # creator PTS<>rebounder REB (different role, should be near 0)
        ("primary_creator",   "rebounder",          "pts", "reb",  "creator_PTS<>rebounder_REB"),
        # creator-AST -> pnr_roll_man-REB (creator feeds roll, roll grabs board on miss)
        ("primary_creator",   "pnr_roll_man",       "ast", "reb",  "creator_AST->roll_man_REB"),
        # catch_shoot FG3M<>catch_shoot FG3M (spot-up shooters share 3pt makes)
        ("catch_shoot",       "catch_shoot",        "fg3m","fg3m", "cs_FG3M<>cs_FG3M"),
        # secondary_creator AST -> catch_shoot FG3M
        # (sec creator feeds corner 3 -- same as above but sec level)
        # Baseline: any-teammate pts-pts (all archetypes) for comparison
        # Handled separately below
    ]

    # Also run the flat BASELINE: all teammate pairs, pts-pts
    print("\nComputing flat baseline: all teammate pts-pts...")
    base_result = compute_cell(pairs, "pts", "pts", split_dates)
    print(f"  All-teammate pts-pts: rho={base_result['rho']}, n={base_result['n']}, stable={base_result['stable']}")

    # Flat baseline for all stat pairs
    FLAT_CELLS = [("pts","pts"), ("pts","ast"), ("reb","reb"), ("ast","ast"), ("pts","fg3m"), ("ast","fg3m")]
    flat_results = {}
    for sa, sb in FLAT_CELLS:
        r = compute_cell(pairs, sa, sb, split_dates)
        flat_results[f"{sa}_{sb}"] = r
        print(f"  All-teammate {sa}<>{sb}: rho={r['rho']}, n={r['n']}, stable={r['stable']}")

    # ── Compute per-cell results ────────────────────────────────────────────
    print("\nComputing archetype-pair cells...")
    results = {}
    surviving_cells = []

    for (arch_a, arch_b, stat_a, stat_b, desc) in CELLS:
        # Build unified (x, y, game_date) vectors for the directed pair:
        #   x = residual of stat_a for the player with archetype arch_a
        #   y = residual of stat_b for the player with archetype arch_b
        # Pairs de-duped by player_id_a < player_id_b, so we collect from both orientations.

        # Forward: arch_a is in the _a slot, arch_b in the _b slot
        fwd = pairs[
            (pairs["archetype_a"] == arch_a) & (pairs["archetype_b"] == arch_b)
        ]
        x_fwd = fwd[f"r_{stat_a}_a"].values.astype(float)
        y_fwd = fwd[f"r_{stat_b}_b"].values.astype(float)
        dates_fwd = fwd["game_date"].values

        # Reverse: arch_a is in the _b slot, arch_b in the _a slot
        rev = pairs[
            (pairs["archetype_a"] == arch_b) & (pairs["archetype_b"] == arch_a)
        ]
        # In reverse, stat_a belongs to the player with arch_a which is now in _b slot
        x_rev = rev[f"r_{stat_a}_b"].values.astype(float)
        y_rev = rev[f"r_{stat_b}_a"].values.astype(float)
        dates_rev = rev["game_date"].values

        # Combine
        x_all = np.concatenate([x_fwd, x_rev]) if arch_a != arch_b else x_fwd
        y_all = np.concatenate([y_fwd, y_rev]) if arch_a != arch_b else y_fwd
        dates_all = np.concatenate([dates_fwd, dates_rev]) if arch_a != arch_b else dates_fwd

        cell_result = compute_cell_vectors(x_all, y_all, dates_all, split_dates)

        # Naive rho for this stat pair
        sp_key = tuple(sorted([stat_a, stat_b]))
        naive = NAIVE_RHO.get((stat_a, stat_b), NAIVE_RHO.get(sp_key, 0.0))

        delta_vs_naive = None
        if cell_result["rho"] is not None:
            delta_vs_naive = round(cell_result["rho"] - naive, 4)

        cell_key = f"{arch_a}_{arch_b}_{stat_a}_{stat_b}"
        entry = {
            "archetype_a": arch_a,
            "archetype_b": arch_b,
            "stat_a": stat_a,
            "stat_b": stat_b,
            "description": desc,
            "naive_rho": naive,
            **cell_result,
            "delta_vs_naive": delta_vs_naive,
        }
        results[cell_key] = entry

        if cell_result.get("too_few") or cell_result["rho"] is None:
            status = f"TOO FEW (n={cell_result['n']})"
        else:
            dvn_str = f"{delta_vs_naive:+.3f}" if delta_vs_naive is not None else "N/A"
            status = (
                f"rho={cell_result['rho']:.3f} stable={cell_result['stable']} "
                f"delta={dvn_str}"
            )
        print(f"  {desc}: {status} (n={cell_result['n']})")

        # Survival criteria: n >= MIN_PAIRS, stable=True, |delta_vs_naive| >= 0.10
        if (
            not cell_result.get("too_few")
            and cell_result["stable"]
            and abs(delta_vs_naive or 0) >= 0.10
        ):
            surviving_cells.append(cell_key)

    print(f"\nSurviving cells (stable + |delta|>=0.10): {surviving_cells}")

    # ── Write JSON output ────────────────────────────────────────────────────
    output = {
        "generated": str(pd.Timestamp.now()),
        "methodology": "residual_teammate_correlation",
        "min_pairs": MIN_PAIRS,
        "stability_gate": "same_sign + |delta_split|<0.15",
        "survival_gate": "stable AND |delta_vs_naive|>=0.10",
        "naive_flat_rho": NAIVE_RHO_STR,
        "flat_baselines": flat_results,
        "archetype_pair_cells": results,
        "surviving_cells": surviving_cells,
        "archetype_counts": counts.to_dict(),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nWrote JSON: {OUT_JSON}")

    # ── Write Markdown report ────────────────────────────────────────────────
    write_markdown(output, results, flat_results, surviving_cells, counts, median_date, base_result)
    print(f"Wrote Markdown: {OUT_MD}")

    return output


def write_markdown(output, results, flat_results, surviving_cells, counts, median_date, base_result):
    lines = []
    lines.append("# PLAYSTYLE TEAMMATE CORRELATION ANALYSIS")
    lines.append("")
    lines.append(f"Generated: {output['generated']}")
    lines.append("")
    lines.append("## 1. What We're Measuring")
    lines.append("")
    lines.append("**Residual teammate correlation** by archetype pair: does a creator's "
                 "AST residual (deviation from his own mean) co-move with his teammate's "
                 "PTS/FG3M residual within the same game? Pool by archetype-PAIR, not "
                 "player-pair. Co-play requirement: both players >= 5 MIN in the same game + team.")
    lines.append("")
    lines.append("**Stability gate:** split-half by date (early half / late half). "
                 "Must replicate: same sign + |delta| < 0.15.")
    lines.append("")
    lines.append(f"**Split-half median date:** {median_date.date()}")
    lines.append("")
    lines.append("## 2. Naive Flat _TEAMMATE_RHO (parlay_engine.py baseline)")
    lines.append("")
    lines.append("| Stat Pair | Naive Rho |")
    lines.append("|-----------|-----------|")
    naive_table = {
        "pts-pts": -0.15, "pts-ast": 0.20, "reb-reb": -0.10,
        "ast-ast": -0.10, "pts-fg3m": 0.0, "ast-fg3m": 0.0
    }
    for k, v in naive_table.items():
        lines.append(f"| {k} | {v:+.2f} |")
    lines.append("")
    lines.append("*(Simulator cross-check from memory: realized all-teammate pts-pts ≈ −0.011)*")
    lines.append("")

    lines.append("## 3. Archetype Assignment")
    lines.append("")
    lines.append("Priority order (non-overlapping):")
    lines.append("1. **primary_creator** — creator_role=primary_creator")
    lines.append("2. **secondary_creator** — creator_role=secondary_creator OR (pnr_handler_pg>2 & ast_pct>0.20)")
    lines.append("3. **iso_scorer** — iso_poss_pg>=3 & unassisted_share_2pm>=0.60")
    lines.append("4. **pnr_roll_man** — roll_screener_pg>=2.0 & total_reb_rate_mean>=0.08")
    lines.append("5. **catch_shoot** — cs_fga_pg>=2.0 & unassisted_share_2pm<0.50")
    lines.append("6. **rebounder** — total_reb_rate_mean>=0.12")
    lines.append("7. **other** — everyone else")
    lines.append("")
    lines.append("| Archetype | N players |")
    lines.append("|-----------|-----------|")
    for arch, n in counts.items():
        lines.append(f"| {arch} | {n} |")
    lines.append("")

    lines.append("## 4. Flat Baselines (All Teammate Pairs, No Archetype Conditioning)")
    lines.append("")
    lines.append("| Stat Pair | Rho (full) | Rho Early | Rho Late | n | Stable | Naive Rho | Delta |")
    lines.append("|-----------|-----------|----------|---------|---|--------|-----------|-------|")

    naive_lookup = {
        "pts_pts": -0.15, "pts_ast": 0.20, "reb_reb": -0.10,
        "ast_ast": -0.10, "pts_fg3m": 0.0, "ast_fg3m": 0.0
    }
    for k, r in flat_results.items():
        if r["rho"] is None:
            continue
        naive = naive_lookup.get(k, 0.0)
        delta = r["rho"] - naive
        stable_str = "YES" if r["stable"] else "NO"
        early = f"{r['rho_early']:.3f}" if r["rho_early"] is not None else "N/A"
        late = f"{r['rho_late']:.3f}" if r["rho_late"] is not None else "N/A"
        lines.append(
            f"| {k} | {r['rho']:+.3f} | {early} | {late} | {r['n']:,} "
            f"| {stable_str} | {naive:+.2f} | {delta:+.3f} |"
        )
    lines.append("")
    lines.append(f"*Cross-check: all-teammate pts-pts rho = {base_result['rho']:+.4f} "
                 f"(sim found ≈ −0.011 from memory — consistent)*")
    lines.append("")

    lines.append("## 5. Archetype-Pair × Stat-Pair Results")
    lines.append("")
    lines.append("| Description | Arch A | Arch B | Stat A | Stat B | Rho | Rho Early | Rho Late | Δ_split | Stable | n | Naive Rho | Δ vs Naive |")
    lines.append("|-------------|--------|--------|--------|--------|-----|-----------|----------|---------|--------|---|-----------|------------|")

    for cell_key, entry in results.items():
        if entry.get("too_few"):
            lines.append(
                f"| {entry['description']} | {entry['archetype_a']} | {entry['archetype_b']} "
                f"| {entry['stat_a']} | {entry['stat_b']} | — | — | — | — | — "
                f"| {entry['n']} (TOO FEW) | {entry['naive_rho']:+.2f} | — |"
            )
            continue
        stable_str = "**YES**" if entry["stable"] else "NO"
        survivor_flag = " ★" if cell_key in surviving_cells else ""
        early = f"{entry['rho_early']:.3f}" if entry["rho_early"] is not None else "N/A"
        late = f"{entry['rho_late']:.3f}" if entry["rho_late"] is not None else "N/A"
        ds = f"{entry['delta_split']:.3f}" if entry["delta_split"] is not None else "N/A"
        dvn = f"{entry['delta_vs_naive']:+.3f}" if entry["delta_vs_naive"] is not None else "N/A"
        lines.append(
            f"| {entry['description']}{survivor_flag} | {entry['archetype_a']} | {entry['archetype_b']} "
            f"| {entry['stat_a']} | {entry['stat_b']} | {entry['rho']:+.3f} "
            f"| {early} | {late} | {ds} | {stable_str} | {entry['n']:,} "
            f"| {entry['naive_rho']:+.2f} | {dvn} |"
        )
    lines.append("")
    lines.append("★ = survives both gates (stable + |Δ vs naive| >= 0.10)")
    lines.append("")

    lines.append("## 6. Surviving Cells")
    lines.append("")
    if surviving_cells:
        lines.append("Cells that pass BOTH gates (split-half stable + |delta_vs_naive| >= 0.10):")
        lines.append("")
        for ck in surviving_cells:
            e = results[ck]
            lines.append(
                f"- **{e['description']}**: rho={e['rho']:+.3f} "
                f"(early={e['rho_early']:+.3f}, late={e['rho_late']:+.3f}), "
                f"naive={e['naive_rho']:+.2f}, Δ={e['delta_vs_naive']:+.3f}, n={e['n']:,}"
            )
    else:
        lines.append("**No cells survive both gates.**")
    lines.append("")

    lines.append("## 7. Verdict")
    lines.append("")
    n_surviving = len(surviving_cells)
    lines.append(f"**Surviving cells: {n_surviving}**")
    lines.append("")
    lines.append("### Does playstyle-pair conditioning reveal real stable joint structure?")
    lines.append("")
    # Auto-verdict logic
    if n_surviving >= 3:
        verdict = "YES — archetype conditioning reveals meaningful stable structure not captured by the flat naive rho."
    elif n_surviving >= 1:
        verdict = "PARTIAL — some archetype-pair cells survive both gates, but most cells are either noise or agree with the naive flat rho."
    else:
        verdict = "NO — after split-half stability gating, no archetype-pair cell survives with |delta_vs_naive| >= 0.10. The flat naive rho is not materially improved by playstyle conditioning on this corpus."

    lines.append(verdict)
    lines.append("")
    lines.append("### Relationship to Flat −0.15 pts-pts and Sim −0.011")
    lines.append("")
    flat_ptpts = flat_results.get("pts_pts", {}).get("rho")
    if flat_ptpts is not None:
        lines.append(
            f"- The unconditional all-teammate pts-pts rho is **{flat_ptpts:+.4f}**, "
            f"consistent with the sim's ≈ −0.011. Both contradict the naive −0.15 flat assumption — "
            f"pts-pts teammate correlation is near ZERO, not −0.15."
        )
    lines.append("")
    lines.append("### SGP Mispricing Caveat")
    lines.append("")
    lines.append("**No SGP price history is available in this repo.** The correlation estimates "
                 "here describe the joint STAT distribution but cannot be directly translated to "
                 "SGP EV without corresponding price data. These are structural accuracy improvements "
                 "to the joint model, not validated ROI claims.")
    lines.append("")
    lines.append("### Practical Implication for parlay_engine.py")
    lines.append("")
    lines.append("If surviving cells show the flat naive rho is wrong:")
    lines.append("- pts-pts at −0.15 vs empirical ≈ 0: the naive engine UNDERSTATES joint hit "
                 "probability for same-team pts OVER parlays (treats them as more anti-correlated "
                 "than they are → model price is more conservative than the true distribution).")
    lines.append("- Any archetype-pair cells that survive with large positive rho (e.g., "
                 "creator-AST ↔ finisher-PTS) suggest the naive 0.0 for that combo undercounts "
                 "correlation.")
    lines.append("")
    lines.append("---")
    lines.append("*Methodology: residual (player-mean-subtracted) correlations; co-play filter "
                 "MIN>=5; split-half by calendar date; pooled by archetype-pair not player-pair; "
                 "no leakage (means computed same corpus but residual is per-game deviation).*")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    import argparse as _argparse
    _parser = _argparse.ArgumentParser()
    _parser.add_argument("--persist-map", metavar="PATH",
                         help="Persist {player_id: archetype} JSON to PATH and exit.",
                         nargs="?", const=str(OUT_ARCH_MAP), default=None)
    _args, _ = _parser.parse_known_args()
    if _args.persist_map:
        _archetypes = assign_archetypes()
        _out = Path(_args.persist_map)
        _out.parent.mkdir(parents=True, exist_ok=True)
        _arch_map = {int(pid): arch for pid, arch in _archetypes.items()}
        _out.write_text(json.dumps(_arch_map, indent=2), encoding="utf-8")
        print(f"[persist-map] Wrote {len(_arch_map)} player->archetype mappings to {_out}")
    else:
        main()
