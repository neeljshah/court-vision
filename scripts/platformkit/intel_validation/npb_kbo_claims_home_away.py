"""NPB + KBO home_win_pct vs away_win_pct split -- sibling module of
npb_kbo_claims.py (kept separate to hold the parent file under the 300-LOC
rail, same wnba_claims.py/_ext.py/_ext2.py 3-way-split precedent).

Reuses npb_kbo_claims.py's rank_desc()/base_caveats() helpers over the SAME
per-team snapshot parquet that module already built -- the third dimension
of the lane's 3-per-league set (win_pct, run_diff_per_game live in the
parent module; this module is the "home vs away" split).

Both halves (home_win_pct, away_win_pct) are the SAME team's win rate
restricted to one venue role -- pairing them surfaces home-field advantage
size per team, not two independent dimensions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.platformkit.intel_validation.npb_kbo_claims import (
    MIN_N_GAMES,
    _rel,
    base_caveats,
    rank_desc,
)


def _one_side_claim(
    league: str, snapshot_path: Path, as_of_iso: str, n_considered: int, table: pd.DataFrame,
    *, value_col: str, n_col: str, side_label: str,
) -> dict[str, Any]:
    ranking, _n_considered, n_excluded = rank_desc(
        table, value_col=value_col, n_col=n_col, min_n=MIN_N_GAMES,
    )
    formula = (
        "home_wins / home_decided_games" if side_label == "home"
        else "away_wins / away_decided_games"
    )
    return {
        "claim_id": f"{league.lower()}_team_{value_col}_full_asof_{as_of_iso}",
        "kind": "ranking",
        "question": (
            f"Which {league} teams have the best {side_label} win percentage "
            f"(full population above floor, as-of {as_of_iso})?"
        ),
        "criteria": {
            "metric": value_col,
            "formula": formula,
            "window": f"asof_{as_of_iso}_{league.lower()}",
            "window_spec": {"kind": "season", "season": None, "n": None, "order_by": None},
            "min_sample": {n_col: MIN_N_GAMES},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "team",
        },
        "ranking": ranking,
        "source_files": [_rel(snapshot_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            f"{value_col} = {side_label}_wins / {side_label}_decided_games (ties excluded "
            f"from the denominator), the SAME team's win rate restricted to its {side_label} "
            f"venue role, from {_rel(snapshot_path)} (built over the full "
            f"data/domains/{league.lower()}/{league.lower()}_results.parquet game-level "
            "corpus).",
            f"min_sample floor uses the team's {side_label}-role game count ({n_col}), "
            f"not overall games -- a team's own {side_label} sample can differ slightly "
            "from its overall n_games (roughly half, per a balanced schedule).",
            "Paired with its counterpart (home_win_pct vs away_win_pct) this dimension "
            "surfaces home-field advantage size per team -- both halves of the SAME split, "
            "not two independent dimensions.",
            *base_caveats(league, as_of_iso, value_col),
        ],
    }


def build_home_away_split_claims(
    league: str, snapshot_path: Path, as_of_iso: str, n_considered: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    table = pd.read_parquet(snapshot_path)
    table["home_win_pct"] = table["home_wins"] / table["home_decided_games"]
    table["away_win_pct"] = table["away_wins"] / table["away_decided_games"]

    home_claim = _one_side_claim(
        league, snapshot_path, as_of_iso, n_considered, table,
        value_col="home_win_pct", n_col="home_decided_games", side_label="home",
    )
    away_claim = _one_side_claim(
        league, snapshot_path, as_of_iso, n_considered, table,
        value_col="away_win_pct", n_col="away_decided_games", side_label="away",
    )
    return home_claim, away_claim
