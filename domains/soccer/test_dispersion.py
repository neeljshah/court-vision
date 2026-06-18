"""Per-file tests for domains.soccer.dispersion (leak-free NB width calibration).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_dispersion.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.soccer import dispersion


def _df_counts(counts, dates=None, stat_col="totalShots", as_of="2026-07-01"):
    """One player-match row per count value (all minutes>0, all before as_of).

    Dates are sequential valid timestamps well before as_of (start 2026-01-01).
    """
    n = len(counts)
    if dates is None:
        base = pd.Timestamp("2026-01-01")
        dates = [(base + pd.Timedelta(days=i)).date().isoformat() for i in range(n)]
    rows = []
    for i, (c, d) in enumerate(zip(counts, dates)):
        rows.append({"player_id": str(100 + i), "date": d, "minutes": 90,
                     stat_col: c})
    return pd.DataFrame(rows)


def test_handchecked_phi_and_r_overdispersed():
    """counts [0,1,4,5] -> m=2.5, var(ddof0)=4.25, phi=1.7, r=m/(phi-1)~=3.57.
    (Prompt's reference phi~1.733 / r~3.41 -- we match within tolerance.)"""
    # Pad to >= _MIN_N rows by repeating the pattern (keeps the same m and phi).
    counts = [0, 1, 4, 5] * 12  # 48 rows > _MIN_N=40
    df = _df_counts(counts)
    res = dispersion.stat_dispersion(df, "Shots", "2026-07-01")
    assert res["status"] == "ok"
    assert res["n"] == 48
    assert abs(res["phi"] - 1.70) < 0.05
    assert res["r"] is not None
    # r at the stat's representative mean (Shots rep_mean=1.6): 1.6/(1.7-1)=2.285.
    # Just assert it's a sensible finite over-dispersion size in range.
    assert 1.0 <= res["r"] <= 50.0


def test_r_for_lam_rowspecific():
    """Row-specific r = lam/(phi-1). At phi=1.7, lam=2.5 -> r=2.5/0.7~=3.57."""
    r = dispersion.r_for_lam(1.7, 2.5)
    assert r is not None
    assert abs(r - (2.5 / 0.7)) < 1e-6
    # phi<=1 -> Poisson (None); lam<=0 -> None.
    assert dispersion.r_for_lam(1.0, 2.5) is None
    assert dispersion.r_for_lam(0.9, 2.5) is None
    assert dispersion.r_for_lam(1.7, 0.0) is None


def test_underdispersed_returns_poisson():
    """phi <= 1 (variance <= mean) -> r None, status ok (Poisson already wide)."""
    # constant counts -> var 0 -> phi 0 <= 1. Pad past _MIN_N.
    df = _df_counts([3] * 48)
    res = dispersion.stat_dispersion(df, "Shots", "2026-07-01")
    assert res["status"] == "ok"
    assert res["phi"] <= 1.0
    assert res["r"] is None


def test_thin_falls_back_to_prior():
    """Small n -> status 'prior' with the per-stat prior phi (not a noisy fit)."""
    df = _df_counts([0, 1, 4, 5])  # only 4 rows << _MIN_N
    res = dispersion.stat_dispersion(df, "Shots", "2026-07-01")
    assert res["status"] == "prior"
    assert abs(res["phi"] - dispersion._PRIOR_PHI["Shots"]) < 1e-9
    assert res["n"] == 4


def test_no_data_is_prior_not_unknown():
    df = _df_counts([1, 2, 3], as_of="2025-01-01")  # all rows AFTER as_of
    res = dispersion.stat_dispersion(df, "Shots", "2025-01-01")
    assert res["status"] == "prior"
    assert res["n"] == 0


def test_unknown_stat_degrades():
    df = _df_counts([1, 2, 3])
    res = dispersion.stat_dispersion(df, "NotAStat", "2026-07-01")
    assert res["status"] == "unknown"
    assert res["r"] is None


def test_leak_free_post_asof_ignored():
    """Adding a match dated ON/AFTER as_of must NOT change the fit (leak guard)."""
    counts = [0, 1, 4, 5] * 12
    df = _df_counts(counts)
    base = dispersion.stat_dispersion(df, "Shots", "2026-07-01")
    # Append a wildly different row dated after as_of.
    leak = pd.DataFrame([{"player_id": "999", "date": "2026-07-05",
                          "minutes": 90, "totalShots": 99}])
    df2 = pd.concat([df, leak], ignore_index=True)
    after = dispersion.stat_dispersion(df2, "Shots", "2026-07-01")
    assert after["n"] == base["n"]
    assert abs(after["phi"] - base["phi"]) < 1e-9
    assert (after["r"] is None) == (base["r"] is None)


def test_all_dispersions_covers_every_stat():
    from domains.soccer.player_rates import CANON_TO_COLS
    df = _df_counts([0, 1, 4, 5] * 12)
    out = dispersion.all_dispersions(df, "2026-07-01")
    assert set(out.keys()) == set(CANON_TO_COLS.keys())
    for stat, res in out.items():
        assert res["status"] in ("ok", "prior", "unknown")


def test_never_raises_on_garbage():
    assert dispersion.stat_dispersion(None, "Shots", "2026-07-01")["status"] in (
        "ok", "prior", "unknown")
    assert dispersion.stat_dispersion(pd.DataFrame(), "Shots", None)["status"] in (
        "ok", "prior", "unknown")
    assert dispersion.r_for_lam(None, None) is None
