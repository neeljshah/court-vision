"""domains.basketball_nba.corpus_b_build -- grow the 2025-26 box corpus (Corpus B).

Implements Option 2 of docs/research/combination-moat/NBA_SECOND_CORPUS_PROBE_2026-07-05.md:
reconcile the 678 ESPN-native rows in espn_boxscores.parquet (event_id format 401...,
NOT yet in player_boxscores.parquet) to NBA game_id via an exact (home_abbr, away_abbr,
date) match against games.parquet's 2025-26 schedule, melt them to the long team-game
shape asof_features.py / asof_box_extra.py already consume, and re-run those UNMODIFIED
builders over player_boxscores + the new rows to produce EXTENDED parquets:

    asof_features_ext.parquet, asof_box_extra_ext.parquet

The wave-1-frozen originals (asof_features.parquet, asof_box_extra.parquet) are never
read for write, only read for the "prior corpus" merge input -- byte-untouched.

DATA BUILD ONLY. No gate run, no verdict change. This module does not import or call
asof_reclaim_gate / asof_reclaim_dims / pregame_stack_gate -- the NBA family re-gate
against the extended files happens later via a sha-pinned A2 amendment (per the task).

RECONCILIATION DISCIPLINE (exact-match, no substring team matching -- prop-settler
lesson): a native row resolves ONLY if exactly one games.parquet row matches
(home_abbr, away_abbr, date) after tricode normalization. 0 or >1 matches ->
UNRESOLVED, dropped, counted, never guessed. All-Star abbrevs (STARS/STRIPES/WORLD
-- not real tricodes) fall out the same way, honestly.

LEAK-NOTE: aggregates realized post-game box stats only (LEAK_POST_GAME). Performs
NO walk-forward math itself -- asof_features.build_asof_features /
asof_box_extra.build_asof_box_extra (imported, not reimplemented) do the actual
snapshot-before-update walk, so the as-of leak-free guarantee is inherited unchanged.

COLUMN-SEMANTICS PARITY: melted rows carry the exact columns _walk_forward_team sums
(ast/fgm/fga/fg3m/reb/oreb/dreb/tov/pts/fta). No player split exists for these games,
but the upstream aggregator sums player rows to team-game totals anyway, so one
synthetic team-total row per team-game is semantics-identical to summing real player
rows. home_fg3m is null in the native rows; home_fg3_made feeds fg3m instead (the
probe's documented rename). home_pts/fgm/fga/fta are ALSO null -- pace_asof (needs
fga+fta) is NaN for these new rows; reported honestly, not papered over.

F5: NO domains.mlb / domains.tennis / domains.soccer / src.* / kernel.* imports.
PRIVATE: never committed to the public repo.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_corpus_b_build.py -q

CLI:
  cd /c/Users/neelj/nba-ai-system && python -m domains.basketball_nba.corpus_b_build
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

from domains.basketball_nba.asof_box_extra import build_asof_box_extra
from domains.basketball_nba.asof_features import build_asof_features
from domains.basketball_nba.espn_nba_bridge import _norm_abbr

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _REPO_ROOT / "data" / "domains" / "basketball_nba"

_ESPN_BOXSCORES = _DATA_DIR / "espn_boxscores.parquet"
_GAMES = _DATA_DIR / "games.parquet"
_PLAYER_BOXSCORES = _DATA_DIR / "player_boxscores.parquet"

OUT_ASOF_FEATURES = _DATA_DIR / "asof_features_ext.parquet"
OUT_ASOF_BOX_EXTRA = _DATA_DIR / "asof_box_extra_ext.parquet"
OUT_COVERAGE_REPORT = _DATA_DIR / "corpus_b_coverage_report.json"

CORPUS_ID = "nba_corpus_b_ext_v1"

# Stats melted from espn_boxscores.parquet's home_/away_ wide columns into the
# long team-game shape asof_features._aggregate_team_games / asof_box_extra
# expect. home_fg3m is null in the native slice; fg3m is sourced from
# home_fg3_made instead (documented compound-stat rename, not a new field).
_STAT_MAP: Tuple[Tuple[str, str], ...] = (
    ("ast", "ast"), ("fgm", "fgm"), ("fga", "fga"), ("fg3m", "fg3m"), ("reb", "reb"),
    ("oreb", "oreb"), ("dreb", "dreb"), ("tov", "tov"), ("pts", "pts"),
    ("fta", "fta"), ("stl", "stl"), ("blk", "blk"),
)


def _native_rows(espn_box: pd.DataFrame) -> pd.DataFrame:
    """The 401...-event_id rows only (ESPN-native scrape, not player_boxscores-derived
    rows re-written under the same filename by team_box_from_players.py)."""
    df = espn_box.copy()
    df["event_id"] = df["event_id"].astype(str)
    return df[df["event_id"].str.startswith("401")].reset_index(drop=True)


def reconcile_event_ids(
    espn_box: Optional[pd.DataFrame] = None,
    games: Optional[pd.DataFrame] = None,
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Exact (home_abbr, away_abbr, date) match of native ESPN rows -> NBA game_id.

    Only STATUS_FINAL rows are eligible. Tricodes normalized via the SAME
    espn_nba_bridge._norm_abbr map (GS/NO/NY/SA/UTAH/WSH -> GSW/NOP/NYK/SAS/UTA/WAS).
    A candidate resolves ONLY if exactly one games.parquet row matches; 0 or >1
    matches on that key -> UNRESOLVED (dropped, counted, never guessed -- exact-match
    discipline, no substring team matching).

    Returns (resolved DataFrame with an added game_id column, counts dict with
    native_final / resolved / unresolved_no_match / unresolved_ambiguous).
    """
    espn_box = espn_box if espn_box is not None else pd.read_parquet(_ESPN_BOXSCORES)
    games = games if games is not None else pd.read_parquet(_GAMES)

    native = _native_rows(espn_box)
    native = native[native["status"] == "STATUS_FINAL"].copy()
    n_native_final = len(native)

    native["_home_nba"] = native["home_abbr"].map(_norm_abbr)
    native["_away_nba"] = native["away_abbr"].map(_norm_abbr)
    native["_date"] = pd.to_datetime(native["date"]).dt.normalize()

    g = games[["game_id", "date", "home_team", "away_team"]].copy()
    g["_date"] = pd.to_datetime(g["date"]).dt.normalize()

    # Count matches per candidate key first, then tag EACH native row (still one
    # row per event_id, no fan-out yet) with how many games.parquet rows share
    # its key -- this is what lets an ambiguous (>1) key be told apart from a
    # clean no-match key without a candidate row ever fanning a native row out
    # to >1 rows before the ambiguity check runs.
    match_counts = (
        g.groupby(["home_team", "away_team", "_date"]).size()
        .rename("_n_matches").reset_index()
    )
    native = native.merge(
        match_counts,
        left_on=["_home_nba", "_away_nba", "_date"],
        right_on=["home_team", "away_team", "_date"],
        how="left", suffixes=("", "_mc"),
    )
    native["_n_matches"] = native["_n_matches"].fillna(0).astype(int)

    no_match = native["_n_matches"] == 0
    ambiguous = native["_n_matches"] > 1
    clean = native[(~no_match) & (~ambiguous)].copy()

    # Only clean (exactly-one-match) rows are merged against g to attach game_id
    # -- ambiguous/no-match rows never enter this merge, so they cannot fan out.
    resolved = clean.merge(
        g[["game_id", "home_team", "away_team", "_date"]],
        left_on=["_home_nba", "_away_nba", "_date"],
        right_on=["home_team", "away_team", "_date"],
        how="inner",
    )
    resolved = resolved.drop_duplicates(subset=["event_id"]).copy()
    resolved["game_id"] = resolved["game_id"].astype(str)

    counts = {
        "native_final": int(n_native_final),
        "resolved": int(len(resolved)),
        "unresolved_no_match": int(no_match.sum()),
        "unresolved_ambiguous": int(ambiguous.sum()),
    }
    drop_cols = [c for c in resolved.columns if c.startswith("_") or c in
                 ("home_team", "away_team", "home_team_mc", "away_team_mc")]
    resolved = resolved.drop(columns=[c for c in drop_cols if c in resolved.columns])
    return resolved.reset_index(drop=True), counts


def melt_to_team_games(resolved: pd.DataFrame) -> pd.DataFrame:
    """Wide home_/away_ resolved rows -> long team-game rows matching the
    player_boxscores.parquet aggregation shape (game_id, date, team, opp, is_home
    + summed stat cols). One synthetic team-total row per side per game -- see
    module docstring for the column-semantics-parity argument."""
    if resolved.empty:
        cols = ["game_id", "date", "team", "opp", "is_home"] + [s for s, _ in _STAT_MAP]
        return pd.DataFrame(columns=cols)

    df = resolved.copy()
    # fg3m fix: home_fg3m is null in the native slice; home_fg3_made carries it.
    df["home_fg3m"] = df["home_fg3_made"]
    df["away_fg3m"] = df["away_fg3_made"]

    sides = []
    for side, opp_side, is_home in (("home", "away", True), ("away", "home", False)):
        rows = {
            "game_id": df["game_id"],
            "date": df["date"],
            "team": df[f"{side}_nba"] if f"{side}_nba" in df.columns else df[f"{side}_abbr"].map(_norm_abbr),
            "opp": df[f"{opp_side}_nba"] if f"{opp_side}_nba" in df.columns else df[f"{opp_side}_abbr"].map(_norm_abbr),
            "is_home": is_home,
        }
        for out_stat, src_stat in _STAT_MAP:
            col = f"{side}_{src_stat}"
            rows[out_stat] = df[col] if col in df.columns else float("nan")
        sides.append(pd.DataFrame(rows))

    long = pd.concat(sides, ignore_index=True)
    long["season"] = "2025-26"
    return long


def build_extended_player_box(
    espn_box: Optional[pd.DataFrame] = None,
    games: Optional[pd.DataFrame] = None,
    player_box: Optional[pd.DataFrame] = None,
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Concat the existing player_boxscores.parquet with the reconciled+melted
    new rows. Returns (extended long frame, reconciliation counts dict).
    De-dupes on game_id: if a reconciled game_id somehow already exists in
    player_boxscores (should not happen -- these are the 678 NOT-yet-covered
    rows per the probe -- but checked defensively), the existing rows win."""
    player_box = player_box if player_box is not None else pd.read_parquet(_PLAYER_BOXSCORES)
    resolved, counts = reconcile_event_ids(espn_box, games)
    new_long = melt_to_team_games(resolved)

    existing_ids = set(player_box["game_id"].astype(str))
    overlap = new_long["game_id"].astype(str).isin(existing_ids) if len(new_long) else pd.Series([], dtype=bool)
    # count UNIQUE overlapping game_ids, not rows (each game_id contributes 2
    # rows -- home + away -- to new_long via melt_to_team_games).
    counts["already_in_player_boxscores"] = (
        int(new_long.loc[overlap, "game_id"].astype(str).nunique()) if len(new_long) else 0
    )
    new_long = new_long[~overlap].reset_index(drop=True) if len(new_long) else new_long

    ext = pd.concat([player_box, new_long], ignore_index=True) if len(new_long) else player_box.copy()
    counts["new_games_added"] = int(new_long["game_id"].nunique()) if len(new_long) else 0
    return ext, counts


def _season_coverage(asof_df: pd.DataFrame, games: pd.DataFrame, n_prior_cols: Tuple[str, str]) -> Dict[str, dict]:
    """Per-season rows / walk-forward coverage report for an extended asof frame."""
    g = games[["game_id", "season"]].copy()
    g["game_id"] = g["game_id"].astype(str)
    merged = asof_df.copy()
    merged["game_id"] = merged["game_id"].astype(str)
    merged = merged.merge(g, on="game_id", how="left")

    out: Dict[str, dict] = {}
    hcol, acol = n_prior_cols
    for season, grp in merged.groupby("season", dropna=True):
        n = len(grp)
        covered = int(((grp[hcol] > 0) & (grp[acol] > 0)).sum())
        out[str(season)] = {
            "rows": int(n),
            "walk_forward_both_sides_covered": covered,
            "walk_forward_coverage_pct": round(100.0 * covered / n, 1) if n else 0.0,
        }
    return out


def build_and_write() -> Dict:
    """Full Option-2 build: reconcile -> melt -> concat -> re-run the UNMODIFIED
    asof builders -> write _ext parquets + coverage report. Wave-1-frozen
    asof_features.parquet / asof_box_extra.parquet are read (as the prior-corpus
    merge input) but never written to."""
    games = pd.read_parquet(_GAMES)
    ext_player_box, counts = build_extended_player_box(games=games)

    build_asof_features(player_box=ext_player_box, out_path=str(OUT_ASOF_FEATURES))
    build_asof_box_extra(player_box=ext_player_box, out_path=str(OUT_ASOF_BOX_EXTRA))

    feat = pd.read_parquet(OUT_ASOF_FEATURES)
    box = pd.read_parquet(OUT_ASOF_BOX_EXTRA)

    report = {
        "corpus_id": CORPUS_ID,
        "reconciliation": counts,
        "asof_features_ext": {
            "total_rows": int(len(feat)),
            "by_season": _season_coverage(feat, games, ("home_n_prior", "away_n_prior")),
        },
        "asof_box_extra_ext": {
            "total_rows": int(len(box)),
            "by_season": _season_coverage(box, games, ("home_n_prior", "away_n_prior")),
        },
        "dim_completeness_asof_features_ext": {
            c: int(feat[c].notna().sum()) for c in
            ("home_pace_asof", "away_pace_asof", "home_oreb_pg_asof", "away_oreb_pg_asof",
             "home_tov_pg_asof", "away_tov_pg_asof")
        },
        "dim_completeness_asof_box_extra_ext": {
            c: int(box[c].notna().sum()) for c in
            ("dreb_diff_asof", "fg3m_diff_asof", "stl_diff_asof", "blk_diff_asof")
        },
    }
    OUT_COVERAGE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_COVERAGE_REPORT.write_text(pd.Series(report).to_json(indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    import json as _json

    result = build_and_write()
    print("=" * 72)
    print("NBA corpus_b_build (Option 2: bridge + re-aggregate ESPN-native 2025-26 tail)")
    print("=" * 72)
    print(_json.dumps(result, indent=2))
    print(f"wrote: {OUT_ASOF_FEATURES}")
    print(f"wrote: {OUT_ASOF_BOX_EXTRA}")
    print(f"wrote: {OUT_COVERAGE_REPORT}")
    print("DATA BUILD ONLY -- no gate run, no verdict change. Re-gate happens via a")
    print("sha-pinned A2 amendment. Wave-1-frozen asof_features.parquet /")
    print("asof_box_extra.parquet are byte-untouched.")
