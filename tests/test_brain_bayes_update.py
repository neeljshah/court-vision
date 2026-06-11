"""P3.2 — the minutes-weighted Bayesian player update + trust curve.

Proves: (1) the DEFAULT (identity trust curve, no json) reproduces BASE EXACTLY — byte-identical,
no shrink; (2) with evidence weight, a cold star reverts UP toward prior and a hot player reverts DOWN;
(3) the posterior is the documented linear blend (monotone in trust_w); (4) the playoff-AST guard caps
the evidence weight. The shrink-toward-current path is the GATED experiment, never the default.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from ingame import trust_curve  # noqa: E402
from ingame.bayes_player_update import evidence_extrap, posterior_projection  # noqa: E402


def test_trust_curve_default_is_identity():
    assert trust_curve.is_identity() is True
    assert trust_curve.trust_w("pts", 0.5, None) == 0.0
    assert trust_curve.trust_w("ast", 0.1, {"is_playoff": True}) == 0.0


def test_identity_reproduces_base_exactly():
    # no json -> trust_w 0 -> posterior == prior (BASE), byte-identical, for any current/minutes
    post, tw, _ = posterior_projection(prior=25.0, current=4.0, min_so_far=10.0, remaining_min=28.0, stat="pts")
    assert tw == 0.0
    assert post == 25.0


def test_cold_star_reverts_up():
    # low current (4 pts in 10 min), big prior (25), lots of game left -> prior pulls ABOVE current pace
    e = evidence_extrap(4.0, 10.0, 28.0)        # 4 + 0.4*28 = 15.2
    post, tw, direction = posterior_projection(25.0, 4.0, 10.0, 28.0, "pts", trust_override=0.5)
    assert direction == "up"
    assert abs(e - 15.2) < 1e-9
    assert e < post < 25.0          # pulled up from the cold 15.2 toward the 25 prior
    assert abs(post - (0.5 * 15.2 + 0.5 * 25.0)) < 1e-9


def test_hot_player_reverts_down():
    e = evidence_extrap(18.0, 10.0, 28.0)       # 18 + 1.8*28 = 68.4
    post, tw, direction = posterior_projection(25.0, 18.0, 10.0, 28.0, "pts", trust_override=0.5)
    assert direction == "down"
    assert 25.0 < post < e          # cooled down from the hot 68.4 toward the 25 prior
    assert abs(post - (0.5 * 68.4 + 0.5 * 25.0)) < 1e-9


def test_posterior_monotone_in_trust_w():
    p0 = posterior_projection(25.0, 4.0, 10.0, 28.0, "pts", trust_override=0.0)[0]
    p1 = posterior_projection(25.0, 4.0, 10.0, 28.0, "pts", trust_override=1.0)[0]
    pmid = posterior_projection(25.0, 4.0, 10.0, 28.0, "pts", trust_override=0.5)[0]
    assert p0 == 25.0                      # trust_w=0 -> prior
    assert abs(p1 - 15.2) < 1e-9           # trust_w=1 -> evidence extrapolation
    assert min(p0, p1) <= pmid <= max(p0, p1)


def test_no_minutes_played_falls_back_to_current():
    # min_so_far=0 -> evidence undefined -> evidence_extrap returns current; prior still dominates at tw=0
    assert evidence_extrap(0.0, 0.0, 30.0) == 0.0
    post, _, _ = posterior_projection(25.0, 0.0, 0.0, 30.0, "pts", trust_override=1.0)
    assert post == 0.0                     # trust_w=1 + no minutes -> current (0)


def test_playoff_ast_guard_caps_evidence_weight():
    # even with a high override, playoff AST trust is capped toward BASE
    post, tw, _ = posterior_projection(8.0, 6.0, 10.0, 28.0, "ast",
                                       regime={"is_playoff": True}, trust_override=0.9)
    assert tw == 0.10
    # non-playoff AST: no cap
    _, tw2, _ = posterior_projection(8.0, 6.0, 10.0, 28.0, "ast",
                                     regime={"is_playoff": False}, trust_override=0.9)
    assert tw2 == 0.9
