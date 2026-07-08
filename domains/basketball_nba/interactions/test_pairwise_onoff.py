"""Per-file test on the real 0022500003.json fixture (same clean game used
by lineups/test_on_off.py): builds stints + shots for one game, runs the
pairwise accumulator, and checks the sanity invariants -- symmetric
"min_together" for a pair regardless of direction, eFG values in the normal
[0, 1.5] eFG range, and a single 48-minute game can never clear the
200/100-minute floors (so the floor-filtered output is empty here by
construction, not a bug).

Run: python -m pytest domains/basketball_nba/interactions/test_pairwise_onoff.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from domains.basketball_nba.interactions.pairwise_onoff import _load_all_shots, compute_pairwise
from domains.basketball_nba.lineups.pbp_lineups import _BOX_SRC, _PBP_DIR, build_game_stints

_FIXTURE = _PBP_DIR / "0022500003.json"


@pytest.mark.skipif(not _FIXTURE.exists() or not _BOX_SRC.exists(), reason="local-only data not present")
def test_pairwise_structurally_sane_on_one_game() -> None:
    game_json = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    box_df = pd.read_parquet(_BOX_SRC)
    stints, notes = build_game_stints(game_json, box_df)
    assert notes == []
    stints_df = pd.DataFrame(stints)

    shots_df = _load_all_shots(stints_df, [game_json["game"]["gameId"]])
    result, n_pairs_total = compute_pairwise(stints_df, shots_df)

    assert n_pairs_total > 0
    # one 48-min game can never supply 200 min_together -- floor empties the output
    assert len(result) == 0

    # rebuild pre-floor to check value ranges (relax the module's own floor for this check)
    import domains.basketball_nba.interactions.pairwise_onoff as mod
    orig_together, orig_without = mod.MIN_TOGETHER_MINUTES, mod.MIN_X_WITHOUT_Y_MINUTES
    mod.MIN_TOGETHER_MINUTES, mod.MIN_X_WITHOUT_Y_MINUTES = 0.0, 0.0
    try:
        raw, _ = compute_pairwise(stints_df, shots_df)
    finally:
        mod.MIN_TOGETHER_MINUTES, mod.MIN_X_WITHOUT_Y_MINUTES = orig_together, orig_without

    assert len(raw) == n_pairs_total
    for col in ("x_efg_with_y_on", "x_efg_without_y"):
        vals = raw[col].dropna()
        assert (vals >= 0.0).all() and (vals <= 1.5).all()  # eFG = (fgm+0.5fg3m)/fga, max 1.5 on all-3s
    # min_together is symmetric in (X,Y) -- both directed rows must agree
    sym = raw.set_index(["team_id", "player_x", "player_y"])["min_together"]
    for (tid, x, y), v in sym.items():
        other = sym.get((tid, y, x))
        if other is not None:
            assert abs(v - other) < 1e-6
