"""Per-file tests for scripts.platformkit.paper.bankroll_daemon + paper_today.

NO NETWORK, NO real sleep: an isolated CLV ledger + bankroll + output paths AND a tmp
heartbeat_path under tmp_path; an injected clock so the heartbeat lands deterministically.
Proves:
  * one tick writes the series / bankroll / today JSON + beats the TMP heartbeat,
  * the injected fake clock NEVER touches the real m1_bankroll heartbeat or the real
    data/frontend files (the C3 heartbeat-poison fix),
  * the SINGLE canonical writer emits the UNIFIED schema (per_day[] AND daily[]),
  * the cumulative curve RECONCILES to the sum of the placed bets' graded unit_results,
  * the per-day ledger rolls over at UTC midnight (a new day opens at the prior close),
  * NO dollar/pnl/roi key is ever written to any output.

Run ONLY this file (the full suite freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/paper/test_bankroll_daemon.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from scripts.platformkit.paper import bankroll_daemon as D
from scripts.platformkit.paper import paper_today as T

_BANNED = ("pnl", "roi", "dollar", "dollars", "profit", "stake_dollars",
           "bankroll_usd", "usd", "$")


def _placed(matchup: str, side: str, dec: float, *, status: str,
            outcome: str = None, settled_at: str = None, ts: str = None,
            unit_result: float = None, tier: str = "B",
            clv_pct: float = None) -> Dict[str, Any]:
    """A PLACED paper-bet row as run_paper_today would record + grade_paper settle.

    stake_units is the flat 1 unit (post-fix). settled rows carry outcome + unit_result.
    """
    r: Dict[str, Any] = {
        "sport": "mlb", "matchup": matchup, "side": side, "taken_book": "stub",
        "taken_decimal": dec, "model_prob": 0.55, "stake_units": 1.0,
        "flat_unit": 1.0, "quarter_kelly": 0.0, "tier": tier,
        "status": status, "executed": False, "ts": ts or "2026-06-20T18:00:00+00:00",
    }
    if status == "settled":
        r["outcome"] = outcome
        r["unit_result"] = unit_result
        r["settled_at"] = settled_at or "2026-06-20T23:00:00+00:00"
        r["clv_pct"] = clv_pct
        r["clv_status"] = "no_close" if clv_pct is None else "true_close"
    return r


def _write_ledger(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _paths(tmp_path: Path):
    return {
        "clv_path": tmp_path / "clv_ledger.jsonl",
        "series_path": tmp_path / "paper_pnl_series.json",
        "today_path": tmp_path / "paper_today.json",
        "bankroll_path": tmp_path / "paper_bankroll.json",
        # heartbeat MUST be tmp so an injected fake clock can never poison the live
        # data/cache/daemon_heartbeats/m1_bankroll.txt (the C3 heartbeat-poison bug).
        "heartbeat_path": tmp_path / "m1_bankroll.txt",
    }


def _no_banned(obj: Any) -> None:
    """Recursively assert no banned $ key appears anywhere in a written payload."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k.lower() not in _BANNED, "banned $ key leaked: %r" % (k,)
            _no_banned(v)
    elif isinstance(obj, list):
        for v in obj:
            _no_banned(v)


# --------------------------------------------------------------------------- #
def test_tick_writes_outputs_and_beats_heartbeat(tmp_path):
    p = _paths(tmp_path)
    rows = [
        _placed("A@B", "home", 2.0, status="settled", outcome="win",
                unit_result=1.0, settled_at="2026-06-20T23:00:00+00:00"),
        _placed("C@D", "away", 2.0, status="settled", outcome="loss",
                unit_result=-1.0, settled_at="2026-06-20T23:30:00+00:00"),
        _placed("E@F", "home", 1.9, status="open"),  # still pending
    ]
    _write_ledger(p["clv_path"], rows)
    series = D.tick(now=123.0, today="2026-06-20", **p)
    assert p["series_path"].exists()
    assert p["today_path"].exists()
    assert p["bankroll_path"].exists()
    assert series["summary"]["n_bets"] == 2  # only the 2 settled placed bets move it
    assert series["reconciles"] is True
    # The tick beat the TMP heartbeat (not the live file): injected now=123.0 landed.
    assert p["heartbeat_path"].exists()
    assert p["heartbeat_path"].read_text(encoding="ascii").startswith("1970-01-01")
    # run() is bounded + offline: a fake clock/sleep, no network, beats every tick.
    sleeps: List[float] = []
    n = D.run(interval_sec=600.0, clock=lambda: 1.0,
              sleep=lambda s: sleeps.append(s), max_ticks=2, today="2026-06-20", **p)
    assert n == 2
    assert sleeps == [600.0]  # slept once between the two bounded ticks


def test_tick_never_touches_real_heartbeat_or_data_files(tmp_path):
    """C3 PROOF: an injected fake clock + tmp paths must NEVER stomp the real live
    heartbeat (data/cache/daemon_heartbeats/m1_bankroll.txt) or the real frontend
    files. We snapshot the real heartbeat's bytes+mtime, run tick AND a bounded run
    with the SAME epoch-1 fake clock the poisoning test used, and assert the real
    file is byte-for-byte unchanged (only the tmp heartbeat moved)."""
    import os
    real_hb = D.HEARTBEAT_PATH
    before = None
    if real_hb.exists():
        before = (real_hb.read_bytes(), os.path.getmtime(str(real_hb)))
    p = _paths(tmp_path)
    rows = [_placed("A@B", "home", 2.0, status="settled", outcome="win",
                    unit_result=1.0, settled_at="2026-06-20T23:00:00+00:00")]
    _write_ledger(p["clv_path"], rows)
    D.tick(now=1.0, today="2026-06-20", **p)            # epoch-1 fake clock
    D.run(interval_sec=600.0, clock=lambda: 1.0,
          sleep=lambda s: None, max_ticks=1, today="2026-06-20", **p)
    # The real heartbeat + canonical frontend files are UNTOUCHED.
    if before is not None:
        assert real_hb.read_bytes() == before[0]
        assert os.path.getmtime(str(real_hb)) == before[1]
    assert D.SERIES_PATH.resolve() != p["series_path"].resolve()
    assert D.TODAY_PATH.resolve() != p["today_path"].resolve()
    # Only the tmp heartbeat carries the (deliberately stale) epoch-1 stamp.
    assert p["heartbeat_path"].read_text(encoding="ascii").startswith("1970-01-01")


def test_series_emits_unified_per_day_and_daily_schema(tmp_path):
    """The SINGLE canonical writer must emit BOTH per_day[] (rich) AND daily[]
    ({day, daily_units}) plus points/summary/start_units -- so the webapp fallback
    (reads pnl.daily) resolves and the dual-writer split can never recur.

    Days are cut on the ET calendar: 23:00 UTC 06-20 is ET-evening 06-20; ET 06-21
    only begins at 04:00 UTC (00:00 ET), so the second bet uses 05:00 UTC = ET 06-21.
    """
    p = _paths(tmp_path)
    rows = [
        _placed("A@B", "home", 2.0, status="settled", outcome="win",
                unit_result=1.0, settled_at="2026-06-20T23:00:00+00:00"),
        _placed("C@D", "home", 2.0, status="settled", outcome="loss",
                unit_result=-1.0, settled_at="2026-06-21T05:00:00+00:00"),
    ]
    _write_ledger(p["clv_path"], rows)
    series = D.tick(now=1.0, today="2026-06-21", **p)
    doc = json.loads(p["series_path"].read_text(encoding="utf-8"))
    # Both schemas present in the SAME file.
    assert isinstance(doc["per_day"], list) and isinstance(doc["daily"], list)
    assert "points" in doc and "summary" in doc and "start_units" in doc
    assert doc["summary"].get("current_units") is not None
    # daily[] mirrors per_day[]'s net for each day (FE reads {day, daily_units}).
    per_day_net = {d["day"]: d["day_units"] for d in doc["per_day"]}
    daily_net = {d["day"]: d["daily_units"] for d in doc["daily"]}
    assert per_day_net == daily_net
    assert set(daily_net) == {"2026-06-20", "2026-06-21"}
    assert daily_net["2026-06-20"] == 1.0 and daily_net["2026-06-21"] == -1.0
    assert series["daily"] == doc["daily"]


def test_curve_reconciles_to_placed_unit_results(tmp_path):
    """The cumulative curve MUST equal the sum of the placed graded unit_results."""
    p = _paths(tmp_path)
    rows = [
        _placed("A@B", "home", 2.5, status="settled", outcome="win",
                unit_result=1.5, settled_at="2026-06-20T23:00:00+00:00"),
        _placed("C@D", "away", 2.0, status="settled", outcome="loss",
                unit_result=-1.0, settled_at="2026-06-20T23:30:00+00:00"),
        _placed("G@H", "home", 1.8, status="settled", outcome="win",
                unit_result=0.8, settled_at="2026-06-20T23:45:00+00:00"),
    ]
    _write_ledger(p["clv_path"], rows)
    series = D.tick(now=1.0, today="2026-06-20", **p)
    # flat-1-unit recompute: win@2.5 -> +1.5, loss -> -1.0, win@1.8 -> +0.8 => +1.3
    expected = round(1.5 - 1.0 + 0.8, 6)
    assert series["summary"]["total_units"] == expected
    # bankroll JSON + series + reconcile() helper all agree (one source of truth)
    bank = json.loads(p["bankroll_path"].read_text(encoding="utf-8"))
    assert bank["current_units"] == round(bank["start_units"] + expected, 6)
    placed = T.load_placed(p["clv_path"])
    rec = T.reconcile(placed, start_units=bank["start_units"])
    assert rec["cumulative_units"] == expected
    assert series["reconciles"] is True


def test_symmetric_two_way_collapses_to_one_bet_in_curve(tmp_path):
    """C1 FIX: both sides of a symmetric two-way market in the CLV ledger must NOT
    double-count -- the curve / n_bets / bankroll reflect ONE position per market.

    home (model_prob 0.586) and away (0.414) of the SAME market both settled; only the
    model-backed home side reaches the curve. Without the fix n_bets=2 and the win/loss
    flatter the total; with it n_bets=1 (home loss) and the curve reconciles to it.
    """
    p = _paths(tmp_path)
    home = _placed("A@B", "home", 1.95, status="settled", outcome="loss",
                   unit_result=-1.0, settled_at="2026-06-20T23:00:00+00:00")
    home["model_prob"] = 0.586
    away = _placed("A@B", "away", 2.60, status="settled", outcome="win",
                   unit_result=1.6, settled_at="2026-06-20T23:00:00+00:00")
    away["model_prob"] = 0.414
    _write_ledger(p["clv_path"], [home, away])
    series = D.tick(now=1.0, today="2026-06-20", **p)
    assert series["summary"]["n_bets"] == 1            # one position, not two
    assert series["summary"]["total_units"] == -1.0    # the model-backed home loss only
    assert series["reconciles"] is True                # reconcile() agrees -> truthful
    bank = json.loads(p["bankroll_path"].read_text(encoding="utf-8"))
    assert bank["current_units"] == round(bank["start_units"] - 1.0, 6)
    placed = T.load_placed(p["clv_path"])
    rec = T.reconcile(placed, start_units=bank["start_units"])
    assert rec["n_settled"] == 1 and rec["cumulative_units"] == -1.0


def test_per_team_two_sided_clv_market_not_collapsed(tmp_path):
    """A genuine per-team CLV market (distinct LINE on the same matchup/day) survives as
    TWO distinct positions -- only the symmetric SAME-line two-way collapses to one."""
    p = _paths(tmp_path)
    m1h = _placed("A@B", "home", 1.9, status="settled", outcome="win",
                  unit_result=0.9, settled_at="2026-06-20T23:00:00+00:00")
    m1h["line"] = 4.5; m1h["model_prob"] = 0.62
    m1a = _placed("A@B", "away", 2.0, status="settled", outcome="loss",
                  unit_result=-1.0, settled_at="2026-06-20T23:00:00+00:00")
    m1a["line"] = 4.5; m1a["model_prob"] = 0.38
    m2 = _placed("A@B", "home", 1.8, status="settled", outcome="win",
                 unit_result=0.8, settled_at="2026-06-20T23:00:00+00:00")
    m2["line"] = 9.5; m2["model_prob"] = 0.55
    _write_ledger(p["clv_path"], [m1h, m1a, m2])
    series = D.tick(now=1.0, today="2026-06-20", **p)
    # two distinct markets (line 4.5 backed-side + line 9.5), the 4.5 two-way collapsed
    assert series["summary"]["n_bets"] == 2
    assert series["summary"]["total_units"] == round(0.9 + 0.8, 6)
    assert series["reconciles"] is True


def test_daily_rollover_at_et_midnight(tmp_path):
    """Per-day ledger: a new ET day opens at the prior day's closing equity.

    The slate is an ET slate, so the rollover is ET midnight (= 04:00 UTC), NOT UTC
    midnight. 23:00 UTC 06-20 is ET-evening 06-20; the two 06-21 bets are at 05:00 and
    06:00 UTC (ET 01:00 / 02:00 on 06-21), so they land on the ET 06-21 day.
    """
    p = _paths(tmp_path)
    rows = [
        _placed("A@B", "home", 2.0, status="settled", outcome="win",
                unit_result=1.0, settled_at="2026-06-20T23:00:00+00:00"),
        _placed("C@D", "home", 2.0, status="settled", outcome="win",
                unit_result=1.0, settled_at="2026-06-21T05:00:00+00:00"),
        _placed("E@F", "away", 2.0, status="settled", outcome="loss",
                unit_result=-1.0, settled_at="2026-06-21T06:00:00+00:00"),
    ]
    _write_ledger(p["clv_path"], rows)
    series = D.tick(now=1.0, today="2026-06-21", **p)
    per_day = {d["day"]: d for d in series["per_day"]}
    assert set(per_day) == {"2026-06-20", "2026-06-21"}
    d20, d21 = per_day["2026-06-20"], per_day["2026-06-21"]
    assert d20["day_units"] == 1.0
    assert d20["end_units"] == round(d20["start_units"] + 1.0, 6)
    # day 21 OPENS at day 20's close (continuous bankroll), nets +1 -1 = 0
    assert d21["start_units"] == d20["end_units"]
    assert d21["day_units"] == 0.0
    assert d21["cumulative_units"] == 1.0  # all-time net carries across the rollover
    # today's view shows only the rollover day's settled bets + today's net
    today = json.loads(p["today_path"].read_text(encoding="utf-8"))
    assert today["date"] == "2026-06-21"
    assert today["day_units"] == 0.0
    assert len(today["settled_today"]) == 2


def test_8pm_et_bet_buckets_into_et_day_not_utc(tmp_path):
    """FIX 1 PROOF: a bet settled at 8pm ET (= 00:00 UTC of the NEXT date) buckets into
    the ET day, NOT the UTC date. settled_at 2026-06-21T00:00:00Z is ET 2026-06-20 20:00,
    so it must land on the 06-20 daily bucket (the live bug had it on 06-21)."""
    p = _paths(tmp_path)
    rows = [
        _placed("A@B", "home", 2.0, status="settled", outcome="win",
                unit_result=1.0, settled_at="2026-06-21T00:00:00+00:00"),
    ]
    _write_ledger(p["clv_path"], rows)
    series = D.tick(now=1.0, today="2026-06-20", **p)
    per_day = {d["day"]: d for d in series["per_day"]}
    # The 00:00-UTC (8pm ET) bet is the 06-20 ET slate, never 06-21.
    assert set(per_day) == {"2026-06-20"}
    assert per_day["2026-06-20"]["day_units"] == 1.0
    bank = json.loads(p["bankroll_path"].read_text(encoding="utf-8"))
    assert bank["day"] == "2026-06-20"
    assert bank["day_units"] == 1.0
    today = json.loads(p["today_path"].read_text(encoding="utf-8"))
    assert today["date"] == "2026-06-20"
    assert len(today["settled_today"]) == 1


def test_no_dollar_key_ever_written(tmp_path):
    p = _paths(tmp_path)
    rows = [_placed("A@B", "home", 2.0, status="settled", outcome="win",
                    unit_result=1.0, clv_pct=3.2)]
    _write_ledger(p["clv_path"], rows)
    D.tick(now=1.0, today="2026-06-20", **p)
    for fpath in (p["series_path"], p["today_path"], p["bankroll_path"]):
        doc = json.loads(fpath.read_text(encoding="utf-8"))
        _no_banned(doc)
        assert doc.get("edge_claimed") is False
        assert doc.get("executed") is False


def test_legacy_dollar_stake_units_renormalised_to_flat(tmp_path):
    """A legacy row whose stake_units is a contaminated DOLLAR amount (e.g. 382) is
    re-staked to a flat 1 unit -- the curve never inherits the dollar magnitude."""
    p = _paths(tmp_path)
    row = _placed("A@B", "home", 2.71, status="settled", outcome="loss",
                  unit_result=-382.317, settled_at="2026-06-20T23:00:00+00:00")
    row["stake_units"] = 382.317  # legacy dollar-Kelly contamination
    _write_ledger(p["clv_path"], [row])
    series = D.tick(now=1.0, today="2026-06-20", **p)
    # flat recompute: a loss is -1.0 unit, NOT -382.317
    assert series["summary"]["total_units"] == -1.0


def test_empty_ledger_degrades_cleanly(tmp_path):
    p = _paths(tmp_path)
    _write_ledger(p["clv_path"], [])
    series = D.tick(now=1.0, today="2026-06-20", **p)
    assert series["summary"]["total_units"] == 0.0
    assert series["summary"]["n_bets"] == 0
    assert series["reconciles"] is True
