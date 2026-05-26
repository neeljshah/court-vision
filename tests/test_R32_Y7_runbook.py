"""test_R32_Y7_runbook.py — verifies docs/operator_runbook.md is complete.

Five gates:
    1. docs/operator_runbook.md exists.
    2. All 7 expected sections present in the doc.
    3. All referenced scripts cited in the doc actually exist on disk.
    4. The cron snippet is syntactically sane (matches m h dom mon dow cmd).
    5. The doc is dense enough to be useful (>= 200 non-blank lines).

LOCAL ONLY. No network. No real-money side effect.
"""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent

DOC_PATH = _ROOT / "docs" / "operator_runbook.md"

# 7 mandatory sections (matches H2 headers in the runbook).
REQUIRED_SECTIONS = (
    "TL;DR",
    "Architecture",
    "Daily timeline",
    "Files to open",
    "Cron setup",
    "Common operations",
    "Incident response",
)

# Scripts the runbook must reference (full path under repo root).
REQUIRED_SCRIPTS = (
    "scripts/daily_workflow.py",
    "scripts/operator_dashboard.py",
    "scripts/mobile_html_server.py",
    "scripts/live_recommendation_engine.py",
    "scripts/ledger_insurance.py",
    "scripts/nightly_cleanup.py",
    "scripts/daemon_registry.json",
    "scripts/daemon_watchdog.py",
    "scripts/reconcile_settlements.py",
    "scripts/live_rec_tracker.py",
    "scripts/feature_drift_detector.py",
    "scripts/nba_injury_report_scraper.py",
    "scripts/recover_line_killed.py",
    "scripts/place_bet.py",
)


class TestRunbookExists(unittest.TestCase):
    def test_doc_file_exists(self):
        self.assertTrue(DOC_PATH.exists(), f"missing: {DOC_PATH}")
        size = DOC_PATH.stat().st_size
        self.assertGreater(size, 4_000, f"doc suspiciously small: {size} bytes")


class TestRunbookSections(unittest.TestCase):
    def setUp(self):
        self.text = DOC_PATH.read_text(encoding="utf-8")

    def test_all_seven_sections_present(self):
        missing = [s for s in REQUIRED_SECTIONS if s not in self.text]
        self.assertEqual(
            missing, [],
            f"missing sections: {missing}; "
            f"have {len(REQUIRED_SECTIONS) - len(missing)}/7",
        )

    def test_tldr_is_at_top(self):
        # TL;DR must appear in the first 1500 chars (above the fold).
        self.assertIn("TL;DR", self.text[:1500])

    def test_doc_density(self):
        lines = [ln for ln in self.text.splitlines() if ln.strip()]
        self.assertGreaterEqual(
            len(lines), 200,
            f"runbook only has {len(lines)} non-blank lines; target >= 200",
        )


class TestRunbookScriptsExist(unittest.TestCase):
    def setUp(self):
        self.text = DOC_PATH.read_text(encoding="utf-8")

    def test_all_referenced_scripts_cited(self):
        missing = [s for s in REQUIRED_SCRIPTS if s not in self.text]
        self.assertEqual(missing, [], f"runbook fails to reference: {missing}")

    def test_all_referenced_scripts_exist_on_disk(self):
        broken = []
        for rel in REQUIRED_SCRIPTS:
            full = _ROOT / rel
            if not full.exists():
                broken.append(rel)
        self.assertEqual(
            broken, [],
            f"runbook references nonexistent scripts: {broken}",
        )


class TestRunbookCron(unittest.TestCase):
    def setUp(self):
        self.text = DOC_PATH.read_text(encoding="utf-8")

    def test_crontab_snippet_has_valid_lines(self):
        # Match: 5 schedule fields then a command. Very loose.
        cron_line_re = re.compile(
            r"^\s*(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+\S+"
        )
        # Limit to the "crontab" code-block portion.
        cron_section = self.text.split("Linux crontab", 1)[-1].split("###", 1)[0]
        cron_lines = [
            ln for ln in cron_section.splitlines()
            if ln and not ln.startswith("#") and not ln.startswith("```")
            and cron_line_re.match(ln)
        ]
        self.assertGreaterEqual(
            len(cron_lines), 3,
            f"expected >=3 crontab lines, got {len(cron_lines)}",
        )

    def test_windows_task_xml_present(self):
        # Coarse: the XML stub must mention the canonical tags.
        self.assertIn("<Task ", self.text)
        self.assertIn("<CalendarTrigger>", self.text)
        self.assertIn("daily_workflow.py", self.text)


if __name__ == "__main__":
    unittest.main()
