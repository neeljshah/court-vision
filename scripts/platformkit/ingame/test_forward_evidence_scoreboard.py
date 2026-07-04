"""Per-file tests for forward_evidence_scoreboard.

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_forward_evidence_scoreboard.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from scripts.platformkit.ingame import forward_evidence_scoreboard as fes


def _write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


# ---------------------------------------------------------------- rate math

def test_distance_decidable_now_when_forward_n_clears_floor():
    assert fes.distance_to_decidable(25, 5.0, 20) == fes._NOW


def test_distance_never_when_zero_rate():
    assert fes.distance_to_decidable(0, 10.0, 20) == fes._NEVER


def test_distance_never_when_days_accruing_nonpositive_and_zero_forward():
    assert fes.distance_to_decidable(0, 0.0, 20) == fes._NEVER
    assert fes.distance_to_decidable(0, -1.0, 20) == fes._NEVER


def test_distance_unknown_when_days_accruing_missing():
    assert fes.distance_to_decidable(3, None, 20) == fes._UNKNOWN


def test_distance_computes_days_needed_from_rate():
    # 10 games in 5 days = 2 games/day; need 20-10=10 more games -> 5 days
    out = fes.distance_to_decidable(10, 5.0, 20)
    assert out == "5_DAYS"


def test_distance_ceils_fractional_days():
    # 3 games in 4 days = 0.75/day; need 20-3=17 more -> 17/0.75=22.67 -> ceil 23
    out = fes.distance_to_decidable(3, 4.0, 20)
    assert out == "23_DAYS"


# ---------------------------------------------------------------- composer: present

def test_composer_reads_present_tail_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr(fes, "DOMAINS_DIR", tmp_path)
    monkeypatch.setattr(fes, "TAIL_SPORTS", ["mlb"])
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    doc = {
        "pre_registered_at": "2026-07-03T00:00:00Z",
        "hypotheses": [
            {"id": "H1_longshot_underpriced", "forward_verdict": "INSUFFICIENT_FORWARD"},
            {"id": "H2_midfav_overpriced", "forward_verdict": "CONFIRMED_FORWARD"},
        ],
        "verdict": "SHIP_REVIEW",
        "n_forward_games_graded": 25,
    }
    _write(tmp_path / "mlb" / "ingame_tail_verdict.json", doc)
    sb = fes.build_scoreboard(now=now)
    mlb_rows = [r for r in sb["rows"] if r["sport"] == "mlb" and r["gate"].startswith("tail_")]
    assert len(mlb_rows) == 2
    h2 = [r for r in mlb_rows if r["gate"] == "tail_H2_midfav_overpriced"][0]
    assert h2["verdict"] == "CONFIRMED_FORWARD"
    assert h2["forward_n"] == 25
    assert h2["distance_to_decidable"] == fes._NOW
    assert h2["days_accruing"] == 7.0


# ---------------------------------------------------------------- composer: absent

def test_composer_absent_file_degrades_honestly(tmp_path, monkeypatch):
    monkeypatch.setattr(fes, "DOMAINS_DIR", tmp_path)
    monkeypatch.setattr(fes, "TAIL_SPORTS", ["tennis"])
    sb = fes.build_scoreboard(now=datetime(2026, 7, 10, tzinfo=timezone.utc))
    rows = [r for r in sb["rows"] if r["sport"] == "tennis"]
    assert len(rows) == 2
    assert all(r["verdict"] == "ABSENT" for r in rows)
    assert all(r["distance_to_decidable"] == fes._UNKNOWN for r in rows)


# ---------------------------------------------------------------- composer: insufficient (zero accrual, future stamp)

def test_composer_insufficient_future_pre_registration(tmp_path, monkeypatch):
    monkeypatch.setattr(fes, "DOMAINS_DIR", tmp_path)
    monkeypatch.setattr(fes, "TAIL_SPORTS", ["wnba"])
    now = datetime(2026, 7, 4, tzinfo=timezone.utc)
    doc = {
        "pre_registered_at": "2026-07-04T12:00:00Z",  # in the future vs 'now'
        "hypotheses": [
            {"id": "H1_longshot_underpriced", "forward_verdict": "INSUFFICIENT_FORWARD"},
            {"id": "H2_midfav_overpriced", "forward_verdict": "INSUFFICIENT_FORWARD"},
        ],
        "verdict": "PENDING_FORWARD",
        "n_forward_games_graded": 0,
    }
    _write(tmp_path / "wnba" / "ingame_tail_verdict.json", doc)
    sb = fes.build_scoreboard(now=now)
    rows = [r for r in sb["rows"] if r["sport"] == "wnba"]
    assert all(r["forward_n"] == 0 for r in rows)
    assert all(r["distance_to_decidable"] == fes._NEVER for r in rows)
    assert all(r["days_accruing"] is not None and r["days_accruing"] < 0 for r in rows)


# ---------------------------------------------------------------- enrichment rows

def test_enrichment_row_reads_n_games(tmp_path, monkeypatch):
    monkeypatch.setattr(fes, "DOMAINS_DIR", tmp_path)
    monkeypatch.setattr(fes, "TAIL_SPORTS", [])
    now = datetime(2026, 7, 20, tzinfo=timezone.utc)
    doc = {
        "pre_registered_at": "2026-07-05T04:00:00Z",
        "verdict": "BETTER_THAN_BASELINE",
        "n_games": 9,
    }
    _write(tmp_path / "mlb" / "enrichment_gate_verdict.json", doc)
    _write(tmp_path / "soccer_intl" / "enrichment_gate_verdict.json",
           {"pre_registered_at": None, "verdict": "INSUFFICIENT_FORWARD", "n_games": 0})
    _write(tmp_path / "soccer_intl" / "enrichment_gate_verdict_staleq.json",
           {"pre_registered_at": None, "verdict": "PENDING", "n_rows": 0})
    sb = fes.build_scoreboard(now=now)
    gate_b = [r for r in sb["rows"] if r["gate"] == "enrichment_B_mlb_baseout"][0]
    assert gate_b["forward_n"] == 9
    assert gate_b["distance_to_decidable"] == fes._NOW  # 9 >= MIN_GAMES=8
    gate_c = [r for r in sb["rows"] if r["gate"] == "enrichment_C_stale_quote_covariate"][0]
    assert gate_c["sport"] == "cross_sport"
    assert gate_c["forward_n"] == 0


# ---------------------------------------------------------------- write/render smoke

def test_write_doc_and_render_smoke(tmp_path, monkeypatch):
    monkeypatch.setattr(fes, "DOMAINS_DIR", tmp_path)
    monkeypatch.setattr(fes, "TAIL_SPORTS", ["mlb"])
    doc = fes.build_scoreboard(now=datetime(2026, 7, 10, tzinfo=timezone.utc))
    out = tmp_path / "out.json"
    fes.write_doc(doc, path=out)
    reloaded = json.loads(out.read_text(encoding="utf-8"))
    assert reloaded["component"] == "forward_evidence_scoreboard"
    assert reloaded["edge_claimed"] is False
    text = fes.render(doc)
    assert "FORWARD-EVIDENCE SCOREBOARD" in text
    assert "edge_claimed=False" in text


def test_build_scoreboard_never_raises_on_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setattr(fes, "DOMAINS_DIR", tmp_path)
    monkeypatch.setattr(fes, "TAIL_SPORTS", ["mlb"])
    p = tmp_path / "mlb" / "ingame_tail_verdict.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not valid json", encoding="utf-8")
    sb = fes.build_scoreboard(now=datetime(2026, 7, 10, tzinfo=timezone.utc))
    assert sb["n_rows"] >= 1
