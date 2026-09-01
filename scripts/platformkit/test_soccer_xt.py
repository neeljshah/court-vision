import numpy as np
import pandas as pd

from scripts.platformkit.soccer_xt import SoccerXT, ball_proxy_events, solve_xt


def test_forward_moves_gain_xt_and_aggregate_by_window():
    events = pd.DataFrame({"x": [20.0, 30.0], "y": [34.0, 34.0],
                           "next_x": [90.0, 95.0], "next_y": [34.0, 34.0],
                           "is_shot": [False, False], "is_goal": [False, False],
                           "team": ["HOME", "HOME"], "timestamp": [12, 18]})
    actions, sums = SoccerXT().apply(events)
    assert (actions.xt_delta > 0).all()
    assert sums.loc[0, "xt_delta"] == actions.xt_delta.sum()


def test_solver_converges_on_toy_transition_matrix():
    shot = np.array([0.0, 0.5])
    goal = np.array([0.0, 0.4])
    move = np.array([1.0, 0.0])
    transition = np.array([[0.0, 1.0], [0.0, 0.0]])
    solved = solve_xt(shot, goal, move, transition)
    assert np.allclose(solved, [0.2, 0.2])


def test_no_ball_rows_are_clean_and_honest(capsys):
    events = ball_proxy_events(pd.DataFrame({"cls": ["player"], "x": [1], "y": [2]}))
    assert events.empty
    assert capsys.readouterr().out.strip() == "PENDING BALL TRACKING"
