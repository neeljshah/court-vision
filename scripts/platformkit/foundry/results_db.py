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
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional

from scripts.platformkit.foundry.grammar import Hypothesis, semantic_hash
from scripts.platformkit.foundry.runner_leases import dead_same_host_claimer
from scripts.platformkit.foundry.results_db_sql import TierResult, _HYPOTHESIS_RAW, _RESULT_FIELDS, _SCHEMA, _hypothesis, _now, recompute_deflated_p

# Production default: gitignored, pod-authoritative, backed up nightly by S29.
# data/registry/ is NEVER agent-written and a tracked path would leak research
# state to the public origin. Tests pass their own tmp_path.
DEFAULT_PATH = Path("data/cache/eval_gate/hypotheses.sqlite")
TRIALS_DIR = Path("data/cache/eval_gate/trials")
GRAMMAR_VERSION = "s11"


LEASE_SECONDS = 900.0  # S66: how long a claim is held before reap_expired frees it
# S135: the DEFAULT lease is LEASE_SECONDS per claimed row -- a claimer screens its batch
# serially, so a flat 900 s expired mid-batch and the next runner claimed rows still being
# screened. ponytail: a per-row multiple, not a scheduler; renew() is the knob above it.
_SQL_VARS = 500  # chunk for an IN (...) list; sqlite's default parameter limit is 999


def trial_artifact_path(hash: str, tier: str, corpus_unit: str) -> Path:
    """Where the evidence JSON lives. The DB indexes it; it never replaces it."""
    return TRIALS_DIR / "{0}_{1}_{2}.json".format(hash, tier, corpus_unit)


class ResultsDB:
    """One sqlite file. Open it, use it, close it (or use it as a context manager)."""

    def __init__(self, path: Any = DEFAULT_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: autocommit, so claim() can own its BEGIN IMMEDIATE.
        # S110: a 30 s busy timeout so a concurrent seed/read never kills the runner with "database is locked"
        self._c = sqlite3.connect(str(self.path), isolation_level=None, timeout=30.0)
        self._c.row_factory = sqlite3.Row
        self._c.execute("PRAGMA foreign_keys=ON")
        self._c.executescript(_SCHEMA)
        # Additive migration for DBs created before S66 / S135 / S74.
        for table, additions in (("queue", (("lease_until", "TEXT"), ("claimer", "TEXT"))),
                                 ("result", (("screen_p", "REAL"),))):
            columns = {row[1] for row in self._c.execute("PRAGMA table_info({0})".format(table))}
            for column, data_type in additions:
                if column not in columns:
                    self._c.execute(
                        "ALTER TABLE {0} ADD COLUMN {1} {2}".format(table, column, data_type))

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
        fields = _RESULT_FIELDS + (("screen_p",) if "screen_p" in row else ())
        self._c.execute(
            "INSERT INTO result({0}) VALUES({1})".format(
                ", ".join(fields), ",".join("?" * len(fields))),
            tuple(row[name] for name in fields))
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

    def family_p_values(self, family: str, tier: Optional[str] = None) -> list:
        """Raw p-values of every scored trial already recorded for ONE frozen family (S59).

        What a within-family BH/BY bar is computed over. Read-only: indexing is not a
        trial, so this costs the FWER ledger nothing and cannot re-score a stored verdict.
        """
        if tier is None:
            rows = self._c.execute(
                "SELECT r.raw_p FROM result r JOIN hypothesis h ON h.hash = r.hash "
                "WHERE h.family = ? AND r.raw_p IS NOT NULL ORDER BY r.id", (family,)).fetchall()
        elif tier == "T1":
            rows = self._c.execute(
                "SELECT r.screen_p FROM result r JOIN hypothesis h ON h.hash = r.hash "
                "WHERE h.family = ? AND r.tier = 'T1' AND r.screen_p IS NOT NULL ORDER BY r.id",
                (family,)).fetchall()
        else:
            rows = self._c.execute(
                "SELECT r.raw_p FROM result r JOIN hypothesis h ON h.hash = r.hash "
                "WHERE h.family = ? AND r.tier = ? AND r.raw_p IS NOT NULL ORDER BY r.id",
                (family, tier)).fetchall()
        return [float(row[0]) for row in rows]

    # -- queue ------------------------------------------------------------------
    def undrainable_queued(self) -> list:
        """Queued hashes no SPORT-BOUND runner can ever claim (S135). Should be empty.

        `claim(sport=...)` joins hypothesis and filters h.sport, so a row with a
        NULL/empty sport (or no hypothesis row) is invisible to every pod screener.
        `enqueue` refuses to create one; this reports what a pre-S135 seed left behind.
        """
        return [row[0] for row in self._c.execute(
            "SELECT q.hash FROM queue q LEFT JOIN hypothesis h ON h.hash = q.hash "
            "WHERE h.hash IS NULL OR h.sport IS NULL OR h.sport = '' ORDER BY q.hash")]

    def _undrainable(self, hashes: list) -> list:
        """Which of `hashes` have no claimable sport. Chunked: a pod seed queues thousands."""
        bad = []
        for start in range(0, len(hashes), _SQL_VARS):
            chunk = hashes[start:start + _SQL_VARS]
            ok = {row[0] for row in self._c.execute(
                "SELECT hash FROM hypothesis WHERE sport IS NOT NULL AND sport <> '' "
                "AND hash IN ({0})".format(",".join("?" * len(chunk))), chunk)}
            bad.extend(h for h in chunk if h not in ok)
        return bad

    def enqueue(self, hashes: Iterable[str], tier: str) -> int:
        """Queue hypotheses for a tier. Already-queued hashes are left alone.

        S135: REFUSED AT SEED TIME, reason named, if any hypothesis has no claimable
        sport -- that row would be one a sport-bound runner can NEVER drain. Fix the
        seed, not the queue.
        """
        now = _now()
        hashes = list(hashes)
        undrainable = self._undrainable(hashes)
        if undrainable:
            raise ValueError(
                "refusing to queue {0} of {1} hypotheses with no claimable sport (NULL/empty "
                "sport, or no hypothesis row): claim() filters on h.sport, so a sport-bound "
                "runner could never drain them. First: {2}".format(
                    len(undrainable), len(hashes), ", ".join(sorted(undrainable)[:5])))
        rows = [(h, tier, now) for h in hashes]
        self._c.executemany(
            "INSERT OR IGNORE INTO queue(hash, tier, enqueued_at, claimed_at) "
            "VALUES(?,?,?,NULL)", rows)
        return len(rows)

    def reap_expired(self, now: Optional[str] = None, owner: Optional[str] = None) -> int:
        """Return expired or dead-same-host claims to the unprocessed queue."""
        stamp = now or _now()
        candidates = self._c.execute(
            "SELECT hash, lease_until, claimer FROM queue WHERE claimed_at IS NOT NULL").fetchall()
        hashes = [row["hash"] for row in candidates if (owner is None or row["claimer"] != owner)
                  and ((row["lease_until"] is not None and row["lease_until"] <= stamp)
                       or dead_same_host_claimer(row["claimer"]))]
        if not hashes:
            return 0
        cursor = self._c.executemany(
            "UPDATE queue SET claimed_at=NULL, lease_until=NULL, claimer=NULL WHERE hash=?",
            [(hash,) for hash in hashes])
        return int(cursor.rowcount)

    def renew(self, hashes: Iterable[str], lease_seconds: float = LEASE_SECONDS,
              now: Optional[str] = None) -> int:
        """Push a still-claimed row's lease forward -- the heartbeat (S135).

        Only STILL-CLAIMED rows move: a reaped or released row is not silently
        re-taken, which would be a re-claim loop wearing a heartbeat's clothes.
        """
        stamp = now or _now()
        until = (datetime.fromisoformat(stamp) + timedelta(seconds=float(lease_seconds))).isoformat()
        return int(self._c.executemany(
            "UPDATE queue SET lease_until=? WHERE hash=? AND claimed_at IS NOT NULL",
            [(until, h) for h in hashes]).rowcount)

    def release(self, hashes: Optional[Iterable[str]] = None, *, claimer: Optional[str] = None) -> int:
        """Hand unfinished claims back by hash (legacy) or process claimer (S150)."""
        if claimer is None and isinstance(hashes, str) and ":" in hashes:
            claimer, hashes = hashes, None
        sql = ("UPDATE queue SET claimed_at=NULL, lease_until=NULL, claimer=NULL WHERE "
               "NOT EXISTS (SELECT 1 FROM result WHERE result.hash=queue.hash "
               "AND result.tier=queue.tier)")
        if claimer is not None:
            return int(self._c.execute(sql + " AND claimer=?", (claimer,)).rowcount)
        return int(self._c.executemany(
            "UPDATE queue SET claimed_at=NULL, lease_until=NULL, claimer=NULL WHERE hash=?",
            [(hash,) for hash in hashes or ()]).rowcount)

    def claim(self, n: int, tier: Optional[str] = None,
              lease_seconds: Optional[float] = None, sport: Optional[str] = None,
              owner: Optional[str] = None) -> list:
        """Claim up to n hypotheses atomically; default lease caps at five intervals."""
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
            self.reap_expired(stamp, owner=owner)
            hashes = [row[0] for row in self._c.execute(sql, args).fetchall()]
            if hashes:
                lease = (LEASE_SECONDS * min(len(hashes), 5) if lease_seconds is None
                         else float(lease_seconds))
                until = (datetime.fromisoformat(stamp)          # all stamps are UTC,
                         + timedelta(seconds=lease)).isoformat()
                self._c.executemany(
                    "UPDATE queue SET claimed_at=?, lease_until=?, claimer=? WHERE hash=?",
                    [(stamp, until, owner, h) for h in hashes])
            rows = [self._c.execute("SELECT * FROM hypothesis WHERE hash=?", (h,)).fetchone()
                    for h in hashes]
            self._c.execute("COMMIT")
        except Exception:
            self._c.execute("ROLLBACK")
            raise
        return [_hypothesis(row) for row in rows if row is not None]
