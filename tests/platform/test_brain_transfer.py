"""Tests for scripts.platformkit.brain_transfer — cross-sport TRANSFER node.

Builds a tiny synthetic _Organized tree (2 sports, a couple Drivers/Mechanisms +
_WhatWins each), runs build_transfer(tmp, write=True), and asserts:
  (a) _Index/_Cross_Sport_Transfer.md is written with >=1 SHAPE row
  (b) wikilinks resolve to REAL driver/mechanism files on disk
  (c) PERSON-FREE (no player/team names from the fixtures)
  (d) NO edge tokens (passes the REAL no-edge audit; no roi/beats market/guaranteed)
  (e) idempotent (run twice -> byte-identical)
Pure stdlib; no pandas / network.
"""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.brain_transfer import (
    build_transfer,
    _classify,
    _SHAPE_ORDER,
)
from scripts.platformkit.brain_audit import scan_text


def _w(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_organized(root: Path) -> None:
    """Two-sport synthetic tree mirroring the real Drivers/Mechanisms layout.

    Fixtures deliberately mention player/team names ONLY inside the source-style
    headings to PROVE the transfer node does not echo them (it uses slug+H1, and
    the H1s here are person-free, structural labels — as the real notes are)."""
    # --- MLB ---
    mlb = root / "MLB"
    _w(mlb / "_WhatWins.md", "# MLB — What Wins & Why\n\nDriver taxonomy.\n")
    _w(mlb / "Drivers" / "big_inning.md",
       "# MLB Driver — BIG_INNING\n\nOne crooked inning decides most games.\n")
    _w(mlb / "Drivers" / "routine.md",
       "# MLB Driver — ROUTINE\n\nThe base-rate game shape.\n")
    _w(mlb / "Mechanisms" / "big_inning_x_total_runs.md",
       "# MLB Mechanism — Big-Inning x Total-Runs Interaction\n\nShape control.\n")
    _w(mlb / "Mechanisms" / "_Mechanisms.md", "# MLB Mechanisms Index\n")
    # --- Soccer ---
    soc = root / "Soccer"
    _w(soc / "_WhatWins.md", "# Soccer — What Wins & Why\n\nDriver taxonomy.\n")
    _w(soc / "Drivers" / "finishing_variance.md",
       "# Soccer Driver — FINISHING_VARIANCE\n\nGoals diverge from shots; regresses.\n")
    _w(soc / "Drivers" / "blowout.md",
       "# Soccer Driver — BLOWOUT\n\nClear quality gap; one-sided.\n")
    _w(soc / "Mechanisms" / "red_card_x_finishing.md",
       "# Soccer Mechanism — Red-Card Event x Finishing-Variance Suppression\n\nSwing.\n")
    _w(soc / "Mechanisms" / "_Mechanisms.md", "# Soccer Mechanisms Index\n")


# ---------------------------------------------------------------------------
# classification unit
# ---------------------------------------------------------------------------

def test_classify_known_shapes():
    assert _classify("big_inning", "BIG_INNING") == "distribution_shape_variance"
    assert _classify("finishing_variance", "FINISHING_VARIANCE") == \
        "mean_reversion_regression"
    assert _classify("blowout", "BLOWOUT") == "dominance_vs_variance"
    assert _classify("routine", "ROUTINE") == "structural_rating_baseline"
    assert _classify("red_card_swing", "Red-Card swing") == "situational_leverage"
    assert _classify("surface_x_serve_hold", "Surface x Serve") in _SHAPE_ORDER


def test_classify_unknown_returns_none():
    assert _classify("zzz_unmapped", "Totally Unmapped Thing") is None


# ---------------------------------------------------------------------------
# build_transfer (write=False, in-memory)
# ---------------------------------------------------------------------------

def test_build_returns_shapes_and_links(tmp_path):
    _make_organized(tmp_path)
    rep = build_transfer(organized_root=tmp_path, write=False)
    assert rep["n_links"] >= 1
    assert rep["n_shapes"] >= 1
    assert set(rep["sports"]) == {"MLB", "Soccer"}
    # by_shape counts the right buckets
    assert "distribution_shape_variance" in rep["by_shape"]
    assert "mean_reversion_regression" in rep["by_shape"]


def test_build_missing_root_is_honest():
    rep = build_transfer(organized_root=Path("does/not/exist"), write=False)
    assert rep["n_links"] == 0 and "error" in rep


# ---------------------------------------------------------------------------
# write path
# ---------------------------------------------------------------------------

def test_writes_file_with_shape_row(tmp_path):
    _make_organized(tmp_path)
    rep = build_transfer(organized_root=tmp_path, write=True)
    out = tmp_path / "_Index" / "_Cross_Sport_Transfer.md"
    assert out.is_file(), "transfer node not written"
    assert rep["path"] == str(out)
    text = out.read_text(encoding="utf-8")
    # >=1 SHAPE row in the table (a bolded shape title in a table row)
    shape_rows = [ln for ln in text.splitlines()
                  if ln.startswith("| **") and ln.rstrip().endswith("|")]
    assert len(shape_rows) >= 1, "no SHAPE rows in the table"


def test_wikilinks_resolve_to_real_files(tmp_path):
    _make_organized(tmp_path)
    build_transfer(organized_root=tmp_path, write=True)
    text = (tmp_path / "_Index" / "_Cross_Sport_Transfer.md").read_text(
        encoding="utf-8")
    # every driver/mechanism link target must resolve to a real .md on disk.
    import re
    # links look like [[MLB/Drivers/big_inning\|BIG_INNING]]
    targets = re.findall(r"\[\[([A-Za-z]+/(?:Drivers|Mechanisms)/[a-z0-9_]+)\\\|",
                         text)
    assert targets, "no resolving driver/mechanism wikilinks found"
    for t in targets:
        assert (tmp_path / f"{t}.md").is_file(), f"dangling link target: {t}"


def test_person_free(tmp_path):
    _make_organized(tmp_path)
    build_transfer(organized_root=tmp_path, write=True)
    text = (tmp_path / "_Index" / "_Cross_Sport_Transfer.md").read_text(
        encoding="utf-8").lower()
    # no per-player / per-team names appear (none in fixtures, but assert anyway)
    for token in ("booker", "durant", "phx", "lal", "yankees", "arsenal"):
        assert token not in text, f"person/team token leaked: {token}"


def test_no_edge_tokens_real_audit(tmp_path):
    _make_organized(tmp_path)
    rep = build_transfer(organized_root=tmp_path, write=True)
    # passes the REAL no-edge audit (W96 lesson: assert the real audit, not a list)
    assert scan_text(rep["md"]) == [], "audit flagged edge claims"
    text = (tmp_path / "_Index" / "_Cross_Sport_Transfer.md").read_text(
        encoding="utf-8")
    assert scan_text(text) == []
    low = text.lower()
    for tok in ("roi", "beats the market", "beats market", "guaranteed",
                "proven edge"):
        assert tok not in low, f"edge token leaked: {tok}"
    # honest banner present
    assert "no edge claimed" in low
    assert "calibration is not edge" in low
    assert "markets efficient" in low


def test_idempotent_byte_identical(tmp_path):
    _make_organized(tmp_path)
    build_transfer(organized_root=tmp_path, write=True)
    out = tmp_path / "_Index" / "_Cross_Sport_Transfer.md"
    first = out.read_bytes()
    build_transfer(organized_root=tmp_path, write=True)
    second = out.read_bytes()
    assert first == second, "build_transfer is not idempotent"


def test_does_not_write_when_no_links(tmp_path):
    # empty tree -> no driver/mechanism notes -> nothing written
    (tmp_path / "NBA").mkdir(parents=True)
    rep = build_transfer(organized_root=tmp_path, write=True)
    assert rep["n_links"] == 0
    assert rep["path"] is None
    assert not (tmp_path / "_Index" / "_Cross_Sport_Transfer.md").exists()
