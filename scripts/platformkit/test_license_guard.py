"""Focused tests for the read-only copyleft import guard.

Run: python -m pytest scripts/platformkit/test_license_guard.py -q
"""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.license_guard import main, scan, tree_sha256


def test_fixture_ultralytics_import_is_flagged_with_location(tmp_path: Path) -> None:
    target = tmp_path / "domains" / "example" / "adapter.py"
    target.parent.mkdir(parents=True)
    target.write_text("from ultralytics import YOLO\n", encoding="utf-8")

    findings = scan(tmp_path)

    assert len(findings) == 1
    assert findings[0].file == "domains/example/adapter.py"
    assert findings[0].line == 1
    assert findings[0].module == "ultralytics"
    assert findings[0].license == "AGPL-3.0"


def test_real_tree_reports_all_five_call_sites_and_never_writes(capsys) -> None:
    root = Path(__file__).resolve().parents[2]
    before = tree_sha256(root)

    findings = scan(root)
    exit_code = main([str(root)])

    assert tree_sha256(root) == before
    assert exit_code == 1
    assert len(findings) >= 5
    files = {finding.file for finding in findings if finding.module == "ultralytics"}
    expected = {
        "domains/baseball/tracking/adapter.py", "domains/football/tracking/adapter.py",
        "domains/soccer/tracking/adapter.py", "domains/tennis/tracking/adapter.py",
        "scripts/platformkit/detection/shim.py",
    }
    assert expected.issubset(files)
    assert '"verdict": "DENY"' in capsys.readouterr().out
