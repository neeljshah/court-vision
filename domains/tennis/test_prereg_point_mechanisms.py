"""Per-file test for domains.tennis.prereg_point_mechanisms.

Covers: break-point identification from a hand-built score-state toy (the
CAREFUL check named in the brief), H1's verdict rules (_corpus_row /
_replication_row), and the as-of leak guard for H2 profiles (date-batched
snapshot-then-update never lets a same-day match see a sibling's outcome).

Run: python -m pytest domains/tennis/test_prereg_point_mechanisms.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.tennis.prereg_point_mechanisms import (
    ALPHA, FAILED_REPLICATION, NOT_TESTABLE, NULL, REPLICATED, SURVIVES,
    _break_point, _corpus_row, _replication_row, asof_walkforward, h1_fit,
)


def test_break_point_toy_cases():
    server_sc = pd.Series(["30", "40", "AD", "40", "0"])
    ret_sc = pd.Series(["40", "40", "40", "AD", "15"])
    got = _break_point(server_sc, ret_sc).tolist()
    # server down 30-40 -> BP; 40-40 deuce -> not; server's OWN ad -> not (his
    # game point, not the returner's); returner's AD -> BP; 0-15 -> not.
    assert got == [True, False, False, True, False]


def test_h1_fit_recovers_known_delta():
    # 2 (match, server) units, each with a clean bp-vs-nonbp win-rate gap.
    rows = []
    for match_id, server in (("m1", 1), ("m2", 1), ("m3", 2)):
        for _ in range(5):  # 5 BP points, server loses all (win rate 0)
            rows.append({"match_id": match_id, "server": server, "server_won": 0, "break_point": True})
        for _ in range(20):  # 20 non-BP points, server wins 80%
            rows.append({"match_id": match_id, "server": server, "server_won": 1 if _ < 16 else 0,
                        "break_point": False})
    frame = pd.DataFrame(rows)
    fit = h1_fit(frame)
    assert fit["n"] == 3
    # bp_win=0.0, non_bp_win=0.8 -> delta=-0.8 for every unit, exactly
    assert abs(fit["effect"] - (-0.8)) < 1e-9
    assert fit["p"] < ALPHA


def test_h1_fit_floors_out_thin_units():
    # only 1 BP point (below MIN_BP=3) -- unit must be dropped, n=0
    frame = pd.DataFrame([
        {"match_id": "m1", "server": 1, "server_won": 0, "break_point": True},
        *[{"match_id": "m1", "server": 1, "server_won": 1, "break_point": False} for _ in range(15)],
    ])
    fit = h1_fit(frame)
    assert fit == {"n": 0, "effect": None, "p": None, "term": "delta_bp_minus_nonbp"}


def test_corpus_row_verdicts():
    assert _corpus_row("h", "c", "point", {"n": 0, "effect": None, "p": None, "term": "t"})["verdict"] == NOT_TESTABLE
    assert _corpus_row("h", "c", "point", {"n": 10, "effect": 0.1, "p": 0.001, "term": "t"})["verdict"] == SURVIVES
    assert _corpus_row("h", "c", "point", {"n": 10, "effect": 0.1, "p": 0.5, "term": "t"})["verdict"] == NULL


def test_replication_row_verdicts():
    sig_pos = {"n": 10, "effect": 0.1, "p": 0.001, "term": "t"}
    sig_pos2 = {"n": 10, "effect": 0.2, "p": 0.001, "term": "t"}
    sig_neg = {"n": 10, "effect": -0.1, "p": 0.001, "term": "t"}
    not_sig = {"n": 10, "effect": 0.1, "p": 0.5, "term": "t"}
    zero = {"n": 0, "effect": None, "p": None, "term": "t"}

    assert _replication_row("h", "point", sig_pos, sig_pos2)["verdict"] == REPLICATED
    assert _replication_row("h", "point", sig_pos, sig_neg)["verdict"] == FAILED_REPLICATION  # opposite sign
    assert _replication_row("h", "point", sig_pos, not_sig)["verdict"] == FAILED_REPLICATION  # not both sig
    assert _replication_row("h", "point", sig_pos, zero)["verdict"] == NOT_TESTABLE  # n=0 never a fail


def test_asof_walkforward_no_same_date_leak():
    """2 matches on the SAME date both involving player X: neither may see the
    other's outcome (must both snapshot n_prior=0). A 3rd match on a LATER
    date must see BOTH same-day matches' combined contribution."""
    d1, d2 = np.datetime64("2020-01-01"), np.datetime64("2020-01-02")
    match_lvl = pd.DataFrame([
        {"match_id": "A", "player_id": "X", "serve_won": 8, "serve_n": 10, "return_won": 0, "return_n": 0, "date": d1},
        {"match_id": "A", "player_id": "Y", "serve_won": 0, "serve_n": 0, "return_won": 2, "return_n": 10, "date": d1},
        {"match_id": "B", "player_id": "X", "serve_won": 2, "serve_n": 10, "return_won": 8, "return_n": 10, "date": d1},
        {"match_id": "C", "player_id": "X", "serve_won": 0, "serve_n": 0, "return_won": 0, "return_n": 0, "date": d2},
    ])
    snap = asof_walkforward(match_lvl).set_index(["match_id", "player_id"])

    # both same-day matches see X with zero prior history -- neither leaks into the other
    assert snap.loc[("A", "X"), "serve_n_prior"] == 0
    assert snap.loc[("B", "X"), "serve_n_prior"] == 0
    assert np.isnan(snap.loc[("A", "X"), "serve_str"])
    assert np.isnan(snap.loc[("B", "X"), "serve_str"])

    # the next day's match sees BOTH d1 matches combined (10+10=20 serve points, 8+2=10 won)
    assert snap.loc[("C", "X"), "serve_n_prior"] == 20
    assert abs(snap.loc[("C", "X"), "serve_str"] - 0.5) < 1e-9
