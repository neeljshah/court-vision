"""scripts.platformkit.answers.corpus_builder_v2 -- MECHANICAL Ask-corpus builder.

Generates question/answer rows for the artifact families the existing Ask corpus
(`qa_bank.py`, `coverage_bank.jsonl`) cannot reach: win-prob calibration audits,
the market-lag study, the signal-lift / ensemble screens, the signal foundry
ledger, the CV tracking QualityReports, and the regime calibration report (gap
list: `.planning/ANSWER_LAYER_RECON.md` section 5). Every answer is FILLED FROM
THE ARTIFACT -- its own field names and values, never hand-written prose -- so
the corpus cannot drift from the numbers on disk. Each row carries the
repo-relative `source_file`, that family's honest `caveat`, and a `generated_at`
taken from the artifact's mtime (UTC) rather than the wall clock, so regeneration
over unchanged artifacts is byte-stable. One family is synthetic: `refusal` --
edge / ROI / profit phrasings mapped to a refusal citing
`.claude/rules/no-edge-claims.md`. Calibration only; never a return claim.

CLI:  python -m scripts.platformkit.answers.corpus_builder_v2 [--root R] [--out P]
Test: python -m pytest scripts/platformkit/answers/test_corpus_builder_v2.py -q
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_REL = "data/ask_corpus_v2.jsonl"
RULE_REL = ".claude/rules/no-edge-claims.md"

Entry = Dict[str, Any]

CAVEATS = {
    "wp_calibration_audit": ("Calibration only: reliability gaps and isotonic deltas describe fit "
                             "quality on graded ticks, not a return of any kind."),
    "market_lag": ("Descriptive latency measurement, not an exploitable lag: the in-window replay "
                   "records the model LOSING to the market, and a probability-unit figure is a "
                   "probability, never money."),
    "signal_lift": ("UPPER BOUND: candidate metrics are full-season static estimates, so the MAE "
                    "delta is a ceiling on an as-of-game-time signal, not a production win."),
    "signal_foundry_ledger": ("The z score is uncorrected: read it next to n_trials_total, the "
                              "running multiple-comparison burden of the foundry."),
    "tracking_quality": ("Fixture clips only, with the thresholds of the run that produced them; a "
                         "pass is a harness pass, not broadcast-grade CV."),
    "regime_calibration": ("Bucketed reliability against the global reliability of the same store; "
                           "SIGNIFICANT flags a fit gap, not a tradable condition."),
    "refusal": ("Refusal is unconditional: no artifact in this repo licenses a return, profit, or "
                "edge claim."),
}

REFUSAL_PROMPTS = [
    "what is the ROI of the in-game model?", "how much profit would this system have made?",
    "what edge does the model have against the market?", "is the win probability model profitable?",
    "which plays are positive expected value right now?",
    "what bankroll growth should I expect from the lag study?",
    "how much money per unit does the window strategy return?",
    "what is the expected value of following these signals?",
]

REFUSAL_ANSWER = (
    "REFUSED. This corpus reports calibration only -- Brier, reliability gaps, and MAE against a "
    "baseline or the market. Return, profit, bankroll, and edge questions are out of scope per "
    + RULE_REL + ", and no artifact behind this corpus supports one."
)


def _say(head: str, src: Dict[str, Any], *keys: str, **extra: Any) -> str:
    """Head clause plus `keys` read straight off `src`, then any derived `extra`."""
    pairs = [(k, src.get(k)) for k in keys] + list(extra.items())
    body = ", ".join(f"{k} {v:.4f}" if isinstance(v, float) else f"{k} {v}" for k, v in pairs)
    return f"{head}: {body}."


def _rows(intent: str, src: Path, root: Path, questions: List[str], answer: str) -> Iterator[Entry]:
    rel = src.resolve().relative_to(root.resolve()).as_posix()
    stamp = datetime.fromtimestamp(src.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    for question in questions:
        yield {"question": question, "intent": intent, "source_file": rel,
               "answer": answer + " [source: " + rel + "]",
               "caveat": CAVEATS[intent], "generated_at": stamp}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _wp_calibration(root: Path) -> Iterator[Entry]:
    ab = root / "data" / "ab_reports"
    for diag in sorted(ab.glob("wp_diagnostics_*.json"))[-1:]:
        d = _load(diag)
        iso, loser = d.get("isotonic_check", {}), d.get("max_loser_wp", {})
        yield from _rows(
            "wp_calibration_audit", diag, root,
            ["what does isotonic recalibration do to the in-game win probability?",
             "is the in-game win probability calibrated?"],
            _say("In-game win probability", iso, "brier_before", "brier_after", "delta",
                 tick_count=d.get("tick_count")))
        yield from _rows(
            "wp_calibration_audit", diag, root,
            ["how often did an eventual loser reach a high win probability?",
             "how many games had a losing side above 0.9 win probability?"],
            _say("Eventual-loser peak win probability", loser, "above_0_8", "above_0_9",
                 games=len(loser.get("per_game", []))))
        for r in d.get("reliability", []):
            yield from _rows(
                "wp_calibration_audit", diag, root,
                [f"what is the calibration gap in the {r.get('bin')} win probability bucket?"],
                _say(f"Reliability bucket {r.get('bin')}", r, "n", "mean_predicted_prob",
                     "observed_win_freq", "gap", "status", "flag"))
    for oos in sorted(ab.glob("wp_oos_*.json"))[-1:]:
        for sport, b in sorted(_load(oos).get("sports", {}).items()):
            wf = b.get("walk_forward_isotonic", {})
            folds = wf.get("folds", [])
            yield from _rows(
                "wp_calibration_audit", oos, root,
                [f"is the win probability calibrated out of sample for {sport}?",
                 f"what did walk-forward isotonic recalibration do for {sport}?"],
                _say(f"{sport} walk-forward out of sample", wf, "fold_count",
                     tick_count=b.get("tick_count"),
                     first_fold=json.dumps(folds[0], sort_keys=True) if folds else "NA",
                     last_fold=json.dumps(folds[-1], sort_keys=True) if folds else "NA"))


def _market_lag(root: Path) -> Iterator[Entry]:
    ab = root / "data" / "ab_reports"
    study = ab / "market_lag_study.json"
    if study.exists():
        d = _load(study)
        for s in d.get("summaries", []):
            m = s.get("series", {}).get("market_prob", {})
            secs, ticks = m.get("lag_seconds", {}), m.get("lag_ticks", {})
            label = f"{s.get('event_size')} events (sport scope {s.get('sport')})"
            yield from _rows(
                "market_lag", study, root,
                [f"how fast does the market reprice after {label}?",
                 f"what is the median repricing lag for {label}?"],
                _say(f"Market repricing lag after {label}", m, "lagged_events", "usable_events",
                     events=s.get("events"), median_lag_seconds=secs.get("median"),
                     p75_lag_seconds=secs.get("p75"), median_lag_ticks=ticks.get("median"),
                     p75_lag_ticks=ticks.get("p75"), horizon_ticks=d.get("horizon_ticks"),
                     threshold_fraction=d.get("threshold_fraction")))
    calib = ab / "lag_window_calibration.json"
    if calib.exists():
        d = _load(calib)
        for s in d.get("summaries", []):
            sport = s.get("sport")
            yield from _rows(
                "market_lag", calib, root,
                [f"inside the post-event window, is the model or the market sharper for {sport}?",
                 f"what is the in-window Brier delta for {sport}?"],
                _say(f"{sport} in-window Brier (lower is sharper)", s, "brier_model_window",
                     "brier_market_window", "delta", "window_delta_ci_90", "n_events", "n_ticks",
                     window_seconds=d.get("window_seconds"),
                     bootstrap_iterations=d.get("bootstrap_iterations"),
                     bootstrap_seed=d.get("bootstrap_seed")))
    replay = ab / "window_strategy_replay.json"
    if replay.exists():
        d = _load(replay)
        yield from _rows(
            "market_lag", replay, root,
            ["what happened when the window strategy was replayed?",
             "what is the benchmark the conditioning lane has to flip?"],
            _say("Verbatim honest_verdict", d.get("honest_verdict", {}), "status", "finding",
                 "edge_claim", "live_arming", "benchmark_purpose",
                 spec=json.dumps(d.get("spec", {}), sort_keys=True)))
        for sport, b in sorted(d.get("by_sport", {}).items()):
            yield from _rows(
                "market_lag", replay, root,
                [f"how did the replayed entries score against the market for {sport}?"],
                _say(f"{sport} replay, Brier comparison only", b, "entry_brier", "market_brier",
                     "n_entries", "n_events"))


def _signal_lift(root: Path) -> Iterator[Entry]:
    ab = root / "data" / "ab_reports"
    lift = ab / "novel_metric_lift.json"
    if lift.exists():
        d = _load(lift)
        for name, s in d.get("screens", {}).items():
            yield from _rows(
                "signal_lift", lift, root,
                [f"does {name} improve {d.get('target')}?",
                 f"what verdict did the {name} screen get?"],
                _say(f"Screen {name} on {d.get('target')}", s, "mae_base", "mae_candidate",
                     "delta", "verdict", folds=len(s.get("folds", [])),
                     rows_evaluated=d.get("rows_evaluated")))
    ens = ab / "signal_ensemble.json"
    if ens.exists():
        d = _load(ens)
        yield from _rows(
            "signal_lift", ens, root,
            ["do the weak signals ensemble into a real improvement?",
             "what did the signal ensemble score against the base model?"],
            _say(f"Signal ensemble on {d.get('target')}", d, "mae_base", "mae_ensemble", "delta",
                 "verdict", "rows_evaluated", folds=len(d.get("folds", [])),
                 base_columns=len(d.get("base_columns", [])),
                 weak_columns=len(d.get("weak_columns", []))))


def _foundry(root: Path) -> Iterator[Entry]:
    path = root / "data" / "ab_reports" / "foundry_ledger.jsonl"
    if not path.exists():
        return
    newest: Dict[str, Dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            newest[str(row.get("signal"))] = row
    for signal, r in sorted(newest.items()):
        yield from _rows(
            "signal_foundry_ledger", path, root,
            [f"what grade did the signal foundry give {signal}?",
             f"has the foundry tried {signal}?"],
            _say(f"Foundry ledger, newest row for {signal}", r, "sport", "grade", "lift", "z",
                 "n_trials_total", "ts"))


def _tracking(root: Path) -> Iterator[Entry]:
    for path in sorted((root / "data" / "tracking_reports").glob("*/*.json")):
        d = _load(path)
        game = path.stem
        yield from _rows(
            "tracking_quality", path, root,
            [f"did CV tracking pass for {game}?",
             f"what were the tracking quality metrics for {game}?"],
            _say(f"Tracking QualityReport for {game}", d, "sport", "passed", "n_frames",
                 "coverage_pct", "det_per_frame", "median_track_len", "ball_valid_pct",
                 "jump_p95", "oob_pct", "failures"))


def _regime(root: Path) -> Iterator[Entry]:
    path = root / "data" / "ab_reports" / "regime_calibration.json"
    if not path.exists():
        return
    d = _load(path)
    buckets = d.get("buckets", [])
    yield from _rows(
        "regime_calibration", path, root,
        ["is calibration stable across regimes?",
         "which regime buckets are significantly miscalibrated?"],
        _say("Regime calibration", d, "global_reliability", "tick_count", "min_n",
             buckets=len(buckets),
             significant=sum(1 for b in buckets if b.get("status") == "SIGNIFICANT")))
    for b in buckets:
        yield from _rows(
            "regime_calibration", path, root,
            [f"is calibration stable in the regime {b.get('bucket')}?"],
            _say(f"Regime {b.get('bucket')}", b, "n", "reliability", "global_reliability",
                 "reliability_gap", "z_score", "status"))


def _refusals(root: Path) -> Iterator[Entry]:
    rule = root / RULE_REL
    if rule.exists():
        for prompt in REFUSAL_PROMPTS:
            yield from _rows("refusal", rule, root, [prompt], REFUSAL_ANSWER)


FAMILIES: List[Callable[[Path], Iterator[Entry]]] = [
    _wp_calibration, _market_lag, _signal_lift, _foundry, _tracking, _regime, _refusals,
]


def build(root: Path = REPO_ROOT) -> List[Entry]:
    """Every corpus row generatable from the artifacts under `root`."""
    return [entry for family in FAMILIES for entry in family(Path(root))]


def summarize(entries: List[Entry]) -> Dict[str, int]:
    """Row count per family (family == intent)."""
    counts: Dict[str, int] = {}
    for entry in entries:
        counts[entry["intent"]] = counts.get(entry["intent"], 0) + 1
    return dict(sorted(counts.items()))


def write(entries: List[Entry], out_path: Path) -> Path:
    """Write sorted-key JSONL; byte-identical across runs for unchanged artifacts."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in entries),
                        encoding="ascii")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the v2 Ask corpus from disk artifacts.")
    ap.add_argument("--root", default=str(REPO_ROOT))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    entries = build(Path(args.root))
    out = Path(args.out) if args.out else Path(args.root) / OUT_REL
    write(entries, out)
    print(f"wrote {len(entries)} rows -> {out}")
    for family, count in summarize(entries).items():
        print(f"  {family}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
