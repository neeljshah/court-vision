"""Per-file test for memory_claim_guard (per-file tests ONLY -- full suite freezes the box)."""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.memory_claim_guard import (render, retracted_tokens, scan, scan_file)


def test_tokens_parse_from_the_rule_file():
    toks = retracted_tokens()
    assert toks, "no retracted numbers parsed from .claude/rules/no-edge-claims.md"
    assert "+18.38%" in toks and "0.119" in toks


def test_bare_claim_is_flagged(tmp_path: Path):
    f = tmp_path / "bad.md"
    f.write_text("The model returns +18.38% ROI on walk-forward bets.", encoding="utf-8")
    assert scan_file(f, ["+18.38%"]) == ["+18.38%"]


def test_retraction_framing_is_allowed(tmp_path: Path):
    f = tmp_path / "good.md"
    f.write_text("The +18.38% headline was RETRACTED -- a market-follow artifact.",
                 encoding="utf-8")
    assert scan_file(f, ["+18.38%"]) == []


def test_scan_reports_offenders_and_render_names_them(tmp_path: Path):
    (tmp_path / "clean.md").write_text("nothing to see", encoding="utf-8")
    (tmp_path / "dirty.md").write_text("we hit 78.11 accuracy in play", encoding="utf-8")
    hits = scan(tmp_path)
    assert [h["file"] for h in hits] == ["dirty.md"]
    out = render(hits, 6, tmp_path)
    assert "dirty.md" in out and "78.11" in out and "ASSERT A RETRACTED CLAIM" in out


def test_clean_render_says_clean(tmp_path: Path):
    assert "CLEAN" in render([], 6, tmp_path)
