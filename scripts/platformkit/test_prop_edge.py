"""Per-file tests for scripts.platformkit.prop_edge (network-free).

  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_edge.py -q
"""
from __future__ import annotations

import json
import os

import pandas as pd

from scripts.platformkit import prop_edge
from scripts.platformkit.odds_provider.base import unavailable
from scripts.platformkit.odds_provider.prop_base import PropLine


def _df():
    # Two prior matches each for our two resolvable players (so not "thin").
    rows = []
    for date in ("2026-06-01", "2026-06-05"):
        rows.append({"player_id": "100", "player": "Luis Diaz", "team_abbr": "COL",
                     "position": "F", "minutes": 90, "totalShots": 3,
                     "shotsOnTarget": 1, "date": date})
        rows.append({"player_id": "200", "player": "Kylian Mbappe", "team_abbr": "FRA",
                     "position": "F", "minutes": 90, "totalShots": 4,
                     "shotsOnTarget": 2, "date": date})
    return pd.DataFrame(rows)


class _CannedProvider:
    def __init__(self, name, rows):
        self.name = name
        self._rows = rows

    def fetch_props(self, sport):
        return list(self._rows)


class _DownProvider:
    name = "down"

    def fetch_props(self, sport):
        return unavailable("down: no rows")


def _lines():
    priced = PropLine(
        sport="soccer_intl", event_id="u1", match="COL v FRA",
        player="Luis Diaz", team="COL", stat="Shots", line=2.5,
        over_price=1.90, under_price=1.90, payout_type="sportsbook",
        source="underdog",
    )
    pickem = PropLine(
        sport="soccer_intl", event_id="p1", match="COL v FRA",
        player="Kylian Mbappe", team="FRA", stat="Shots On Target", line=1.5,
        over_price=None, under_price=None, payout_type="dfs_pickem",
        source="prizepicks",
    )
    unresolved = PropLine(
        sport="soccer_intl", event_id="p2", match="COL v FRA",
        player="Cristiano Ronaldo", team="POR", stat="Goals", line=0.5,
        over_price=None, under_price=None, payout_type="dfs_pickem",
        source="prizepicks",
    )
    return [priced, pickem, unresolved]


def _patch_dist(monkeypatch, p_over=0.62):
    """Force prop_distribution to a deterministic ok result."""
    def fake(df, player_id, stat_c, as_of, **kw):
        return {
            "lam": 2.1, "model": "poisson",
            "p_over": lambda line: p_over,
            "status": "ok", "per90": 3.0, "e_minutes": 90.0,
        }
    monkeypatch.setattr(prop_edge.prop_engine, "prop_distribution", fake)


def test_priced_and_pickem_and_unresolved(monkeypatch):
    _patch_dist(monkeypatch, p_over=0.62)
    providers = [_CannedProvider("underdog", [_lines()[0]]),
                 _CannedProvider("prizepicks", _lines()[1:])]
    board = prop_edge.build_prop_board(
        "soccer_intl", as_of="2026-06-11", providers=providers, df=_df())

    assert board["status"] == "ok"
    edges = board["edges"]
    assert len(edges) == 2  # priced + pickem resolve; Ronaldo does not.

    # The Ronaldo row is unresolved (name not in df).
    assert board["unresolved_count"] == 1
    assert board["unresolved"][0]["player"] == "Cristiano Ronaldo"

    priced = next(e for e in edges if e["edge_basis"] == "ev_vs_priced")
    assert isinstance(priced["best_ev"], float)
    assert priced["tier"] == "MODEL_VIEW"
    assert priced["best_side"] in ("over", "under")
    assert priced["side"] == "over"  # p_over 0.62 >= 0.5

    pickem = next(e for e in edges if e["edge_basis"] == "model_view")
    assert pickem["best_ev"] is None
    assert isinstance(pickem["model_gap"], float)
    assert abs(pickem["model_gap"] - 0.12) < 1e-6  # |0.62 - 0.5|


def test_ranking_priced_before_pickem(monkeypatch):
    _patch_dist(monkeypatch, p_over=0.62)
    providers = [_CannedProvider("underdog", [_lines()[0]]),
                 _CannedProvider("prizepicks", _lines()[1:])]
    board = prop_edge.build_prop_board(
        "soccer_intl", as_of="2026-06-11", providers=providers, df=_df())
    # First edge must be the priced one.
    assert board["edges"][0]["edge_basis"] == "ev_vs_priced"
    assert board["edges"][-1]["edge_basis"] == "model_view"


def test_unknown_sport_no_raise():
    board = prop_edge.build_prop_board("basketball_nba", df=_df())
    assert board["status"] == "unknown_sport"
    assert board["edges"] == []


def test_provider_down_is_recorded(monkeypatch):
    _patch_dist(monkeypatch)
    board = prop_edge.build_prop_board(
        "soccer_intl", as_of="2026-06-11", providers=[_DownProvider()], df=_df())
    assert board["status"] == "ok"
    assert "down" in board["sources"]
    assert board["edges"] == []


def test_lines_source_bypass(monkeypatch):
    _patch_dist(monkeypatch)
    board = prop_edge.build_prop_board(
        "soccer_intl", as_of="2026-06-11", df=_df(), lines_source=_lines())
    assert board["status"] == "ok"
    assert len(board["edges"]) == 2
    assert board["unresolved_count"] == 1


# ---- calibration-tiered ranking (BUILD 2) --------------------------------------

def _calib_cache(tmp_path):
    """Stub cache: Saves PROVEN (bss 0.3), Shots On Target WEAK (bss -0.05)."""
    p = os.path.join(str(tmp_path), "calib.json")
    payload = {"as_of": "x", "mode": "strict leak-free", "overall": {},
               "per_stat": {
                   "Saves": {"bss": 0.3, "n": 662, "brier": 0.02, "ece": 0.004},
                   "Shots On Target": {"bss": -0.05, "n": 662, "brier": 0.15,
                                       "ece": 0.07}}}
    with open(p, "w", encoding="ascii") as fh:
        json.dump(payload, fh)
    return p


def _two_priced_lines():
    # A PROVEN-stat (Saves) edge and a higher-EV WEAK-stat (SOT) edge, both
    # two-sided priced (so reliable + ev_flag ok). Same two resolvable players.
    saves = PropLine(
        sport="soccer_intl", event_id="s1", match="COL v FRA",
        player="Luis Diaz", team="COL", stat="Saves", line=2.5,
        over_price=1.95, under_price=1.95, payout_type="sportsbook",
        source="underdog")
    sot = PropLine(
        sport="soccer_intl", event_id="s2", match="COL v FRA",
        player="Kylian Mbappe", team="FRA", stat="Shots On Target", line=1.5,
        over_price=2.20, under_price=1.70, payout_type="sportsbook",
        source="underdog")  # priced so SOT's raw EV > Saves' EV
    return [saves, sot]


def test_calibration_promotes_proven_over_higher_ev_weak(monkeypatch, tmp_path):
    # SOT priced to give it a LARGER raw EV than Saves; calibration must still
    # rank the PROVEN Saves edge first. Force both edges reliable (club-backed)
    # so the proven path (reliable + ev ok) is exercised.
    _patch_dist(monkeypatch, p_over=0.62)
    monkeypatch.setattr(prop_edge, "_confidence", lambda *a, **k: "ok")
    board = prop_edge.build_prop_board(
        "soccer_intl", as_of="2026-06-11", df=_df(),
        lines_source=_two_priced_lines(), calibration_path=_calib_cache(tmp_path))
    assert board["status"] == "ok"
    edges = board["edges"]
    assert len(edges) == 2
    by_stat = {e["stat"]: e for e in edges}
    # labels attached
    assert by_stat["Saves"]["calibration"] == "proven"
    assert by_stat["Saves"]["tier"] == "CALIBRATION_PROVEN"
    assert by_stat["Saves"]["oos_bss"] == 0.3
    assert by_stat["Shots On Target"]["calibration"] == "weak"
    assert by_stat["Shots On Target"]["tier"] == "MODEL_VIEW"
    # the WEAK SOT edge has the bigger raw EV...
    assert by_stat["Shots On Target"]["best_ev"] > by_stat["Saves"]["best_ev"]
    # ...yet the PROVEN Saves edge ranks FIRST.
    assert edges[0]["stat"] == "Saves"
    # label distribution among reliable+ok edges
    assert board["calibration_labels"]["proven"] == 1
    assert board["calibration_labels"]["weak"] == 1


# ---- opponent adjustment (leak-free team_defense multiplier) -------------------

def _opp_line(match, team):
    return PropLine(
        sport="soccer_intl", event_id="o1", match=match,
        player="Luis Diaz", team=team, stat="Shots", line=2.5,
        over_price=None, under_price=None, payout_type="dfs_pickem",
        source="prizepicks")


def _capture_dist(monkeypatch, captured):
    """Patch prop_distribution to record the opp_mult kwarg it is called with."""
    def fake(df, player_id, stat_c, as_of, **kw):
        captured.append(kw.get("opp_mult"))
        return {"lam": 2.1, "model": "poisson", "p_over": lambda line: 0.6,
                "status": "ok", "per90": 3.0, "e_minutes": 90.0}
    monkeypatch.setattr(prop_edge.prop_engine, "prop_distribution", fake)


def test_opponent_mapped_passes_opp_mult(monkeypatch):
    # The OTHER team in match ("FRA") maps to team_abbr FRA; all_multipliers is
    # forced to a known map, so the Shots multiplier (1.5) must reach prop_distribution.
    monkeypatch.setattr(prop_edge.soccer_team_map, "_NAME_TO_ABBR", {}, raising=False)
    import domains.soccer.team_defense as td
    monkeypatch.setattr(td, "all_multipliers",
                        lambda df, opp, as_of: {"Shots": 1.5})
    captured = []
    _capture_dist(monkeypatch, captured)
    board = prop_edge.build_prop_board(
        "soccer_intl", as_of="2026-06-11", df=_df(),
        lines_source=[_opp_line("COL v FRA", "COL")])
    assert board["status"] == "ok"
    assert len(board["edges"]) == 1
    # both distribution passes (base + dispersion) saw the opponent multiplier 1.5
    assert 1.5 in captured
    assert board["edges"][0]["opp_mult"] == 1.5


def test_opponent_unmappable_falls_back_to_one(monkeypatch):
    # Opponent "Brazil" is not in the df team_abbr universe -> opp_mult stays 1.0.
    captured = []
    _capture_dist(monkeypatch, captured)
    board = prop_edge.build_prop_board(
        "soccer_intl", as_of="2026-06-11", df=_df(),
        lines_source=[_opp_line("Colombia vs Brazil", "Colombia")])
    assert board["status"] == "ok"
    # Colombia maps to COL (prefix) but it IS the player's own team; opponent Brazil
    # has no abbr in the df -> blind. Every distribution call used opp_mult 1.0.
    assert all((c is None or c == 1.0) for c in captured)
    if board["edges"]:
        assert board["edges"][0]["opp_mult"] == 1.0


def test_no_cache_all_unmeasured_prior_ranking(monkeypatch):
    # Cache absent -> everything "unmeasured"; ranking falls back to the prior
    # behavior (priced before pick'em), and nothing raises.
    _patch_dist(monkeypatch, p_over=0.62)
    board = prop_edge.build_prop_board(
        "soccer_intl", as_of="2026-06-11", df=_df(), lines_source=_lines(),
        calibration_path=os.path.join("nope", "absent.json"))
    assert board["status"] == "ok"
    for e in board["edges"]:
        assert e["calibration"] == "unmeasured"
        assert e["tier"] == "MODEL_VIEW"
    # prior ranking preserved: priced edge first, pick'em last
    assert board["edges"][0]["edge_basis"] == "ev_vs_priced"
    assert board["edges"][-1]["edge_basis"] == "model_view"


# ---- MLB sport-dispatch (Task D) -----------------------------------------------

def _mlb_df():
    """Canned MLB gamelog df: a batter + a pitcher, each with >= _MLB_RELIABLE_N
    prior exposures so the engine reaches them; the resolver matches on name+team."""
    import pandas as pd
    rows = []
    for date in ("2026-06-01", "2026-06-05"):
        rows.append({"game_pk": "g_%s_b" % date, "date": date, "team": "TB",
                     "player_id": "100", "player": "Yandy Diaz", "is_pitcher": False,
                     "batting_order": 3, "atBats": 20, "baseOnBalls": 5,
                     "hitByPitch": 0, "hits": 8, "totalBases": 12, "rbi": 4,
                     "runs": 5, "homeRuns": 1, "strikeOuts": 4, "stolenBases": 1})
        rows.append({"game_pk": "g_%s_p" % date, "date": date, "team": "NYM",
                     "player_id": "200", "player": "Kodai Senga", "is_pitcher": True,
                     "battersFaced": 25, "pitch_strikeOuts": 8, "earnedRuns": 2,
                     "hits_allowed": 4, "baseOnBalls_allowed": 2, "outs": 18})
    return pd.DataFrame(rows)


class _MLBProvider:
    def __init__(self, name, rows):
        self.name = name
        self._rows = rows

    def fetch_props(self, sport):
        assert sport == "mlb"
        return list(self._rows)


def _mlb_lines():
    hits = PropLine(
        sport="mlb", event_id="m1", match="TB vs NYM", player="Yandy Diaz",
        team="TB", stat="Hits", line=1.5, over_price=1.90, under_price=1.90,
        payout_type="sportsbook", source="underdog")  # two-way priced -> EV
    ks = PropLine(
        sport="mlb", event_id="m2", match="TB vs NYM", player="Kodai Senga",
        team="NYM", stat="Strikeouts", line=5.5, over_price=None,
        under_price=None, payout_type="dfs_pickem", source="prizepicks")
    nogo = PropLine(  # name not in df -> unresolved (never guessed)
        sport="mlb", event_id="m3", match="TB vs NYM", player="Nobody Here",
        team="TB", stat="Hits", line=0.5, payout_type="dfs_pickem",
        source="prizepicks")
    bad_stat = PropLine(  # canon stat outside MLB_CANON -> unresolved (stat_unsupported)
        sport="mlb", event_id="m4", match="TB vs NYM", player="Yandy Diaz",
        team="TB", stat="Fantasy Points", line=8.5, payout_type="dfs_pickem",
        source="prizepicks")
    return [hits, ks, nogo, bad_stat]


def _patch_mlb_engine(monkeypatch, p_over=0.6, n=80):
    """Stub the MLB engine's prop_distribution to a deterministic ok result so the
    test is network/data-shape independent (n drives reliability)."""
    import scripts.platformkit.prop_edge_mlb as pem
    real_cfg = prop_edge.prop_edge_config.get_config

    def fake(df, player_id, stat_c, as_of, **kw):
        # exposure must be None on the live board (engine PROJECTS it).
        assert kw.get("exposure") is None
        return {"lam": 2.0, "model": "poisson", "p_over": lambda line: p_over,
                "status": "ok", "exposure": 4.0, "n": n}

    def cfg_with_fake(sport):
        cfg = real_cfg(sport)
        if cfg is not None and sport == "mlb":
            cfg.engine_distribution = fake
        return cfg

    monkeypatch.setattr(prop_edge.prop_edge_config, "get_config", cfg_with_fake)
    return pem


def test_mlb_board_ranks_tiers_resolves(monkeypatch):
    _patch_mlb_engine(monkeypatch, p_over=0.6, n=80)
    providers = [_MLBProvider("underdog", [_mlb_lines()[0]]),
                 _MLBProvider("prizepicks", _mlb_lines()[1:])]
    board = prop_edge.build_prop_board("mlb", as_of="2026-06-18",
                                       providers=providers, df=_mlb_df())
    assert board["status"] == "ok"
    edges = board["edges"]
    # Hits (priced, resolves) + Strikeouts (pickem, resolves) -> 2 edges.
    assert len(edges) == 2
    # Nobody Here (no match) + Fantasy Points (unsupported stat) -> 2 unresolved.
    assert board["unresolved_count"] == 2
    reasons = {u["reason"] for u in board["unresolved"]}
    assert "stat_unsupported" in reasons

    by_stat = {e["stat"]: e for e in edges}
    hits = by_stat["Hits"]
    assert hits["edge_basis"] == "ev_vs_priced"
    assert isinstance(hits["best_ev"], float)
    assert hits["matched_name"] == "Yandy Diaz"  # resolver applied
    assert hits["reliable"] is True  # n=80 >= gate
    assert hits["side"] == "over"  # p_over 0.6 >= 0.5
    # Strikeouts canonicalizes (bare "Strikeouts" -> "Pitcher Strikeouts").
    ks = by_stat["Pitcher Strikeouts"]
    assert ks["edge_basis"] == "model_view"
    assert ks["best_ev"] is None
    assert abs(ks["model_gap"] - 0.1) < 1e-6  # |0.6 - 0.5|
    # No measured MLB calibration cache here -> all "unmeasured", tier MODEL_VIEW.
    for e in edges:
        assert e["calibration"] == "unmeasured"
        assert e["tier"] == "MODEL_VIEW"


def test_mlb_thin_prior_demoted_no_raise(monkeypatch):
    # n below the reliability gate -> ev_flag uncalibrated_thin, NOT reliable.
    _patch_mlb_engine(monkeypatch, p_over=0.7, n=3)
    board = prop_edge.build_prop_board(
        "mlb", as_of="2026-06-18", df=_mlb_df(),
        lines_source=[_mlb_lines()[0]])
    assert board["status"] == "ok"
    assert len(board["edges"]) == 1
    e = board["edges"][0]
    assert e["reliable"] is False
    assert e["ev_flag"] == "uncalibrated_thin"


def test_mlb_unmeasured_cache_degrades(monkeypatch):
    # Absent MLB calibration cache must degrade to "unmeasured" (never raise).
    _patch_mlb_engine(monkeypatch, p_over=0.6, n=80)
    board = prop_edge.build_prop_board(
        "mlb", as_of="2026-06-18", df=_mlb_df(),
        lines_source=[_mlb_lines()[0]],
        calibration_path=os.path.join("nope", "absent_mlb.json"))
    assert board["status"] == "ok"
    assert board["edges"][0]["calibration"] == "unmeasured"
