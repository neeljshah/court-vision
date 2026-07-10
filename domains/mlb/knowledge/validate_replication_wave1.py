"""domains.mlb.knowledge.validate_replication_wave1 -- second-corpus
replication of the 2 strongest CONFIRMED_LOCALs from the 2025-only ledger:

  #43 compassionate-umpire count-behavior (validate_research_wave1.py)
  #39 called-strike dispersion exceeds binomial noise (validate_called_strike_dispersion.py)

Ponytail: imports and calls the ORIGINAL validator functions directly (same
zone set, same thresholds, same combine rule) rather than re-implementing
them -- this IS the "same bars as the original validator" guarantee, since
the bars live in one place and this module never redeclares them.

Outcomes (RAILS vocabulary): REPLICATED (clears the original's own bar on
the second corpus) / FAILED_REPLICATION (does not) / NOT_REPLICABLE_NO_CORPUS
(the season's parquet does not exist locally -- checked before any read).

Run: python -m domains.mlb.knowledge.validate_replication_wave1
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from domains.mlb.knowledge._data import LEDGER_PATH, STATCAST_DIR, load_season
from domains.mlb.knowledge.validate_called_strike_dispersion import (
    called_strike_dispersion_exceeds_binomial_noise, per_game_frame)
from domains.mlb.knowledge.validate_research_wave1 import compassionate_umpire_count_zone, _combine
from scripts.platformkit.io_atomic import append_jsonl_atomic

REPLICATION_SEASON = 2024


def _corpus_exists(season: int) -> bool:
    return (STATCAST_DIR / ("savant_full__%d.parquet" % season)).exists()


def _not_replicable(hyp: str, season: int) -> Dict[str, Any]:
    return {"hypothesis": "%s__replication_%d" % (hyp, season), "verdict": "NOT_REPLICABLE_NO_CORPUS",
            "n": 0, "note": "savant_full__%d.parquet does not exist locally" % season}


def replicate_called_strike_dispersion(season: int = REPLICATION_SEASON) -> Dict[str, Any]:
    """Reuses called_strike_dispersion_exceeds_binomial_noise unchanged (same
    PHI_THRESHOLD/ALPHA bar the original 2025 pass used) on the season parquet."""
    df = load_season(season)
    g = per_game_frame(df)
    original = called_strike_dispersion_exceeds_binomial_noise(g)
    verdict = "REPLICATED" if original["verdict"] == "CONFIRMED_LOCAL" else "FAILED_REPLICATION"
    return {"hypothesis": "called_strike_dispersion_exceeds_binomial_noise__replication_%d" % season,
            "verdict": verdict, "n": original["n"], "phi": original.get("phi"), "p": original.get("p"),
            "note": "replication on savant_full__%d (2025 CONFIRMED_LOCAL was phi=1.389, n=2406): %s"
                    % (season, original["note"])}


def replicate_compassionate_umpire(season: int = REPLICATION_SEASON) -> Dict[str, Any]:
    """Same split-half-by-date design as the original #43 pass, reusing
    compassionate_umpire_count_zone + the shared _combine bar/direction rule."""
    df = load_season(season)
    df = df.dropna(subset=["game_date"]).copy()
    df["game_date"] = pd.to_datetime(df["game_date"])
    mid = df["game_date"].median()
    halves = [compassionate_umpire_count_zone(df[df["game_date"] <= mid], "h1"),
              compassionate_umpire_count_zone(df[df["game_date"] > mid], "h2")]
    combined = _combine("compassionate_umpire_count_zone", halves)
    verdict = "REPLICATED" if combined["verdict"] == "CONFIRMED_LOCAL" else "FAILED_REPLICATION"
    return {"hypothesis": "compassionate_umpire_count_zone__replication_%d" % season,
            "verdict": verdict, "n": combined["n"],
            "note": "replication on savant_full__%d (split-half by date, same 0.05/p<0.01 bar as original): %s"
                    % (season, combined["note"])}


def run(season: int = REPLICATION_SEASON) -> List[Dict[str, Any]]:
    if not _corpus_exists(season):
        rows = [_not_replicable("called_strike_dispersion_exceeds_binomial_noise", season),
                _not_replicable("compassionate_umpire_count_zone", season)]
    else:
        rows = [replicate_called_strike_dispersion(season), replicate_compassionate_umpire(season)]
    for r in rows:
        r["sport"] = "mlb"
        r["corpus"] = "savant_full__%d" % season
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-58s %-24s %s" % (r["hypothesis"], r["verdict"], r.get("note", "")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: the corpus-existence gate, and that a season
    with no parquet on disk produces NOT_REPLICABLE_NO_CORPUS honestly
    instead of raising or silently skipping."""
    assert _corpus_exists(REPLICATION_SEASON), "expected savant_full__2024.parquet on disk for this replication"
    assert not _corpus_exists(1901)
    r = _not_replicable("compassionate_umpire_count_zone", 1901)
    assert r["verdict"] == "NOT_REPLICABLE_NO_CORPUS"
    print("self-check OK")
