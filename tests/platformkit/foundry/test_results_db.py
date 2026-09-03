"""Claim, lease, and reap checks for the foundry results DB.

S155 split (2026-09-04): the real ledger data/cache/eval_gate/backtest_fwer.jsonl is never touched -- every _charge_ledger call here is against tmp_path.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts.platformkit.foundry.grammar import Hypothesis, semantic_hash
from scripts.platformkit.foundry.results_db import ResultsDB

CONDITIONING = frozenset(("phase=period", "rest=NORMAL", "month=2026-09", "confidence=T2"))
TIER = "T2"


def _db(tmp_path):
    return ResultsDB(tmp_path / "hypotheses.sqlite")


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
        assert db._c.execute("SELECT COUNT(*) FROM queue WHERE claimed_at IS NULL").fetchone()[0] == 0


# --- S66: claim leases + family round trip -----------------------------------

def _plus(seconds):
    """An ISO-UTC stamp `seconds` from now -- what a lease is compared against."""
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _queued(db, halflives=(3, 5, 10), sport="nba", family="pace"):
    """Upsert and queue one hypothesis per halflife. Returns the hashes."""
    hashes = []
    for halflife in halflives:
        hypothesis = Hypothesis(sport, "pace_diff_asof", "ew", (("halflife", halflife),), CONDITIONING, "pregame", "ml", family=family)
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


# --- S135: lease renewal, owner-scoped reaping, no undrainable queue row ---------

def test_a_renewed_lease_is_not_double_claimed_at_901_seconds(tmp_path):
    """The S135 probe: runner B claimed A's 3 rows at +901 s while A was still working."""
    with _db(tmp_path) as db:
        _queued(db)
        assert len(db.claim(3, tier=TIER, lease_seconds=900, owner="A")) == 3
        assert db.renew(_queued_hashes(db), lease_seconds=900, now=_plus(800)) == 3
        db.reap_expired(_plus(901))
        assert db.claim(3, tier=TIER, owner="B") == []       # the probe: 0 rows for B
        assert db.reap_expired(_plus(1701)) == 3             # 800 + 900, then it frees


def test_the_default_lease_scales_with_the_batch(tmp_path):
    """A claimer screens its batch serially, so 3 rows hold 3 x LEASE_SECONDS.

    An explicit lease_seconds is honoured exactly -- every pre-S135 caller unchanged.
    """
    with _db(tmp_path) as db:
        _queued(db)
        assert len(db.claim(3, tier=TIER)) == 3
        assert db.reap_expired(_plus(901)) == 0              # was 3 before S135
        assert db.reap_expired(_plus(2701)) == 3


def test_a_reap_never_frees_the_callers_own_expired_claim(tmp_path):
    """reap_expired was global: a runner whose batch outran its lease reaped and
    then re-claimed the very rows it was still screening."""
    with _db(tmp_path) as db:
        _queued(db)
        db.claim(3, tier=TIER, lease_seconds=-1, owner="A")  # already expired
        assert db.reap_expired(owner="A") == 0               # A never reaps A
        assert db.claim(3, tier=TIER, owner="A") == []
        assert db.reap_expired(owner="B") == 3               # another claimer may


def test_renew_does_not_resurrect_a_released_row(tmp_path):
    """B4: a heartbeat must not silently re-take a row somebody else now owns."""
    with _db(tmp_path) as db:
        hashes = _queued(db)
        db.claim(3, tier=TIER, owner="A")
        db.release(hashes)
        assert db.renew(hashes) == 0
        assert len(db.claim(3, tier=TIER, owner="B")) == 3


def test_a_sport_null_hypothesis_is_refused_at_seed_time(tmp_path):
    """Reproduced: claim(sport="mlb") -> 0 while claim(sport=None) -> 1, so a
    sport-bound pod runner could never drain it. Refused with a named reason."""
    with _db(tmp_path) as db:
        hypothesis = Hypothesis("nba", "pace_diff_asof", "ew", (("halflife", 3),), CONDITIONING, "pregame", "ml", family="pace")
        digest = db.upsert_hypothesis(hypothesis)
        db._c.execute("UPDATE hypothesis SET sport=NULL WHERE hash=?", (digest,))
        with pytest.raises(ValueError, match="no claimable sport"):
            db.enqueue([digest], TIER)
        assert db._c.execute("SELECT COUNT(*) FROM queue").fetchone()[0] == 0
        with pytest.raises(ValueError, match="no claimable sport"):
            db.enqueue(["a_hash_with_no_hypothesis_row"], TIER)
        assert db.undrainable_queued() == []


def test_undrainable_queued_reports_a_pre_s135_row(tmp_path):
    """A queue seeded before S135 may already hold one; the fix reports, never hides."""
    with _db(tmp_path) as db:
        hashes = _queued(db, halflives=(3,))
        db._c.execute("UPDATE hypothesis SET sport='' WHERE hash=?", (hashes[0],))
        assert db.undrainable_queued() == hashes
        assert db.claim(5, tier=TIER, sport="nba") == []


def _queued_hashes(db):
    return [row[0] for row in db._c.execute("SELECT hash FROM queue ORDER BY hash")]
