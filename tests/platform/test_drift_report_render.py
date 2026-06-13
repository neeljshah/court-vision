"""test_drift_report_render.py — Direct unit tests for drift_report_render.py.

Imports drift_report_render directly (not via drift_report.py) to provide
first-class coverage of render_vault_note and _render_stat_table.

Six scenarios:
    1. Non-empty per-stat report → stat names in markdown.
    2. Required section headings always present.
    3. Bias flag surfaced when |bias|>0.5 (via all_flags).
    4. PIT non-uniform flag surfaced when present.
    5. Empty report → valid minimal markdown, no crash.
    6. Determinism — same input → same output.

Python 3.9 compatible. No network, no GPU, no parquet files.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import pytest

ROOT = Path(__file__).resolve().parents[2]
_OBS_DIR = ROOT / "scripts" / "platformkit" / "obs"
for _p in (str(_OBS_DIR), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import drift_report_render as drr  # noqa: E402

# ---------------------------------------------------------------------------
# Required headings (must appear in every rendered note)
# ---------------------------------------------------------------------------

_REQUIRED_HEADINGS = [
    "## Point Calibration Metrics",
    "## Interval Coverage",
    "## Feature Drift",
    "## Data Sources",
]

# ---------------------------------------------------------------------------
# Stub builders — pure dicts, no DataFrames, no I/O
# ---------------------------------------------------------------------------


def _pit(flag: str = "ok") -> Dict[str, Any]:
    """Minimal PIT block."""
    base = {"n": 200, "mean": 0.01, "std": 1.0, "skew": 0.0,
            "chi_sq_stat": 7.2, "p_value": 0.51, "flag": flag}
    if flag == "non_uniform":
        base.update({"p_value": 0.007, "chi_sq_stat": 22.8})
    return base


def _make_per_stat(stats=("pts", "reb"), bias: float = 0.1,
                   pit_flag: str = "ok") -> Dict[str, Any]:
    return {
        s: {"n": 80, "rmse": 4.58, "bias": bias, "mse": 20.97,
            "brier_binary": 0.249, "pit": _pit(pit_flag)}
        for s in stats
    }


def _make_report(*, stats=("pts", "reb"), bias: float = 0.1,
                 pit_flag: str = "ok", all_flags=None) -> Dict[str, Any]:
    flags = list(all_flags) if all_flags else []
    return {
        "generated_at": "2026-06-11T12:00:00+00:00",
        "data_sources": {"calibration_frame": "ok"},
        "point_metrics": {
            "window_days": 30, "n_total": len(stats) * 80,
            "as_of_date": "2026-06-11",
            "per_stat": _make_per_stat(stats, bias=bias, pit_flag=pit_flag),
            "flags": flags,
        },
        "coverage_metrics": {
            "per_stat": {s: {"n": 80, "coverage": 0.80,
                             "nominal": 0.80, "gap": 0.0, "status": "ok"}
                         for s in stats},
            "flags": [],
        },
        "drift_metrics": {"model_count": 2, "flagged_models": [],
                          "n_flagged": 0, "flags": []},
        "all_flags": flags,
    }


def _make_empty_report() -> Dict[str, Any]:
    return {
        "generated_at": "2026-06-11T12:00:00+00:00",
        "data_sources": {},
        "point_metrics": {"window_days": 30, "n_total": 0,
                          "as_of_date": "unknown", "per_stat": {}, "flags": []},
        "coverage_metrics": {"per_stat": {}, "flags": []},
        "drift_metrics": {"model_count": 0, "flagged_models": [],
                          "n_flagged": 0, "flags": []},
        "all_flags": [],
    }


# ---------------------------------------------------------------------------
# 1. Non-empty per-stat report → stat names in markdown
# ---------------------------------------------------------------------------


def test_stat_names_appear_in_markdown():
    """Stat names from per_stat must appear in the rendered markdown."""
    md = drr.render_vault_note(_make_report(stats=("pts", "reb", "ast")))
    for stat in ("pts", "reb", "ast"):
        assert stat in md, f"Stat '{stat}' missing from markdown"


def test_stat_table_rendered_not_placeholder():
    """A non-empty per_stat must produce a Markdown table, not the placeholder."""
    md = drr.render_vault_note(_make_report(stats=("fg3m",)))
    assert "_No point calibration data available._" not in md
    assert "fg3m" in md


# ---------------------------------------------------------------------------
# 2. Required section headings always present
# ---------------------------------------------------------------------------


def test_required_headings_non_empty():
    """All required section headings appear in a non-empty report."""
    md = drr.render_vault_note(_make_report())
    for h in _REQUIRED_HEADINGS:
        assert h in md, f"Missing heading: {h!r}"


def test_required_headings_empty():
    """All required section headings appear even in an empty report."""
    md = drr.render_vault_note(_make_empty_report())
    for h in _REQUIRED_HEADINGS:
        assert h in md, f"Missing heading in empty report: {h!r}"


def test_banner_present():
    """The N-OBS-003 HTML banner must appear in every rendered note."""
    for report in (_make_report(), _make_empty_report()):
        assert drr._BANNER in drr.render_vault_note(report)


# ---------------------------------------------------------------------------
# 3. Bias flag surfaced when |bias| > 0.5
# ---------------------------------------------------------------------------


def test_bias_flag_appears_in_all_flags_section():
    """A bias flag in all_flags must appear in the ## All Flags section."""
    flag_text = "pts: bias=1.200 (|bias|>0.5)"
    report = _make_report(bias=1.2, all_flags=[flag_text])
    md = drr.render_vault_note(report)
    assert "## All Flags" in md
    assert flag_text in md


def test_no_flags_section_when_all_flags_empty():
    """## All Flags heading must be absent when all_flags is empty."""
    md = drr.render_vault_note(_make_report(all_flags=[]))
    assert "## All Flags" not in md


def test_flag_count_badge():
    """Status badge must reflect the correct flag count."""
    flags = ["pts: bias=1.2", "reb: PIT non-uniform"]
    assert "2 flag(s)" in drr.render_vault_note(_make_report(all_flags=flags))


def test_no_flag_badge_when_clean():
    """Status badge must say 'No flags' when all_flags is empty."""
    assert "No flags" in drr.render_vault_note(_make_report(all_flags=[]))


# ---------------------------------------------------------------------------
# 4. PIT non-uniform flag surfaced when present
# ---------------------------------------------------------------------------


def test_pit_non_uniform_in_table():
    """'non_uniform' must appear in the PIT Uniformity table cell."""
    md = drr.render_vault_note(_make_report(pit_flag="non_uniform"))
    assert "non_uniform" in md


def test_pit_ok_in_table():
    """'ok' must appear in the PIT Uniformity table cell."""
    md = drr.render_vault_note(_make_report(pit_flag="ok"))
    assert "ok" in md


def test_pit_flag_in_all_flags_section():
    """A PIT non-uniform flag in all_flags appears in the All Flags section."""
    pit_text = "pts: PIT non-uniform (p=0.007)"
    report = _make_report(pit_flag="non_uniform", all_flags=[pit_text])
    assert pit_text in drr.render_vault_note(report)


# ---------------------------------------------------------------------------
# 5. Empty report → valid minimal markdown without crashing
# ---------------------------------------------------------------------------


def test_empty_report_no_crash():
    """render_vault_note() on an empty stub must not raise."""
    try:
        md = drr.render_vault_note(_make_empty_report())
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"render_vault_note() crashed on empty report: {exc}")
    assert isinstance(md, str) and len(md.strip()) > 0


def test_empty_report_placeholder_strings():
    """Empty-report output must include the 'No data' fallback strings."""
    md = drr.render_vault_note(_make_empty_report())
    has_placeholder = (
        "_No data available._" in md
        or "_No point calibration data available._" in md
    )
    assert has_placeholder, "Expected no-data placeholder in empty report"


def test_empty_report_ends_with_newline():
    """render_vault_note() output must end with a newline."""
    assert drr.render_vault_note(_make_empty_report()).endswith("\n")


def test_minimal_keys_no_crash():
    """render_vault_note() must not crash if most optional sub-keys are absent."""
    minimal: Dict[str, Any] = {
        "generated_at": "2026-06-11T00:00:00",
        "point_metrics": {},
        "coverage_metrics": {},
        "drift_metrics": {},
        "all_flags": [],
    }
    try:
        md = drr.render_vault_note(minimal)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"render_vault_note() crashed on minimal keys: {exc}")
    assert isinstance(md, str)


# ---------------------------------------------------------------------------
# 6. Determinism — same input → same output
# ---------------------------------------------------------------------------


def test_deterministic_non_empty():
    """Two calls with the same dict produce identical output."""
    report = _make_report(stats=("pts", "reb"), bias=0.3)
    assert drr.render_vault_note(report) == drr.render_vault_note(report)


def test_deterministic_empty():
    """Determinism holds for the empty-report edge case."""
    report = _make_empty_report()
    assert drr.render_vault_note(report) == drr.render_vault_note(report)


def test_deterministic_with_flags():
    """Determinism holds when all_flags is populated."""
    flags = ["pts: bias=1.2 (|bias|>0.5)", "reb: PIT non-uniform (p=0.003)"]
    report = _make_report(all_flags=flags)
    assert drr.render_vault_note(report) == drr.render_vault_note(report)


# ---------------------------------------------------------------------------
# _render_stat_table — direct low-level coverage
# ---------------------------------------------------------------------------


def test_render_stat_table_empty_placeholder():
    """_render_stat_table with empty per_stat returns the placeholder string."""
    result = drr._render_stat_table({}, [("n", "n"), ("bias", "bias")])
    assert result == "_No data available._"


def test_render_stat_table_columns_and_values():
    """_render_stat_table includes column headers and stat values."""
    per_stat = {"pts": {"n": 50, "bias": 0.12}}
    result = drr._render_stat_table(per_stat, [("n", "n"), ("bias", "bias")])
    assert "pts" in result and "bias" in result and "50" in result


def test_render_stat_table_missing_key_dash():
    """_render_stat_table renders '—' for a key absent from the stat dict."""
    per_stat = {"pts": {"n": 50}}   # 'bias' key absent
    result = drr._render_stat_table(per_stat, [("n", "n"), ("bias", "bias")])
    assert "—" in result
