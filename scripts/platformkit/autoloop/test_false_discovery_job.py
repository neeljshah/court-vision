"""Per-file test for scripts.platformkit.autoloop.false_discovery_job.

Acceptance criteria (PREREG R1/R2, docs/research/PREREG_ALPHA_BUDGETS.md):
1. accounting_row: R1 schema, NOT_TESTABLE contributes 0 expectation but
   counts toward n_tested, R2 within_noise_floor True when observed<=ceil(expected).
2. R2 within_noise_floor False when observed_survivors exceeds the ceiling.
3. Replication rows (replication_of set) excluded from discovery accounting.
4. Backfill: one row per completed date with >=1 discovery row; today-so-far
   is never accounted.
5. Idempotent: a date already in the FDR ledger is never re-appended.
6. No-new-dates clean no-op still stamps the watermark.
7. Append failure for one date isolates (errors recorded, watermark withheld,
   d1e8eccb retry-next-tick convention) without blocking sibling dates.
8. Registration: false_discovery_accounting appears in maintenance_templates._JOB_TABLE.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_false_discovery_job.py -q
"""
from __future__ import annotations

from datetime import date

from scripts.platformkit.autoloop import false_discovery_job as FDJ


def _row(cid, tid, verdict, computed_at, alpha_fwer=None, replication_of=None):
    row = {"candidate_id": cid, "template_id": tid, "verdict": verdict,
          "computed_at": computed_at, "alpha_fwer": alpha_fwer}
    if replication_of is not None:
        row["replication_of"] = replication_of
    return row


def test_accounting_row_r1_schema_and_r2_within_noise_floor():
    rows = [
        _row("a1", "fam_a", "NULL", "2026-07-09T00:00:00Z", alpha_fwer=0.05),
        _row("a2", "fam_a", "NULL", "2026-07-09T01:00:00Z", alpha_fwer=0.05),
        _row("a3", "fam_a", "NOT_TESTABLE", "2026-07-09T02:00:00Z", alpha_fwer=None),
    ]
    row = FDJ.accounting_row("2026-07-09", rows)
    assert row["date"] == "2026-07-09"
    assert row["n_tested"] == 3  # NOT_TESTABLE counts toward n_tested
    assert row["families_touched"] == ["fam_a"]
    assert row["expected_false_survivors"] == 0.1  # NOT_TESTABLE contributes 0
    assert row["alpha_used"] == FDJ.DEFAULT_EPS
    assert row["observed_survivors"] == 0
    assert row["survivor_ids"] == []
    assert row["within_noise_floor"] is True  # 0 <= ceil(0.1)=1


def test_r2_within_noise_floor_false_when_survivors_exceed_ceiling():
    rows = [_row("s%d" % i, "fam_a", "SURVIVES_PREREG_PROVISIONAL", "2026-07-09T00:00:00Z",
                alpha_fwer=0.01) for i in range(3)]
    row = FDJ.accounting_row("2026-07-09", rows)
    assert row["observed_survivors"] == 3
    assert row["expected_false_survivors"] == 0.03
    assert row["within_noise_floor"] is False  # 3 > ceil(0.03)=1


def test_replication_rows_excluded_from_discovery_accounting():
    rows = [
        _row("a1", "fam_a", "NULL", "2026-07-09T00:00:00Z", alpha_fwer=0.05),
        _row("repl_a1", "fam_a", "REPLICATED", "2026-07-09T05:00:00Z", replication_of="a1"),
    ]
    by_date = FDJ._discovery_rows_by_date(rows)
    assert len(by_date["2026-07-09"]) == 1
    assert by_date["2026-07-09"][0]["candidate_id"] == "a1"


def test_run_backfills_completed_dates_and_skips_today(tmp_path):
    src = tmp_path / "source.jsonl"
    fdr = tmp_path / "fdr.jsonl"
    rows = [
        _row("a1", "fam_a", "NULL", "2026-07-09T00:00:00Z", alpha_fwer=0.05),
        _row("b1", "fam_a", "NULL", "2026-07-10T00:00:00Z", alpha_fwer=0.05),
        _row("c1", "fam_a", "NULL", "2026-07-13T00:00:00Z", alpha_fwer=0.05),  # today: excluded
    ]
    watermarks: dict = {}
    out = FDJ.run_false_discovery_accounting(
        watermarks, source_ledger_path=src, fdr_ledger_path=fdr,
        load_source_fn=lambda p: rows, today=date(2026, 7, 13))
    assert out["dates_appended"] == ["2026-07-09", "2026-07-10"]
    assert out["watermark_stamped"] is True
    assert FDJ.STATE_KEY in watermarks
    appended_rows = list(FDJ._iter_jsonl(fdr))
    assert {r["date"] for r in appended_rows} == {"2026-07-09", "2026-07-10"}


def test_idempotent_second_run_no_duplicate_dates(tmp_path):
    src = tmp_path / "source.jsonl"
    fdr = tmp_path / "fdr.jsonl"
    rows = [_row("a1", "fam_a", "NULL", "2026-07-09T00:00:00Z", alpha_fwer=0.05)]
    watermarks: dict = {}
    FDJ.run_false_discovery_accounting(
        watermarks, source_ledger_path=src, fdr_ledger_path=fdr,
        load_source_fn=lambda p: rows, today=date(2026, 7, 13))
    out2 = FDJ.run_false_discovery_accounting(
        watermarks, source_ledger_path=src, fdr_ledger_path=fdr,
        load_source_fn=lambda p: rows, today=date(2026, 7, 13))
    assert out2["dates_appended"] == []
    assert out2["watermark_stamped"] is True
    assert len(list(FDJ._iter_jsonl(fdr))) == 1


def test_no_new_dates_clean_noop_stamps_watermark(tmp_path):
    fdr = tmp_path / "fdr.jsonl"
    watermarks: dict = {}
    out = FDJ.run_false_discovery_accounting(
        watermarks, source_ledger_path=tmp_path / "missing.jsonl", fdr_ledger_path=fdr,
        load_source_fn=lambda p: [], today=date(2026, 7, 13))
    assert out["dates_appended"] == []
    assert out["watermark_stamped"] is True
    assert FDJ.STATE_KEY in watermarks


def test_append_failure_isolated_no_watermark_stamp(tmp_path):
    src = tmp_path / "source.jsonl"
    fdr = tmp_path / "fdr.jsonl"
    rows = [
        _row("a1", "fam_a", "NULL", "2026-07-09T00:00:00Z", alpha_fwer=0.05),
        _row("b1", "fam_a", "NULL", "2026-07-10T00:00:00Z", alpha_fwer=0.05),
    ]

    def boom_append(row, path):
        if row["date"] == "2026-07-09":
            raise RuntimeError("disk boom")
        FDJ.append_row(row, path=path)

    watermarks: dict = {}
    out = FDJ.run_false_discovery_accounting(
        watermarks, source_ledger_path=src, fdr_ledger_path=fdr,
        load_source_fn=lambda p: rows, today=date(2026, 7, 13), append_fn=boom_append)
    assert "2026-07-09" in out["errors"]
    assert out["dates_appended"] == ["2026-07-10"]
    assert out["watermark_stamped"] is False
    assert FDJ.STATE_KEY not in watermarks

    # retry next tick: 07-09 still unaccounted (never marked done), 07-10 not reprocessed
    out2 = FDJ.run_false_discovery_accounting(
        watermarks, source_ledger_path=src, fdr_ledger_path=fdr,
        load_source_fn=lambda p: rows, today=date(2026, 7, 13))
    assert out2["dates_appended"] == ["2026-07-09"]
    assert out2["watermark_stamped"] is True


def test_registered_in_job_table():
    from scripts.platformkit.autoloop import maintenance_templates as MT
    keys = [row[0] for row in MT._JOB_TABLE]
    assert "false_discovery_accounting" in keys
    row = next(r for r in MT._JOB_TABLE if r[0] == "false_discovery_accounting")
    assert row[1] == "scripts.platformkit.autoloop.false_discovery_job"
    assert row[2] == "run_false_discovery_accounting"
    assert "watermarks" in row[3]
