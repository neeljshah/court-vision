"""Per-file tests for scripts.platformkit.ingame.ticker_settlement_join.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/ingame/test_ticker_settlement_join.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import pytest

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.ingame import ticker_settlement_join as J


class _StubHomeWinResolver:
    """Injectable resolver: fixed verdict per ticker, mirrors the real
    .home_win(ticker)->0/1/None contract without touching any parquet."""

    def __init__(self, verdicts):
        self._verdicts = verdicts
        self.available = True

    def home_win(self, ticker: str) -> Optional[int]:
        return self._verdicts.get(ticker)


def _write_ticks(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _tick(ticker: str, ts: str, model_p: float, market_p: float) -> dict:
    return {"sport": "mlb", "game_id": ticker, "ts": ts, "model_prob": model_p,
            "market_prob": market_p, "side": "home", "state_summary": "inning=5"}


# --------------------------------------------------------------------------- #
# join_ticker_file: the core join
# --------------------------------------------------------------------------- #
def test_join_ticker_file_produces_all_four_fields(tmp_path):
    grade_dir = tmp_path / "grade"
    p = grade_dir / "mlb" / "KXMLBGAME-26JUL011235CWSBAL.jsonl"
    _write_ticks(p, [
        _tick(p.stem, "2026-07-01T17:00:00Z", 0.58, 0.55),
        _tick(p.stem, "2026-07-01T17:05:00Z", 0.63, 0.60),
    ])
    resolver = _StubHomeWinResolver({p.stem: 1})

    summary = J.join_ticker_file("mlb", p, resolver,
                                  joined_dir=tmp_path / "joined", grade_dir=grade_dir)

    assert summary["status"] == "joined"
    assert summary["n_joined"] == 2
    out = Path(summary["path"])
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    for r in rows:
        # THE deliverable: all four fields non-null together, in the SAME record.
        assert r["model_prob"] is not None
        assert r["market_prob"] is not None
        assert r["outcome"] == 1.0
        assert r["close_source"] == J._CLOSE_SOURCE_LABEL["mlb"]
    assert rows[-1]["close_prob"] == 0.60  # last tick's market_prob is the close proxy

    # the SOURCE grade file also got an idempotent settle_stamp with close_source.
    stamped = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
    settle_rows = [r for r in stamped if r.get("settled")]
    assert len(settle_rows) == 1
    assert settle_rows[0]["home_win"] == 1.0
    assert settle_rows[0]["close_source"] == J._CLOSE_SOURCE_LABEL["mlb"]


def test_join_ticker_file_unresolved_outcome_is_honest_skip(tmp_path):
    grade_dir = tmp_path / "grade"
    p = grade_dir / "mlb" / "KXMLBGAME-26JUL011235XXXYYY.jsonl"
    _write_ticks(p, [_tick(p.stem, "2026-07-01T17:00:00Z", 0.5, 0.5)])
    resolver = _StubHomeWinResolver({})  # never resolves anything

    summary = J.join_ticker_file("mlb", p, resolver, joined_dir=tmp_path / "joined")

    assert summary["status"] == "skipped"
    assert summary["reason"] == "unresolved_outcome"
    assert not (tmp_path / "joined" / "mlb" / p.name).exists()


def test_join_ticker_file_no_valid_ticks_is_honest_skip(tmp_path):
    grade_dir = tmp_path / "grade"
    p = grade_dir / "mlb" / "KXMLBGAME-EMPTY.jsonl"
    _write_ticks(p, [{"sport": "mlb", "game_id": p.stem, "ts": "t", "settled": True,
                      "home_win": 1.0}])  # a stamp-only row, no probs
    resolver = _StubHomeWinResolver({p.stem: 1})

    summary = J.join_ticker_file("mlb", p, resolver, joined_dir=tmp_path / "joined")

    assert summary["status"] == "skipped"
    assert summary["reason"] == "no_valid_ticks"


def test_soccer_draw_outcome_kept_as_half_never_stamped(tmp_path):
    class _StubFinalScore:
        available = True

        def final_score(self, ticker: str):
            return (1, 1)  # a draw

    grade_dir = tmp_path / "grade"
    p = grade_dir / "soccer_intl" / "KXWCGAME-DRAWTEST.jsonl"
    _write_ticks(p, [_tick(p.stem, "t", 0.4, 0.4)])

    summary = J.join_ticker_file("soccer_intl", p, _StubFinalScore(),
                                  joined_dir=tmp_path / "joined", grade_dir=grade_dir)

    assert summary["status"] == "joined"
    out = Path(summary["path"])
    row = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert row["outcome"] == 0.5
    # a draw is never coerced into a fake binary home_win stamp on the source file.
    stamped = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
    assert not any(r.get("settled") for r in stamped)


# --------------------------------------------------------------------------- #
# backfill_sport: join-rate over a small synthetic corpus (join-rate assert)
# --------------------------------------------------------------------------- #
def test_backfill_sport_join_rate(tmp_path, monkeypatch):
    grade_dir = tmp_path / "grade"
    tickers = ["KXMLBGAME-A", "KXMLBGAME-B", "KXMLBGAME-C"]
    for t in tickers:
        _write_ticks(grade_dir / "mlb" / (t + ".jsonl"), [_tick(t, "t", 0.5, 0.5)])
    # 2 of 3 resolve -- an honest sub-100% rate, not a fabricated pass.
    resolver = _StubHomeWinResolver({"KXMLBGAME-A": 1, "KXMLBGAME-B": 0})
    monkeypatch.setattr(J, "_build_resolver", lambda sport, **kw: resolver)

    result = J.backfill_sport("mlb", grade_dir=grade_dir, joined_dir=tmp_path / "joined")

    assert result["n_files"] == 3
    assert result["n_joined"] == 2
    assert result["join_rate"] == pytest.approx(2 / 3)


# --------------------------------------------------------------------------- #
# S83: the five mlb_* player-identity fields survive the join unchanged, and a tick
# without them still produces the exact same non-player row it always did.
# --------------------------------------------------------------------------- #
def test_player_identity_carried_through_and_other_fields_unchanged(tmp_path):
    grade_dir = tmp_path / "grade"
    p = grade_dir / "mlb" / "KXMLBGAME-26JUL011235CWSBAL.jsonl"
    ids = {"mlb_batter_id": 592450, "mlb_pitcher_id": 656302,
           "mlb_pitcher_pitch_count": 74, "mlb_ondeck_id": 700000,
           "mlb_bullpen_used": [656492, 111]}
    with_ids = dict(_tick(p.stem, "2026-07-01T17:00:00Z", 0.58, 0.55), **ids)
    without = _tick(p.stem, "2026-07-01T17:05:00Z", 0.63, 0.60)
    _write_ticks(p, [with_ids, without])
    resolver = _StubHomeWinResolver({p.stem: 1})

    J.join_ticker_file("mlb", p, resolver, joined_dir=tmp_path / "joined",
                       grade_dir=grade_dir)
    rows = [json.loads(x) for x in
            (tmp_path / "joined" / "mlb" / p.name).read_text(encoding="utf-8").splitlines()]

    assert len(rows) == 2
    for k, v in ids.items():
        assert rows[0][k] == v            # carried through UNCHANGED
        assert k not in rows[1]           # absent stays absent, never fabricated
    # every non-player field is byte-identical to the pre-S83 schema
    non_player = {k: v for k, v in rows[0].items() if k not in ids}
    assert list(non_player) == list(rows[1])   # identical key order + key set
    assert non_player == {"sport": "mlb", "game_id": p.stem,
                          "ts": "2026-07-01T17:00:00Z", "model_prob": 0.58,
                          "market_prob": 0.55, "side": "home",
                          "state_summary": "inning=5", "outcome": 1.0,
                          "close_source": J._CLOSE_SOURCE_LABEL["mlb"],
                          "outcome_source": J._CLOSE_SOURCE_LABEL["mlb"],
                          "close_prob": non_player["close_prob"],
                          "close_ts": non_player["close_ts"], "edge_claimed": False}


class _SourcedResolver:
    """Resolver that reports WHICH map answered (the S95 contract)."""

    def __init__(self, source):
        self.last_source = source

    def home_win(self, ticker):
        return 1


@pytest.mark.parametrize("source", ["espn_boxscores_parquet", "games_parquet_fallback"])
def test_outcome_source_is_per_row_from_the_resolver(tmp_path, source):
    grade_dir = tmp_path / "grade" / "mlb"
    grade_dir.mkdir(parents=True)
    p = grade_dir / "KXMLBGAME-26JUL011235CWSBAL.jsonl"
    _write_ticks(p, [_tick(p.stem, "2026-07-01T17:00:00Z", 0.58, 0.55)])
    J.join_ticker_file("mlb", p, _SourcedResolver(source),
                       joined_dir=tmp_path / "joined", grade_dir=grade_dir)
    row = json.loads((tmp_path / "joined" / "mlb" / p.name).read_text(
        encoding="utf-8").strip())
    assert row["outcome_source"] == source
    # close_source is the resolver-family label and is NOT rewritten
    assert row["close_source"] == J._CLOSE_SOURCE_LABEL["mlb"]


def test_backfill_sport_unknown_sport_is_honest_empty(tmp_path):
    result = J.backfill_sport("curling", grade_dir=tmp_path / "grade")
    assert result == {"sport": "curling", "n_files": 0, "n_joined": 0,
                      "join_rate": 0.0, "results": []}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
