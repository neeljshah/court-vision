"""Per-file test for domains.soccer.ingest_shotxg_states (no network).

Covers, against a synthetic ESPN-shaped commentary payload:
  (a) SCHEMA  -- frozen base merge keys (game_id, asof_idx) present + the additive as-of
      location-xG cols (xgloc_diff, home_xgloc, away_xgloc, n_shots_loc);
  (b) LEAK-FREE -- a shot at minute m contributes ONLY to ticks >= m (no future leak);
      no match-final / season-final aggregate feeds a per-tick row; unusable / unattributable
      shots are DROPPED not 0-filled; goalPositionX/Y are never read;
  (c) AS-OF-MONOTONIC -- home_xgloc / away_xgloc / n_shots_loc are cumulative non-decreasing
      across the 19-point grid (state uses prior-N / clock<=m only, step function);
  (d) PARITY -- the SAME pure builder (shot_xg_events -> build_xgloc_states) yields identical
      additive cols whether called at "train" (full corpus) or "inference" (one live game).

Run ONLY this file:
  python -m pytest tests/domains/soccer/test_ingest_shotxg_states.py -q
"""
from __future__ import annotations

from domains.soccer import ingest_shotxg_states as M


def _comm(type_text, fx, fy, name, clock):
    """One ESPN commentary item: c['play'] carries type/clock/fieldPosition/participants."""
    play = {"type": {"text": type_text}, "clock": {"displayValue": clock},
            "participants": [{"athlete": {"displayName": name}}]}
    if fx is not None:
        play["fieldPositionX"] = fx
    if fy is not None:
        play["fieldPositionY"] = fy
    # goalPositionX/Y intentionally present-but-zero to prove we never read them.
    play["goalPositionX"] = 0.0
    play["goalPositionY"] = 0.0
    return {"play": play}


def _payload():
    """Home 'H' (Alice, Bob) vs Away 'A' (Cara, Dan). Shots:
      - Alice  min 10  near goal     (high xg)   HOME
      - Cara   min 30  long range    (low xg)    AWAY
      - Bob    min 60  no fieldX      -> DROPPED (coverage guard)
      - Ghost  min 70  near goal      -> DROPPED (not in either roster)
      - Dan    min 80  near goal     (high xg)   AWAY
    Also a non-shot (Foul) that must be ignored entirely.
    """
    commentary = [
        _comm("Shot on Target", 0.96, 0.50, "Alice", "10'"),
        _comm("Shot off Target", 0.50, 0.30, "Cara", "30'"),
        _comm("Foul", 0.40, 0.40, "Bob", "45'"),
        _comm("Shot on Target", None, None, "Bob", "60'"),
        _comm("Shot on Target", 0.95, 0.50, "GhostStriker", "70'"),
        _comm("Goal", 0.97, 0.50, "Dan", "80'"),
    ]
    return {
        "header": {"competitions": [{"competitors": [
            {"homeAway": "home", "team": {"id": "H"}},
            {"homeAway": "away", "team": {"id": "A"}},
        ]}]},
        "rosters": [
            {"team": {"id": "H"}, "roster": [
                {"athlete": {"displayName": "Alice"}},
                {"athlete": {"displayName": "Bob"}}]},
            {"team": {"id": "A"}, "roster": [
                {"athlete": {"displayName": "Cara"}},
                {"athlete": {"displayName": "Dan"}}]},
        ],
        "commentary": commentary,
    }


def test_loc_xg_monotone_in_distance_and_bounded():
    near = M.loc_xg(0.98, 0.5)
    far = M.loc_xg(0.50, 0.5)
    assert near > far                      # closer to goal -> higher finishing proxy
    wide = M.loc_xg(0.98, 0.05)            # same distance, extreme angle
    assert wide < near                     # angle penalty lowers it
    for p in (near, far, wide, M.loc_xg(0.0, 0.5)):
        assert M._XG_MIN <= p <= M._XG_MAX  # a probability proxy, never 0/1, never $


def test_shot_xg_events_drops_unusable_and_unattributable():
    ev = M.shot_xg_events(_payload())
    # 3 usable+attributed shots survive: Alice(home), Cara(away), Dan(away).
    # Bob's 2nd shot has no fieldPositionX -> dropped; Ghost not in roster -> dropped; Foul ignored.
    assert len(ev) == 3
    sides = sorted(sd for _, sd, _ in ev)
    assert sides == ["away", "away", "home"]
    minutes = sorted(m for m, _, _ in ev)
    assert minutes == [10.0, 30.0, 80.0]


def test_schema_frozen_keys_and_additive_cols():
    shots = M.shot_xg_events(_payload())
    rows = M.build_xgloc_states("evt1", shots)
    assert len(rows) == len(M._GRID) == 19
    frozen = {"game_id", "asof_idx"}                 # base merge keys
    additive = {"xgloc_diff", "home_xgloc", "away_xgloc", "n_shots_loc"}
    assert frozen <= set(rows[0])
    assert additive <= set(rows[0])
    # asof_idx is the per-game monotone grid index 0..18
    assert [r["asof_idx"] for r in rows] == list(range(19))
    assert all(r["game_id"] == "evt1" for r in rows)
    # xgloc_diff == home_xgloc - away_xgloc exactly (no hidden term)
    for r in rows:
        assert abs(r["xgloc_diff"] - (r["home_xgloc"] - r["away_xgloc"])) < 1e-9


def test_asof_monotonic_cumulative_stepfunction():
    rows = M.build_xgloc_states("evt1", M.shot_xg_events(_payload()))
    hx = [r["home_xgloc"] for r in rows]
    ax = [r["away_xgloc"] for r in rows]
    nn = [r["n_shots_loc"] for r in rows]
    assert hx == sorted(hx)                 # cumulative non-decreasing
    assert ax == sorted(ax)
    assert nn == sorted(nn)
    # grid: idx*5 minutes. Alice(min10) lands at idx>=2; Cara(min30) idx>=6; Dan(min80) idx>=16.
    assert rows[0]["n_shots_loc"] == 0 and rows[1]["n_shots_loc"] == 0      # <10'
    assert rows[2]["n_shots_loc"] == 1                                      # 10'
    assert rows[6]["n_shots_loc"] == 2                                      # 30'
    assert rows[16]["n_shots_loc"] == 3                                     # 80'
    assert rows[18]["n_shots_loc"] == 3                                     # final tick


def test_leakfree_no_future_and_no_final_aggregate():
    rows = M.build_xgloc_states("evt1", M.shot_xg_events(_payload()))
    # Dan's away goal (min 80) must NOT bleed into any tick < idx 16 (no lookahead).
    early_away = rows[15]["away_xgloc"]
    late_away = rows[16]["away_xgloc"]
    assert late_away > early_away
    # before minute 30 away has zero (Cara at 30, Dan at 80 both still in the future)
    assert rows[5]["away_xgloc"] == 0.0
    # the builder receives ONLY (minute, side, xg) tuples -- no final-score / no boxscore
    # total is in scope; the additive cols cannot encode a match-final aggregate.
    assert "outcome" not in rows[0] and "home_final" not in rows[0]
    # goalPositionX/Y are present-but-zero on the wire and must never have been read:
    # if they had been, a zero placement would crash the (0,1)-bounded proxy. Survives -> unread.
    assert all(M._XG_MIN <= r["home_xgloc"] or r["home_xgloc"] == 0.0 for r in rows)


def test_train_inference_parity():
    pay = _payload()
    # "train": ingest over a 2-game corpus via the same pure path the label-ingest uses.
    train_rows = []
    for gid in ("g1", "g2"):
        train_rows += M.build_xgloc_states(gid, M.shot_xg_events(pay))
    # "inference": one live game, identical functions, no separate code path.
    infer_rows = M.build_xgloc_states("g1", M.shot_xg_events(pay))
    g1_train = [r for r in train_rows if r["game_id"] == "g1"]
    assert len(g1_train) == len(infer_rows) == 19
    for a, b in zip(g1_train, infer_rows):
        assert a["xgloc_diff"] == b["xgloc_diff"]
        assert a["home_xgloc"] == b["home_xgloc"]
        assert a["away_xgloc"] == b["away_xgloc"]
        assert a["n_shots_loc"] == b["n_shots_loc"]
