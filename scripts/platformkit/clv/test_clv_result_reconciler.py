"""Per-file tests for clv_result_reconciler."""
from __future__ import annotations

import json

from scripts.platformkit.clv import clv_result_reconciler as _mod
from scripts.platformkit.clv.clv_result_reconciler import (
    KNOWN_CHANNELS, _close_implied_expectation, _duplicate_close_pairs,
    _record, _single_side, _verdict, _zscore, main, reconcile_channel)


def _row(side, taken_decimal, close_home, close_away, unit_result, fair_close_prob,
         event_id="e1", channel="paper_pm", stake_units=1.0, clv_pct=1.0):
    return {
        "channel": channel, "status": "settled", "side": side,
        "taken_decimal": taken_decimal,
        "closing_decimal_home": close_home, "closing_decimal_away": close_away,
        "fair_close_prob": fair_close_prob, "clv_pct": clv_pct,
        "clv_status": "true_close", "unit_result": unit_result,
        "stake_units": stake_units, "event_id": event_id,
        "bet_id": "b-%s-%s" % (event_id, side),
    }


def test_record_counts_wlp_and_units():
    rows = [
        _row("home", 2.0, 2.0, 2.0, 1.0, 0.5),
        _row("home", 2.0, 2.0, 2.0, -1.0, 0.5),
        _row("home", 2.0, 2.0, 2.0, 0.0, 0.5),
    ]
    rec = _record(rows)
    assert rec == {"wins": 1, "losses": 1, "pushes": 1, "net_units": 0.0}


def test_close_implied_expectation_matches_fair_prob():
    # A single fair-coin bet at decimal 2.0: E[units] = 0.5*1 - 0.5*1 = 0, E[wins]=0.5.
    rows = [_row("home", 2.0, 2.0, 2.0, 1.0, 0.5)]
    exp = _close_implied_expectation(rows)
    assert exp["n_used"] == 1
    assert exp["exp_wins"] == 0.5
    assert exp["exp_units"] == 0.0


def test_close_implied_expectation_skips_bad_rows():
    rows = [_row("home", 2.0, 2.0, 2.0, 1.0, 0.5)]
    bad = dict(rows[0])
    bad.pop("fair_close_prob")
    exp = _close_implied_expectation(rows + [bad])
    assert exp["n_used"] == 1  # bad row silently skipped, never crashes


def test_zscore_none_when_no_se():
    assert _zscore(5.0, 4.0, None) is None
    assert _zscore(5.0, 4.0, 0.0) is None
    assert _zscore(6.0, 4.0, 2.0) == 1.0


def test_verdict_insufficient_data_below_min_n():
    v = _verdict(3, 0.1, 0.1)
    assert v.startswith("INSUFFICIENT_DATA")


def test_verdict_genuine_variance_within_band():
    v = _verdict(20, -0.5, -1.2)
    assert v.startswith("GENUINE_VARIANCE")


def test_verdict_divergent_worse():
    v = _verdict(20, -2.5, -0.3)
    assert v.startswith("DIVERGENT")
    assert "WORSE" in v


def test_verdict_divergent_better():
    v = _verdict(20, 2.5, 0.3)
    assert v.startswith("DIVERGENT")
    assert "BETTER" in v


def test_duplicate_close_pairs_counts_cross_event_only():
    rows = [
        _row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="g1"),
        _row("away", 2.0, 2.0, 2.0, -1.0, 0.5, event_id="g1"),   # same event -> not counted
        _row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="g2"),    # different event, same pair
    ]
    assert _duplicate_close_pairs(rows) == 1


def test_reconcile_channel_genuine_variance_synthetic():
    # 20 fair-coin bets, roughly half win -> should read GENUINE_VARIANCE.
    rows = []
    for i in range(20):
        won = i % 2 == 0
        rows.append(_row(
            "home", 2.0, 2.0, 2.0,
            unit_result=(1.0 if won else -1.0), fair_close_prob=0.5,
            event_id="g%d" % i, clv_pct=2.0,
        ))
    report = reconcile_channel("paper_pm", ledger=rows)
    assert report["n_measurable"] == 20
    assert report["record"]["wins"] == 10
    assert report["verdict"].startswith("GENUINE_VARIANCE")


def test_reconcile_channel_insufficient_data_small_n():
    rows = [_row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="g1")]
    report = reconcile_channel("paper_pm", ledger=rows)
    assert report["n_measurable"] == 1
    assert report["verdict"].startswith("INSUFFICIENT_DATA")


def test_reconcile_channel_ignores_other_channels_and_unmeasurable():
    rows = [
        _row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="g1", channel="paper"),
        {"channel": "paper_pm", "status": "settled", "clv_status": "no_close",
         "event_id": "g2", "bet_id": "b-g2"},
    ]
    report = reconcile_channel("paper_pm", ledger=rows)
    assert report["n_measurable"] == 0
    assert report["verdict"].startswith("INSUFFICIENT_DATA")


# ---------------------------------------------------------------------------
# E-check-3 BUILD-WAVE EXTENSION: always-emit-every-known-channel.
# ---------------------------------------------------------------------------

def test_known_channels_matches_spec_set():
    assert set(KNOWN_CHANNELS) == {
        "moneyline", "paper_pm", "paper_ingame", "paper_ingame_prop"}


def test_zero_row_channel_has_no_fabricated_z(tmp_path, monkeypatch):
    # Ledger has rows for only ONE channel; the other three KNOWN_CHANNELS
    # entries must still each get an honest INSUFFICIENT_DATA file with real
    # n_measurable and un-fabricated (None) z-scores.
    only_paper_pm = [
        _row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="g1", channel="paper_pm"),
    ]
    monkeypatch.setattr(_mod, "load_ledger", lambda: only_paper_pm)
    rc = main(argv=[], out_dir=str(tmp_path))
    assert rc == 0
    for ch in KNOWN_CHANNELS:
        out_path = tmp_path / ("clv_reconcile_%s.json" % ch)
        assert out_path.exists(), "missing emitted file for known channel %s" % ch
        report = json.loads(out_path.read_text(encoding="utf-8"))
        assert report["channel"] == ch
        if ch == "paper_pm":
            continue  # this channel has the one row; other 3 are zero-row
        assert report["n_measurable"] == 0
        assert report["verdict"].startswith("INSUFFICIENT_DATA")
        assert report["z_wins"] is None
        assert report["z_units"] is None


def test_main_default_argv_covers_every_known_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(_mod, "load_ledger", lambda: [])
    main(argv=[], out_dir=str(tmp_path))
    written = {p.name for p in tmp_path.glob("clv_reconcile_*.json")}
    assert written == {"clv_reconcile_%s.json" % ch for ch in KNOWN_CHANNELS}


def test_explicit_argv_still_scopes_to_requested_channels(tmp_path, monkeypatch):
    # Manual/ad-hoc CLI use (explicit channel args) is unchanged: only the
    # requested channel(s) are written, not the full known set.
    monkeypatch.setattr(_mod, "load_ledger", lambda: [])
    main(argv=["moneyline"], out_dir=str(tmp_path))
    written = {p.name for p in tmp_path.glob("clv_reconcile_*.json")}
    assert written == {"clv_reconcile_moneyline.json"}


# ---------------------------------------------------------------------------
# single_side: both-sides-pair independence transparency fix.
# ---------------------------------------------------------------------------

def test_single_side_collapses_both_sides_pairs_keeps_first_taken():
    rows = [
        _row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="p1"),   # pair p1, first
        _row("away", 2.0, 2.0, 2.0, -1.0, 0.5, event_id="p1"),  # pair p1, dropped
        _row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="p2"),   # pair p2, first
        _row("away", 2.0, 2.0, 2.0, -1.0, 0.5, event_id="p2"),  # pair p2, dropped
        _row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="s1"),
        _row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="s2"),
        _row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="s3"),
    ]
    out, both_pairs = _single_side(rows)
    assert len(out) == 5
    assert both_pairs == 2
    kept_ids = [r["event_id"] for r in out]
    assert kept_ids == ["p1", "p2", "s1", "s2", "s3"]
    assert [r["side"] for r in out[:2]] == ["home", "home"]  # first-taken side kept


def test_reconcile_channel_single_side_block_2_pairs_3_singles():
    rows = [
        _row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="p1"),
        _row("away", 1.8, 2.0, 2.0, -1.0, 0.45, event_id="p1"),
        _row("home", 2.0, 2.0, 2.0, -1.0, 0.5, event_id="p2"),
        _row("away", 1.9, 2.0, 2.0, 1.0, 0.48, event_id="p2"),
        _row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="s1"),
        _row("home", 2.0, 2.0, 2.0, -1.0, 0.5, event_id="s2"),
        _row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="s3"),
    ]
    report = reconcile_channel("paper_pm", ledger=rows)
    # Headline stays computed over ALL 7 rows -- no behavior change.
    assert report["n_measurable"] == 7
    pre_fix_verdict = report["verdict"]
    pre_fix_z_wins = report["z_wins"]
    pre_fix_z_units = report["z_units"]
    # New block is additive context on the one-row-per-event_id subset.
    ss = report["single_side"]
    assert ss["n"] == 5
    assert ss["both_sides_pairs"] == 2
    assert ss["note"] is not None and "2 event" in ss["note"]
    # Headline fields provably unaffected by computing the additive block.
    assert report["verdict"] == pre_fix_verdict
    assert report["z_wins"] == pre_fix_z_wins
    assert report["z_units"] == pre_fix_z_units


def test_reconcile_channel_single_side_identical_to_headline_when_no_pairs():
    rows = [
        _row("home", 2.0, 2.0, 2.0, (1.0 if i % 2 == 0 else -1.0), 0.5,
             event_id="g%d" % i)
        for i in range(20)
    ]
    report = reconcile_channel("paper_pm", ledger=rows)
    ss = report["single_side"]
    assert ss["n"] == report["n_measurable"]
    assert ss["both_sides_pairs"] == 0
    assert ss["note"] is None
    assert ss["z_wins"] == report["z_wins"]
    assert ss["z_units"] == report["z_units"]


def test_cross_venue_basis_flags_pm_taken_book_close():
    # Kalshi-taken rows priced against a Pinnacle (different-venue) close are
    # cross-venue basis; the verdict/z stay untouched, the block flags the basis.
    rows = []
    for i in range(20):
        r = _row("home", 2.0, 2.0, 2.0,
                 unit_result=(1.0 if i % 2 == 0 else -1.0), fair_close_prob=0.5,
                 event_id="g%d" % i, clv_pct=15.0)
        r["venue"] = "kalshi"
        r["is_pm"] = True
        r["close_book_home"] = r["close_book_away"] = "pinnacle"
        rows.append(r)
    report = reconcile_channel("paper_pm", ledger=rows)
    cvb = report["cross_venue_basis"]
    assert cvb["n"] == 20 and cvb["n_measurable"] == 20
    assert cvb["books"] == {"pinnacle": 20}
    assert cvb["mean_clv_pct"] == 15.0
    assert cvb["note"] and "BASIS" in cvb["note"]
    # Same-venue (pm_close_capture) close is NOT counted as basis.
    for r in rows:
        r["close_source"] = "kalshi"
    same = reconcile_channel("paper_pm", ledger=rows)
    assert same["cross_venue_basis"]["n"] == 0


def test_cross_venue_basis_zero_for_non_pm_rows():
    # Plain moneyline (non-PM) rows are never cross-venue basis.
    rows = [_row("home", 2.0, 2.0, 2.0, 1.0, 0.5, event_id="g%d" % i,
                 channel="paper_pm") for i in range(12)]
    report = reconcile_channel("paper_pm", ledger=rows)
    assert report["cross_venue_basis"]["n"] == 0
    assert report["cross_venue_basis"]["note"] is None


def test_existing_channel_with_adequate_data_unchanged_by_extension(tmp_path, monkeypatch):
    # Regression lock: moneyline/paper_pm w/ adequate measurable data still
    # reads GENUINE_VARIANCE (the always-emit extension must not perturb the
    # existing per-channel math or write format for a well-populated channel).
    rows = []
    for i in range(20):
        won = i % 2 == 0
        rows.append(_row(
            "home", 2.0, 2.0, 2.0,
            unit_result=(1.0 if won else -1.0), fair_close_prob=0.5,
            event_id="g%d" % i, clv_pct=2.0, channel="paper_pm",
        ))
    monkeypatch.setattr(_mod, "load_ledger", lambda: rows)
    main(argv=[], out_dir=str(tmp_path))
    report = json.loads(
        (tmp_path / "clv_reconcile_paper_pm.json").read_text(encoding="utf-8"))
    assert report["n_measurable"] == 20
    assert report["record"]["wins"] == 10
    assert report["verdict"].startswith("GENUINE_VARIANCE")


# --------------------------------------------------------------------------------------- #
# W1 FIX: kx-proxy measurable tier -- SEPARATE from true_close, PROXY-labelled verdict.    #
# --------------------------------------------------------------------------------------- #
def _proxy_row(side, taken_decimal, fair_close_prob, unit_result, event_id,
               channel="paper_ingame", clv_pct=1.0, stake_units=1.0):
    return {
        "channel": channel, "status": "settled", "side": side,
        "taken_decimal": taken_decimal, "fair_close_prob": fair_close_prob,
        "clv_pct": clv_pct, "clv_status": "proxy", "clv_is_proxy": True,
        "unit_result": unit_result, "stake_units": stake_units,
        "event_id": event_id, "sport": "mlb", "game_id": "KX-%s" % event_id,
        "bet_id": "b-%s-%s" % (event_id, side),
    }


def test_proxy_tier_separate_never_merged_into_true_close():
    rows = [_proxy_row("home", 1.9, 0.55, 1.0, "e%d" % i) for i in range(3)]
    report = reconcile_channel("paper_ingame", ledger=rows)
    assert report["n_measurable"] == 0            # true_close tier untouched
    assert report["clv_proxy"]["n_measurable_proxy"] == 3


def test_paper_ingame_verdict_falls_back_to_proxy_when_true_close_thin():
    rows = [_proxy_row("home", 2.0, 0.5, (1.0 if i % 2 == 0 else -1.0), "e%d" % i)
            for i in range(12)]
    report = reconcile_channel("paper_ingame", ledger=rows)
    assert report["n_measurable"] == 0
    assert report["clv_proxy"]["n_measurable_proxy"] == 12
    assert "PROXY" in report["verdict"]
    assert report["verdict"] == report["clv_proxy"]["verdict"]


def test_non_paper_ingame_channel_verdict_never_uses_proxy_fallback():
    # Even with plenty of proxy rows, only paper_ingame's TOP-LEVEL verdict
    # may fall back to the proxy tier.
    rows = [_proxy_row("home", 2.0, 0.5, 1.0, "e%d" % i, channel="paper_pm")
            for i in range(12)]
    report = reconcile_channel("paper_pm", ledger=rows)
    assert report["clv_proxy"]["n_measurable_proxy"] == 12
    assert report["verdict"].startswith("INSUFFICIENT_DATA")  # 0 true_close, not proxy-boosted
    assert "PROXY" not in report["verdict"]


def test_paper_ingame_verdict_stays_true_close_when_both_thin():
    rows = [_proxy_row("home", 2.0, 0.5, 1.0, "e1")]  # 1 proxy row -- below _MIN_N
    report = reconcile_channel("paper_ingame", ledger=rows)
    assert report["verdict"].startswith("INSUFFICIENT_DATA")
    assert "PROXY" not in report["verdict"]


def test_render_shows_proxy_block():
    from scripts.platformkit.clv.clv_result_reconciler import render
    rows = [_proxy_row("home", 2.0, 0.5, (1.0 if i % 2 == 0 else -1.0), "e%d" % i)
            for i in range(12)]
    txt = render(reconcile_channel("paper_ingame", ledger=rows))
    assert "PROXY" in txt
