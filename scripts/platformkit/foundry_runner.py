"""Continuously screen the Signal Foundry pool: a claim-driven T0/T1 queue, or the legacy matrix.

`run_pass(number, queue=...)` claims hypotheses from the S15 results DB and runs the S12 cheap
tiers (T0 then T1) on the SCREEN side of the family partition; an empty queue idles for
`poll_seconds` and never rebuilds `PASS_CONFIGS`. `run_pass(number)` (no queue) and `--legacy`
keep the old rotated-matrix behaviour byte-for-byte. T0/T1 never reach the FWER ledger --
`tiers.charge_tier` refuses them by construction -- and T2/T3 run only off `tiers.promote`,
serially under `ledger_lock`, and only with `--allow-charge`. Calibration only: a SCREEN is
a non-finding.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

import pandas as pd

from scripts.platformkit import signal_foundry as foundry
from scripts.platformkit.clv_ledger_io import ledger_lock
from scripts.platformkit.foundry import results_db, tiers
from scripts.platformkit.novel_metric_lift import CANDIDATE_METRICS, pivot_player_metrics
from scripts.platformkit.teacher_student_ab import LOAD_FEATURES, build_features, expanding_folds


SUMMARY_PATH = Path(os.environ.get("FOUNDRY_RUNNER_SUMMARY", "data/ab_reports/foundry_runner.jsonl"))
HEARTBEAT_PATH = Path(os.environ.get("FOUNDRY_RUNNER_HEARTBEAT", "data/ab_reports/foundry_runner.heartbeat.json"))
PASS_CONFIGS = ((3, 1), (4, 2), (5, 1), (3, 2), (4, 1), (5, 2))
POLL_SECONDS = 60.0
SCREEN_ROWS = 800


class ChargeNotAllowed(RuntimeError):
    """A charged tier was reached without the explicit `--allow-charge` opt-in."""


def build_minutes_matrix() -> tuple[pd.DataFrame, list[foundry.SignalSpec]]:
    """Build the demo minutes matrix and its complete reusable signal pool."""
    root = Path(os.environ.get("NBA_DATA_ROOT", "data"))
    nba = root / "nba"
    frame = build_features(
        pd.read_parquet(nba / "player_tracking_features_asof.parquet"),
        pd.read_parquet(nba / "player_load_state_asof.parquet"),
        pd.read_parquet(nba / "player_embeddings_asof.parquet"),
    )
    metrics = pivot_player_metrics(pd.read_parquet(root / "ab_reports" / "novel_metrics_players.parquet"))
    frame = frame.merge(metrics, on="personId", how="left").dropna(subset=["gameDate"])
    frame = frame.sort_values("gameDate").reset_index(drop=True)
    names = [*CANDIDATE_METRICS, *[name for name in frame if name in LOAD_FEATURES or name.startswith("style_embedding_")]]
    specs = []
    for name in names:
        spec = foundry.REGISTRY.get(name)
        if spec is None:
            spec = foundry.register(foundry.SignalSpec(name, "nba", "player_game", "none", name))
        specs.append(spec)
    return frame, specs


def _append_summary(item: dict[str, object]) -> None:
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, allow_nan=False) + "\n")


def _legacy_pass(number: int) -> dict[str, object]:
    """Run one configuration, preserving progress when an individual stage fails."""
    n_folds, embargo_blocks = PASS_CONFIGS[number % len(PASS_CONFIGS)]
    config = {"n_folds": n_folds, "embargo_blocks": embargo_blocks}
    grades: dict[str, int] = {}
    pool_delta: float | None = None
    signals: Sequence[foundry.SignalSpec] = []
    try:
        matrix, signals = build_minutes_matrix()
        folds = list(expanding_folds(matrix, folds=n_folds))
        original_embargo = foundry.EMBARGO_BLOCKS
        try:
            foundry.EMBARGO_BLOCKS = embargo_blocks
            for spec in signals:
                try:
                    result = foundry.evaluate_signal(matrix, "minutes", spec, folds)
                    grade = str(result.get("grade", "ERROR"))
                except Exception as error:  # A bad signal must not stop the pod.
                    print("signal_failed name={0} error={1}".format(spec.name, type(error).__name__))
                    grade = "ERROR"
                grades[grade] = grades.get(grade, 0) + 1
            try:
                pool_delta = float(foundry.combine_pool(matrix, "minutes", signals, folds)["oos_lift"])
            except Exception as error:  # Pool analysis is evidence-only and non-fatal.
                print("pool_failed error={0}".format(type(error).__name__))
        finally:
            foundry.EMBARGO_BLOCKS = original_embargo
    except Exception as error:
        print("pass_failed error={0}".format(type(error).__name__))
    summary = {"ts": datetime.now(timezone.utc).isoformat(), "pass_config": config,
               "n_signals": len(signals), "grades_histogram": grades, "pool_delta": pool_delta}
    _append_summary(summary)
    print("foundry_pass={0} folds={1} embargo={2} signals={3}".format(
        number, n_folds, embargo_blocks, len(signals)))
    return summary


@dataclass
class ScreenQueue:
    """One continuous screening context: claimable rows plus the corpus both sides sit on."""

    db: Any
    states: Sequence[dict]                      # SCREEN side only (T0/T1 may read nothing else)
    predict_fn: Callable
    partition: tiers.Partition
    rule: tiers.PromotionRule
    ledger_path: Path
    verdict_states: Sequence[dict] = field(default_factory=tuple)
    corpus_sha: str = ""
    family: str = "foundry"
    poll_seconds: float = POLL_SECONDS
    allow_charge: bool = False
    trials_dir: Path | None = None       # None -> the S15 production trials directory


def screen_queue(sport: str, *, db: Any, ledger_path: Any, rows: int = SCREEN_ROWS,
                 allow_charge: bool = False, spec_path: Any = tiers.SPEC_PATH,
                 trials_dir: Any = None) -> ScreenQueue:
    """Build a queue over a real gate corpus. `p_base` is the screen predictor -- honest, not tuned.

    ponytail: eval_gate.close_join covers soccer and tennis only today; a sport it does not
    support raises there rather than being faked here.
    """
    from scripts.platformkit.eval_gate.close_join import gate_corpus_states

    states = gate_corpus_states(sport, "1900-01-01", "2999-01-01")
    rule = tiers.PromotionRule.from_spec(spec_path)
    partition = tiers.partition_corpus(states, seed=rule.partition_seed)
    screen = [s for s in states if s["game_id"] in partition.screen_ids][-rows:]
    verdict = [s for s in states if s["game_id"] in partition.verdict_ids][-rows:]
    return ScreenQueue(db, screen, _p_base_predict, partition, rule, Path(ledger_path), verdict,
                       partition.screen_sha256[:16], sport, allow_charge=allow_charge,
                       trials_dir=None if trials_dir is None else Path(trials_dir))


def _p_base_predict(train: Sequence[dict], test: dict, select_inside: bool) -> float:
    return min(max(float(test["features"]["p_base"]), 0.001), 0.999)


def _record(queue: ScreenQueue, result: tiers.TierResult) -> None:
    """Index one tier call and write its evidence JSON. The DB indexes evidence, never replaces it."""
    row = {"hash": result.hash, "tier": result.tier, "corpus": result.corpus,
           "corpus_unit": result.corpus_unit, "corpus_sha": queue.corpus_sha, "n": result.n,
           "n_eff": result.n_eff, "brier_model": result.brier_model,
           "brier_close": result.brier_close, "dm_stat": result.dm, "raw_p": result.raw_p,
           "k_family": result.k_family, "k_global": result.k_global,
           "deflated_p": result.deflated_p, "pbo": result.pbo, "verdict": result.verdict,
           "prereg_sha256": result.prereg_sha256, "artifact_path": "", "run_at": None}
    path = results_db.trial_artifact_path(result.hash, result.tier, result.corpus_unit or "all")
    if queue.trials_dir is not None:
        path = Path(queue.trials_dir) / path.name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, allow_nan=False), encoding="ascii")
    row["artifact_path"] = path.as_posix()
    try:
        queue.db.record(row)
    except sqlite3.IntegrityError:   # the same trial is never double-indexed; it still counted
        pass


def _screen_one(queue: ScreenQueue, hypothesis: Any, family: str) -> tiers.TierResult | None:
    """T0 then T1 on the screen side. A failed screen is a screen with its reason, never dropped."""
    last = None
    for tier in tiers.SCREEN_TIERS:
        try:
            last = tiers.run_tier(hypothesis, tier, states=queue.states, predict_fn=queue.predict_fn,
                                  ledger_path=queue.ledger_path, partition=queue.partition,
                                  rule=queue.rule, family=family)
        except Exception as error:   # a bad hypothesis must not stop the pod
            print("screen_failed tier={0} family={1} reason={2}".format(tier, family, type(error).__name__))
            return None
        _record(queue, last)
        if tier == "T0" and last.verdict != "COVERED":
            return None
    return last


def run_charged(queue: ScreenQueue, hypotheses: Sequence[Any], screened_n: int,
                family: str, tier: str = "T2") -> int:
    """THE OPT-IN: charged tiers refuse to run without --allow-charge. Serial under ledger_lock."""
    if not queue.allow_charge:
        raise ChargeNotAllowed("{0} needs --allow-charge; the runner screens by default".format(tier))
    charged = 0
    with ledger_lock(queue.ledger_path):
        for hypothesis in hypotheses:
            result = tiers.run_tier(hypothesis, tier, states=queue.verdict_states,
                                    predict_fn=queue.predict_fn, ledger_path=queue.ledger_path,
                                    partition=queue.partition, rule=queue.rule, family=family,
                                    screened_n=screened_n)
            _record(queue, result)
            charged += 1
    return charged


def _promotions(queue: ScreenQueue, screens: Sequence[tiers.TierResult]) -> tuple[int, int]:
    """Promote per family off `tiers.promote` only; the width comes off the frozen spec."""
    promoted, charges = 0, 0
    for family in sorted({r.family for r in screens}):
        group = [r for r in screens if r.family == family]
        picks = tiers.promote(group, queue.rule)
        promoted += len(picks)
        try:
            charges += run_charged(queue, picks, len(group), family)
        except ChargeNotAllowed:
            print("promotions_held family={0} count={1} reason=allow_charge_off".format(family, len(picks)))
    return promoted, charges


def _finish(number: int, screened: dict[str, int], promotions: int, charges: int,
            idle: bool, started: float) -> dict[str, object]:
    summary = {"ts": datetime.now(timezone.utc).isoformat(), "pass": number,
               "screens": sum(screened.values()), "screened_n": screened,
               "promotions": promotions, "charges": charges, "idle": idle,
               "seconds": round(time.time() - started, 3)}
    _append_summary(summary)
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_PATH.write_text(json.dumps(summary, allow_nan=False), encoding="ascii")
    print("foundry_pass={0} screens={1} promotions={2} charges={3} idle={4}".format(
        number, summary["screens"], promotions, charges, idle))
    return summary


def run_pass(number: int, queue: ScreenQueue | None = None, batch: int = 50) -> dict[str, object]:
    """Screen a claimed batch; idle on an empty queue. Without a queue: the legacy matrix pass."""
    if queue is None:
        return _legacy_pass(number)
    started = time.time()
    hypotheses = queue.db.claim(batch, tier="T0")
    if not hypotheses:
        time.sleep(queue.poll_seconds)
        return _finish(number, {}, 0, 0, True, started)
    screened: dict[str, int] = {}
    screens: list[tiers.TierResult] = []
    for hypothesis in hypotheses:
        family = getattr(hypothesis, "family", "") or queue.family
        screened[family] = screened.get(family, 0) + 1
        result = _screen_one(queue, hypothesis, family)
        if result is not None and result.tier == "T1":
            screens.append(result)
    promotions, charges = _promotions(queue, screens)
    return _finish(number, screened, promotions, charges, False, started)


def run(max_passes: int | None = None, sleep_seconds: float = 900.0,
        queue: ScreenQueue | None = None, batch: int = 50,
        deadline: float | None = None) -> list[dict[str, object]]:
    """Run until stopped, or for a bounded pass count / wall deadline in tests and jobs.

    Legacy (queue=None) is unchanged; with a queue the pass itself idles, so no second sleep.
    """
    results: list[dict[str, object]] = []
    while max_passes is None or len(results) < max_passes:
        results.append(run_pass(len(results), queue, batch) if queue is not None
                       else run_pass(len(results)))
        if deadline is not None and time.time() >= deadline:
            break
        if queue is None and (max_passes is None or len(results) < max_passes):
            time.sleep(sleep_seconds)
    return results


def main() -> None:
    """Screen from the results-DB queue, or `--legacy` for the old rotated matrix."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-passes", type=int, default=None)
    parser.add_argument("--sleep-seconds", type=float, default=900.0)
    parser.add_argument("--legacy", action="store_true", help="old matrix + 900 s sleep")
    parser.add_argument("--db", default=str(results_db.DEFAULT_PATH))
    parser.add_argument("--ledger", default="data/cache/eval_gate/backtest_fwer.jsonl")
    parser.add_argument("--sport", default="soccer")
    parser.add_argument("--batch", type=int, default=50)
    parser.add_argument("--screen-rows", type=int, default=SCREEN_ROWS)
    parser.add_argument("--poll-seconds", type=float, default=POLL_SECONDS)
    parser.add_argument("--minutes", type=float, default=None, help="stop after this much wall time")
    parser.add_argument("--trials-dir", default=None)
    # THE REFUSAL, defaulting OFF: without this flag no promotion may reach the FWER ledger.
    parser.add_argument("--allow-charge", action="store_true")
    args = parser.parse_args()
    if args.legacy:
        run(args.max_passes, args.sleep_seconds)
        return
    deadline = None if args.minutes is None else time.time() + args.minutes * 60.0
    with results_db.ResultsDB(args.db) as db:
        queue = screen_queue(args.sport, db=db, ledger_path=args.ledger, rows=args.screen_rows,
                             allow_charge=args.allow_charge, trials_dir=args.trials_dir)
        queue.poll_seconds = args.poll_seconds
        run(args.max_passes, args.sleep_seconds, queue, args.batch, deadline)


if __name__ == "__main__":
    main()
