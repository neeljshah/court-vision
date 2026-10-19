"""Tests for claim_consistency: python -m pytest scripts/platformkit/eval_gate/test_claim_consistency.py -q"""
from __future__ import annotations

import re
from pathlib import Path

from scripts.platformkit.eval_gate.claim_consistency import check, load, main, scan_text

ROOT = Path(__file__).resolve().parents[3]
CFG = load(ROOT)

# The three lines as they read before the 2026-10-06 correction.
PRE_NOTE = [
    "| 4-sport real-data edge hunt: pregame MATCHES the Shin-devigged close within noise on "
    "team-strength markets across 6 independent corpora (NBA/MLB moneyline, soccer O/U) |",
    "  the calibrated model MATCHES the devigged close within noise on team-strength markets and EVERY",
    "**MARKET-EFFICIENT HERE** on team-strength markets: where we have power, the calibrated "
    "forecast MATCHES the devigged close within noise -- the expected, honest success state",
]


def _kinds(findings):
    return [f.split(" ", 1)[0] for f in findings]


def test_tracked_surfaces_are_clean():
    assert check(ROOT) == []
    assert main(["--repo-root", str(ROOT)]) == 0


def test_pre_note_lines_are_stale_and_corrected_lines_pass():
    found = scan_text("old.md", "\n".join(PRE_NOTE), CFG)
    assert _kinds(found) == ["STALE"] * 3
    fixed = [l + " (corrected 2026-10-06 from DM_RECOMPUTE_2026-09-24)" for l in PRE_NOTE]
    assert scan_text("new.md", "\n".join(fixed), CFG) == []


def test_changed_interval_and_verdict_are_caught(tmp_path):
    good = "| MLB | 13,992 | +0.0039, 95% CI [+0.0028, +0.0051], DM p 3.6e-12 | TRAILS_CLOSE |"
    assert scan_text("s.md", good, CFG) == []
    bad_ci = good.replace("+0.0051", "+0.0061")
    bad_verdict = good.replace("TRAILS_CLOSE", "MATCHES_CLOSE")
    planted = tmp_path / "fourth_surface.md"
    planted.write_text(bad_ci + "\n" + bad_verdict + "\n", encoding="utf-8")
    found = check(ROOT, [str(planted)])
    assert len(found) == 2 and all(f.startswith("DISAGREE") for f in found)
    assert main(["--repo-root", str(ROOT), str(planted)]) == 1


def test_retracted_figure_only_inside_framing():
    assert _kinds(scan_text("r.md", "Headline: +18.38% on the season.", CFG)) == ["RETRACTED"]
    assert scan_text("r.md", "The +18.38% figure was retracted (grading artifact).", CFG) == []
    assert scan_text("r.md", "## Retracted figures\n+18.38% pregame", CFG) == []
    assert scan_text("r.md", "endQ3 Brier 0.1191 later fixed", CFG) == []  # 0.119 not a prefix hit


def test_strict_language_only_on_methods_pages():
    line = "This shows a clear edge and ROI."
    assert scan_text("x.md", line, CFG) == []
    assert _kinds(scan_text("x.md", line, CFG, strict=True)) == ["LANGUAGE", "LANGUAGE"]


def test_figures_match_their_source_artifacts():
    for fig in CFG["figures"]:
        src = (ROOT / fig["source"]).read_text(encoding="utf-8")
        printed = {round(float(x), 4) for x in re.findall(r"(?<![\d.])\d\.\d{4,5}(?!\d)", src)}
        for k in ("model", "close", "gap"):
            if k in fig:  # the source may print 5 decimals; compare at the canonical 4
                assert round(fig[k], 4) in printed, (fig["key"], k)
        if "ci95" in fig and "DM_RECOMPUTE" in fig["source"]:
            lo, hi = fig["ci95"]
            assert "[%+.4f, %+.4f]" % (lo, hi) in src, fig["key"]
            assert fig["dm_p"] in src and fig["verdict"] in src, fig["key"]
        if "ttl_30_fills_credited" in fig:
            assert "'ttl_30_fills_credited': '%d" % fig["ttl_30_fills_credited"] in src


def test_full_default_surface_is_clean():
    """Default surface = every tracked docs/**/*.md + README + EVIDENCE, minus local-only trees."""
    from scripts.platformkit.eval_gate.claim_consistency import default_surfaces
    surf = default_surfaces(ROOT, CFG)
    assert {"README.md", "EVIDENCE.md", "docs/QUANT_BRIEF.md", "docs/guide/10_HONEST_LIMITS.md"} <= set(surf)
    assert not [s for s in surf if s.startswith(("docs/research/", "docs/strategy/"))]
    assert len(surf) > 100
    assert check(ROOT) == []
