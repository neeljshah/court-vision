"""Per-file tests for ingame_paper_settle (offline; injected score/grade fns)."""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_paper_settle as ps


def _ledger(tmp_path, rows):
    p = tmp_path / "ledger.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def _open_bet(gid, side="home", ek=None):
    return {"channel": "paper_ingame", "status": "open", "sport": "mlb",
            "game_id": gid, "side": side, "market": "win_home",
            "taken_decimal": 1.9, "model_prob": 0.6,
            "edge_key": ek or ("mlb|%s|win_home|%s|2026-06-28" % (gid, side))}


def test_settles_resolvable_open_bets(tmp_path):
    led = _ledger(tmp_path, [_open_bet("KXMLBGAME-G1"), _open_bet("KXMLBGAME-G2")])
    scores = {"KXMLBGAME-G1": (5, 4), "KXMLBGAME-G2": (2, 7)}
    graded = []

    def fake_grade(bet, hs, as_, path=None):
        graded.append((bet["game_id"], hs, as_))
        return {"status": "settled", "outcome": "win" if hs > as_ else "loss"}

    doc = ps.settle_open(ledger_path=led, score_fn=lambda g: scores.get(g),
                         grade_fn=fake_grade)
    assert doc["settled"] == 2, doc
    assert doc["still_open"] == 0
    assert doc["by_sport"]["mlb"]["settled"] == 2
    assert set(g for g, _, _ in graded) == {"KXMLBGAME-G1", "KXMLBGAME-G2"}
    assert doc["executed"] is False and doc["edge_claimed"] is False


def test_unresolved_game_stays_open(tmp_path):
    led = _ledger(tmp_path, [_open_bet("LIVE1")])  # game not final -> score_fn None
    doc = ps.settle_open(ledger_path=led, score_fn=lambda g: None,
                         grade_fn=lambda *a, **k: {"status": "settled"})
    assert doc["settled"] == 0
    assert doc["still_open"] == 1
    assert doc["by_sport"]["mlb"]["open"] == 1


def test_idempotent_skips_already_settled(tmp_path):
    ek = "mlb|G9|win_home|home|2026-06-28"
    rows = [_open_bet("KXMLBGAME-G9", ek=ek),
            {"channel": "paper_ingame", "status": "settled", "edge_key": ek,
             "graded": True, "outcome": "win"}]
    led = _ledger(tmp_path, rows)
    called = []
    doc = ps.settle_open(ledger_path=led, score_fn=lambda g: (5, 4),
                         grade_fn=lambda *a, **k: called.append(1) or {"status": "settled"})
    assert doc["settled"] == 0          # already-settled edge_key skipped
    assert not called


def test_grade_error_counted_not_fatal(tmp_path):
    led = _ledger(tmp_path, [_open_bet("KXMLBGAME-G1"), _open_bet("KXMLBGAME-G2")])

    def boom(bet, hs, as_, path=None):
        if bet["game_id"] == "KXMLBGAME-G1":
            raise ValueError("boom")
        return {"status": "settled"}

    doc = ps.settle_open(ledger_path=led, score_fn=lambda g: (1, 0), grade_fn=boom)
    assert doc["errors"] == 1 and doc["settled"] == 1  # one bad settle didn't stop the other


def test_write_status(tmp_path):
    doc = ps.settle_open(ledger_path=_ledger(tmp_path, []), score_fn=lambda g: None)
    out = tmp_path / "status.json"
    ps.write_status(doc, out)
    assert out.exists()
    got = json.loads(out.read_text())
    assert got["component"] == ps.COMPONENT
    assert got["status"] == "OK"  # nothing open -> not stuck
    assert got["consecutive_zero_ticks"] == 0


def test_stuck_detector_flags_after_n_zero_ticks(tmp_path):
    """2026-07-07 incident shape: open>0, settled==0 for many ticks, errors==0
    -- must surface as STUCK instead of staying silent."""
    out = tmp_path / "status.json"
    for i in range(3):
        ps.write_status({"settled": 0, "still_open": 129}, out, stuck_after=3)
        got = json.loads(out.read_text())
        assert got["consecutive_zero_ticks"] == i + 1
    assert got["status"] == "STUCK"


def test_stuck_counter_resets_when_a_settle_lands(tmp_path):
    out = tmp_path / "status.json"
    for _ in range(5):
        ps.write_status({"settled": 0, "still_open": 10}, out, stuck_after=3)
    ps.write_status({"settled": 2, "still_open": 8}, out, stuck_after=3)
    got = json.loads(out.read_text())
    assert got["consecutive_zero_ticks"] == 0
    assert got["status"] == "OK"


def _soccer_bet(gid, side="home", ek=None):
    return {"channel": "paper_ingame", "status": "open", "sport": "soccer_intl",
            "game_id": gid, "side": side, "market": "win_home",
            "taken_decimal": 1.9, "model_prob": 0.6,
            "edge_key": ek or ("soccer_intl|%s|win_home|%s|2026-07-01" % (gid, side))}


def test_dispatch_routes_mlb_and_soccer_tickers_by_prefix():
    mlb_calls, soccer_calls = [], []

    def mlb_fn(t):
        mlb_calls.append(t)
        return (5, 4)

    def soccer_fn(t):
        soccer_calls.append(t)
        return (2, 1)

    fn = ps._dispatch_score_fn(mlb_fn, soccer_fn)
    assert fn("KXMLBGAME-26JUN241845PHIWSH") == (5, 4)
    assert fn("KXWCGAME-26JUL01ENGCOD") == (2, 1)
    assert fn("KXNBAGAME-whatever") is None  # unrecognised prefix -> never a guess
    assert mlb_calls == ["KXMLBGAME-26JUN241845PHIWSH"]
    assert soccer_calls == ["KXWCGAME-26JUL01ENGCOD"]


def test_dispatch_missing_resolver_leaves_ticker_unresolved():
    fn = ps._dispatch_score_fn(None, None)
    assert fn("KXMLBGAME-x") is None
    assert fn("KXWCGAME-x") is None


def test_dispatch_routes_wnba_ticker_by_prefix():
    wnba_calls = []

    def wnba_fn(t):
        wnba_calls.append(t)
        return (88, 81)

    fn = ps._dispatch_score_fn(None, None, wnba_fn=wnba_fn)
    assert fn("KXWNBAGAME-26JUL051930LVACHI") == (88, 81)
    assert fn("KXMLBGAME-x") is None  # no mlb resolver injected -> unresolved
    assert wnba_calls == ["KXWNBAGAME-26JUL051930LVACHI"]


def test_dispatch_missing_wnba_resolver_leaves_ticker_unresolved():
    fn = ps._dispatch_score_fn(None, None, wnba_fn=None)
    assert fn("KXWNBAGAME-26JUL051930LVACHI") is None


def test_dispatch_routes_tennis_ticker_by_prefix():
    tennis_calls = []

    def tennis_fn(t):
        tennis_calls.append(t)
        return (1, 0)

    fn = ps._dispatch_score_fn(None, None, tennis_fn=tennis_fn)
    assert fn("KXATPMATCH-26JUL05AUGDAV-DAV") == (1, 0)
    assert fn("KXWTAMATCH-26JUL05BENGAU-GAU") == (1, 0)
    assert fn("KXMLBGAME-x") is None  # no mlb resolver injected -> unresolved
    assert tennis_calls == ["KXATPMATCH-26JUL05AUGDAV-DAV", "KXWTAMATCH-26JUL05BENGAU-GAU"]


def test_dispatch_missing_tennis_resolver_leaves_ticker_unresolved():
    fn = ps._dispatch_score_fn(None, None, tennis_fn=None)
    assert fn("KXATPMATCH-26JUL05AUGDAV-DAV") is None
    assert fn("KXWTAMATCH-26JUL05BENGAU-GAU") is None


def _wnba_bet(gid, side="home", ek=None):
    return {"channel": "paper_ingame", "status": "open", "sport": "wnba",
            "game_id": gid, "side": side, "market": "win_home",
            "taken_decimal": 1.9, "model_prob": 0.6,
            "edge_key": ek or ("wnba|%s|win_home|%s|2026-07-05" % (gid, side))}


def test_settle_open_wnba_batch_via_injected_wnba_score_fn(tmp_path):
    ticker = "KXWNBAGAME-26JUL051930LVACHI"
    led = _ledger(tmp_path, [_wnba_bet(ticker)])
    score_fn = ps._dispatch_score_fn(None, None, wnba_fn=lambda t: (88, 81))

    def fake_grade(bet, hs, as_, path=None):
        return {"status": "settled", "outcome": "win" if hs > as_ else "loss"}

    doc = ps.settle_open(ledger_path=led, score_fn=score_fn, grade_fn=fake_grade)
    assert doc["settled"] == 1
    assert doc["by_sport"]["wnba"]["settled"] == 1


def test_wnba_score_fn_inert_without_scoreboard_parquet(monkeypatch, tmp_path):
    # WnbaOutcomeResolver() with no local parquet -> available=False -> _wnba_score_fn
    # returns None (the bet stays open, never a fabricated settle).
    from scripts.platformkit.ingame import wnba_outcome_resolver as wr
    monkeypatch.setattr(wr, "DEFAULT_SCOREBOARD_PARQUET", tmp_path / "missing.parquet")
    assert ps._wnba_score_fn() is None


def test_default_score_fn_paths_never_touch_network_when_score_fn_injected(tmp_path, monkeypatch):
    # settle_open with an explicit score_fn must NEVER build the default resolvers
    # (and therefore never call the soccer finals refresh) -- guards the per-file
    # test suite from making real network calls.
    called = []
    monkeypatch.setattr(ps, "_default_score_fn",
                        lambda: (called.append(1) or (lambda g: None)))
    led = _ledger(tmp_path, [_open_bet("KXMLBGAME-G1")])
    ps.settle_open(ledger_path=led, score_fn=lambda g: (5, 4),
                   grade_fn=lambda *a, **k: {"status": "settled"})
    assert not called


def test_settle_open_mixed_mlb_and_soccer_batch(tmp_path):
    led = _ledger(tmp_path, [_open_bet("KXMLBGAME-G1"),
                             _soccer_bet("KXWCGAME-26JUL01ENGCOD")])
    scores = {"KXMLBGAME-G1": (5, 4), "KXWCGAME-26JUL01ENGCOD": (2, 1)}

    def fake_grade(bet, hs, as_, path=None):
        return {"status": "settled", "outcome": "win" if hs > as_ else "loss"}

    doc = ps.settle_open(ledger_path=led, score_fn=lambda g: scores.get(g),
                         grade_fn=fake_grade)
    assert doc["settled"] == 2
    assert doc["by_sport"]["mlb"]["settled"] == 1
    assert doc["by_sport"]["soccer_intl"]["settled"] == 1


# --------------------------------------------------------------------------------------- #
# LANE 3: NPB/KBO dispatch wiring (capture-only today -- no bets placed for either sport,   #
# see inplay_capture_loop.DEFAULT_SPORTS; this settle arm activates the moment a future     #
# lane wires a live model, exercised here via injected score_fns).                          #
# --------------------------------------------------------------------------------------- #
def test_dispatch_routes_npb_ticker_by_prefix():
    npb_calls = []

    def npb_fn(t):
        npb_calls.append(t)
        return (5, 3)

    fn = ps._dispatch_score_fn(None, None, npb_fn=npb_fn)
    assert fn("KXNPBGAME-26JUL050500YOKYAK-YOK") == (5, 3)
    assert fn("KXMLBGAME-x") is None  # no mlb resolver injected -> unresolved
    assert npb_calls == ["KXNPBGAME-26JUL050500YOKYAK-YOK"]


def test_dispatch_routes_kbo_ticker_by_prefix():
    kbo_calls = []

    def kbo_fn(t):
        kbo_calls.append(t)
        return (6, 2)

    fn = ps._dispatch_score_fn(None, None, kbo_fn=kbo_fn)
    assert fn("KXKBOGAME-26JUL050500NCDKIA-NCD") == (6, 2)
    assert fn("KXWNBAGAME-x") is None  # no wnba resolver injected -> unresolved
    assert kbo_calls == ["KXKBOGAME-26JUL050500NCDKIA-NCD"]


def test_dispatch_missing_npb_kbo_resolvers_leaves_ticker_unresolved():
    fn = ps._dispatch_score_fn(None, None, npb_fn=None, kbo_fn=None)
    assert fn("KXNPBGAME-26JUL050500YOKYAK-YOK") is None
    assert fn("KXKBOGAME-26JUL050500NCDKIA-NCD") is None


def test_npb_score_fn_inert_without_results_parquet(monkeypatch, tmp_path):
    from scripts.platformkit.ingame import npb_outcome_resolver as nr
    monkeypatch.setattr(nr, "DEFAULT_RESULTS_PARQUET", tmp_path / "missing.parquet")
    assert ps._npb_score_fn() is None


def test_kbo_score_fn_inert_without_results_parquet(monkeypatch, tmp_path):
    from scripts.platformkit.ingame import kbo_outcome_resolver as kr
    monkeypatch.setattr(kr, "DEFAULT_RESULTS_PARQUET", tmp_path / "missing.parquet")
    assert ps._kbo_score_fn() is None


def test_settle_open_npb_kbo_batch_via_injected_score_fns(tmp_path):
    npb_ticker = "KXNPBGAME-26JUL050500YOKYAK-YOK"
    kbo_ticker = "KXKBOGAME-26JUL050500NCDKIA-NCD"
    led = _ledger(tmp_path, [
        {"channel": "paper_ingame", "status": "open", "sport": "npb",
         "game_id": npb_ticker, "side": "home", "market": "win_home",
         "taken_decimal": 1.9, "model_prob": 0.6,
         "edge_key": "npb|%s|win_home|home|2026-07-05" % npb_ticker},
        {"channel": "paper_ingame", "status": "open", "sport": "kbo",
         "game_id": kbo_ticker, "side": "home", "market": "win_home",
         "taken_decimal": 1.9, "model_prob": 0.6,
         "edge_key": "kbo|%s|win_home|home|2026-07-05" % kbo_ticker},
    ])
    scores = {npb_ticker: (5, 3), kbo_ticker: (6, 2)}
    score_fn = ps._dispatch_score_fn(None, None, npb_fn=lambda t: scores.get(t),
                                     kbo_fn=lambda t: scores.get(t))

    def fake_grade(bet, hs, as_, path=None):
        return {"status": "settled", "outcome": "win" if hs > as_ else "loss"}

    doc = ps.settle_open(ledger_path=led, score_fn=score_fn, grade_fn=fake_grade)
    assert doc["settled"] == 2
    assert doc["by_sport"]["npb"]["settled"] == 1
    assert doc["by_sport"]["kbo"]["settled"] == 1


# --------------------------------------------------------------------------------------- #
# MLB DOUBLEHEADERS (2026-07-07 MIL@STL incident): tickers end G1/G2; the boxscore has     #
# two same-day same-matchup rows disambiguated by start_time (G1 = earliest). Exercised    #
# end-to-end through the REAL MlbOutcomeResolver + dispatch + settle_open.                 #
# --------------------------------------------------------------------------------------- #
def _dh_box_df():
    import pandas as pd
    return pd.DataFrame([
        # G1: MIL won 6-2, first pitch 18:15Z
        {"event_id": "10", "date": "2026-07-07", "home_abbr": "STL", "away_abbr": "MIL",
         "home_score": 2.0, "away_score": 6.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-07T18:15Z"},
        # G2: STL won 5-1, first pitch 23:15Z
        {"event_id": "11", "date": "2026-07-07", "home_abbr": "STL", "away_abbr": "MIL",
         "home_score": 5.0, "away_score": 1.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-07T23:15Z"},
        # single game the same day (PHI @ WSH) -- must settle exactly as before
        {"event_id": "12", "date": "2026-07-07", "home_abbr": "WSH", "away_abbr": "PHI",
         "home_score": 4.0, "away_score": 3.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-07T22:05Z"},
    ])


def test_doubleheader_g1_g2_settle_against_correct_games(tmp_path):
    from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver
    res = MlbOutcomeResolver(box_df=_dh_box_df())
    g1 = "KXMLBGAME-26JUL071415MILSTLG1"
    g2 = "KXMLBGAME-26JUL071915MILSTLG2"
    single = "KXMLBGAME-26JUL071805PHIWSH"
    led = _ledger(tmp_path, [_open_bet(g1), _open_bet(g2), _open_bet(single)])
    graded = {}

    def fake_grade(bet, hs, as_, path=None):
        graded[bet["game_id"]] = (hs, as_)
        return {"status": "settled"}

    fn = ps._dispatch_score_fn(res.final_score, None)
    doc = ps.settle_open(ledger_path=led, score_fn=fn, grade_fn=fake_grade)
    assert doc["settled"] == 3, doc
    assert graded[g1] == (2, 6)      # G1 = earlier start
    assert graded[g2] == (5, 1)      # G2 = later start
    assert graded[single] == (4, 3)  # single-game ticker path unchanged


# --------------------------------------------------------------------------------------- #
# W1: settle_open must NEVER append extra ledger rows -- the kx-proxy CLV correction is    #
# READ-TIME ONLY (opus judge 2026-07-10: an on-disk twin double-counts settles in          #
# paper_analytics._iter_ledger, which has no bet_id dedup).                                #
# --------------------------------------------------------------------------------------- #
def test_settle_open_never_appends_ledger_rows(tmp_path, monkeypatch):
    from scripts.platformkit.ingame import ingame_paper_settle as psmod
    led = _ledger(tmp_path, [_open_bet("KXMLBGAME-G1")])

    def fake_grade(bet, hs, as_, path=None):
        return {"status": "settled", "outcome": "win", "clv_status": "no_close",
                "game_id": bet["game_id"], "sport": "mlb", "side": "home",
                "taken_decimal": 1.9, "bet_id": "bx1"}

    appended = []
    monkeypatch.setattr(psmod._clv, "append_settlement",
                        lambda row, path=None: appended.append(row) or row)
    doc = ps.settle_open(ledger_path=led, score_fn=lambda g: (5, 4), grade_fn=fake_grade)
    assert doc["settled"] == 1
    # no_close stays no_close on disk; proxy CLV attaches at read time only.
    assert appended == []


def test_doubleheader_no_gnum_or_missing_game_stays_open(tmp_path):
    from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver
    res = MlbOutcomeResolver(box_df=_dh_box_df())
    # no G suffix on a 2-row day (ambiguous) + a G2 whose day has only G1 final
    led = _ledger(tmp_path, [
        _open_bet("KXMLBGAME-26JUL071415MILSTL"),
    ])
    fn = ps._dispatch_score_fn(res.final_score, None)
    doc = ps.settle_open(ledger_path=led, score_fn=fn,
                         grade_fn=lambda *a, **k: {"status": "settled"})
    assert doc["settled"] == 0 and doc["still_open"] == 1  # fail closed
