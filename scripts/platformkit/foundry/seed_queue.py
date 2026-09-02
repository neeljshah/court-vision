"""Seed the foundry results-DB queue from the on-disk catalogue.

Enumeration is NOT a trial: nothing here calls `_charge_ledger` or any tier, so seeding a
million hypotheses costs the FWER ledger exactly nothing. The alphabet is deliberately narrow
(the S11 grammar's closed vocabulary, one transform pair, no conditioning) so `--limit` bounds
a knowable denominator rather than truncating an open grid. Calibration bookkeeping only.
"""
from __future__ import annotations

import argparse
from typing import Iterator, Sequence

import pandas as pd

from scripts.platformkit.foundry import catalogue, results_db
from scripts.platformkit.foundry.grammar import Hypothesis, enumerate_family

# The grammar's OWN closed alphabet, spelled out so `--limit` is the only bound. A name that
# drifts out of the grammar raises in canonical_payload -- loudly, never silently dropped.
# "ew" fans out to its four legal halflives inside enumerate_family.
TRANSFORMS: tuple[str, ...] = ("raw", "ew", "rank_in_league", "z_vs_league",
                               "delta_vs_prior", "ratio_to_opponent")
HORIZONS: tuple[str, ...] = ("pregame", "period", "live_tick")
MARKETS: tuple[str, ...] = ("ml", "total", "spread", "prop", "inplay")
# Spine / label / already-scored columns are never hypotheses about themselves.
EXCLUDED = frozenset(("event_id", "corpus_unit", "event_date", "date", "y", "p_base", "p_close",
                      "game_id", "home_team", "away_team", "season", "index"))


def columns_of(path) -> tuple[str, ...]:
    """Feature columns of one catalogue parquet, spine and label columns removed."""
    frame = pd.read_parquet(path)
    return tuple(str(name) for name in frame.columns if str(name) not in EXCLUDED)


def hypotheses(entries: Sequence[catalogue.Entry] | None = None,
               sport: str | None = None) -> Iterator[Hypothesis]:
    """Enumerate every catalogue parquet present on disk. Absent paths are named, never faked."""
    for entry in (catalogue.entries() if entries is None else entries):
        if sport is not None and entry.sport != sport:
            continue
        columns = columns_of(entry.path)
        if not columns:
            print("skipped path={0} reason=no_feature_columns".format(entry.path.name))
            continue
        spec = {"sport": entry.sport, "transforms": TRANSFORMS, "conditionings": (frozenset(),),
                "horizons": HORIZONS, "markets": MARKETS, "columns": columns,
                "family": "{0}:{1}".format(entry.sport, entry.path.stem),
                # runtime_available is honest-conservative: the teacher lane owns these columns
                # until a runtime adapter is measured. It is excluded from semantic_hash.
                "runtime_available": {name: False for name in columns}}
        try:
            for hypothesis in enumerate_family(spec):
                yield hypothesis
        except ValueError as error:   # an unusable family is named, not silently dropped
            print("skipped path={0} reason={1}".format(entry.path.name, error))


def frozen_hypotheses(sport: str | None = None) -> Iterator[Hypothesis]:
    """S58c: the FROZEN grammar -- every member of every FWER_FAMILIES_SPEC family x the 9
    transform instances, at the family's frozen horizon/market, conditioning {}. 3,564 enumerated;
    a member shared by two families (same sport/horizon/market) collapses to one semantic_hash."""
    from scripts.platformkit.eval_gate.family_bars import load_families

    for family in load_families().families:
        if sport is not None and family.sport != sport:
            continue
        spec = {"sport": family.sport, "transforms": TRANSFORMS, "conditionings": (frozenset(),),
                "horizons": (family.horizon,), "markets": (family.market,),
                "columns": family.members, "family": family.name,
                "runtime_available": {name: False for name in family.members}}
        for hypothesis in enumerate_family(spec):
            yield hypothesis


def seed(db: results_db.ResultsDB, *, limit: int, tier: str = "T0",
         sport: str | None = None, frozen: bool = False) -> int:
    """Upsert up to `limit` hypotheses and queue them at `tier`. Returns the number queued."""
    hashes: list[str] = []
    for hypothesis in (frozen_hypotheses(sport) if frozen else hypotheses(sport=sport)):
        if len(hashes) >= limit:
            break
        hashes.append(db.upsert_hypothesis(hypothesis, family=hypothesis.family,
                                           runtime_available=hypothesis.runtime_available))
    db.enqueue(hashes, tier)
    return len(hashes)


def main() -> None:
    """Seed the queue. Never charges; `--limit` is the only bound."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(results_db.DEFAULT_PATH))
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--tier", default="T0")
    parser.add_argument("--sport", default=None, help="restrict to one catalogue sport")
    parser.add_argument("--frozen", action="store_true",
                        help="seed the frozen FWER_FAMILIES_SPEC grammar instead of the catalogue grid")
    args = parser.parse_args()
    with results_db.ResultsDB(args.db) as db:
        seeded = seed(db, limit=args.limit, tier=args.tier, sport=args.sport, frozen=args.frozen)
        print("seeded={0} db={1} tier={2} sport={3} frozen={4}".format(
            seeded, args.db, args.tier, args.sport, args.frozen))


if __name__ == "__main__":
    main()
