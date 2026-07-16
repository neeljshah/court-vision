"""Per-file test for scripts.platformkit.analytics_verify.sentinel.

Synthetic served-JSON + ledger fixtures under tmp_path prove the VERIFIED,
DISCREPANT and UNCHECKABLE paths and tolerance behaviour. Real-data assertions
are skipped when the frontend files are absent.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/analytics_verify/test_sentinel.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.platformkit.analytics_verify import sentinel as S


def _write_ledger(path: Path, rows):
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _mk_rows():
    # 10 settled rows: 6 win, 4 loss; 9 carry a true close (clv_pct), 1 proxy.
    rows = []
    for i in range(9):
        rows.append({
            "sport": "mlb", "status": "settled",
            "outcome": "win" if i < 6 else "loss",
            "clv_pct": 5.0 if i % 2 == 0 else -1.0,
            "clv_is_proxy": False,
            "taken_decimal": 2.0,
        })
    rows.append({
        "sport": "mlb", "status": "settled", "outcome": "loss",
        "clv_pct": 3.0, "clv_is_proxy": True, "taken_decimal": 1.9,
    })
    return rows


def test_grade_summary_verified(tmp_path):
    clv_path = tmp_path / "clv_ledger.jsonl"
    rows = _mk_rows()
    _write_ledger(clv_path, rows)

    recomputed = S._recompute_grade_summary(clv_path)
    assert recomputed["n_settled"] == 10
    assert recomputed["n_clv"] == 9  # true-close only, proxy excluded

    served_path = tmp_path / "grade_summary.json"
    served = dict(recomputed)
    served["as_of"] = datetime.now(timezone.utc).isoformat()
    served_path.write_text(json.dumps(served))

    checks = S.grade_summary_checks(clv_path, served_path)
    verdicts = {c["check"]: c["verdict"] for c in checks}
    assert all(v == "VERIFIED" for v in verdicts.values()), verdicts


def test_grade_summary_discrepant(tmp_path):
    clv_path = tmp_path / "clv_ledger.jsonl"
    _write_ledger(clv_path, _mk_rows())
    recomputed = S._recompute_grade_summary(clv_path)

    served = dict(recomputed)
    served["n_settled"] = recomputed["n_settled"] + 5  # inject a real discrepancy
    served["as_of"] = datetime.now(timezone.utc).isoformat()
    served_path = tmp_path / "grade_summary.json"
    served_path.write_text(json.dumps(served))

    checks = S.grade_summary_checks(clv_path, served_path)
    by_name = {c["check"]: c for c in checks}
    assert by_name["grade_summary.n_settled"]["verdict"] == "DISCREPANT"
    assert by_name["grade_summary.n_settled"]["delta"] == 5


def test_grade_summary_uncheckable_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    checks = S.grade_summary_checks(tmp_path / "clv_ledger.jsonl", missing)
    assert all(c["verdict"] == "UNCHECKABLE" for c in checks)


def test_grade_summary_stale(tmp_path):
    clv_path = tmp_path / "clv_ledger.jsonl"
    _write_ledger(clv_path, _mk_rows())
    recomputed = S._recompute_grade_summary(clv_path)
    served = dict(recomputed)
    served["as_of"] = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    served_path = tmp_path / "grade_summary.json"
    served_path.write_text(json.dumps(served))

    checks = S.grade_summary_checks(clv_path, served_path)
    assert any(c["verdict"] == "STALE" for c in checks)


def test_tolerance_boundary():
    row = S._check("x", Path("f.json"), "x", 10.0, 10.005, tolerance=0.01)
    assert row["verdict"] == "VERIFIED"
    row2 = S._check("x", Path("f.json"), "x", 10.0, 10.02, tolerance=0.01)
    assert row2["verdict"] == "DISCREPANT"


def test_pnl_series_missing_summary(tmp_path):
    served_path = tmp_path / "paper_pnl_series.json"
    served_path.write_text(json.dumps({"no_summary_here": True}))
    checks = S.pnl_series_checks(tmp_path / "clv.jsonl", tmp_path / "bankroll.json",
                                  served_path)
    assert all(c["verdict"] == "UNCHECKABLE" for c in checks)


def test_build_report_counts(tmp_path):
    clv_path = tmp_path / "clv_ledger.jsonl"
    _write_ledger(clv_path, _mk_rows())
    grade_recomputed = S._recompute_grade_summary(clv_path)
    grade_served = dict(grade_recomputed)
    grade_served["as_of"] = datetime.now(timezone.utc).isoformat()
    grade_path = tmp_path / "grade_summary.json"
    grade_path.write_text(json.dumps(grade_served))

    pnl_path = tmp_path / "paper_pnl_series.json"
    pnl_path.write_text(json.dumps({"no_summary_here": True}))  # forces UNCHECKABLE

    report = S.build_report(
        clv_path=clv_path, bankroll_path=tmp_path / "bankroll.json",
        grade_summary_path=grade_path, pnl_series_path=pnl_path,
    )
    assert report["edge_claimed"] is False
    assert report["n_verified"] == 6  # the 6 grade_summary fields
    assert report["n_uncheckable"] == 5  # the 5 pnl_series.summary fields
    assert report["overall"] == "VERIFIED"


def test_real_data_grade_summary():
    if not S.GRADE_SUMMARY_PATH.exists() or not S._clv.DEFAULT_LEDGER.exists():
        pytest.skip("real frontend data not present in this environment")
    checks = S.grade_summary_checks()
    assert len(checks) == 6
