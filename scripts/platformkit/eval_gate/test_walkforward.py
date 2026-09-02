"""Tests for the leak-free walk-forward harness. stdlib only; standalone or pytest."""
from __future__ import annotations
import os as _os, sys as _sys  # noqa: E402
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # blueprint uses bare sibling imports; make them work under "python -m pytest" from the repo root too
from walkforward import LeakError, walk_forward, assert_vintage, redact_test_view


def _s(game_id, ts, home, away, **kw):
    base = {"game_id": game_id, "state_ts": ts, "home": home, "away": away,
            "features": {"x": 1.0},
            "feature_avail": {"x": ts[:10] + "T00:00:00"}, "devig_close_prob": 0.5,
            "outcome": 0}
    base.update(kw)
    # ensure feature is known strictly before state_ts (day-before midnight < same-day game)
    # and keep features/feature_avail key parity (leak-contract hardening 2026-09-01)
    base["feature_avail"] = {k: (ts[:8] + "01T00:00:00") for k in base["features"]}
    return base


def _trivial(train, test, select_inside):
    return 0.5


def test_no_lookahead():
    # distinct teams per game -> no purge/embargo applies, so train = all prior states.
    states = [_s(f"g{i}", f"2024-02-{10+i:02d}T19:00:00", f"H{i}", f"V{i}") for i in range(5)]
    seen = {}

    def peeking(train, test, select_inside):
        for tr in train:                          # every training state strictly before test
            assert tr["state_ts"] < test["state_ts"], "LOOKAHEAD"
        seen[test["game_id"]] = [t["game_id"] for t in train]
        return 0.5

    res = walk_forward(states, peeking)
    assert len(res.records) == 5
    assert seen["g0"] == []                        # first state has empty train
    assert seen["g4"] == ["g0", "g1", "g2", "g3"]  # expanding window, no team overlap


def test_purge_same_team_within_48h():
    # two A-vs-C games 24h apart: the later one's train must EXCLUDE the earlier (same team, <48h)
    states = [
        _s("early", "2024-03-01T19:00:00", "A", "C"),
        _s("late", "2024-03-02T19:00:00", "A", "D"),   # shares team A, 24h later
    ]
    captured = {}

    def cap(train, test, select_inside):
        captured[test["game_id"]] = [t["game_id"] for t in train]
        return 0.5

    walk_forward(states, cap)
    assert captured["late"] == []                  # 'early' purged (same team A within 48h)


def test_embargo_same_matchup_within_3d():
    states = [
        _s("m1", "2024-03-01T19:00:00", "A", "B"),
        _s("m2", "2024-03-02T19:00:00", "A", "B"),   # same matchup, 1 day later
    ]
    captured = {}

    def cap(train, test, select_inside):
        captured[test["game_id"]] = [t["game_id"] for t in train]
        return 0.5

    walk_forward(states, cap)
    assert captured["m2"] == []                    # 'm1' embargoed (same matchup within 3d)


def test_distant_same_team_is_kept():
    # same team but 5 days apart -> NOT purged (outside 48h) and not same matchup -> kept
    states = [
        _s("old", "2024-03-01T19:00:00", "A", "C"),
        _s("new", "2024-03-08T19:00:00", "A", "D"),
    ]
    captured = {}

    def cap(train, test, select_inside):
        captured[test["game_id"]] = [t["game_id"] for t in train]
        return 0.5

    walk_forward(states, cap)
    assert captured["new"] == ["old"]


def test_vintage_leak_raises():
    bad = _s("g", "2024-03-01T19:00:00", "A", "B")
    bad["feature_avail"] = {"x": "2024-03-02T00:00:00"}   # AFTER state_ts
    try:
        assert_vintage(bad); raise SystemExit("FAIL: leak not caught")
    except AssertionError as e:
        assert "LEAK" in str(e)


def test_select_inside_flag_recorded():
    states = [_s("g0", "2024-03-01T19:00:00", "A", "B")]
    res_ok = walk_forward(states, _trivial, select_inside=True)
    res_bad = walk_forward(states, _trivial, select_inside=False)
    assert res_ok.select_inside is True
    assert res_bad.select_inside is False          # gate must FAIL the run when this is False


def test_s40b_rt18_new_settled_column_is_not_handed_to_the_predictor():
    """RT-18: the deny-list let ANY new settled column through. Measured before the fix:
    a state carrying `final_margin` let an oracle score Brier 0.0000 with no LeakError."""
    states = [_s(f"g{i}", f"2024-02-{10+i:02d}T19:00:00", f"H{i}", f"V{i}",
                 final_margin=10.0) for i in range(4)]

    # default (legacy) mode is unchanged: the four deny-listed keys and nothing else.
    legacy = redact_test_view(states[0])
    assert "final_margin" in legacy                      # documented legacy behaviour
    assert not {"outcome", "devig_close_prob"} & set(legacy)

    # strict mode: the undeclared settled column is a LeakError, not a silent pass-through.
    try:
        walk_forward(states, lambda train, test, inside: 0.5, strict_redaction=True)
        raise SystemExit("FAIL: undeclared settled column reached the predictor")
    except LeakError as exc:
        assert "final_margin" in str(exc)

    # a caller that genuinely needs a key DECLARES it, and only that key comes back.
    view = redact_test_view(states[0], allow_keys=("final_margin",), strict=True)
    assert view["final_margin"] == 10.0
    assert view["game_id"] == "g0" and "outcome" not in view


def test_s40b_rt18_strict_view_is_exactly_the_declared_allow_list():
    """The strict view is derived from TEST_VIEW_KEYS, not from what the state happens
    to carry -- an independently written expectation, not a copy of the constant."""
    state = _s("g0", "2024-03-01T19:00:00", "A", "B", season="2023-24", sport="nba")
    view = redact_test_view(state, strict=True)
    assert set(view) == {"game_id", "state_ts", "home", "away", "features",
                         "feature_avail", "season", "sport"}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} walk-forward tests passed.")
