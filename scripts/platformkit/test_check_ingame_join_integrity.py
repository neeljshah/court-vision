"""Per-file test for scripts.platformkit.check_ingame_join_integrity.

Synthetic fixture only -- never touches data/cache/ingame_grade_joined.
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/test_check_ingame_join_integrity.py -q
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from scripts.platformkit import check_ingame_join_integrity as mod


def _tick(ts, home, away, inning, market, outcome):
    return json.dumps({
        "sport": "mlb", "game_id": "x", "ts": ts,
        "model_prob": 0.5, "market_prob": market, "side": "home",
        "state_summary": "home_score=%.1f away_score=%.1f inning=%d half=top outs=0"
                         % (home, away, inning),
        "outcome": outcome, "edge_claimed": False,
    })


def _write(path: Path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _clean_game(day="02", market_start=0.5):
    """A well-formed single game on 2026-07-<day>: home wins 5-2, market moves."""
    return [_tick("2026-07-%sT18:0%d:00Z" % (day, i), min(i, 5), min(i // 2, 2),
                  1 + i, market_start + 0.02 * i, 1.0) for i in range(12)]


def _fixture(root: Path):
    sport = root / "mlb"
    # (a) clean: label agrees, market moves, dates inside the window, one segment
    _write(sport / "KXMLBGAME-26JUL021235AAABBB.jsonl", _clean_game())
    # (b) mis-joined: two games glued together, frozen market, a tick a day early,
    #     and a label that contradicts the final leader (home leads 5-2, outcome 0)
    early = [_tick("2026-06-30T22:00:00Z", 0, 0, 1, 0.535, 0.0),
             _tick("2026-07-01T00:10:00Z", 0, 8, 9, 0.535, 0.0)]
    late = [_tick("2026-07-02T18:0%d:00Z" % i, min(i, 5), min(i // 2, 2), 1 + i,
                  0.535, 0.0) for i in range(12)]
    # two trailing STATELESS ticks: they must neither invent a segment reset nor be
    # mistaken for a 0-0 final score.
    stateless = [json.dumps({"ts": "2026-07-02T18:20:00Z", "model_prob": 0.5,
                             "market_prob": 0.535, "state_summary": "live",
                             "outcome": 0.0})] * 2
    _write(sport / "KXMLBGAME-26JUL021235CCCDDD.jsonl", early + late + stateless)
    # (c) short path: 3 ticks only
    _write(sport / "KXMLBGAME-26JUL021235EEEFFF.jsonl", _clean_game()[:3])


def test_clean_game_is_flag_free(tmp_path):
    _fixture(tmp_path)
    rec = mod.scan_game(tmp_path / "mlb" / "KXMLBGAME-26JUL021235AAABBB.jsonl")
    assert rec["n_ticks"] == 12
    for flag in mod.FLAGS:
        assert rec[flag] is False, flag


def test_misjoined_game_trips_every_flag(tmp_path):
    _fixture(tmp_path)
    rec = mod.scan_game(tmp_path / "mlb" / "KXMLBGAME-26JUL021235CCCDDD.jsonl")
    assert rec["label_disagree"] is True
    assert rec["frozen_market"] is True
    assert rec["ts_outside"] is True and rec["n_ticks_outside_window"] == 2
    # exactly 2 segments: the stateless tail must not add a third
    assert rec["multi_game"] is True and rec["segments"] == 2
    assert rec["n_stateless_ticks"] == 2 and rec["stateless_only"] is False
    # final score read from the last STATED tick, not the trailing "live" rows
    assert (rec["final_home"], rec["final_away"]) == (5.0, 2.0)
    assert rec["leader"] == "home" and rec["outcome"] == 0.0


def test_short_path_flagged_without_label_disagreement(tmp_path):
    _fixture(tmp_path)
    rec = mod.scan_game(tmp_path / "mlb" / "KXMLBGAME-26JUL021235EEEFFF.jsonl")
    assert rec["short_path"] is True
    assert rec["label_disagree"] is False


def test_scan_sport_totals_and_leader_table(tmp_path):
    _fixture(tmp_path)
    s = mod.scan_sport(tmp_path / "mlb")
    assert s["n_games"] == 3
    assert s["totals"] == {"label_disagree": 1, "frozen_market": 1, "ts_outside": 1,
                           "short_path": 1, "multi_game": 1, "stateless_only": 0}
    assert s["n_stateless_ticks"] == 2
    # finals: clean 5-2 (agrees), mis-joined 5-2 (disagrees), short 2-1 (agrees)
    assert s["leader_at_last_tick"]["margin_ge_1"]["n_games"] == 3
    assert s["leader_at_last_tick"]["margin_ge_1"]["observed_freq"] == round(2 / 3, 4)
    assert s["leader_at_last_tick"]["margin_ge_3"]["n_games"] == 2
    assert s["leader_at_last_tick"]["margin_ge_3"]["observed_freq"] == 0.5
    assert s["leader_at_last_tick"]["margin_ge_5"]["n_games"] == 0
    assert s["leader_at_last_tick"]["margin_ge_5"]["observed_freq"] is None
    assert s["offenders"]["label_disagree"] == ["KXMLBGAME-26JUL021235CCCDDD"]


def test_main_exits_nonzero_and_writes_json(tmp_path, capsys):
    _fixture(tmp_path)
    out = tmp_path / "report" / "ingame_join_integrity.json"
    rc = mod.main(["--root", str(tmp_path), "--out", str(out)])
    assert rc == 1
    printed = capsys.readouterr().out
    assert "INGAME JOIN INTEGRITY" in printed
    assert "LEADER AT LAST TICK" in printed
    assert "TOTAL label disagreements: 1" in printed
    assert printed.isascii()
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["n_label_disagree_total"] == 1
    assert report["sports"]["mlb"]["n_games"] == 3


def test_main_exits_zero_on_a_clean_root(tmp_path):
    _write(tmp_path / "mlb" / "KXMLBGAME-26JUL021235AAABBB.jsonl", _clean_game())
    assert mod.main(["--root", str(tmp_path)]) == 0


def test_missing_root_is_no_data(tmp_path, capsys):
    assert mod.main(["--root", str(tmp_path / "nope")]) == 2
    assert "NO_DATA" in capsys.readouterr().out


def test_helpers():
    assert mod.ticker_date("KXMLBGAME-26JUL021235PITPHI") == date(2026, 7, 2)
    assert mod.ticker_date("KXWCGAME-26JUL01BELSEN") == date(2026, 7, 1)
    assert mod.ticker_date("no-date-here") is None
    assert mod.parse_state("home_score=1.0 away_score=6.0 inning=9 half=top") == {
        "home_score": 1.0, "away_score": 6.0, "inning": 9.0}
    # a bare non-numeric summary (early soccer capture) yields no fields, never raises
    assert mod.parse_state("live") == {}
    assert mod.parse_state(None) == {}
