"""tests.platformkit.combo.test_combo_recalibrator -- MF1 inert + honest leg/build guards.

Sentinel ABSENT => build_combo_candidate returns None (byte-identical NO_CANDIDATE) on the
VERY FIRST line, even on a non-empty settled batch and an importable module. With the
sentinel PRESENT and a clean batch carrying the spec's legs, it builds a gate-consumable
candidate; an ABSENT leg returns None (honest NO_CANDIDATE, never a 0-filled column).

Per-file test only (full pytest freezes the box). ASCII; stdlib + numpy deps.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.combo import combo_recalibrator as CR  # noqa: E402
from scripts.platformkit.combo.combination_families import CombinationSpec  # noqa: E402
from scripts.platformkit.improve import pipeline_flag as PF  # noqa: E402


def _spec(a="run_diff", b="pace"):
    return CombinationSpec(
        family="COMB_DETAIL_x_DETAIL", sport="nba", target="winprob",
        signature="comb_detail_x_detail=a:%s|b:%s" % tuple(sorted((a, b))),
        params={"a": min(a, b), "b": max(a, b)})


def _settled(n=14, with_legs=True):
    """Each game carries BOTH a 1-outcome and a 0-outcome state (so the audit confirms a 1
    and the fitted column sees both classes); detail legs vary so the combo column is not
    degenerate."""
    games = []
    for i in range(n):
        def _det(j):
            return ({"run_diff": float(i - n / 2 + j), "pace": float(1 + ((i + j) % 3))}
                    if with_legs else {})
        states = [{"p0": 0.55 + 0.01 * (i % 5), "outcome": 1.0, "detail": _det(0)},
                  {"p0": 0.40 + 0.01 * (i % 5), "outcome": 0.0, "detail": _det(1)}]
        games.append({"sport": "nba", "game_id": "G%02d" % i, "outcome": 1.0,
                      "states": states})
    return games


def test_inert_when_sentinel_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")
    assert PF.pipeline_enabled() is False
    out = CR.build_combo_candidate(_spec(), "nba", _settled(14))
    assert out is None  # MF1 first line: byte-identical NO_CANDIDATE on a non-empty batch.
    # The bound build_fn is inert too (the enumerator path).
    fn = CR.make_build_fn("nba", _settled(14))
    assert fn(_spec()) is None


def test_builds_candidate_when_sentinel_present(monkeypatch, tmp_path):
    sentinel = tmp_path / "PIPELINE_ENABLED"
    sentinel.write_text("on", encoding="ascii")
    monkeypatch.setattr(PF, "SENTINEL_PATH", sentinel)
    assert PF.pipeline_enabled() is True
    cand = CR.build_combo_candidate(_spec(), "nba", _settled(14))
    assert cand is not None
    assert cand["family"] == "COMB_DETAIL_x_DETAIL"
    assert len(cand["base_preds"]) == len(cand["cand_preds"]) == len(cand["y"])
    assert cand["corpora"] == []           # single corpus -> gate REJECTs downstream
    assert cand["vs_close"] == "UNPROVEN"
    assert "$" not in str(cand) and "roi" not in str(cand).lower()


def test_absent_leg_returns_none_never_zero_fills(monkeypatch, tmp_path):
    sentinel = tmp_path / "PIPELINE_ENABLED"
    sentinel.write_text("on", encoding="ascii")
    monkeypatch.setattr(PF, "SENTINEL_PATH", sentinel)
    # Spec references legs that the batch does NOT carry -> honest NO_CANDIDATE.
    out = CR.build_combo_candidate(_spec("absent_a", "absent_b"), "nba", _settled(14))
    assert out is None
    # An empty batch (no legs at all) is also None.
    assert CR.build_combo_candidate(_spec(), "nba", _settled(14, with_legs=False)) is None
