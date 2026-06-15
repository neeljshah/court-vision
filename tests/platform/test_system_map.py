"""Per-file test for scripts/platformkit/system_map.py.

Run: python -m pytest tests/platform/test_system_map.py -q
"""
from __future__ import annotations

from scripts.platformkit import system_map as mod


def test_build_covers_all_sports():
    m = mod.build()
    sports = {r["sport"] for r in m["rows"]}
    assert sports == {"NBA", "MLB", "SOCCER", "TENNIS"}
    # every sport has a concrete repricer wired (no not_wired stubs)
    for s, name in m["repricers"].items():
        assert name.endswith("Repricer"), f"{s} repricer = {name}"


def test_render_markdown_organized():
    md = mod.render_markdown(mod.build())
    assert "System Map" in md
    assert "Beat-the-close (measured)" in md
    for s in ("NBA", "MLB", "SOCCER", "TENNIS"):
        assert f"### {s}" in md
    assert "In-game = the real edge" in md
    assert "honest bottom line" in md.lower()
