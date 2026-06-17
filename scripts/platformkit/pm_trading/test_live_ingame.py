"""Per-file tests for live_ingame.py + run_live in-game path (mock; no network).

Run: python -m pytest scripts/platformkit/pm_trading/test_live_ingame.py -q
"""
import pathlib
import sys
import tempfile

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import live_feed as LF  # noqa: E402
import live_ingame as LI  # noqa: E402
import run_live as RL  # noqa: E402


def _fake_live(g):
    # home prob rises with run differential (deterministic, clamped)
    p = 0.5 + 0.1 * ((g.home_runs or 0) - (g.away_runs or 0))
    return {"p_home_win": max(0.01, min(0.99, p))}


def _live_games():
    return [
        LF.Game("mlb", "NYY", "CWS", game_id="G1", game_date="2026-06-16",
                inning=7, half="bottom", home_runs=11, away_runs=2, state="Live"),
        LF.Game("mlb", "BOS", "TOR", game_id="G2", game_date="2026-06-16",
                inning=9, half="bottom", home_runs=1, away_runs=6, state="Live"),
    ]


def test_source_name():
    assert LI.MLBLiveStateSource().name == "mlb_live"


def test_build_ingame_shapes_and_layer():
    preds = LI.build_ingame_predictions(_live_games(), _fake_live,
                                        pred_ts="2026-06-16T23:00:00+00:00")
    assert len(preds) == 2
    p0 = preds[0]
    assert p0["layer"] == "ingame" and p0["market"] == "ml"
    assert p0["inputs"]["inning"] == 7 and p0["inputs"]["half"] == "bottom"
    assert p0["calibrated_prob"] > 0.9   # NYY up 9 runs


def test_build_ingame_skips_games_without_state():
    games = [LF.Game("mlb", "A", "B", game_id="X")]  # no inning/runs -> pregame
    assert LI.build_ingame_predictions(games, _fake_live, "t") == []


def test_run_ingame_once_logs_ingame_layer():
    from scripts.platformkit.ledger.ledger import read_ledger
    led = tempfile.mkdtemp(prefix="pm_ig_")
    s = RL.run_ingame_once([LF.MockGamesSource(_live_games())],
                           predict_live_fn=_fake_live,
                           pred_ts="2026-06-16T23:00:00+00:00", ledger_dir=led)
    assert s["mode"] == "ingame" and s["predictions_logged"] == 2
    df = read_ledger(base_dir=led)
    assert len(df) == 2 and set(df["layer"]) == {"ingame"}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("%d/%d green" % (len(fns), len(fns)))
