"""Per-file test for retention.line_history_consolidate (offline, tmp dir, synthetic fixtures).

Proves:
  * find_stale_month_groups only groups dailies strictly older than stale_days,
    grouped by (year, month), and never touches recent/active files;
  * write_month_archive + verify_month_archive round-trip: verify passes when the
    archive fully represents the dailies;
  * consolidate_sport_month with apply=True deletes source dailies ONLY after a
    passing verify, and with apply=False (dry-run) never writes or deletes;
  * a corrupted/short archive fails verify closed and dailies are NOT deleted.

  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/retention/test_line_history_consolidate.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pyarrow.parquet as pq

from scripts.platformkit.retention import line_history_consolidate as lhc

NOW = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)  # "today"


def _mk_daily(sport_dir, name, rows):
    sport_dir.mkdir(parents=True, exist_ok=True)
    p = sport_dir / name
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p


def _sample_rows(n, tag):
    return [{"sport": "nba", "game_id": f"g{tag}{i}", "odds": 1.5 + i * 0.01} for i in range(n)]


def test_find_stale_month_groups_excludes_recent(tmp_path):
    sd = tmp_path / "nba"
    _mk_daily(sd, "2026-07-04.jsonl", _sample_rows(2, "today"))   # active, never grouped
    _mk_daily(sd, "2026-06-20.jsonl", _sample_rows(2, "recent"))  # 14d old, not stale (30d)
    old1 = _mk_daily(sd, "2026-05-15.jsonl", _sample_rows(3, "old1"))
    old2 = _mk_daily(sd, "2026-05-20.jsonl", _sample_rows(2, "old2"))
    _mk_daily(sd, "2026-04-10.jsonl", _sample_rows(1, "ancient"))

    groups = lhc.find_stale_month_groups(sd, stale_days=30, now=NOW)
    yms = {g.year_month for g in groups}
    assert yms == {"2026-05", "2026-04"}
    may_group = next(g for g in groups if g.year_month == "2026-05")
    assert {p.name for p in may_group.files} == {old1.name, old2.name}
    assert sum(len(g.files) for g in groups) == 3


def test_write_and_verify_round_trip(tmp_path):
    sd = tmp_path / "line_history" / "nba"
    _mk_daily(sd, "2026-05-15.jsonl", _sample_rows(3, "a"))
    _mk_daily(sd, "2026-05-20.jsonl", _sample_rows(2, "b"))
    groups = lhc.find_stale_month_groups(sd, stale_days=30, now=NOW)
    assert len(groups) == 1
    group = groups[0]

    archive_root = tmp_path / "line_history_archive"
    archive_path = lhc.write_month_archive(group, archive_root)
    assert archive_path.exists()

    verify = lhc.verify_month_archive(group, archive_path)
    assert verify["ok"] is True
    assert verify["expected_rows"] == 5
    assert verify["archive_rows"] == 5

    table = pq.read_table(archive_path)
    assert "source_file" in table.column_names


def test_consolidate_apply_deletes_only_after_verify_pass(tmp_path):
    sd = tmp_path / "line_history" / "nba"
    f1 = _mk_daily(sd, "2026-05-15.jsonl", _sample_rows(3, "a"))
    f2 = _mk_daily(sd, "2026-05-20.jsonl", _sample_rows(2, "b"))
    groups = lhc.find_stale_month_groups(sd, stale_days=30, now=NOW)
    group = groups[0]
    archive_root = tmp_path / "line_history_archive"

    dry = lhc.consolidate_sport_month(group, archive_root, apply=False)
    assert dry["applied"] is False
    assert f1.exists() and f2.exists()
    assert not (archive_root / "nba" / "2026-05.parquet").exists()

    result = lhc.consolidate_sport_month(group, archive_root, apply=True)
    assert result["verified"] is True
    assert result["applied"] is True
    assert result["deleted"] == 2
    assert not f1.exists() and not f2.exists()


def test_consolidate_apply_fails_closed_on_corrupt_archive(tmp_path, monkeypatch):
    sd = tmp_path / "line_history" / "nba"
    f1 = _mk_daily(sd, "2026-05-15.jsonl", _sample_rows(3, "a"))
    groups = lhc.find_stale_month_groups(sd, stale_days=30, now=NOW)
    group = groups[0]
    archive_root = tmp_path / "line_history_archive"

    def _write_bad_archive(g, root):
        # Simulate a truncated/corrupt write: write only 1 of 3 rows.
        import pyarrow as pa
        recs, _ = lhc._read_daily_records(f1)
        table = pa.Table.from_pylist(recs[:1])
        out_path = lhc._archive_path(root, g.sport, g.year_month)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, out_path)
        return out_path

    monkeypatch.setattr(lhc, "write_month_archive", _write_bad_archive)
    result = lhc.consolidate_sport_month(group, archive_root, apply=True)
    assert result["verified"] is False
    assert result["reason"] == "row_count_mismatch"
    assert result["deleted"] == 0
    assert f1.exists()  # fail-closed: daily NOT deleted


def test_plan_all_dry_run_reports_without_side_effects(tmp_path):
    base = tmp_path / "line_history"
    sd_nba = base / "nba"
    _mk_daily(sd_nba, "2026-05-15.jsonl", _sample_rows(3, "a"))
    _mk_daily(sd_nba, "2026-07-04.jsonl", _sample_rows(1, "today"))
    sd_mlb = base / "mlb"
    _mk_daily(sd_mlb, "2026-04-01.jsonl", _sample_rows(2, "old"))

    report = lhc.plan_all(base, stale_days=30, now=NOW)
    sports = {s["sport"]: s["groups"] for s in report["sports"]}
    assert sports["nba"] == [{"year_month": "2026-05", "file_count": 1,
                              "total_bytes": (sd_nba / "2026-05-15.jsonl").stat().st_size}]
    assert len(sports["mlb"]) == 1
    assert sports["mlb"][0]["year_month"] == "2026-04"
    # dry-run: nothing written to an archive dir
    assert not (tmp_path / "line_history_archive").exists()
