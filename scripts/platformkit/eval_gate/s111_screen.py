"""S111 (d) -- the local factory screen over the newly covered families, reproducibly.

S85's re-screen was run ad hoc and left nothing a verifier could re-run. This is that run as
a script: seed the FROZEN family grammar for a named set of families into a SCRATCH sqlite,
screen T0/T1 on the SCREEN side of the frozen partition with `--predictor real`, and print
the coverage table and the per-family best screen.

CHARGES ARE OFF AND UNREACHABLE HERE: `allow_charge=False` (the runner's default), so
`tiers.charge_tier` is never called, the ledger path is a scratch path that is never created,
and the production `data/cache/eval_gate/backtest_fwer.jsonl` is neither read nor written.

THE CI IS RECOMPUTED HERE from the archived per-event differential in the documented
direction (d = loss_incumbent - loss_model), never taken from the stored `dm_stat`: S79 filed
that `tiers._run_screen` passes the sign mirror and that finding is unrepaired.

A SCREEN IS A NON-FINDING. Calibration language only -- no dollar, ROI or edge claim.

Run (scratch dir must exist):
  python -m scripts.platformkit.eval_gate.s111_screen --out-dir <scratch>
"""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from scripts.platformkit import foundry_runner
from scripts.platformkit.foundry import results_db, seed_queue

# The S111 acquisitions, plus the three NBA families S85 already screened -- they are the
# regression check: their numbers must not move, because the bridge is consulted only for the
# pairs it lists and none of those three is one of them.
TARGETS = {
    "tennis": ("tennis_features", "tennis_return", "tennis_meta",
               "tennis_schedule_density", "tennis_travel_scouting"),
    "nba": ("nba_quarter_shape", "nba_player_value_features", "nba_opp_allowed",
            "nba_player_adv"),
}
SCREEN_ROWS = 800


def seed(db, sport: str, families) -> int:
    hashes = [db.upsert_hypothesis(h, family=h.family, runtime_available=h.runtime_available)
              for h in seed_queue.frozen_hypotheses(sport) if h.family in families]
    db.enqueue(hashes, "T0")
    return len(hashes)


def run(out_dir: Path) -> list:
    """Seed, screen and return the trial rows. Nothing outside `out_dir` is written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    trials, db_path = out_dir / "trials", out_dir / "s111_screen.sqlite"
    db_path.unlink(missing_ok=True)
    with results_db.ResultsDB(str(db_path)) as db:
        for sport, families in TARGETS.items():
            print("seeded sport=%s n=%d" % (sport, seed(db, sport, families)))
        queues = {sport: foundry_runner.screen_queue(
            sport, db=db, ledger_path=str(out_dir / "never_created_ledger.jsonl"),
            rows=SCREEN_ROWS, allow_charge=False, trials_dir=str(trials), predictor="real")
            for sport in TARGETS}
        for sport, queue in queues.items():
            queue.poll_seconds = 0.0
            print("screen_partition_sha256 sport=%s %s" % (sport, queue.partition.screen_sha256[:16]))
        started = time.time()
        foundry_runner.run(max_passes=200, sleep_seconds=0.0, queue=queues, batch=200,
                           idle_exit=True)
        print("wall_seconds=%.1f charged_ledger_created=%s"
              % (time.time() - started, (out_dir / "never_created_ledger.jsonl").exists()))
    return [json.loads(p.read_text()) for p in sorted(trials.glob("*.json"))]


def dm_ci(archive: dict):
    """Cluster-robust 95 pct interval on the paired d = loss_incumbent - loss_model."""
    per = archive.get("differential")
    if not per:
        return None
    groups = defaultdict(list)
    for _event_id, _ts, cluster, loss_model, loss_close in per:
        groups[str(cluster)].append(float(loss_close) - float(loss_model))
    means = [float(np.mean(v)) for v in groups.values()]
    sizes = [len(v) for v in groups.values()]
    n, g = sum(sizes), len(means)
    mean = sum(m * s for m, s in zip(means, sizes)) / n
    var = sum((s * (m - mean)) ** 2 for m, s in zip(means, sizes)) / (n * n) * (g / max(1, g - 1))
    se = math.sqrt(var) if var > 0 else float("nan")
    return mean, mean - 1.96 * se, mean + 1.96 * se, g, n


def report(rows: list) -> None:
    t0 = [r for r in rows if r["tier"] == "T0"]
    t1 = [r for r in rows if r["tier"] == "T1"]
    print("\nresult rows: %d = %d T0 (%d COVERED, %d UNCOVERED) + %d T1 SCREEN" % (
        len(rows), len(t0), sum(1 for r in t0 if r["verdict"] == "COVERED"),
        sum(1 for r in t0 if r["verdict"] != "COVERED"), len(t1)))
    print("\n%-30s %5s %8s %14s %8s" % ("family", "T0", "COVERED", "best filled/n", "pct"))
    for family in sorted({r["family"] for r in t0}):
        mine = [r for r in t0 if r["family"] == family]
        filled = max(int(r["n_eff"] or 0) for r in mine)
        print("%-30s %5d %8d %14s %8.4f" % (
            family, len(mine), sum(1 for r in mine if r["verdict"] == "COVERED"),
            "%d/%d" % (filled, mine[0]["n"]), filled / max(1, mine[0]["n"])))

    best: dict = {}
    for row in t1:
        if row["brier_model"] is None:
            continue
        improvement = row["brier_close"] - row["brier_model"]
        if row["family"] not in best or improvement > best[row["family"]][0]:
            best[row["family"]] = (improvement, row)
    print("\n%-30s %5s %-40s %9s %9s %10s %9s %28s" % (
        "family", "n", "best member / transform", "b_incumb", "b_model", "improve",
        "screen_p", "DM CI 95 (recomputed)"))
    for family in sorted(best):
        improvement, row = best[family]
        interval = dm_ci(row.get("archive") or {})
        print("%-30s %5d %-40s %9.6f %9.6f %+10.6f %9.4f %28s" % (
            family, sum(1 for r in t1 if r["family"] == family), row["archive"]["feature"],
            row["brier_close"], row["brier_model"], improvement,
            row["archive"].get("screen_p", float("nan")),
            "n/a" if interval is None else "[%+.6f, %+.6f] g=%d"
            % (interval[1], interval[2], interval[3])))
        print("        incumbent=%s n=%d" % (row["incumbent"], row["n"]))

    positive = [r for r in t1 if (ci := dm_ci(r.get("archive") or {})) is not None and ci[1] > 0]
    print("\nT1 with recomputed CI lower bound > 0: %d of %d (expected ~%.1f by chance at 2.5 pct)"
          % (len(positive), len(t1), 0.025 * len(t1)))
    for row in positive:
        print("   %s %s improve=%+.6f" % (row["family"], row["archive"]["feature"],
                                          row["brier_close"] - row["brier_model"]))
    improved = sum(1 for r in t1 if r["brier_model"] is not None
                   and r["brier_close"] - r["brier_model"] > 0)
    print("improved (any positive): %d of %d (%.1f pct) -- a SCREEN is a NON-FINDING"
          % (improved, len(t1), 100.0 * improved / max(1, len(t1))))


def main() -> None:
    parser = argparse.ArgumentParser(description="S111 local factory screen (charges off)")
    parser.add_argument("--out-dir", required=True, help="scratch directory; nothing else is written")
    report(run(Path(parser.parse_args().out_dir)))


if __name__ == "__main__":
    main()
