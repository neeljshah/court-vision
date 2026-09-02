"""Foundry results DB -- an INDEX of trial evidence, never a replacement for it.

stdlib `sqlite3` only (MLflow / DVC / Phoenix would be one more service to keep
alive on the pod for a job one file does). Indexing is NOT a trial: nothing in
this module calls `_charge_ledger`, so a re-proposed hypothesis is a lookup and
costs the FWER ledger nothing.

Red-team prerequisites (REDTEAM_SIGNAL_FACTORY 187101ea):
  SF-12  same hash + different raw params -> sqlite3.IntegrityError, surfaced.
  SF-13  corpus_sha is part of the UNIQUE key; a changed corpus is a fresh trial.
  SF-14  a lookup returns k_at_run and flags verdict_needs_rescore whenever the
         caller's current K differs; recompute_deflated_p() serves the current p.

Calibration bookkeeping only -- no dollar, ROI, profit or edge claim lives here.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from scripts.platformkit.eval_gate.deflated_metrics import deflated_p as _deflated_p
from scripts.platformkit.foundry.grammar import Hypothesis, semantic_hash

# Production default: gitignored, pod-authoritative, backed up nightly by S29.
# data/registry/ is NEVER agent-written and a tracked path would leak research
# state to the public origin. Tests pass their own tmp_path.
DEFAULT_PATH = Path("data/cache/eval_gate/hypotheses.sqlite")
TRIALS_DIR = Path("data/cache/eval_gate/trials")
GRAMMAR_VERSION = "s11"

_HYPOTHESIS_RAW = ("sport", "feature", "transform", "params", "conditioning", "horizon", "market")
_RESULT_FIELDS = ("hash", "tier", "corpus", "corpus_unit", "corpus_sha", "n", "n_eff",
                  "brier_model", "brier_close", "dm_stat", "raw_p", "k_family", "k_global",
                  "deflated_p", "pbo", "verdict", "artifact_path", "prereg_sha256", "run_at")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS hypothesis(
    hash TEXT PRIMARY KEY, family TEXT, sport TEXT, feature TEXT, transform TEXT,
    params TEXT, conditioning TEXT, horizon TEXT, market TEXT,
    runtime_available INTEGER, created_at TEXT, grammar_version TEXT);
CREATE TABLE IF NOT EXISTS result(
    id INTEGER PRIMARY KEY, hash TEXT REFERENCES hypothesis(hash), tier TEXT, corpus TEXT,
    corpus_unit TEXT, corpus_sha TEXT, n INTEGER, n_eff REAL, brier_model REAL,
    brier_close REAL, dm_stat REAL, raw_p REAL, k_family INTEGER, k_global INTEGER,
    deflated_p REAL, pbo REAL, verdict TEXT, artifact_path TEXT, prereg_sha256 TEXT,
    run_at TEXT, UNIQUE(hash, tier, corpus, corpus_unit, corpus_sha));
CREATE TABLE IF NOT EXISTS queue(
    hash TEXT PRIMARY KEY, tier TEXT, enqueued_at TEXT, claimed_at TEXT, lease_until TEXT);
"""

LEASE_SECONDS = 900.0  # S66: how long a claim is held before reap_expired frees it


@dataclass(frozen=True)
class TierResult:
    """The minimal shape `record()` accepts.

    Defined here rather than imported so this module does not depend on S12;
    scripts/platformkit/foundry/tiers.py adapts to this field list. `record()`
    also takes any plain mapping carrying the same keys.
    """

    hash: str
    tier: str
    corpus: str
    corpus_unit: str
    corpus_sha: str
    n: int
    n_eff: float
    brier_model: float
    brier_close: float
    dm_stat: float
    raw_p: float
    k_family: Optional[int]
    k_global: int
    deflated_p: float
    pbo: Optional[float]
    verdict: str
    artifact_path: str
    prereg_sha256: Optional[str] = None
    run_at: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def trial_artifact_path(hash: str, tier: str, corpus_unit: str) -> Path:
    """Where the evidence JSON lives. The DB indexes it; it never replaces it."""
    return TRIALS_DIR / "{0}_{1}_{2}.json".format(hash, tier, corpus_unit)


def recompute_deflated_p(row: Mapping[str, Any], k_now: int) -> Optional[float]:
    """SF-14: the current-K deflated p for a stored row. Never serve row['deflated_p']
    as current -- it was computed at row['k_at_run'] and the ledger only grows."""
    raw_p = row.get("raw_p")
    return None if raw_p is None else _deflated_p(float(raw_p), int(k_now))


def _hypothesis(row: sqlite3.Row) -> Hypothesis:
    return Hypothesis(
        sport=row["sport"], feature=row["feature"], transform=row["transform"],
        params=tuple(tuple(pair) for pair in json.loads(row["params"])),
        conditioning=frozenset(json.loads(row["conditioning"])),
        horizon=row["horizon"], market=row["market"],
        # S66: DROPPED here before, so every claimed hypothesis came back with
        # family="" and the runner's `or queue.family` fallback labelled all 6,000
        # pod claims with the queue's sport. Stored all along; reconstruction lost it.
        family=row["family"] or "",
        runtime_available=bool(row["runtime_available"]))


class ResultsDB:
    """One sqlite file. Open it, use it, close it (or use it as a context manager)."""

    def __init__(self, path: Any = DEFAULT_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: autocommit, so claim() can own its BEGIN IMMEDIATE.
        self._c = sqlite3.connect(str(self.path), isolation_level=None)
        self._c.row_factory = sqlite3.Row
        self._c.execute("PRAGMA foreign_keys=ON")
        self._c.executescript(_SCHEMA)
        # Additive migration for a DB created before S66 (see reap_expired).
        columns = {row[1] for row in self._c.execute("PRAGMA table_info(queue)")}
        if "lease_until" not in columns:
            self._c.execute("ALTER TABLE queue ADD COLUMN lease_until TEXT")

    def close(self) -> None:
        self._c.close()

    def __enter__(self) -> "ResultsDB":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- hypotheses -------------------------------------------------------------
    def upsert_hypothesis(self, hypothesis: Hypothesis, *, family: Optional[str] = None,
                          runtime_available: Optional[bool] = None,
                          grammar_version: str = GRAMMAR_VERSION,
                          created_at: Optional[str] = None) -> str:
        """Insert-if-absent, keyed by semantic_hash. Returns the hash.

        SF-12: an insert whose hash exists with DIFFERENT raw params is a grid-snap
        collision. sqlite has already refused it on the primary key; we re-raise
        that IntegrityError rather than merging the two hypotheses into one row.
        An identical re-proposal is simply idempotent.

        S66: `family` / `runtime_available` now DEFAULT to the hypothesis's own
        fields (hash-excluded, so neither can move the digest), so a caller that
        forgets them can no longer strand a row with family="".
        """
        digest = semantic_hash(hypothesis)
        family = hypothesis.family if family is None else family
        runtime_available = (hypothesis.runtime_available if runtime_available is None
                             else runtime_available)
        raw = (hypothesis.sport, hypothesis.feature, hypothesis.transform,
               json.dumps([list(pair) for pair in hypothesis.params]),
               json.dumps(sorted(hypothesis.conditioning)),
               hypothesis.horizon, hypothesis.market)
        try:
            self._c.execute(
                "INSERT INTO hypothesis(hash, family, sport, feature, transform, params, "
                "conditioning, horizon, market, runtime_available, created_at, grammar_version) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (digest, family) + raw + (int(bool(runtime_available)),
                                          created_at or _now(), grammar_version))
        except sqlite3.IntegrityError:
            stored = self._c.execute(
                "SELECT {0} FROM hypothesis WHERE hash=?".format(", ".join(_HYPOTHESIS_RAW)),
                (digest,)).fetchone()
            if stored is None or tuple(stored) != raw:
                raise
        return digest

    def get_hypothesis(self, hash: str) -> Optional[Hypothesis]:
        row = self._c.execute("SELECT * FROM hypothesis WHERE hash=?", (hash,)).fetchone()
        return None if row is None else _hypothesis(row)

    # -- results ----------------------------------------------------------------
    def record(self, result: Any) -> int:
        """Index one scored trial. Returns the result row id.

        A duplicate (hash, tier, corpus, corpus_unit, corpus_sha) raises
        sqlite3.IntegrityError -- the same trial is never double-indexed.
        """
        row = dict(asdict(result) if is_dataclass(result) else result)
        missing = [name for name in _RESULT_FIELDS if name not in row]
        if missing:
            raise ValueError("result missing fields: {0}".format(", ".join(missing)))
        row["run_at"] = row.get("run_at") or _now()
        self._c.execute(
            "INSERT INTO result({0}) VALUES({1})".format(
                ", ".join(_RESULT_FIELDS), ",".join("?" * len(_RESULT_FIELDS))),
            tuple(row[name] for name in _RESULT_FIELDS))
        return int(self._c.execute("SELECT last_insert_rowid()").fetchone()[0])

    def lookup(self, hash: str, tier: str, corpus: str, corpus_unit: str,
               corpus_sha: str, k_now: Optional[int] = None) -> Optional[dict]:
        """The prior trial for this exact (hypothesis, tier, corpus, unit, corpus_sha),
        or None. SF-13: a different corpus_sha misses, so a changed corpus is a fresh
        trial. SF-14: the hit carries k_at_run, and verdict_needs_rescore is True
        whenever the caller's current K differs from the K the verdict was priced at.
        """
        row = self._c.execute(
            "SELECT * FROM result WHERE hash=? AND tier=? AND corpus=? AND corpus_unit=? "
            "AND corpus_sha=?", (hash, tier, corpus, corpus_unit, corpus_sha)).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["k_at_run"] = out["k_global"]
        out["verdict_needs_rescore"] = (
            k_now is not None and int(k_now) != int(out["k_at_run"]))
        return out

    def family_p_values(self, family: str) -> list:
        """Raw p-values of every scored trial already recorded for ONE frozen family (S59).

        What a within-family BH/BY bar is computed over. Read-only: indexing is not a
        trial, so this costs the FWER ledger nothing and cannot re-score a stored verdict.
        """
        rows = self._c.execute(
            "SELECT r.raw_p FROM result r JOIN hypothesis h ON h.hash = r.hash "
            "WHERE h.family = ? AND r.raw_p IS NOT NULL ORDER BY r.id", (family,)).fetchall()
        return [float(row[0]) for row in rows]

    # -- queue ------------------------------------------------------------------
    def enqueue(self, hashes: Iterable[str], tier: str) -> int:
        """Queue hypotheses for a tier. Already-queued hashes are left alone."""
        now = _now()
        rows = [(h, tier, now) for h in hashes]
        self._c.executemany(
            "INSERT OR IGNORE INTO queue(hash, tier, enqueued_at, claimed_at) "
            "VALUES(?,?,?,NULL)", rows)
        return len(rows)

    def reap_expired(self, now: Optional[str] = None) -> int:
        """Hand every EXPIRED claim back to the queue. Returns the row count.

        B4: a claimer that dies mid-tier must not strand its rows. `claim()` calls
        this inside its own transaction, so every claimer reaps by construction; it
        is public because the runner may also reap on a pass that claims nothing.
        A row claimed BEFORE S66 has lease_until NULL and is NEVER auto-reaped --
        nothing can tell a live pre-lease claimer from a dead one, so only
        `release()` frees those."""
        cursor = self._c.execute(
            "UPDATE queue SET claimed_at=NULL, lease_until=NULL WHERE claimed_at IS NOT NULL "
            "AND lease_until IS NOT NULL AND lease_until <= ?", (now or _now(),))
        return int(cursor.rowcount)

    def release(self, hashes: Iterable[str]) -> int:
        """Hand claimed rows back on a FAILURE path, without waiting out the lease."""
        cursor = self._c.executemany(
            "UPDATE queue SET claimed_at=NULL, lease_until=NULL WHERE hash=?",
            [(h,) for h in hashes])
        return int(cursor.rowcount)

    def claim(self, n: int, tier: Optional[str] = None,
              lease_seconds: float = LEASE_SECONDS, sport: Optional[str] = None) -> list:
        """Claim up to n queued hypotheses in ONE transaction, holding a lease.

        BEGIN IMMEDIATE takes the write lock before the SELECT, so two claimers can
        never both see the same unclaimed row. A claimed row is not claimable again
        until its lease expires (B4): `reap_expired` runs in the same transaction, so
        an expired claim is reclaimable on the NEXT claim and never before it.
        S75: `sport` filters the hypothesis's OWN sport, so a screener bound to one
        corpus cannot claim a row it would screen on foreign states. None = as before.
        """
        sql = ("SELECT q.hash FROM queue q JOIN hypothesis h ON h.hash=q.hash "
               "WHERE q.claimed_at IS NULL")
        args: list = []
        for column, value in (("q.tier", tier), ("h.sport", sport)):
            if value is not None:
                sql += " AND {0}=?".format(column)
                args.append(value)
        sql += " ORDER BY q.enqueued_at, q.hash LIMIT ?"
        args.append(int(n))
        self._c.execute("BEGIN IMMEDIATE")
        try:
            stamp = _now()
            self.reap_expired(stamp)
            hashes = [row[0] for row in self._c.execute(sql, args).fetchall()]
            if hashes:
                until = (datetime.fromisoformat(stamp)          # all stamps are UTC,
                         + timedelta(seconds=float(lease_seconds))).isoformat()
                self._c.executemany(
                    "UPDATE queue SET claimed_at=?, lease_until=? WHERE hash=?",
                    [(stamp, until, h) for h in hashes])
            rows = [self._c.execute("SELECT * FROM hypothesis WHERE hash=?", (h,)).fetchone()
                    for h in hashes]
            self._c.execute("COMMIT")
        except Exception:
            self._c.execute("ROLLBACK")
            raise
        return [_hypothesis(row) for row in rows if row is not None]
