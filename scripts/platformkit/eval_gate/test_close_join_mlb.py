"""S10 -- synthetic construct for the modern MLB close joiner (n = 40, CONSTRUCT)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate import close_join_mlb as mod

_TOK = {"ARI": "AZ", "CUB": "CHC", "KAN": "KC", "SDG": "SD", "SFO": "SF",
        "TAM": "TB", "WAS": "WSH", "OAK": "ATH"}
_PAIRS = [("ATL", "NYM"), ("BOS", "NYY"), ("CUB", "MIL"), ("ARI", "SDG"),
          ("SFO", "LAD"), ("TAM", "TOR"), ("KAN", "MIN"), ("WAS", "PHI")]


def _token(code: str) -> str:
    return _TOK.get(code, code)


def _build(n_ok: int = 30, n_post: int = 5, n_one: int = 3, n_none: int = 2):
    """40-game spine over two seasons + a price series with known drop reasons."""
    spine, ticks = [], []
    total = n_ok + n_post + n_one + n_none
    for i in range(total):
        home, away = _PAIRS[i % len(_PAIRS)]
        season = 2025 if i < total // 2 else 2026
        # Unique (season, day, pair) per game -> no doubleheader collision.
        date = pd.Timestamp(season, 4, 1) + pd.Timedelta(days=1 + i % 28)
        spine.append({"event_id": f"{date.date()}-{home}-{away}-1", "date": date,
                      "season": season, "home_team": home, "away_team": away,
                      "target_home_win": i % 2})
        start = date + pd.Timedelta(hours=23)  # 19:00 ET == 23:00 UTC
        key = (f"KXMLBGAME-{str(season)[2:]}{date.strftime('%b').upper()}"
               f"{date.day:02d}1900{_token(away)}{_token(home)}")
        if i < n_ok:
            offs, sides = [-600, -60], [(_token(home), 0.60), (_token(away), 0.44)]
        elif i < n_ok + n_post:
            offs, sides = [+600], [(_token(home), 0.60), (_token(away), 0.44)]
        elif i < n_ok + n_post + n_one:
            offs, sides = [-60], [(_token(home), 0.60)]
        else:
            offs, sides = [], []
        for off in offs:
            for side, prob in sides:
                ticks.append({
                    "sport": "mlb", "venue": "kalshi", "game_date": str(date.date()),
                    "ticker_or_slug": f"{key}-{side}", "event_key": key,
                    "market_type": "moneyline", "side": side,
                    "ts": int((start + pd.Timedelta(seconds=off)).timestamp()),
                    "prob": prob, "traded": None, "close_time": None,
                    "result_where_known": None})
    return pd.DataFrame(spine), pd.DataFrame(ticks)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    spine, ticks = _build()
    path = tmp_path_factory.mktemp("s10") / "series.parquet"
    ticks.to_parquet(path)
    return spine, path


def test_join_rate_is_exactly_30_of_40(built):
    spine, path = built
    report = mod.coverage_report_mlb(path, spine)
    assert report["spine_rows"] == 40
    assert report["joined_devig"] == 30
    assert report["join_rate"] == pytest.approx(30 / 40)


def test_drop_reasons_counted_exactly(built):
    spine, path = built
    close = mod.derive_modern_close(path, spine)
    drops = close.attrs
    assert drops["no_pre_start_quote"] == 5   # post-start ticks only
    assert drops["one_sided_proxy"] == 3      # one side present -> PROXY, not devigged
    assert len(close) == 33                   # 30 devig + 3 proxy
    # 2 games have no quote at all: they never enter the series, so the spine
    # accounts for them -- joins + every drop reason == the 40-row spine.
    assert 30 + drops["no_pre_start_quote"] + drops["one_sided_proxy"] + 2 == 40


def test_one_sided_rows_are_labelled_proxy(built):
    spine, path = built
    close = mod.derive_modern_close(path, spine)
    kinds = close["close_kind"].value_counts().to_dict()
    assert kinds == {"DEVIG_TWO_SIDED": 30, "PROXY_ONE_SIDED": 3}
    assert close.loc[close["close_kind"] == "PROXY_ONE_SIDED", "close_prob"].notna().all()


def test_per_season_denominators_sum_to_the_spine(built):
    spine, path = built
    report = mod.coverage_report_mlb(path, spine)
    seasons = report["by_season"]
    assert sum(s["denominator"] for s in seasons.values()) == 40
    assert sum(s["joined_devig"] for s in seasons.values()) == report["joined_devig"]


def test_last_pre_start_tick_wins_and_two_even_prices_devig_to_half(built):
    spine, path = built
    close = mod.derive_modern_close(path, spine)
    devig = close.loc[close["close_kind"] == "DEVIG_TWO_SIDED", "close_prob"]
    # 0.60 / 0.44 -> decimal 1.6667 / 2.2727, devigged home share 0.60/1.04.
    assert devig.round(6).eq(round(0.60 / 1.04, 6)).all()
    # A symmetric 2.00 / 2.00 pair must devig to exactly 0.5000.
    even = mod._devig(pd.DataFrame({"prob_home": [0.5], "prob_away": [0.5]}))
    assert float(even.iloc[0]) == pytest.approx(0.5, abs=1e-12)


def test_ambiguous_doubleheader_spine_keys_are_dropped_and_counted(built, tmp_path):
    spine, path = built
    dh = spine.iloc[[0]].copy()
    dh["event_id"] = dh["event_id"].str.replace("-1$", "-2", regex=True)
    close = mod.derive_modern_close(path, pd.concat([spine, dh], ignore_index=True))
    assert close.attrs["ambiguous_spine_key"] == 2
    assert len(close) == 32  # that one game can no longer be keyed
