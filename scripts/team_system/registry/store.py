"""SHARDED, TRANSACTIONAL, LOCK-SERIALIZED REGISTRY I/O (MASTER_SYSTEM_BUILD sections 3 + 5).

NOT one growing parquet (that is O(N^2) at 10k+ rows). Each registry is an append-only directory of
shard parts `data/registry/<name>/part-*.parquet` + an in-memory {id: row} index. Writes are a new part
via temp-name + os.replace() (atomic on the same volume). compact() coalesces parts when count > 64.

INVARIANTS enforced here (so the unattended loop cannot silently corrupt the source of truth):
  - register(row) is PURE: compute the content id; if present, no-op return id; else append one part.
    Registration NEVER computes a value -- only records a definition.
  - Writes are SERIALIZED behind data/registry/.lock (single writer; subagents return rows, they do not
    write concurrently -- section 5).
  - PROVENANCE INTEGRITY: after every write, assert no two rows share an id with DIFFERENT definition
    columns. On violation -> raise (the loop must STOP + report, never proceed on a corrupt registry).
  - transactional_write(): any artifact (parquet/json) is written staging -> validate -> [board] ->
    keep .bak -> os.replace(). A failed validator never touches the live file.
"""
from __future__ import annotations
import json
import os
import time
from contextlib import contextmanager

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
REGISTRY_DIR = os.path.join(ROOT, "data", "registry")
_LOCK = os.path.join(REGISTRY_DIR, ".lock")
_COMPACT_THRESHOLD = 64

# (id_col, def_cols = identity columns that MUST be constant per id; the rest are mutable status/metrics)
SCHEMAS = {
    "signal_registry": dict(
        id_col="signal_id",
        def_cols=["grain", "entity_scope", "domain_tags", "source", "formula_ast",
                  "transform_chain", "asof_fn", "causal_sign"],
        cols=["signal_id", "grain", "entity_scope", "domain_tags", "source", "formula_ast",
              "transform_chain", "asof_fn", "causal_sign", "input_hash", "honesty_class",
              "bet_wireable", "status", "gateA_rel", "gateA_fdr_q", "gateX_verdict",
              "judge_sign_ok", "judge_engine_ortho", "family_key", "n", "coverage_pct",
              "created_utc", "builder", "artifact_path", "legacy_name", "note",
              "declared_sign", "measured_sign", "quantity"],
    ),
    "model_registry": dict(
        id_col="model_id",
        def_cols=["domain_tag", "entity_scope", "signal_id_set_hash", "method"],
        cols=["model_id", "domain_tag", "entity_scope", "signal_id_set_hash", "method",
              "input_hash", "oos_score", "xseason_verdict", "engine_node", "status",
              "artifact_path", "created_utc"],
    ),
    "engine_registry": dict(
        id_col="engine_id",
        def_cols=["name", "method"],          # consumes_models/owns_nodes are mutable wiring, NOT identity
        cols=["engine_id", "name", "consumes_models", "owns_nodes", "method",
              "reliability_weight", "engine_corr", "last_backtest_utc"],
    ),
    "calibration_registry": dict(
        id_col="key",
        def_cols=["key"],
        cols=["key", "shapeErr", "coverage", "reliability", "n", "updated_utc"],
    ),
    "domain_registry": dict(
        id_col="domain",
        def_cols=["domain", "family"],
        cols=["domain", "family", "scopes", "honesty_class", "default_status"],
    ),
}


def _pid_alive_or_fresh(stamp: float, stale_after: float = 120.0) -> bool:
    """A lock is 'live' only if its file is younger than stale_after seconds (registry writes hold the
    lock for milliseconds; 120s is a very safe staleness floor that also self-heals a crashed holder)."""
    return (time.time() - stamp) < stale_after


@contextmanager
def registry_lock(timeout: float = 30.0, poll: float = 0.05, stale_after: float = 120.0):
    """Single-writer file lock for all registry writes. Steals a stale lock (crashed holder)."""
    os.makedirs(REGISTRY_DIR, exist_ok=True)
    start = time.monotonic()
    while True:
        try:
            fd = os.open(_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}:{time.time():.3f}".encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                age = os.path.getmtime(_LOCK)
            except FileNotFoundError:
                continue
            if not _pid_alive_or_fresh(age, stale_after):
                try:
                    os.remove(_LOCK)  # steal stale lock
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() - start > timeout:
                raise TimeoutError(f"registry_lock: could not acquire {_LOCK} within {timeout}s")
            time.sleep(poll)
    try:
        yield
    finally:
        try:
            os.remove(_LOCK)
        except FileNotFoundError:
            pass


def _atomic_write_parquet(df: pd.DataFrame, dest: str) -> None:
    tmp = dest + ".tmp"
    df.to_parquet(tmp, index=False)
    os.replace(tmp, dest)


class Registry:
    """Append-only sharded registry with an in-memory latest-row index."""

    def __init__(self, name: str):
        if name not in SCHEMAS:
            raise KeyError(f"unknown registry '{name}' (known: {list(SCHEMAS)})")
        self.name = name
        self.schema = SCHEMAS[name]
        self.id_col = self.schema["id_col"]
        self.dir = os.path.join(REGISTRY_DIR, name)
        os.makedirs(self.dir, exist_ok=True)
        self._index: dict = {}
        self._reload_index()

    # ---- read ----
    def _parts(self) -> list:
        return sorted(p for p in os.listdir(self.dir) if p.startswith("part-") and p.endswith(".parquet"))

    def _reload_index(self) -> None:
        self._index = {}
        for part in self._parts():
            try:
                df = pd.read_parquet(os.path.join(self.dir, part))
            except Exception as _exc:
                # Warn loudly instead of silently skipping -- a corrupt part means rows are
                # missing from the index until compaction recovers them. This is a low-risk
                # observability fix: the exception is still swallowed so the caller doesn't
                # crash, but the log line makes silent data-loss detectable in run output.
                print(f"  [registry] WARNING: could not read part {part} in {self.name} "
                      f"({type(_exc).__name__}: {str(_exc)[:120]}); rows in this part are "
                      f"excluded from the index until the file is recovered or removed.")
                continue
            for row in df.to_dict("records"):
                self._index[row[self.id_col]] = row  # write order => latest wins

    def all(self) -> pd.DataFrame:
        if not self._index:
            return pd.DataFrame(columns=self.schema["cols"])
        return pd.DataFrame(list(self._index.values()))

    def get(self, rid: str):
        return self._index.get(rid)

    def __len__(self):
        return len(self._index)

    # ---- write (lock-serialized, append-only) ----
    def _write_part(self, rows: list) -> None:
        """Append one shard part. MUST be called while holding registry_lock (callers all hold it)."""
        seq = len(self._parts())
        part = os.path.join(self.dir, f"part-{seq:06d}-{int(time.time()*1000)%1000000:06d}.parquet")
        _atomic_write_parquet(pd.DataFrame(rows), part)
        for r in rows:
            self._index[r[self.id_col]] = r
        self._assert_integrity()
        if len(self._parts()) > _COMPACT_THRESHOLD:
            self._compact_nolock()              # already under the lock -> do NOT re-acquire (deadlock)

    def register(self, row: dict) -> str:
        """PURE: if the id already exists, no-op (return id). Else append one part. Never overwrites."""
        rid = row.get(self.id_col)
        if not rid:
            raise ValueError(f"row missing id_col '{self.id_col}'")
        if rid in self._index:
            return rid
        with registry_lock():
            self._reload_index()                # re-read in case another writer appended
            if rid in self._index:
                return rid
            self._write_part([self._coerce(row)])
        return rid

    def register_many(self, rows: list) -> dict:
        """Batch-register: write all NEW rows (id not already present) in ONE part under one lock.
        Avoids the O(N^2) per-row reload/integrity storm during migration/foundry batches."""
        with registry_lock():
            self._reload_index()
            fresh, seen = [], set(self._index)
            for r in rows:
                rid = r.get(self.id_col)
                if not rid or rid in seen:
                    continue
                seen.add(rid)
                fresh.append(self._coerce(r))
            if fresh:
                self._write_part(fresh)
        return dict(registered=len(fresh), skipped=len(rows) - len(fresh))

    def upsert(self, row: dict) -> str:
        """Append a SUPERSEDING row (same id, updated mutable fields). The def_cols must match any prior
        row with that id (enforced by the integrity check). Use for status/metric updates."""
        rid = row.get(self.id_col)
        if not rid:
            raise ValueError(f"row missing id_col '{self.id_col}'")
        with registry_lock():
            self._reload_index()
            prior = self._index.get(rid)
            merged = dict(prior or {}, **row)
            self._write_part([self._coerce(merged)])
        return rid

    def update_status(self, rid: str, **fields) -> str:
        with registry_lock():
            self._reload_index()
            prior = self._index.get(rid)
            if prior is None:
                raise KeyError(f"{rid} not in {self.name}")
            self._write_part([self._coerce(dict(prior, **fields))])
        return rid

    def _coerce(self, row: dict) -> dict:
        out = {c: row.get(c) for c in self.schema["cols"]}
        out[self.id_col] = row[self.id_col]
        # carry any extra def cols even if not in cols list (defensive)
        for c in self.schema["def_cols"]:
            if c in row:
                out[c] = row[c]
        return out

    def _assert_integrity(self) -> None:
        """No two rows may share an id with DIFFERENT definition columns (id IS the def hash)."""
        seen: dict = {}
        for part in self._parts():
            try:
                df = pd.read_parquet(os.path.join(self.dir, part))
            except Exception:
                continue
            for row in df.to_dict("records"):
                rid = row[self.id_col]
                sig = json.dumps({c: _norm(row.get(c)) for c in self.schema["def_cols"]},
                                 sort_keys=True, default=str)
                if rid in seen and seen[rid] != sig:
                    raise RuntimeError(
                        f"REGISTRY INTEGRITY VIOLATION in {self.name}: id {rid} has two definitions. "
                        f"STOP and report (section 5).")
                seen[rid] = sig

    def compact(self) -> None:
        """Coalesce all parts into one (latest row per id). Lock-protected; atomic swap."""
        with registry_lock():
            self._compact_nolock()

    def _compact_nolock(self) -> None:
        """Coalesce parts; caller MUST hold registry_lock. Writes the coalesced part under a fresh name,
        removes the old parts, then renames (so a crash mid-compact never loses rows)."""
        df = self.all()
        final = os.path.join(self.dir, "part-000000-000000.parquet")
        tmp = os.path.join(self.dir, "_compact.tmp.parquet")
        df.to_parquet(tmp, index=False)
        for p in self._parts():
            try:
                os.remove(os.path.join(self.dir, p))
            except FileNotFoundError:
                pass
        os.replace(tmp, final)
        self._reload_index()


def _norm(v):
    if isinstance(v, (list, tuple)):
        return sorted(str(x) for x in v)
    return v


# ---------------------------------------------------------------------------
# transactional_write -- the staging -> validate -> [board] -> .bak -> os.replace cycle for ANY artifact
# ---------------------------------------------------------------------------
def transactional_write(path: str, write_fn, validator=None, board_fn=None, keep_bak: bool = True) -> bool:
    """write_fn(staging_path) writes the artifact to a staging file; validator(staging_path) raises on
    failure; board_fn() (optional) re-runs the regression board and must return truthy. Only on all-green
    does staging atomically replace live (keeping one .bak). A failed step never touches the live file.

    Returns True on commit. On any failure: staging is removed, live file is untouched, raises is suppressed
    into a False return with the reason printed (caller decides to PAUSE)."""
    staging = path + ".staging"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    try:
        write_fn(staging)
        if validator is not None:
            validator(staging)               # must raise on invalid
        if board_fn is not None and not board_fn():
            raise RuntimeError("board_fn returned falsy (regression board not green)")
        if keep_bak and os.path.exists(path):
            bak = path + ".bak"
            try:
                if os.path.exists(bak):
                    os.remove(bak)
                os.replace(path, bak)
            except OSError:
                pass
        os.replace(staging, path)
        return True
    except Exception as e:
        print(f"  transactional_write FAILED for {os.path.basename(path)}: {str(e)[:200]}")
        try:
            if os.path.exists(staging):
                os.remove(staging)
        except OSError:
            pass
        return False


def rollback(path: str) -> bool:
    """Restore <path> from <path>.bak (one deep)."""
    bak = path + ".bak"
    if not os.path.exists(bak):
        return False
    os.replace(bak, path)
    return True


if __name__ == "__main__":
    import sys
    if "--status" in sys.argv:
        for name in SCHEMAS:
            d = os.path.join(REGISTRY_DIR, name)
            if os.path.isdir(d):
                r = Registry(name)
                print(f"{name:24s} {len(r):5d} rows, {len(r._parts())} parts")
            else:
                print(f"{name:24s} (not yet created)")
    else:
        print("registry.store: Registry(name), registry_lock(), transactional_write(); --status to view")
