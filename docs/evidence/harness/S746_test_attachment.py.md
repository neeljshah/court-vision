"""S746 PROPOSED construct cases: training floor for the fitted arms B, C and D.

Written to FAIL on trunk (no floor, no warmup_reason) and PASS with the S746 diff
applied. Construct rows only; no archive, no network, no sealed file read.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
import importlib

import pytest

DAY = '2026-10-03'
STATE = 'score_diff={d} inning=5 half=top outs=1 base=0'


def _eligibility():
    return importlib.import_module('scripts.platformkit.ingame.baseline_four_arm_eligibility')


def _scoreboard():
    return importlib.import_module('scripts.platformkit.execution.ingame_scoreboard')


def _floor():
    floor = getattr(_scoreboard(), 'TRAIN_FLOOR_GAMES', None)
    assert isinstance(floor, int) and floor >= 2, 'S746: TRAIN_FLOOR_GAMES must be declared (int >= 2)'
    return floor


def history(outcomes, start=datetime(2026, 9, 1, 18, tzinfo=timezone.utc)):
    """One settled MLB history game per outcome, two ticks each, all before the embargo."""
    rows = []
    for g, y in enumerate(outcomes):
        begin = start + timedelta(hours=6 * g)
        for k in range(2):
            rows.append(dict(game_id=f'h{g}', sport='mlb', outcome=y,
                             ts=(begin + timedelta(minutes=k)).isoformat(),
                             close_ts=(begin + timedelta(hours=3)).isoformat(),
                             market_prob=str(0.35 + 0.01 * (g % 30) + 0.02 * k),
                             state_summary=STATE.format(d=(g % 3) - 1)))
    return rows


def direct(outcomes, **extra):
    """History rows as predict_rows reads them (float probabilities)."""
    return [dict(r, market_prob=float(r['market_prob']), **extra) for r in history(outcomes)]


def ticks(n=3):
    """Home-oriented live MLB ticks on the scored night (S431 native shape)."""
    out = []
    for i in range(n):
        ts = f'{DAY}T20:{10 + i:02d}:00Z'
        state = dict(status='live', home_abbr='NYY', away_abbr='BOS', response_end_utc=ts,
                     state=dict(inning=5, half='Top', outs=1, base_state=0, score_home=1, score_away=0))
        out.append(dict(game_key='g-night', ts=ts, mid=0.55, state=state, home_oriented=True))
    return out


@pytest.mark.parametrize('train, floor, reason', [
    ([], None, 'no_history'), ([], 20, 'no_history'),
    ([dict(game_id='a', outcome=1)], None, None),
    ([dict(game_id='a', outcome=1)] * 3, 2, 'below_game_floor'),
    ([dict(game_id='a', outcome=1)], 1, 'one_outcome'),
    ([dict(game_id=str(i), outcome=1) for i in range(5)], 5, 'one_outcome'),
    ([dict(game_id=str(i), outcome=0) for i in range(5)], 5, 'one_outcome'),
    ([dict(game_id=str(i), outcome=i % 2) for i in range(4)], 5, 'below_game_floor'),
    ([dict(game_id=str(i), outcome=i % 2) for i in range(5)], 5, None),
    ([dict(game_id=str(i), outcome=int(i == 0)) for i in range(5)], 5, None),
])
def test_case1_warmup_reason_table(train, floor, reason):
    assert _eligibility().warmup_reason(train, floor) == reason


def test_case2_s744_night_one_game_one_outcome_is_warmup():
    """S744: one history game with outcome 1 gave B = C = 0.99475 on every tick; now warmup."""
    counts = Counter()
    out = _scoreboard()._models(ticks(), history([1]), 'mlb', DAY, counts, True)
    assert out == {}
    assert counts['model_warmup:below_game_floor'] == 3
    assert sum(v for k, v in counts.items() if k.startswith('model_warmup:')) == 3


def test_case3_below_floor_with_both_outcomes_is_warmup():
    floor = _floor()
    counts = Counter()
    out = _scoreboard()._models(ticks(), history([g % 2 for g in range(floor - 1)]), 'mlb', DAY, counts, True)
    assert out == {} and counts['model_warmup:below_game_floor'] == 3


def test_case4_at_floor_one_outcome_is_warmup():
    floor = _floor()
    counts = Counter()
    out = _scoreboard()._models(ticks(), history([1] * floor), 'mlb', DAY, counts, True)
    assert out == {} and counts['model_warmup:one_outcome'] == 3


def test_case5_at_floor_both_outcomes_fits_b_and_c():
    floor = _floor()
    counts = Counter()
    out = _scoreboard()._models(ticks(), history([g % 2 for g in range(floor)]), 'mlb', DAY, counts, True)
    assert len(out) == 3
    assert not any(k.startswith('model_warmup:') for k in counts)
    for r in out.values():
        assert not r['warmup'] and r['train_n_games'] == floor
        assert all(0 < r[a] < 1 for a in 'BC') and (r['B'], r['C']) != (r['A'], r['A'])


def test_case6_predict_rows_floor_none_keeps_pre_s746_rule():
    """Power: floor None reproduces the S744 one-outcome fit (B near 1, not warmup)."""
    scorer = importlib.import_module('scripts.platformkit.ingame.baseline_four_arm')
    test = [dict(game_id='g-night', ts=f'{DAY}T20:10:00+00:00', close_ts='2026-10-05T00:00:00+00:00',
                 outcome=0, market_prob=0.55, state_summary=STATE.format(d=1))]
    rows = direct([1]) + test
    old = [r for r in scorer.predict_rows(rows, 'mlb', model_optional=True, floor=None) if r['game_id'] == 'g-night']
    new = [r for r in scorer.predict_rows(rows, 'mlb', model_optional=True, floor=2) if r['game_id'] == 'g-night']
    assert not old[0]['warmup'] and old[0]['B'] > 0.99 and old[0]['C'] > 0.99
    assert new[0]['warmup'] and new[0]['B'] == new[0]['C'] == new[0]['A'] == 0.55
    assert [r for r in scorer.predict_rows(rows, 'mlb', model_optional=True) if r['game_id'] == 'g-night'] == old


def test_case7_paired_d_follows_the_floor():
    """D's own training subset obeys the same floor (non-optional sport: every row has a model)."""
    scorer = importlib.import_module('scripts.platformkit.ingame.baseline_four_arm')
    hist = direct([1, 0, 1], model_prob=0.5)
    test = [dict(game_id='g-night', ts=f'{DAY}T20:10:00+00:00', close_ts='2026-10-05T00:00:00+00:00',
                 outcome=0, market_prob=0.55, model_prob=0.5, state_summary=STATE.format(d=1))]
    low = [r for r in scorer.predict_rows(hist + test, 'mlb', floor=4) if r['game_id'] == 'g-night'][0]
    ok = [r for r in scorer.predict_rows(hist + test, 'mlb', floor=3) if r['game_id'] == 'g-night'][0]
    assert low['warmup'] and low['D'] == low['A'] == 0.55
    assert not ok['warmup'] and ok['D'] != ok['A']
