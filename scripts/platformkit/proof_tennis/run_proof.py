"""scripts.platformkit.proof_tennis.run_proof — CLI entry point for the tennis proof.

Orchestrates V1 (calibration), V2 (CLV mechanics), V3 (honest gate), V4 (paper
portfolio walk-forward) by delegating execution to proof_runner.py and writing
a Markdown report.

EXPECTED VERDICTS (written before any gate run — the honest discipline):
  tennis_fatigue_rest       → REJECT  (rest/fatigue fully priced by sharp books)
  tennis_surface_transition → REJECT or DEFER  (sparse sub-population; likely priced)
  tennis_h2h_residual       → REJECT  (classic narrative stat, priced, weak null-shuffle)
A REJECT is the success criterion — it proves the gate's honesty transfers across sports.

Market-efficiency framing (binding):
  Pinnacle tennis is sharp.  Devigged Pinnacle Brier EXPECTED to beat our calibrated
  Elo on every eval corpus.  V1 success = calibration quality + plumbing, not edge.

F5 compliance: ZERO domains.nba / src.data / src.sim / src.tracking / src.pipeline.

CLI:  python run_proof.py --corpus data/domains/tennis [--report PATH]
If corpus parquets are absent, exits cleanly (code 2) — no crash.

PRIVATE: report is price-bearing; default path .planning/platform/proof_tennis/
PROOF_RESULT.md is gitignored.
"""
from __future__ import annotations
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

import argparse
import datetime as dt
import logging
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from domains.tennis.adapter import TennisAdapter
from scripts.platformkit.proof_tennis.proof_runner import run_v1, run_v2, run_v3, run_v4

logger = logging.getLogger(__name__)

_DEFAULT_REPORT = ".planning/platform/proof_tennis/PROOF_RESULT.md"


# ---------------------------------------------------------------------------
# Corpus loader
# ---------------------------------------------------------------------------

def _load_adapter(corpus_dir: Path) -> Optional[TennisAdapter]:
    """Return a TennisAdapter or None when matches.parquet is absent."""
    matches_path = corpus_dir / "matches.parquet"
    if not matches_path.exists():
        return None
    try:
        matches_df = pd.read_parquet(matches_path)
    except Exception as exc:
        logger.error("Failed to read matches.parquet: %s", exc)
        return None
    odds_df: Optional[pd.DataFrame] = None
    odds_path = corpus_dir / "odds.parquet"
    if odds_path.exists():
        try:
            odds_df = pd.read_parquet(odds_path)
        except Exception:
            logger.warning("odds.parquet unreadable; CLV columns will be absent")
    return TennisAdapter(matches_df=matches_df, odds_df=odds_df)


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _fmt_v1(v1: Dict[str, Any]) -> str:
    lines = ["## V1 — Calibration", ""]
    if "error" in v1.get("detail", {}):
        lines.append(f"ERROR: {v1['detail']['error']}")
        return "\n".join(lines)
    for label, corpus in v1.get("detail", {}).items():
        if "error" in corpus:
            lines += [f"### Corpus {label}: ERROR — {corpus['error']}", ""]
            continue
        lines += [
            f"### Corpus {label}",
            f"  n_eval           : {corpus.get('n_eval')}",
            f"  raw_brier        : {corpus.get('raw_brier')}",
            f"  calibrated_brier : {corpus.get('calibrated_brier')}",
            f"  ece              : {corpus.get('ece')} (threshold < 0.025)",
            f"  reliability_slope: {corpus.get('reliability_slope')} (target [0.9,1.1])",
            f"  pinnacle_devig_brier: {corpus.get('pinnacle_devig_brier')}",
            f"  market_beats_elo : {corpus.get('market_beats_elo')}  ← EXPECTED yes",
            f"  calib_beats_raw  : {corpus.get('calib_beats_raw')}",
            f"  ece_ok / slope_ok: {corpus.get('ece_ok')} / {corpus.get('slope_ok')}",
            f"  corpus_ok        : {corpus.get('corpus_ok')}", "",
        ]
    lines.append(f"**V1 overall: {'PASS' if v1['ok'] else 'FAIL'}**")
    return "\n".join(lines)


def _fmt_v2(v2: Dict[str, Any]) -> str:
    lines = ["## V2 — CLV Mechanics (plumbing correctness — NOT edge)", ""]
    if v2.get("note"):
        lines += [f"NOTE: {v2['note']}", ""]
    for k, v in v2.get("detail", {}).items():
        lines.append(f"  {k}: {v}")
    lines += ["", f"**V2 overall: {'PASS' if v2['ok'] else 'FAIL'}**"]
    return "\n".join(lines)


def _fmt_v3(v3: Dict[str, Any]) -> str:
    lines = [
        "## V3 — Honest Gate End-to-End", "",
        "Pre-run expected verdicts (SECOND_DOMAIN_PROOF.md §4.4):",
        "  tennis_fatigue_rest       → REJECT  (rest fully priced)",
        "  tennis_surface_transition → REJECT or DEFER  (sparse; likely priced)",
        "  tennis_h2h_residual       → REJECT  (narrative stat, priced)",
        "",
        "KERNEL_DISCIPLINE #1: REJECT = success. Gate honesty transfers across sports.",
        "A SHIP requires full artifact-hunt + forward CLV before being believed.", "",
    ]
    for r in v3.get("verdicts", []):
        sym = "OK" if r.get("passed_expected") else "!!"
        lines += [
            f"### [{sym}] {r['signal']}",
            f"  expected: {r['expected']}  actual: {r['actual']}",
            f"  reason  : {r.get('reason', '')}",
            f"  wf_folds: {r.get('wf_folds', [])}  all_improve={r.get('wf_all_improve')}",
            f"  abl_delta={r.get('ablation_delta')} pass={r.get('ablation_pass')}  "
            f"null_pass={r.get('null_pass')}  calib_ok={r.get('calibration_ok')}",
            f"  clv={r.get('clv')}  p_value={r.get('p_value')}", "",
        ]
    lines.append(f"**V3 overall: {'PASS' if v3['ok'] else 'FAIL (unexpected SHIP)'}**")
    return "\n".join(lines)


def _fmt_v4(v4: Dict[str, Any]) -> str:
    lines = [
        "## V4 — Paper Portfolio Walk-Forward (ARTIFACT-DISCLAIMED)", "",
        "> **DISCLAIMER:** paper P&L is a market-follow artifact, not realized edge; "
        "no real money; markets efficient.", "",
    ]
    if v4.get("note"):
        lines += [f"NOTE: {v4['note']}", ""]
    d = v4.get("detail", {})
    for k in ("n_bets", "kelly_fraction_used", "risk_gate_fired", "drawdown_inject_fired",
              "paper_pnl_units", "paper_return_pct"):
        if k in d:
            lines.append(f"  {k}: {d[k]}")
    lines += ["", f"**V4 overall: {'PASS' if v4['ok'] else 'FAIL'}**"]
    return "\n".join(lines)


def write_report(report_path: Path, v1: Dict, v2: Dict, v3: Dict, run_ts: str,
                 v4: Optional[Dict] = None) -> None:
    """Write PROOF_RESULT.md."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    overall = "PASS" if (v1["ok"] and v2["ok"] and v3["ok"]
                         and (v4 is None or v4["ok"])) else "PARTIAL/FAIL"
    v4_section = f"\n\n---\n\n{_fmt_v4(v4)}" if v4 is not None else ""
    body = textwrap.dedent(f"""\
        # Tennis Second-Domain Proof — Results

        > **PRIVATE** — price-bearing; never commit to public repo.
        > Generated: {run_ts}
        > Proof spec: SECOND_DOMAIN_PROOF.md  |  F5: ZERO domains.nba imports.

        **Overall: {overall}**

        ---

        {_fmt_v1(v1)}

        ---

        {_fmt_v2(v2)}

        ---

        {_fmt_v3(v3)}{v4_section}

        ---

        ## Falsifier checklist

        - [ ] F1. No kernel file needed a logic edit (hash delta) to run tennis.
        - [ ] F2. No kernel function has a tennis-conditional branch.
        - [x] F3. gate.evaluate ran on sport-2 data via injected FeatureBundle (V3).
        - [ ] F4. Calibration criteria met without modifying calibrator internals.
        - [x] F5. Adapter imports ZERO domains.nba / src.data / src.sim / src.tracking.
        - [ ] F6. Adapter LOC within ~2x §3.2 budget.

        ## Market-efficiency framing

        Pinnacle tennis is sharp. Expected: devigged Pinnacle Brier < calibrated Elo
        Brier (market beats us). V1 records this honestly — V1 success is calibration
        quality and plumbing, not edge over the market. All 3 signals expected REJECT;
        that demonstrates kernel honesty transfers to a second sport.
        """)
    report_path.write_text(body, encoding="utf-8")
    print(f"Report written: {report_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Tennis second-domain proof runner (V1/V2/V3/V4)."
    )
    parser.add_argument("--corpus", default="data/domains/tennis")
    parser.add_argument("--report", default=None)
    parser.add_argument("--paper-book-dir", default=None,
                        help="Dir for V4 paper P&L output (default: data/domains/tennis/paper_book)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    repo_root = Path(__file__).resolve().parents[3]
    corpus_dir = (
        (repo_root / args.corpus) if not Path(args.corpus).is_absolute()
        else Path(args.corpus)
    )

    adapter = _load_adapter(corpus_dir)
    if adapter is None:
        print(
            f"[run_proof] corpus not built: matches.parquet not found at {corpus_dir}.\n"
            "Run domains/tennis/ingest_sackmann.py first.",
            file=sys.stderr,
        )
        return 2

    paper_book_dir = (
        Path(args.paper_book_dir) if args.paper_book_dir
        else repo_root / "data" / "domains" / "tennis" / "paper_book"
    )

    run_ts = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    print(f"[run_proof] Starting proof at {run_ts}")

    print("[run_proof] V1: Calibration...")
    v1 = run_v1(adapter)
    print(f"  V1 ok={v1['ok']}")

    print("[run_proof] V2: CLV mechanics...")
    v2 = run_v2(adapter)
    print(f"  V2 ok={v2['ok']}")

    print("[run_proof] V3: Honest gate (3 signals)...")
    v3 = run_v3(adapter)
    for r in v3.get("verdicts", []):
        print(f"    {r['signal']}: expected={r['expected']} actual={r['actual']}")
    print(f"  V3 ok={v3['ok']}")

    print("[run_proof] V4: Paper portfolio walk-forward...")
    v4 = run_v4(adapter, paper_book_dir=paper_book_dir)
    print(f"  V4 ok={v4['ok']}")

    report_path = (
        Path(args.report) if args.report else (repo_root / _DEFAULT_REPORT)
    )
    write_report(report_path, v1, v2, v3, run_ts, v4=v4)

    overall_ok = v1["ok"] and v2["ok"] and v3["ok"] and v4["ok"]
    print(f"[run_proof] Overall: {'PASS' if overall_ok else 'PARTIAL/FAIL'}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
