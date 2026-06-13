"""Tests for research_ledger + research_writeup (tmp_path I/O only; Py3.9)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "scripts" / "research_harness"
sys.path.insert(0, str(HARNESS))

from research_ledger import Ledger, ResearchFinding, VALID_VERDICTS  # noqa: E402
from research_writeup import render_writeup  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FINDINGS_FIXTURE: list[dict] = [
    {
        "sport": "tennis",
        "family": "tennis_abs_rest_diff",
        "hypothesis": "Absolute rest-day difference predicts ML outcome",
        "verdict": "REJECT",
        "evidence": {"n": 30616, "p_value": 0.174, "clv": None},
        "what_would_change_my_mind": "Positive CLV on >=2 independent corpora, FDR p<0.05",
    },
    {
        "sport": "tennis",
        "family": "tennis_elo_gap_magnitude",
        "hypothesis": "Elo gap magnitude as standalone signal",
        "verdict": "REJECT",
        "evidence": {"n": 30616, "p_value": 1.0, "null_pass": False},
        "what_would_change_my_mind": "A second corpus with positive CLV above vig",
    },
    {
        "sport": "soccer",
        "family": "soccer_over_under_poisson",
        "hypothesis": "Poisson-derived O/U-2.5 signal beats null shuffle",
        "verdict": "REJECT",
        "evidence": {"n": 12000, "splits": 3, "metric": "log_loss_delta"},
        "what_would_change_my_mind": "Real closing-line CLV improvement on 2+ seasons",
    },
    {
        "sport": "mlb",
        "family": "mlb_home_away_ml",
        "hypothesis": "Home/away ML split provides durable edge",
        "verdict": "DEFER",
        "evidence": {"n": 5000, "reason": "insufficient OOS data"},
        "what_would_change_my_mind": "Full season OOS corpus plus 2nd independent exchange",
    },
    {
        "sport": "nba",
        "family": "nba_ast_signal",
        "hypothesis": "AST signal produces positive CLV gated on reg season only",
        "verdict": "SHIP",
        "evidence": {"n": 8000, "clv": 0.05, "p_value": 0.03},
        "what_would_change_my_mind": "N/A — already shipped under full honest gate",
    },
]


def _make_findings() -> list[ResearchFinding]:
    return [ResearchFinding.from_dict(d) for d in FINDINGS_FIXTURE]


# ---------------------------------------------------------------------------
# ResearchFinding schema tests
# ---------------------------------------------------------------------------

def test_finding_key_is_tuple():
    f = ResearchFinding.from_dict(FINDINGS_FIXTURE[0])
    assert f.key == ("tennis", "tennis_abs_rest_diff", "Absolute rest-day difference predicts ML outcome")


def test_invalid_verdict_raises():
    with pytest.raises(ValueError, match="verdict must be one of"):
        ResearchFinding(
            sport="nba", family="x", hypothesis="h",
            verdict="BOGUS", evidence={},
            what_would_change_my_mind="something",
        )


def test_empty_what_would_change_raises():
    with pytest.raises(ValueError, match="what_would_change_my_mind"):
        ResearchFinding(
            sport="nba", family="x", hypothesis="h",
            verdict="REJECT", evidence={},
            what_would_change_my_mind="   ",
        )


def test_all_verdicts_valid():
    for v in VALID_VERDICTS:
        f = ResearchFinding(
            sport="nba", family="f", hypothesis="h",
            verdict=v, evidence={},
            what_would_change_my_mind="something",
        )
        assert f.verdict == v


def test_to_dict_roundtrip():
    f = ResearchFinding.from_dict(FINDINGS_FIXTURE[2])
    d = f.to_dict()
    f2 = ResearchFinding.from_dict(d)
    assert f.key == f2.key
    assert f2.verdict == "REJECT"


# ---------------------------------------------------------------------------
# Ledger: append + dedup + idempotency
# ---------------------------------------------------------------------------

def test_append_writes_all_findings(tmp_path: Path):
    ledger = Ledger(path=tmp_path / "findings.jsonl")
    findings = _make_findings()
    written = [ledger.append(f) for f in findings]
    assert all(written), "All unique findings should be written"
    assert len(ledger.all_findings()) == len(findings)


def test_dedup_same_key_skipped(tmp_path: Path):
    ledger = Ledger(path=tmp_path / "findings.jsonl")
    f = ResearchFinding.from_dict(FINDINGS_FIXTURE[0])
    assert ledger.append(f) is True
    assert ledger.append(f) is False  # duplicate
    assert len(ledger.all_findings()) == 1


def test_idempotent_reload(tmp_path: Path):
    p = tmp_path / "findings.jsonl"
    ledger1 = Ledger(path=p)
    for f in _make_findings():
        ledger1.append(f)

    # Reload from disk; same keys should not be duplicated
    ledger2 = Ledger(path=p)
    for f in _make_findings():
        result = ledger2.append(f)
        assert result is False, "Re-appending existing keys must be deduped"

    assert len(ledger2.all_findings()) == len(FINDINGS_FIXTURE)


def test_dedup_different_hypothesis_allowed(tmp_path: Path):
    """Two findings with same sport+family but different hypothesis are distinct."""
    ledger = Ledger(path=tmp_path / "findings.jsonl")
    f1 = ResearchFinding(
        sport="tennis", family="x", hypothesis="hyp A",
        verdict="REJECT", evidence={},
        what_would_change_my_mind="second corpus",
    )
    f2 = ResearchFinding(
        sport="tennis", family="x", hypothesis="hyp B",
        verdict="REJECT", evidence={},
        what_would_change_my_mind="second corpus",
    )
    assert ledger.append(f1) is True
    assert ledger.append(f2) is True
    assert len(ledger.all_findings()) == 2


# ---------------------------------------------------------------------------
# JSONL round-trip
# ---------------------------------------------------------------------------

def test_jsonl_round_trip(tmp_path: Path):
    p = tmp_path / "findings.jsonl"
    ledger = Ledger(path=p)
    for f in _make_findings():
        ledger.append(f)

    # Read raw lines and verify valid JSON
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == len(FINDINGS_FIXTURE)
    for line in lines:
        obj = json.loads(line)
        assert "sport" in obj
        assert "verdict" in obj
        assert obj["verdict"] in VALID_VERDICTS


def test_jsonl_fields_present(tmp_path: Path):
    p = tmp_path / "findings.jsonl"
    ledger = Ledger(path=p)
    ledger.append(ResearchFinding.from_dict(FINDINGS_FIXTURE[0]))
    obj = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    for field in ("sport", "family", "hypothesis", "verdict", "evidence",
                  "what_would_change_my_mind", "dated"):
        assert field in obj, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# Summarize counts
# ---------------------------------------------------------------------------

def test_summarize_counts(tmp_path: Path):
    ledger = Ledger(path=tmp_path / "findings.jsonl")
    for f in _make_findings():
        ledger.append(f)
    s = ledger.summarize()
    assert s["total"] == 5
    assert s["by_verdict"]["REJECT"] == 3
    assert s["by_verdict"]["DEFER"] == 1
    assert s["by_verdict"]["SHIP"] == 1


def test_summarize_by_sport(tmp_path: Path):
    ledger = Ledger(path=tmp_path / "findings.jsonl")
    for f in _make_findings():
        ledger.append(f)
    s = ledger.summarize()
    assert s["by_sport"]["tennis"]["REJECT"] == 2
    assert s["by_sport"]["soccer"]["REJECT"] == 1
    assert s["by_sport"]["mlb"]["DEFER"] == 1
    assert s["by_sport"]["nba"]["SHIP"] == 1


def test_summarize_empty_ledger(tmp_path: Path):
    ledger = Ledger(path=tmp_path / "findings.jsonl")
    s = ledger.summarize()
    assert s["total"] == 0
    for v in VALID_VERDICTS:
        assert s["by_verdict"][v] == 0


# ---------------------------------------------------------------------------
# Writeup rendering
# ---------------------------------------------------------------------------

def test_writeup_renders_all_findings(tmp_path: Path):
    ledger = Ledger(path=tmp_path / "findings.jsonl")
    for f in _make_findings():
        ledger.append(f)
    md = render_writeup(ledger)
    assert "tennis" in md.lower()
    assert "soccer" in md.lower()
    assert "mlb" in md.lower()
    assert "nba" in md.lower()


def test_writeup_honest_no_edge_framing(tmp_path: Path):
    ledger = Ledger(path=tmp_path / "findings.jsonl")
    for f in _make_findings():
        ledger.append(f)
    md = render_writeup(ledger)
    md_lower = md.lower()
    assert "no edge is claimed" in md_lower, "Must contain honest no-edge disclaimer"
    assert "market efficient" in md_lower or "market efficiency" in md_lower, \
        "Must reference market efficiency thesis"
    assert "reject" in md_lower, "Must mention REJECT verdicts"


def test_writeup_reject_findings_visible(tmp_path: Path):
    ledger = Ledger(path=tmp_path / "findings.jsonl")
    for f in _make_findings():
        ledger.append(f)
    md = render_writeup(ledger)
    assert "tennis_abs_rest_diff" in md
    assert "tennis_elo_gap_magnitude" in md
    assert "soccer_over_under_poisson" in md


def test_writeup_ship_representable(tmp_path: Path):
    """A SHIP verdict is valid and renders in the writeup."""
    ledger = Ledger(path=tmp_path / "findings.jsonl")
    ship = ResearchFinding.from_dict(FINDINGS_FIXTURE[4])  # nba SHIP
    assert ship.verdict == "SHIP"
    ledger.append(ship)
    md = render_writeup(ledger)
    assert "nba_ast_signal" in md
    assert "SHIP" in md


def test_writeup_what_would_change_rendered(tmp_path: Path):
    ledger = Ledger(path=tmp_path / "findings.jsonl")
    ledger.append(ResearchFinding.from_dict(FINDINGS_FIXTURE[0]))
    md = render_writeup(ledger)
    assert "What would change my mind" in md


def test_writeup_accepts_plain_list():
    """render_writeup also accepts a raw list of findings, not just a Ledger."""
    findings = _make_findings()
    md = render_writeup(findings)
    assert "no edge is claimed" in md.lower()
    assert len(findings) > 0


def test_writeup_empty_ledger(tmp_path: Path):
    ledger = Ledger(path=tmp_path / "findings.jsonl")
    md = render_writeup(ledger)
    assert "No findings recorded yet" in md
    assert "no edge is claimed" in md.lower()
