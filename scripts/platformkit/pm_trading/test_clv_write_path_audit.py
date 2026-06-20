"""tests for clv_write_path_audit.py -- per-file test (BE-R3-4).

Acceptance criteria (from workstream spec):
  1. A synthetic "raw-append writer" (calls append_settlement without routing
     through the guard) IS detected and flagged as a violation.
  2. A writer that routes through record_bet / append_if_new_status_aware
     passes CLEAN (zero violations for that file).
  3. The report carries no $ / dollar / pnl / roi / profit field.
  4. The module is read-only: it never mutates any source file.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/pm_trading/test_clv_write_path_audit.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.platformkit.pm_trading.clv_write_path_audit import scan_clv_write_paths

# ---------------------------------------------------------------------------
# Fixtures: synthetic source files written to tmp_path
# ---------------------------------------------------------------------------

_OFFENDING_WRITER = """\
# synthetic_bad_writer.py -- intentionally bypasses the guard (test fixture)
import json
from scripts.platformkit import clv_ledger as _clv

def write_raw_settlement(bet, path=None):
    # BAD: calls append_settlement without routing through
    # append_if_new_status_aware / record_settlement_guarded.
    # This bypasses the bet_id stamp and the dup guard.
    settled = dict(bet)
    settled["status"] = "settled"
    _clv.append_settlement(settled, path=path)
"""

_SAFE_WRITER = """\
# synthetic_safe_writer.py -- routes through the guarded path (test fixture)
from scripts.platformkit.clv_settle_write import write_settlement
from scripts.platformkit.clv_status_aware_append import settle_append

def record_via_guard(bet, path=None):
    # SAFE: funnels through write_settlement (which calls
    # append_if_new_status_aware) -- dedup + bet_id guaranteed.
    return write_settlement(bet, path=path)

def record_via_settle_append(bet, path=None):
    # SAFE: settle_append is the canonical status-aware wrapper.
    return settle_append(bet, path=path)
"""

_MIXED_WRITER = """\
# synthetic_mixed_writer.py -- both patterns in one file (test fixture)
import json
from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit.clv_ledger_guarded_append import append_if_new_status_aware

def the_bad_path(bet, path=None):
    # BAD: direct raw call
    settled = dict(bet)
    _clv.append_settlement(settled, path=path)

def the_safe_path(row, path=None):
    # SAFE: guarded
    return append_if_new_status_aware(row, path=path)
"""

_RAW_JSON_LEDGER_WRITER = """\
# synthetic_raw_json_writer.py -- raw json.dumps to clv_ledger (test fixture)
import json
from pathlib import Path
from scripts.platformkit.clv_ledger import DEFAULT_LEDGER

def bad_raw_write(record, path=None):
    # BAD: raw json.dumps + open("a") targeting the clv_ledger path.
    # No bet_id stamp, no dup guard.
    target = path or DEFAULT_LEDGER
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\\n")
"""


@pytest.fixture()
def synthetic_root(tmp_path: Path) -> Path:
    """Create a synthetic scan root with the four fixture files."""
    scan_dir = tmp_path / "fake_pm_trading"
    scan_dir.mkdir()

    (scan_dir / "synthetic_bad_writer.py").write_text(
        _OFFENDING_WRITER, encoding="utf-8")
    (scan_dir / "synthetic_safe_writer.py").write_text(
        _SAFE_WRITER, encoding="utf-8")
    (scan_dir / "synthetic_mixed_writer.py").write_text(
        _MIXED_WRITER, encoding="utf-8")
    (scan_dir / "synthetic_raw_json_writer.py").write_text(
        _RAW_JSON_LEDGER_WRITER, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Test 1: raw append_settlement call is flagged as a violation
# ---------------------------------------------------------------------------

def test_raw_append_settlement_is_detected(synthetic_root: Path) -> None:
    """The offending writer (bare append_settlement call) must appear in violations."""
    report = scan_clv_write_paths(
        roots=["fake_pm_trading"],
        repo_root=synthetic_root,
    )

    assert report["status"] == "ok"
    violations = report["violations"]
    flagged_files = {v["file"] for v in violations}
    # At least one violation from the bad writer.
    assert any("synthetic_bad_writer" in f for f in flagged_files), (
        "Expected synthetic_bad_writer.py to be flagged; violations=%r" % violations
    )
    # The violation reason mentions the guard to use.
    bad_v = [v for v in violations if "synthetic_bad_writer" in v["file"]]
    assert bad_v, "No violation rows from synthetic_bad_writer.py"
    assert "append_settlement" in bad_v[0]["reason"].lower() or \
           "bet_id" in bad_v[0]["reason"].lower() or \
           "guard" in bad_v[0]["reason"].lower(), (
        "Violation reason should mention the missing guard, got: %r" % bad_v[0]["reason"]
    )


# ---------------------------------------------------------------------------
# Test 2: guarded writer passes clean
# ---------------------------------------------------------------------------

def test_safe_writer_passes_clean(tmp_path: Path) -> None:
    """A writer that only calls write_settlement / settle_append must NOT be flagged."""
    scan_dir = tmp_path / "safe_only"
    scan_dir.mkdir()
    (scan_dir / "synthetic_safe_writer.py").write_text(
        _SAFE_WRITER, encoding="utf-8")

    report = scan_clv_write_paths(
        roots=["safe_only"],
        repo_root=tmp_path,
    )

    assert report["status"] == "ok"
    violations = report["violations"]
    safe_flagged = [v for v in violations if "synthetic_safe_writer" in v["file"]]
    assert not safe_flagged, (
        "Safe writer should have no violations, got: %r" % safe_flagged
    )
    # The safe call-sites should be found.
    safe_sites = report["safe_call_sites"]
    safe_guards_found = {s["guard"] for s in safe_sites
                         if "synthetic_safe_writer" in s["file"]}
    assert safe_guards_found, (
        "Expected safe call-sites from synthetic_safe_writer.py; sites=%r" % safe_sites
    )


# ---------------------------------------------------------------------------
# Test 3: mixed file -- only the bad path is flagged
# ---------------------------------------------------------------------------

def test_mixed_file_flags_only_bad_path(tmp_path: Path) -> None:
    """In a file with both patterns only the raw call should be in violations."""
    scan_dir = tmp_path / "mixed_only"
    scan_dir.mkdir()
    (scan_dir / "synthetic_mixed_writer.py").write_text(
        _MIXED_WRITER, encoding="utf-8")

    report = scan_clv_write_paths(
        roots=["mixed_only"],
        repo_root=tmp_path,
    )

    violations = report["violations"]
    safe_sites = report["safe_call_sites"]

    # At least one violation for the mixed file.
    mixed_v = [v for v in violations if "synthetic_mixed_writer" in v["file"]]
    assert mixed_v, "Expected violation in mixed writer, got none; violations=%r" % violations

    # And at least one safe site.
    mixed_s = [s for s in safe_sites if "synthetic_mixed_writer" in s["file"]]
    assert mixed_s, "Expected safe call-site in mixed writer, got none; safe=%r" % safe_sites


# ---------------------------------------------------------------------------
# Test 4: raw json.dumps targeting clv_ledger is flagged
# ---------------------------------------------------------------------------

def test_raw_json_dump_to_ledger_is_flagged(tmp_path: Path) -> None:
    """A file that writes raw json.dumps to clv_ledger path must be flagged."""
    scan_dir = tmp_path / "rawjson_only"
    scan_dir.mkdir()
    (scan_dir / "synthetic_raw_json_writer.py").write_text(
        _RAW_JSON_LEDGER_WRITER, encoding="utf-8")

    report = scan_clv_write_paths(
        roots=["rawjson_only"],
        repo_root=tmp_path,
    )

    violations = report["violations"]
    rjw_v = [v for v in violations if "synthetic_raw_json_writer" in v["file"]]
    assert rjw_v, (
        "Expected violation in raw json writer, got none; violations=%r" % violations
    )


# ---------------------------------------------------------------------------
# Test 5: report carries no dollar / $ / profit / pnl / roi field
# ---------------------------------------------------------------------------

def test_report_has_no_dollar_field(synthetic_root: Path) -> None:
    """The audit report must not introduce any $ / pnl / roi / profit key."""
    report = scan_clv_write_paths(
        roots=["fake_pm_trading"],
        repo_root=synthetic_root,
    )
    report_json = json.dumps(report)
    banned_terms = ('"pnl"', '"roi"', '"profit"', '"bankroll"', '"dollar"')
    for term in banned_terms:
        assert term not in report_json.lower(), (
            "Report contains banned key %r -- units-only contract violated" % term
        )
    # The $ sign must not appear as a key in the report.
    assert '"$"' not in report_json, "Report must not carry a '$' field"


# ---------------------------------------------------------------------------
# Test 6: report is read-only (source files not modified)
# ---------------------------------------------------------------------------

def test_report_is_read_only(tmp_path: Path) -> None:
    """scan_clv_write_paths must not modify any source file."""
    scan_dir = tmp_path / "readonly_check"
    scan_dir.mkdir()
    bad_file = scan_dir / "synthetic_bad_writer.py"
    bad_file.write_text(_OFFENDING_WRITER, encoding="utf-8")

    original_content = bad_file.read_text(encoding="utf-8")
    original_mtime = bad_file.stat().st_mtime

    scan_clv_write_paths(roots=["readonly_check"], repo_root=tmp_path)

    assert bad_file.read_text(encoding="utf-8") == original_content, (
        "Audit must not modify the scanned source file"
    )
    assert bad_file.stat().st_mtime == original_mtime, (
        "Audit must not change the source file's modification time"
    )


# ---------------------------------------------------------------------------
# Test 7: summary string reflects violation count
# ---------------------------------------------------------------------------

def test_summary_string_reflects_violations(synthetic_root: Path) -> None:
    """The summary field must mention VIOLATION when there are violations."""
    report = scan_clv_write_paths(
        roots=["fake_pm_trading"],
        repo_root=synthetic_root,
    )
    if report["violations"]:
        assert "VIOLATION" in report["summary"].upper(), (
            "Expected VIOLATION in summary when violations detected; got: %r"
            % report["summary"]
        )
    else:
        assert "CLEAN" in report["summary"].upper(), (
            "Expected CLEAN in summary when no violations; got: %r"
            % report["summary"]
        )


# ---------------------------------------------------------------------------
# Test 8: real codebase scan surfaces the known offenders
# ---------------------------------------------------------------------------

def test_real_codebase_flags_known_offenders() -> None:
    """Scanning the live platformkit/pm_trading and ingame dirs must surface
    the KNOWN raw append_settlement call-sites in paper_autobet.py and
    paper_ingame.py as violations.

    This is the key regression guard: if those writers are ever fixed to route
    through write_settlement / settle_append, the test will pass with 0
    violations. If they are added back unguarded, this test fails and alerts.
    """
    report = scan_clv_write_paths()  # uses default roots
    violations = report["violations"]
    flagged_files = {v["file"] for v in violations}

    # Both known offenders must appear (this pinpoints the upstream cause of BE-R3-3).
    expected_offenders = {
        "paper_autobet.py",
        "paper_ingame.py",
    }
    detected_names = {Path(f).name for f in flagged_files}
    missing = expected_offenders - detected_names
    assert not missing, (
        "Expected these files to be flagged as violations: %r; "
        "actually detected: %r; full violations: %r"
        % (missing, detected_names, violations)
    )
