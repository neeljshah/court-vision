"""scripts.platformkit.ingest_manifest_core -- per-sport data provenance contract.

Declares WHICH corpora a sport depends on, each tagged with a leak_class (when the
data becomes known relative to tip) and a freshness SLA. The leak_class is the
honesty anchor: a pre_game feature may train the pregame model; in_game/post_game
data must never leak into a pregame feature. The manifest also cross-links to the
data_registry census so a sport's declared sources can be validated to actually
exist and be non-empty.

PURE dataclasses + light validation. No src/kernel/api imports. ASCII only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# When the data becomes known, relative to event start.
LEAK_PRE_GAME = "pre_game"     # known before tip; safe for pregame features
LEAK_IN_GAME = "in_game"       # accrues during play; in-game conditioning only
LEAK_POST_GAME = "post_game"   # only after final; settlement / labels / training targets
LEAK_REFERENCE = "reference"   # static reference (parks, surfaces, schedules)
_LEAK_CLASSES = (LEAK_PRE_GAME, LEAK_IN_GAME, LEAK_POST_GAME, LEAK_REFERENCE)


@dataclass(frozen=True)
class IngestSource:
    """One declared corpus dependency for a sport.

    corpus      : the census file-stem this lands in (e.g. "games", "odds").
    leak_class  : one of the LEAK_* constants.
    sla_minutes : max acceptable staleness in minutes (None = no live SLA, e.g.
                  historical/reference corpora).
    description : human-readable provenance note.
    """

    corpus: str
    leak_class: str
    sla_minutes: Optional[int] = None
    description: str = ""


@dataclass(frozen=True)
class IngestManifest:
    """A sport's full corpus-provenance contract."""

    sport: str
    sources: Tuple[IngestSource, ...]

    def validate(self) -> List[str]:
        """Return a list of structural errors ([] == valid)."""
        errs: List[str] = []
        seen = set()
        for s in self.sources:
            if s.leak_class not in _LEAK_CLASSES:
                errs.append(f"{self.sport}/{s.corpus}: bad leak_class {s.leak_class!r}")
            if s.corpus in seen:
                errs.append(f"{self.sport}: duplicate corpus {s.corpus!r}")
            seen.add(s.corpus)
            if s.sla_minutes is not None and s.sla_minutes <= 0:
                errs.append(f"{self.sport}/{s.corpus}: sla_minutes must be > 0")
        return errs

    def pregame_corpora(self) -> List[str]:
        """Corpora that are safe to feed a PREGAME feature (pre_game + reference)."""
        return [s.corpus for s in self.sources
                if s.leak_class in (LEAK_PRE_GAME, LEAK_REFERENCE)]

    def validate_against_inventory(self, inventory: dict) -> List[str]:
        """Return errors where a declared source is absent / empty in the census.

        ``inventory`` is the dict produced by data_registry.inventory.build_inventory.
        """
        errs: List[str] = []
        present: Dict[str, dict] = {
            r["name"]: r for r in inventory.get("rows", [])
            if r.get("sport") == self.sport
        }
        for s in self.sources:
            row = present.get(s.corpus)
            if row is None:
                errs.append(f"{self.sport}/{s.corpus}: declared source absent from census")
            elif row.get("is_empty"):
                errs.append(f"{self.sport}/{s.corpus}: declared source is 0-row")
        return errs
