"""The shared POINT-IN-TIME store: one knowledge substrate for both arms.

Stores atlas-section values AND shipped-signal learned per-entity values keyed by
``(entity, field, as_of)`` with strict leak-safety on reads: ``read(entity, field,
as_of)`` returns the freshest record whose ``as_of <= requested as_of`` -- NEVER a
future record. This is what makes both signals and atlases consume the substrate
leak-free.

Three writers (per the architecture):
  * PBP / NBA-API builders (now)              -- ``write`` atlas sections.
  * shipped signals (write learned values back) -- ``write_signal_field``.
  * the CV branch (fills reserved CV slots later) -- ``fill_cv_slot``.

Backed by an append-only JSONL on-disk cache under ``data/cache/loop_store/`` so
point-in-time feature reads are fast on re-test and survive across processes. An
in-memory index (entity, field) -> sorted [(as_of, record)] gives O(log n) as-of
lookup. Records are immutable; a new value at a newer as_of supersedes on read.

Leak-safety is the contract: nothing here ever returns a record stamped after the
requested as_of. CV slots are written with the same as_of discipline.
"""
from __future__ import annotations

import bisect
import datetime as _dt
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DIR = ROOT / "data" / "cache" / "loop_store"

# Record kinds distinguish the three writers for provenance/audit.
KIND_ATLAS = "atlas"
KIND_SIGNAL = "signal"
KIND_CV = "cv"

_DateLike = Union[str, _dt.date, _dt.datetime]


def _to_iso(when: _DateLike) -> str:
    """Normalise any date-like to an ISO ``YYYY-MM-DD`` string (date granularity)."""
    if isinstance(when, str):
        return when[:10]
    if isinstance(when, _dt.datetime):
        return when.date().isoformat()
    if isinstance(when, _dt.date):
        return when.isoformat()
    raise TypeError(f"unsupported as_of type: {type(when)!r}")


@dataclass
class StoreRecord:
    """One immutable point-in-time fact.

    Attributes:
        entity:     "player:<id>" or "team:<tricode>" (namespaced key).
        field:      atlas section key or signal feature name.
        as_of:      ISO date the value is valid as-of (the leak boundary).
        value:      the stored payload (dict for atlas, float/dict for signal).
        kind:       KIND_ATLAS | KIND_SIGNAL | KIND_CV.
        provenance: ``{source, n, confidence, ...}``.
        written_at: wall-clock write time (audit only; NEVER used for leak logic).
    """

    entity: str
    field: str
    as_of: str
    value: Any
    kind: str = KIND_ATLAS
    provenance: Dict[str, Any] = field(default_factory=dict)
    written_at: Optional[str] = None

    def to_json(self) -> dict:
        return {
            "entity": self.entity, "field": self.field, "as_of": self.as_of,
            "value": self.value, "kind": self.kind,
            "provenance": self.provenance, "written_at": self.written_at,
        }

    @classmethod
    def from_json(cls, d: dict) -> "StoreRecord":
        return cls(
            entity=d["entity"], field=d["field"], as_of=d["as_of"],
            value=d.get("value"), kind=d.get("kind", KIND_ATLAS),
            provenance=d.get("provenance", {}), written_at=d.get("written_at"),
        )


def entity_key(entity_type: str, entity_id: Any) -> str:
    """Build the namespaced entity key, e.g. ``("player", 1628983) -> "player:1628983"``."""
    return f"{entity_type}:{entity_id}"


class PointInTimeStore:
    """Append-only, leak-safe, on-disk-cached substrate read by both arms.

    Args:
        store_dir: directory for the JSONL cache (default data/cache/loop_store/).
        autoload:  load existing records on construction.
    """

    def __init__(self, store_dir: Optional[Union[str, Path]] = None,
                 autoload: bool = True) -> None:
        self.dir = Path(store_dir) if store_dir else _DEFAULT_DIR
        self.dir.mkdir(parents=True, exist_ok=True)
        self._path = self.dir / "records.jsonl"
        self._lock = threading.RLock()
        # index: (entity, field) -> (sorted as_of list, parallel record list)
        self._index: Dict[Tuple[str, str], Tuple[List[str], List[StoreRecord]]] = {}
        if autoload:
            self.load()

    # ---- load / persist ------------------------------------------------------
    def load(self) -> int:
        """Load all records from the JSONL cache into the in-memory index."""
        if not self._path.exists():
            return 0
        n = 0
        with self._lock, self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    self._index_record(StoreRecord.from_json(json.loads(line)),
                                       persist=False)
                    n += 1
                except (json.JSONDecodeError, KeyError):
                    continue
        return n

    def _index_record(self, rec: StoreRecord, persist: bool = True) -> None:
        """Insert a record into the sorted-by-as_of index (and optionally disk)."""
        key = (rec.entity, rec.field)
        asofs, recs = self._index.setdefault(key, ([], []))
        pos = bisect.bisect_right(asofs, rec.as_of)
        asofs.insert(pos, rec.as_of)
        recs.insert(pos, rec)
        if persist:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec.to_json()) + "\n")

    # ---- writes (three writers) ---------------------------------------------
    def write(self, entity: str, field_: str, as_of: _DateLike, value: Any, *,
              kind: str = KIND_ATLAS, provenance: Optional[dict] = None) -> StoreRecord:
        """Write a point-in-time record (generic; used by atlas builders).

        Append-only: writing the same (entity, field, as_of) twice keeps both; the
        latest write at that as_of wins on read (records are ordered by insertion
        within equal as_of via bisect_right).
        """
        rec = StoreRecord(
            entity=entity, field=field_, as_of=_to_iso(as_of), value=value,
            kind=kind, provenance=provenance or {},
            written_at=_dt.datetime.utcnow().isoformat() + "Z",
        )
        with self._lock:
            self._index_record(rec, persist=True)
        return rec

    def write_atlas(self, entity_type: str, entity_id: Any, section: str,
                    as_of: _DateLike, data: dict, provenance: dict) -> StoreRecord:
        """Writer #1/#2: persist an atlas-section artifact payload."""
        return self.write(entity_key(entity_type, entity_id), section, as_of, data,
                          kind=KIND_ATLAS, provenance=provenance)

    def write_signal_field(self, entity_type: str, entity_id: Any,
                           signal_name: str, as_of: _DateLike, value: Any, *,
                           provenance: Optional[dict] = None) -> StoreRecord:
        """Writer #2 (reinforcement): a SHIPPED signal writes learned per-entity
        values back as a new atlas-style field, so future signals can read them."""
        prov = dict(provenance or {})
        prov.setdefault("source", f"shipped_signal:{signal_name}")
        return self.write(entity_key(entity_type, entity_id),
                          f"signal__{signal_name}", as_of, value,
                          kind=KIND_SIGNAL, provenance=prov)

    def fill_cv_slot(self, entity_type: str, entity_id: Any, section: str,
                     slot: str, as_of: _DateLike, value: Any, *,
                     provenance: Optional[dict] = None) -> StoreRecord:
        """Writer #3 (CV branch): fill a reserved CV slot for a section.

        Stored as a distinct field ``cv__<section>__<slot>`` so it merges into the
        atlas read without clobbering the descriptive payload.
        """
        prov = dict(provenance or {})
        prov.setdefault("source", "cv_branch")
        return self.write(entity_key(entity_type, entity_id),
                          f"cv__{section}__{slot}", as_of, value,
                          kind=KIND_CV, provenance=prov)

    # ---- leak-safe reads -----------------------------------------------------
    def read(self, entity: str, field_: str, as_of: _DateLike) -> Optional[Any]:
        """Return the freshest value with ``record.as_of <= as_of`` (LEAK-SAFE).

        Returns ``None`` if no record exists at or before the requested as_of --
        never returns a future record.
        """
        rec = self.read_record(entity, field_, as_of)
        return rec.value if rec is not None else None

    def read_record(self, entity: str, field_: str,
                    as_of: _DateLike) -> Optional[StoreRecord]:
        """Leak-safe record lookup: latest record at or before ``as_of``."""
        key = (entity, field_)
        with self._lock:
            entry = self._index.get(key)
            if not entry:
                return None
            asofs, recs = entry
            target = _to_iso(as_of)
            # rightmost record with as_of <= target
            pos = bisect.bisect_right(asofs, target) - 1
            if pos < 0:
                return None
            return recs[pos]

    def read_atlas(self, entity_type: str, entity_id: Any, section: str,
                   as_of: _DateLike, *, with_cv: bool = True) -> Optional[dict]:
        """Read an atlas section leak-safe, optionally merging filled CV slots."""
        ek = entity_key(entity_type, entity_id)
        data = self.read(ek, section, as_of)
        if data is None:
            return None
        if not with_cv or not isinstance(data, dict):
            return data
        merged = dict(data)
        cv = dict(merged.get("_cv_fields", {}))
        for (e, f), (asofs, recs) in self._index.items():
            if e != ek or not f.startswith(f"cv__{section}__"):
                continue
            slot = f[len(f"cv__{section}__"):]
            rec = self.read_record(ek, f, as_of)
            if rec is not None:
                cv.setdefault(slot, {})
                cv[slot] = {**cv.get(slot, {}), "value": rec.value}
        merged["_cv_fields"] = cv
        return merged

    def read_signal_field(self, entity_type: str, entity_id: Any,
                          signal_name: str, as_of: _DateLike) -> Optional[Any]:
        """Read a shipped signal's learned per-entity value (the reinforcement read)."""
        return self.read(entity_key(entity_type, entity_id),
                         f"signal__{signal_name}", as_of)

    # ---- introspection -------------------------------------------------------
    def fields(self, entity: str) -> List[str]:
        """List all field names stored for an entity."""
        with self._lock:
            return sorted({f for (e, f) in self._index if e == entity})

    def stats(self) -> Dict[str, int]:
        """Counts by kind for health/reporting."""
        out: Dict[str, int] = {"total": 0, KIND_ATLAS: 0, KIND_SIGNAL: 0, KIND_CV: 0}
        with self._lock:
            for (_, _), (_, recs) in self._index.items():
                for r in recs:
                    out["total"] += 1
                    out[r.kind] = out.get(r.kind, 0) + 1
        return out


_DEFAULT_STORE: Optional[PointInTimeStore] = None


def get_store(store_dir: Optional[Union[str, Path]] = None) -> PointInTimeStore:
    """Return a process-wide default store (constructed on first use)."""
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None or store_dir is not None:
        _DEFAULT_STORE = PointInTimeStore(store_dir=store_dir)
    return _DEFAULT_STORE
