"""domains.mlb.postmortem — Per-game descriptive postmortem for MLB.

LEAK TIER: DESCRIPTIVE / KNOWLEDGE
    All fields use REALIZED game outcomes (final scores, actual inning-by-inning
    runs). This module describes what happened, it does NOT predict future games.
    Using decided_by labels or big_inning_share as a pre-game predictive signal
    would constitute a leak; that is explicitly out of scope here.
    A leak-free as-of companion module is a separate future work item.

Joins:
    data/domains/mlb/games.parquet    — event_id, home_runs, away_runs, target_home_win
    data/domains/mlb/pitchers.parquet — home_innings, away_innings, home_sp_name, away_sp_name

Output:
    data/domains/mlb/postmortem.parquet

decided_by label definitions (applied in priority order):
    BLOWOUT       : margin >= 7
    SP_DUEL       : total_runs <= 4 AND margin <= 2
    BIG_INNING    : one team's biggest_inning_runs >= 50% of that team's total runs
                    (applied to EITHER team; not BLOWOUT)
    LATE_COMEBACK : winner had fewer runs after 6 innings but won the game
    BULLPEN_SWING : |home_runs_7_9 - away_runs_7_9| >= 3 (and not above)
    ROUTINE       : everything else

sp_hand_matchup values: LL, LR, RL, RR, MIXED (when either SP absent/unknown)

CLI (python -m domains.mlb.postmortem):
    Prints decided_by distribution, mean big_inning_share, coverage.

INVARIANTS: <=300 LOC; only reads data/domains/mlb/; no src/kernel edits.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pandas as pd

from domains.mlb.linescore import innings_shape


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[2]
_MLB_DATA = _ROOT / "data" / "domains" / "mlb"
_GAMES_PATH = _MLB_DATA / "games.parquet"
_PITCHERS_PATH = _MLB_DATA / "pitchers.parquet"
_OUT_PATH = _MLB_DATA / "postmortem.parquet"

_EXPECTED_COLS = [
    "event_id",
    "margin",
    "total_runs",
    "home_big_inning_share",
    "away_big_inning_share",
    "home_scoreless_frame_rate",
    "away_scoreless_frame_rate",
    "home_runs_1_3",
    "home_runs_4_6",
    "home_runs_7_9",
    "away_runs_1_3",
    "away_runs_4_6",
    "away_runs_7_9",
    "decided_by",
    "home_sp_hand",
    "away_sp_hand",
    "sp_hand_matchup",
]


# ---------------------------------------------------------------------------
# SP handedness helper
# ---------------------------------------------------------------------------

def _extract_hand(sp_name: Optional[str]) -> str:
    """Return 'L', 'R', or 'U' (unknown) from SP name like 'JBECKETT-R'."""
    if not isinstance(sp_name, str) or not sp_name.strip():
        return "U"
    parts = sp_name.rsplit("-", 1)
    if len(parts) == 2 and parts[1] in ("L", "R"):
        return parts[1]
    return "U"


def _hand_matchup(home_hand: str, away_hand: str) -> str:
    """Return matchup string: LL/LR/RL/RR or MIXED if either is unknown."""
    if home_hand in ("L", "R") and away_hand in ("L", "R"):
        return home_hand + away_hand
    return "MIXED"


# ---------------------------------------------------------------------------
# decided_by labeler
# ---------------------------------------------------------------------------

def _label_game(
    home_runs: int,
    away_runs: int,
    h: dict,
    a: dict,
) -> str:
    """Assign the decided_by label for one game.

    Parameters
    ----------
    home_runs, away_runs : final run totals
    h : innings_shape dict for home team
    a : innings_shape dict for away team
    """
    margin = abs(home_runs - away_runs)
    total = home_runs + away_runs

    # --- BLOWOUT ---
    if margin >= 7:
        return "BLOWOUT"

    # --- SP_DUEL ---
    if total <= 4 and margin <= 2:
        return "SP_DUEL"

    # --- BIG_INNING ---
    # Applies if EITHER team's biggest inning >= 50% of their total runs
    home_big_share = h["big_inning_share"]   # 0..1; 0 if total==0
    away_big_share = a["big_inning_share"]
    if home_big_share >= 0.50 or away_big_share >= 0.50:
        return "BIG_INNING"

    # --- LATE_COMEBACK ---
    # Winner had fewer runs through 6 innings but won outright
    home_through_6 = h["runs_1_3"] + h["runs_4_6"]
    away_through_6 = a["runs_1_3"] + a["runs_4_6"]
    winner_is_home = home_runs > away_runs
    if winner_is_home and home_through_6 < away_through_6:
        return "LATE_COMEBACK"
    if not winner_is_home and away_through_6 < home_through_6:
        return "LATE_COMEBACK"

    # --- BULLPEN_SWING ---
    late_diff = abs(h["runs_7_9"] - a["runs_7_9"])
    if late_diff >= 3:
        return "BULLPEN_SWING"

    return "ROUTINE"


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def build_postmortem(
    games_path: Optional[str] = None,
    pitchers_path: Optional[str] = None,
    out_path: Optional[str] = None,
) -> pd.DataFrame:
    """Build postmortem records and write to out_path.

    Returns the resulting DataFrame (index-reset).
    """
    gp = Path(games_path) if games_path else _GAMES_PATH
    pp = Path(pitchers_path) if pitchers_path else _PITCHERS_PATH
    op = Path(out_path) if out_path else _OUT_PATH

    games = pd.read_parquet(gp)
    pitchers = pd.read_parquet(pp)

    # Merge on event_id; inner join (both must be present)
    df = games.merge(
        pitchers[["event_id", "home_innings", "away_innings",
                  "home_sp_name", "away_sp_name"]],
        on="event_id",
        how="inner",
    )

    records = []
    for _, row in df.iterrows():
        home_runs = int(row["home_runs"])
        away_runs = int(row["away_runs"])

        h = innings_shape(row["home_innings"])
        a = innings_shape(row["away_innings"])

        home_hand = _extract_hand(row.get("home_sp_name"))
        away_hand = _extract_hand(row.get("away_sp_name"))

        decided = _label_game(home_runs, away_runs, h, a)

        records.append({
            "event_id": row["event_id"],
            "margin": abs(home_runs - away_runs),
            "total_runs": home_runs + away_runs,
            "home_big_inning_share": round(h["big_inning_share"], 4),
            "away_big_inning_share": round(a["big_inning_share"], 4),
            "home_scoreless_frame_rate": round(h["scoreless_frame_rate"], 4),
            "away_scoreless_frame_rate": round(a["scoreless_frame_rate"], 4),
            "home_runs_1_3": h["runs_1_3"],
            "home_runs_4_6": h["runs_4_6"],
            "home_runs_7_9": h["runs_7_9"],
            "away_runs_1_3": a["runs_1_3"],
            "away_runs_4_6": a["runs_4_6"],
            "away_runs_7_9": a["runs_7_9"],
            "decided_by": decided,
            "home_sp_hand": home_hand,
            "away_sp_hand": away_hand,
            "sp_hand_matchup": _hand_matchup(home_hand, away_hand),
        })

    out = pd.DataFrame(records, columns=_EXPECTED_COLS)
    op.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(op, index=False)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    """Print decided_by distribution, mean big_inning_share, coverage."""
    gp = _GAMES_PATH
    if not gp.exists():
        print(f"ERROR: games corpus not found at {gp}", file=sys.stderr)
        sys.exit(1)
    if not _PITCHERS_PATH.exists():
        print(f"ERROR: pitchers corpus not found at {_PITCHERS_PATH}", file=sys.stderr)
        sys.exit(1)

    total_games = len(pd.read_parquet(gp))

    print("Building postmortem …", flush=True)
    df = build_postmortem()
    processed = len(df)

    print(f"\n=== MLB Postmortem — {processed} / {total_games} games ===\n")

    print("decided_by distribution:")
    dist = df["decided_by"].value_counts()
    for label, count in dist.items():
        pct = 100.0 * count / processed if processed > 0 else 0.0
        print(f"  {label:<16s}: {count:6d}  ({pct:.1f}%)")

    mean_big = (
        (df["home_big_inning_share"] + df["away_big_inning_share"]) / 2
    ).mean()
    print(f"\nMean big_inning_share (home+away avg): {mean_big:.4f}")

    cov_pct = 100.0 * processed / total_games if total_games > 0 else 0.0
    print(f"\nCoverage: {processed} / {total_games} ({cov_pct:.1f}%)")
    print(f"\nOutput written to: {_OUT_PATH}")


if __name__ == "__main__":
    _cli()
