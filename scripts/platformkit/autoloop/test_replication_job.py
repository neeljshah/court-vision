"""Per-file test for scripts.platformkit.autoloop.replication_job.

Acceptance criteria:
1. No pending survivors -> clean no-op, watermark still stamped (success).
2. Pending-survivor selection: a SURVIVES row with no replication_of pointer
   anywhere in the ledger is pending; one that already has a replication row
   is not; a non-SURVIVES latest verdict is not.
3. A family's worker raising -> that family reports "error", watermark NOT
   stamped (PARTIAL/FAILED retries next tick, commit d1e8eccb's lesson).
4. Bounded batch: a family whose pending count exceeds max_per_tick is
   deferred, not run; other families under budget still run.
5. A family with no registered worker is reported NO_WORKER_REGISTERED, not
   attempted, and never blocks a sibling family from running.
6. Registration: replication_cadence appears in maintenance_templates._JOB_TABLE.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_replication_job.py -q
"""
from __future__ import annotations

from scripts.platformkit.autoloop import replication_job as RJ


def _row(cid, tid, verdict="SURVIVES_PREREG_PROVISIONAL", computed_at="2026-07-13T00:00:00Z",
         replication_of=None):
    row = {"candidate_id": cid, "template_id": tid, "verdict": verdict, "computed_at": computed_at}
    if replication_of is not None:
        row["replication_of"] = replication_of
    return row


def test_pending_survivors_join_key():
    rows = [
        _row("a1", "fam_a"),                                    # pending: never replicated
        _row("a2", "fam_a"),
        _row("repl_of_a2", "fam_a", verdict="REPLICATED", replication_of="a2"),  # a2 done
        _row("b1", "fam_b", verdict="NULL"),                     # not a survivor at all
    ]
    pending = RJ.pending_survivors(rows)
    assert set(pending.keys()) == {"fam_a"}
    assert [r["candidate_id"] for r in pending["fam_a"]] == ["a1"]


def test_no_pending_clean_noop_stamps_watermark():
    watermarks: dict = {}
    out = RJ.run_replication_cadence(watermarks, load_ledger_fn=lambda p: [])
    assert out["status"] == "ran"
    assert out["total_pending"] == 0
    assert out["families"] == {}
    assert out["watermark_stamped"] is True
    assert RJ.STATE_KEY in watermarks


def test_worker_runs_for_pending_family_and_stamps():
    rows = [_row("a1", "fam_a")]
    calls = []

    def worker(ledger_path=None):
        calls.append(ledger_path)
        return [{"candidate_id": "a1", "verdict": "REPLICATED"}]

    watermarks: dict = {}
    out = RJ.run_replication_cadence(
        watermarks, load_ledger_fn=lambda p: rows, family_workers={"fam_a": worker})
    assert calls == [RJ.IFR.LEDGER_PATH]
    assert out["families"]["fam_a"]["status"] == "ran"
    assert out["families"]["fam_a"]["n_appended"] == 1
    assert out["families_ran"] == 1
    assert out["watermark_stamped"] is True
    assert watermarks[RJ.STATE_KEY]["total_pending_at_run"] == 1


def test_shared_worker_called_once_across_family_keys():
    """One worker registered under TWO family keys (the batch2b shape) must be
    invoked exactly once per tick -- a second call re-appends the sibling
    family's rows (the 07-13 double-fire)."""
    rows = [_row("a1", "fam_a"), _row("b1", "fam_b")]
    calls = []

    def shared(ledger_path=None):
        calls.append(ledger_path)
        return [{"candidate_id": "a1", "verdict": "REPLICATED"},
                {"candidate_id": "b1", "verdict": "REPLICATED"}]

    watermarks: dict = {}
    out = RJ.run_replication_cadence(
        watermarks, load_ledger_fn=lambda p: rows,
        family_workers={"fam_a": shared, "fam_b": shared})
    assert len(calls) == 1
    assert out["families"]["fam_a"]["status"] == "ran"
    assert out["families"]["fam_b"] == {"status": "ran_shared", "n_pending": 1,
                                        "via_family": "fam_a"}
    assert out["watermark_stamped"] is True


def test_worker_raising_isolated_no_watermark_stamp():
    rows = [_row("a1", "fam_a"), _row("b1", "fam_b")]

    def boom(ledger_path=None):
        raise RuntimeError("fit boom")

    def ok(ledger_path=None):
        return [{"candidate_id": "b1"}]

    watermarks: dict = {}
    out = RJ.run_replication_cadence(
        watermarks, load_ledger_fn=lambda p: rows,
        family_workers={"fam_a": boom, "fam_b": ok})
    assert out["families"]["fam_a"]["status"] == "error"
    assert "fit boom" in out["families"]["fam_a"]["error"]
    # sibling family still ran despite fam_a's raise
    assert out["families"]["fam_b"]["status"] == "ran"
    assert out["watermark_stamped"] is False
    assert RJ.STATE_KEY not in watermarks


def test_bounded_batch_defers_family_over_budget():
    rows = [_row("a1", "fam_a"), _row("a2", "fam_a"), _row("a3", "fam_a"),
            _row("b1", "fam_b")]
    calls = []

    def worker_a(ledger_path=None):
        calls.append("fam_a")
        return []

    def worker_b(ledger_path=None):
        calls.append("fam_b")
        return []

    watermarks: dict = {}
    out = RJ.run_replication_cadence(
        watermarks, load_ledger_fn=lambda p: rows, max_per_tick=2,
        family_workers={"fam_a": worker_a, "fam_b": worker_b})
    assert out["families"]["fam_a"]["status"] == "deferred_bound"  # 3 pending > budget 2
    assert out["families"]["fam_b"]["status"] == "ran"             # 1 pending <= budget
    assert calls == ["fam_b"]
    # deferred family did not error -> a clean defer still stamps the watermark
    assert out["watermark_stamped"] is True


def test_no_worker_registered_reported_and_isolated():
    rows = [_row("a1", "fam_unmapped"), _row("b1", "fam_b")]
    calls = []

    def worker_b(ledger_path=None):
        calls.append("fam_b")
        return []

    watermarks: dict = {}
    out = RJ.run_replication_cadence(
        watermarks, load_ledger_fn=lambda p: rows,
        family_workers={"fam_b": worker_b})
    assert out["families"]["fam_unmapped"]["status"] == "NO_WORKER_REGISTERED"
    assert out["no_worker_registered"] == {"fam_unmapped": 1}
    assert out["families"]["fam_b"]["status"] == "ran"
    assert calls == ["fam_b"]
    assert out["watermark_stamped"] is True  # no_worker is not an error


def test_dry_run_lists_without_calling_worker():
    rows = [_row("a1", "fam_a")]
    calls = []

    def worker(ledger_path=None):
        calls.append("called")
        return []

    out = RJ.dry_run(ledger_path=RJ.IFR.LEDGER_PATH, family_workers={"fam_a": worker})
    # dry_run reads the REAL ledger (no injection point for load) -- just assert
    # it never calls the worker regardless of what it finds.
    assert calls == []
    assert isinstance(out, dict)


def test_reserved_corpus_row_routes_to_generic_worker_over_family_map():
    """R2: a pending row carrying reserved_corpus routes to RR.replicate
    FIRST, even when a per-template worker is ALSO registered for that
    family -- the fallback map never wins once a row is reserved."""
    rows = [_row("a1", "fam_a")]
    rows[0]["reserved_corpus"] = "2023"
    calls = []

    def rr_stub(ledger_path=None):
        calls.append("RR")
        return [{"candidate_id": "a1", "verdict": "REPLICATED"}]

    def family_stub(ledger_path=None):
        calls.append("family_map")
        return []

    watermarks: dict = {}
    orig_replicate = RJ.RR.replicate
    RJ.RR.replicate = rr_stub
    try:
        out = RJ.run_replication_cadence(
            watermarks, load_ledger_fn=lambda p: rows, family_workers={"fam_a": family_stub})
    finally:
        RJ.RR.replicate = orig_replicate
    assert calls == ["RR"]
    assert out["families"]["fam_a"]["status"] == "ran"
    assert out["watermark_stamped"] is True


def test_no_reserved_corpus_still_falls_back_to_family_map():
    """No row carries reserved_corpus -> unchanged pre-R2 behavior (the
    per-template map wins), same premise every pre-spec survivor still has."""
    rows = [_row("a1", "fam_a")]  # no reserved_corpus key at all
    calls = []

    def family_stub(ledger_path=None):
        calls.append("family_map")
        return []

    watermarks: dict = {}
    out = RJ.run_replication_cadence(
        watermarks, load_ledger_fn=lambda p: rows, family_workers={"fam_a": family_stub})
    assert calls == ["family_map"]
    assert out["families"]["fam_a"]["status"] == "ran"


def test_registered_in_job_table():
    from scripts.platformkit.autoloop import maintenance_templates as MT
    keys = [row[0] for row in MT._JOB_TABLE]
    assert "replication_cadence" in keys
    row = next(r for r in MT._JOB_TABLE if r[0] == "replication_cadence")
    assert row[1] == "scripts.platformkit.autoloop.replication_job"
    assert row[2] == "run_replication_cadence"
    assert "watermarks" in row[3]
