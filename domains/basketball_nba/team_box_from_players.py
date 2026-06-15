"""team_box_from_players.py — aggregate player-game rows to team-game box stats.

Reads the gitignored ``data/domains/basketball_nba/player_boxscores.parquet``
(27 k+ player-game rows) and sums numeric box stats per (game_id, home/away side)
to produce one row PER GAME with ``home_<stat>`` / ``away_<stat>`` paired columns
in the shape ``scripts/platformkit/brain_keystats`` expects.

HONEST BANNER: descriptive realized box stats aggregated from player rows.
NOT a leak-free signal and NOT a bet. Must be joined as-of before any model
use. Markets are efficient; no edge claimed.

CLI: ``python -m domains.basketball_nba.team_box_from_players``
     Writes ``data/domains/basketball_nba/espn_boxscores.parquet``; idempotent.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Stats to SUM per team-game side; order determines column order in output.
_SUM_STATS = [
    "pts", "reb", "oreb", "dreb", "ast", "stl", "blk",
    "tov", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pf",
]

_DEFAULT_PLAYERS_PQ = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_DEFAULT_OUT_PQ = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "espn_boxscores.parquet"

_BANNER = (
    "Descriptive realized box stats; NOT a leak-free signal; "
    "must be joined as-of before any model use; markets efficient; no edge."
)


def aggregate_team_box(players_df):  # noqa: ANN001
    """Pure aggregation: player DataFrame -> team-game wide DataFrame.

    Accepts a pandas DataFrame with at least the columns:
        game_id, date, team, opp, is_home (0/1 or bool),
        pts, reb, oreb, dreb, ast, stl, blk, tov,
        fgm, fga, fg3m, fg3a, ftm, fta, pf.

    Returns a DataFrame with one row per game:
        event_id, date, home_abbr, away_abbr, home_score, away_score,
        home_<stat>, away_<stat>  for each stat in _SUM_STATS.

    No network access, no I/O. Deterministic. Pure stdlib + pandas (lazy import).
    """
    import pandas as pd  # noqa: PLC0415

    df = players_df.copy()

    # Normalise is_home to int (0/1) — may arrive as bool or float.
    df["is_home"] = df["is_home"].astype(float).astype(int)

    # Summable stat columns actually present.
    sum_cols = [s for s in _SUM_STATS if s in df.columns]

    # Group by (game_id, is_home) and sum stats; pick one date+team per group.
    meta = df.groupby(["game_id", "is_home"], as_index=False).agg(
        date=("date", "first"),
        team=("team", "first"),
        **{s: (s, "sum") for s in sum_cols},
    )

    # Split into home and away halves.
    home = meta[meta["is_home"] == 1].copy()
    away = meta[meta["is_home"] == 0].copy()

    # Merge on game_id — inner join drops games with only one side recorded.
    merged = home.merge(away, on="game_id", suffixes=("_h", "_a"))

    # Build output frame with canonical column names.
    out: dict = {
        "event_id": merged["game_id"].values,
        "date": merged["date_h"].values,
        "home_abbr": merged["team_h"].values,
        "away_abbr": merged["team_a"].values,
    }

    # Score columns (pts sum = score).
    out["home_score"] = merged["pts_h"].values if "pts_h" in merged.columns else None
    out["away_score"] = merged["pts_a"].values if "pts_a" in merged.columns else None

    # Paired stat columns.
    for s in sum_cols:
        h_col = f"{s}_h"
        a_col = f"{s}_a"
        out[f"home_{s}"] = merged[h_col].values if h_col in merged.columns else None
        out[f"away_{s}"] = merged[a_col].values if a_col in merged.columns else None

    result = pd.DataFrame(out)
    result = result.sort_values("event_id").reset_index(drop=True)
    return result


def build_team_box(
    players_parquet: Optional[Path] = None,
    out_path: Optional[Path] = None,
) -> Path:
    """Load player parquet, aggregate to team-game box, write parquet.

    Returns the path written.  Idempotent — safe to re-run.
    """
    import pandas as pd  # noqa: PLC0415

    src = Path(players_parquet) if players_parquet else _DEFAULT_PLAYERS_PQ
    dst = Path(out_path) if out_path else _DEFAULT_OUT_PQ

    players = pd.read_parquet(src)
    result = aggregate_team_box(players)
    dst.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(dst, index=False)
    return dst


def _main(argv=None) -> int:  # noqa: ANN001
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    dst = build_team_box()
    import pandas as pd  # noqa: PLC0415
    n = len(pd.read_parquet(dst))
    print(f"team_box_from_players: wrote {n} rows -> {dst}")
    print(f"NOTE: {_BANNER}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
