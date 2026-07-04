"""Per-file tests for ingame_tail_scan_multi (synthetic corpora per sport).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_tail_scan_multi.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.ingame import ingame_tail_scan_multi as tsm


def _write_game(dirp: Path, sport: str, stem: str, rows) -> None:
    dirp.mkdir(parents=True, exist_ok=True)
    with open(dirp / ("%s.jsonl" % stem), "w", encoding="utf-8") as fh:
        for mkt, mdl, ts in rows:
            fh.write(json.dumps({"sport": sport, "game_id": stem, "ts": ts,
                                 "market_prob": mkt, "model_prob": mdl,
                                 "side": "home"}) + "\n")


def test_tennis_has_no_capture_reads_insufficient_n(tmp_path):
    # No tennis dir at all on disk -> n_games_graded=0 -> INSUFFICIENT_N.
    gd = tmp_path / "grade"
    gd.mkdir()
    res = tsm.scan_sport("tennis", grade_dir=gd, iters=20)
    assert res["n_games_graded"] == 0
    assert res["sport_verdict"] == "INSUFFICIENT_N"
    assert res["edge_claimed"] is False


def test_tennis_lookup_wired_to_resolver(monkeypatch, tmp_path):
    # _tennis_lookup() now builds a REAL TennisOutcomeResolver (drop-in, no longer
    # the always-None stub). Stub the resolver class so this stays offline/fast,
    # but the wiring itself (constructed + .home_win bound) is exercised for real.
    calls = []

    class _FakeResolver:
        def home_win(self, ticker):
            calls.append(ticker)
            return 1

    monkeypatch.setattr(
        "scripts.platformkit.ingame.tennis_outcome_resolver.TennisOutcomeResolver",
        lambda *a, **k: _FakeResolver())

    lookup = tsm._tennis_lookup()
    assert lookup("KXATPMATCH-26JUL05AUGDAV") == 1
    assert calls == ["KXATPMATCH-26JUL05AUGDAV"]


def test_tennis_scan_graded_count_via_wired_resolver(monkeypatch, tmp_path):
    # End-to-end: capture writes tennis ticks -> scan_sport(sport_lookup) uses the
    # SAME _tennis_lookup() dispatch this module wires -> graded games increments.
    gd = tmp_path / "grade" / "tennis"
    for i in range(25):
        _write_game(gd, "tennis", "KXATPMATCH-26JUL05AAA%03d" % i,
                   [(0.2, 0.2, "2026-07-05T00:00:00Z")] * 3)

    class _FakeResolver:
        def home_win(self, ticker):
            return 1  # every ticket resolves: code_a ("home") won

    monkeypatch.setattr(
        "scripts.platformkit.ingame.tennis_outcome_resolver.TennisOutcomeResolver",
        lambda *a, **k: _FakeResolver())

    res = tsm.scan_sport("tennis", grade_dir=tmp_path / "grade",
                         outcome_lookup=tsm._tennis_lookup(), iters=200)
    assert res["n_games_resolved"] == 25
    assert res["n_games_graded"] == 25
    assert res["sport_verdict"] == "SCANNED"


def test_soccer_lookup_excludes_draws(tmp_path):
    gd = tmp_path / "grade" / "soccer_intl"
    _write_game(gd, "soccer_intl", "KXWCGAME-26JUL01AAABBB",
                [(0.5, 0.5, "2026-07-01T00:00:00Z")])

    class _FakeResolver:
        def final_score(self, ticker):
            return (1, 1)  # draw
    lookup_calls = []

    def fake_lookup(stem):
        r = _FakeResolver().final_score(stem)
        lookup_calls.append(stem)
        return None if r is None or r[0] == r[1] else int(r[0] > r[1])

    res = tsm.scan_sport("soccer_intl", grade_dir=tmp_path / "grade",
                         outcome_lookup=fake_lookup, iters=20)
    assert res["n_games_resolved"] == 0
    assert res["n_games_unresolved"] == 1
    assert res["n_games_graded"] == 0
    assert res["sport_verdict"] == "INSUFFICIENT_N"


def test_soccer_lookup_resolves_win(tmp_path):
    gd = tmp_path / "grade" / "soccer_intl"
    for i in range(25):
        _write_game(gd, "soccer_intl", "G%03d" % i,
                   [(0.15, 0.15, "2026-07-01T00:00:00Z")] * 5)

    def lookup(stem):
        return 1  # every game: home won
    res = tsm.scan_sport("soccer_intl", grade_dir=tmp_path / "grade",
                         outcome_lookup=lookup, iters=200)
    assert res["n_games_resolved"] == 25
    assert res["n_games_graded"] == 25
    assert res["sport_verdict"] == "SCANNED"
    band = res["bands"]["[0.10,0.20)"]
    assert band["venue_verdict"] == "VENUE_UNDERPRICES"


def test_scan_all_never_raises_on_bad_sport(tmp_path):
    def _boom(**kw):
        raise RuntimeError("synthetic failure")
    orig = tsm.scan_sport
    try:
        tsm.scan_sport = _boom  # type: ignore
        results = tsm.scan_all(sports=["tennis"], grade_dir=tmp_path / "grade")
    finally:
        tsm.scan_sport = orig  # type: ignore
    assert results["tennis"]["sport_verdict"] == "ERROR"
    assert results["tennis"]["edge_claimed"] is False


def test_wnba_npb_kbo_in_sports_list():
    for sport in ("wnba", "npb", "kbo"):
        assert sport in tsm.SPORTS


def test_nba_in_sports_list():
    assert "nba" in tsm.SPORTS


def test_wnba_has_no_capture_reads_insufficient_n(tmp_path):
    gd = tmp_path / "grade"
    gd.mkdir()
    res = tsm.scan_sport("wnba", grade_dir=gd, iters=20)
    assert res["n_games_graded"] == 0
    assert res["sport_verdict"] == "INSUFFICIENT_N"
    assert res["edge_claimed"] is False


def test_npb_has_no_capture_reads_insufficient_n(tmp_path):
    gd = tmp_path / "grade"
    gd.mkdir()
    res = tsm.scan_sport("npb", grade_dir=gd, iters=20)
    assert res["n_games_graded"] == 0
    assert res["sport_verdict"] == "INSUFFICIENT_N"
    assert res["edge_claimed"] is False


def test_kbo_has_no_capture_reads_insufficient_n(tmp_path):
    gd = tmp_path / "grade"
    gd.mkdir()
    res = tsm.scan_sport("kbo", grade_dir=gd, iters=20)
    assert res["n_games_graded"] == 0
    assert res["sport_verdict"] == "INSUFFICIENT_N"
    assert res["edge_claimed"] is False


def test_nba_has_no_capture_reads_insufficient_n(tmp_path):
    gd = tmp_path / "grade"
    gd.mkdir()
    res = tsm.scan_sport("nba", grade_dir=gd, iters=20)
    assert res["n_games_graded"] == 0
    assert res["sport_verdict"] == "INSUFFICIENT_N"
    assert res["edge_claimed"] is False


def test_wnba_lookup_wired_to_resolver(monkeypatch):
    calls = []

    class _FakeResolver:
        def home_win(self, ticker):
            calls.append(ticker)
            return 1

    monkeypatch.setattr(
        "scripts.platformkit.ingame.wnba_outcome_resolver.WnbaOutcomeResolver",
        lambda *a, **k: _FakeResolver())
    lookup = tsm._wnba_lookup()
    assert lookup("KXWNBAGAME-26JUL05DALTOR-TOR") == 1
    assert calls == ["KXWNBAGAME-26JUL05DALTOR-TOR"]


def test_npb_lookup_wired_to_resolver(monkeypatch):
    calls = []

    class _FakeResolver:
        def home_win(self, ticker):
            calls.append(ticker)
            return 0

    monkeypatch.setattr(
        "scripts.platformkit.ingame.npb_outcome_resolver.NpbOutcomeResolver",
        lambda *a, **k: _FakeResolver())
    lookup = tsm._npb_lookup()
    assert lookup("KXNPBGAME-26JUL050500YOKYAK-YOK") == 0
    assert calls == ["KXNPBGAME-26JUL050500YOKYAK-YOK"]


def test_kbo_lookup_wired_to_resolver(monkeypatch):
    calls = []

    class _FakeResolver:
        def home_win(self, ticker):
            calls.append(ticker)
            return 1

    monkeypatch.setattr(
        "scripts.platformkit.ingame.kbo_outcome_resolver.KboOutcomeResolver",
        lambda *a, **k: _FakeResolver())
    lookup = tsm._kbo_lookup()
    assert lookup("KXKBOGAME-26JUL050500NCDKIA-NCD") == 1
    assert calls == ["KXKBOGAME-26JUL050500NCDKIA-NCD"]


def test_nba_lookup_wired_to_resolver(monkeypatch):
    calls = []

    class _FakeResolver:
        def home_win(self, ticker):
            calls.append(ticker)
            return 0

    monkeypatch.setattr(
        "scripts.platformkit.ingame.nba_outcome_resolver.NbaOutcomeResolver",
        lambda *a, **k: _FakeResolver())
    lookup = tsm._nba_lookup()
    assert lookup("KXNBAGAME-26JUN13NYKSAS-SAS") == 0
    assert calls == ["KXNBAGAME-26JUN13NYKSAS-SAS"]


def test_wnba_scan_graded_count_via_wired_resolver(monkeypatch, tmp_path):
    gd = tmp_path / "grade" / "wnba"
    for i in range(25):
        _write_game(gd, "wnba", "KXWNBAGAME-26JUL05AAA%03d" % i,
                   [(0.15, 0.15, "2026-07-05T00:00:00Z")] * 3)

    class _FakeResolver:
        def home_win(self, ticker):
            return 1

    monkeypatch.setattr(
        "scripts.platformkit.ingame.wnba_outcome_resolver.WnbaOutcomeResolver",
        lambda *a, **k: _FakeResolver())

    res = tsm.scan_sport("wnba", grade_dir=tmp_path / "grade",
                         outcome_lookup=tsm._wnba_lookup(), iters=200)
    assert res["n_games_resolved"] == 25
    assert res["n_games_graded"] == 25
    assert res["sport_verdict"] == "SCANNED"


def test_nba_scan_graded_count_via_wired_resolver(monkeypatch, tmp_path):
    gd = tmp_path / "grade" / "nba"
    for i in range(25):
        _write_game(gd, "nba", "KXNBAGAME-26JAN05AAA%03d" % i,
                   [(0.15, 0.15, "2026-01-05T00:00:00Z")] * 3)

    class _FakeResolver:
        def home_win(self, ticker):
            return 1

    monkeypatch.setattr(
        "scripts.platformkit.ingame.nba_outcome_resolver.NbaOutcomeResolver",
        lambda *a, **k: _FakeResolver())

    res = tsm.scan_sport("nba", grade_dir=tmp_path / "grade",
                         outcome_lookup=tsm._nba_lookup(), iters=200)
    assert res["n_games_resolved"] == 25
    assert res["n_games_graded"] == 25
    assert res["sport_verdict"] == "SCANNED"


def test_write_artifacts_writes_one_file_per_sport(tmp_path, monkeypatch):
    monkeypatch.setattr(tsm, "_REPO_ROOT", tmp_path)
    results = {
        "tennis": {"sport": "tennis", "sport_verdict": "INSUFFICIENT_N"},
        "soccer_intl": {"sport": "soccer_intl", "sport_verdict": "SCANNED"},
    }
    paths = tsm.write_artifacts(results)
    assert paths["tennis"] == tmp_path / "data" / "domains" / "tennis" / "ingame_tail_scan.json"
    loaded = json.loads(paths["tennis"].read_text(encoding="utf-8"))
    assert loaded["sport_verdict"] == "INSUFFICIENT_N"
    loaded2 = json.loads(paths["soccer_intl"].read_text(encoding="utf-8"))
    assert loaded2["sport_verdict"] == "SCANNED"
