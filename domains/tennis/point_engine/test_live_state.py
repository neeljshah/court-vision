import pandas as pd

from domains.tennis.point_engine.corpus import score_bucket, set_bucket
from domains.tennis.point_engine.match_sim import DEUCE_BUCKET
from domains.tennis.point_engine.point_model import PointModel
from domains.tennis.point_engine.live_state import (
    LiveState, live_point_prob, live_state_from_match, live_states_from_feed,
    to_point_frame_row,
)


def _match(server=1, points=("30", "40"), sets=(0, 1), games=((4, 3), (6, 4)),
           status="live", event_status=None, is_tiebreak=False, mid="m1"):
    return {
        "id": mid,
        "players": {"p1": {"name": "Alice"}, "p2": {"name": "Bob"}},
        "status": status, "event_status": event_status,
        "score": {"sets": list(sets), "games": [list(games[0]), list(games[1])],
                  "points": list(points), "server": server,
                  "is_tiebreak": is_tiebreak},
    }


def test_server_maps_to_p1_and_score_bucket_matches_corpus():
    st = live_state_from_match(_match(server=1, points=("30", "15")))
    assert st.server_id == "Alice" and st.returner_id == "Bob"
    assert st.server_pts == 2 and st.returner_pts == 1
    assert st.score_bucket == score_bucket(2, 1)   # same collapse as the fit path
    assert st.is_live is True and st.terminal_reason is None


def test_server_two_swaps_server_and_returner_points():
    # points is always [p1_point, p2_point]; server 2 -> p2 serves
    st = live_state_from_match(_match(server=2, points=("15", "40")))
    assert st.server_id == "Bob" and st.returner_id == "Alice"
    assert st.server_pts == 3 and st.returner_pts == 1
    assert st.score_bucket == score_bucket(3, 1)


def test_set_bucket_from_games_length():
    # two per-set entries -> second set in progress -> set_no 2 -> bucket 1
    st = live_state_from_match(_match(games=((4, 3), (6, 4))))
    assert st.set_no == 2 and st.set_bucket == set_bucket(2) == 1


def test_break_point_true_receiver_at_40_vs_30():
    # server Alice at 30, receiver Bob at 40 -> receiver one point from breaking
    st = live_state_from_match(_match(server=1, points=("30", "40")))
    assert st.break_point is True


def test_break_point_true_receiver_ad():
    st = live_state_from_match(_match(server=1, points=("AD", None)))  # p2 (receiver) AD? no
    # construct AD to the receiver explicitly: server=1 -> receiver is p2
    st = live_state_from_match(_match(server=1, points=("40", "AD")))
    assert st.returner_pts == 4 and st.break_point is True


def test_deuce_is_not_a_break_point():
    st = live_state_from_match(_match(server=1, points=("40", "40")))
    assert st.score_bucket == 16 and st.break_point is False


def test_server_ahead_is_not_a_break_point():
    st = live_state_from_match(_match(server=1, points=("40", "15")))
    assert st.break_point is False


def test_tiebreak_routes_to_deuce_proxy_and_undef_break_point():
    st = live_state_from_match(_match(is_tiebreak=True, points=("6", "5")))
    assert st.is_tiebreak is True
    assert st.score_bucket == DEUCE_BUCKET      # matches match_sim.play_tiebreak
    assert st.break_point is None               # UNDEF inside a tiebreak


def test_retired_match_is_terminal_not_live_and_break_point_undef():
    st = live_state_from_match(_match(status="live", event_status="Retired"))
    assert st.is_live is False and st.terminal_reason == "retired"
    assert st.break_point is None


def test_walkover_is_terminal():
    st = live_state_from_match(_match(status="completed", event_status="Walk Over"))
    assert st.is_live is False and st.terminal_reason == "walk over"


def test_completed_match_with_null_points_yields_no_bucket():
    st = live_state_from_match(_match(status="completed", points=(None, None)))
    assert st.is_live is False
    assert st.score_bucket is None
    assert st.break_point is None


def test_missing_server_yields_undecidable_state():
    st = live_state_from_match(_match(server=None))
    assert st.server_id is None and st.score_bucket is None


def test_live_point_prob_none_when_not_live():
    st = live_state_from_match(_match(status="completed", points=(None, None)))
    assert live_point_prob(lambda s, sb, tb: 0.6, st) is None


def test_live_point_prob_conditions_on_the_live_bucket():
    st = live_state_from_match(_match(server=1, points=("30", "15")))
    seen = {}

    def prob_fn(sid, sb, tb):
        seen["args"] = (sid, sb, tb)
        return 0.63

    p = live_point_prob(prob_fn, st)
    assert p == 0.63
    assert seen["args"] == ("Alice", st.score_bucket, st.set_bucket)


def test_live_point_prob_composes_with_a_real_point_model():
    df = pd.DataFrame([{"server_id": "Alice", "score_bucket": score_bucket(2, 1),
                        "set_bucket": 1, "server_won": i % 2} for i in range(40)])
    model = PointModel.fit(df)
    st = live_state_from_match(_match(server=1, points=("30", "15")))
    p = live_point_prob(model.prob, st)
    assert p is not None and 0.0 <= p <= 1.0


def test_to_point_frame_row_matches_corpus_contract():
    st = live_state_from_match(_match(server=1, points=("30", "15")))
    row = to_point_frame_row(st)
    assert set(row) == {"match_id", "server_id", "returner_id", "score_bucket",
                        "set_bucket", "server_won"}
    assert row["server_won"] is None            # live: label not known yet
    assert row["server_id"] == "Alice"


def test_feed_reshape_filters_non_dicts():
    payload = {"data": [_match(mid="a"), "junk", _match(mid="b", server=2)]}
    states = live_states_from_feed(payload)
    assert [s.match_id for s in states] == ["a", "b"]
    assert all(isinstance(s, LiveState) for s in states)


def test_empty_or_malformed_feed_is_empty_list():
    assert live_states_from_feed({}) == []
    assert live_states_from_feed({"data": None}) == []
