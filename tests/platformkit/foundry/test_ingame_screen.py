"""S82 in-game screen tier: the tick-time as-of guard, the purge/embargo, the archived
differential and the no-ledger property. ASCII only.

Run: python -m pytest tests/platformkit/foundry/test_ingame_screen.py -q
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.foundry import ingame_screen as S

LEDGER = S.ROOT / "data" / "cache" / "eval_gate" / "backtest_fwer.jsonl"
_SUMMARY = ("home_score={h} away_score={a} inning=1 half=top outs=0 base=0 bos=0 re=0.481 "
            "count=0-1 pitch_count={p} tto=1")


def _src(n: int = 40) -> pd.DataFrame:
    """A causal tick source: two games interleaved, one row per (game, timestamp)."""
    rows = []
    for step in range(n):
        for game in ("G1", "G2"):
            rows.append({"game": game, "timestamp": "2026-01-05T%02d:%02d:00Z" % (step // 4, step % 4 * 15),
                         "state_summary": _SUMMARY.format(h=step % 3, a=step % 2, p=step),
                         "_row_id": len(rows)})
    return pd.DataFrame(rows).sort_values(["timestamp", "game"], kind="stable").reset_index(drop=True)


def test_asof_guard_passes_on_the_real_builder():
    checked = S.assert_tick_asof(_src(), S.build_features, probes=4)
    assert len(checked) == 4 and checked[0] > 0


def test_asof_guard_raises_on_a_feature_that_reads_a_later_tick():
    def leaky(src: pd.DataFrame) -> pd.DataFrame:
        out = S.build_features(src)
        out["peek"] = out["score_diff"].shift(-1)      # the NEXT tick's state
        return out

    with pytest.raises(S.TickTimeLeak) as excinfo:
        S.assert_tick_asof(_src(), leaky, probes=3)
    assert "peek" in str(excinfo.value)


def _rows(spec) -> pd.DataFrame:
    """(game, game_date, first hour, n ticks) -> the screen-row frame walk_forward wants."""
    rng, out = np.random.default_rng(7), []
    for game, date, hour, count in spec:
        for i in range(count):
            x = float(rng.normal())
            out.append({"game": game, "game_date": date,
                        "ts": "%sT%02d:%02d:%02dZ" % (date, hour + i // 3600, (i // 60) % 60, i % 60),
                        "y": float(rng.random() < 1.0 / (1.0 + np.exp(-x))),
                        "p_e4": 0.5, "market": 0.5, "x": x})
    return pd.DataFrame(out)


def test_purge_and_embargo_drop_a_game_still_ticking_during_the_fold():
    # G_LATE opens on 01-05 like G_EARLY but keeps ticking into 01-07: the settlement purge
    # must drop it, while the game-first-date rule alone would have kept it in the train set.
    rows = _rows([("G_EARLY", "2026-01-05", 0, 1200), ("G_LATE", "2026-01-05", 0, 60),
                  ("G_TEST", "2026-01-07", 0, 300)])
    rows.loc[rows["game"] == "G_LATE", "ts"] = ["2026-01-07T00:%02d:00Z" % i for i in range(60)]
    candidate, null, folds = S.walk_forward_feature(rows, "x")
    scored = [f for f in folds if f["status"] == "OK"]
    assert len(scored) == 1 and scored[0]["date"] == "2026-01-07"
    assert scored[0]["n_train"] == 1200 and scored[0]["n_train_games"] == 1
    assert candidate.notna().sum() == 300 and null.notna().sum() == 300
    assert candidate[rows["game"] != "G_TEST"].isna().all()


def test_no_train_fold_is_recorded_not_scored():
    rows = _rows([("G_A", "2026-01-05", 0, 50), ("G_B", "2026-01-06", 0, 50)])
    candidate, _, folds = S.walk_forward_feature(rows, "x")
    assert [f["status"] for f in folds] == ["NO_TRAIN"] and candidate.isna().all()


def _corpus():
    """Two ISO weeks so partition_corpus has both sides; week 1 is the screen side."""
    spec = [("G1", "2026-01-05", 0, 1200), ("G2A", "2026-01-07", 0, 150),
            ("G2B", "2026-01-07", 4, 150), ("G3", "2026-01-12", 0, 120),
            ("G4", "2026-01-13", 0, 120)]
    rows = _rows(spec)
    ticks = [{"_row_id": i, "game": r.game, "timestamp": r.ts, "outcome": r.y,
              "market_prob": r.market, "state_summary": None}
             for i, r in enumerate(rows.itertuples(index=False))]
    table = pd.DataFrame({"_row_id": range(len(rows)), "game": rows["game"], "timestamp": rows["ts"],
                          "x": rows["x"]})
    first = rows.groupby("game")["game_date"].min().to_dict()
    return ticks, [0.5] * len(rows), table, first


def test_paired_loss_series_length_equals_the_scored_screen_ticks(tmp_path):
    ticks, e4, table, first = _corpus()
    csv = tmp_path / "series.csv"
    report = S.run(ticks, e4, table, first, out_json=tmp_path / "r.json", out_csv=csv,
                   features={"member": "x"})
    assert report["partition"]["basis"] == "iso_week"
    assert report["partition"]["n_screen_games"] == 3
    row = report["results"][0]
    assert row["status"] == "SCREENED" and row["n_ticks"] == 300 and row["n_games"] == 2
    series = pd.read_csv(csv)
    assert len(series) == row["n_ticks"] == int((series["feature"] == "x").sum())
    assert set(series.columns) >= {"p_e4", "p_null", "p_candidate", "market", "y", "game"}
    # Q9: the summary is recomputable from the archived differential alone.
    loss = lambda p: float(((series[p] - series["y"]) ** 2).mean())   # noqa: E731
    assert loss("p_candidate") == pytest.approx(row["brier_candidate"], abs=1e-12)
    assert loss("p_null") - loss("p_candidate") == pytest.approx(row["improvement_vs_null"], abs=1e-12)


def test_the_screen_touches_no_ledger_and_no_prereg(tmp_path):
    body = Path(S.__file__).read_text(encoding="ascii").split('"""', 2)[2]   # past the docstring
    for banned in ("_charge_ledger", "backtest_runner", "backtest_fwer", "charge_tier",
                   "prereg_sha256", "PREREG"):
        assert banned not in body, "the screen tier must never reach the FWER ledger"
    before = LEDGER.read_bytes() if LEDGER.exists() else None
    ticks, e4, table, first = _corpus()
    S.run(ticks, e4, table, first, out_json=tmp_path / "r.json", features={"member": "x"})
    assert (LEDGER.read_bytes() if LEDGER.exists() else None) == before


def test_the_embargo_holds_in_every_timestamp_spelling():
    """S125: the purge compared stamp STRINGS to a strftime'd cut, and ' ' (0x20) sorts before
    'T', so a space-separated spelling admitted a train game that settled 2 h before the fold
    (n_train 8 where 0 is correct) -- and BOTH asserts passed because they shared the order."""
    train_ts = [pd.Timestamp("2026-07-05T21:00:00") + pd.Timedelta(minutes=15 * i) for i in range(8)]
    test_ts = [pd.Timestamp("2026-07-06T01:00:00") + pd.Timedelta(minutes=15 * i) for i in range(8)]
    rng = np.random.default_rng(0)

    def _frame(fmt):
        return pd.DataFrame([
            {"game": game, "ts": fmt(stamp), "game_date": date, "y": float(rng.integers(0, 2)),
             "p_e4": 0.5, "market": 0.5, "x": float(rng.normal())}
            for game, stamps, date in (("TRAIN", train_ts, "2026-07-05"),
                                       ("TEST", test_ts, "2026-07-06"))
            for stamp in stamps])

    for fmt in (lambda s: s.strftime("%Y-%m-%dT%H:%M:%SZ"), str, lambda s: s.isoformat()):
        fold = S.walk_forward_feature(_frame(fmt), "x")[2][0]
        assert (fold["status"], fold["n_train"]) == ("NO_TRAIN", 0), fold
        assert fold["cut"] == "2026-07-05T01:00:00Z", fold
