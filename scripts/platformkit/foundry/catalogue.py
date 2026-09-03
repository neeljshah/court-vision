"""Shared catalogue-to-sport mapping for the foundry families (S11 enumerated it, S12/S15 reuse it).

Lifted out of tests/platformkit/foundry/test_grammar.py so the enumeration
denominator is one auditable list instead of a copy per test. Import-free of
foundry.tiers / foundry.results_db on purpose: this module is the shared input
to both, so it may not depend on either.
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[3]

# Step-1 named catalogue of the S11 spec (32 entries). A path that is absent is
# NAMED by absent(), never silently dropped.
NAMED: tuple[str, ...] = (
    "data/cache/combo/gate_corpus_nba.parquet",
    "data/cache/combo/gate_corpus_mlb.parquet",
    "data/cache/combo/gate_corpus_soccer.parquet",
    "data/cache/combo/gate_corpus_tennis.parquet",
    "data/domains/basketball_nba/asof_team_adv.parquet",
    "data/domains/basketball_nba/asof_defender_rollup.parquet",
    "data/domains/basketball_nba/boxdetail_asof.parquet",
    "data/domains/basketball_nba/carryover_asof.parquet",
    "data/domains/basketball_nba/asof_quarter_shape.parquet",
    "data/domains/basketball_nba/asof_player_adv.parquet",
    "data/domains/basketball_nba/player_value_features.parquet",
    "data/domains/mlb/asof_inning.parquet",
    "data/domains/mlb/bullpen_relief_chains.parquet",
    "data/domains/mlb/catcher_framing_index.parquet",
    "data/domains/soccer/asof_xg_proxy.parquet",
    "data/domains/soccer/style_fingerprints.parquet",
    "data/domains/soccer/referee_card_foul_profiles.parquet",
    "data/domains/soccer/asof_discipline_features.parquet",
    "data/domains/tennis/asof_features.parquet",
    "data/domains/tennis/asof_hold.parquet",
    "data/domains/tennis/asof_return.parquet",
    "data/domains/tennis/asof_setdetail.parquet",
    "data/domains/tennis/asof_meta.parquet",
    "data/domains/tennis/schedule_density.parquet",
    "data/domains/tennis/serve_return_profiles.parquet",
    "data/domains/tennis/travel_scouting.parquet",
    "data/domains/tennis/asof_features_wta.parquet",
    "data/domains/tennis/asof_hold_wta.parquet",
    "data/domains/tennis/asof_return_wta.parquet",
    "data/domains/tennis/asof_setdetail_wta.parquet",
    "data/domains/tennis/asof_meta_wta.parquet",
    "data/domains/tennis/schedule_density_wta.parquet",
    "data/domains/tennis/travel_scouting_wta.parquet",
)

GLOBS: tuple[str, ...] = (
    "data/cache/pit/opp_allowed_asof_*.parquet",
    "data/cache/ingame/*states*.parquet",
)

SPORTS = frozenset(("nba", "mlb", "soccer", "tennis"))
_DOMAIN_DIRS = (("basketball_nba", "nba"), ("mlb", "mlb"), ("soccer", "soccer"), ("tennis", "tennis"))
_NAME_TOKENS = (("nba", "nba"), ("mlb", "mlb"), ("soccer", "soccer"), ("tennis", "tennis"),
                ("pbp_", "nba"), ("possession_", "nba"))


class Entry(NamedTuple):
    """One catalogue parquet that exists on disk, with its sport label."""

    path: Path
    sport: str


def sport_of(path: Path | str) -> str:
    """Label one catalogue parquet: domain directory first, then filename token."""
    lowered = Path(path).as_posix().lower()
    for token, sport in _DOMAIN_DIRS:
        if "/domains/{0}/".format(token) in lowered:
            return sport
    if "/cache/pit/" in lowered:
        return "nba"
    name = Path(path).name.lower()
    for token, sport in _NAME_TOKENS:
        if token in name:
            return sport
    raise ValueError("no sport for catalogue path: {0}".format(lowered))


def absent() -> tuple[Path, ...]:
    """Named catalogue paths that do not exist on disk today."""
    return tuple(ROOT / name for name in NAMED if not (ROOT / name).exists())


def entries() -> tuple[Entry, ...]:
    """Every catalogue parquet present on disk, sport-labelled and de-duplicated."""
    paths = [ROOT / name for name in NAMED if (ROOT / name).exists()]
    for pattern in GLOBS:
        paths.extend(sorted(ROOT.glob(pattern)))
    seen: dict[Path, Entry] = {}
    for path in paths:
        seen.setdefault(path, Entry(path, sport_of(path)))
    return tuple(seen[key] for key in sorted(seen))


if __name__ == "__main__":  # pragma: no cover - operator readout
    rows = entries()
    print("PRESENT: {0} parquets".format(len(rows)))
    for sport in sorted(SPORTS):
        print("  {0}: {1}".format(sport, sum(1 for row in rows if row.sport == sport)))
    missing = absent()
    print("ABSENT / SKIPPED: {0} of {1} named".format(len(missing), len(NAMED)))
    for path in missing:
        print("  - {0}".format(path.relative_to(ROOT).as_posix()))
