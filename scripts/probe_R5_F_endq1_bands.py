"""probe_R5_F_endq1_bands.py -- R5-F validation: endQ1 quantile bands.

Validates the endQ1 calibration on a held-out 25% of games (last 25% by date).

For each held-out (player, game, stat):
  q10 = max(0, q50 - Z80 * scale * sigma)  [asymmetric stats]
  q10 = q50 - Z80 * scale * sigma           [symmetric stats]
  q90 = q50 + Z80 * scale * sigma

Ship gate:
  - 7/7 stats with coverage in [0.78, 0.82]
  - sigma_endQ1 > sigma_endQ2 for all 7 stats (loaded from
    data/models/live_quantile_calibration.json)

Writes:
  scripts/_results/improve_R5_F_endq1_bands.md
  scripts/_results/improve_R5_F_endq1_bands.json

Run:
    python scripts/probe_R5_F_endq1_bands.py
    python scripts/probe_R5_F_endq1_bands.py --max-games 200
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae as rim  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
_Z80 = 1.2816

_CAL_PATH = os.path.join(PROJECT_DIR, "data", "models", "quantile_calibration_endq1.json")
_ENQ2_CAL_PATH = os.path.join(PROJECT_DIR, "data", "models", "live_quantile_calibration.json")
_OUT_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")


def _load_calibration() -> Dict[str, dict]:
    with open(_CAL_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _load_endq2_sigmas() -> Dict[str, float]:
    try:
        with open(_ENQ2_CAL_PATH, encoding="utf-8") as fh:
            cal = json.load(fh)
        return {stat: float(cal["endQ2"][stat]["sigma"]) for stat in STATS
                if stat in cal.get("endQ2", {})}
    except Exception:
        return {}


def _collect_holdout_pairs(max_games: int = 0) -> Dict[str, List[Tuple[float, float]]]:
    """Collect (q50_proj, actual) for the last 25% of games by date."""
    from src.prediction.live_engine import project_from_snapshot

    qstats = rim.load_quarter_stats()
    game_ids = list(qstats["game_id"].unique())

    # Sort by date using find_game_date (best effort; fallback to game_id string sort)
    print(f"  sorting {len(game_ids)} games by date...", flush=True)
    dated: List[Tuple[str, str]] = []
    for gid in game_ids:
        d = rim.find_game_date(gid, qstats) or gid
        dated.append((d, gid))
    dated.sort(key=lambda x: x[0])
    sorted_ids = [gid for _, gid in dated]

    # Take last 25% as holdout
    n_holdout = max(1, len(sorted_ids) // 4)
    holdout_ids = set(sorted_ids[-n_holdout:])
    if max_games:
        holdout_ids = set(list(holdout_ids)[:max_games])

    print(f"  holdout games: {len(holdout_ids)} (last 25% by date)", flush=True)

    out: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
    n_ok = 0
    for gid in holdout_ids:
        actuals = rim.actuals_for_game(gid, qstats)
        if not actuals:
            continue
        snap = rim.build_snapshot(gid, "endQ1", qstats)
        if snap is None:
            continue
        try:
            rows = project_from_snapshot(snap)
        except Exception:
            continue
        for r in rows:
            pid = r.get("player_id")
            stat = r.get("stat")
            if pid is None or stat not in STATS:
                continue
            try:
                proj = float(r.get("projected_final", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            actual = actuals.get((int(pid), stat))
            if actual is None:
                continue
            out[stat].append((proj, float(actual)))
        n_ok += 1
    print(f"  holdout games with endQ1 data: {n_ok}", flush=True)
    return out


def _compute_coverage(
    pairs: List[Tuple[float, float]],
    sigma: float,
    scale: float,
    asymmetric: bool,
) -> Tuple[float, int]:
    """Return (coverage, n)."""
    if not pairs:
        return 0.0, 0
    arr = np.asarray(pairs, dtype=float)
    projs, actuals = arr[:, 0], arr[:, 1]
    half = scale * sigma * _Z80
    q10 = np.maximum(0.0, projs - half) if asymmetric else projs - half
    q90 = projs + half
    cov = float(((actuals >= q10) & (actuals <= q90)).mean())
    return cov, len(pairs)


def probe(max_games: int = 0) -> int:
    print("[probe-R5-F] loading calibration...", flush=True)
    cal = _load_calibration()
    endq2_sigmas = _load_endq2_sigmas()

    print("[probe-R5-F] collecting holdout pairs...", flush=True)
    pairs = _collect_holdout_pairs(max_games=max_games)

    results: Dict[str, dict] = {}
    in_band_count = 0
    sigma_sanity_pass = 0

    print("\n  stat   sigma_Q1  sigma_Q2  Q1>Q2?  cov_holdout  n     in_band?")
    print("  " + "-" * 68)
    for stat in STATS:
        entry = cal.get(stat)
        if entry is None:
            print(f"  {stat:4s}  [MISSING calibration entry]")
            results[stat] = {"error": "missing calibration entry"}
            continue

        sigma = float(entry["sigma"])
        scale = float(entry["scale"])
        asym = bool(entry.get("asymmetric", False))
        sigma_q2 = endq2_sigmas.get(stat, float("nan"))

        cov, n = _compute_coverage(pairs.get(stat, []), sigma, scale, asym)
        in_band = 0.78 <= cov <= 0.82
        sigma_ok = sigma > sigma_q2 if not np.isnan(sigma_q2) else None

        if in_band:
            in_band_count += 1
        if sigma_ok:
            sigma_sanity_pass += 1

        in_band_str = "YES" if in_band else "NO "
        sigma_ok_str = ("YES" if sigma_ok else "NO ") if sigma_ok is not None else "N/A"

        print(
            f"  {stat:4s}  {sigma:7.3f}  {sigma_q2:7.3f}  {sigma_ok_str}  "
            f"{cov:.4f}       {n:5d}  {in_band_str}",
            flush=True,
        )

        results[stat] = {
            "sigma_endQ1": round(sigma, 4),
            "sigma_endQ2": round(sigma_q2, 4) if not np.isnan(sigma_q2) else None,
            "sigma_sanity_pass": bool(sigma_ok) if sigma_ok is not None else None,
            "coverage_holdout": round(cov, 4),
            "n_holdout": n,
            "in_band": bool(in_band),
        }

    # Gate evaluation
    all_in_band = in_band_count == 7
    sigma_gate = sigma_sanity_pass == 7
    gate_pass = all_in_band and sigma_gate

    verdict = "SHIP" if gate_pass else "REJECT"
    print(f"\n  Coverage gate (7/7 in [0.78,0.82]): {in_band_count}/7 {'PASS' if all_in_band else 'FAIL'}")
    print(f"  Sigma sanity gate (7/7 endQ1>endQ2): {sigma_sanity_pass}/7 {'PASS' if sigma_gate else 'FAIL'}")
    print(f"  Overall: {verdict}", flush=True)

    # Write results
    os.makedirs(_OUT_DIR, exist_ok=True)
    summary = {
        "verdict": verdict,
        "stats": results,
        "gates": {
            "coverage_in_band": in_band_count,
            "coverage_in_band_pass": bool(all_in_band),
            "sigma_sanity_pass": sigma_sanity_pass,
            "sigma_sanity_gate_pass": bool(sigma_gate),
        },
    }
    json_path = os.path.join(_OUT_DIR, "improve_R5_F_endq1_bands.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    print(f"  wrote {json_path}", flush=True)

    # Markdown report
    md_lines = [
        "# R5-F endQ1 Quantile Band Calibration — Probe Results",
        "",
        f"**Verdict: {verdict}**",
        "",
        f"- Coverage gate (7/7 in [0.78, 0.82]): {in_band_count}/7 {'PASS' if all_in_band else 'FAIL'}",
        f"- Sigma sanity gate (7/7 endQ1 > endQ2): {sigma_sanity_pass}/7 {'PASS' if sigma_gate else 'FAIL'}",
        "",
        "## Per-stat results (holdout = last 25% of games by date)",
        "",
        "| stat | sigma_endQ1 | sigma_endQ2 | Q1>Q2? | coverage | n | in_band? |",
        "|------|-------------|-------------|--------|----------|---|----------|",
    ]
    for stat in STATS:
        r = results.get(stat, {})
        if "error" in r:
            md_lines.append(f"| {stat} | — | — | — | — | — | ERROR |")
            continue
        md_lines.append(
            f"| {stat} | {r['sigma_endQ1']:.4f} | "
            f"{r['sigma_endQ2']:.4f} | "
            f"{'YES' if r['sigma_sanity_pass'] else 'NO'} | "
            f"{r['coverage_holdout']:.4f} | {r['n_holdout']} | "
            f"{'YES' if r['in_band'] else 'NO'} |"
        )
    md_lines += [
        "",
        "## Gate definition",
        "",
        "- Coverage in band: `0.78 <= empirical_coverage <= 0.82` on held-out 25% of games.",
        "- Sigma sanity: `sigma_endQ1 > sigma_endQ2` — more uncertainty earlier in the game.",
        "- Ship requires BOTH gates at 7/7.",
        "",
    ]
    md_path = os.path.join(_OUT_DIR, "improve_R5_F_endq1_bands.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md_lines) + "\n")
    print(f"  wrote {md_path}", flush=True)

    return 0 if gate_pass else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="R5-F endQ1 band probe (held-out 25%).")
    ap.add_argument("--max-games", type=int, default=0,
                    help="Limit holdout to first N holdout games (debug).")
    args = ap.parse_args()
    import warnings
    warnings.filterwarnings("ignore")
    return probe(max_games=args.max_games)


if __name__ == "__main__":
    sys.exit(main())
