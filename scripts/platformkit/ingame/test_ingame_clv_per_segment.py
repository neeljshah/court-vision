"""Per-file test for ingame_clv_per_segment.

Acceptance criteria (from workstream BE-R5-6):
  1. Synthetic Q1..Q4 pairs -> per-segment CLV recovered for segments meeting min thresholds.
  2. Under-min segment (fewer than min_games or min_ticks) -> verdict = INSUFFICIENT_DATA.
  3. Empty corpus (no files) -> all segments are INSUFFICIENT_DATA.
  4. No $ key, units/CLV-prob only: no 'roi'/'pnl'/'profit'/'edge' field anywhere.
  5. Segment label parser covers NBA periods (1..4, OT), baseball innings, soccer halves.
  6. Game with <2 ticks in a segment contributes 0 scored ticks (close excluded).

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_clv_per_segment.py -q
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import List

import pytest

from scripts.platformkit.ingame.ingame_clv_per_segment import (
    aggregate_by_segment,
    format_report,
    _infer_segment,
    _clv_for_rows,
    _verdict_for_seg,
    MIN_GAMES_PER_SEG,
    MIN_TICKS_PER_SEG,
    EPS_DEFAULT,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _make_row(
    sport: str,
    game_id: str,
    ts: str,
    market_prob: float,
    model_prob: float,
    period: int,
) -> dict:
    return {
        "sport": sport,
        "game_id": game_id,
        "ts": ts,
        "market_prob": market_prob,
        "model_prob": model_prob,
        "side": "home",
        "state_summary": "period=%d clock=08:00 home_score=10 away_score=8" % period,
    }


def _write_game(tmp_dir: Path, sport: str, game_id: str, rows: List[dict]) -> Path:
    """Write a fake grade file and return its path."""
    sub = tmp_dir / sport
    sub.mkdir(parents=True, exist_ok=True)
    p = sub / ("%s.jsonl" % game_id)
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=True) + "\n")
    return p


def _no_money_keys(d: dict, path: str = "") -> List[str]:
    """Recursively find any forbidden money-related key."""
    bad: List[str] = []
    forbidden = {"roi", "pnl", "profit", "stake", "bankroll", "dollar",
                 "edge_value", "expected_value_dollar"}
    for k, v in d.items():
        full = path + "." + k if path else k
        if k.lower() in forbidden or "$" in k:
            bad.append(full)
        if isinstance(v, dict):
            bad.extend(_no_money_keys(v, full))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    bad.extend(_no_money_keys(item, "%s[%d]" % (full, i)))
    return bad


# ---------------------------------------------------------------------------
# 1. Segment label parser
# ---------------------------------------------------------------------------
class TestInferSegment:
    def test_nba_periods(self):
        for p, expected in [(1, "Q1"), (2, "Q2"), (3, "Q3"), (4, "Q4"), (5, "QOT")]:
            assert _infer_segment("nba", "period=%d clock=05:00" % p) == expected

    def test_nba_period_zero_is_unk(self):
        assert _infer_segment("nba", "period=0") == "UNK"

    def test_mlb_innings(self):
        for inn, expected in [(1, "I1"), (5, "I5"), (9, "I9"), (12, "I9")]:
            ss = "inning=%d half=top home_score=3 away_score=1" % inn
            assert _infer_segment("mlb", ss) == expected, "inning=%d" % inn

    def test_soccer_minute(self):
        assert _infer_segment("soccer", "minute=30") == "H1"
        assert _infer_segment("soccer", "minute=60") == "H2"
        assert _infer_segment("soccer", "minute=45") == "H1"  # boundary included in H1

    def test_soccer_half_explicit(self):
        assert _infer_segment("soccer", "half=1") == "H1"
        assert _infer_segment("soccer", "half=2") == "H2"

    def test_empty_state_is_unk(self):
        assert _infer_segment("nba", "") == "UNK"

    def test_unknown_keys_is_unk(self):
        assert _infer_segment("generic", "foo=bar baz=qux") == "UNK"


# ---------------------------------------------------------------------------
# 2. Per-game CLV within a segment (close excluded)
# ---------------------------------------------------------------------------
class TestClvForRows:
    def _row(self, mkt: float, mdl: float) -> dict:
        return {"market_prob": mkt, "model_prob": mdl}

    def test_close_excluded(self):
        # 3 rows: scored = first 2, close = last 1 excluded
        rows = [self._row(0.45, 0.50), self._row(0.46, 0.51), self._row(0.50, 0.50)]
        mean_clv, n = _clv_for_rows(rows)
        assert n == 2
        # expected = mean([0.05, 0.05]) = 0.05
        assert abs(mean_clv - 0.05) < 1e-9

    def test_single_row_returns_zero_ticks(self):
        rows = [self._row(0.5, 0.55)]
        mean_clv, n = _clv_for_rows(rows)
        assert n == 0
        assert mean_clv == 0.0

    def test_empty_rows(self):
        mean_clv, n = _clv_for_rows([])
        assert n == 0
        assert mean_clv == 0.0

    def test_negative_clv(self):
        rows = [self._row(0.55, 0.45), self._row(0.55, 0.46), self._row(0.56, 0.50)]
        mean_clv, n = _clv_for_rows(rows)
        assert n == 2
        assert mean_clv < 0.0


# ---------------------------------------------------------------------------
# 3. Verdict logic per segment
# ---------------------------------------------------------------------------
class TestVerdictForSeg:
    def test_insufficient_below_min_games(self):
        # 2 games but min_games=3 -> INSUFFICIENT_DATA
        v, *_ = _verdict_for_seg([0.02, 0.03], 20, 2, min_games=3, min_ticks=5)
        assert v == "INSUFFICIENT_DATA"

    def test_insufficient_below_min_ticks(self):
        v, *_ = _verdict_for_seg([0.02, 0.03, 0.04], 8, 3, min_games=3, min_ticks=10)
        assert v == "INSUFFICIENT_DATA"

    def test_beat_with_enough_data(self):
        # 5 games, all positive CLV well above eps -> BEAT
        clvs = [0.03] * 5
        v, pooled, ci_lo, ci_hi = _verdict_for_seg(
            clvs, 50, 5, eps=0.005, min_games=3, min_ticks=10
        )
        assert v == "BEAT"
        assert pooled > 0
        assert ci_lo > 0.0

    def test_behind(self):
        clvs = [-0.03] * 5
        v, pooled, *_ = _verdict_for_seg(
            clvs, 50, 5, eps=0.005, min_games=3, min_ticks=10
        )
        assert v == "BEHIND"
        assert pooled < 0

    def test_match_near_zero(self):
        clvs = [0.001] * 5
        v, *_ = _verdict_for_seg(clvs, 50, 5, eps=0.005, min_games=3, min_ticks=10)
        assert v == "MATCH"


# ---------------------------------------------------------------------------
# 4. Empty corpus -> all INSUFFICIENT_DATA
# ---------------------------------------------------------------------------
class TestEmptyCorpus:
    def test_no_files(self, tmp_path: Path):
        result = aggregate_by_segment(grade_dir=tmp_path)
        segs = result["segments"]
        # All segments that appear must be INSUFFICIENT_DATA
        for label, s in segs.items():
            assert s["verdict"] == "INSUFFICIENT_DATA", "seg=%s should be INSUFFICIENT_DATA" % label

    def test_no_dollar_keys_empty(self, tmp_path: Path):
        result = aggregate_by_segment(grade_dir=tmp_path)
        bad = _no_money_keys(result)
        assert bad == [], "Forbidden money keys found: %s" % bad

    def test_edge_claimed_false_empty(self, tmp_path: Path):
        result = aggregate_by_segment(grade_dir=tmp_path)
        assert result["edge_claimed"] is False
        for s in result["segments"].values():
            assert s["edge_claimed"] is False


# ---------------------------------------------------------------------------
# 5. Synthetic Q1..Q4 pairs -> per-segment CLV recovered
# ---------------------------------------------------------------------------
class TestSyntheticQuarters:
    """Build synthetic grade files with known, distinct CLV per quarter."""

    @staticmethod
    def _build_corpus(tmp_path: Path, n_games: int = 4, ticks_per_q: int = 5) -> Path:
        """
        Plant:
          Q1: model leads market by +0.04 per tick  -> positive CLV
          Q2: model lags market by -0.04 per tick   -> negative CLV
          Q3: model == market                        -> zero CLV
          Q4: positive CLV same as Q1
        Each game contributes ticks_per_q ticks per quarter.
        The last tick in each quarter set is the within-segment close proxy (excluded).
        To guarantee enough data: n_games * (ticks_per_q - 1) scored ticks per segment.
        """
        grade_dir = tmp_path / "grade"
        for i in range(n_games):
            rows = []
            ts_base = "2026-06-0%dT%02d:00:00Z" % (i + 1, 10)
            # Q1: positive CLV
            for t in range(ticks_per_q):
                rows.append(_make_row("nba", "game_%d" % i,
                                      "2026-06-0%dT10:%02d:00Z" % (i + 1, t),
                                      0.45, 0.49, period=1))
            # Q2: negative CLV
            for t in range(ticks_per_q):
                rows.append(_make_row("nba", "game_%d" % i,
                                      "2026-06-0%dT11:%02d:00Z" % (i + 1, t),
                                      0.50, 0.46, period=2))
            # Q3: zero CLV (model == market)
            for t in range(ticks_per_q):
                rows.append(_make_row("nba", "game_%d" % i,
                                      "2026-06-0%dT12:%02d:00Z" % (i + 1, t),
                                      0.50, 0.50, period=3))
            # Q4: positive CLV
            for t in range(ticks_per_q):
                rows.append(_make_row("nba", "game_%d" % i,
                                      "2026-06-0%dT13:%02d:00Z" % (i + 1, t),
                                      0.45, 0.49, period=4))
            _ = ts_base  # used implicitly via ts pattern above
            _write_game(grade_dir, "nba", "game_%d" % i, rows)
        return grade_dir

    def test_positive_q1_recovered(self, tmp_path: Path):
        grade_dir = self._build_corpus(tmp_path, n_games=5, ticks_per_q=5)
        result = aggregate_by_segment(
            grade_dir=grade_dir, min_games=3, min_ticks_per_seg=8
        )
        q1 = result["segments"]["Q1"]
        # With 5 games * 4 scored ticks each = 20 ticks; planted CLV = +0.04
        assert q1["n_games"] == 5
        assert q1["total_ticks"] == 20   # 5 games * 4 scored (5-1 excluded per game)
        assert q1["pooled_mean_clv"] > EPS_DEFAULT
        assert q1["verdict"] in ("BEAT", "MATCH")  # BEAT requires CI lower > 0

    def test_negative_q2_recovered(self, tmp_path: Path):
        grade_dir = self._build_corpus(tmp_path, n_games=5, ticks_per_q=5)
        result = aggregate_by_segment(
            grade_dir=grade_dir, min_games=3, min_ticks_per_seg=8
        )
        q2 = result["segments"]["Q2"]
        assert q2["pooled_mean_clv"] < -EPS_DEFAULT
        assert q2["verdict"] == "BEHIND"

    def test_zero_clv_q3_is_match(self, tmp_path: Path):
        grade_dir = self._build_corpus(tmp_path, n_games=5, ticks_per_q=5)
        result = aggregate_by_segment(
            grade_dir=grade_dir, min_games=3, min_ticks_per_seg=8
        )
        q3 = result["segments"]["Q3"]
        assert abs(q3["pooled_mean_clv"]) <= EPS_DEFAULT
        assert q3["verdict"] == "MATCH"

    def test_no_dollar_keys_synthetic(self, tmp_path: Path):
        grade_dir = self._build_corpus(tmp_path)
        result = aggregate_by_segment(grade_dir=grade_dir)
        bad = _no_money_keys(result)
        assert bad == [], "Forbidden money keys: %s" % bad

    def test_edge_claimed_false(self, tmp_path: Path):
        grade_dir = self._build_corpus(tmp_path)
        result = aggregate_by_segment(grade_dir=grade_dir)
        assert result["edge_claimed"] is False
        for s in result["segments"].values():
            assert s["edge_claimed"] is False

    def test_units_probability(self, tmp_path: Path):
        grade_dir = self._build_corpus(tmp_path)
        result = aggregate_by_segment(grade_dir=grade_dir)
        assert result["units"] == "probability"
        for s in result["segments"].values():
            assert s["units"] == "probability"


# ---------------------------------------------------------------------------
# 6. Under-min segment -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------
class TestUnderMinThreshold:
    def test_one_game_per_segment_is_insufficient(self, tmp_path: Path):
        """Only 1 game in the corpus -> all segments below min_games=3 -> INSUFFICIENT_DATA."""
        grade_dir = tmp_path / "grade"
        rows = []
        for t in range(8):
            rows.append(_make_row("nba", "only_game",
                                  "2026-06-01T10:%02d:00Z" % t, 0.45, 0.50, period=1))
        _write_game(grade_dir, "nba", "only_game", rows)
        result = aggregate_by_segment(grade_dir=grade_dir, min_games=3, min_ticks_per_seg=8)
        q1 = result["segments"]["Q1"]
        assert q1["verdict"] == "INSUFFICIENT_DATA", (
            "Expected INSUFFICIENT_DATA for 1 game, got %s" % q1["verdict"]
        )

    def test_too_few_ticks_per_segment_is_insufficient(self, tmp_path: Path):
        """Enough games but only 1 tick per segment (0 scored after excluding close)."""
        grade_dir = tmp_path / "grade"
        for i in range(5):
            # Only 1 tick per period (= 0 scored ticks after close exclusion)
            rows = [_make_row("nba", "g%d" % i, "2026-06-0%dT10:00:00Z" % (i + 1),
                              0.45, 0.50, period=1)]
            _write_game(grade_dir, "nba", "g%d" % i, rows)
        result = aggregate_by_segment(grade_dir=grade_dir, min_games=3, min_ticks_per_seg=5)
        q1 = result["segments"]["Q1"]
        # 0 scored ticks each -> total_ticks=0 -> INSUFFICIENT_DATA
        assert q1["verdict"] == "INSUFFICIENT_DATA"
        assert q1["total_ticks"] == 0


# ---------------------------------------------------------------------------
# 7. MLB inning segments (cross-sport)
# ---------------------------------------------------------------------------
class TestMLBSegments:
    def test_inning_segments_recovered(self, tmp_path: Path):
        grade_dir = tmp_path / "grade"
        n_games = 4
        for i in range(n_games):
            rows = []
            for inn in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
                for t in range(4):
                    rows.append({
                        "sport": "mlb",
                        "game_id": "mlb_g%d" % i,
                        "ts": "2026-06-0%dT%02d:%02d:00Z" % (i + 1, inn + 10, t),
                        "market_prob": 0.50,
                        "model_prob": 0.55,
                        "side": "home",
                        "state_summary": "inning=%d half=top home_score=%d away_score=2" % (
                            inn, inn),
                    })
            _write_game(grade_dir, "mlb", "mlb_g%d" % i, rows)
        result = aggregate_by_segment(grade_dir=grade_dir, min_games=3, min_ticks_per_seg=8)
        i1 = result["segments"]["I1"]
        assert i1["n_games"] == n_games
        assert i1["pooled_mean_clv"] > EPS_DEFAULT
        assert i1["verdict"] in ("BEAT", "MATCH")

    def test_no_dollar_keys_mlb(self, tmp_path: Path):
        grade_dir = tmp_path / "grade"
        rows = [{"sport": "mlb", "game_id": "x", "ts": "2026-01-01T00:00:00Z",
                 "market_prob": 0.5, "model_prob": 0.55, "side": "home",
                 "state_summary": "inning=3 half=top"}]
        _write_game(grade_dir, "mlb", "x", rows)
        result = aggregate_by_segment(grade_dir=grade_dir)
        bad = _no_money_keys(result)
        assert bad == [], bad


# ---------------------------------------------------------------------------
# 8. format_report is ASCII and doesn't crash
# ---------------------------------------------------------------------------
class TestFormatReport:
    def test_ascii_no_crash(self, tmp_path: Path):
        result = aggregate_by_segment(grade_dir=tmp_path)
        report = format_report(result)
        assert isinstance(report, str)
        report.encode("ascii")   # must be pure ASCII

    def test_no_dollar_sign_in_report(self, tmp_path: Path):
        result = aggregate_by_segment(grade_dir=tmp_path)
        report = format_report(result)
        assert "$" not in report
