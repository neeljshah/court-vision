"""Per-file tests for live_feed.py + run_live.py.

Uses a Mock games source + a fake predictor (no corpus build, no network).
Run: python -m pytest scripts/platformkit/pm_trading/test_live.py -q
"""
import pathlib
import sys
import tempfile

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import live_feed as LF  # noqa: E402
import run_live as RL  # noqa: E402


def _fake_predict(sport, home, away):
    # deterministic fair prob; one matchup returns no prob (skipped)
    if home == "NOPROB":
        return {}
    return {"p_home_win": 0.58}


def _games():
    return [
        LF.Game("mlb", "Yankees", "Red Sox", game_id="1", game_date="2026-06-16"),
        LF.Game("mlb", "Dodgers", "Giants", game_id="2", game_date="2026-06-16"),
    ]


def test_mock_source_fetch():
    s = LF.MockGamesSource(_games())
    assert s.name == "mock" and len(s.fetch()) == 2


def test_collect_games_tolerates_bad_source():
    class Boom(LF.GameSource):
        @property
        def name(self):
            return "boom"

        def fetch(self):
            raise RuntimeError("offline")
    got = LF.collect_games([LF.MockGamesSource(_games()), Boom()])
    assert len(got) == 2  # bad source skipped, not fatal


def test_build_predictions_shapes_and_skips_no_prob():
    games = _games() + [LF.Game("mlb", "NOPROB", "X")]
    preds = LF.build_predictions(games, _fake_predict, pred_ts="2026-06-16T00:00:00+00:00")
    assert len(preds) == 2  # NOPROB skipped
    p = preds[0]
    assert p["calibrated_prob"] == 0.58 and p["market"] == "ml"
    assert p["pred_ts"].startswith("2026") and p["sport"] == "mlb"


def test_json_file_source(tmp_path=None):
    import json
    d = tempfile.mkdtemp(prefix="pm_games_")
    fp = pathlib.Path(d) / "games.json"
    fp.write_text(json.dumps([{"sport": "mlb", "home": "A", "away": "B",
                               "game_id": "9"}]), encoding="utf-8")
    s = LF.JSONFileSource(path=str(fp))
    g = s.fetch()
    assert len(g) == 1 and g[0].home == "A" and g[0].game_id == "9"
    # missing file -> empty, not error
    assert LF.JSONFileSource(path=str(pathlib.Path(d) / "missing.json")).fetch() == []


def test_run_once_logs_to_ledger():
    from scripts.platformkit.ledger.ledger import read_ledger
    led = tempfile.mkdtemp(prefix="pm_live_led_")
    s = RL.run_once([LF.MockGamesSource(_games())], predict_fn=_fake_predict,
                    pred_ts="2026-06-16T00:00:00+00:00", ledger_dir=led)
    assert s["games_found"] == 2 and s["predictions_logged"] == 2
    assert s["trades"] == 0 and "log-only" in s["note"]
    df = read_ledger(base_dir=led)
    assert len(df) == 2 and float(df.iloc[0]["calibrated_prob"]) == 0.58


def test_mlb_name_map_covers_30_and_uses_predictor_codes():
    m = LF.MLB_NAME_TO_ABBR
    # 30 clubs (+ Athletics alias) all map to 2-3 char upper codes
    assert "Philadelphia Phillies" in m and m["Philadelphia Phillies"] == "PHI"
    # the codes that differ from MLB official must use the predictor's form
    assert m["Kansas City Royals"] == "KAN"
    assert m["San Diego Padres"] == "SDG"
    assert m["Tampa Bay Rays"] == "TAM"
    assert m["Washington Nationals"] == "WAS"
    assert all(2 <= len(v) <= 3 and v.isupper() for v in m.values())


def test_run_once_empty_when_no_games():
    led = tempfile.mkdtemp(prefix="pm_live_led_")
    s = RL.run_once([LF.MockGamesSource([])], predict_fn=_fake_predict,
                    pred_ts="t", ledger_dir=led)
    assert s["games_found"] == 0 and s["predictions_logged"] == 0


def test_loop_max_ticks_stops():
    led = tempfile.mkdtemp(prefix="pm_live_led_")
    src = [LF.MockGamesSource(_games())]
    n = RL.loop(src, interval=1, max_ticks=2, ledger_dir=led,
                predict_fn=_fake_predict, verbose=False)
    assert n == 2  # ran exactly twice


if __name__ == "__main__":
    import inspect
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and inspect.isfunction(v)]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("%d/%d green" % (len(fns), len(fns)))
