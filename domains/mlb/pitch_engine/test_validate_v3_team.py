"""python -m pytest domains/mlb/pitch_engine/test_validate_v3_team.py -q

Fast: reuses validate_v3.compare_snapshot_v3 (already unit-tested) plus
bullpen_v3's team-tier fit/predict path on a tiny synthetic frame -- no
parquet load (the full walk-forward run is the CLI)."""
from __future__ import annotations

import numpy as np

from domains.mlb.pitch_engine.bullpen_v3 import PitcherQualityTier, TeamBullpenTier, RelieverPAv3
from domains.mlb.pitch_engine.validate_v3_team import _fit
from domains.mlb.pitch_engine.game_sim import GameStart
from domains.mlb.pitch_engine.validate_v3 import compare_snapshot_v3
from domains.mlb.pitch_engine.test_game_sim_v2 import _trans, _removal
from domains.mlb.pitch_engine.test_game_sim_v3 import _dists_v3
from domains.mlb.pitch_engine.test_bullpen_v3 import _team_relief_frame


def test_team_tier_matrix_feeds_the_same_compare_snapshot_v3():
    """The team-tier RelieverPAv3 matrix plugs into the SAME compare fn v3's
    gate uses -- confirms the candidate is wired through the identical harness,
    not a bespoke comparator."""
    pa = _team_relief_frame()
    pt = PitcherQualityTier.fit(pa)
    tt = TeamBullpenTier.fit(pa)
    rp = RelieverPAv3.fit(pa, pt, team_tiers=tt)
    m = rp.bucket_lead_matrix()
    tr = _trans(); rem = _removal(); sp, _ = _dists_v3()
    st = GameStart(inning=7, half=0, home_score=1, away_score=0)
    p1, p3 = compare_snapshot_v3(sp, sp, m, m, tr, rem, fh=3, fa=2, st=st, seed=5, n=300)
    assert 0.0 <= p1 <= 1.0 and 0.0 <= p3 <= 1.0


def test_fit_module_importable_and_exposes_run_pieces():
    """Smoke-check the gate module's private _fit signature stays wired to
    bullpen_v3's TeamBullpenTier without a parquet load (import-level only)."""
    assert callable(_fit)
