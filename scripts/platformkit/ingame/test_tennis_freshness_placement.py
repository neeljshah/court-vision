"""Per-file test: tennis ticker->player-id resolution + model-prob lookup (pure
functions, no real disk parquet -- mirrors test_freshness_model_placement.py's
own scope of testing the resolver/lookup logic, not the full placement run)."""
import datetime as dt

import pandas as pd

from scripts.platformkit.ingame import tennis_freshness_placement as tfp


def test_candidates_by_day_groups_by_tour_and_date():
    df = pd.DataFrame([
        {"tour": "atp", "date": dt.date(2026, 7, 1), "p1_name": "Felix Auger Aliassime",
         "p1_id": 1, "p2_name": "Dino Prizmic", "p2_id": 2},
        {"tour": "wta", "date": dt.date(2026, 7, 1), "p1_name": "Iga Swiatek",
         "p1_id": 3, "p2_name": "Aryna Sabalenka", "p2_id": 4},
    ])
    out = tfp._candidates_by_day(df)
    assert out[("atp", dt.date(2026, 7, 1))] == [("Felix Auger Aliassime", 1, "Dino Prizmic", 2)]
    assert out[("wta", dt.date(2026, 7, 1))] == [("Iga Swiatek", 3, "Aryna Sabalenka", 4)]


def test_match_tail_ids_unique_split():
    candidates = [("Felix Auger Aliassime", 1, "Dino Prizmic", 2)]
    # ticker tail "AUGPRI" -> AUG (Auger) + PRI (Prizmic)
    m = tfp.match_tail_ids(candidates, "AUGPRI")
    assert m == ("AUG", 1, "PRI", 2)


def test_match_tail_ids_ambiguous_returns_none():
    # two candidate matches both plausible for the same tail -> ambiguous
    candidates = [
        ("Felix Auger Aliassime", 1, "Dino Prizmic", 2),
        ("Someone Aug", 5, "Another Pri", 6),
    ]
    m = tfp.match_tail_ids(candidates, "AUGPRI")
    assert m is None


def test_resolve_model_prob_ref_side_and_date_grace():
    candidates_by_day = {("atp", dt.date(2026, 7, 1)): [("Felix Auger Aliassime", 1, "Dino Prizmic", 2)]}
    elo_luts = {"atp": {(dt.date(2026, 7, 1), frozenset({1, 2})): {1: 0.7, 2: 0.3}}}
    # ticker date off by one day -- resolver tries +/-1 day grace
    p = tfp._resolve_model_prob("KXATPMATCH-26JUN30AUGPRI", candidates_by_day, elo_luts)
    # ref = alphabetically-first of {AUG,PRI} = AUG = player 1 -> prob 0.7
    assert abs(p - 0.7) < 1e-9


def test_resolve_model_prob_none_when_unresolved():
    assert tfp._resolve_model_prob("KXATPMATCH-26JUL01AUGPRI", {}, {}) is None
    assert tfp._resolve_model_prob("KXMLBGAME-26APR261920LAAKC", {}, {}) is None
