"""Per-file test for scripts.platformkit.prop_paper (network-free, tmp ledger).

  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_paper.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from scripts.platformkit import prop_paper
from scripts.platformkit.prop_paper import (
    grade_open, prop_summary, record_board, load_ledger,
)


def _board():
    # One reliable+ok edge (priced over) and one thin edge.
    return {
        "sport": "soccer_intl",
        "edges": [
            {
                "player": "Test Player", "matched_name": "Test Player",
                "match": "AAA vs BBB", "team": "AAA", "stat": "Shots",
                "line": 1.5, "side": "over", "model_p_over": 0.62,
                "reliable": True, "ev_flag": "ok", "source": "book",
                "over_price": 1.91, "under_price": 1.91, "as_of": "2026-06-01",
            },
            {
                "player": "Thin Guy", "matched_name": "Thin Guy",
                "match": "AAA vs BBB", "team": "AAA", "stat": "Fouls",
                "line": 0.5, "side": "over", "model_p_over": 0.55,
                "reliable": False, "ev_flag": "uncalibrated_thin",
                "source": "dfs", "over_price": None, "under_price": None,
                "as_of": "2026-06-01",
            },
        ],
    }


def _realized_df():
    # Test Player resolves to P1; in event E9 dated AFTER as_of they had 3 shots.
    return pd.DataFrame(
        [
            {"event_id": "E9", "player_id": "P1", "player": "Test Player",
             "team_abbr": "AAA", "date": "2026-06-02", "totalShots": 3.0,
             "shotsOnTarget": 1.0, "yellowCards": 0.0, "redCards": 0.0},
        ]
    )


def test_only_reliable_records_one(tmp_path):
    led = tmp_path / "prop_ledger.jsonl"
    res = record_board(_board(), only_reliable=True, ledger_path=led)
    assert res["status"] == "ok"
    assert res["recorded"] == 1
    assert res["below_bar"] == 1
    rows = load_ledger(led)
    assert len(rows) == 1
    assert rows[0]["player"] == "Test Player"
    assert rows[0]["executed"] is False
    assert rows[0]["channel"] == "paper"
    assert rows[0]["market"] == "prop"
    assert rows[0]["status"] == "open"


def test_record_is_idempotent(tmp_path):
    led = tmp_path / "prop_ledger.jsonl"
    record_board(_board(), only_reliable=True, ledger_path=led)
    res2 = record_board(_board(), only_reliable=True, ledger_path=led)
    assert res2["recorded"] == 0
    assert res2["skipped_existing"] == 1
    assert len(load_ledger(led)) == 1


def test_record_dedups_across_changing_as_of(tmp_path):
    # The dedup fix: re-recording the SAME prop with a DIFFERENT as_of (as a cadence
    # loop does every refresh) must add NOTHING -- as_of is not part of the key.
    led = tmp_path / "prop_ledger.jsonl"
    record_board(_board(), only_reliable=True, ledger_path=led)
    board2 = _board()
    for e in board2["edges"]:
        e["as_of"] = "2026-06-09"  # later refresh -> fresh taken-line timestamp
    res2 = record_board(board2, only_reliable=True, ledger_path=led)
    assert res2["recorded"] == 0
    assert res2["skipped_existing"] == 1
    rows = load_ledger(led)
    assert len(rows) == 1
    # The STORED as_of is the FIRST-sight value (the line we actually took).
    assert rows[0]["as_of"] == "2026-06-01"


def test_only_reliable_false_records_thin_too(tmp_path):
    led = tmp_path / "prop_ledger.jsonl"
    res = record_board(_board(), only_reliable=False, ledger_path=led)
    assert res["recorded"] == 2
    assert len(load_ledger(led)) == 2


def test_grade_settles_a_win(tmp_path):
    led = tmp_path / "prop_ledger.jsonl"
    record_board(_board(), only_reliable=True, ledger_path=led)
    g = grade_open(realized_df=_realized_df(), ledger_path=led)
    assert g["status"] == "ok"
    assert g["graded"] == 1
    settled = [r for r in load_ledger(led) if r.get("status") == "settled"]
    assert len(settled) == 1
    # 3 shots > 1.5 over -> win; unit record at 1.91 = +0.91.
    assert settled[0]["result"] == "win"
    assert settled[0]["realized"] == 3.0
    assert abs(settled[0]["unit_result"] - 0.91) < 1e-6


def test_grade_is_idempotent(tmp_path):
    led = tmp_path / "prop_ledger.jsonl"
    record_board(_board(), only_reliable=True, ledger_path=led)
    grade_open(realized_df=_realized_df(), ledger_path=led)
    g2 = grade_open(realized_df=_realized_df(), ledger_path=led)
    assert g2["graded"] == 0
    assert g2["already_settled"] == 1


def test_summary_returns_n_and_hit_rate(tmp_path):
    led = tmp_path / "prop_ledger.jsonl"
    record_board(_board(), only_reliable=True, ledger_path=led)
    grade_open(realized_df=_realized_df(), ledger_path=led)
    s = prop_summary(ledger_path=led)
    assert s["status"] == "ok"
    assert s["overall"]["n"] == 1
    assert s["overall"]["hit_rate"] == 1.0
    assert "Shots" in s["by_stat"]
    assert "TODO" in s["note"]


def test_priced_settled_bet_gets_clv_from_history(tmp_path):
    # A canned line history whose CLOSING (latest-ts) over price is SHORTER (1.60)
    # than the taken 1.91 -> the taken bet got a BETTER number -> clv_pct > 0.
    led = tmp_path / "prop_ledger.jsonl"
    hist = tmp_path / "prop_line_history.jsonl"
    rows = [
        {"match": "AAA vs BBB", "player": "Test Player", "stat": "Shots",
         "line": 1.5, "over_price": 1.91, "under_price": 1.91, "source": "book",
         "ts": "2026-06-01T00:00:00+00:00"},
        # Closing line (latest ts): over shortened, under lengthened.
        {"match": "AAA vs BBB", "player": "Test Player", "stat": "Shots",
         "line": 1.5, "over_price": 1.60, "under_price": 2.40, "source": "book",
         "ts": "2026-06-02T11:00:00+00:00"},
    ]
    with hist.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    record_board(_board(), only_reliable=True, ledger_path=led)
    g = grade_open(realized_df=_realized_df(), ledger_path=led, history_path=hist)
    assert g["graded"] == 1
    settled = [r for r in load_ledger(led) if r.get("status") == "settled"]
    assert settled[0]["clv_pct"] is not None
    assert settled[0]["clv_pct"] > 0.0  # took 1.91 vs a 1.60 close = better number
    # Summary surfaces CLV over priced bets.
    s = prop_summary(ledger_path=led)
    assert s["overall"]["n_clv"] == 1
    assert s["overall"]["mean_clv_pct"] > 0.0
    assert s["overall"]["pct_beat_close"] == 100.0


def test_clv_none_without_history(tmp_path):
    # No history file -> priced bet still settles, clv_pct stays None (no fake CLV).
    led = tmp_path / "prop_ledger.jsonl"
    record_board(_board(), only_reliable=True, ledger_path=led)
    grade_open(realized_df=_realized_df(), ledger_path=led,
               history_path=tmp_path / "absent.jsonl")
    settled = [r for r in load_ledger(led) if r.get("status") == "settled"]
    assert settled[0]["clv_pct"] is None
    s = prop_summary(ledger_path=led)
    assert s["overall"]["n_clv"] == 0
    assert s["overall"]["mean_clv_pct"] is None


def _realized_df_missing_stat():
    # Match IS final (player has a box-score row dated after as_of) but the mapped
    # stat column (totalShots) is NaN -> genuinely MISSING, must NOT become a 0.
    return pd.DataFrame(
        [
            {"event_id": "E9", "player_id": "P1", "player": "Test Player",
             "team_abbr": "AAA", "date": "2026-06-02",
             "totalShots": float("nan"), "shotsOnTarget": float("nan"),
             "yellowCards": 0.0, "redCards": 0.0},
        ]
    )


def _realized_df_genuine_zero():
    # Player played and recorded a TRUE 0 shots -> grades as a real 0 (under wins
    # vs a 1.5 line, but as a GENUINE graded result, not a fabricated void).
    return pd.DataFrame(
        [
            {"event_id": "E9", "player_id": "P1", "player": "Test Player",
             "team_abbr": "AAA", "date": "2026-06-02", "totalShots": 0.0,
             "shotsOnTarget": 0.0, "yellowCards": 0.0, "redCards": 0.0},
        ]
    )


def test_missing_realized_stat_voids_not_win(tmp_path):
    # THE HONESTY BUG: a NaN realized stat must VOID (excluded), never settle as a
    # fabricated 0 that an UNDER would "win" (or that an OVER would "loss").
    led = tmp_path / "prop_ledger.jsonl"
    record_board(_board(), only_reliable=True, ledger_path=led)
    g = grade_open(realized_df=_realized_df_missing_stat(), ledger_path=led)
    assert g["status"] == "ok"
    assert g["graded"] == 0          # nothing graded as win/loss/push
    assert g["voided"] == 1          # the prop is voided
    settled = [r for r in load_ledger(led) if r.get("status") == "settled"]
    assert len(settled) == 1
    assert settled[0]["result"] == "void"
    assert settled[0]["realized"] is None
    assert settled[0]["unit_result"] is None


def test_void_excluded_from_hit_rate(tmp_path):
    # A void must not count in n, hit_rate, net_units, or CLV -- only n_void.
    led = tmp_path / "prop_ledger.jsonl"
    record_board(_board(), only_reliable=True, ledger_path=led)
    grade_open(realized_df=_realized_df_missing_stat(), ledger_path=led)
    s = prop_summary(ledger_path=led)
    assert s["overall"]["n"] == 0
    assert s["overall"]["n_void"] == 1
    assert s["overall"]["hit_rate"] is None   # zero decisive -> undefined, not 1.0
    assert s["overall"]["net_units"] is None
    # UNITS ONLY: no $ / roi key in the prop summary.
    assert "paper_roi" not in s["overall"] and "roi" not in s["overall"]


def test_genuine_zero_grades_not_voided(tmp_path):
    # A genuinely-recorded 0 IS a real graded result (here: over 1.5 -> loss).
    led = tmp_path / "prop_ledger.jsonl"
    record_board(_board(), only_reliable=True, ledger_path=led)
    g = grade_open(realized_df=_realized_df_genuine_zero(), ledger_path=led)
    assert g["graded"] == 1
    assert g["voided"] == 0
    settled = [r for r in load_ledger(led) if r.get("status") == "settled"]
    assert settled[0]["result"] == "loss"   # 0 shots, over 1.5 -> loss
    assert settled[0]["realized"] == 0.0
    s = prop_summary(ledger_path=led)
    assert s["overall"]["n"] == 1
    assert s["overall"]["n_void"] == 0
    assert s["overall"]["hit_rate"] == 0.0


def test_public_fns_never_raise_on_garbage(tmp_path):
    led = tmp_path / "prop_ledger.jsonl"
    assert record_board(None, ledger_path=led)["status"].startswith(("ok", "error"))
    assert record_board({"edges": [{}]}, only_reliable=False,
                        ledger_path=led)["status"] == "ok"
    assert grade_open(realized_df=None, ledger_path=led)["status"] in (
        "ok", "no_realized_data")
    assert prop_summary(ledger_path=led)["status"] == "ok"


# ---------------------------------------------------------------------------
# m13-breaker-bypass (bare-caller close-out, wave-36): main()'s --record path
# used to call build_prop_board(sport) BARE, which re-derives
# cfg.default_providers() UN-GATED inside prop_edge.py -- re-dispatching to a
# provider the circuit breaker just opened. The fix routes it through the SAME
# breaker_filtered_providers() helper the wave-35 prop_cards.py fix uses.
# ---------------------------------------------------------------------------

def test_cli_record_uses_breaker_filtered_providers(monkeypatch, tmp_path, capsys):
    calls = []

    def fake_board(sport, **kw):  # noqa: ANN001
        calls.append((sport, kw))
        return {"sport": sport, "status": "ok", "edges": []}
    monkeypatch.setattr("scripts.platformkit.prop_edge.build_prop_board", fake_board)
    monkeypatch.setattr(prop_paper, "record_board",
                        lambda board, only_reliable=True: {"status": "ok", "recorded": 0})

    class _FakeProvider:
        name = "fake_survivor"

    filtered_calls = []

    def fake_breaker_filtered(sport):  # noqa: ANN001
        filtered_calls.append(sport)
        return [_FakeProvider()]

    import scripts.platformkit.bestbets.prop_cards_circuit_io as pcio
    monkeypatch.setattr(pcio, "breaker_filtered_providers", fake_breaker_filtered)

    rc = prop_paper.main(["--record", "--sport", "mlb"])
    assert rc == 0
    assert filtered_calls == ["mlb"]
    assert len(calls) == 1
    sport_arg, kwargs = calls[0]
    assert sport_arg == "mlb"
    assert [getattr(p, "name", None) for p in kwargs.get("providers", [])] == ["fake_survivor"]


def test_cli_record_never_calls_bare_unfiltered_providers(monkeypatch):
    # Even if the breaker helper is unavailable (returns None), the CLI must pass
    # an explicit EMPTY providers list -- never omit providers / let
    # build_prop_board fall back to cfg.default_providers() un-gated.
    calls = []

    def fake_board(sport, **kw):  # noqa: ANN001
        calls.append((sport, kw))
        return {"sport": sport, "status": "ok", "edges": []}
    monkeypatch.setattr("scripts.platformkit.prop_edge.build_prop_board", fake_board)
    monkeypatch.setattr(prop_paper, "record_board",
                        lambda board, only_reliable=True: {"status": "ok", "recorded": 0})

    import scripts.platformkit.bestbets.prop_cards_circuit_io as pcio
    monkeypatch.setattr(pcio, "breaker_filtered_providers", lambda sport: None)

    rc = prop_paper.main(["--record", "--sport", "mlb"])
    assert rc == 0
    assert len(calls) == 1
    _, kwargs = calls[0]
    assert kwargs.get("providers") == []
