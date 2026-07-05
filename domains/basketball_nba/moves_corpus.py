"""domains.basketball_nba.moves_corpus -- rebuild the historical player-team
moves corpus across ALL available seasons (lane bbref-ingest, wave-52).

Combines the existing verified corpus (data/cache/bbref_advanced_extended
.parquet, 2 seasons: 2024-25/2025-26) with any newly-backfilled seasons
(data/cache/bbref_backfill/advanced_*.parquet, from bbref_backfill.py) and
applies the SAME STRICT off-season-move rule pre-registered in
docs/research/intel-layer/fit_validity_gate_prereg.json verbatim:

    a player has a "clean single-real-team full season" in season N iff (a)
    their team code that season is one of the 30 real 3-letter bbref codes
    (never a 2TM/3TM/4TM multi-team-stint marker), AND (b) they appear
    EXACTLY ONCE in that season's rows (a second appearance under a real
    code, alongside a 2TM/3TM aggregate row, is bbref's own signature of a
    mid-season trade -- excluding it is what makes H0/H1 comparable, see the
    prereg's gate_comparability rail).

    a STRICT MOVE between adjacent seasons N and N+1 is a player with a
    clean single-real-team season in BOTH N and N+1, where the team code
    differs.

This rule is REPRODUCED exactly (not paraphrased) from
FIT_VALIDITY_GATE_PREREG_2026-07-05.md section 2 and verified this session
to reproduce the pre-registration's own counts on the 2-season corpus
(488 clean 2024-25 / 510 clean 2025-26 / 350 clean-both / 96 strict moves)
byte-for-byte before being applied to any additional season. THE RULE ITSELF
IS NEVER ALTERED by this module -- only the season coverage grows.

PROVENANCE: reads bbref_advanced_extended.parquet (existing, untouched) +
data/cache/bbref_backfill/advanced_*.parquet (new, tagged
source=bbref_backfill_2026-07-05 by bbref_backfill.py). Writes ONLY to
data/cache/bbref_backfill/moves_corpus.parquet -- never back to
bbref_advanced_extended.parquet.

CLI:
    python -m domains.basketball_nba.moves_corpus
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_EXISTING_SRC = REPO_ROOT / "data" / "cache" / "bbref_advanced_extended.parquet"
_BACKFILL_DIR = REPO_ROOT / "data" / "cache" / "bbref_backfill"
_OUT_PATH = _BACKFILL_DIR / "moves_corpus.parquet"

# The 30 real bbref 3-letter team codes, verbatim from the prereg's own
# corpus definition -- a team code NOT in this set (2TM/3TM/4TM/empty) marks
# a mid-season multi-team stint and must be excluded, never counted as a
# clean single-team season.
REAL_TEAM_CODES = frozenset({
    "ATL", "BOS", "BRK", "CHI", "CHO", "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHO", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
})


@dataclass
class MovesCorpusResult:
    seasons_used: list[str] = field(default_factory=list)
    clean_counts_per_season: dict[str, int] = field(default_factory=dict)
    moves_per_season_pair: dict[str, int] = field(default_factory=dict)
    n_moves_total: int = 0
    moves_df: pd.DataFrame = field(default_factory=pd.DataFrame)


def _load_all_available_seasons() -> pd.DataFrame:
    """Concat the existing verified corpus with any backfilled seasons.
    Column sets are aligned to the shared subset (player_name, team, season,
    season_year) -- backfilled rows carry player_id=NaN/unresolved (id
    resolution is out of scope for this lane, see bbref_backfill.py), which
    is fine because the strict-move rule never keys on player_id."""
    frames = []
    if _EXISTING_SRC.exists():
        frames.append(pd.read_parquet(_EXISTING_SRC))
    if _BACKFILL_DIR.is_dir():
        for p in sorted(_BACKFILL_DIR.glob("advanced_*.parquet")):
            frames.append(pd.read_parquet(p))
    if not frames:
        raise FileNotFoundError("no bbref advanced-stat sources found (neither existing nor backfilled)")
    combined = pd.concat(frames, ignore_index=True, sort=False)
    # A season may appear in BOTH the existing corpus and a backfill run (re-run
    # safety) -- de-dup on (player_name, season), preferring the EXISTING,
    # already-verified corpus's row when both exist (existing rows are listed
    # first in `frames`, so keep="first" is correct here).
    combined = combined.drop_duplicates(subset=["player_name", "season"], keep="first")
    return combined


def _clean_single_team_season(season_df: pd.DataFrame) -> pd.DataFrame:
    """Players with a clean single-real-team season: team code is real AND
    the player appears exactly once in this season's rows (verbatim rule,
    see module docstring)."""
    real_rows = season_df[season_df["team"].isin(REAL_TEAM_CODES)]
    counts = season_df["player_name"].value_counts()
    single_appearance = counts[counts == 1].index
    return real_rows[real_rows["player_name"].isin(single_appearance)]


def build_moves_corpus() -> MovesCorpusResult:
    df = _load_all_available_seasons()
    seasons = sorted(df["season"].dropna().unique().tolist())

    clean_by_season: dict[str, pd.DataFrame] = {}
    clean_counts: dict[str, int] = {}
    for s in seasons:
        season_df = df[df["season"] == s]
        clean = _clean_single_team_season(season_df)
        clean_by_season[s] = clean
        clean_counts[s] = int(clean["player_name"].nunique())

    all_moves: list[dict[str, Any]] = []
    moves_per_pair: dict[str, int] = {}
    for i in range(len(seasons) - 1):
        s_pre, s_post = seasons[i], seasons[i + 1]
        pre = clean_by_season[s_pre].set_index("player_name")
        post = clean_by_season[s_post].set_index("player_name")
        both = pre.index.intersection(post.index)
        pair_moves = 0
        for player in both:
            team_pre = pre.loc[player, "team"]
            team_post = post.loc[player, "team"]
            # a player could (rarely) have duplicate clean rows if source
            # dedup left a stray row; guard by taking the first if so
            if isinstance(team_pre, pd.Series):
                team_pre = team_pre.iloc[0]
            if isinstance(team_post, pd.Series):
                team_post = team_post.iloc[0]
            if team_pre == team_post:
                continue
            pair_moves += 1
            row_pre = pre.loc[player]
            row_post = post.loc[player]
            if isinstance(row_pre, pd.DataFrame):
                row_pre = row_pre.iloc[0]
            if isinstance(row_post, pd.DataFrame):
                row_post = row_post.iloc[0]
            all_moves.append({
                "player_name": player,
                "season_pre": s_pre,
                "season_post": s_post,
                "team_pre": team_pre,
                "team_post": team_post,
                "bpm_pre": row_pre.get("bpm"),
                "bpm_post": row_post.get("bpm"),
                "bpm_delta": (row_post.get("bpm") - row_pre.get("bpm"))
                if pd.notna(row_post.get("bpm")) and pd.notna(row_pre.get("bpm")) else None,
                "vorp_pre": row_pre.get("vorp"),
                "vorp_post": row_post.get("vorp"),
                "ts_pct_pre": row_pre.get("ts_pct"),
                "ts_pct_post": row_post.get("ts_pct"),
                "usg_pct_pre": row_pre.get("usg_pct"),
                "usg_pct_post": row_post.get("usg_pct"),
            })
        moves_per_pair[f"{s_pre}_to_{s_post}"] = pair_moves

    moves_df = pd.DataFrame(all_moves)
    return MovesCorpusResult(
        seasons_used=seasons,
        clean_counts_per_season=clean_counts,
        moves_per_season_pair=moves_per_pair,
        n_moves_total=len(moves_df),
        moves_df=moves_df,
    )


def write_moves_corpus(result: MovesCorpusResult, out_path: Path = _OUT_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.moves_df.to_parquet(out_path, index=False, engine="pyarrow")
    return out_path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Rebuild the historical bbref strict-moves corpus")
    parser.add_argument("--out", type=str, default=str(_OUT_PATH))
    args = parser.parse_args(argv)

    result = build_moves_corpus()
    out_path = write_moves_corpus(result, Path(args.out))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seasons_used": result.seasons_used,
        "clean_counts_per_season": result.clean_counts_per_season,
        "moves_per_season_pair": result.moves_per_season_pair,
        "n_moves_total": result.n_moves_total,
        "output_path": str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
        if str(out_path).startswith(str(REPO_ROOT)) else str(out_path),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
