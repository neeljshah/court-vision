"""Per-file tests for ingame.aggregate_clv_to_corpus -- the THIN ADAPTER that hands the
multi-game aggregate grader's per-game OUTCOME-Brier evidence to the SECOND CORPUS
(improve.clv_corpus.build_close_corpus), plus the measurement-only CLV-over-time read path.

OFFLINE + deterministic: per-game paired-capture jsonl is written to tmp dirs (the
live_grade row schema, same fixtures shape as test_inplay_aggregate_grade). Binding contracts:

  (a) A pool where the model GENUINELY beats the close on the OUTCOME -> build_corpus_from_grades
      (with require_enabled=False to bypass the sentinel) returns a corpus with the clv_corpus
      id; a market-COPY pool -> None (P1 preserved: shrink-to-close earns NO corpus).
  (b) INERT by default: with the sentinel ABSENT (require_enabled=True), build_corpus_from_grades
      returns None and inject_grades_corpus returns the candidate UNCHANGED (corpora:[] baseline).
  (c) The CLV-over-time read path (frontend.status_routes._clv_over_time_block) returns the
      series with NO $ field, units=probability, edge_claimed False.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_aggregate_clv_to_corpus.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.platformkit.ingame import aggregate_clv_to_corpus as adapter
from scripts.platformkit.ingame import inplay_aggregate_grade as ag


# --------------------------------------------------------------------------------------- #
# fixtures (same paired-capture schema as the aggregate-grader tests).                     #
# --------------------------------------------------------------------------------------- #
def _ts(gidx: int, i: int) -> str:
    base = (datetime(2026, 6, 18, 1, 0, 0, tzinfo=timezone.utc)
            + timedelta(hours=gidx, seconds=30 * i))
    return base.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_game(grade_dir: Path, gid: str, rows: list, *, sport: str = "mlb") -> Path:
    d = grade_dir / sport
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("%s.jsonl" % gid)
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=True) + "\n")
    return p


def _beat_game(gidx: int, gid: str, outcome: float, *, n: int = 14) -> list:
    """A game the model BEATS the CLOSE on OUTCOME-Brier. The closing line (final tick)
    is informative-but-IMPERFECT -- it lands at ~0.65 toward the realized outcome, never
    on it. The model sits CLOSER to the realized outcome than that close on every scored
    state, so loss_close - loss_model > 0 (model beats the close on the outcome)."""
    rows = []
    close_line = 0.50 + (outcome - 0.50) * 0.30   # imperfect close (~0.65 / ~0.35)
    for i in range(n):
        frac = i / (n - 1)
        if i == n - 1:
            market = close_line                    # the in-play CLOSE (yardstick)
        else:
            market = 0.50 + (close_line - 0.50) * frac
        model = 0.50 + (outcome - 0.50) * (0.70 + 0.25 * frac)  # sharper toward outcome
        model = min(0.99, max(0.01, model))
        rows.append({
            "sport": "mlb", "game_id": gid, "ts": _ts(gidx, i),
            "market_prob": round(market, 6), "model_prob": round(model, 6),
            "side": "home", "state_summary": "live", "outcome": outcome,
        })
    return rows


def _copy_game(gidx: int, gid: str, outcome: float, *, n: int = 14) -> list:
    """A market-FOLLOW game: model == market on every tick, and the close == the model's
    own number -> per-state outcome-Brier d == 0 -> NO corpus (the P1 reject)."""
    rows = []
    close_line = 0.50 + (outcome - 0.50) * 0.30
    for i in range(n):
        frac = i / (n - 1)
        market = close_line if i == n - 1 else 0.50 + (close_line - 0.50) * frac
        rows.append({
            "sport": "mlb", "game_id": gid, "ts": _ts(gidx, i),
            "market_prob": round(market, 6), "model_prob": round(close_line, 6),
            "side": "home", "state_summary": "live", "outcome": outcome,
        })
    return rows


def _write_pool(gd: Path, prefix: str, builder, outcomes) -> None:
    for k, o in enumerate(outcomes):
        gid = "%s-G%d" % (prefix, k)
        _write_game(gd, gid, builder(k, gid, o))


# --------------------------------------------------------------------------------------- #
# (a) corpus forms ONLY on a real beat; market-copy -> None (P1 preserved).                 #
# --------------------------------------------------------------------------------------- #
def test_corpus_forms_only_on_real_beat(tmp_path):
    outcomes = [1.0, 0.0, 1.0, 1.0, 0.0, 1.0]

    beat_dir = tmp_path / "beat"
    _write_pool(beat_dir, "BEAT", _beat_game, outcomes)
    # require_enabled=False bypasses the human sentinel for the offline proof.
    corpus = adapter.build_corpus_from_grades(grade_dir=beat_dir, require_enabled=False)
    assert corpus is not None, "a genuine model-beats-close pool must earn a corpus"
    assert corpus["corpus_id"] == adapter.CLV_CORPUS_ID
    assert corpus["all_positive"] is True
    assert corpus["units"] == "probability"

    copy_dir = tmp_path / "copy"
    _write_pool(copy_dir, "COPY", _copy_game, outcomes)
    # P1 KEYSTONE: a pure market-copy / shrink-to-close pool earns NO corpus.
    none_corpus = adapter.build_corpus_from_grades(grade_dir=copy_dir, require_enabled=False)
    assert none_corpus is None, "shrink-to-close pool must yield NO corpus (P1)"


# --------------------------------------------------------------------------------------- #
# (b) INERT when the sentinel is absent (default require_enabled=True).                     #
# --------------------------------------------------------------------------------------- #
def test_inert_when_sentinel_absent(tmp_path):
    gd = tmp_path / "beat"
    _write_pool(gd, "BEAT", _beat_game, [1.0, 0.0, 1.0, 1.0, 0.0, 1.0])
    # Default require_enabled=True: sentinel is absent on the box -> no corpus.
    assert adapter.build_corpus_from_grades(grade_dir=gd) is None
    # inject_grades_corpus must return the candidate UNCHANGED (corpora:[] baseline).
    cand = {"name": "cand", "corpora": []}
    out = adapter.inject_grades_corpus(cand, grade_dir=gd)
    assert out == {"name": "cand", "corpora": []}
    assert out.get("clv_corpus_injected") is None
    assert out.get("vs_close") in (None, "UNPROVEN")


# --------------------------------------------------------------------------------------- #
# (b2) the shape map: a settled game has scored states + a single close yardstick.          #
# --------------------------------------------------------------------------------------- #
def test_game_to_settled_excludes_close_tick(tmp_path):
    gd = tmp_path / "one"
    p = _write_game(gd, "G", _beat_game(0, "G", 1.0, n=10))
    g = adapter.game_to_settled(p)
    assert g is not None
    assert g["is_true_close"] is True
    # 10 captured ticks -> 9 scored states (the final tick is the close yardstick).
    assert len(g["states"]) == 9
    close_p = {s["close_p"] for s in g["states"]}
    assert len(close_p) == 1  # one common close (the last captured market price)
    for s in g["states"]:
        assert s["outcome"] == 1.0 and s["is_true_close"] is True
    # A proxy-close game (any row flagged is_true_close False) is dropped.
    rows = _beat_game(0, "PX", 1.0, n=10)
    rows[3]["is_true_close"] = False
    p2 = _write_game(gd, "PX", rows)
    assert adapter.game_to_settled(p2) is None


# --------------------------------------------------------------------------------------- #
# (c) the CLV-over-time read path returns the series with NO $ field.                       #
# --------------------------------------------------------------------------------------- #
def test_clv_over_time_read_path_no_dollar(tmp_path, monkeypatch):
    from frontend import status_routes as sr

    gd = tmp_path / "beat"
    _write_pool(gd, "BEAT", _beat_game, [1.0, 0.0, 1.0, 1.0, 0.0, 1.0])

    # Point the aggregate grader at the fixture dir for this read.
    orig = ag.aggregate_grade
    monkeypatch.setattr(ag, "aggregate_grade",
                        lambda *a, **k: orig(grade_dir=gd))

    block = sr._clv_over_time_block()
    assert block["status"] == "ok"
    assert "clv_over_time" in block and len(block["clv_over_time"]) == 6
    # ordered by settle time + numbers only.
    assert block["clv_over_time"] == sorted(
        block["clv_over_time"], key=lambda e: e["settle_ts"])
    assert block["units"] == "probability"
    assert block["edge_claimed"] is False
    banned = ("roi", "pnl", "stake", "bankroll", "dollar", "usd", "$",
              "profit", "edge_pct", "money")
    blob = json.dumps(block).lower()
    for tok in banned:
        assert tok not in blob, "banned token %r leaked into the read path" % tok
