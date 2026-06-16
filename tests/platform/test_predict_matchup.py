"""Per-file tests for scripts.platformkit.predict_matchup (the buyer-facing CLI).

Run ONLY this file (full pytest freezes the box):
    python -m pytest tests/platform/test_predict_matchup.py -q
"""
from __future__ import annotations

import json

import pytest

import scripts.platformkit.predict_matchup as pm
from scripts.platformkit.predict_matchup import build_parser, live_kwargs
from scripts.platformkit.predictor_jd import _build_predictor

_SPORTS = ("nba", "mlb", "soccer", "tennis")


# ----------------------------- pure parsing / mapping (no corpus) -----------------

def test_parser_requires_sport_home_away():
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args([])  # missing required args
    a = p.parse_args(["--sport", "nba", "--home", "BOS", "--away", "LAL"])
    assert a.sport == "nba" and a.home == "BOS" and a.away == "LAL"


def test_parser_accepts_alias_and_rejects_unknown_sport():
    p = build_parser()
    a = p.parse_args(["--sport", "basketball_nba", "--home", "BOS", "--away", "LAL"])
    assert a.sport == "basketball_nba"
    with pytest.raises(SystemExit):
        p.parse_args(["--sport", "cricket", "--home", "A", "--away", "B"])


def test_live_kwargs_nba_complete_and_partial():
    p = build_parser()
    full = p.parse_args(["--sport", "nba", "--home", "BOS", "--away", "LAL",
                         "--elapsed", "24", "--home-score", "55", "--away-score", "50"])
    assert live_kwargs("nba", full) == {
        "elapsed_minutes": 24.0, "home_score": 55, "away_score": 50}
    partial = p.parse_args(["--sport", "nba", "--home", "BOS", "--away", "LAL",
                            "--elapsed", "24"])
    assert live_kwargs("nba", partial) is None  # missing scores -> pregame only


def test_live_kwargs_mlb_mapping():
    p = build_parser()
    a = p.parse_args(["--sport", "mlb", "--home", "NYY", "--away", "BOS",
                      "--inning", "5", "--half", "bottom",
                      "--home-score", "3", "--away-score", "2"])
    assert live_kwargs("mlb", a) == {
        "inning": 5, "half": "bottom", "home_runs": 3, "away_runs": 2}
    # missing half -> None
    b = p.parse_args(["--sport", "mlb", "--home", "NYY", "--away", "BOS",
                      "--inning", "5", "--home-score", "3", "--away-score", "2"])
    assert live_kwargs("mlb", b) is None


def test_live_kwargs_soccer_mapping():
    p = build_parser()
    a = p.parse_args(["--sport", "soccer", "--home", "Arsenal", "--away", "Chelsea",
                      "--elapsed", "60", "--home-score", "1", "--away-score", "0"])
    assert live_kwargs("soccer", a) == {
        "minute": 60.0, "home_goals": 1, "away_goals": 0}


def test_live_kwargs_tennis_mapping_with_and_without_games():
    p = build_parser()
    a = p.parse_args(["--sport", "tennis", "--home", "Djokovic", "--away", "Alcaraz",
                      "--sets-home", "1", "--sets-away", "0", "--surface", "Clay"])
    assert live_kwargs("tennis", a) == {
        "sets_p1": 1, "sets_p2": 0, "surface": "Clay"}
    b = p.parse_args(["--sport", "tennis", "--home", "Djokovic", "--away", "Alcaraz",
                      "--sets-home", "1", "--sets-away", "0",
                      "--games-home", "3", "--games-away", "2"])
    kw = live_kwargs("tennis", b)
    assert kw["sets_p1"] == 1 and kw["games_p1"] == 3 and kw["games_p2"] == 2


# ----------------------------- guarded end-to-end (corpus or skip) ----------------

@pytest.mark.parametrize("sport", _SPORTS)
def test_cli_unavailable_corpus_prints_message_and_returns_zero(monkeypatch, capsys, sport):
    monkeypatch.setattr(pm, "_build_predictor", lambda s: None)
    h, aw = ("Djokovic", "Alcaraz") if sport == "tennis" else ("AAA", "BBB")
    rc = pm.main(["--sport", sport, "--home", h, "--away", aw])
    assert rc == 0
    out = capsys.readouterr().out
    assert "corpus unavailable on this clone" in out


def _home_away(sport: str):
    if sport == "nba":
        return "BOS", "LAL"
    if sport == "mlb":
        return "NYY", "BOS"
    if sport == "soccer":
        return "Arsenal", "Man City"
    return "Novak Djokovic", "Carlos Alcaraz"


@pytest.mark.parametrize("sport", _SPORTS)
def test_cli_pregame_block_when_corpus_present(capsys, sport):
    if _build_predictor(sport) is None:
        pytest.skip(f"{sport}: corpus absent on this clone (gitignored)")
    h, aw = _home_away(sport)
    rc = pm.main(["--sport", sport, "--home", h, "--away", aw])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["edge_claimed"] is False
    ph = out["pregame"]["p_home_win"]
    assert ph is not None and 0.0 < float(ph) < 1.0


def test_cli_nba_ingame_coherent_with_pregame_at_tipoff(capsys):
    if _build_predictor("nba") is None:
        pytest.skip("nba corpus absent on this clone (gitignored)")
    rc = pm.main(["--sport", "nba", "--home", "BOS", "--away", "LAL",
                  "--elapsed", "0", "--home-score", "0", "--away-score", "0"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "ingame" in out
    pre = float(out["pregame"]["p_home_win"])
    live = float(out["ingame"]["p_home_win"])
    assert abs(live - pre) <= 0.06, f"tipoff live {live} should track pregame {pre}"
