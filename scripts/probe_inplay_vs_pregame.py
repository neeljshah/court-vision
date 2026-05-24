"""probe_inplay_vs_pregame.py — measure in-play vs pre-game projection MAE.

Cycle 88n shipped save_live_predictions.py, which persists in-game projections
to data/predictions/<date>_inplay.csv tagged by pred_kind (Q1_inplay_HHMM,
Q2_inplay_HHMM, ...). But until now there was NO harness to retroactively
compare those in-play projections against the cycle-47/49/80 pre-game
predictions once the actual box scores are known.

Without such a harness, we can never empirically prove that the cycle-88
live-update logic actually improves on the pre-game prediction. This script
is the framework: for a given date, it loads the pre-game ledger, the in-play
ledger (grouped by Q1/Q2/Q3/...), and the realised actuals from
build_pergame_dataset, then computes per-stat MAE for each pred_kind and
writes a markdown comparison table.

Critically, the script is GRACEFUL when in-play data hasn't accumulated yet
— it writes a "no data; framework operational" report and exits 0, so it
can be safely wired into nightly_report immediately.

Run:
    python scripts/probe_inplay_vs_pregame.py --date 2026-05-24
    python scripts/probe_inplay_vs_pregame.py --date 2026-05-24 \\
        --output scripts/_results/inplay_vs_pregame_2026-05-24.md
"""
from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# Type aliases for readability.
StatKey   = Tuple[str, str]               # (player_id, stat)
KindKey   = Tuple[str, str, str]          # (player_id, stat, pred_kind)


# ── loaders ──────────────────────────────────────────────────────────────

def load_pregame(path: str) -> Dict[StatKey, float]:
    """Read pre-game ledger as {(player_id, stat): pred}.

    Multiple rows for the same (player_id, stat) — e.g. when predict_slate
    is rerun mid-day — collapse to the LAST one written, mirroring the
    cycle-49 "latest write wins" semantics of the ledger consumers.
    """
    out: Dict[StatKey, float] = {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            pid = (r.get("player_id") or "").strip()
            stat = (r.get("stat") or "").strip().lower()
            if not pid or stat not in STATS:
                continue
            try:
                out[(pid, stat)] = float(r.get("pred") or "nan")
            except ValueError:
                continue
    return out


def load_inplay(path: str) -> Dict[KindKey, float]:
    """Read in-play ledger as {(player_id, stat, kind): MEDIAN over snapshots}.

    The in-play ledger may hold many snapshots per (player, stat, pred_kind)
    — e.g. five Q2_inplay snapshots written between 8:00 and 6:00 of Q2.
    We collapse to the median so a single anomalous snapshot doesn't tilt
    the per-kind MAE. (Mean would over-weight outliers — and projection
    spikes during scoring runs are exactly the noise we want to suppress.)
    """
    buckets: Dict[KindKey, List[float]] = defaultdict(list)
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            pid = (r.get("player_id") or "").strip()
            stat = (r.get("stat") or "").strip().lower()
            raw_kind = (r.get("pred_kind") or "").strip()
            if not pid or stat not in STATS or not raw_kind:
                continue
            # Normalise kind: drop trailing _HHMM so Q2_inplay_1942 and
            # Q2_inplay_2003 both bucket as "Q2_inplay" for per-quarter MAE.
            kind = _normalise_kind(raw_kind)
            try:
                buckets[(pid, stat, kind)].append(float(r.get("pred") or "nan"))
            except ValueError:
                continue
    return {k: statistics.median(v) for k, v in buckets.items() if v}


def _normalise_kind(raw: str) -> str:
    """Q2_inplay_1942 -> Q2_inplay; manual_check -> manual_check."""
    parts = raw.split("_")
    if (len(parts) >= 3 and parts[0].startswith("Q")
            and parts[1] == "inplay" and parts[-1].isdigit()):
        return "_".join(parts[:2])
    return raw


def load_actuals_from_dataset(date_str: str) -> Dict[StatKey, float]:
    """Filter build_pergame_dataset rows to date_str → {(pid,stat): actual}.

    Heavy import is deferred so the no-inplay-yet path and the test fixtures
    don't pay the cost. If something fails (no gamelogs yet, import error,
    etc.) we return {} — MAE will then be empty and the report just flags
    actuals-missing rather than crashing.
    """
    try:
        from src.prediction.prop_pergame import build_pergame_dataset  # noqa
    except Exception:
        return {}
    try:
        rows, _ = build_pergame_dataset(min_prior=0)
    except Exception:
        return {}
    return actuals_map_from_rows(rows, date_str)


def actuals_map_from_rows(rows: List[dict], date_str: str) -> Dict[StatKey, float]:
    """Pure helper — easy to unit test without touching disk."""
    out: Dict[StatKey, float] = {}
    for r in rows:
        if str(r.get("date", ""))[:10] != date_str:
            continue
        pid = str(r.get("player_id") or "").strip()
        if not pid:
            continue
        for stat in STATS:
            v = r.get(f"target_{stat}")
            if v is None:
                continue
            try:
                out[(pid, stat)] = float(v)
            except (TypeError, ValueError):
                continue
    return out


# ── MAE computation ───────────────────────────────────────────────────────

def per_stat_mae(preds: Dict[StatKey, float],
                  actuals: Dict[StatKey, float]) -> Dict[str, Tuple[int, float]]:
    """Return {stat: (n, mae)} over (pid, stat) keys in BOTH preds and actuals."""
    by_stat: Dict[str, List[float]] = defaultdict(list)
    for (pid, stat), pred in preds.items():
        actual = actuals.get((pid, stat))
        if actual is None:
            continue
        by_stat[stat].append(abs(pred - actual))
    return {s: (len(errs), sum(errs) / len(errs))
            for s, errs in by_stat.items() if errs}


def per_stat_mae_inplay(inplay: Dict[KindKey, float],
                          actuals: Dict[StatKey, float]
                          ) -> Dict[str, Dict[str, Tuple[int, float]]]:
    """Return {stat: {kind: (n, mae)}} for inplay predictions."""
    by_stat_kind: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for (pid, stat, kind), pred in inplay.items():
        actual = actuals.get((pid, stat))
        if actual is None:
            continue
        by_stat_kind[stat][kind].append(abs(pred - actual))
    out: Dict[str, Dict[str, Tuple[int, float]]] = {}
    for stat, by_kind in by_stat_kind.items():
        out[stat] = {k: (len(errs), sum(errs) / len(errs))
                     for k, errs in by_kind.items() if errs}
    return out


# ── report assembly ───────────────────────────────────────────────────────

def build_report(date_str: str,
                  pregame_mae: Dict[str, Tuple[int, float]],
                  inplay_mae: Dict[str, Dict[str, Tuple[int, float]]],
                  status: str = "ok") -> Tuple[str, dict]:
    """Build the markdown report + a console-friendly summary dict."""
    lines: List[str] = []
    lines.append(f"# In-play vs pre-game MAE — {date_str}")
    lines.append("")

    if status == "no_inplay_data":
        lines.append("**Status:** NO INPLAY DATA YET for this date.")
        lines.append("")
        lines.append("Framework is operational. Once "
                     "`scripts/save_live_predictions.py` accumulates "
                     "snapshots for live games, this report will populate "
                     "per-quarter MAE rows automatically.")
        return "\n".join(lines) + "\n", {"status": "no_inplay_data"}

    # Discover the union of inplay pred_kinds across stats, sorted Q1 → ...
    all_kinds = sorted({k for stat_map in inplay_mae.values()
                          for k in stat_map.keys()})

    # Header row
    header_cells = ["stat", "n_pre", "pregame_mae"]
    for k in all_kinds:
        header_cells.append(f"{k}_mae")
    header_cells.append("best")
    lines.append("| " + " | ".join(header_cells) + " |")
    lines.append("|" + "|".join(["---"] * len(header_cells)) + "|")

    summary_best: Dict[str, Tuple[str, float]] = {}
    for stat in STATS:
        n_pre, mae_pre = pregame_mae.get(stat, (0, float("nan")))
        if n_pre == 0:
            continue
        row_cells = [stat, str(n_pre), f"{mae_pre:.4f}"]
        best_kind = "pregame"
        best_mae = mae_pre
        for k in all_kinds:
            entry = inplay_mae.get(stat, {}).get(k)
            if entry is None:
                row_cells.append("—")
                continue
            n_k, mae_k = entry
            row_cells.append(f"{mae_k:.4f} (n={n_k})")
            if mae_k < best_mae:
                best_mae = mae_k
                best_kind = k
        summary_best[stat] = (best_kind, best_mae)
        row_cells.append(best_kind)
        lines.append("| " + " | ".join(row_cells) + " |")

    lines.append("")
    lines.append("## Per-stat winners")
    lines.append("")
    for stat, (kind, mae) in summary_best.items():
        lines.append(f"- **{stat}**: {kind} at MAE={mae:.4f}")

    # Console summary picks the stat with the largest pregame n.
    if summary_best:
        focus_stat = max(summary_best, key=lambda s: pregame_mae[s][0])
        focus_kind, focus_mae = summary_best[focus_stat]
        summary = {
            "status": "ok",
            "focus_stat": focus_stat,
            "pregame_mae": pregame_mae[focus_stat][1],
            "best_inplay_mae": focus_mae,
            "best_kind": focus_kind,
        }
    else:
        summary = {"status": "no_overlap"}

    return "\n".join(lines) + "\n", summary


def write_report(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


# ── CLI ───────────────────────────────────────────────────────────────────

def run(date_str: str,
        output: str,
        pred_dir: Optional[str] = None,
        actuals_loader=load_actuals_from_dataset) -> int:
    """Test-friendly entry point.

    Args:
        date_str: ISO date for the report.
        output:   Where to write the markdown.
        pred_dir: Override data/predictions/ — used by tests.
        actuals_loader: Callable(date_str) -> {(pid, stat): actual}. Injected
            by tests so we don't touch the real per-game dataset.
    """
    pred_dir = pred_dir or os.path.join(PROJECT_DIR, "data", "predictions")
    pre_path = os.path.join(pred_dir, f"{date_str}.csv")
    inp_path = os.path.join(pred_dir, f"{date_str}_inplay.csv")

    if not os.path.exists(pre_path):
        print(f"[fail] no pregame ledger for {date_str}: {pre_path}")
        return 1

    if not os.path.exists(inp_path):
        print(f"[empty] NO INPLAY DATA YET for {date_str}; "
              "harness is ready for when data accumulates.")
        md, _ = build_report(date_str, {}, {}, status="no_inplay_data")
        write_report(output, md)
        return 0

    pregame = load_pregame(pre_path)
    inplay  = load_inplay(inp_path)
    actuals = actuals_loader(date_str)

    pre_mae = per_stat_mae(pregame, actuals)
    inp_mae = per_stat_mae_inplay(inplay, actuals)

    md, summary = build_report(date_str, pre_mae, inp_mae, status="ok")
    write_report(output, md)

    if summary.get("status") == "no_overlap":
        print(f"{date_str}: no overlap between predictions and actuals "
              "(actuals missing for every (player, stat) in the ledger)")
    else:
        print(f"{date_str}: focus_stat={summary['focus_stat']} "
              f"pregame_mae={summary['pregame_mae']:.4f}, "
              f"best_inplay_mae={summary['best_inplay_mae']:.4f} "
              f"(kind={summary['best_kind']})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--output", default=None,
                    help="Markdown report path (default: "
                         "scripts/_results/inplay_vs_pregame_<date>.md)")
    args = ap.parse_args()

    out = args.output or os.path.join(
        PROJECT_DIR, "scripts", "_results",
        f"inplay_vs_pregame_{args.date}.md")
    return run(args.date, out)


if __name__ == "__main__":
    sys.exit(main())
