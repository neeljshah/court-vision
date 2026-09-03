"""S112 -- per-file test for the nba/mlb close attach (synthetic CONSTRUCT fixtures).

Covers the four rules the memo states: the two-sided devig, the nba first-tick rule (with the
within-30-s-of-tip flag), the placeholder-0.500 exclusion, and strictly-pregame for mlb.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from kernel.validation.proof_metrics import devig2
from scripts.platformkit.eval_gate import close_join_nba_mlb as mod
from scripts.platformkit.eval_gate import s108_pregame_full_model as s108
from scripts.platformkit.eval_gate import s112_rescore_vs_close as rescore

_TOK = {"ARI": "AZ", "CUB": "CHC", "KAN": "KC", "SDG": "SD", "SFO": "SF",
        "TAM": "TB", "WAS": "WSH", "OAK": "ATH"}
_PAIRS = [("ATL", "NYM"), ("BOS", "NYY"), ("CUB", "MIL"), ("ARI", "SDG"),
          ("SFO", "LAD"), ("TAM", "TOR"), ("KAN", "MIN"), ("WAS", "PHI")]
# kind -> (offsets from first pitch in seconds, [(seat, prob, traded)])
_HOME_P, _AWAY_P = 0.60, 0.44


def _mlb_fixture(tmp_path):
    """8 games, one per rule: ok / post-start-only / untraded-later / placeholder / one-sided."""
    kinds = ["ok", "ok", "post_start_only", "untraded_later", "placeholder", "one_sided",
             "ok", "pickem"]
    spine, ticks = [], []
    for i, kind in enumerate(kinds):
        home, away = _PAIRS[i]
        date = pd.Timestamp(2026, 4, 1) + pd.Timedelta(days=1 + i)
        spine.append({"event_id": "%s-%s-%s-1" % (date.date(), home, away), "date": date,
                      "season": 2026, "home_team": home, "away_team": away,
                      "target_home_win": i % 2})
        start = date + pd.Timedelta(hours=23)      # 19:00 ET == 23:00 UTC
        key = ("KXMLBGAME-26%s%02d1900%s%s"
               % (date.strftime("%b").upper(), date.day,
                  _TOK.get(away, away), _TOK.get(home, home)))
        plan = {
            # (offset seconds, seat prob home, seat prob away, traded)
            "ok": [(-600, _HOME_P, _AWAY_P, True), (-60, _HOME_P, _AWAY_P, True)],
            "post_start_only": [(+600, _HOME_P, _AWAY_P, True)],
            "untraded_later": [(-600, _HOME_P, _AWAY_P, True), (-60, 0.99, 0.99, False)],
            "placeholder": [(-60, 0.5, 0.5, True)],
            "one_sided": [(-60, _HOME_P, None, True)],
            # S133: symmetric RAW quote -> devigs to exactly 0.500, a genuine pick'em
            "pickem": [(-60, 0.52, 0.52, True)],
        }[kind]
        for off, ph, pa, traded in plan:
            for seat, prob in (("home", ph), ("away", pa)):
                if prob is None:
                    continue
                token = _TOK.get(home if seat == "home" else away,
                                 home if seat == "home" else away)
                ticks.append({
                    "sport": "mlb", "venue": "kalshi", "game_date": str(date.date()),
                    "ticker_or_slug": "%s-%s" % (key, token), "event_key": key,
                    "market_type": "moneyline", "side": token,
                    "ts": int((start + pd.Timedelta(seconds=off)).timestamp()),
                    "prob": prob, "traded": traded, "close_time": None,
                    "result_where_known": None})
    path = tmp_path / "series.parquet"
    pd.DataFrame(ticks).to_parquet(path)
    return pd.DataFrame(spine), path


@pytest.fixture(scope="module")
def mlb_built(tmp_path_factory):
    return _mlb_fixture(tmp_path_factory.mktemp("s112_mlb"))


def test_mlb_close_is_the_two_sided_devig(mlb_built):
    """One devig through close_join.close_column, never the raw venue probability."""
    spine, path = mlb_built
    drops = mod._drops()
    close = mod.mlb_close(path, spine, drops)
    expected = devig2(1.0 / _HOME_P, 1.0 / _AWAY_P)[0]
    priced = close.loc[~close["event_id"].str.contains("WAS")]     # not the pick'em game
    assert set(close["close_kind"]) == {"DEVIG_TWO_SIDED"}
    assert priced["p_close"].to_numpy(dtype=float) == pytest.approx(expected)
    assert expected != pytest.approx(_HOME_P)          # the vig really was removed


def test_mlb_close_is_strictly_pregame_and_traded(mlb_built):
    """A post-first-pitch tick never becomes a close, and an untraded later tick never wins."""
    spine, path = mlb_built
    drops = mod._drops()
    close = mod.mlb_close(path, spine, drops).set_index("event_id")
    ids = list(close.index)
    assert not any("CUB" in i for i in ids)            # post_start_only game: no close at all
    assert all(np.asarray(close["close_sec_after_tip"], dtype=float) < 0.0)
    untraded = [i for i in ids if "ARI" in i]          # untraded_later game
    assert len([i for i in ids if "WAS" in i]) == 1     # S133: the pick'em survived
    assert len(untraded) == 1
    # The 0.99/0.99 untraded tick at -60 s would devig to 0.5; the traded -600 s tick wins.
    assert float(close.loc[untraded[0], "p_close"]) == pytest.approx(
        devig2(1.0 / _HOME_P, 1.0 / _AWAY_P)[0])


def test_mlb_placeholder_half_excluded_and_counted(mlb_built):
    spine, path = mlb_built
    drops = mod._drops()
    close = mod.mlb_close(path, spine, drops)
    assert drops["placeholder_half"] == 1              # the RAW 0.5/0.5 listing only
    assert len(close) == 5                             # 8 - post_start - placeholder - one_sided
    # S133: the placeholder rule runs on the RAW quote, so a devigged 0.500 SURVIVES.
    pickem = close.loc[close["event_id"].str.contains("WAS"), "p_close"]
    assert float(pickem.iloc[0]) == pytest.approx(mod.PLACEHOLDER_PROB)


def _nba_ticks(rows):
    return pd.DataFrame([{
        "game_id": g, "game_date": "2024-11-0%d" % (1 + i % 8), "ts": ts, "period": period,
        "game_clock_s": clock, "score_home": 0, "score_away": 0, "margin": 0,
        "market_prob": prob, "traded": traded, "market_ticker": "nba-nyk-bos-2024-11-01",
        "outcome_home_win": 1, "venue": "polymarket"}
        for i, (g, ts, period, clock, prob, traded) in enumerate(rows)])


@pytest.fixture
def nba_patched(monkeypatch, tmp_path):
    """Crosswalk stubbed: this test owns the first-tick rule, not the identity bridge."""
    from scripts.platformkit.ingame import nba_mechanism_ladder

    def _crosswalk(frame):
        ids = sorted(set(frame["game_id"].astype(str)))
        return pd.DataFrame({"game_id": ids, "nba_game_id": ["00224000%02d" % i
                                                             for i in range(len(ids))]})
    monkeypatch.setattr(nba_mechanism_ladder, "build_crosswalk", _crosswalk)
    return tmp_path


def test_nba_first_tick_is_the_earliest_traded_tick(nba_patched):
    """Earliest ts per game wins; seconds-after-tip = 720 - game_clock_s."""
    path = nba_patched / "ck.parquet"
    _nba_ticks([("a", 200, 1, 699.0, 0.62, True),      # later
                ("a", 100, 1, 714.0, 0.55, True),      # EARLIEST -> the close
                ("b", 100, 1, 690.0, 0.33, True),      # exactly 30 s after tip
                ("c", 100, 1, 660.0, 0.71, True)]).to_parquet(path)
    drops = mod._drops()
    out = mod.nba_first_inplay_tick(path, drops).set_index("event_id")
    assert len(out) == 3
    first = out.loc["0022400000"]
    assert float(first["p_close"]) == pytest.approx(0.55)
    assert float(first["close_sec_after_tip"]) == pytest.approx(6.0)
    assert bool(first["close_within_30s"]) is True
    assert bool(out.loc["0022400001", "close_within_30s"]) is True     # 30 s is inside
    assert bool(out.loc["0022400002", "close_within_30s"]) is False    # 60 s is not
    # S132: 60 s of live play after tip is not a close -- labelled, and priceless.
    assert set(out["close_source"]) == {"first_inplay_tick", "inplay_contaminated"}
    assert out.loc["0022400002", "close_source"] == "inplay_contaminated"
    assert np.isnan(float(out.loc["0022400002", "p_close"]))
    assert set(out["close_kind"]) == {"VENUE_PROB_ONE_SIDED"}


def test_nba_untraded_and_non_period_1_and_placeholder_dropped(nba_patched):
    path = nba_patched / "ck.parquet"
    _nba_ticks([("a", 50, 1, 700.0, 0.61, False),      # untraded, ignored -> b's tick is first
                ("a", 100, 1, 690.0, 0.61, True),
                ("b", 100, 2, 700.0, 0.44, True),      # first traded tick is period 2 -> dropped
                ("c", 100, 1, 700.0, 0.50, True)]).to_parquet(path)
    drops = mod._drops()
    out = mod.nba_first_inplay_tick(path, drops)
    assert drops["first_tick_not_period_1"] == 1
    assert drops["placeholder_half"] == 1
    assert len(out) == 1
    assert float(out["p_close"].iloc[0]) == pytest.approx(0.61)


def test_nba_pregame_close_outranks_the_in_play_tick(nba_patched, monkeypatch):
    """A real pregame close beats a first-in-play tick for the same event_id."""
    pregame = nba_patched / "pre.parquet"
    pd.DataFrame([
        {"game_id": "0022400000", "date": "2024-11-01", "home_team": "NYK", "away_team": "BOS",
         "home_win": 1.0, "venue": "polymarket", "corpus_id": "x",
         "close_kind": "last_tick_before_commence", "close_ts": "2024-11-01T23:59:36Z",
         "close_prob_home": 0.42, "commence_time": "2024-11-02T00:00:00Z",
         "seconds_before_tip": 24.0, "validation_only": True},
        {"game_id": "0022400009", "date": "2024-11-02", "home_team": "NYK", "away_team": "BOS",
         "home_win": 0.0, "venue": "polymarket", "corpus_id": "x",
         "close_kind": "last_tick_before_commence", "close_ts": "2024-11-02T23:59:36Z",
         "close_prob_home": 0.50, "commence_time": "2024-11-03T00:00:00Z",
         "seconds_before_tip": 24.0, "validation_only": True},
    ]).to_parquet(pregame)
    ticks = nba_patched / "ck.parquet"
    _nba_ticks([("a", 100, 1, 700.0, 0.61, True)]).to_parquet(ticks)
    monkeypatch.setattr(mod, "NBA_PREGAME_CLOSE", pregame)
    monkeypatch.setattr(mod, "CHECKPOINTS", ticks)
    drops = mod._drops()
    out = mod.nba_close(drops).set_index("event_id")
    assert drops["placeholder_half"] == 1                      # the 0.50 pregame row
    assert float(out.loc["0022400000", "p_close"]) == pytest.approx(0.42)
    assert out.loc["0022400000", "close_source"] == "pregame_last_tick_before_commence"
    assert float(out.loc["0022400000", "close_sec_after_tip"]) == pytest.approx(-24.0)


def test_bar_is_not_moved():
    """Q3: the re-score reads S108's bar; it is never redefined here."""
    assert rescore.IMPROVEMENT_BAR == s108.IMPROVEMENT_BAR == 0.004
    assert rescore.OUTER_FOLDS_BY_SPORT["nba"] == s108.OUTER_FOLDS


def test_close_columns_are_additive_only():
    """B2: the attach appends, it never renames or drops a live-corpus column."""
    assert mod.CLOSE_COLUMNS == ("p_close", "close_ts", "close_source", "close_kind",
                                 "close_sec_after_tip", "close_within_30s",
                                 "close_score_on_board")
    assert mod.close_corpus_path("nba").name == "gate_corpus_nba_close.parquet"
    assert mod.close_corpus_path("nba") != mod.close_corpus_path("mlb")


def test_nba_tick_with_points_on_the_board_is_not_a_close(nba_patched):
    """S132: a tick inside the 30 s window but with a score already up is contaminated."""
    path = nba_patched / "ck.parquet"
    ticks = _nba_ticks([("a", 100, 1, 700.0, 0.61, True),      # 20 s, 0-0  -> a real close
                        ("b", 100, 1, 700.0, 0.44, True),      # 20 s, 2-0  -> contaminated
                        ("c", 100, 1, 700.0, 0.55, True)])     # 20 s, 2-2  -> contaminated
    ticks.loc[1, ["score_home", "score_away", "margin"]] = [2, 0, 2]
    ticks.loc[2, ["score_home", "score_away", "margin"]] = [2, 2, 0]
    ticks.to_parquet(path)
    drops = mod._drops()
    out = mod.nba_first_inplay_tick(path, drops).set_index("event_id")
    assert drops["inplay_contaminated"] == 2
    assert float(out.loc["0022400000", "p_close"]) == pytest.approx(0.61)
    assert float(out.loc["0022400000", "close_score_on_board"]) == 0.0
    for event in ("0022400001", "0022400002"):     # margin != 0 AND a 2-2 tie both fail
        assert out.loc[event, "close_source"] == "inplay_contaminated"
        assert np.isnan(float(out.loc[event, "p_close"]))

    # allow_contaminated reproduces the pre-S132 behaviour, for an A2 comparison only.
    old = mod.nba_first_inplay_tick(path, mod._drops(), allow_contaminated=True)
    assert set(old["close_source"]) == {"first_inplay_tick"}
    assert int(old["p_close"].notna().sum()) == 3


def test_nba_ambiguous_pregame_close_does_not_downgrade_to_the_tick(nba_patched, monkeypatch):
    """S133: two venue rows for one game -> one priceless `ambiguous` row, never the tick."""
    pregame = nba_patched / "pre.parquet"
    row = {"date": "2024-11-01", "home_team": "NYK", "away_team": "BOS", "home_win": 1.0,
           "venue": "polymarket", "corpus_id": "x", "close_kind": "last_tick_before_commence",
           "close_ts": "2024-11-01T23:59:36Z", "commence_time": "2024-11-02T00:00:00Z",
           "seconds_before_tip": 24.0, "validation_only": True}
    pd.DataFrame([dict(row, game_id="0022400000", close_prob_home=0.42),
                  dict(row, game_id="0022400000", close_prob_home=0.70)]).to_parquet(pregame)
    ticks = nba_patched / "ck.parquet"
    _nba_ticks([("a", 100, 1, 700.0, 0.61, True)]).to_parquet(ticks)
    monkeypatch.setattr(mod, "NBA_PREGAME_CLOSE", pregame)
    monkeypatch.setattr(mod, "CHECKPOINTS", ticks)
    drops = mod._drops()
    out = mod.nba_close(drops).set_index("event_id")
    assert drops["ambiguous_event_id"] == 2
    assert out.loc["0022400000", "close_source"] == "ambiguous"
    assert np.isnan(float(out.loc["0022400000", "p_close"]))
