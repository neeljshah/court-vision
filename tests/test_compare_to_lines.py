"""
test_compare_to_lines.py -- Tests for the scripts/compare_to_lines.py CLI.

The CLI reads a CSV of (player, opp, venue, stat, line, over_odds,
under_odds), pulls per-stat model predictions + calibrated quantile
intervals, then prints ranked EV bets (Kelly stake optional). All NBA
API + model + calibration calls are mocked; the suite runs offline.
"""

from __future__ import annotations

import json
import os
import sys
from math import erf, isclose, sqrt
from unittest import mock

import pytest


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import compare_to_lines  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _write_csv(tmp_path, rows, header=("player", "opp", "venue", "stat", "line",
                                       "over_odds", "under_odds")):
    """Write a list-of-dict rows to tmp_path/lines.csv and return its path."""
    p = tmp_path / "lines.csv"
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(header) + "\n")
        for r in rows:
            f.write(",".join(str(r.get(h, "")) for h in header) + "\n")
    return str(p)


def _patch_externals(monkeypatch, model_value, qint, calibration=None,
                     resolve_pid=203999):
    """Patch nba_api roster, build_prediction_row, predict_pergame,
    predict_pergame_quantiles, and apply_quantile_calibration."""
    fake_static = mock.MagicMock()
    fake_static.get_players.return_value = [
        {"id": resolve_pid, "full_name": "Nikola Jokić"},
        {"id": 1630162, "full_name": "Anthony Edwards"},
        {"id": 1628369, "full_name": "Jayson Tatum"},
    ]
    monkeypatch.setitem(sys.modules, "nba_api.stats.static.players",
                        fake_static)

    monkeypatch.setattr(compare_to_lines, "build_prediction_row",
                        lambda *a, **kw: {"f1": 1.0})
    monkeypatch.setattr(compare_to_lines, "predict_pergame",
                        lambda *a, **kw: model_value)
    monkeypatch.setattr(compare_to_lines, "predict_pergame_quantiles",
                        lambda *a, **kw: qint)
    # Calibration: by default return the raw (q10, q90).
    if calibration is None:
        monkeypatch.setattr(
            compare_to_lines, "apply_quantile_calibration",
            lambda stat, q10, q50, q90: (q10, q90))
    else:
        monkeypatch.setattr(
            compare_to_lines, "apply_quantile_calibration", calibration)


# ── CSV row parsing ──────────────────────────────────────────────────────────

def test_csv_row_parsing_runs_through_all_rows(tmp_path, monkeypatch, capsys):
    """Three rows in CSV → predictor called once per row, output table
    contains all three player names."""
    csv_path = _write_csv(tmp_path, [
        {"player": "Nikola Jokic", "opp": "LAL", "venue": "home",
         "stat": "pts", "line": 28.5, "over_odds": -110, "under_odds": -110},
        {"player": "Anthony Edwards", "opp": "DEN", "venue": "away",
         "stat": "pts", "line": 26.5, "over_odds": -110, "under_odds": -110},
        {"player": "Jayson Tatum", "opp": "NYK", "venue": "away",
         "stat": "reb", "line": 8.5, "over_odds": -110, "under_odds": -110},
    ])
    _patch_externals(monkeypatch, model_value=25.0,
                     qint={"q10": 15.0, "q50": 25.0, "q90": 35.0})
    monkeypatch.setattr(sys, "argv",
                        ["compare_to_lines.py", csv_path])
    compare_to_lines.main()
    out = capsys.readouterr().out
    assert "Nikola Jokic" in out
    assert "Anthony Edwards" in out
    assert "Jayson Tatum" in out


# ── EV math reproducibility ──────────────────────────────────────────────────

def test_ev_computation_matches_normal_cdf(monkeypatch, capsys, tmp_path):
    """Set model_pred=20, q10/q90 = 15/25 (calibration identity), line=22.5,
    odds=-110. Compute analytic _model_hit_prob and EV, then check that the
    printed EV column matches."""
    # raw spread is q90 - q10 = 10. sigma = 10 / (2 * 1.2816) ≈ 3.9013
    sigma = 10 / (2 * 1.2816)
    z = (22.5 - 20.0) / sigma
    cdf = 0.5 * (1 + erf(z / sqrt(2)))
    p_over = 1 - cdf
    p_under = 1 - p_over  # since model_pred < line → side = UNDER
    # Net payout @ -110 = 100/110 = 0.90909...
    payout = 100 / 110
    expected_ev = p_under * payout - (1 - p_under) * 1.0

    csv_path = _write_csv(tmp_path, [
        {"player": "Nikola Jokic", "opp": "LAL", "venue": "home",
         "stat": "pts", "line": 22.5, "over_odds": -110, "under_odds": -110},
    ])
    _patch_externals(monkeypatch, model_value=20.0,
                     qint={"q10": 15.0, "q50": 20.0, "q90": 25.0})
    monkeypatch.setattr(sys, "argv", ["compare_to_lines.py", csv_path])
    compare_to_lines.main()
    out = capsys.readouterr().out
    # The model_pred=20 < line=22.5, so the recommended side is UNDER.
    assert "UNDER" in out
    # The EV is printed as a signed 4-dp number; pull it out of the data row.
    data_row = next(ln for ln in out.splitlines() if "Nikola Jokic" in ln)
    # EV/$ is the 9th whitespace token in the row.
    tokens = data_row.split()
    # Layout: player(2 words) stat line model edge side prob odds EV Kelly
    # ['Nikola', 'Jokic', 'PTS', '22.5', '20.00', '-2.50', 'UNDER', '0.738', '-110', '+0.3093', '23.83%']
    ev_token = tokens[9]
    printed_ev = float(ev_token)
    assert isclose(printed_ev, round(expected_ev, 4), abs_tol=5e-4), \
        f"printed EV={printed_ev}, expected={expected_ev}"


# ── Kelly fraction sign behaviour ────────────────────────────────────────────

def test_kelly_zero_when_no_edge():
    """Kelly fraction must be 0 when the modelled probability is below the
    book's implied probability (negative edge)."""
    # -110 implies p_break_even = 110/210 ≈ 0.5238
    # Model says 0.40 → negative edge → Kelly = 0.
    kf = compare_to_lines._kelly_fraction(prob=0.40, odds=-110)
    assert kf == 0.0


def test_kelly_positive_when_edge_is_positive():
    """Kelly > 0 once the modelled probability sits above implied."""
    kf = compare_to_lines._kelly_fraction(prob=0.70, odds=-110)
    assert kf > 0.0


# ── ranking by EV descending ─────────────────────────────────────────────────

def test_ranking_is_by_ev_descending(monkeypatch, capsys, tmp_path):
    """First row's model is far from the line (big edge), second row's is
    close. The first row must appear before the second in the printed
    output."""
    csv_path = _write_csv(tmp_path, [
        # row A: model way above the line → big +EV
        {"player": "Anthony Edwards", "opp": "DEN", "venue": "away",
         "stat": "pts", "line": 20.0, "over_odds": -110, "under_odds": -110},
        # row B: model close to the line → small edge
        {"player": "Nikola Jokic", "opp": "LAL", "venue": "home",
         "stat": "pts", "line": 27.9, "over_odds": -110, "under_odds": -110},
    ])

    # Return a different model_pred per row by stat (both rows are PTS so use
    # call_count via a closure).
    call_state = {"n": 0}
    pred_per_call = [28.0, 28.0]   # constant: line=20 → edge=+8, line=27.9 → edge=+0.1

    def _pred(stat, row, model_dir):
        v = pred_per_call[call_state["n"]]
        call_state["n"] += 1
        return v

    _patch_externals(monkeypatch, model_value=28.0,
                     qint={"q10": 22.0, "q50": 28.0, "q90": 34.0})
    monkeypatch.setattr(compare_to_lines, "predict_pergame", _pred)
    monkeypatch.setattr(sys, "argv", ["compare_to_lines.py", csv_path])
    compare_to_lines.main()
    out = capsys.readouterr().out
    # The Anthony Edwards row (huge edge → high EV) must be printed BEFORE
    # the Jokic row (tiny edge → low EV).
    edw_idx = out.find("Anthony Edwards")
    jok_idx = out.find("Nikola Jokic")
    assert edw_idx != -1 and jok_idx != -1, out
    assert edw_idx < jok_idx, "Higher-EV bet should be ranked first"


# ── file-not-found gives clean exit ─────────────────────────────────────────

def test_missing_csv_raises_clean_error(monkeypatch, capsys, tmp_path):
    """Pointing at a nonexistent CSV must raise a recognisable error (not
    crash deep in csv.DictReader with a confusing traceback)."""
    missing = str(tmp_path / "does_not_exist.csv")
    monkeypatch.setattr(sys, "argv", ["compare_to_lines.py", missing])
    with pytest.raises((FileNotFoundError, SystemExit)):
        compare_to_lines.main()


# ── empty CSV exits cleanly ─────────────────────────────────────────────────

def test_empty_csv_exits_one(tmp_path, monkeypatch, capsys):
    """A header-only CSV (no rows) must print '[fail] empty CSV' and
    SystemExit(1)."""
    p = tmp_path / "empty.csv"
    p.write_text("player,opp,venue,stat,line,over_odds,under_odds\n",
                 encoding="utf-8")
    _patch_externals(monkeypatch, model_value=25.0,
                     qint={"q10": 15.0, "q50": 25.0, "q90": 35.0})
    monkeypatch.setattr(sys, "argv", ["compare_to_lines.py", str(p)])
    with pytest.raises(SystemExit) as ei:
        compare_to_lines.main()
    assert ei.value.code == 1
    out = capsys.readouterr().out
    assert "empty CSV" in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
