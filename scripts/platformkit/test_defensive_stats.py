"""Self-check for defensive_stats + pbp_lineups. Run: python -m scripts.platformkit.test_defensive_stats"""
from scripts.platformkit.defensive_stats import _f, deterrence, finalize
from scripts.platformkit.pbp_lineups import clock_to_sec, SUB_RE


def test_f():
    assert _f("3.5") == 3.5
    assert _f("") == 0.0
    assert _f(None) == 0.0
    assert _f("nan") == 0.0          # NaN guard, else it poisons every mean
    assert _f("x", 9.0) == 9.0


def test_clock():
    assert clock_to_sec("PT7M1.00S") == 421.0
    assert clock_to_sec("PT0M0.00S") == 0.0
    assert clock_to_sec("PT12M0.00S") == 720.0
    assert clock_to_sec("garbage") is None


def test_sub_regex():
    m = SUB_RE.match("Maxi Kleber enters the game for Daniel Gafford")
    assert m and m.group(1) == "Maxi Kleber" and m.group(2) == "Daniel Gafford"
    assert SUB_RE.match("Luka Doncic 3PT Jump Shot") is None


def test_deterrence():
    # 3 possessions attacked the rim, 2 yielded nothing -> 2/3
    rows = [
        {"drive_share": 0.5, "rim_share": 0.0, "points_allowed": 0.0},
        {"drive_share": 0.0, "rim_share": 0.3, "points_allowed": 0.0},
        {"drive_share": 0.2, "rim_share": 0.0, "points_allowed": 2.0},
        {"drive_share": 0.0, "rim_share": 0.0, "points_allowed": 3.0},  # not attacked
    ]
    rate, n = deterrence(rows)
    assert n == 3, n
    assert abs(rate - 2.0 / 3.0) < 1e-9, rate
    assert deterrence([]) == (0.0, 0)


def test_finalize_skips_thin_possessions():
    poss = {"1": {"points": 2.0, "result": "made_fg", "offense": "LAL", "duration": 14.0}}
    thin = {"1": dict(frames=3, handler_frames=0, drive_frames=0, rim_frames=0,
                      pressure_sum=0.0, pressure_n=0, paint_opp_sum=0.0,
                      spacing_sum=0.0, spacing_n=0, contest_sum=0.0, contest_n=0,
                      jumps=0, closeout_sum=0.0, closeout_n=0, rotations=0,
                      offball_prev={}, min_rim_dist=99.0, iso_sum=0.0, iso_n=0)}
    assert finalize(thin, poss, "G") == []       # under the 10-frame floor
    thin["1"]["frames"] = 40
    out = finalize(thin, poss, "G")
    assert len(out) == 1 and out[0]["points_allowed"] == 2.0
    assert out[0]["late_clock"] == 0             # 14s < 17s threshold


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok  %s" % name)
    print("all passed")
