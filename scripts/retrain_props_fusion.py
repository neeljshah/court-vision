"""
retrain_props_fusion.py — Retrain all 7 prop models with fused features + sample_weight.

Compares R2 vs pre-fusion baseline and writes vault/Improvements/fusion_v1.md.

Usage:
    python scripts/retrain_props_fusion.py [--seasons 2022-23 2023-24 2024-25]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

VAULT_DIR   = PROJECT_DIR / "vault" / "Improvements"
VAULT_DIR.mkdir(parents=True, exist_ok=True)

# Pre-fusion R2 baseline (from CLAUDE.md session 33)
_BASELINE_R2 = {
    "pts":  0.47,
    "reb":  0.40,
    "ast":  0.46,
    "fg3m": 0.28,
    "blk":  0.18,
    "tov":  0.25,
    "stl":  0.07,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", default=["2022-23", "2023-24", "2024-25"])
    args = ap.parse_args()

    print(f"[retrain_fusion] Starting retrain with seasons: {args.seasons}")
    print(f"[retrain_fusion] data_confidence will be used as sample_weight")

    from src.prediction.player_props import train_props
    results = train_props(seasons=args.seasons, force=True)

    if not results:
        print("[retrain_fusion] No results returned (possibly insufficient data)")
        return

    # Compare vs baseline
    print("\n=== R2 Comparison (Fusion vs Baseline) ===")
    rows = []
    for stat, metrics in results.items():
        new_r2  = metrics.get("r2", 0.0)
        base_r2 = _BASELINE_R2.get(stat, 0.0)
        delta   = round(new_r2 - base_r2, 4)
        pct     = round((delta / max(base_r2, 0.001)) * 100, 1) if base_r2 else 0.0
        sign    = "+" if delta >= 0 else ""
        print(f"  {stat.upper():<6} baseline={base_r2:.4f}  new={new_r2:.4f}  "
              f"delta={sign}{delta:.4f} ({sign}{pct}%)")
        rows.append({
            "stat": stat, "baseline_r2": base_r2,
            "new_r2": new_r2, "delta": delta, "pct": pct,
            "mae": metrics.get("mae", None),
        })

    # Write vault log
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M")
    out  = VAULT_DIR / "fusion_v1.md"
    lines = [
        f"# Fusion v1 — Prop Model Retrain",
        f"",
        f"**Date:** {ts}",
        f"**Seasons:** {', '.join(args.seasons)}",
        f"**Change:** Added xPTS_per_shot feature + data_confidence sample_weight",
        f"",
        f"## R2 Comparison",
        f"",
        f"| Stat | Baseline R2 | Fusion R2 | Delta | % Change | MAE |",
        f"|------|-------------|-----------|-------|----------|-----|",
    ]
    for r in rows:
        sign = "+" if r["delta"] >= 0 else ""
        lines.append(
            f"| {r['stat'].upper()} | {r['baseline_r2']:.4f} | {r['new_r2']:.4f} | "
            f"{sign}{r['delta']:.4f} | {sign}{r['pct']:.1f}% | "
            f"{r['mae']:.3f} |"
        )
    lines += [
        f"",
        f"## Notes",
        f"- `xPTS_per_shot`: heuristic zone-based (CV dataset too small for LR fit)",
        f"- `data_confidence` as sample_weight: NBA API rows ~0.85, CV rows ~0.95",
        f"- Next: grow CV dataset (Phase G batch) to enable LR-fitted xPTS",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[retrain_fusion] Vault log written to {out}")


if __name__ == "__main__":
    main()
