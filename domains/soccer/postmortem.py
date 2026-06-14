# LEAK TIER: DESCRIPTIVE/KNOWLEDGE — realized match stats only; not a signal.
# Builds one post-mortem record per match explaining WHY the result went as it did.
# Source: data/domains/soccer/match_stats.parquet + matches.parquet
# Output: data/domains/soccer/postmortem.parquet
"""Soccer per-match post-mortem: deterministic decided_by rule cascade."""
from __future__ import annotations

import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
_STATS_PATH = ROOT / "data" / "domains" / "soccer" / "match_stats.parquet"
_MATCHES_PATH = ROOT / "data" / "domains" / "soccer" / "matches.parquet"
_OUTPUT_PATH = ROOT / "data" / "domains" / "soccer" / "postmortem.parquet"

# Rule names in cascade priority order
RULES = [
    "RED_CARD_SWING",
    "FINISHING_VARIANCE",
    "DOMINANT_BUT_DREW",
    "HT_COLLAPSE",
    "HT_COMEBACK",
    "TERRITORIAL_CONTROL",
    "ROUTINE",
]

# Thresholds
_FINISHING_RESIDUAL_THRESHOLD = 1.5   # goals vs 0.32*SoT
_SOT_DIFF_DRAW_THRESHOLD = 2          # SoT gap for dominant-but-drew
_TERRITORY_THRESHOLD = 5              # corners+SoT gap for territorial control


def _compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived columns used by the rule cascade."""
    df = df.copy()

    # Finishing residual: goals vs naive xG proxy (0.32 per SoT)
    df["finishing_residual_home"] = df["fthg"] - 0.32 * df["home_sot"].fillna(0)
    df["finishing_residual_away"] = df["ftag"] - 0.32 * df["away_sot"].fillna(0)

    # SoT differential (home minus away)
    df["sot_diff"] = df["home_sot"].fillna(0) - df["away_sot"].fillna(0)

    # Red card flags
    df["home_red_f"] = df["home_red"].fillna(0)
    df["away_red_f"] = df["away_red"].fillna(0)
    df["red_flags"] = (df["home_red_f"] > 0) | (df["away_red_f"] > 0)

    # HT flip: HT leader failed to win at FT
    # htr H/D/A; ftr H/D/A
    htr_ok = df["htr"].notna()
    ftr_ok = df["ftr"].notna()
    # HT_COLLAPSE: had a HT lead (H or A) but didn't convert to a FT win
    ht_lead_home = (df["htr"] == "H") & (df["ftr"] != "H")
    ht_lead_away = (df["htr"] == "A") & (df["ftr"] != "A")
    df["ht_flip"] = htr_ok & ftr_ok & (ht_lead_home | ht_lead_away)

    # HT COMEBACK sub-flag: from behind at HT to winning at FT
    ht_comeback_home = (df["htr"] == "A") & (df["ftr"] == "H")
    ht_comeback_away = (df["htr"] == "H") & (df["ftr"] == "A")
    df["ht_comeback"] = htr_ok & ftr_ok & (ht_comeback_home | ht_comeback_away)

    # Territorial composite (corners + SoT)
    df["home_territory"] = df["home_corners"].fillna(0) + df["home_sot"].fillna(0)
    df["away_territory"] = df["away_corners"].fillna(0) + df["away_sot"].fillna(0)
    df["territory_diff"] = df["home_territory"] - df["away_territory"]

    return df


def _red_card_swing(row: pd.Series) -> bool:
    """Red card occurred AND the man-up side (fewer reds) won or drew."""
    if not row["red_flags"]:
        return False
    hr, ar = row["home_red_f"], row["away_red_f"]
    ftr = row["ftr"]
    # Home gets red(s), away is man-up → away wins or draws
    if ar < hr and ftr in ("A", "D"):
        return True
    # Away gets red(s), home is man-up → home wins or draws
    if hr < ar and ftr in ("H", "D"):
        return True
    # Both sides have reds but equal → no clear swing
    return False


def _finishing_variance(row: pd.Series) -> bool:
    return (
        abs(row["finishing_residual_home"]) > _FINISHING_RESIDUAL_THRESHOLD
        or abs(row["finishing_residual_away"]) > _FINISHING_RESIDUAL_THRESHOLD
    )


def _dominant_but_drew(row: pd.Series) -> bool:
    return row["ftr"] == "D" and abs(row["sot_diff"]) > _SOT_DIFF_DRAW_THRESHOLD


def _ht_collapse(row: pd.Series) -> bool:
    """HT leader fails to win (but not a full comeback — covers draws from HT lead)."""
    if row["ht_comeback"]:
        return False  # comeback is its own rule
    return bool(row["ht_flip"])


def _ht_comeback(row: pd.Series) -> bool:
    return bool(row["ht_comeback"])


def _territorial_control(row: pd.Series) -> bool:
    td = row["territory_diff"]
    ftr = row["ftr"]
    return (td >= _TERRITORY_THRESHOLD and ftr == "H") or (
        td <= -_TERRITORY_THRESHOLD and ftr == "A"
    )


_RULE_FNS = [
    ("RED_CARD_SWING", _red_card_swing),
    ("FINISHING_VARIANCE", _finishing_variance),
    ("DOMINANT_BUT_DREW", _dominant_but_drew),
    ("HT_COLLAPSE", _ht_collapse),
    ("HT_COMEBACK", _ht_comeback),
    ("TERRITORIAL_CONTROL", _territorial_control),
    ("ROUTINE", lambda _: True),  # always fires
]


def _apply_cascade(df: pd.DataFrame) -> pd.Series:
    """Vectorised-friendly row-by-row cascade. Returns a Series of decided_by strings."""
    labels = pd.Series("ROUTINE", index=df.index, dtype="object")
    # Apply in reverse priority so highest-priority rule overwrites
    for name, fn in reversed(_RULE_FNS):
        mask = df.apply(fn, axis=1)
        labels[mask] = name
    return labels


def build_postmortem(
    path_stats: str | Path = _STATS_PATH,
    path_matches: str | Path = _MATCHES_PATH,
    output_path: str | Path = _OUTPUT_PATH,
) -> pd.DataFrame:
    """Load, compute, and write the postmortem parquet. Returns the DataFrame."""
    stats = pd.read_parquet(path_stats)
    matches = pd.read_parquet(path_matches)[
        ["event_id", "fthg", "ftag", "ftr", "season"]
    ]

    # Merge on event_id (left join to keep all stats rows)
    df = stats.merge(matches, on="event_id", how="left")

    # Ensure numeric
    for col in ["home_sot", "away_sot", "home_corners", "away_corners",
                "home_red", "away_red", "fthg", "ftag"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df = _compute_features(df)
    df["decided_by"] = _apply_cascade(df)

    out_cols = [
        "event_id", "date", "fthg", "ftag", "ftr",
        "decided_by",
        "finishing_residual_home", "finishing_residual_away",
        "sot_diff", "red_flags", "ht_flip",
    ]
    result = df[out_cols].copy()

    os.makedirs(Path(output_path).parent, exist_ok=True)
    result.to_parquet(output_path, index=False)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cli() -> None:
    pm = build_postmortem()
    n = len(pm)
    print(f"\n=== Soccer Post-Mortem Distribution ({n:,} matches) ===\n")

    dist = pm["decided_by"].value_counts()
    for rule in RULES:
        count = dist.get(rule, 0)
        print(f"  {rule:<25s} {count:>6,}  ({100*count/n:.1f}%)")

    # Key rates for sanity-check vs architect numbers
    red_rate = pm["red_flags"].mean()
    ht_flip_rate = pm["ht_flip"].mean()
    draws = pm[pm["ftr"] == "D"]
    dom_drew = (
        (draws["sot_diff"].abs() > _SOT_DIFF_DRAW_THRESHOLD).mean()
        if len(draws) else float("nan")
    )

    print(f"\n--- Sanity-check rates ---")
    print(f"  Red-card matches        : {100*red_rate:.1f}%  (architect ~16%)")
    print(f"  HT-leader failed to win : {100*ht_flip_rate:.1f}%  (architect ~22%)")
    print(f"  Dominant-but-drew       : {100*dom_drew:.1f}% of draws  (architect ~24%)")

    print("\nKNOWLEDGE LAYER — descriptive realized stats only; not a predictive signal.")


if __name__ == "__main__":
    _cli()
