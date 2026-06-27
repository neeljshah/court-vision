"""Per-file tests for scripts.platformkit.paper.paper_today + et_day.

Synthetic temp ledgers ONLY -- never touches the real data/frontend ledgers.

Proves the three overnight audit fixes:
  * FIX 1 (ET day boundary): an 8pm-ET / 00:00-UTC bet buckets into the ET day, not
    the UTC date; the et_day helper cuts on America/New_York.
  * FIX 2 (flat-1u served rows): build_today's served placed/settled_today rows are
    flat 1u with unit_result recomputed at flat 1u -- NO legacy dollar-Kelly magnitude
    leaks onto the units rail, and the served rows RECONCILE to the curve.
  * FIX 3 (small-N CLV floor): mean_clv is INSUFFICIENT_DATA below MIN_CLV_N true
    closes and n_clv (the true-close count) is surfaced.

Run ONLY this file (the full suite freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/paper/test_paper_today.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from scripts.platformkit.paper import et_day as ET
from scripts.platformkit.paper import paper_today as PT


def _write_ledger(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _row(matchup: str, side: str, dec: float, *, status: str, outcome: str = None,
         settled_at: str = None, ts: str = None, unit_result: float = None,
         stake_units: float = 1.0, clv_pct: float = None) -> Dict[str, Any]:
    r: Dict[str, Any] = {
        "sport": "mlb", "matchup": matchup, "side": side, "taken_book": "stub",
        "taken_decimal": dec, "model_prob": 0.55, "stake_units": stake_units,
        "status": status, "executed": False, "ts": ts or "2026-06-20T18:00:00+00:00",
    }
    if status == "settled":
        r["outcome"] = outcome
        r["unit_result"] = unit_result
        r["settled_at"] = settled_at or "2026-06-20T23:00:00+00:00"
        r["clv_pct"] = clv_pct
        r["clv_status"] = "no_close" if clv_pct is None else "true_close"
    return r


# --------------------------------------------------------------------------- #
# FIX 1 -- ET day boundary
# --------------------------------------------------------------------------- #
def test_et_day_of_8pm_et_is_prior_date():
    # 2026-06-21T00:00:00Z == 8pm ET on 2026-06-20 (EDT, -4).
    assert ET.et_day_of("2026-06-21T00:00:00+00:00") == "2026-06-20"
    # 2026-06-21T04:00:00Z == midnight ET -> the ET day flips to 06-21.
    assert ET.et_day_of("2026-06-21T04:00:00+00:00") == "2026-06-21"
    # Trailing Z and naive (UTC-assumed) forms parse the same.
    assert ET.et_day_of("2026-06-21T00:00:00Z") == "2026-06-20"
    assert ET.et_day_of("2026-06-21T00:00:00") == "2026-06-20"


def test_settle_day_uses_et(tmp_path):
    row = _row("A@B", "home", 2.0, status="settled", outcome="win",
               unit_result=1.0, settled_at="2026-06-21T00:00:00+00:00")
    # 8pm ET 06-20 must bucket as 06-20, not the UTC 06-21.
    assert PT._settle_day(row) == "2026-06-20"


def test_build_today_buckets_8pm_et_bet_into_et_day(tmp_path):
    clv = tmp_path / "clv.jsonl"
    bank = tmp_path / "bank.json"
    # One settled bet at 8pm ET (00:00 UTC next date) -> belongs to ET 06-20.
    _write_ledger(clv, [
        _row("A@B", "home", 2.0, status="settled", outcome="win",
             unit_result=1.0, settled_at="2026-06-21T00:00:00+00:00"),
    ])
    doc = PT.build_today(clv_path=clv, today="2026-06-20", bankroll_path=bank)
    assert doc["date"] == "2026-06-20"
    assert len(doc["settled_today"]) == 1  # the 8pm-ET bet is on the 06-20 slate
    assert doc["day_units"] == 1.0


# --------------------------------------------------------------------------- #
# FIX 2 -- served rows flat-1u + reconcile to the curve
# --------------------------------------------------------------------------- #
def test_served_rows_are_flat_one_unit_and_reconcile(tmp_path):
    clv = tmp_path / "clv.jsonl"
    bank = tmp_path / "bank.json"
    # Legacy dollar-Kelly contamination: stake_units=500, unit_result=+536 / -500.
    _write_ledger(clv, [
        _row("A@B", "home", 2.08, status="settled", outcome="loss",
             unit_result=-500.0, stake_units=500.0,
             settled_at="2026-06-20T23:00:00+00:00"),
        _row("C@D", "away", 2.3, status="settled", outcome="win",
             unit_result=536.0, stake_units=412.31,
             settled_at="2026-06-20T23:30:00+00:00"),
        # an open placed bet with a fat dollar stake too
        _row("E@F", "home", 1.82, status="open", stake_units=500.0,
             ts="2026-06-20T18:00:00+00:00"),
    ])
    doc = PT.build_today(clv_path=clv, today="2026-06-20", bankroll_path=bank)
    # Every served row -- placed + pending + settled -- carries a flat 1u stake
    # (the E@F open bet's legacy 500 dollar-Kelly magnitude must NOT leak onto the
    # pending list; FIX 1 routes pending through the same _view_row flat-units rail).
    for r in doc["placed"] + doc["pending"] + doc["settled_today"]:
        assert r["stake_units"] == 1.0
        assert abs(float(r["stake_units"])) <= 1.0
    # The open bet appears in pending and is flat 1u, not 500.
    pend = {r["matchup"]: r for r in doc["pending"]}
    assert "E@F" in pend
    assert pend["E@F"]["stake_units"] == 1.0
    # Settled rows' unit_result is recomputed at flat 1u (loss=-1, win=+(dec-1)).
    by = {r["matchup"]: r["unit_result"] for r in doc["settled_today"]}
    assert by["A@B"] == -1.0                       # flat loss, not -500
    assert by["C@D"] == round(2.3 - 1.0, 6)        # flat win, not +536
    # The served settled rows RECONCILE to the curve: sum of served unit_results
    # equals the day's flat-normalised net (and the all-time cumulative here).
    served_net = round(sum(r["unit_result"] for r in doc["settled_today"]), 6)
    assert served_net == doc["day_units"]
    assert served_net == doc["cumulative_units"]
    assert doc["reconciles"] is True


def test_no_served_row_has_nonflat_stake_units(tmp_path):
    """FIX 1: NO served row (placed / pending / settled_today) has stake_units != 1.0.

    Builds a ledger where every status carries a fat legacy dollar-Kelly stake and
    asserts the units-only rail is intact across ALL three served lists.
    """
    clv = tmp_path / "clv.jsonl"
    bank = tmp_path / "bank.json"
    _write_ledger(clv, [
        _row("P1@X", "home", 1.91, status="open", stake_units=500.0,
             ts="2026-06-20T18:00:00+00:00"),
        _row("P2@X", "away", 2.40, status="open", stake_units=382.3,
             ts="2026-06-20T19:00:00+00:00"),
        _row("S1@X", "home", 2.10, status="settled", outcome="win",
             unit_result=611.0, stake_units=500.0,
             settled_at="2026-06-20T23:00:00+00:00"),
    ])
    doc = PT.build_today(clv_path=clv, today="2026-06-20", bankroll_path=bank)
    served = doc["placed"] + doc["pending"] + doc["settled_today"]
    assert served, "expected served rows in the view"
    offenders = [r for r in served if r.get("stake_units") != 1.0]
    assert not offenders, "non-flat served rows: %r" % offenders
    # pending carries the open positions, each flat-units.
    assert len(doc["pending"]) == 2
    for r in doc["pending"]:
        assert r["stake_units"] == 1.0
        assert r["flat_unit"] == 1.0


def test_view_row_does_not_mutate_ledger_row(tmp_path):
    src = _row("A@B", "home", 2.5, status="settled", outcome="win",
               unit_result=745.0, stake_units=500.0)
    out = PT._view_row(src, placed=True)
    # The served row is flat 1u; the SOURCE dict is untouched (on-read normalisation).
    assert out["stake_units"] == 1.0 and out["unit_result"] == round(2.5 - 1.0, 6)
    assert src["stake_units"] == 500.0 and src["unit_result"] == 745.0


# --------------------------------------------------------------------------- #
# FIX 3 -- small-N CLV floor + surfaced n_clv
# --------------------------------------------------------------------------- #
def test_mean_clv_insufficient_below_floor_and_surfaces_n_clv(tmp_path):
    clv = tmp_path / "clv.jsonl"
    bank = tmp_path / "bank.json"
    rows = []
    # 4 true closes (< MIN_CLV_N) among many no-close settled bets.
    for i in range(4):
        rows.append(_row("T%d@X" % i, "home", 2.0, status="settled", outcome="win",
                         unit_result=1.0, clv_pct=3.0,
                         settled_at="2026-06-20T2%d:00:00+00:00" % i))
    for i in range(10):
        rows.append(_row("N%d@X" % i, "away", 2.0, status="settled", outcome="loss",
                         unit_result=-1.0, clv_pct=None,
                         settled_at="2026-06-20T18:0%d:00+00:00" % i))
    _write_ledger(clv, rows)
    doc = PT.build_today(clv_path=clv, today="2026-06-20", bankroll_path=bank)
    # Only 4 true closes -> below MIN_CLV_N -> INSUFFICIENT_DATA, never a number.
    assert PT.MIN_CLV_N >= 8
    assert doc["mean_clv_pct_or_INSUFFICIENT"] == "INSUFFICIENT_DATA"
    assert doc["n_clv"] == 4  # the true-close count is surfaced
    assert doc["min_clv_n"] == PT.MIN_CLV_N


def test_mean_clv_reports_number_at_or_above_floor(tmp_path):
    clv = tmp_path / "clv.jsonl"
    bank = tmp_path / "bank.json"
    rows = [
        _row("T%d@X" % i, "home", 2.0, status="settled", outcome="win",
             unit_result=1.0, clv_pct=2.0,
             settled_at="2026-06-20T2%d:00:00+00:00" % (i % 6))
        for i in range(PT.MIN_CLV_N)
    ]
    _write_ledger(clv, rows)
    doc = PT.build_today(clv_path=clv, today="2026-06-20", bankroll_path=bank)
    assert doc["n_clv"] == PT.MIN_CLV_N
    assert doc["mean_clv_pct_or_INSUFFICIENT"] == 2.0  # now a real number
