"""Tests for scripts.platformkit.brain_audit — fixture tree, no real vault."""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.brain_audit import audit_tree, scan_text


def _w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_scan_text_flags_edge_claims_only():
    assert scan_text("Guaranteed +7% edge, beats the market.")
    # honest denials are NOT edge claims
    assert scan_text("Markets efficient; NO model edge claimed; calibration is not edge.") == []
    # 'profitable' is tactically ambiguous in scouting prose -> NOT flagged
    assert scan_text("Crashing the offensive glass is profitable here.") == []
    # a CAVEATED edge mention (the documented AST finding) is NOT a claim
    assert scan_text(
        "the only prop edge OOS is gated assists at roughly +5% ROI, regular-season "
        "only; none of this is a validated betting signal, not to size bets.") == []


def test_clean_tree_passes(tmp_path):
    _w(tmp_path / "NBA" / "_Read.md",
       "# NBA\n> HONEST: markets efficient; NO model edge claimed; calibration is not edge.\n"
       "Archetypes and schemes only.\n")
    _w(tmp_path / "MLB" / "_Model_Card.md",
       "# MLB Model Card\n> ACCURACY != EDGE; neither model beats the close.\nBrier 0.244.\n")
    rep = audit_tree(tmp_path)
    assert rep["n_files"] == 2
    assert rep["clean"] is True and rep["n_flagged"] == 0
    assert rep["n_with_honest_banner"] == 2


def test_planted_violation_is_flagged(tmp_path):
    _w(tmp_path / "NBA" / "_Read.md", "# NBA\nclean, no edge claimed.\n")
    _w(tmp_path / "NBA" / "_Bad.md",
       "# Bad\nThis play is guaranteed profitable, +12% ROI, beats the market.\n")
    rep = audit_tree(tmp_path)
    assert rep["clean"] is False and rep["n_flagged"] == 1
    assert rep["flagged"][0]["file"] == "NBA/_Bad.md"
    assert rep["flagged"][0]["matches"]


def test_missing_root(tmp_path):
    rep = audit_tree(tmp_path / "does_not_exist")
    assert rep["clean"] is True and rep["n_files"] == 0 and "error" in rep


def test_negated_edge_tokens_are_not_claims():
    from scripts.platformkit.brain_audit import scan_text
    # explicit denials -> NOT flagged (the W87 self-catch case)
    assert scan_text("None of this beats the market — it is calibration only.") == []
    assert scan_text("The model never beats the market close.") == []
    assert scan_text("This is not guaranteed.") == []
    # genuine un-negated claims STILL flagged
    assert scan_text("This play is guaranteed, +12% ROI, beats the market.")
