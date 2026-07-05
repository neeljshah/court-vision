"""domains.mlb.asof_current_rebuild -- extend the leak-free as-of park + SP-RA
builders onto the current era (games_current.parquet, 2022-2026).

BLOCKER THIS CLOSES: pregame_stack_gate.py's corpus B (games_current, 10826
rows) has ZERO added-feature coverage -- asof_park.parquet / asof_features.py
are keyed off pitchers.parquet / games.parquet, both frozen at 2010-2021 (the
sportsbookreviewsonline archive era). Every corpus-B gate row falls back to
p_base, making corpus-B replication impossible for ANY MLB stack candidate.

RAW-SOURCE COVERAGE AUDIT (verified against real parquets, not assumed):
  - pitchers.parquet      2010-04-04 .. 2021-11-02 (27983 rows). Era-A ONLY.
  - games.parquet         same range as pitchers (paired 1:1 by event_id).
  - games_current.parquet 2022-04-07 .. 2026-06-16 (10826 rows). Era-B target.
  - probables.parquet     game_date 2022-2026 full-season coverage each year
                           (11128 rows; home_sp_name/away_sp_name + game_pk +
                           full-name team dialect + captured_at fetch time).
                           THE ONLY SP-IDENTITY SOURCE for era B.
  - espn_boxscores.parquet 2025-03 .. 2026-07 ONLY (partial; no pitcher
                           identity at all, aggregate team box only) --
                           insufficient for a full 2022-2026 SP proxy.
  - player_gamelogs.parquet 2022-2026 (321012 rows) but per game_pk_bridge.py's
                           own finding, row-order is NOT start order (~25% hit
                           rate for "first row = starter") -- NOT a reliable
                           SP-identity source. Confirmed CORPUS_ABSENT, not
                           used here (matches the prior asof_bullpen_DEFER
                           finding; not re-derived).
  - statcast starter_table 2022-2023 ONLY (via statcast_sp_fatigue_adapter) --
                           does not reach 2024-2026. CORPUS_ABSENT beyond 2023
                           for any statcast-keyed feature.

HONEST CAVEAT on probables.parquet's captured_at: the snapshot_date/game_date
lag is large for most rows (median ~773 days) -- this table was predominantly
BACKFILLED by re-querying the historical MLB Stats API schedule endpoint per
date, not captured contemporaneously day-of. The starting-pitcher IDENTITY
returned for a historical date is still the real announced starter (not an
outcome-derived proxy) and no future game result enters this feature, so it
stays leak-free by construction -- but it is NOT evidence of genuine
real-time "we knew before first pitch" capture for the bulk of the corpus.
Framed honestly in the coverage report below; never oversold as live-captured.

BUILD:
  asof_park_current.parquet     -- identical algorithm to asof_park.py, called
                                    directly on games_current (that function
                                    already accepts an arbitrary games frame;
                                    NO new park logic needed).
  asof_features_current.parquet -- SP-RA walk-forward via asof_features.py's
                                    existing engine, fed a probables-derived
                                    frame shaped like pitchers.parquet (same
                                    game_pk_bridge-style date+team-pair join
                                    used for player_gamelogs, reused here for
                                    probables' own full-name dialect).

Both outputs keep the SAME column names as the era-A files (park_factor,
sp_ra_diff_asof, ...) and are keyed on event_id, so pregame_stack_gate.py
picks them up with a path swap only -- NO gate code change in this module,
and none is made (frozen family stays REJECT per the lane's charter; this
module rebuilds DATA ONLY).

PURE pandas/numpy -- no src.*/kernel.*/other-domain imports.
PRIVATE: derived from price-bearing corpora; never tracked on the public repo.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from domains.mlb.asof_park import build_park_features
from domains.mlb.asof_features import build_asof_features
from domains.mlb.team_name_resolver import resolve as _resolve_full_name

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GAMES_CURRENT = _REPO_ROOT / "data/domains/mlb/games_current.parquet"
_PROBABLES = _REPO_ROOT / "data/domains/mlb/probables.parquet"
_OUT_PARK = _REPO_ROOT / "data/domains/mlb/asof_park_current.parquet"
_OUT_FEATURES = _REPO_ROOT / "data/domains/mlb/asof_features_current.parquet"

# team_name_resolver.resolve() targets the era-A games.parquet dialect (CHC,
# SFG); games_current uses two different legacy codes for the same two
# franchises (CUB, SFO). Corrected HERE ONLY -- team_name_resolver.py serves
# other era-A callers unchanged.
_ERA_A_TO_ERA_B = {"CHC": "CUB", "SFG": "SFO"}


def _to_era_b_code(full_name: object) -> Optional[str]:
    code = _resolve_full_name(str(full_name))
    if code is None:
        return None
    return _ERA_A_TO_ERA_B.get(code, code)


def coverage_report() -> Dict[str, object]:
    """Per-season coverage of each raw source against games_current's seasons.

    Returns a dict with per-source year -> row-count and an explicit
    CORPUS_ABSENT list for sources that do not reach the full 2022-2026 span.
    Never proxies or synthesizes a missing season -- names the exact gap.
    """
    gc = pd.read_parquet(_GAMES_CURRENT)
    gc_years = sorted(pd.to_datetime(gc["date"]).dt.year.unique().tolist())

    pr = pd.read_parquet(_PROBABLES)
    pr_years = pd.to_datetime(pr["game_date"]).dt.year.value_counts().sort_index()

    espn_p = _REPO_ROOT / "data/domains/mlb/espn_boxscores.parquet"
    espn_years: Dict[int, int] = {}
    if espn_p.exists():
        eb = pd.read_parquet(espn_p)
        if "date" in eb.columns and len(eb):
            espn_years = pd.to_datetime(eb["date"]).dt.year.value_counts().sort_index().to_dict()

    statcast_seasons_present = []
    for season in (2022, 2023, 2024, 2025, 2026):
        p = _REPO_ROOT / f"data/cache/statcast/starter_table__{season}.parquet"
        if p.exists():
            statcast_seasons_present.append(season)

    corpus_absent = []
    if not statcast_seasons_present or max(gc_years) > max(statcast_seasons_present, default=0):
        missing = [y for y in gc_years if y not in statcast_seasons_present]
        if missing:
            corpus_absent.append(
                f"statcast starter_table: missing seasons {missing} "
                f"(present only {statcast_seasons_present or 'none'}) -- "
                "no statcast-keyed feature can extend past 2023"
            )
    missing_espn = [y for y in gc_years if y not in espn_years]
    if missing_espn:
        corpus_absent.append(
            f"espn_boxscores: missing seasons {missing_espn} "
            f"(present only {sorted(espn_years.keys())}) -- also carries no "
            "pitcher identity in any season, so it cannot back an SP-RA proxy "
            "even where dates overlap"
        )
    corpus_absent.append(
        "player_gamelogs: covers 2022-2026 by date but row-order is NOT start "
        "order (game_pk_bridge.py measured ~25% first-row-is-starter hit rate) "
        "-- not usable as an SP-identity source; CONFIRMED, not re-derived"
    )

    return {
        "games_current_years": {int(y): int((pd.to_datetime(gc["date"]).dt.year == y).sum())
                                for y in gc_years},
        "probables_years": {int(y): int(n) for y, n in pr_years.items()},
        "espn_boxscores_years": {int(y): int(n) for y, n in espn_years.items()},
        "statcast_seasons_present": statcast_seasons_present,
        "corpus_absent": corpus_absent,
    }


def build_probables_as_pitchers_frame(
    probables: Optional[pd.DataFrame] = None,
    games_current: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Re-key probables.parquet onto games_current.event_id, pitchers.parquet shape.

    Join key: date (game_date) + unordered team-pair, both sides normalised
    through team_name_resolver (full-name -> era-A code -> era-B code). A
    doubleheader (same date+pair, >1 event) is AMBIGUOUS and dropped, never
    guessed -- mirrors game_pk_bridge.py's doubleheader discipline exactly.
    Duplicate probables snapshots for one game_pk keep the LATEST captured_at
    (most-complete announced rotation info; SP identity only, no outcome
    leaks through this choice).

    Output columns match asof_features._PITCHER_COLS so
    asof_features.build_asof_features can consume it unmodified:
      event_id, date, home_sp_name, away_sp_name,
      home_sp_present, away_sp_present.
    """
    pr = (probables.copy() if isinstance(probables, pd.DataFrame)
          else pd.read_parquet(str(_PROBABLES)))
    gc = (games_current.copy() if isinstance(games_current, pd.DataFrame)
          else pd.read_parquet(str(_GAMES_CURRENT)))

    pr = pr.sort_values("captured_at", kind="mergesort").drop_duplicates(
        subset="game_pk", keep="last")

    def _pair_key(date_val: object, home_code: Optional[str], away_code: Optional[str]
                 ) -> Optional[str]:
        if home_code is None or away_code is None:
            return None
        d = str(pd.to_datetime(date_val).date())
        x, y = sorted((home_code, away_code))
        return f"{d}|{x}|{y}"

    gc_keys: Dict[str, list] = {}
    for _, r in gc.iterrows():
        k = _pair_key(r["date"], str(r["home_team"]), str(r["away_team"]))
        if k is not None:
            gc_keys.setdefault(k, []).append(str(r["event_id"]))

    rows = []
    for _, r in pr.iterrows():
        h_code = _to_era_b_code(r["home_team"])
        a_code = _to_era_b_code(r["away_team"])
        k = _pair_key(r["game_date"], h_code, a_code)
        events = gc_keys.get(k) if k is not None else None
        if not events or len(events) > 1:
            continue  # unmatched or ambiguous doubleheader -- never guess
        h_present = bool(r["home_sp_name"]) and pd.notna(r["home_sp_name"])
        a_present = bool(r["away_sp_name"]) and pd.notna(r["away_sp_name"])
        rows.append({
            "event_id": events[0],
            "date": r["game_date"],
            "home_sp_name": r["home_sp_name"] if h_present else None,
            "away_sp_name": r["away_sp_name"] if a_present else None,
            "home_sp_present": h_present,
            "away_sp_present": a_present,
        })
    return pd.DataFrame(rows, columns=[
        "event_id", "date", "home_sp_name", "away_sp_name",
        "home_sp_present", "away_sp_present",
    ])


def build_asof_park_current(games_current: Optional[pd.DataFrame] = None,
                             out_path: Optional[str] = None) -> Path:
    """Era-B park factor: SAME algorithm as asof_park.build_park_features,
    just pointed at games_current instead of games.parquet. No new logic."""
    gc = (games_current.copy() if isinstance(games_current, pd.DataFrame)
          else pd.read_parquet(str(_GAMES_CURRENT)))
    return build_park_features(games=gc, out_path=out_path or str(_OUT_PARK))


def build_asof_features_current(probables: Optional[pd.DataFrame] = None,
                                 games_current: Optional[pd.DataFrame] = None,
                                 out_path: Optional[str] = None) -> Path:
    """Era-B SP-RA walk-forward via the existing asof_features engine, fed a
    probables-derived pitchers-shaped frame (bridged to event_id)."""
    gc = (games_current.copy() if isinstance(games_current, pd.DataFrame)
          else pd.read_parquet(str(_GAMES_CURRENT)))
    pitchers_frame = build_probables_as_pitchers_frame(probables, gc)
    return build_asof_features(pitchers=pitchers_frame, games=gc,
                               out_path=out_path or str(_OUT_FEATURES))


def _pct(n: int, d: int) -> str:
    return f"{(100.0 * n / d):.1f}%" if d else "n/a"


def main() -> None:
    """CLI: python -m domains.mlb.asof_current_rebuild [--out-dir DIR]."""
    ap = argparse.ArgumentParser(description=(
        "Rebuild leak-free MLB as-of park + SP-RA features onto games_current "
        "(2022-2026). No gate re-run; frozen family stays REJECT."
    ))
    ap.add_argument("--out-dir", default=None,
                    help="override data/domains/mlb/ output directory")
    args = ap.parse_args()
    out_dir = Path(args.out_dir) if args.out_dir else None
    park_out = str(out_dir / "asof_park_current.parquet") if out_dir else None
    feat_out = str(out_dir / "asof_features_current.parquet") if out_dir else None

    print("=" * 72)
    print("MLB CURRENT-ERA (2022-2026) AS-OF REBUILD -- coverage audit")
    print("=" * 72)
    cov = coverage_report()
    print("games_current rows by season:", cov["games_current_years"])
    print("probables rows by season:    ", cov["probables_years"])
    print("espn_boxscores rows by season:", cov["espn_boxscores_years"])
    print("statcast seasons present:     ", cov["statcast_seasons_present"])
    if cov["corpus_absent"]:
        print("\nCORPUS_ABSENT (named, not proxied):")
        for line in cov["corpus_absent"]:
            print(f"  - {line}")

    park_p = build_asof_park_current(out_path=park_out)
    park_df = pd.read_parquet(park_p)
    n = len(park_df)
    park_cov = int(park_df["park_factor"].notna().sum())
    print(f"\nwrote {park_p} ({n} rows) -- park_factor coverage {_pct(park_cov, n)}")

    feat_p = build_asof_features_current(out_path=feat_out)
    feat_df = pd.read_parquet(feat_p)
    n2 = len(feat_df)
    both_prior = int(((feat_df["home_sp_starts_prior"] > 0)
                      & (feat_df["away_sp_starts_prior"] > 0)).sum())
    ra_cov = int(feat_df["sp_ra_diff_asof"].notna().sum())
    print(f"wrote {feat_p} ({n2} rows) -- sp_ra_diff_asof coverage "
         f"{_pct(ra_cov, n2)}, both-SP-have-prior {_pct(both_prior, n2)}")
    print("\n(Data rebuild ONLY -- no gate re-run, no verdict change; the "
         "frozen mlb family stays REJECT until a sha-pinned amendment "
         "authorizes a re-gate on this widened corpus.)")


if __name__ == "__main__":
    main()
