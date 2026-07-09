"""Per-file tests for pitch_engine.game_sim -- transition + MC determinism."""
import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.game_sim import (
    BaseOutTransition, simulate_game, GameStart, INNING_OVER)
from domains.mlb.pitch_engine.corpus import PA_EVENTS


def _pa_frame_for_trans():
    # 40 distinct clean 3-out half-innings: PA at base_out_state 0->1->2, the last
    # (2 outs) OUT ends the inning (shift(-1) NaN -> INNING_OVER).
    rows = []
    for i in range(40):
        for ab, bos in [(1, 0), (2, 1), (3, 2)]:
            rows.append(dict(game_pk=1, inning=i + 1, inning_topbot="Top",
                             at_bat_number=ab, pa_evt="OUT", runs=0,
                             base_mask=0, outs_start=bos % 3, base_out_state=bos))
    return pd.DataFrame(rows)


def test_transition_absorbs_third_out():
    tr = BaseOutTransition.fit(_pa_frame_for_trans(), min_cell=5)
    # from base_out_state=2 (empty, 2 outs) an OUT ends the inning
    key = np.array([2 * 8 + PA_EVENTS.index("OUT")])
    evt = np.array([PA_EVENTS.index("OUT")])
    runs, nxt = tr.sample(key, evt, np.random.default_rng(0))
    assert nxt[0] == INNING_OVER
    assert runs[0] == 0


def test_simulate_game_determinism_and_shape():
    tr = BaseOutTransition.fit(_pa_frame_for_trans(), min_cell=5)
    # every batter always makes an out -> both teams score 0, game ends fast
    pa = np.zeros((9, 8)); pa[:, PA_EVENTS.index("OUT")] = 1.0
    h1, a1 = simulate_game(pa, pa, tr, n=200, seed=7)
    h2, a2 = simulate_game(pa, pa, tr, n=200, seed=7)
    assert np.array_equal(h1, h2) and np.array_equal(a1, a2)   # deterministic
    assert (a1 == 0).all()                                     # away never scores
    assert (h1 >= 0).all() and len(h1) == 200                  # finite, terminates
    # different seed still valid shape
    h3, _ = simulate_game(pa, pa, tr, n=50, seed=8)
    assert len(h3) == 50


def test_home_leads_after_top9_ends_game():
    tr = BaseOutTransition.fit(_pa_frame_for_trans(), min_cell=5)
    pa = np.zeros((9, 8)); pa[:, PA_EVENTS.index("OUT")] = 1.0
    # start bottom of 9 with home already ahead -> game already decided on next check
    start = GameStart(inning=9, half=0, home_score=5, away_score=0)
    h, a = simulate_game(pa, pa, tr, n=20, seed=1, start=start)
    assert (h == 5).all() and (a == 0).all()
