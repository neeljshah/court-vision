"""Coverage summary for cross_sport_market depth_imbalance descriptors --
ALL 8 sports, with EXPLICIT zero-coverage rows for sports with no captures
this window (nba, soccer) instead of silently omitting them.

Reuses depth_imbalance_prep._prep_sport (the tidy-prep row builder already
verified this session, see that module's docstring) -- this file only adds
the summary layer over the 8-sport universe; depth_imbalance_prep.py itself
intentionally only loops its 6-sport _SPORTS allowlist (nba/soccer have no
data/cache/depth_history/<sport>/ dir this window, so _load_sport_raw's glob
returns [] for them and _prep_sport returns an empty frame -- no code change
needed there to cover them here).

DESCRIPTIVE METADATA ONLY: per-sport execution-quality (orderbook depth
imbalance) coverage + distribution stats for realism bookkeeping. Not a
predictive signal, no $/edge claim (edge_claimed:false in the output).

CLI: python -m domains.cross_sport_market.depth_imbalance_coverage
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.quant.depth_imbalance_prep import _prep_sport

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "data" / "domains" / "cross_sport_market" / "depth_imbalance_coverage.json"

# Canonical 8-sport universe -- matches line_dynamics_prep.py's _SPORTS tuple
# (the cross-sport-market module that already enumerates all 8, vs.
# depth_imbalance_prep.py's narrower 6-sport allowlist).
ALL_SPORTS = ("kbo", "mlb", "nba", "npb", "soccer", "soccer_intl", "tennis", "wnba")


def _summarize_sport(sport: str) -> dict:
    df = _prep_sport(sport)
    if df.empty:
        return {
            "sport": sport,
            "coverage": "zero",
            "n_rows": 0,
            "mean_imbalance": None,
            "bid_heavy_rate": None,
        }
    return {
        "sport": sport,
        "coverage": "present",
        "n_rows": int(len(df)),
        "mean_imbalance": round(float(df["imbalance"].mean()), 4),
        "bid_heavy_rate": round(float(df["bid_heavy_flag"].mean()), 4),
    }


def build(out_path: Path | None = None) -> dict:
    out_path = out_path or OUT_PATH
    rows = [_summarize_sport(s) for s in ALL_SPORTS]
    n_present = sum(1 for r in rows if r["coverage"] == "present")
    summary = {
        "component": "depth_imbalance_coverage",
        "n_sports_total": len(ALL_SPORTS),
        "n_sports_covered": n_present,
        "n_sports_zero": len(ALL_SPORTS) - n_present,
        "rows": rows,
        "edge_claimed": False,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


def main() -> int:
    print(json.dumps(build(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
