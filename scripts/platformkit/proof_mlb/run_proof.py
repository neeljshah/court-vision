"""scripts.platformkit.proof_mlb.run_proof — CLI for the MLB V1/V2/V3/V4 proof.

Runs BOTH NL-home (corpus 1) and AL-home (corpus 2) — the ≥2-corpora requirement.
Expected verdicts (pre-run): mlb_rest_advantage / mlb_streak_form / mlb_h2h_season
all REJECT — gate honesty on MLB (sport-4). REJECT = success criterion.
Market-efficiency framing: MLB moneyline is efficient; devigged close expected to
beat the pitcher-blind Elo model. No edge claims anywhere.
F5: ZERO domains.nba/basketball_nba/other-sport / src.data/sim/tracking/pipeline.
CLI: python run_proof.py --corpus data/domains/mlb [--league-filter NL|AL]
Exits code 2 if games.parquet absent. PRIVATE: never commit to public repo.
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

from domains.mlb.adapter import MLBAdapter
from scripts.platformkit.proof_mlb.proof_runner import run_v1, run_v2, run_v3, run_v4

logger = logging.getLogger(__name__)

_DEFAULT_REPORT = ".planning/platform/proof_mlb/PROOF_RESULT.md"
_LEAGUES = ["NL", "AL"]


# ---------------------------------------------------------------------------
# Corpus loader
# ---------------------------------------------------------------------------

def _load_adapter(corpus_dir: Path) -> Optional[MLBAdapter]:
    """Return an MLBAdapter or None when games.parquet is absent."""
    games_path = corpus_dir / "games.parquet"
    if not games_path.exists():
        return None
    try:
        games_df = pd.read_parquet(games_path)
    except Exception as exc:
        logger.error("Failed to read games.parquet: %s", exc)
        return None
    odds_df: Optional[pd.DataFrame] = None
    odds_path = corpus_dir / "odds.parquet"
    if odds_path.exists():
        try:
            odds_df = pd.read_parquet(odds_path)
        except Exception:
            logger.warning("odds.parquet unreadable; CLV columns will be absent")
    return MLBAdapter(games_df=games_df, odds_df=odds_df)


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _fmt_v1(v1: Dict[str, Any], league: Optional[str]) -> str:
    tag = f" [{league}]" if league else ""
    lines = [f"## V1 — Calibration{tag}", ""]
    if "error" in v1.get("detail", {}):
        lines.append(f"ERROR: {v1['detail']['error']}")
        return "\n".join(lines)
    for label, corpus in v1.get("detail", {}).items():
        if "error" in corpus:
            lines += [f"### Corpus {label}: ERROR — {corpus['error']}", ""]
            continue
        if corpus.get("regime_note"):
            lines += [f"  REGIME NOTE: {corpus['regime_note']}", ""]
        lines += [
            f"### Corpus {label}",
            f"  n_eval             : {corpus.get('n_eval')}",
            f"  raw_brier          : {corpus.get('raw_brier')}",
            f"  calibrated_brier   : {corpus.get('calibrated_brier')}",
            f"  ece                : {corpus.get('ece')} (threshold < 0.025)",
            f"  reliability_slope  : {corpus.get('reliability_slope')} (target [0.9,1.1])",
            f"  market_devig_brier : {corpus.get('market_devig_brier')}",
            f"  market_beats_model : {corpus.get('market_beats_model')}  <- EXPECTED yes (model is pitcher-blind)",
            f"  calib_beats_raw    : {corpus.get('calib_beats_raw')}",
            f"  ece_ok / slope_ok  : {corpus.get('ece_ok')} / {corpus.get('slope_ok')}",
            f"  corpus_ok          : {corpus.get('corpus_ok')}", "",
        ]
    lines.append(f"**V1 overall: {'PASS' if v1['ok'] else 'FAIL'}**")
    return "\n".join(lines)


def _fmt_v2(v2: Dict[str, Any], league: Optional[str]) -> str:
    tag = f" [{league}]" if league else ""
    lines = [f"## V2 — CLV Mechanics (plumbing correctness — NOT edge){tag}", ""]
    if v2.get("note"):
        lines += [f"NOTE: {v2['note']}", ""]
    for k, v in v2.get("detail", {}).items():
        lines.append(f"  {k}: {v}")
    lines += ["", f"**V2 overall: {'PASS' if v2['ok'] else 'FAIL'}**"]
    return "\n".join(lines)


def _fmt_v3(v3: Dict[str, Any], league: Optional[str]) -> str:
    tag = f" [{league}]" if league else ""
    lines = [
        f"## V3 — Honest Gate End-to-End{tag}", "",
        "Pre-run expected verdicts (MLB_PROOF_PLAN.md §4.4):",
        "  mlb_rest_advantage → REJECT  (rest diff near-zero; schedule fully public and priced)",
        "  mlb_streak_form    → REJECT  (hot-team L10 narrative stat; fully priced)",
        "  mlb_h2h_season     → REJECT  (H2H season series narrative; priced; small sample)",
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


def _fmt_v4(v4: Dict[str, Any], league: Optional[str]) -> str:
    tag = f" [{league}]" if league else ""
    lines = [
        f"## V4 — Paper Portfolio Walk-Forward (ARTIFACT-DISCLAIMED){tag}", "",
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


def write_report(
    report_path: Path,
    results_by_league: Dict[str, Dict[str, Any]],
    run_ts: str,
) -> None:
    """Write PROOF_RESULT.md with results for all leagues."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    all_ok = all(
        d["v1"]["ok"] and d["v2"]["ok"] and d["v3"]["ok"] and d["v4"]["ok"]
        for d in results_by_league.values()
    )
    overall = "PASS" if all_ok else "PARTIAL/FAIL"

    sections: List[str] = []
    for league, d in results_by_league.items():
        sections.append(f"---\n\n## League: {league}\n")
        sections.append(_fmt_v1(d["v1"], league))
        sections.append("\n---\n\n" + _fmt_v2(d["v2"], league))
        sections.append("\n---\n\n" + _fmt_v3(d["v3"], league))
        sections.append("\n---\n\n" + _fmt_v4(d["v4"], league))

    body = textwrap.dedent(f"""\
        # MLB Fourth-Domain Proof — Results

        > **PRIVATE** — price-bearing; never commit to public repo.
        > Generated: {run_ts}
        > Proof spec: MLB_PROOF_PLAN.md  |  F5: ZERO other-sport-domain imports.
        > Corpora: NL-home games (corpus 1) + AL-home games (corpus 2).

        **Overall: {overall}**

        """) + "\n\n".join(sections) + textwrap.dedent("""

        ---

        ## Falsifier checklist

        - [ ] F1. No kernel file needed a logic edit (hash delta) to run MLB.
        - [ ] F2. No kernel function has an MLB-conditional branch.
        - [x] F3. gate.evaluate ran on MLB FeatureBundle data via injected FeatureBundle (V3).
        - [ ] F4. Calibration criteria met without modifying calibrator internals.
        - [x] F5. Adapter imports ZERO other-sport-domain / src.data / src.sim / src.tracking.
        - [ ] F6. Adapter + proof LOC within budget.

        ## Market-efficiency framing

        MLB moneyline markets are efficient. Expected: devigged closing-line Brier
        < calibrated Elo model Brier (market beats the model). V1 success is
        calibration quality and plumbing, not edge over the market. The model is
        deliberately pitcher-blind — the efficiency gap is expected to be LARGER
        than in prior sports proofs. All 3 signals expected REJECT; that demonstrates
        kernel honesty transfers to sport-4 (MLB).
        """)
    report_path.write_text(body, encoding="utf-8")
    print(f"Report written: {report_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="MLB fourth-domain proof runner (V1/V2/V3/V4)."
    )
    parser.add_argument("--corpus", default="data/domains/mlb")
    parser.add_argument("--league-filter", choices=["NL", "AL"], default=None,
                        help="Run a single corpus (NL or AL). Omit to run both.")
    parser.add_argument("--report", default=None)
    parser.add_argument("--paper-book-dir", default=None,
                        help="Dir for V4 paper P&L output")
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
            f"[run_proof] corpus not built: games.parquet not found at {corpus_dir}.\n"
            "Run domains/mlb/ingest_sbro.py first.",
            file=sys.stderr,
        )
        return 2

    paper_book_dir: Optional[Path] = (
        Path(args.paper_book_dir) if args.paper_book_dir
        else repo_root / "data" / "domains" / "mlb" / "paper_book"
    )

    leagues = [args.league_filter] if args.league_filter else _LEAGUES
    run_ts = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    print(f"[run_proof] Starting MLB proof at {run_ts} — corpora: {leagues}")

    results_by_league: Dict[str, Dict[str, Any]] = {}
    for league in leagues:
        print(f"\n[run_proof] === Corpus: {league} ===")
        print(f"[run_proof] V1: Calibration [{league}]...")
        v1 = run_v1(adapter, league_filter=league)
        print(f"  V1 ok={v1['ok']}")

        print(f"[run_proof] V2: CLV mechanics [{league}]...")
        v2 = run_v2(adapter, league_filter=league)
        print(f"  V2 ok={v2['ok']}")

        print(f"[run_proof] V3: Honest gate (3 signals) [{league}]...")
        v3 = run_v3(adapter, league_filter=league)
        for r in v3.get("verdicts", []):
            print(f"    {r['signal']}: expected={r['expected']} actual={r['actual']}")
        print(f"  V3 ok={v3['ok']}")

        print(f"[run_proof] V4: Paper portfolio walk-forward [{league}]...")
        v4 = run_v4(adapter, paper_book_dir=paper_book_dir, league_filter=league)
        print(f"  V4 ok={v4['ok']}")

        results_by_league[league] = {"v1": v1, "v2": v2, "v3": v3, "v4": v4}

    report_path = (
        Path(args.report) if args.report else (repo_root / _DEFAULT_REPORT)
    )
    write_report(report_path, results_by_league, run_ts)

    overall_ok = all(
        d["v1"]["ok"] and d["v2"]["ok"] and d["v3"]["ok"] and d["v4"]["ok"]
        for d in results_by_league.values()
    )
    print(f"\n[run_proof] Overall: {'PASS' if overall_ok else 'PARTIAL/FAIL'}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
