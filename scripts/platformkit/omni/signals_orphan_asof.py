"""scripts.platformkit.omni.signals_orphan_asof -- ORPHAN-1 lane.

Converts the 13 NBA trained-signal parquets under data/cache/signals/ (per
docs/research/DATA_COVERAGE_MAP.md row 1 of the TOP-10 table -- "the 13 NBA
trained-signal catalog -- only vault-fold reads, no model consumer") into
leak-free AS-OF attribute frames the interaction factory can consume.

CENSUS (data/cache/signals/, 14 files total; form_trajectory_asof.parquet is
already the leak-free per-game conversion of form_trajectory.parquet, built
separately by scripts/signals/build_form_trajectory_asof.py -- not one of
the 13, informational only):

  CONVERTIBLE (season-grain, >=2 distinct seasons, stable entity key):
    defense_matchup   entity=def_player_id  season in {2023-24..2025-26}
    lineup_5man       entity=lineup_str     season in 7 seasons 2018-19..2025-26
    playmaking        entity=player_id      season in {2021-22..2025-26}
    rebounding        entity=player_id      season in {2022-23..2025-26}
    team_offdef       entity=team_tricode   season in {2022-23..2025-26}

  NOT_CONVERTIBLE (no usable time axis -- reason recorded per signal):
    correlation_joint        -- no season/date col; one row per player, aggregated
                                 across entire multi-season history (leak trap:
                                 season-final aggregate, no walk-forward boundary)
    durability_availability  -- season axis embedded in wide column-name suffixes
                                 (games_missed_injury_2022_23, ...), not a
                                 normalized season column; out of scope for the
                                 generic prior-season shift this lane ships
    form_trajectory          -- superseded: form_trajectory_asof.parquet already
                                 is the leak-free per-game conversion of this
                                 exact signal (149870ff), reconverting here would
                                 duplicate it at strictly worse (season) grain
    ingame_rotation           -- no season/date col; all-history aggregate
    lineup_pair_trio         -- season col present but only ONE season (2024-25)
                                 in the corpus -- no prior season to shift from
    scoring_profile           -- no season/date col; all-history aggregate
    shotclock_leverage        -- no season/date col; all-history aggregate
    situational_splits        -- no season/date col; all-history aggregate

CONVERSION RULE (prior-completed-season AS-OF, leak-free by construction):
a player/team-season aggregate row is fully known only once that season
completes, so it is a valid AS-OF attribute for games in the entity's NEXT
season -- never for games within the season it summarizes (that IS the
season-final leak trap; docs/research/DATA_COVERAGE_MAP.md TOP-10 row 1 and
the spacing-signal NOT_TESTABLE precedent). Per entity, sort seasons
chronologically (season strings 'YYYY-YY' sort correctly lexically) and
shift every numeric feature column by 1 season. An entity's first season in
the corpus has no prior season -> every asof__ column is honestly NaN
(never faked), matching the debut convention in asof_common.py /
build_form_trajectory_asof.py.

Output: one parquet per convertible signal under data/omni/signals_asof/,
columns [entity_col, season, asof__<feature>...]; season is the season the
row's as-of value is VALID FOR (the season AFTER the one it summarizes).
knowable_at = season start of `season` (the summarized season has fully
closed out by then).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_signals_orphan_asof.py -q
"""
from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from scripts.platformkit.omni import claims_ledger

REPO = pathlib.Path(__file__).resolve().parents[3]
SIGNALS_DIR = REPO / "data" / "cache" / "signals"
OUT_DIR = REPO / "data" / "omni" / "signals_asof"

# (parquet stem, entity_col) -- season col is always literally "season".
CONVERTIBLE: List[Tuple[str, str]] = [
    ("defense_matchup", "def_player_id"),
    ("lineup_5man", "lineup_str"),
    ("playmaking", "player_id"),
    ("rebounding", "player_id"),
    ("team_offdef", "team_tricode"),
]

NOT_CONVERTIBLE: Dict[str, str] = {
    "correlation_joint": "no season/date col; one row per player aggregated "
        "across entire multi-season history -- no walk-forward boundary exists",
    "durability_availability": "season axis embedded in wide column-name "
        "suffixes (games_missed_injury_2022_23, ...), not a normalized season "
        "column -- out of scope for the generic prior-season shift",
    "form_trajectory": "superseded: form_trajectory_asof.parquet already is "
        "the leak-free per-game conversion of this exact signal (149870ff)",
    "ingame_rotation": "no season/date col; all-history aggregate",
    "lineup_pair_trio": "season col present but only ONE season (2024-25) in "
        "the corpus -- no prior season to shift from",
    "scoring_profile": "no season/date col; all-history aggregate",
    "shotclock_leverage": "no season/date col; all-history aggregate",
    "situational_splits": "no season/date col; all-history aggregate",
}

SEASON_COL = "season"


def census() -> pd.DataFrame:
    """Read schema + row counts for every parquet under data/cache/signals/ (schema-only)."""
    rows = []
    for path in sorted(SIGNALS_DIR.glob("*.parquet")):
        df = pd.read_parquet(path)
        rows.append({
            "name": path.stem,
            "rows": len(df),
            "n_cols": len(df.columns),
            "has_season": SEASON_COL in df.columns,
            "n_seasons": df[SEASON_COL].nunique() if SEASON_COL in df.columns else 0,
        })
    return pd.DataFrame(rows)


def _feature_cols(df: pd.DataFrame, entity_col: str) -> List[str]:
    """Numeric columns to shift -- everything except the entity/season keys."""
    exclude = {entity_col, SEASON_COL}
    return [c for c in df.columns if c not in exclude and pd.api.types.is_numeric_dtype(df[c])]


def convert_prior_season_asof(df: pd.DataFrame, entity_col: str) -> pd.DataFrame:
    """Shift every numeric feature column by 1 season per entity (leak-free).

    Output row for (entity, season=S) carries entity's own season==S-1 (prior,
    completed) feature values under asof__<col>. An entity's first season in
    the corpus emits NaN in every asof__ column (no prior season exists).
    """
    feature_cols = _feature_cols(df, entity_col)
    ordered = df.sort_values([entity_col, SEASON_COL], kind="mergesort").reset_index(drop=True)
    shifted = ordered.groupby(entity_col, sort=False)[feature_cols].shift(1)
    out = ordered[[entity_col, SEASON_COL]].copy()
    for c in feature_cols:
        out[f"asof__{c}"] = shifted[c]
    return out


def assert_no_prior_season_leak(asof_df: pd.DataFrame, entity_col: str) -> None:
    """An entity's FIRST season row (no prior season in the corpus) must be
    all-NaN across every asof__ column -- otherwise a season's own aggregate
    leaked into its own as-of row."""
    asof_cols = [c for c in asof_df.columns if c.startswith("asof__")]
    first = asof_df.sort_values([entity_col, SEASON_COL], kind="mergesort")
    first = first.groupby(entity_col, sort=False).head(1)
    if not asof_cols:
        return
    bad = int(first[asof_cols].notna().any(axis=1).sum())
    if bad > 0:
        raise AssertionError(
            f"Future-leak: {bad} debut-season rows have non-NaN asof__ values."
        )


def build_all(out_dir: pathlib.Path = OUT_DIR) -> Dict[str, dict]:
    """Convert every CONVERTIBLE signal, write parquets, return a per-signal result dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results: Dict[str, dict] = {}
    for name, entity_col in CONVERTIBLE:
        src = SIGNALS_DIR / f"{name}.parquet"
        df = pd.read_parquet(src)
        if df[SEASON_COL].nunique() < 2:
            results[name] = {"status": "NOT_CONVERTIBLE",
                              "reason": "fewer than 2 distinct seasons at conversion time"}
            continue
        asof_df = convert_prior_season_asof(df, entity_col)
        assert_no_prior_season_leak(asof_df, entity_col)
        out_path = out_dir / f"{name}_asof.parquet"
        asof_df.to_parquet(out_path, index=False)
        results[name] = {"status": "CONVERTED", "rows": len(asof_df), "path": str(out_path)}
    for name, reason in NOT_CONVERTIBLE.items():
        results[name] = {"status": "NOT_CONVERTIBLE", "reason": reason}
    return results


def ledger_all(results: Dict[str, dict], base_dir: Optional[str] = None) -> List[str]:
    """One structural claim per signal parquet, statement = conversion verdict."""
    claim_ids = []
    for name, res in results.items():
        if res["status"] == "CONVERTED":
            statement = f"{name}: converted-and-registered pending (asof frame built, factory registration is a PROPOSED diff -- data/omni/signals_asof/{name}_asof.parquet, {res['rows']} rows)"
        else:
            statement = f"{name}: NOT_CONVERTIBLE ({res['reason']})"
        claim = {
            "statement": statement,
            "type": "structural",
            "scope": {"sport": "nba"},
            "topic": "signals_orphan_asof",
            "provenance": {"created_by_lane": "orphan1"},
        }
        claim_ids.append(claims_ledger.add_claim(claim, base_dir=base_dir))
    return claim_ids


def main() -> None:
    print("Census of data/cache/signals/:")
    print(census().to_string(index=False))
    results = build_all()
    print("\nConversion results:")
    for name, res in results.items():
        print(f"  {name}: {res['status']}" + (f" reason={res['reason']}" if res["status"] != "CONVERTED" else f" rows={res['rows']}"))
    claim_ids = ledger_all(results)
    print(f"\nLedgered {len(claim_ids)} claims.")


if __name__ == "__main__":
    main()
