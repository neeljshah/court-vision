"""Per-file test: horizon at-or-before extraction, exclusion, devig, MLB start parse."""
import numpy as np

from scripts.platformkit.ingame import freshness_premium as fp


def test_last_at_or_before():
    ts = np.array([100.0, 200.0, 300.0])
    p = np.array([0.1, 0.2, 0.3])
    # cutoff exactly on a tick -> that tick (at-OR-before)
    assert fp._last_at_or_before(ts, p, 200.0) == 0.2
    # cutoff between ticks -> the earlier one
    assert fp._last_at_or_before(ts, p, 250.0) == 0.2
    # cutoff after all -> last
    assert fp._last_at_or_before(ts, p, 999.0) == 0.3
    # cutoff before all -> None (excluded)
    assert fp._last_at_or_before(ts, p, 50.0) is None


def test_devig():
    # both sides -> normalized
    assert abs(fp._devig(0.55, 0.55) - 0.5) < 1e-9
    assert abs(fp._devig(0.6, 0.4) - 0.6) < 1e-9   # already sums to 1
    # only ref -> raw single-sided implied prob
    assert fp._devig(0.7, None) == 0.7
    # degenerate sum -> raw
    assert fp._devig(0.0, 0.0) == 0.0
    # no ref -> None
    assert fp._devig(None, 0.5) is None


def test_mlb_start_parse():
    # 26APR26 19:20 ET -> 23:20 UTC same day (EDT -4)
    s = fp.mlb_start_from_ticker("KXMLBGAME-26APR261920LAAKC")
    import datetime as dt
    got = dt.datetime.fromtimestamp(s, dt.timezone.utc)
    assert (got.month, got.day, got.hour, got.minute) == (4, 26, 23, 20)
    assert fp.mlb_start_from_ticker("KXNBAGAME-26APR26BOSPHI") is None


def test_curve_exclusion_and_scoring(tmp_path, monkeypatch):
    """Synthetic 3-game corpus: game missing early ticks is excluded from T-24h."""
    import pandas as pd
    _CLOSE = "2026-04-27T00:00:00Z"
    start = int(fp._parse_close(_CLOSE))  # duration 'syn'=0 -> start == close == this epoch
    rows = []

    def add(ek, side, res, offsets, prob):
        for off in offsets:
            rows.append(dict(venue="kalshi", event_key=ek, market_type="moneyline",
                             side=side, ts=start + off, prob=prob,
                             close_time=_CLOSE, result_where_known=res))

    # game A: ticks from -30h..0, ref (AAA) wins, priced 0.7
    add("gA", "AAA", "yes", [-30 * 3600, -6 * 3600, -600, 0], 0.7)
    add("gA", "BBB", "no", [-30 * 3600, -6 * 3600, -600, 0], 0.3)
    # game B: ticks only from -2h (NO tick before T-24h/T-6h/T-3h cutoffs) -> excluded there
    add("gB", "AAA", "no", [-2 * 3600, -600, 0], 0.4)
    add("gB", "CCC", "yes", [-2 * 3600, -600, 0], 0.6)
    # game C: single-sided (raw prob), ref wins
    add("gC", "AAA", "yes", [-30 * 3600, 0], 0.8)

    df = pd.DataFrame(rows)
    p = tmp_path / "syn_price_series.parquet"
    df.to_parquet(p)
    monkeypatch.setattr(fp, "_ODDS", tmp_path)
    # force close-minus-duration path but with a start that matches our synthetic 'start'
    # close_time above = start + 0; duration pushes start earlier, so use ticker=None sport 'syn'
    monkeypatch.setitem(fp._DURATION_H, "syn", 0.0)  # start == close == epoch 'start'... but close!=start
    games, diag = fp.load_games("syn")
    # 3 games kept (all have 2 valid sides except gC single-sided but ref present)
    # gC has one side only -> len(sides)!=2 -> excluded as bad_sides
    assert diag["games_bad_sides"] == 1  # gC dropped (single side)
    assert diag["games_kept"] == 2

    res = fp.curve_for_sport("syn")
    h = {r["horizon"]: r for r in res["horizons"]}
    # T-24h: only gA has a tick before start-24h; gB excluded -> n=1
    assert h["T-24h"]["n"] == 1 and h["T-24h"]["excluded"] == 1
    # last_pregame_tick: both gA,gB present -> n=2
    assert h["last_pregame_tick"]["n"] == 2
    assert res["notes"]["edge_claimed"] is False


if __name__ == "__main__":
    test_last_at_or_before()
    test_devig()
    test_mlb_start_parse()
    print("core asserts pass (run pytest for the fixture-based test)")
