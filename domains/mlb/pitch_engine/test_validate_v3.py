"""python -m pytest domains/mlb/pitch_engine/test_validate_v3.py -q

Fast: drives compare_snapshot_v3 on a synthetic transition/removal, no parquet
load (the full walk-forward run is the CLI)."""
from __future__ import annotations

import numpy as np

from domains.mlb.pitch_engine.game_sim import GameStart
from domains.mlb.pitch_engine.validate_v3 import compare_snapshot_v3
from domains.mlb.pitch_engine.validate_v2 import _pit_stat
from domains.mlb.pitch_engine.test_game_sim_v2 import _trans, _removal
from domains.mlb.pitch_engine.test_game_sim_v3 import _dists_v3
from domains.mlb.pitch_engine import bullpen as bp


def test_compare_snapshot_v3_returns_two_pits():
    tr = _trans(); rem = _removal(); sp, rp = _dists_v3()
    st = GameStart(inning=7, half=0, home_score=1, away_score=0)
    p1, p3 = compare_snapshot_v3(sp, sp, rp, rp, tr, rem, fh=3, fa=2, st=st, seed=5, n=300)
    assert 0.0 <= p1 <= 1.0 and 0.0 <= p3 <= 1.0


def test_reliever_suppression_shifts_pit_v3():
    """All-out reliever dist suppresses away scoring at an inn7 snapshot, so v3's
    home-margin sim >= v1's -> its realized-margin PIT differs from v1's."""
    tr = _trans(); rem = _removal(); sp, _ = _dists_v3()
    rp_out = np.zeros((bp.N_BUCKET, bp.N_LEAD, 8)); rp_out[:, :, 0] = 1.0
    st = GameStart(inning=7, half=0, home_score=1, away_score=0)
    p1, p3 = compare_snapshot_v3(sp, sp, rp_out, rp_out, tr, rem, fh=1, fa=0, st=st,
                                 seed=5, n=400)
    assert p3 != p1


def test_pit_stat_reused_from_v2():
    s = _pit_stat(list(np.linspace(0, 1, 200)))
    assert s["n"] == 200
    assert s["uniformity_dev"] < 0.1
