"""Per-file tests for status.py (read-only standing dashboard).

Run: python -m pytest scripts/platformkit/pm_trading/test_status.py -q
"""
import pathlib
import sys
import tempfile

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import status as S  # noqa: E402
from pnl import PnLBlotter  # noqa: E402
from venues.base import Fill, Side  # noqa: E402


def test_empty_when_no_record():
    rep = S.status_report(ledger_dir=tempfile.mkdtemp(prefix="pm_st_"),
                          blotter_dir=tempfile.mkdtemp(prefix="pm_st_"))
    assert rep["n_predictions"] == 0 and rep["n_graded"] == 0
    assert "EMPTY" in rep["standing"]
    assert "no edge claimed" in rep["note"]


def test_accumulating_after_predictions():
    from scripts.platformkit.ledger.ledger import append_prediction
    led = tempfile.mkdtemp(prefix="pm_st_led_")
    for i, (h, a) in enumerate([("NYY", "BOS"), ("LAD", "SFG"), ("HOU", "SEA")]):
        append_prediction("mlb", "pregame", "ml", h, a, 0.55,
                          {"i": i}, "2026-06-16T00:00:00+00:00",
                          game_date="2026-06-16", base_dir=led)
    rep = S.status_report(ledger_dir=led, blotter_dir=tempfile.mkdtemp())
    assert rep["n_predictions"] == 3 and rep["n_graded"] == 0
    assert rep["by_sport"].get("mlb") == 3
    assert rep["forward_days"] == 1
    assert "ACCUMULATING" in rep["standing"]


def test_by_layer_breakdown_separates_pregame_and_ingame():
    from scripts.platformkit.ledger.ledger import append_prediction
    led = tempfile.mkdtemp(prefix="pm_st_layer_")
    append_prediction("mlb", "pregame", "ml", "NYY", "BOS", 0.55, {"i": 1},
                      "2026-06-16T15:00:00+00:00", game_date="2026-06-16",
                      game_id="P1", base_dir=led)
    append_prediction("mlb", "ingame", "ml", "LAD", "SFG", 0.95, {"i": 2},
                      "2026-06-16T22:00:00+00:00", game_date="2026-06-16",
                      game_id="I1", base_dir=led)
    rep = S.status_report(ledger_dir=led, blotter_dir=tempfile.mkdtemp())
    assert rep["by_layer"]["pregame"]["n"] == 1
    assert rep["by_layer"]["ingame"]["n"] == 1
    # not settled yet -> no accuracy key, just counts
    assert rep["by_layer"]["pregame"]["settled"] == 0
    out = S.format_report(rep)
    assert "pregame" in out and "ingame" in out


def test_paper_blotter_surfaced():
    bdir = tempfile.mkdtemp(prefix="pm_st_blot_")
    b = PnLBlotter(base_dir=bdir)
    b.record_fill(Fill("F1", "O1", "M", Side.BUY, 100, 0.40, 1.0, "t1"))
    b.record_settlement("M", 1.0, 100, 0.40)  # +60 gross, -1 fee
    rep = S.status_report(ledger_dir=tempfile.mkdtemp(), blotter_dir=bdir)
    assert rep["paper"]["net_paper_pnl"] == 59.0 and rep["paper"]["n_fills"] == 1


def test_format_report_is_ascii_and_honest():
    rep = S.status_report(ledger_dir=tempfile.mkdtemp(), blotter_dir=tempfile.mkdtemp())
    out = S.format_report(rep)
    assert out.isascii()
    assert "paper" in out.lower() and "no edge claimed" in out
    assert "STATUS" in out


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("%d/%d green" % (len(fns), len(fns)))
