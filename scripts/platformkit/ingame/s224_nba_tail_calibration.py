"""S224 NBA in-game tail reliability measurement.

The module reads one bounded checkpoint parquet and reports the frozen twenty
one-percent market-probability bins.  S123's default incumbent is the raw
market probability, so its Brier is recorded separately but is identical by
construction.  This is a descriptive calibration measurement; it fits no arm.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts.platformkit.ingame.gap_effective_n import effective_sample_size

ROOT = Path(__file__).resolve().parents[3]
CHECKPOINTS = ROOT / "data" / "cache" / "inplay_odds" / "nba_checkpoints_full.parquet"
EVIDENCE = ROOT / "docs" / "evidence" / "harness"
STEM = "S224_ingame_tail_calibration_2026-09-04"
BAR = 0.004
LOWER_EDGES = tuple(round(index / 100.0, 2) for index in range(0, 10))
UPPER_EDGES = tuple(round(index / 100.0, 2) for index in range(90, 100))
Z_ALPHA_TWO_SIDED = 1.959963984540054
Z_POWER_80 = 0.8416212335729143


def frozen_bin_labels() -> tuple[str, ...]:
    """Return the twenty immutable one-percent tail labels in display order."""
    low = tuple("%02d-%02d" % (start, start + 1) for start in range(0, 10))
    high = tuple("%02d-%02d" % (start, start + 1) for start in range(90, 100))
    return low + high


def _bin_label(probability: float) -> str:
    if probability <= 0.10:
        index = min(int(math.floor(probability * 100.0)), 9)
        return "%02d-%02d" % (index, index + 1)
    if probability >= 0.90:
        index = min(int(math.floor(probability * 100.0)), 99)
        return "%02d-%02d" % (index, index + 1)
    return "MIDDLE"


def assign_frozen_bins(rows: pd.DataFrame) -> pd.DataFrame:
    """Assign every valid probability to exactly one tail bin or MIDDLE."""
    required = {"game_id", "market_prob", "outcome_home_win"}
    missing = required.difference(rows.columns)
    if missing:
        raise ValueError("missing required columns: %s" % ", ".join(sorted(missing)))
    frame = rows.loc[:, ["game_id", "market_prob", "outcome_home_win"]].copy()
    frame["market_prob"] = frame["market_prob"].astype(float)
    frame["outcome_home_win"] = frame["outcome_home_win"].astype(float)
    if (not np.isfinite(frame["market_prob"]).all() or
            not frame["market_prob"].between(0.0, 1.0, inclusive="both").all()):
        raise ValueError("market probabilities must be finite values in [0, 1]")
    if not frame["outcome_home_win"].isin((0.0, 1.0)).all():
        raise ValueError("outcomes must be binary")
    frame["bin"] = frame["market_prob"].map(_bin_label)
    assigned = frame["bin"].isin(frozen_bin_labels()) | frame["bin"].eq("MIDDLE")
    assert bool(assigned.all()), "fall-through bin assignment"
    return frame


def _mde(n_eff: float) -> float | None:
    """80 percent-power MDE using the bounded paired Brier-difference scale."""
    if n_eff <= 0.0:
        return None
    return float((Z_ALPHA_TWO_SIDED + Z_POWER_80) / math.sqrt(n_eff))


def summarize(frame: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compute the complete frozen table without excluding lopsided games."""
    binned = assign_frozen_bins(frame)
    labels = frozen_bin_labels()
    tail_total = int(binned["bin"].isin(labels).sum())
    rows: list[dict[str, Any]] = []
    for label in labels:
        part = binned[binned["bin"] == label]
        count = int(len(part))
        if count:
            market = part["market_prob"].to_numpy(dtype=float)
            outcome = part["outcome_home_win"].to_numpy(dtype=float)
            loss = (market - outcome) ** 2
            ess = effective_sample_size(pd.DataFrame({
                "game": part["game_id"].astype(str), "loss_differential": loss,
            }))
            realized = float(outcome.mean())
            brier = float(loss.mean())
            ece_abs = float(abs(market.mean() - realized))
            n_eff = float(ess["n_eff"])
            mde = _mde(n_eff)
        else:
            realized = brier = ece_abs = 0.0
            n_eff, mde = 0.0, None
        rows.append({
            "bin": label,
            "count": count,
            "realized_rate": realized,
            "market_brier": brier,
            "incumbent_brier": brier,
            "ece_absolute": ece_abs,
            "ece_weighted": float(count / tail_total * ece_abs) if tail_total else 0.0,
            "n_eff_game_clustered": n_eff,
            "mde_80pct": mde,
            "status": "SCORABLE" if mde is not None and mde <= BAR else "UNDERPOWERED",
        })
    sides = {}
    for name, labels_for_side in (("low", labels[:10]), ("high", labels[10:])):
        part = binned[binned["bin"].isin(labels_for_side)]
        sides[name] = {"ticks": int(len(part)), "games": int(part["game_id"].nunique()),
                       "realized_rate": float(part["outcome_home_win"].mean())}
    counts = {"total": int(len(binned)), "tail": tail_total,
              "middle": int((binned["bin"] == "MIDDLE").sum())}
    assert counts["total"] == counts["tail"] + counts["middle"], "denominator loss"
    summary = {
        "denominator": counts,
        "sides": sides,
        "tail_ece_weighted": float(sum(row["ece_weighted"] for row in rows)),
        "scorable_bins": int(sum(row["status"] == "SCORABLE" for row in rows)),
        "underpowered_bins": int(sum(row["status"] == "UNDERPOWERED" for row in rows)),
        "verdict": "CLOSED AT LIMIT" if all(row["status"] == "UNDERPOWERED" for row in rows)
        else "TAIL BINS PARTIALLY SCORABLE",
    }
    return rows, summary


def run(source: Path = CHECKPOINTS, output_dir: Path = EVIDENCE) -> dict[str, Any]:
    """Read the checkpoint store once and write deterministic CSV and JSON evidence."""
    source = Path(source)
    raw = pd.read_parquet(source)
    table, summary = summarize(raw)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / (STEM + "_per_bin.csv")
    fields = list(table[0])
    with csv_path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(table)
    report = {
        "bar": BAR,
        "incumbent": "S123 market default; identical to market by construction",
        "input": {"path": str(source), "bytes": int(source.stat().st_size),
                  "rows": int(len(raw)), "resolution": "not applicable"},
        "mde_method": ("(z_0.975 + z_0.80) / sqrt(n_eff), with bounded paired "
                       "Brier-difference scale 1 and game-clustered n_eff"),
        "per_bin_csv": str(csv_path),
        "bins": table,
        **summary,
    }
    json_path = output_dir / (STEM + "_summary.json")
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return report


def _render(rows: list[dict[str, Any]]) -> str:
    header = "BIN | N | REALIZED | MARKET_BRIER | INCUMBENT_BRIER | ECE_WEIGHTED | N_EFF | MDE | STATUS"
    lines = [header]
    for row in rows:
        mde = "-" if row["mde_80pct"] is None else "%.6f" % row["mde_80pct"]
        lines.append("%s | %d | %.6f | %.6f | %.6f | %.6f | %.2f | %s | %s" % (
            row["bin"], row["count"], row["realized_rate"], row["market_brier"],
            row["incumbent_brier"], row["ece_weighted"], row["n_eff_game_clustered"],
            mde, row["status"]))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="S224 tail calibration measurement")
    parser.add_argument("--source", type=Path, default=CHECKPOINTS)
    parser.add_argument("--output-dir", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    report = run(args.source, args.output_dir)
    rows = report["bins"]
    print("S224 LOW TAIL")
    print(_render(rows[:10]))
    print("S224 HIGH TAIL")
    print(_render(rows[10:]))
    denominator = report["denominator"]
    low, high = report["sides"]["low"], report["sides"]["high"]
    print("S224 premise low=%d ticks/%d games rate=%.6f high=%d ticks/%d games rate=%.6f" % (
        low["ticks"], low["games"], low["realized_rate"],
        high["ticks"], high["games"], high["realized_rate"]))
    print("S224 denominator total=%d tail=%d middle=%d dropped=0" % (
        denominator["total"], denominator["tail"], denominator["middle"]))
    print("S224 scorable_bins=%d underpowered_bins=%d verdict=%s" % (
        report["scorable_bins"], report["underpowered_bins"], report["verdict"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
