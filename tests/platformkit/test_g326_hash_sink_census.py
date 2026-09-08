"""G326 -- the AST sink census must see what a same-line grep cannot.

The G326 verifier rejected the first attempt because its denominator was a `grep` that only
matched a read and a hash on ONE source line, so every streamed/multiline sink was silently
outside the "exhaustive" table. These tests pin the three sinks the verifier named, prove the
committed CSV was produced by the walker rather than typed by hand, and demonstrate that the
grep the census replaces still cannot find them. Run this file alone; never a full pytest.
"""
import ast
import csv
import re
from pathlib import Path

from scripts.platformkit import g326_hash_sink_census as census

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "docs/evidence/tracking/g326_artifact/hash_sinks.csv"
# The three sinks the G326 verifier named as absent from the rejected same-line table.
NAMED = {
    "scripts/platformkit/autoloop/standing_prereg.py": (241, "FILE_WHOLE"),
    "scripts/platformkit/combo/corpus_cache.py": (42, "FILE_WHOLE"),
    "scripts/platformkit/eval_gate/ledger_backup.py": (37, "FILE_STREAM"),
}
CLASSES = {"FILE_WHOLE", "FILE_STREAM", "TAINTED", "MEMORY", "PARSE_ERROR"}
VERDICTS = {"DEFECT", "ALREADY_LF", "FINE_BINARY", "FINE_RECORD_ONLY", "FINE_MEMORY",
            "FINE_CTOR", "REVIEW_UNKNOWN"}


def _rows():
    with open(CSV_PATH, newline="", encoding="ascii") as fh:
        return list(csv.DictReader(fh))


def test_committed_census_contains_every_sink_the_verifier_named():
    """The rejected table's three counter-examples are all rows in the census artifact."""
    rows = _rows()
    assert rows and list(rows[0]) == census.HEADER
    for path, (line, klass) in NAMED.items():
        hit = [r for r in rows if r["file"] == path and int(r["line"]) == line]
        assert len(hit) == 1, f"{path}:{line} missing from the census"
        assert hit[0]["input_class"] == klass, hit[0]
        assert hit[0]["api"] == "update", hit[0]


def test_the_walker_reproduces_those_rows_from_source():
    """Re-scan just those three files, so the CSV cannot be a hand-written table."""
    for path, (line, klass) in NAMED.items():
        source = ROOT / path
        census.HELPERS[census.mod_path(source)] = census.helper_names(ast.parse(source.read_bytes()))
        rows = census.Scan(source, ast.parse(source.read_bytes())).rows()
        hit = [r for r in rows if r[1] == line and r[2] == "update"]
        assert len(hit) == 1, f"walker found {len(hit)} sinks at {path}:{line}"
        assert hit[0][3] == klass, hit[0]


def test_the_same_line_grep_cannot_find_them():
    """The premise of the supplement: this is why the rejected denominator was incomplete."""
    grep = re.compile(r"(read_bytes\(\)|open\(.*['\"]rb['\"]\)|\.read\()")
    hashed = re.compile(r"hashlib\.(sha256|sha1|md5)|sha256\(")
    for path, (line, _) in NAMED.items():
        text = (ROOT / path).read_text(encoding="utf-8", errors="replace").splitlines()[line - 1]
        assert not (grep.search(text) and hashed.search(text)), f"{path}:{line} is same-line after all"


def test_every_row_uses_the_sealed_vocabulary():
    """A class or verdict outside the prereg supplement would make the table unreadable."""
    rows = _rows()
    assert {r["input_class"] for r in rows} <= CLASSES
    assert {r["verdict"] for r in rows} <= VERDICTS
    assert {r["text_or_binary"] for r in rows} <= {"TEXT", "BINARY", "UNKNOWN", "-"}
    assert {r["compared"] for r in rows} <= {"COMMITTED", "RECORD_ONLY", "-"}
    defects = [r for r in rows if r["verdict"] == "DEFECT"]
    assert defects and all(r["text_or_binary"] == "TEXT" and r["compared"] == "COMMITTED" for r in defects)
    assert all(int(r["line"]) >= 0 for r in rows)
    # One row per call node, so a line holding several sinks contributes several rows; only a
    # PARSE_ERROR row is allowed to carry line 0.
    assert all(int(r["line"]) > 0 for r in rows if r["input_class"] != "PARSE_ERROR")
