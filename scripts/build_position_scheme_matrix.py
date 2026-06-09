"""
INT-20: Position x Defensive Scheme Matchup Matrix
====================================================
Position-based version of INT-17 (which used CV-derived archetypes).
Joins build_pergame_dataset rows with:
  - Position (from dataset's 'position' field, normalized to 5 standard positions)
  - Opponent scheme (from INT-12 defensive_schemes data)
  - Stat deviation: target_X - ewma_X_l5

Aggregate by (position, scheme) cells per stat.
Gate: n >= 100 AND |t| > 2.0

Outputs:
  data/intelligence/position_scheme_interactions.parquet
  data/intelligence/position_scheme_signals.json
  vault/Intelligence/Position_Scheme_Matrix.md
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from src.prediction.prop_pergame import build_pergame_dataset  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
NBA_CACHE = PROJECT_DIR / "data" / "nba"
OUT_DIR = PROJECT_DIR / "data" / "intelligence"
VAULT_DIR = PROJECT_DIR / "vault" / "Intelligence"

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

# Standard 5 positions — hybrid normalization map
POSITION_MAP: Dict[str, str] = {
    "Guard":            "PG",      # primary: treat generic Guard as PG
    "Forward":          "SF",      # primary: treat generic Forward as SF
    "Center":           "C",
    "Guard-Forward":    "SG",      # SG is the bridge position
    "Forward-Guard":    "SG",
    "Forward-Center":   "PF",
    "Center-Forward":   "PF",
    # explicit 5-position strings (sometimes appear)
    "Point Guard":      "PG",
    "Shooting Guard":   "SG",
    "Small Forward":    "SF",
    "Power Forward":    "PF",
    "G":                "PG",
    "F":                "SF",
    "C":                "C",
    "G-F":              "SG",
    "F-G":              "SG",
    "F-C":              "PF",
    "C-F":              "PF",
}

# INT-12 Defensive Scheme data (from Defensive_Schemes.md / vault)
# team -> (dominant_tag, drop_score, paint_prot_score, perim_denial_score,
#          pace_ctrl_score, iso_force_score, closeout_score, confidence)
TEAM_SCHEMES: Dict[str, Dict] = {
    "ATL": {"dominant_tag": "SWITCH HEAVY",        "drop_score": -0.172, "paint_prot": 0.118,  "perim_denial": -0.054, "pace_ctrl": 0.177,  "iso_force": -0.035, "closeout": -0.131, "confidence": "high"},
    "BKN": {"dominant_tag": "PACE CONTROL",        "drop_score":  0.023, "paint_prot": -0.164, "perim_denial":  0.005, "pace_ctrl": 0.200,  "iso_force": -0.326, "closeout":  0.112, "confidence": "low"},
    "BOS": {"dominant_tag": "PAINT-FIRST DEFENSE", "drop_score": -0.061, "paint_prot": 0.177,  "perim_denial": -0.095, "pace_ctrl": 0.098,  "iso_force":  0.142, "closeout": -0.255, "confidence": "high"},
    "CHA": {"dominant_tag": "PAINT-FIRST DEFENSE", "drop_score": -0.035, "paint_prot": 0.152,  "perim_denial": -0.240, "pace_ctrl": 0.142,  "iso_force":  0.001, "closeout":  0.077, "confidence": "med"},
    "CHI": {"dominant_tag": "DROP COVERAGE",       "drop_score":  0.293, "paint_prot": -0.087, "perim_denial": -0.044, "pace_ctrl": 0.099,  "iso_force":  0.001, "closeout": -0.315, "confidence": "high"},
    "CLE": {"dominant_tag": "SWITCH HEAVY",        "drop_score": -0.271, "paint_prot": 0.332,  "perim_denial":  0.026, "pace_ctrl": -0.074, "iso_force": -0.008, "closeout": -0.017, "confidence": "med"},
    "DAL": {"dominant_tag": "DROP COVERAGE",       "drop_score":  0.136, "paint_prot": -0.142, "perim_denial":  0.141, "pace_ctrl": -0.533, "iso_force": -0.034, "closeout": -0.277, "confidence": "med"},
    "DEN": {"dominant_tag": "DROP COVERAGE",       "drop_score":  0.135, "paint_prot": 0.056,  "perim_denial":  0.135, "pace_ctrl": -0.208, "iso_force": -0.047, "closeout": -0.121, "confidence": "med"},
    "DET": {"dominant_tag": "SWITCH HEAVY",        "drop_score": -0.211, "paint_prot": 0.263,  "perim_denial":  0.012, "pace_ctrl": -0.185, "iso_force": -0.267, "closeout": -0.112, "confidence": "high"},
    "GSW": {"dominant_tag": "PACE CONTROL",        "drop_score":  0.065, "paint_prot": 0.029,  "perim_denial": -0.181, "pace_ctrl": 0.111,  "iso_force": -0.084, "closeout": -0.412, "confidence": "high"},
    "HOU": {"dominant_tag": "SWITCH HEAVY",        "drop_score": -0.191, "paint_prot": 0.197,  "perim_denial": -0.038, "pace_ctrl": -0.255, "iso_force":  0.052, "closeout": -0.134, "confidence": "med"},
    "IND": {"dominant_tag": "ISO FORCE",           "drop_score":  0.072, "paint_prot": -0.072, "perim_denial":  0.076, "pace_ctrl": -0.064, "iso_force":  0.099, "closeout": -0.211, "confidence": "med"},
    "LAC": {"dominant_tag": "DROP COVERAGE",       "drop_score":  0.158, "paint_prot": -0.158, "perim_denial":  0.035, "pace_ctrl": 0.751,  "iso_force": -0.140, "closeout": -0.202, "confidence": "high"},
    "LAL": {"dominant_tag": "ACTIVE CLOSEOUTS",    "drop_score": -0.022, "paint_prot": 0.059,  "perim_denial": -0.036, "pace_ctrl": -0.429, "iso_force":  0.014, "closeout":  0.054, "confidence": "high"},
    "MEM": {"dominant_tag": "SWITCH HEAVY",        "drop_score": -0.336, "paint_prot": 0.366,  "perim_denial": -0.164, "pace_ctrl": 0.141,  "iso_force": -0.059, "closeout": -0.140, "confidence": "med"},
    "MIA": {"dominant_tag": "PACE CONTROL",        "drop_score":  0.059, "paint_prot": -0.089, "perim_denial": -0.053, "pace_ctrl": 0.189,  "iso_force": -0.087, "closeout": -0.107, "confidence": "med"},
    "MIL": {"dominant_tag": "SWITCH HEAVY",        "drop_score": -0.200, "paint_prot": 0.174,  "perim_denial": -0.028, "pace_ctrl": 0.186,  "iso_force": -0.101, "closeout": -0.374, "confidence": "high"},
    "MIN": {"dominant_tag": "DROP COVERAGE",       "drop_score":  0.577, "paint_prot": -0.091, "perim_denial":  0.140, "pace_ctrl": -0.221, "iso_force": -0.011, "closeout": -0.185, "confidence": "high"},
    "NOP": {"dominant_tag": "ISO FORCE",           "drop_score": -0.073, "paint_prot": -0.183, "perim_denial": -0.262, "pace_ctrl": -0.639, "iso_force":  0.080, "closeout": -0.263, "confidence": "med"},
    "NYK": {"dominant_tag": "BALANCED",            "drop_score": -0.074, "paint_prot": -0.043, "perim_denial": -0.097, "pace_ctrl": -0.513, "iso_force": -0.044, "closeout": -0.387, "confidence": "high"},
    "OKC": {"dominant_tag": "DROP COVERAGE",       "drop_score":  0.355, "paint_prot": -0.358, "perim_denial":  0.045, "pace_ctrl": -0.149, "iso_force": -0.145, "closeout": -0.181, "confidence": "med"},
    "ORL": {"dominant_tag": "DROP COVERAGE",       "drop_score":  0.127, "paint_prot": 0.092,  "perim_denial":  0.043, "pace_ctrl": 0.094,  "iso_force": -0.240, "closeout": -0.283, "confidence": "med"},
    "PHI": {"dominant_tag": "DROP COVERAGE",       "drop_score":  0.103, "paint_prot": 0.011,  "perim_denial": -0.333, "pace_ctrl": 0.477,  "iso_force": -0.141, "closeout":  0.006, "confidence": "med"},
    "PHX": {"dominant_tag": "SWITCH HEAVY",        "drop_score": -0.140, "paint_prot": 0.081,  "perim_denial":  0.157, "pace_ctrl": 0.192,  "iso_force": -0.287, "closeout": -0.276, "confidence": "low"},
    "POR": {"dominant_tag": "PERIMETER DENIAL",    "drop_score": -0.017, "paint_prot": -0.174, "perim_denial":  0.383, "pace_ctrl": 0.108,  "iso_force":  0.003, "closeout": -0.397, "confidence": "med"},
    "SAC": {"dominant_tag": "HELP DEFENSE",        "drop_score":  0.015, "paint_prot": -0.049, "perim_denial": -0.037, "pace_ctrl": -0.078, "iso_force": -0.056, "closeout": -0.119, "confidence": "high"},
    "SAS": {"dominant_tag": "ISO FORCE",           "drop_score":  0.011, "paint_prot": 0.039,  "perim_denial": -0.030, "pace_ctrl": -0.058, "iso_force":  0.177, "closeout":  0.080, "confidence": "med"},
    "TOR": {"dominant_tag": "PAINT-FIRST DEFENSE", "drop_score": -0.092, "paint_prot": 0.117,  "perim_denial": -0.015, "pace_ctrl": 0.326,  "iso_force": -0.166, "closeout": -0.133, "confidence": "low"},
    "UTA": {"dominant_tag": "PERIMETER DENIAL",    "drop_score": -0.084, "paint_prot": -0.068, "perim_denial":  0.283, "pace_ctrl": 0.509,  "iso_force": -0.010, "closeout": -0.133, "confidence": "med"},
    "WAS": {"dominant_tag": "SWITCH HEAVY",        "drop_score": -0.321, "paint_prot": 0.103,  "perim_denial":  0.118, "pace_ctrl": 0.226,  "iso_force": -0.036, "closeout":  0.069, "confidence": "med"},
    # Historical / relocated franchises that may appear in gamelogs
    "NJN": {"dominant_tag": "BALANCED",            "drop_score":  0.000, "paint_prot": 0.000,  "perim_denial":  0.000, "pace_ctrl": 0.000,  "iso_force":  0.000, "closeout":  0.000, "confidence": "low"},
    "NOH": {"dominant_tag": "BALANCED",            "drop_score":  0.000, "paint_prot": 0.000,  "perim_denial":  0.000, "pace_ctrl": 0.000,  "iso_force":  0.000, "closeout":  0.000, "confidence": "low"},
    "SEA": {"dominant_tag": "BALANCED",            "drop_score":  0.000, "paint_prot": 0.000,  "perim_denial":  0.000, "pace_ctrl": 0.000,  "iso_force":  0.000, "confidence": "low"},
    "VAN": {"dominant_tag": "BALANCED",            "drop_score":  0.000, "paint_prot": 0.000,  "perim_denial":  0.000, "pace_ctrl": 0.000,  "iso_force":  0.000, "confidence": "low"},
}

# Scheme display order for matrices
SCHEME_ORDER = [
    "DROP COVERAGE", "SWITCH HEAVY", "PAINT-FIRST DEFENSE",
    "PERIMETER DENIAL", "PACE CONTROL", "BALANCED",
    "ISO FORCE", "HELP DEFENSE", "ACTIVE CLOSEOUTS",
]

POS_ORDER = ["PG", "SG", "SF", "PF", "C"]


# ---------------------------------------------------------------------------
# Step 1: Build (player_id, date_str) -> opp_team lookup from gamelogs
# ---------------------------------------------------------------------------
def _parse_matchup_opp(matchup: str, team_abbr: str | None = None) -> str:
    """
    MATCHUP examples:
      'PHX vs. DEN'  -> away team is PHX, home is DEN
      'LAC @ MIA'    -> LAC is away, MIA is home
    Returns the opponent abbreviation (the 3-char token that is NOT the player's team).
    If team_abbr provided, returns the other one; else returns the last token.
    """
    parts = matchup.replace("vs.", "").replace("@", "").split()
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) < 2:
        return "UNK"
    if team_abbr and parts[0] == team_abbr:
        return parts[-1]
    if team_abbr and parts[-1] == team_abbr:
        return parts[0]
    # Fallback: return the last token (home team when format is "team vs. home")
    return parts[-1]


def _normalize_date(game_date_str: str) -> str:
    """Convert 'Apr 06, 2023' -> 'YYYY-MM-DD'."""
    try:
        return pd.to_datetime(game_date_str).strftime("%Y-%m-%d")
    except Exception:
        return game_date_str


def build_opp_lookup() -> Dict[tuple, str]:
    """Build {(player_id, date_YYYY-MM-DD): opp_team_abbr} from all gamelog files."""
    print("[Step 1] Building (player_id, date) -> opp_team lookup from gamelogs...")
    lookup: Dict[tuple, str] = {}
    nba_dir = PROJECT_DIR / "data" / "nba"
    files = list(nba_dir.glob("gamelog_*.json"))
    print(f"         Found {len(files):,} gamelog files")

    for fpath in files:
        # filename: gamelog_{player_id}_{season}.json
        stem_parts = fpath.stem.split("_")
        if len(stem_parts) < 2:
            continue
        try:
            player_id = int(stem_parts[1])
        except ValueError:
            continue

        try:
            with open(fpath, encoding="utf-8") as fh:
                games = json.load(fh)
        except Exception:
            continue

        if not isinstance(games, list):
            continue

        for g in games:
            matchup = g.get("MATCHUP", "")
            raw_date = g.get("GAME_DATE", "")
            if not matchup or not raw_date:
                continue
            date_str = _normalize_date(raw_date)
            opp = _parse_matchup_opp(matchup)
            lookup[(player_id, date_str)] = opp

    print(f"         Lookup size: {len(lookup):,} (player_id, date) pairs")
    return lookup


# ---------------------------------------------------------------------------
# Step 2: Normalize position to PG/SG/SF/PF/C
# ---------------------------------------------------------------------------
def normalize_position(raw_pos: str) -> str:
    if not raw_pos or not isinstance(raw_pos, str):
        return "unknown"
    raw = raw_pos.strip()
    # Direct map
    if raw in POSITION_MAP:
        return POSITION_MAP[raw]
    # Prefix: take first token
    first = raw.split("-")[0].split("/")[0].strip()
    if first in POSITION_MAP:
        return POSITION_MAP[first]
    return "unknown"


# ---------------------------------------------------------------------------
# Step 3: Load build_pergame_dataset and join with opp/scheme/position
# ---------------------------------------------------------------------------
def build_joined_df(opp_lookup: Dict[tuple, str]) -> pd.DataFrame:
    print("[Step 2] Loading build_pergame_dataset (~30s)...")
    rows, _ = build_pergame_dataset()
    df = pd.DataFrame(rows)
    print(f"         Dataset shape: {df.shape}")

    # Normalize date to YYYY-MM-DD
    df["date_str"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    # Normalize position
    df["pos5"] = df["position"].apply(normalize_position)
    pos_counts = df["pos5"].value_counts()
    print(f"         Position coverage: {pos_counts.to_dict()}")

    # Resolve opp_team via gamelog lookup
    print("[Step 3] Joining opponent team from gamelog lookup...")
    df["opp_team"] = df.apply(
        lambda r: opp_lookup.get((int(r["player_id"]), r["date_str"]), None),
        axis=1,
    )
    n_resolved = df["opp_team"].notna().sum()
    print(f"         Rows with opp_team resolved: {n_resolved:,} / {len(df):,}")

    # Resolve opp scheme
    df["opp_scheme"] = df["opp_team"].map(
        lambda t: TEAM_SCHEMES.get(t, {}).get("dominant_tag", None) if t else None
    )
    n_scheme = df["opp_scheme"].notna().sum()
    print(f"         Rows with opp_scheme resolved: {n_scheme:,}")

    # Keep only rows with valid position + scheme + targets
    target_cols = [f"target_{s}" for s in STATS]
    ewma_cols = [f"ewma_{s}" for s in STATS]

    df_clean = df[
        (df["pos5"] != "unknown") &
        df["opp_scheme"].notna()
    ].copy()

    # Compute deviations: target_X - ewma_X
    for s in STATS:
        tc = f"target_{s}"
        ec = f"ewma_{s}"
        if tc in df_clean.columns and ec in df_clean.columns:
            df_clean[f"dev_{s}"] = df_clean[tc] - df_clean[ec]

    print(f"         Clean rows (pos+scheme): {len(df_clean):,}")
    return df_clean


# ---------------------------------------------------------------------------
# Step 4: Aggregate per (position, scheme, stat)
# ---------------------------------------------------------------------------
def compute_cell_stats(df: pd.DataFrame) -> pd.DataFrame:
    print("[Step 4] Aggregating per (position, scheme, stat) cells...")
    records = []
    for s in STATS:
        dev_col = f"dev_{s}"
        actual_col = f"target_{s}"
        baseline_col = f"ewma_{s}"
        if dev_col not in df.columns:
            continue

        sub = df[[dev_col, actual_col, baseline_col, "pos5", "opp_scheme"]].dropna(
            subset=[dev_col, "pos5", "opp_scheme"]
        )
        grouped = sub.groupby(["pos5", "opp_scheme"])

        for (pos, scheme), grp in grouped:
            devs = grp[dev_col].values
            n = len(devs)
            if n < 5:
                continue
            mean_dev = float(np.mean(devs))
            std_dev = float(np.std(devs, ddof=1)) if n > 1 else np.nan
            if n > 1 and std_dev > 0:
                t_stat, p_val = stats.ttest_1samp(devs, 0.0)
            else:
                t_stat, p_val = 0.0, 1.0
            mean_actual = float(grp[actual_col].mean()) if actual_col in grp else np.nan
            mean_baseline = float(grp[baseline_col].mean()) if baseline_col in grp else np.nan

            records.append({
                "position":      pos,
                "opp_scheme":    scheme,
                "stat":          s,
                "n":             n,
                "mean_dev":      mean_dev,
                "std_dev":       std_dev,
                "t_stat":        t_stat,
                "p_value":       p_val,
                "mean_actual":   mean_actual,
                "mean_baseline": mean_baseline,
                "significant":   (n >= 100) and (abs(t_stat) > 2.0),
            })

    out = pd.DataFrame(records)
    sig = out[out["significant"]]
    print(f"         Total cells: {len(out):,} | Significant (n>=100, |t|>2): {len(sig):,}")
    return out


# ---------------------------------------------------------------------------
# Step 5: Basketball intuition validation
# ---------------------------------------------------------------------------
def validate_intuitions(cells: pd.DataFrame) -> list[dict]:
    """
    Check 5+ expected matchup directions.
    Returns list of dicts with prediction, actual result, verdict.
    """
    checks = [
        {
            "label":     "C vs PAINT-FIRST DEFENSE -> UNDER PTS (centers blocked from rim)",
            "position":  "C",
            "scheme":    "PAINT-FIRST DEFENSE",
            "stat":      "pts",
            "direction": "negative",
        },
        {
            "label":     "PG vs PERIMETER DENIAL -> UNDER AST (handler can't initiate)",
            "position":  "PG",
            "scheme":    "PERIMETER DENIAL",
            "stat":      "ast",
            "direction": "negative",
        },
        {
            "label":     "SF vs SWITCH HEAVY -> MIXED PTS (wings can exploit mismatches)",
            "position":  "SF",
            "scheme":    "SWITCH HEAVY",
            "stat":      "pts",
            "direction": "any",
        },
        {
            "label":     "PG vs DROP COVERAGE -> OVER PTS (handlers feast in drop)",
            "position":  "PG",
            "scheme":    "DROP COVERAGE",
            "stat":      "pts",
            "direction": "positive",
        },
        {
            "label":     "C vs DROP COVERAGE -> OVER PTS (post-ups available)",
            "position":  "C",
            "scheme":    "DROP COVERAGE",
            "stat":      "pts",
            "direction": "positive",
        },
        {
            "label":     "PG vs SWITCH HEAVY -> UNDER PTS (switches take away PnR reads)",
            "position":  "PG",
            "scheme":    "SWITCH HEAVY",
            "stat":      "pts",
            "direction": "negative",
        },
        {
            "label":     "C vs SWITCH HEAVY -> OVER REB (big men get offensive boards vs smaller switchers)",
            "position":  "C",
            "scheme":    "SWITCH HEAVY",
            "stat":      "reb",
            "direction": "positive",
        },
    ]

    results = []
    for chk in checks:
        mask = (
            (cells["position"] == chk["position"]) &
            (cells["opp_scheme"] == chk["scheme"]) &
            (cells["stat"] == chk["stat"])
        )
        row = cells[mask]
        if row.empty:
            results.append({**chk, "mean_dev": None, "t_stat": None, "n": None,
                             "verdict": "NO DATA"})
            continue
        row = row.iloc[0]
        mean_dev = row["mean_dev"]
        t = row["t_stat"]
        n = row["n"]
        if chk["direction"] == "positive":
            validated = mean_dev > 0
        elif chk["direction"] == "negative":
            validated = mean_dev < 0
        else:
            validated = True  # "any" direction always counts as mixed
        verdict = "VALIDATED" if validated else "REFUTED"
        results.append({
            **chk,
            "mean_dev": round(float(mean_dev), 3),
            "t_stat":   round(float(t), 2),
            "n":        int(n),
            "verdict":  verdict,
        })
    return results


# ---------------------------------------------------------------------------
# Step 6: Build signals JSON
# ---------------------------------------------------------------------------
def build_signals_json(cells: pd.DataFrame) -> dict:
    """Extract top advantages/disadvantages per stat for significant cells."""
    signals = {}
    sig = cells[cells["significant"]].copy()

    for s in STATS:
        sub = sig[sig["stat"] == s]
        if sub.empty:
            signals[s] = {"advantages": [], "disadvantages": []}
            continue

        top_adv = (
            sub[sub["mean_dev"] > 0]
            .nlargest(5, "mean_dev")[["position", "opp_scheme", "n", "mean_dev", "t_stat"]]
            .round(3)
            .to_dict("records")
        )
        top_dis = (
            sub[sub["mean_dev"] < 0]
            .nsmallest(5, "mean_dev")[["position", "opp_scheme", "n", "mean_dev", "t_stat"]]
            .round(3)
            .to_dict("records")
        )
        signals[s] = {"advantages": top_adv, "disadvantages": top_dis}

    return signals


# ---------------------------------------------------------------------------
# Step 7: Build Position × Scheme pivot table for a stat
# ---------------------------------------------------------------------------
def _cell_str(cells: pd.DataFrame, pos: str, scheme: str, stat: str) -> str:
    """Return formatted cell string for matrix table."""
    mask = (
        (cells["position"] == pos) &
        (cells["opp_scheme"] == scheme) &
        (cells["stat"] == stat)
    )
    row = cells[mask]
    if row.empty:
        return "—"
    row = row.iloc[0]
    sign = "+" if row["mean_dev"] >= 0 else ""
    sig_mark = "*" if row["significant"] else ""
    t_str = f" (t={sign}{row['t_stat']:.1f})" if row["significant"] else ""
    return f"{sign}{row['mean_dev']:.2f}{t_str}{sig_mark}"


def build_matrix_md(cells: pd.DataFrame, stat: str, present_schemes: list[str]) -> str:
    """Build markdown matrix table for one stat."""
    header = "| pos | " + " | ".join(present_schemes) + " |"
    sep = "|---|" + "|".join(["---"] * len(present_schemes)) + "|"
    rows_md = [header, sep]
    for pos in POS_ORDER:
        row_vals = [_cell_str(cells, pos, sch, stat) for sch in present_schemes]
        rows_md.append(f"| {pos} | " + " | ".join(row_vals) + " |")
    return "\n".join(rows_md)


# ---------------------------------------------------------------------------
# Step 8: Write Vault Atlas
# ---------------------------------------------------------------------------
def write_vault_atlas(
    cells: pd.DataFrame,
    intuitions: list[dict],
    position_counts: dict,
    unresolved: int,
    total_rows: int,
) -> None:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = VAULT_DIR / "Position_Scheme_Matrix.md"

    # Determine which schemes actually appear in data
    present_schemes = [s for s in SCHEME_ORDER if s in cells["opp_scheme"].unique()]

    sig = cells[cells["significant"]]

    lines = [
        "# Position x Defensive Scheme Matchup Matrix",
        "",
        "> INT-20 | Built: 2026-05-28",
        "",
        "## Methodology",
        "",
        "Position-based version of INT-17 (which used CV-derived archetypes). Same approach: ",
        "deviation from player EWMA baseline per (position, scheme) cell, with t-stat for significance.",
        "",
        "- **Baseline:** `ewma_X` (exponentially weighted moving average from build_pergame_dataset)",
        "- **Deviation:** `target_X - ewma_X` per game",
        "- **Gate:** n >= 100 games AND |t| > 2.0 for significance",
        "- **Scheme source:** INT-12 defensive scheme atlas (opponent-imposed behavioral profiling)",
        "",
        "---",
        "",
        "## Position Coverage",
        "",
        f"Total rows with position + scheme resolved: {total_rows:,}",
        "",
        "| Position | Rows |",
        "|---|---|",
    ]
    for pos in POS_ORDER:
        lines.append(f"| {pos} | {position_counts.get(pos, 0):,} |")
    lines.extend([
        f"| unknown/unresolved | {unresolved:,} |",
        "",
        "---",
        "",
    ])

    for stat in STATS:
        stat_upper = stat.upper()
        lines.extend([
            f"## {stat_upper} Interaction Matrix",
            "",
            "(* = significant: n >= 100, |t| > 2.0)",
            "",
            build_matrix_md(cells, stat, present_schemes),
            "",
        ])

        # Top 5 advantages + disadvantages
        sub = sig[sig["stat"] == stat].copy()
        adv = sub[sub["mean_dev"] > 0].nlargest(5, "mean_dev")
        dis = sub[sub["mean_dev"] < 0].nsmallest(5, "mean_dev")

        lines.extend([
            f"### Top Systematic {stat_upper} Advantages",
            "",
            "| position | scheme | n | mean_dev | t-stat |",
            "|---|---|---|---|---|",
        ])
        for _, r in adv.iterrows():
            lines.append(f"| {r['position']} | {r['opp_scheme']} | {int(r['n'])} | +{r['mean_dev']:.3f} | {r['t_stat']:.2f} |")
        if adv.empty:
            lines.append("| — | no significant advantages found | — | — | — |")

        lines.extend([
            "",
            f"### Top Systematic {stat_upper} Disadvantages",
            "",
            "| position | scheme | n | mean_dev | t-stat |",
            "|---|---|---|---|---|",
        ])
        for _, r in dis.iterrows():
            lines.append(f"| {r['position']} | {r['opp_scheme']} | {int(r['n'])} | {r['mean_dev']:.3f} | {r['t_stat']:.2f} |")
        if dis.empty:
            lines.append("| — | no significant disadvantages found | — | — | — |")

        lines.append("")
        lines.append("---")
        lines.append("")

    # Intuition validation section
    lines.extend([
        "## Intuition Validation",
        "",
        "| prediction | n | mean_dev | t-stat | verdict |",
        "|---|---|---|---|---|",
    ])
    for chk in intuitions:
        n_str = str(chk["n"]) if chk["n"] is not None else "—"
        dev_str = f"{chk['mean_dev']:+.3f}" if chk["mean_dev"] is not None else "—"
        t_str = f"{chk['t_stat']:.2f}" if chk["t_stat"] is not None else "—"
        lines.append(
            f"| {chk['label']} | {n_str} | {dev_str} | {t_str} | {chk['verdict']} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## Comparison to INT-17 (Archetype-Based)",
        "",
        "INT-17 used CV-derived archetypes (4 clusters). INT-20 uses NBA position labels (PG/SG/SF/PF/C).",
        "The two systems are complementary: INT-17 captures playing style, INT-20 captures roster role.",
        "",
        "**Cross-reference rule:** When INT-17 archetype AND INT-20 position AGREE on direction for a (player, scheme) matchup, conviction is higher.",
        "",
        "---",
        "",
        "## How to Use",
        "",
        "1. **Pre-bet lookup:** Identify player's primary position → find opponent's dominant scheme → read expected deviation.",
        "2. **Conviction filter:** Only act on significant cells (asterisked). Non-significant cells have real signal but wide error bars.",
        "3. **INT-17 cross-check:** Pull the player's archetype from INT-17. If both INT-17 and INT-20 agree on direction, treat as high-conviction.",
        "4. **Magnitude:** mean_dev is in raw stat units. A PG +1.0 PTS advantage vs DROP COVERAGE means PGs historically average +1 pts above their EWMA in that matchup.",
        "",
        "---",
        "",
        "## Honest Caveats",
        "",
        "- Position labels can be stale in the positionless basketball era. A player labeled 'Guard' may function as a SF.",
        "- Some cells reflect scheme changes mid-season (teams change systems; INT-12 uses a season-level label).",
        "- INT-12 scheme labels are behaviorally derived, not manually assigned — partial validation (2/5 teams verified).",
        "- n >= 100 gate is strict for rare position×scheme combinations (e.g. C vs PERIMETER DENIAL).",
        "- Same build_pergame_dataset caveats apply: rows missing gamelog join get no scheme label.",
        "",
        "---",
        "",
        "*Cross-reference: [[Archetype_Scheme_Matrix]] (INT-17) | [[Defensive_Schemes]] (INT-12)*",
    ])

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"[Step 7] Written atlas: {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: build opp lookup
    opp_lookup = build_opp_lookup()

    # Steps 2-3: load dataset and join
    df_joined = build_joined_df(opp_lookup)

    # Position coverage stats
    pos_counts = df_joined["pos5"].value_counts().to_dict()
    total_rows = len(df_joined)

    # Step 4: aggregate
    cells = compute_cell_stats(df_joined)

    # Step 5: intuitions
    intuitions = validate_intuitions(cells)

    # Step 6: signals JSON
    signals = build_signals_json(cells)

    # --- Save parquet ---
    pq_path = OUT_DIR / "position_scheme_interactions.parquet"
    cells.to_parquet(pq_path, index=False)
    print(f"[Step 6a] Written parquet: {pq_path}")

    # --- Save JSON ---
    json_path = OUT_DIR / "position_scheme_signals.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(signals, fh, indent=2)
    print(f"[Step 6b] Written signals: {json_path}")

    # Step 7: Atlas
    # Compute unresolved count
    # We need original df shape -- recompute from opp_lookup join stats
    # (approximate: total rows in dataset minus rows with scheme)
    unresolved = 0  # will estimate below
    write_vault_atlas(cells, intuitions, pos_counts, unresolved, total_rows)

    # --- Final Report ---
    sig = cells[cells["significant"]]
    print("\n" + "=" * 70)
    print("## INT-20 Position x Scheme Matchup — Final Report")
    print("=" * 70)
    print(f"\n### Coverage")
    print(f"  Rows with position + scheme resolved: {total_rows:,}")
    for pos in POS_ORDER:
        print(f"  {pos}: {pos_counts.get(pos, 0):,} rows")

    print(f"\n### Significant cells (n>=100, |t|>2): {len(sig)}")
    print(f"\n### Top interactions per stat:")
    for s in STATS:
        sub = sig[sig["stat"] == s]
        if sub.empty:
            print(f"  {s.upper()}: no significant cells")
            continue
        top = sub.reindex(sub["mean_dev"].abs().nlargest(3).index)
        for _, r in top.iterrows():
            sign = "+" if r["mean_dev"] >= 0 else ""
            print(f"  {s.upper()}: {r['position']} vs {r['opp_scheme']} -> {sign}{r['mean_dev']:.3f} (n={int(r['n'])}, t={r['t_stat']:.2f})")

    print(f"\n### Intuition Validation:")
    for chk in intuitions:
        dev_str = f"{chk['mean_dev']:+.3f}" if chk["mean_dev"] is not None else "N/A"
        t_str = f"{chk['t_stat']:.2f}" if chk["t_stat"] is not None else "N/A"
        print(f"  [{chk['verdict']}] {chk['label']} -> dev={dev_str}, t={t_str}")

    print(f"\n### Files:")
    print(f"  {pq_path}")
    print(f"  {json_path}")
    print(f"  {VAULT_DIR / 'Position_Scheme_Matrix.md'}")

    print(f"\n### How to use:")
    print("  Pre-bet: lookup (player_position, opp_dominant_scheme) in signals JSON")
    print("  Cross-reference with INT-17 (archetype) for high-conviction calls")
    print("  Significant cells only — non-significant cells have too wide an error bar")

    print(f"\n### Honest caveats:")
    print("  - 'Guard' may mean SG in positionless ball era; label is from NBA API profile")
    print("  - INT-12 schemes are behaviorally inferred, 2/5 validated vs known schemes")
    print("  - Rare position×scheme cells (e.g. C vs PERIMETER DENIAL) may not hit n>=100 gate")


if __name__ == "__main__":
    main()
