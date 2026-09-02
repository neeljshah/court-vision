"""CONSTRUCT checks for the foundry results DB (S15).

The headline case: the SAME hypothesis proposed twice at T2 yields 1 charged
trial + 1 lookup, and a TMP FWER ledger's K is UNCHANGED on the second proposal.
The real ledger (data/cache/eval_gate/backtest_fwer.jsonl) is never touched --
every _charge_ledger call here is against tmp_path.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from scripts.platformkit.eval_gate.backtest_runner import _charge_ledger
from scripts.platformkit.eval_gate.deflated_metrics import deflated_p
from scripts.platformkit.foundry.grammar import Hypothesis, semantic_hash
from scripts.platformkit.foundry.results_db import (
    ResultsDB, TierResult, recompute_deflated_p, trial_artifact_path)

CONDITIONING = frozenset(("phase=period", "rest=NORMAL", "month=2026-09", "confidence=T2"))
HYPOTHESIS = Hypothesis("nba", "pace_diff_asof", "ew", (("halflife", 5),), CONDITIONING,
                        "pregame", "ml")
CORPUS, UNIT, SHA, TIER = "nba_gate_v3", "game", "sha_corpus_v1", "T2"


def _db(tmp_path):
    return ResultsDB(tmp_path / "hypotheses.sqlite")


def _k(ledger):
    """Current global K in a ledger file: 0 when it does not exist yet."""
    if not ledger.exists():
        return 0
    rows = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    return max((int(r["k_cumulative"]) for r in rows), default=0)


def _propose(db, hypothesis, ledger, k_now=None):
    """The proposer contract: look up first, charge only on a miss.

    Returns ("lookup", row) or ("trial", row). Indexing is not a trial.
    """
    digest = db.upsert_hypothesis(hypothesis, family="pace")
    hit = db.lookup(digest, TIER, CORPUS, UNIT, SHA, k_now=k_now)
    if hit is not None:
        return "lookup", hit
    charge = _charge_ledger(ledger, "spec:pace", "nba", "2024-10-01", "2025-04-01",
                            family="pace", hypothesis_hash=digest, tier=TIER)
    db.record(TierResult(
        hash=digest, tier=TIER, corpus=CORPUS, corpus_unit=UNIT, corpus_sha=SHA,
        n=412, n_eff=380.5, brier_model=0.2201, brier_close=0.2198, dm_stat=-0.41,
        raw_p=0.34, k_family=charge.get("k_family"), k_global=charge["k_cumulative"],
        deflated_p=deflated_p(0.34, charge["k_cumulative"]), pbo=0.48, verdict="MATCH",
        artifact_path=str(trial_artifact_path(digest, TIER, UNIT)),
        prereg_sha256="0" * 64))
    return "trial", db.lookup(digest, TIER, CORPUS, UNIT, SHA, k_now=k_now)


def test_reproposal_is_a_lookup_and_charges_nothing(tmp_path):
    """Denominator = 2 proposals of the same hash. Bar = 1 trial + 1 lookup, K flat."""
    ledger = tmp_path / "backtest_fwer.jsonl"
    with _db(tmp_path) as db:
        first_kind, _ = _propose(db, HYPOTHESIS, ledger)
        k_after_first = _k(ledger)
        second_kind, second = _propose(db, HYPOTHESIS, ledger)
        k_after_second = _k(ledger)

        assert (first_kind, second_kind) == ("trial", "lookup")
        assert k_after_first == 1 and k_after_second == 1  # K UNCHANGED on re-proposal
        assert db._c.execute("SELECT COUNT(*) FROM result").fetchone()[0] == 1
        assert second["k_at_run"] == 1


def test_changed_corpus_sha_is_a_fresh_trial(tmp_path):
    """SF-13: corpus_sha is in the UNIQUE key, so a changed corpus never hits."""
    with _db(tmp_path) as db:
        digest = db.upsert_hypothesis(HYPOTHESIS)
        db.record(_result(digest, corpus_sha=SHA))
        assert db.lookup(digest, TIER, CORPUS, UNIT, SHA) is not None
        assert db.lookup(digest, TIER, CORPUS, UNIT, "sha_corpus_v2") is None
        db.record(_result(digest, corpus_sha="sha_corpus_v2"))
        assert db._c.execute("SELECT COUNT(*) FROM result").fetchone()[0] == 2


def test_stale_k_lookup_flags_rescore(tmp_path):
    """SF-14: never serve the stored deflated_p as current once K has moved."""
    with _db(tmp_path) as db:
        digest = db.upsert_hypothesis(HYPOTHESIS)
        db.record(_result(digest, k_global=3, raw_p=0.02, deflated_p=deflated_p(0.02, 3)))
        same = db.lookup(digest, TIER, CORPUS, UNIT, SHA, k_now=3)
        assert same["verdict_needs_rescore"] is False and same["k_at_run"] == 3
        stale = db.lookup(digest, TIER, CORPUS, UNIT, SHA, k_now=14)
        assert stale["verdict_needs_rescore"] is True and stale["k_at_run"] == 3
        assert stale["deflated_p"] == pytest.approx(0.06)
        assert recompute_deflated_p(stale, 14) == pytest.approx(0.28)


def test_same_hash_different_raw_params_raises(tmp_path):
    """SF-12: a grid-snap collision is surfaced as IntegrityError, never merged."""
    other = Hypothesis("nba", "pace_diff_asof", "raw", (("unused", "a"),), CONDITIONING,
                       "pregame", "ml")
    twin = Hypothesis("nba", "pace_diff_asof", "raw", (("unused", "b"),), CONDITIONING,
                      "pregame", "ml")
    assert semantic_hash(other) == semantic_hash(twin)  # unused params are grid-snapped away
    with _db(tmp_path) as db:
        db.upsert_hypothesis(other)
        db.upsert_hypothesis(other)  # identical raw params -> idempotent
        with pytest.raises(sqlite3.IntegrityError):
            db.upsert_hypothesis(twin)


def test_round_trip_every_column(tmp_path):
    with _db(tmp_path) as db:
        digest = db.upsert_hypothesis(HYPOTHESIS, family="pace", runtime_available=False,
                                      grammar_version="s11", created_at="2026-09-03T00:00:00+00:00")
        hypothesis_row = dict(db._c.execute("SELECT * FROM hypothesis").fetchone())
        assert hypothesis_row == {
            "hash": digest, "family": "pace", "sport": "nba", "feature": "pace_diff_asof",
            "transform": "ew", "params": '[["halflife", 5]]',
            "conditioning": json.dumps(sorted(CONDITIONING)), "horizon": "pregame",
            "market": "ml", "runtime_available": 0, "created_at": "2026-09-03T00:00:00+00:00",
            "grammar_version": "s11"}
        # S66: family / runtime_available now survive the round trip. Before the fix
        # this read back as HYPOTHESIS (family="") -- the stored "pace" was dropped.
        assert db.get_hypothesis(digest) == replace(
            HYPOTHESIS, family="pace", runtime_available=False)

        db.record(_result(digest))
        row = db.lookup(digest, TIER, CORPUS, UNIT, SHA)
        expected = {"id": 1, "hash": digest, "tier": TIER, "corpus": CORPUS,
                    "corpus_unit": UNIT, "corpus_sha": SHA, "n": 412, "n_eff": 380.5,
                    "brier_model": 0.2201, "brier_close": 0.2198, "dm_stat": -0.41,
                    "raw_p": 0.34, "k_family": 1, "k_global": 7, "deflated_p": 1.0,
                    "pbo": 0.48, "verdict": "MATCH",
                    "artifact_path": str(trial_artifact_path(digest, TIER, UNIT)),
                    "prereg_sha256": "0" * 64, "run_at": "2026-09-03T01:00:00+00:00",
                    "k_at_run": 7, "verdict_needs_rescore": False}
        assert row == expected
        assert str(trial_artifact_path(digest, TIER, UNIT)).endswith(
            "{0}_{1}_{2}.json".format(digest, TIER, UNIT))


def test_unique_constraint_rejects_a_duplicate_trial(tmp_path):
    with _db(tmp_path) as db:
        digest = db.upsert_hypothesis(HYPOTHESIS)
        db.record(_result(digest))
        with pytest.raises(sqlite3.IntegrityError):
            db.record(_result(digest))


def test_claim_is_atomic(tmp_path):
    with _db(tmp_path) as db:
        hashes = []
        for halflife in (3, 5, 10):
            hypothesis = Hypothesis("nba", "pace_diff_asof", "ew", (("halflife", halflife),),
                                    CONDITIONING, "pregame", "ml")
            hashes.append(db.upsert_hypothesis(hypothesis))
        assert db.enqueue(hashes, TIER) == 3
        db.enqueue(hashes, TIER)  # re-enqueue does not duplicate
        assert db._c.execute("SELECT COUNT(*) FROM queue").fetchone()[0] == 3

        first = db.claim(2, tier=TIER)
        second = db.claim(2, tier=TIER)
        assert len(first) == 2 and len(second) == 1
        claimed = {semantic_hash(h) for h in first + second}
        assert claimed == set(hashes)  # each row claimed exactly once
        assert db.claim(2, tier=TIER) == []
        assert db._c.execute(
            "SELECT COUNT(*) FROM queue WHERE claimed_at IS NULL").fetchone()[0] == 0


def _result(hash, **overrides):
    fields = dict(hash=hash, tier=TIER, corpus=CORPUS, corpus_unit=UNIT, corpus_sha=SHA,
                  n=412, n_eff=380.5, brier_model=0.2201, brier_close=0.2198, dm_stat=-0.41,
                  raw_p=0.34, k_family=1, k_global=7, deflated_p=deflated_p(0.34, 7), pbo=0.48,
                  verdict="MATCH", artifact_path=str(trial_artifact_path(hash, TIER, UNIT)),
                  prereg_sha256="0" * 64, run_at="2026-09-03T01:00:00+00:00")
    fields.update(overrides)
    return TierResult(**fields)


# --- S66: claim leases + family round trip -----------------------------------

def _plus(seconds):
    """An ISO-UTC stamp `seconds` from now -- what a lease is compared against."""
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _queued(db, halflives=(3, 5, 10), sport="nba", family="pace"):
    """Upsert and queue one hypothesis per halflife. Returns the hashes."""
    hashes = []
    for halflife in halflives:
        hypothesis = Hypothesis(sport, "pace_diff_asof", "ew", (("halflife", halflife),),
                                CONDITIONING, "pregame", "ml", family=family)
        hashes.append(db.upsert_hypothesis(hypothesis))
    db.enqueue(hashes, TIER)
    return hashes


def test_expired_claim_is_reclaimable_after_the_lease_never_before(tmp_path):
    """B4: a claimer that DIES (never releases, never records) strands nothing."""
    with _db(tmp_path) as db:
        _queued(db)
        assert len(db.claim(3, tier=TIER, lease_seconds=900)) == 3
        # the claimer dies here -- no release, no record.
        assert db.claim(3, tier=TIER) == []              # never before the lease
        row = db._c.execute("SELECT claimed_at, lease_until FROM queue").fetchone()
        assert row["claimed_at"] is not None and row["lease_until"] > row["claimed_at"]

        assert db.reap_expired(_plus(899)) == 0          # still inside the lease
        assert db.claim(3, tier=TIER) == []
        assert db.reap_expired(_plus(901)) == 3          # after it
        assert len(db.claim(3, tier=TIER)) == 3          # reclaimable


def test_claim_reaps_expired_rows_itself(tmp_path):
    """The reap runs INSIDE claim, so a claimer cannot forget to call it."""
    with _db(tmp_path) as db:
        _queued(db)
        assert len(db.claim(3, tier=TIER, lease_seconds=-1)) == 3   # already expired
        assert len(db.claim(3, tier=TIER)) == 3


def test_release_frees_a_claim_before_the_lease(tmp_path):
    with _db(tmp_path) as db:
        hashes = _queued(db)
        assert len(db.claim(3, tier=TIER)) == 3
        assert db.release(hashes[:2]) == 2
        assert len(db.claim(3, tier=TIER)) == 2


def test_pre_lease_claim_is_never_auto_reaped(tmp_path):
    """A row claimed before S66 has lease_until NULL: only release() frees it."""
    with _db(tmp_path) as db:
        hashes = _queued(db)
        db.claim(3, tier=TIER)
        db._c.execute("UPDATE queue SET lease_until=NULL")
        assert db.reap_expired(_plus(100000)) == 0
        assert db.release(hashes) == 3


def test_claimed_hypothesis_round_trips_its_family(tmp_path):
    with _db(tmp_path) as db:
        _queued(db, halflives=(3,), family="pace")
        claimed = db.claim(1, tier=TIER)
        assert [h.family for h in claimed] == ["pace"]


def test_mixed_queue_claims_group_per_family(tmp_path):
    """What run_pass counts per family: the claim itself must carry the family,
    or every row falls through to the queue's single sport label."""
    with _db(tmp_path) as db:
        _queued(db, halflives=(3, 5), sport="nba", family="nba_pace")
        _queued(db, halflives=(10, 20), sport="soccer", family="soccer_form")
        groups = {}
        for hypothesis in db.claim(10, tier=TIER):
            groups[hypothesis.family] = groups.get(hypothesis.family, 0) + 1
        assert groups == {"nba_pace": 2, "soccer_form": 2}


# --- S75: a claim may be filtered to ONE sport ---------------------------------

def test_claim_with_a_sport_never_returns_another_sports_row(tmp_path):
    """A screener bound to one corpus must not be handed a hypothesis of another sport."""
    with _db(tmp_path) as db:
        _queued(db, halflives=(3, 5), sport="nba", family="nba_pace")
        _queued(db, halflives=(10, 20), sport="soccer", family="soccer_form")
        nba = db.claim(10, tier=TIER, sport="nba")
        assert [h.sport for h in nba] == ["nba", "nba"]
        soccer = db.claim(10, tier=TIER, sport="soccer")
        assert [h.sport for h in soccer] == ["soccer", "soccer"]
        assert db.claim(10, tier=TIER, sport="tennis") == []      # nothing queued, nothing stolen
        assert db.claim(10, tier=TIER) == []                      # all four already claimed


def test_an_unfiltered_claim_is_unchanged_by_the_sport_argument(tmp_path):
    """sport=None is the pre-S75 behaviour: claim across every sport in queue order."""
    with _db(tmp_path) as db:
        _queued(db, halflives=(3,), sport="nba", family="nba_pace")
        _queued(db, halflives=(10,), sport="soccer", family="soccer_form")
        assert sorted(h.sport for h in db.claim(10, tier=TIER)) == ["nba", "soccer"]
