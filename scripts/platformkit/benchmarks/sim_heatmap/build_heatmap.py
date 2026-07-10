"""scripts.platformkit.benchmarks.sim_heatmap.build_heatmap -- cross-sport sim
state-cell PIT/CRPS heatmap.

Reads each atomic engine's OWN already-rerunnable walk-forward validation
artifact (data/frontend/ops/*.json, written by that engine's own
validate.py / validate_v2.py / validate_v3.py) and reshapes its per-bucket
PIT-deviation + CRPS + n into one normalized cross-sport schema, so the
worst state cells are NAMED (not buried in per-engine JSON) and tracked
release over release. edge_claimed:false throughout -- sharpness/calibration
only, never a $/edge claim.

ponytail: this tool reads the engines' own validated eval-path OUTPUT rather
than re-deriving the sim -- that logic already lives in domains/*/*/validate*.py
and is independently fitted + tested there (per-file tests, heavy-IO-is-CLI-only,
same convention as scripts/platformkit/benchmarks/crps_market). Default is
read-cached (fast); pass --refresh to actually re-invoke each engine's own
run() and regenerate its ops JSON before aggregating.

Coverage ceiling (named, not silently papered over): NBA sim2 and the MLB
pitch engine simulate FROM a mid-game snapshot, so real (period|inning x
margin) state cells exist with per-bucket PIT+CRPS+n. tennis.point_engine and
soccer.chain_engine only simulate WHOLE matches from serve-1 / kickoff (no
mid-match restart hook in match_sim.py) -- their rows are one honest
whole-match pseudo-cell with a coverage_gap note, not fabricated buckets.
Upgrade path: add a simulate-from-set-score / simulate-from-minute-score
entry point to each engine's match_sim.py (a real build, not this lane).

Also note: neither MLB harness computes CRPS per bucket today (only pooled
game-level CRPS) -- flagged per-sport as crps_per_bucket:false, not faked.

CLI: cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.benchmarks.sim_heatmap.build_heatmap [--refresh]
Test: python -m pytest scripts/platformkit/benchmarks/sim_heatmap/test_build_heatmap.py -q
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO = Path(__file__).resolve().parents[4]
OPS = _REPO / "data" / "frontend" / "ops"
REPORT = _REPO / "docs" / "research" / "sim_heatmap_2026-07-11.md"

# Manual cross-ref of the knowledge ledgers (domains/<sport>/knowledge/mechanisms.md)
# against the worst NAMED bucket per sport. Queue-only: does NOT build a fix.
MECHANISM_CROSSREF = {
    "nba": {
        "bucket_hint": "P3|m3",
        "note": ("no CONFIRMED mechanism specifically targets Q3-near-even-margin "
                 "conditioning; nearest analogs (#18 clutch usage amplification, "
                 "clutch rotation shortening) are LATE-GAME clutch, not Q3 -- a "
                 "Q3-specific state mechanism is a ledger GAP, not yet probed."),
    },
    "mlb": {
        "bucket_hint": "inn7|m2",
        "note": ("CONFIRMED mechanism #29 'high-leverage strand prevention' "
                 "(domains/mlb/knowledge/validate_situational_state.py::"
                 "high_leverage_strand_prevention) -- strikeout-heavy relievers "
                 "strand RISP at a higher rate late/close -- is NOT wired into "
                 "bullpen.py's reliever-quality pooling; conditioning the "
                 "inn7-home-lead removal/pool on reliever K-rate could reduce "
                 "variance in exactly this bucket."),
    },
    "tennis": {
        "bucket_hint": None,
        "note": ("no state-cell bucket exists yet (coverage gap). If built, "
                 "#3 'pressure-point population dip' (CONFIRMED) is the nearest "
                 "score-state-conditioned mechanism already in the ledger to "
                 "cross-check against a per-set/score bucket."),
    },
    "soccer": {
        "bucket_hint": None,
        "note": ("no state-cell bucket exists yet (coverage gap). If built, "
                 "#9 'leading-team defensive shell (game-state shot suppression)' "
                 "(CONFIRMED, reversed direction) is the nearest score-state "
                 "mechanism already in the ledger to cross-check against a "
                 "per-minute/score bucket."),
    },
}


def _load(name: str) -> Optional[dict]:
    p = OPS / name
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _worst(buckets: List[dict], key: str = "pit_dev_baseline") -> Optional[dict]:
    rows = [b for b in buckets if b.get(key) is not None]
    return max(rows, key=lambda b: b[key]) if rows else None


def collect_nba(refresh: bool = False) -> Dict[str, Any]:
    if refresh:
        from domains.basketball_nba.sim2.validate_v3 import run as _run
        _run()
    doc = _load("nba_sim2_v3_validation.json")
    if doc is None:
        return {"sport": "nba", "engine": "sim2_v2_v3", "coverage_gap": "no cached artifact; run --refresh", "buckets": []}
    src = doc["panel_A_B_pit_crps"]
    buckets = []
    for k, v in sorted(src["buckets"].items()):
        buckets.append({"bucket": k, "n": v["n"], "pit_dev_baseline": v["pit_dev_v2"],
                        "pit_dev_variant": v["pit_dev_v3"], "crps_baseline": v["crps_v2"],
                        "crps_variant": v["crps_v3"],
                        "regressed_under_variant": v["pit_dev_v3"] > v["pit_dev_v2"]})
    named = {k: v for k, v in src["named"].items() if v}
    return {"sport": "nba", "engine": "sim2 (v2=production baseline, v3=composite-conditioner variant)",
            "corpus": "fit %s, test %s (walk-forward)" % (doc["fit_seasons"], doc["test_season"]),
            "crps_per_bucket": True, "buckets": buckets,
            "regression_anchors": named, "worst_bucket": _worst(buckets),
            "mechanism_crossref": MECHANISM_CROSSREF["nba"]}


def collect_mlb(refresh: bool = False) -> Dict[str, Any]:
    if refresh:
        from domains.mlb.pitch_engine.validate import run as _run1
        from domains.mlb.pitch_engine.validate_v2 import run as _run2
        _run1(); _run2()
    v1 = _load("mlb_pitch_engine_v1.json")
    v2 = _load("mlb_pitch_engine_v2.json")
    buckets = []
    if v1 is not None:
        pd = v1["panel_C_game_pit_crps"]["panel_D_state_conditional_pit"]
        for k, v in sorted(pd.items()):
            buckets.append({"bucket": k, "n": v["n"], "pit_dev_baseline": v["uniformity_dev"],
                            "pit_dev_variant": None, "crps_baseline": None, "crps_variant": None,
                            "regressed_under_variant": None})
    anchors = None
    if v2 is not None:
        anchors = {k: {"n": v["v1"]["n"], "pit_dev_v1": v["v1"]["uniformity_dev"],
                       "pit_dev_v2_bullpen_seam": v["v2"]["uniformity_dev"],
                       "regressed_under_v2": v["v2"]["uniformity_dev"] > v["v1"]["uniformity_dev"]}
                  for k, v in v2["state_conditional_inn7_buckets"].items()}
    return {"sport": "mlb", "engine": "pitch_engine (v1=production baseline; v2=bullpen-seam variant, inn7 only)",
            "corpus": "v1 buckets: fit 2023/test 2024. v2 anchors: fit 2023-2025/test 2026 (different corpus, do not compare magnitudes across)",
            "crps_per_bucket": False, "buckets": buckets,
            "regression_anchors": anchors, "worst_bucket": _worst(buckets),
            "mechanism_crossref": MECHANISM_CROSSREF["mlb"]}


def _whole_match_gap(sport: str, engine: str, panel: dict, corpus: str) -> Dict[str, Any]:
    m = panel["model"]
    brier_key = "brier_match_winner" if "brier_match_winner" in m else "brier_home_win"
    row = {"bucket": "whole_match (no mid-match restart hook)", "n": m["n"],
           "pit_dev_baseline": m["pit_total_uniformity_dev"], "pit_dev_variant": None,
           "crps_baseline": m["crps_total_sim"], "crps_variant": None,
           "regressed_under_variant": None, "brier": m[brier_key]}
    return {"sport": sport, "engine": engine, "corpus": corpus, "crps_per_bucket": False,
            "buckets": [row], "regression_anchors": None, "worst_bucket": row,
            "coverage_gap": ("no (set|time x score-margin) state-cell simulation entry point "
                             "in match_sim.py -- only whole-match MC from the real start exists; "
                             "n=%d whole-match rows is the finest granularity available." % m["n"]),
            "mechanism_crossref": MECHANISM_CROSSREF[sport]}


def collect_tennis(refresh: bool = False) -> Dict[str, Any]:
    if refresh:
        from domains.tennis.point_engine.validate import run as _run
        _run()
    doc = _load("tennis_point_engine_v1.json")
    if doc is None:
        return {"sport": "tennis", "coverage_gap": "no cached artifact; run --refresh", "buckets": []}
    return _whole_match_gap("tennis", "point_engine v1",
                            doc["panel_B_match_mc"],
                            "fit %s, test %s" % (doc["fit_years"], doc["test_year"]))


def collect_soccer(refresh: bool = False) -> Dict[str, Any]:
    if refresh:
        from domains.soccer.chain_engine.validate import run as _run
        _run()
    doc = _load("soccer_chain_engine_v1.json")
    if doc is None:
        return {"sport": "soccer", "coverage_gap": "no cached artifact; run --refresh", "buckets": []}
    out = {}
    for tag, r in doc["results"].items():
        out[tag] = _whole_match_gap("soccer", "chain_engine v1 corpus %s" % tag,
                                    r["panel_B_match_mc"], doc["corpora"][tag])
    combined = dict(out["A"])
    combined["per_corpus"] = out
    combined["buckets"] = out["A"]["buckets"] + out["B"]["buckets"]
    combined["worst_bucket"] = _worst(combined["buckets"])
    return combined


COLLECTORS = {"nba": collect_nba, "mlb": collect_mlb, "tennis": collect_tennis, "soccer": collect_soccer}


def _write_markdown(docs: Dict[str, dict]) -> None:
    lines = ["# Cross-sport sim state-cell heatmap -- worst-bucket queue (2026-07-11)", "",
             "Sharpness/calibration only, edge_claimed:false. Generated by "
             "`scripts/platformkit/benchmarks/sim_heatmap/build_heatmap.py`.", ""]
    lines.append("## Worst named bucket per sport")
    lines.append("| sport | engine | worst bucket | n | pit_dev | mechanism cross-ref (QUEUE) |")
    lines.append("|---|---|---|---|---|---|")
    for sport, d in docs.items():
        w = d.get("worst_bucket") or {}
        xr = (d.get("mechanism_crossref") or {}).get("note", "")
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            sport, d.get("engine", ""), w.get("bucket", "n/a"), w.get("n", "n/a"),
            w.get("pit_dev_baseline", "n/a"), xr))
    lines.append("")
    lines.append("## Regression anchors (known, cross-referenced against ledgers)")
    for sport, d in docs.items():
        ra = d.get("regression_anchors")
        if not ra:
            continue
        lines.append("- **%s** (%s): %s" % (sport, d.get("corpus", ""), json.dumps(ra)))
    lines.append("")
    lines.append("## Coverage gaps")
    for sport, d in docs.items():
        gap = d.get("coverage_gap")
        if gap:
            lines.append("- **%s**: %s" % (sport, gap))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")


def run(refresh: bool = False, sports: Optional[List[str]] = None) -> Dict[str, dict]:
    sports = sports or list(COLLECTORS)
    docs = {}
    for s in sports:
        d = COLLECTORS[s](refresh=refresh)
        docs[s] = d
        OPS.mkdir(parents=True, exist_ok=True)
        (OPS / ("sim_heatmap_%s.json" % s)).write_text(
            json.dumps({"generated_by": "sim_heatmap.build_heatmap", "edge_claimed": False, **d},
                       indent=2, ensure_ascii=True, default=str), encoding="utf-8")
    _write_markdown(docs)
    return docs


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-invoke each engine's own run() first")
    ap.add_argument("--sport", action="append", choices=list(COLLECTORS), dest="sports")
    a = ap.parse_args(argv)
    docs = run(refresh=a.refresh, sports=a.sports)
    for sport, d in docs.items():
        w = d.get("worst_bucket") or {}
        print("%-8s worst=%-30s n=%-5s pit_dev=%s%s" % (
            sport, w.get("bucket", "n/a"), w.get("n", "n/a"), w.get("pit_dev_baseline", "n/a"),
            "  [GAP: %s]" % d["coverage_gap"] if d.get("coverage_gap") else ""))
    print("wrote", REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
