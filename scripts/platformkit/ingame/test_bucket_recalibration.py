"""Per-file tests for bucket_recalibration.py -- MLB walk-forward state-bucket
recalibration. OFFLINE + deterministic: grade files written to tmp_path,
outcome resolver injected via MlbOutcomeResolver(box_df=...) (no parquet, no
network). Mirrors test_state_bucket_benchmark.py's fixtures.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_bucket_recalibration.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

import scripts.platformkit.ingame.bucket_recalibration as br
from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver


def _ts(day: int, i: int) -> str:
    return (datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
           + timedelta(days=day, seconds=30 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ticker(day: int, n: int) -> str:
    # Same (date, away, home) key repeats across n slots -> tag each as a doubleheader
    # game (G1, G2, ...) so the resolver's ambiguous-doubleheader guard doesn't drop it.
    return "KXMLBGAME-26JUN%02d1200NYYBOSG%d" % (1 + day, n + 1)


def _write_game(grade_dir: Path, gid: str, day: int, rows: list) -> None:
    p = grade_dir / "mlb" / ("%s.jsonl" % gid)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for i, (model_p, market_p, home_score, away_score, inning) in enumerate(rows):
            fh.write(json.dumps({
                "sport": "mlb", "game_id": gid, "ts": _ts(day, i), "side": "home",
                "model_prob": model_p, "market_prob": market_p,
                "state_summary": "home_score=%s away_score=%s inning=%s half=top" % (
                    home_score, away_score, inning),
            }) + "\n")


def _box_df(n_days: int, games_per_day: int, home_win: bool = True) -> pd.DataFrame:
    rows = []
    for day in range(n_days):
        for n in range(games_per_day):
            rows.append({
                "event_id": "%d%d" % (day, n), "home_abbr": "BOS", "away_abbr": "NYY",
                "home_score": 5 if home_win else 2, "away_score": 2 if home_win else 5,
                "status": "STATUS_FINAL", "date": "2026-06-%02d" % (1 + day),
                "start_time": "2026-06-%02dT%02d:00:00Z" % (1 + day, 12 + n),  # G1 < G2 < ...
            })
    return pd.DataFrame(rows)


def _make_corpus(tmp_path: Path, n_days: int = 20, games_per_day: int = 3):
    """n_days*games_per_day resolvable games; model overconfident by phase/margin
    (systematic bias a Platt fit can actually correct), market == truth-leaning 0.65."""
    grade_dir = tmp_path / "ingame_grade"
    for day in range(n_days):
        for n in range(games_per_day):
            gid = _ticker(day, n)
            rows = [(0.95, 0.65, 5.0, 0.0, 8)] * 15  # late|leading_big, home truly wins
            _write_game(grade_dir, gid, day, rows)
    resolver = MlbOutcomeResolver(box_df=_box_df(n_days, games_per_day, home_win=True))
    return grade_dir, resolver


# --------------------------------------------------------------------------------------- #
def test_load_recal_ticks_has_date_phase_margin(tmp_path: Path) -> None:
    grade_dir, resolver = _make_corpus(tmp_path, n_days=5, games_per_day=2)
    ticks = br.load_recal_ticks(grade_dir, resolver)
    assert len(ticks) == 5 * 2 * 15
    assert all(t["phase"] == "late" and t["margin"] == 5.0 for t in ticks)
    assert len(set(t["date"] for t in ticks)) == 5


def test_walk_forward_never_uses_same_date_or_future_games() -> None:
    """Fake fit_fn/apply_fn record the max date seen in their training window; assert
    it is always strictly less than the date being evaluated (the leak-free contract)."""
    ticks = []
    for day in range(10):
        d = "2026-06-%02d" % (1 + day)
        for n in range(20):
            ticks.append({"game_id": "g%d_%d" % (day, n), "date": d, "phase": "late",
                          "margin": 3.0, "model_prob": 0.8, "market_prob": 0.6, "outcome": 1.0})
    seen_max_train_date = []

    def fake_fit(train):
        seen_max_train_date.append(max((t["date"] for t in train), default=None))
        return None

    def fake_apply(tick, model):
        return tick["model_prob"]

    br.SPECS["_test_spec"] = (fake_fit, fake_apply)
    try:
        out, burn_dates = br.walk_forward_recal(ticks, "_test_spec")
    finally:
        del br.SPECS["_test_spec"]

    eval_dates = sorted(set(t["date"] for t in out if not t["in_burn_in"]))
    assert len(eval_dates) == len(seen_max_train_date)
    for d, max_train_date in zip(eval_dates, seen_max_train_date):
        if max_train_date is not None:
            assert max_train_date < d  # never same-date or future


def test_recalibrated_probs_stay_in_zero_one(tmp_path: Path) -> None:
    grade_dir, resolver = _make_corpus(tmp_path, n_days=20, games_per_day=3)
    doc = br.build_recalibration(grade_dir, resolver, benchmark_generated_at="2026-01-01T00:00:00Z")
    for bucket in doc["buckets"]:
        for m in (bucket["raw"], bucket["recal"], bucket["market"]):
            if m is not None:
                assert 0.0 <= m["brier"] <= 1.0  # brier bounded => probs were in [0,1]
    assert doc["winner"] in br.SPECS
    assert doc["edge_claimed"] is False


def test_burn_in_is_raw_passthrough_and_excluded(tmp_path: Path) -> None:
    grade_dir, resolver = _make_corpus(tmp_path, n_days=10, games_per_day=2)
    ticks = br.load_recal_ticks(grade_dir, resolver)
    out, burn_dates = br.walk_forward_recal(ticks, "phase_platt")
    all_dates = sorted(set(t["date"] for t in ticks))
    assert len(burn_dates) == max(1, -(-len(all_dates) * 20 // 100))  # ceil(20%)
    burn_ticks = [t for t in out if t["in_burn_in"]]
    eval_ticks = [t for t in out if not t["in_burn_in"]]
    assert burn_ticks and eval_ticks
    assert all(t["date"] in burn_dates for t in burn_ticks)
    assert all(t["date"] not in burn_dates for t in eval_ticks)
    # burn-in rows are raw passthrough: recal_prob == model_prob exactly
    assert all(t["recal_prob"] == t["model_prob"] for t in burn_ticks)


def test_write_recalibration_output_shape(tmp_path: Path) -> None:
    grade_dir, resolver = _make_corpus(tmp_path, n_days=20, games_per_day=3)
    bench_path = tmp_path / "bench.json"
    bench_path.write_text(json.dumps({"generated_at": "2026-06-30T00:00:00Z"}), encoding="utf-8")
    out_path = tmp_path / "out" / "mlb_bucket_recalibration.json"
    params_path = tmp_path / "out" / "mlb_bucket_recalib_params.json"
    history_path = tmp_path / "out" / "scoreboard_history.jsonl"
    doc = br.write_recalibration(out_path, params_path, grade_dir, resolver,
                                 history_path=history_path, benchmark_path=bench_path)
    assert out_path.is_file()
    assert history_path.is_file()  # never touches the real data/cache history
    reloaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert reloaded["generated_at"] == "2026-06-30T00:00:00Z"  # from benchmark, not now()
    assert reloaded["sport"] == "mlb"
    assert reloaded["edge_claimed"] is False
    assert reloaded["calibration_scoreboard"]["per_sport"][0]["sport"] == "mlb"
    assert doc["params_path"] == (str(params_path) if doc["params_written"] else None)
    if doc["params_written"]:
        assert params_path.is_file()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
