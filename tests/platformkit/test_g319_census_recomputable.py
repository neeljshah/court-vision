"""G319 -- the census-recomputability check, pinned on a hand-built construct."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.platformkit.tracking.census_recomputable import (  # noqa: E402
    ABSENT,
    NOT_RECOMPUTABLE,
    RECOMPUTABLE,
    UNPARSED,
    scan_memo,
    write_csv,
)

MEMO = "\n".join([
    "# Construct memo",
    "The second read saw 8/9 ledger rows and is backed by the committed table.",
    "The first read saw 7/9 ledger rows and has no snapshot behind it.",
    "The agreement ratio 3/4 held throughout, with no noun the parser accepts.",
    "The snapshot list carries n = 12 ledger rows for the archived source.",
    "Two reads at 23:34 / 23:37 over data/2026/09/absent.jsonl rows.",
    "Artifacts: `census.csv` and `snapshots.json`.",
    "",
])


def _build(root: Path) -> str:
    (root / "census.csv").write_text(
        "game_id,rows\n" + "".join(f"g{i},1\n" for i in range(8)), encoding="ascii"
    )
    (root / "snapshots.json").write_text(
        json.dumps({"snapshots": [{"sha256": "0" * 64, "rows_total": 12, "at": "t"}]}),
        encoding="ascii",
    )
    (root / "memo.md").write_text(MEMO, encoding="ascii")
    return "memo.md"


def _by_line(report: dict) -> dict[int, dict]:
    return {row["line"]: row for row in report["rows"]}


def test_the_check_pins_all_four_verdicts_on_a_construct(tmp_path):
    memo = _build(tmp_path)
    report = scan_memo(memo, tmp_path)

    assert report["exists"] is True
    assert set(report["artifacts"]) == {"census.csv", "snapshots.json"}
    rows = _by_line(report)

    backed = rows[2]
    assert backed["verdict"] == RECOMPUTABLE
    assert backed["components"] == [8, 9]
    assert backed["artifacts"] == ["census.csv"]

    unbacked = rows[3]
    assert unbacked["verdict"] == NOT_RECOMPUTABLE
    assert unbacked["components"] == [7, 9]
    assert unbacked["missing"] == [7]

    no_noun = rows[4]
    assert no_noun["verdict"] == UNPARSED
    assert no_noun["reason"] == "line names no source noun"

    from_snapshot_list = rows[5]
    assert from_snapshot_list["verdict"] == RECOMPUTABLE
    assert from_snapshot_list["kind"] == "n_equals"
    assert from_snapshot_list["components"] == [12]
    assert from_snapshot_list["artifacts"] == ["snapshots.json"]

    assert report["totals"] == {RECOMPUTABLE: 2, NOT_RECOMPUTABLE: 1, UNPARSED: 1}
    assert report["n"] == 4


def test_a_clock_time_and_a_path_are_not_parsed_as_counts(tmp_path):
    memo = _build(tmp_path)
    report = scan_memo(memo, tmp_path)
    assert 6 not in _by_line(report), "line 6 holds only a clock time and a path"


def test_an_uncommitted_memo_is_absent_not_skipped(tmp_path):
    report = scan_memo("never_written.md", tmp_path)
    assert report["exists"] is False
    assert report["totals"] == {ABSENT: 1}
    assert report["n"] == 0
    assert report["rows"] == []


def test_csv_zero_pads_every_integer_cell(tmp_path):
    memo = _build(tmp_path)
    reports = [scan_memo(memo, tmp_path), scan_memo("never_written.md", tmp_path)]
    out = tmp_path / "sweep.csv"
    write_csv(reports, out, {memo: "CONSTRUCT"})
    lines = out.read_text(encoding="ascii").splitlines()

    assert lines[0] == "row,memo,line,kind,components,verdict,missing,artifacts"
    assert "CONSTRUCT,memo.md,000002,fraction,000008|000009,RECOMPUTABLE,,census.csv" in lines
    assert ("CONSTRUCT,memo.md,000003,fraction,000007|000009,"
            "NOT RECOMPUTABLE,000007,census.csv") in lines
    assert lines[-1].endswith(f",000000,none,,{ABSENT},,")
    for line in lines[1:]:
        for cell in line.split(",")[2:3]:
            assert len(cell) == 6 and cell.isdigit()
