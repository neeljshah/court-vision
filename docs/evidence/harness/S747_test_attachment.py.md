"""S747 PROPOSED construct cases: MLB Middle / End with outs 3 encoded as the adjacent half.

Written to FAIL on trunk (tick_row refuses outs above 2; the parser accepts only top or
bottom) and PASS with the S747 diff applied. Construct rows shaped like the S744 night
(235 Middle, 201 End, 3 transition ticks, all outs 3); no archive, no sealed file read.
"""
from collections import Counter
from decimal import Decimal as D

import pytest

from scripts.platformkit.execution.ingame_scoreboard_rules import segment, tick_row
from scripts.platformkit.ingame.baseline_four_arm_features import parse_state

CLOSE = '2026-10-05T00:00:00Z'


def tick(inning, half, outs, i=0, base=0, home=2, away=1):
    ts = f'2026-10-03T{18 + i // 3600:02d}:{(i // 60) % 60:02d}:{i % 60:02d}Z'
    state = dict(status='live', home_abbr='NYY', away_abbr='BOS', response_end_utc=ts,
                 state=dict(inning=inning, half=half, outs=outs, base_state=base,
                            score_home=home, score_away=away))
    return dict(game_key='g', ts=ts, mid=0.5, state=state, home_oriented=True)


def summary(t):
    counts = Counter()
    row = tick_row(t, 'mlb', CLOSE, 0, counts)
    return (None if row is None else row['state_summary']), counts


def fraction(sport_row):
    """The sealed segment() boundary position of a state (Middle / End mapped as sealed)."""
    s = sport_row['state']
    from scripts.platformkit.execution.ingame_scoreboard_rules import _HALF
    return (D(s['inning'] - 1) + _HALF[s['half'].lower()]) / 9


@pytest.mark.parametrize('inning, half, want', [
    (5, 'Middle', 'score_diff=1 inning=5 half=bottom outs=0 base=0'),
    (5, 'End', 'score_diff=1 inning=6 half=top outs=0 base=0'),
    (1, 'Middle', 'score_diff=1 inning=1 half=bottom outs=0 base=0'),
    (9, 'End', 'score_diff=1 inning=10 half=top outs=0 base=0'),
    (12, 'middle', 'score_diff=1 inning=12 half=bottom outs=0 base=0'),
    (7, 'END', 'score_diff=1 inning=8 half=top outs=0 base=0'),
])
def test_case1_tick_row_maps_adjacent_half(inning, half, want):
    text, counts = summary(tick(inning, half, 3))
    assert text == want and counts['model_state_refused'] == 0


@pytest.mark.parametrize('inning, half, outs', [
    (5, 'Top', 3), (5, 'Bottom', 3), (5, 'Middle', 4), (5, 'End', '3'), (5, 'Middle', True),
    (5, 'Inning', 3), (31, 'Middle', 3), (0, 'End', 3),
])
def test_case2_other_outs3_states_stay_refused(inning, half, outs):
    text, counts = summary(tick(inning, half, outs))
    assert text is None and counts['model_state_refused'] == 1


def test_case3_middle_end_below_three_outs_unchanged():
    """Middle / End with outs 0-2 keep today's encoding (half carried; the parser refuses it)."""
    for half in ('Middle', 'End'):
        text, _ = summary(tick(5, half, 2))
        assert text == f'score_diff=1 inning=5 half={half.lower()} outs=2 base=0'
        with pytest.raises(ValueError, match='missing_state:half'):
            parse_state(text, 'mlb')


def test_case4_mapped_row_parses_as_the_adjacent_half_and_matches_segment():
    for inning, half, adj_inning, adj_half in ((5, 'Middle', 5, 'Bottom'), (5, 'End', 6, 'Top')):
        mapped, _ = summary(tick(inning, half, 3))
        explicit, _ = summary(tick(adj_inning, adj_half, 0))
        assert parse_state(mapped, 'mlb') == parse_state(explicit, 'mlb')
        original, adjacent = tick(inning, half, 3)['state'], tick(adj_inning, adj_half, 0)['state']
        assert fraction(original) == fraction(adjacent)
        assert segment('mlb', original) == segment('mlb', adjacent)


@pytest.mark.parametrize('text, want', [
    ('score_diff=1 inning=5 half=middle outs=3 base=0', 'score_diff=1 inning=5 half=bottom outs=0 base=0'),
    ('score_diff=1 inning=5 half=end outs=3 base=0', 'score_diff=1 inning=6 half=top outs=0 base=0'),
    ('score_diff=-2 inning=9 half=End outs=3 base=0', 'score_diff=-2 inning=10 half=top outs=0 base=0'),
])
def test_case5_parser_maps_middle_end_outs3(text, want):
    assert parse_state(text, 'mlb') == parse_state(want, 'mlb')


@pytest.mark.parametrize('text', [
    'score_diff=1 inning=5 half=top outs=3 base=0',
    'score_diff=1 inning=5 half=bottom outs=3 base=0',
    'score_diff=1 inning=5 half=middle outs=2 base=0',
    'score_diff=1 inning=x half=end outs=3 base=0',
    'score_diff=1 inning=5 half=end outs=3.0 base=0',
])
def test_case6_parser_still_refuses(text):
    with pytest.raises(ValueError):
        parse_state(text, 'mlb')


def test_case7_s744_night_shape_counts():
    """235 Middle + 201 End + 3 transition ticks (S744 counts); 436 encoded, 3 refused."""
    rows = [tick(1 + i % 9, 'Middle', 3, i) for i in range(235)]
    rows += [tick(1 + i % 9, 'End', 3, 235 + i) for i in range(201)]
    rows += [tick(9, 'Top', 3, 436), tick(9, 'Bottom', 3, 437), tick(8, 'Top', 3, 438)]
    counts = Counter()
    encoded = [tick_row(t, 'mlb', CLOSE, 0, counts) for t in rows]
    kept = [r for r in encoded if r is not None]
    assert len(rows) == 439 and len(kept) == 436 and counts['model_state_refused'] == 3
    assert all(parse_state(r['state_summary'], 'mlb')['outs'] == 0 for r in kept)
    halves = Counter(parse_state(r['state_summary'], 'mlb')['half'] for r in kept)
    assert halves == {1.0: 235, 0.0: 201}
