"""capture_pytest_baseline.py — Overnight-baseline parsing/comparison machinery.

Parses pytest junit-xml reports and --durations=0 output, supports ID-aware G1
comparison, and persists/restores frozen baselines as JSON.

Does NOT invoke pytest. Feed it junit files you already have.

CLI usage:
  python capture_pytest_baseline.py --from-junit results.xml --freeze baseline.json
  python capture_pytest_baseline.py --from-junit results.xml --check  baseline.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_junit_xml(xml_text_or_path: str | Path) -> dict:
    """Parse a pytest junit-xml report into a summary dict.

    Accepts either raw XML text (str) or a path (str/Path) to an xml file.

    Returns::

        {
            "passed":       int,
            "failed_ids":   set[str],   # nodeid of FAILED tests
            "error_ids":    set[str],   # nodeid of ERROR tests
            "skipped":      int,
            "total_collected": int,     # all testcase elements found
        }
    """
    if isinstance(xml_text_or_path, Path) or (
        isinstance(xml_text_or_path, str) and not xml_text_or_path.lstrip().startswith("<")
    ):
        text = Path(xml_text_or_path).read_text(encoding="utf-8")
    else:
        text = xml_text_or_path

    root = ET.fromstring(text)

    # junit-xml may have a single <testsuite> or a <testsuites> wrapper
    if root.tag == "testsuites":
        suites = list(root.iter("testsuite"))
    elif root.tag == "testsuite":
        suites = [root]
    else:
        suites = list(root.iter("testsuite"))

    failed_ids: set[str] = set()
    error_ids: set[str] = set()
    passed = 0
    skipped = 0
    total_collected = 0

    for suite in suites:
        for tc in suite.iter("testcase"):
            total_collected += 1
            classname = tc.get("classname", "")
            name = tc.get("name", "")
            nodeid = f"{classname}::{name}" if classname else name

            if tc.find("failure") is not None:
                failed_ids.add(nodeid)
            elif tc.find("error") is not None:
                error_ids.add(nodeid)
            elif tc.find("skipped") is not None:
                skipped += 1
            else:
                passed += 1

    return {
        "passed": passed,
        "failed_ids": failed_ids,
        "error_ids": error_ids,
        "skipped": skipped,
        "total_collected": total_collected,
    }


def parse_durations(text: str) -> List[Tuple[str, float]]:
    """Parse pytest ``--durations=0`` output into a sorted slow-list.

    Expects lines like::

        0.42s call     tests/foo/test_bar.py::test_baz

    Returns a list of ``(nodeid, seconds)`` tuples sorted descending by
    duration (slowest first).
    """
    pattern = re.compile(
        r"^\s*(\d+\.\d+)s\s+(?:call|setup|teardown)\s+(.+)$",
        re.MULTILINE,
    )
    results: dict[str, float] = {}
    for m in pattern.finditer(text):
        secs = float(m.group(1))
        nodeid = m.group(2).strip()
        # accumulate across setup/call/teardown for the same nodeid
        results[nodeid] = results.get(nodeid, 0.0) + secs

    return sorted(results.items(), key=lambda x: x[1], reverse=True)


# ---------------------------------------------------------------------------
# G1 comparison (ID-aware)
# ---------------------------------------------------------------------------

def g1_compare(
    baseline: dict,
    current: dict,
    max_collection_drop: int = 5,
) -> Tuple[bool, List[str]]:
    """ID-aware G1 gate.

    PASS iff:
    * No NEW failing or error nodeids appear vs the baseline frozen set.
    * The collected test count does not drop by more than *max_collection_drop*
      (default 5) unexplained items.

    Pre-existing (frozen) failing/error ids are *allowed* — they do not
    trigger a failure.

    Parameters
    ----------
    baseline:
        Dict from ``load_baseline`` or a previous ``parse_junit_xml`` call.
    current:
        Dict from ``parse_junit_xml`` on the new run.
    max_collection_drop:
        How many fewer collected tests are tolerated before flagging a drop.

    Returns
    -------
    (passed: bool, reasons: list[str])
        *reasons* is empty on PASS and non-empty on FAIL.
    """
    baseline_bad: set[str] = (
        set(baseline.get("failed_ids", set()))
        | set(baseline.get("error_ids", set()))
    )
    current_bad: set[str] = (
        set(current.get("failed_ids", set()))
        | set(current.get("error_ids", set()))
    )

    new_failures = current_bad - baseline_bad
    reasons: List[str] = []

    if new_failures:
        sorted_new = sorted(new_failures)
        reasons.append(
            f"NEW failing/error ids ({len(sorted_new)}): "
            + ", ".join(sorted_new[:10])
            + (" …" if len(sorted_new) > 10 else "")
        )

    baseline_total = baseline.get("total_collected", 0)
    current_total = current.get("total_collected", 0)
    drop = baseline_total - current_total
    if drop > max_collection_drop:
        reasons.append(
            f"Collection count dropped {drop} (baseline={baseline_total}, "
            f"current={current_total}, tolerance={max_collection_drop})"
        )

    return (len(reasons) == 0, reasons)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def write_baseline(parsed: dict, out_path: str | Path) -> None:
    """Persist a parsed result as a JSON baseline file.

    Sets in *parsed* (failed_ids, error_ids) are serialised to sorted lists
    so the file is deterministic and human-readable.
    """
    serialisable = {
        "passed": parsed.get("passed", 0),
        "failed_ids": sorted(parsed.get("failed_ids", set())),
        "error_ids": sorted(parsed.get("error_ids", set())),
        "skipped": parsed.get("skipped", 0),
        "total_collected": parsed.get("total_collected", 0),
    }
    Path(out_path).write_text(
        json.dumps(serialisable, indent=2), encoding="utf-8"
    )


def load_baseline(path: str | Path) -> dict:
    """Load a frozen baseline from JSON.

    Converts failed_ids / error_ids back to ``set[str]``.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    raw["failed_ids"] = set(raw.get("failed_ids", []))
    raw["error_ids"] = set(raw.get("error_ids", []))
    return raw


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Parse a pytest junit-xml file and either freeze a baseline "
            "or compare against one."
        )
    )
    p.add_argument(
        "--from-junit",
        metavar="PATH",
        required=True,
        help="Path to an existing pytest junit-xml report.",
    )
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--freeze",
        metavar="OUT_JSON",
        help="Write the parsed result as the frozen baseline JSON.",
    )
    group.add_argument(
        "--check",
        metavar="BASELINE_JSON",
        help="Compare the junit report against a frozen baseline; exit 1 on G1 FAIL.",
    )
    p.add_argument(
        "--collection-drop-tolerance",
        type=int,
        default=5,
        metavar="N",
        help="Max tolerated collection-count drop (default: 5).",
    )
    return p


def main(argv: List[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    parsed = parse_junit_xml(args.from_junit)
    print(
        f"Parsed: {parsed['total_collected']} collected, "
        f"{parsed['passed']} passed, "
        f"{len(parsed['failed_ids'])} failed, "
        f"{len(parsed['error_ids'])} error, "
        f"{parsed['skipped']} skipped."
    )

    if args.freeze:
        write_baseline(parsed, args.freeze)
        print(f"Baseline frozen → {args.freeze}")
        return 0

    # --check
    baseline = load_baseline(args.check)
    ok, reasons = g1_compare(
        baseline, parsed, max_collection_drop=args.collection_drop_tolerance
    )
    if ok:
        print("G1 PASS — no new failures, collection count stable.")
        return 0
    else:
        print("G1 FAIL:")
        for r in reasons:
            print(f"  • {r}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
