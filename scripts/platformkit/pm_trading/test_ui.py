"""Per-file tests for ui.py (static dashboard generator; no network).

Run: python -m pytest scripts/platformkit/pm_trading/test_ui.py -q
"""
import pathlib
import sys
import tempfile

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import ui as UI  # noqa: E402


def _ledger_with_rows():
    from scripts.platformkit.ledger.ledger import append_prediction
    led = tempfile.mkdtemp(prefix="pm_ui_")
    for h, a in [("NYY", "BOS"), ("LAD", "SFG")]:
        append_prediction("mlb", "pregame", "ml", h, a, 0.61, {"x": 1},
                          "2026-06-16T15:00:00+00:00", game_date="2026-06-16",
                          game_id=h + a, base_dir=led)
    return led


def test_dashboard_renders_core_sections():
    led = _ledger_with_rows()
    htmls = UI.build_dashboard(ledger_dir=led, include_live=False,
                               now_iso="2026-06-16T18:00:00")
    assert "PM-Trading Dashboard" in htmls
    assert "PAPER MODE" in htmls and "NO betting edge is claimed" in htmls
    assert "Live now" in htmls and "Today's slate" in htmls
    assert "NYY" in htmls and "LAD" in htmls          # logged matchups shown
    assert "No games live right now." in htmls         # live skipped


def test_dashboard_is_ascii_and_has_stats():
    led = _ledger_with_rows()
    htmls = UI.build_dashboard(ledger_dir=led, include_live=False,
                               now_iso="2026-06-16T18:00:00")
    assert htmls.isascii()
    assert "Predictions" in htmls and "Paper P&L" in htmls


def test_empty_ledger_still_renders():
    led = tempfile.mkdtemp(prefix="pm_ui_empty_")
    htmls = UI.build_dashboard(ledger_dir=led, include_live=False)
    assert "No pregame predictions logged for today yet." in htmls
    assert "PM-Trading Dashboard" in htmls


def test_write_dashboard_creates_file():
    led = _ledger_with_rows()
    out = pathlib.Path(tempfile.mkdtemp(prefix="pm_ui_out_")) / "dash.html"
    p = UI.write_dashboard(path=str(out), ledger_dir=led, include_live=False)
    assert pathlib.Path(p).exists()
    assert "PM-Trading Dashboard" in pathlib.Path(p).read_text(encoding="utf-8")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("%d/%d green" % (len(fns), len(fns)))
