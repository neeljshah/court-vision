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


# --- canonical_counts (commits, modules, findings, forward window, G6 wording) ---
from scripts.platformkit.eval_gate.claim_consistency import explain, scan_counts  # noqa: E402


def test_commit_count_drift_caught_and_dated_history_passes():
    assert _kinds(scan_counts("c.md", "built with 6,800+ commits since March", CFG)) == ["COUNT"]
    assert scan_counts("c.md", "holds 6,508 commits from 2026-03-09 to 2026-10-19", CFG) == []
    assert scan_counts("c.md", "5,504 commits, Mar-Sep 2026", CFG) == []  # dated audit count
    assert _kinds(scan_counts("c.md", "5,504 commits in the repo", CFG)) == ["COUNT"]
    assert scan_counts("c.md", "the 8,600+ commits figure was retracted", CFG) == []


def test_module_count_drift_caught():
    assert _kinds(scan_counts("m.md", "74 analytics modules", CFG)) == ["COUNT"]
    assert _kinds(scan_counts("m.md", "54 published source modules", CFG)) == ["COUNT"]
    assert scan_counts("m.md", "77 measurement modules and ~130 modules of research code", CFG) == []


def test_findings_count_drift_caught():
    assert _kinds(scan_counts("f.md", "29 papers, 18 findings", CFG)) == ["COUNT"]
    assert scan_counts("f.md", "16 titled findings", CFG) == []


def test_forward_window_drift_caught():
    assert _kinds(scan_counts("w.md", "## 5. Forward paper record 2026-10-06 .. 2026-10-18", CFG)) == ["COUNT"]
    assert _kinds(scan_counts("w.md", "(PACKET.md#5-forward-paper-record-2026-10-06--2026-10-18-as-of)", CFG)) == ["COUNT"]
    assert scan_counts("w.md", "Forward paper record 2026-10-06 to 2026-10-22", CFG) == []


def test_g6_zero_qualifying_weeks_is_forbidden():
    assert _kinds(scan_counts("g.md", "G6 has zero qualifying weeks as of 2026-10-19", CFG)) == ["WORDING"]
    assert scan_counts("g.md", "G6 has not started as of 2026-10-19 (zero weeks collected)", CFG) == []


def test_count_check_runs_only_on_count_surfaces(tmp_path):
    planted = tmp_path / "other.md"
    planted.write_text("6,800+ commits\n", encoding="utf-8")
    assert check(ROOT, [str(planted)], defaults=False) == []  # not a count surface
    assert "AGENTS.md" in CFG["surfaces"]  # retracted-figure scan covers AGENTS.md too


def test_counts_match_their_sources():
    by = {f["key"]: f for f in CFG["canonical_counts"]["figures"]}
    for f in by.values():
        assert f["source"] and re.match(r"\d{4}-\d{2}-\d{2}$", f["as_of"]), f["key"]
    import json
    man = json.loads((ROOT / "webapp/public/data/showcase/site_manifest.json").read_text(encoding="utf-8"))
    assert man["module_count"] == by["published_module_count"]["value"]
    pages = [p for p in (ROOT / "webapp/app/(analytics)/analytics/findings").glob("*/page.tsx")
             if "RedirectStub" not in p.read_text(encoding="utf-8")]  # same rule as webapp/lib/figures.test.ts
    assert len(pages) == by["titled_findings_count"]["value"]


def test_explain_prints_every_figure_with_source(capsys):
    lines = explain(CFG)
    keys = [f["key"] for f in CFG["canonical_counts"]["figures"] + CFG["figures"]]
    assert all(any(l.startswith(k + " = ") and " <- " in l for l in lines) for k in keys)
    assert main(["--repo-root", str(ROOT), "--explain"]) == 0
    assert "public_commit_count = 6556" in capsys.readouterr().out


def test_real_repo_is_green(capsys):
    assert main(["--repo-root", str(ROOT)]) == 0
    assert "claim_consistency: 0 finding(s)" in capsys.readouterr().out


def test_framing_and_unless_apply_to_the_figures_own_clause():
    # codex counterexamples (REVIEW_tooling_20261020): both returned no findings before
    assert _kinds(scan_counts("f.md", "18 findings (uncorrected)", CFG)) == ["COUNT"]
    assert _kinds(scan_counts(
        "m.md", "74 analytics modules; 23 modules in the recorded-analytics inventory", CFG)) == ["COUNT"]
    assert _kinds(scan_counts("f.md", "18 findings. The old 20 findings figure was retracted.", CFG)) == ["COUNT"]
    assert _kinds(scan_counts("f.md", "| 18 findings | superseded |", CFG)) == ["COUNT"]
    assert scan_counts("m.md", "23 modules in the recorded-analytics inventory", CFG) == []


def test_historical_commit_count_needs_its_own_date_on_the_clause():
    assert _kinds(scan_counts("c.md", "5,504 commits, latest audit date 2026-10-19", CFG)) == ["COUNT"]
    assert _kinds(scan_counts("c.md", "| 5,504 commits | 2026-09-07 |", CFG)) == ["COUNT"]
    assert scan_counts("c.md", "5,504 commits at 2026-09-07", CFG) == []
    assert scan_counts("c.md", "An intensive solo build (5,504 commits, Mar\u2013Sep 2026).", CFG) == []
    assert scan_counts("c.md", "5,504 commits as of Sep 2026", CFG) == []


def test_forward_window_end_any_iso_date():
    assert _kinds(scan_counts("w.md", "record 2026-10-06 to 2026-11-01", CFG)) == ["COUNT"]
    assert _kinds(scan_counts("w.md", "record 2026-10-06 through 2027-10-16", CFG)) == ["COUNT"]
