"""tests/platform/test_capture_pytest_baseline.py

Hermetic offline tests for capture_pytest_baseline.py.
Never invokes pytest itself; all fixtures are synthetic strings.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from scripts.platformkit.capture_pytest_baseline import (
    g1_compare,
    load_baseline,
    parse_durations,
    parse_junit_xml,
    write_baseline,
)

# ---------------------------------------------------------------------------
# Synthetic junit-xml fixtures
# ---------------------------------------------------------------------------

# 4 tests: 2 pass, 2 fail, 1 error, 1 skip  (total_collected = 6)
JUNIT_BASE = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="6" errors="1" failures="2" skipped="1">
  <testcase classname="tests.foo.test_alpha" name="test_pass_one" time="0.01"/>
  <testcase classname="tests.foo.test_alpha" name="test_pass_two" time="0.02"/>
  <testcase classname="tests.foo.test_alpha" name="test_fail_one" time="0.03">
    <failure message="AssertionError">assert False</failure>
  </testcase>
  <testcase classname="tests.foo.test_alpha" name="test_fail_two" time="0.04">
    <failure message="AssertionError">assert 1 == 2</failure>
  </testcase>
  <testcase classname="tests.foo.test_alpha" name="test_error_one" time="0.05">
    <error message="RuntimeError">boom</error>
  </testcase>
  <testcase classname="tests.foo.test_alpha" name="test_skip_one" time="0.00">
    <skipped message="skip reason"/>
  </testcase>
</testsuite>
"""

# Same as BASE but adds one NEW failure: test_fail_new
JUNIT_NEW_FAILURE = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="7" errors="1" failures="3" skipped="1">
  <testcase classname="tests.foo.test_alpha" name="test_pass_one" time="0.01"/>
  <testcase classname="tests.foo.test_alpha" name="test_pass_two" time="0.02"/>
  <testcase classname="tests.foo.test_alpha" name="test_fail_one" time="0.03">
    <failure message="AssertionError">assert False</failure>
  </testcase>
  <testcase classname="tests.foo.test_alpha" name="test_fail_two" time="0.04">
    <failure message="AssertionError">assert 1 == 2</failure>
  </testcase>
  <testcase classname="tests.foo.test_alpha" name="test_error_one" time="0.05">
    <error message="RuntimeError">boom</error>
  </testcase>
  <testcase classname="tests.foo.test_alpha" name="test_skip_one" time="0.00">
    <skipped message="skip reason"/>
  </testcase>
  <testcase classname="tests.foo.test_alpha" name="test_fail_new" time="0.06">
    <failure message="AssertionError">brand new failure</failure>
  </testcase>
</testsuite>
"""

# 6 → 0 tests: massive collection drop
JUNIT_EMPTY = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="0" errors="0" failures="0" skipped="0">
</testsuite>
"""

# Wrapped in <testsuites>
JUNIT_TESTSUITES_WRAPPER = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="suite1" tests="2">
    <testcase classname="tests.bar" name="test_a" time="0.1"/>
    <testcase classname="tests.bar" name="test_b" time="0.2">
      <failure message="oops">oops</failure>
    </testcase>
  </testsuite>
</testsuites>
"""

# ---------------------------------------------------------------------------
# parse_junit_xml tests
# ---------------------------------------------------------------------------

class TestParseJunitXml:
    def test_counts_on_base(self) -> None:
        r = parse_junit_xml(JUNIT_BASE)
        assert r["total_collected"] == 6
        assert r["passed"] == 2
        assert r["skipped"] == 1
        assert len(r["failed_ids"]) == 2
        assert len(r["error_ids"]) == 1

    def test_failed_nodeids(self) -> None:
        r = parse_junit_xml(JUNIT_BASE)
        assert "tests.foo.test_alpha::test_fail_one" in r["failed_ids"]
        assert "tests.foo.test_alpha::test_fail_two" in r["failed_ids"]

    def test_error_nodeid(self) -> None:
        r = parse_junit_xml(JUNIT_BASE)
        assert "tests.foo.test_alpha::test_error_one" in r["error_ids"]

    def test_skipped_not_in_failed(self) -> None:
        r = parse_junit_xml(JUNIT_BASE)
        skip_id = "tests.foo.test_alpha::test_skip_one"
        assert skip_id not in r["failed_ids"]
        assert skip_id not in r["error_ids"]

    def test_testsuites_wrapper(self) -> None:
        r = parse_junit_xml(JUNIT_TESTSUITES_WRAPPER)
        assert r["total_collected"] == 2
        assert r["passed"] == 1
        assert len(r["failed_ids"]) == 1

    def test_reads_from_path(self, tmp_path: Path) -> None:
        p = tmp_path / "results.xml"
        p.write_text(JUNIT_BASE, encoding="utf-8")
        r = parse_junit_xml(p)
        assert r["total_collected"] == 6

    def test_reads_from_path_str(self, tmp_path: Path) -> None:
        p = tmp_path / "results.xml"
        p.write_text(JUNIT_BASE, encoding="utf-8")
        r = parse_junit_xml(str(p))
        assert r["total_collected"] == 6

    def test_empty_suite(self) -> None:
        r = parse_junit_xml(JUNIT_EMPTY)
        assert r["total_collected"] == 0
        assert r["passed"] == 0
        assert len(r["failed_ids"]) == 0


# ---------------------------------------------------------------------------
# g1_compare tests
# ---------------------------------------------------------------------------

class TestG1Compare:
    def setup_method(self) -> None:
        self.baseline = parse_junit_xml(JUNIT_BASE)

    def test_identical_run_passes(self) -> None:
        current = parse_junit_xml(JUNIT_BASE)
        ok, reasons = g1_compare(self.baseline, current)
        assert ok is True
        assert reasons == []

    def test_new_failure_fails(self) -> None:
        current = parse_junit_xml(JUNIT_NEW_FAILURE)
        ok, reasons = g1_compare(self.baseline, current)
        assert ok is False
        assert len(reasons) >= 1
        assert any("test_fail_new" in r for r in reasons)

    def test_collection_drop_fails(self) -> None:
        current = parse_junit_xml(JUNIT_EMPTY)
        ok, reasons = g1_compare(self.baseline, current, max_collection_drop=5)
        assert ok is False
        assert any("Collection count dropped" in r for r in reasons)

    def test_small_collection_drop_allowed(self) -> None:
        # current loses 1 test (baseline=6, current=5) — within tolerance=5
        tiny_drop = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="5">
  <testcase classname="tests.foo.test_alpha" name="test_pass_one"/>
  <testcase classname="tests.foo.test_alpha" name="test_pass_two"/>
  <testcase classname="tests.foo.test_alpha" name="test_fail_one">
    <failure message="x">x</failure>
  </testcase>
  <testcase classname="tests.foo.test_alpha" name="test_fail_two">
    <failure message="x">x</failure>
  </testcase>
  <testcase classname="tests.foo.test_alpha" name="test_error_one">
    <error message="x">x</error>
  </testcase>
</testsuite>
"""
        current = parse_junit_xml(tiny_drop)
        ok, reasons = g1_compare(self.baseline, current, max_collection_drop=5)
        assert ok is True

    def test_preexisting_failures_allowed(self) -> None:
        # A run that has ONLY the same failures as baseline — must PASS
        same_bad = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="3">
  <testcase classname="tests.foo.test_alpha" name="test_fail_one">
    <failure message="x">x</failure>
  </testcase>
  <testcase classname="tests.foo.test_alpha" name="test_fail_two">
    <failure message="x">x</failure>
  </testcase>
  <testcase classname="tests.foo.test_alpha" name="test_error_one">
    <error message="x">x</error>
  </testcase>
</testsuite>
"""
        current = parse_junit_xml(same_bad)
        ok, reasons = g1_compare(self.baseline, current)
        assert ok is True

    def test_reasons_list_populated_on_fail(self) -> None:
        current = parse_junit_xml(JUNIT_NEW_FAILURE)
        ok, reasons = g1_compare(self.baseline, current)
        assert not ok
        assert isinstance(reasons, list)
        assert all(isinstance(r, str) for r in reasons)

    def test_both_failures_and_drop_both_reported(self) -> None:
        # new failure + massive collection drop → 2 reasons
        current = parse_junit_xml(JUNIT_EMPTY)
        # inject a new bad id
        current["failed_ids"].add("tests.foo::test_brand_new")
        ok, reasons = g1_compare(self.baseline, current, max_collection_drop=1)
        assert not ok
        assert len(reasons) == 2


# ---------------------------------------------------------------------------
# parse_durations tests
# ---------------------------------------------------------------------------

DURATIONS_SAMPLE = """\
============================= slowest durations ==============================
3.21s call     tests/slow/test_model.py::test_train
1.05s call     tests/slow/test_model.py::test_predict
0.42s setup    tests/slow/test_model.py::test_predict
0.18s call     tests/fast/test_utils.py::test_quick
0.01s teardown tests/fast/test_utils.py::test_quick
"""


class TestParseDurations:
    def test_returns_list_of_tuples(self) -> None:
        result = parse_durations(DURATIONS_SAMPLE)
        assert isinstance(result, list)
        assert all(isinstance(t, tuple) and len(t) == 2 for t in result)

    def test_sorted_descending(self) -> None:
        result = parse_durations(DURATIONS_SAMPLE)
        secs = [s for _, s in result]
        assert secs == sorted(secs, reverse=True)

    def test_accumulates_phases(self) -> None:
        # test_predict has call(1.05) + setup(0.42) = 1.47 total
        result = parse_durations(DURATIONS_SAMPLE)
        totals = dict(result)
        predict_key = "tests/slow/test_model.py::test_predict"
        assert abs(totals[predict_key] - 1.47) < 1e-6

    def test_slowest_first(self) -> None:
        result = parse_durations(DURATIONS_SAMPLE)
        # test_train (3.21) should be first
        assert result[0][0] == "tests/slow/test_model.py::test_train"
        assert abs(result[0][1] - 3.21) < 1e-6

    def test_empty_input(self) -> None:
        assert parse_durations("") == []

    def test_no_duration_lines(self) -> None:
        assert parse_durations("just some random text\nno timings here") == []


# ---------------------------------------------------------------------------
# write_baseline / load_baseline round-trip tests
# ---------------------------------------------------------------------------

class TestBaselinePersistence:
    def test_roundtrip_preserves_counts(self, tmp_path: Path) -> None:
        parsed = parse_junit_xml(JUNIT_BASE)
        out = tmp_path / "baseline.json"
        write_baseline(parsed, out)
        loaded = load_baseline(out)
        assert loaded["passed"] == parsed["passed"]
        assert loaded["skipped"] == parsed["skipped"]
        assert loaded["total_collected"] == parsed["total_collected"]

    def test_roundtrip_preserves_ids(self, tmp_path: Path) -> None:
        parsed = parse_junit_xml(JUNIT_BASE)
        out = tmp_path / "baseline.json"
        write_baseline(parsed, out)
        loaded = load_baseline(out)
        assert loaded["failed_ids"] == parsed["failed_ids"]
        assert loaded["error_ids"] == parsed["error_ids"]

    def test_ids_are_sets_after_load(self, tmp_path: Path) -> None:
        parsed = parse_junit_xml(JUNIT_BASE)
        out = tmp_path / "baseline.json"
        write_baseline(parsed, out)
        loaded = load_baseline(out)
        assert isinstance(loaded["failed_ids"], set)
        assert isinstance(loaded["error_ids"], set)

    def test_json_file_is_valid(self, tmp_path: Path) -> None:
        parsed = parse_junit_xml(JUNIT_BASE)
        out = tmp_path / "baseline.json"
        write_baseline(parsed, out)
        raw = json.loads(out.read_text(encoding="utf-8"))
        assert "failed_ids" in raw
        assert isinstance(raw["failed_ids"], list)  # serialised as list

    def test_deterministic_output(self, tmp_path: Path) -> None:
        parsed = parse_junit_xml(JUNIT_BASE)
        out1 = tmp_path / "b1.json"
        out2 = tmp_path / "b2.json"
        write_baseline(parsed, out1)
        write_baseline(parsed, out2)
        assert out1.read_text() == out2.read_text()

    def test_g1_compare_works_with_loaded_baseline(self, tmp_path: Path) -> None:
        parsed = parse_junit_xml(JUNIT_BASE)
        out = tmp_path / "baseline.json"
        write_baseline(parsed, out)
        baseline = load_baseline(out)
        current = parse_junit_xml(JUNIT_NEW_FAILURE)
        ok, reasons = g1_compare(baseline, current)
        assert not ok
        assert any("test_fail_new" in r for r in reasons)
