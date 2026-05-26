"""Probe R12_F4: PrizePicks systematic offset vs OOF q50 predictions.

Cross-reference 2026-05-25 PP snapshots with OOF q50 predictions to identify
per-stat systematic mispricing. PP rows have no player_id; we fall back to
matching by player_name (NFKD-normalized) and using each player's MOST RECENT
OOF q50 for the matching stat as a proxy for what the model would predict.

This is diagnostic only -- no production paths modified.
"""
from __future__ import annotations

import json
import sys
import unicodedata
from math import erfc, sqrt
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
PP_CSV = PROJECT_DIR / "data" / "lines" / "2026-05-25_pp.csv"
OOF_PQ = PROJECT_DIR / "data" / "cache" / "pregame_oof.parquet"
PLAYERINFO_DIR = PROJECT_DIR / "data" / "cache" / "playerinfo"
OUT_MODEL = PROJECT_DIR / "data" / "models" / "pp_systematic_offset_v1.json"
OUT_RESULT = PROJECT_DIR / "data" / "cache" / "probe_R12_F4_pp_systematic_offset_results.json"


def _name_key(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _build_player_id_to_name() -> Dict[int, str]:
    """Walk playerinfo cache -> {player_id: display_name}."""
    mapping: Dict[int, str] = {}
    if not PLAYERINFO_DIR.exists():
        return mapping
    for jf in PLAYERINFO_DIR.iterdir():
        if jf.suffix != ".json":
            continue
        try:
            with open(jf, "r", encoding="utf-8") as fh:
                blob = json.load(fh)
            pid = blob.get("player_id")
            cpi = blob.get("common_player_info") or []
            if pid is None or not cpi:
                continue
            disp = cpi[0].get("DISPLAY_FIRST_LAST") or ""
            if disp:
                mapping[int(pid)] = disp
        except Exception:
            continue
    return mapping


def main():
    print(f"[probe_R12_F4] loading PP snapshots: {PP_CSV}")
    pp = pd.read_csv(PP_CSV, on_bad_lines="skip")
    print(f"  PP rows: {len(pp)}")
    print(f"  stats: {sorted(pp['stat'].unique())}")

    # Deduplicate PP: one row per (player_name, stat) using MOST RECENT capture
    pp["captured_at"] = pd.to_datetime(pp["captured_at"], errors="coerce")
    pp_dedup = (
        pp.sort_values("captured_at")
          .drop_duplicates(subset=["player_name", "stat"], keep="last")
          .copy()
    )
    pp_dedup["name_key"] = pp_dedup["player_name"].map(_name_key)
    print(f"  PP dedup rows (player x stat): {len(pp_dedup)}")

    print(f"[probe_R12_F4] loading OOF: {OOF_PQ}")
    oof = pd.read_parquet(OOF_PQ)
    oof["game_date"] = pd.to_datetime(oof["game_date"], errors="coerce")
    print(f"  OOF rows: {len(oof)}, date range: {oof['game_date'].min()} .. {oof['game_date'].max()}")

    # Build player_id -> name map
    print("[probe_R12_F4] building player_id -> name mapping from playerinfo cache")
    id2name = _build_player_id_to_name()
    print(f"  mapped {len(id2name)} player_ids -> names")

    # Attach name_key to OOF
    oof["player_name"] = oof["player_id"].map(id2name).fillna("")
    oof["name_key"] = oof["player_name"].map(_name_key)
    oof = oof[oof["name_key"] != ""].copy()
    print(f"  OOF rows with mapped name: {len(oof)}")

    # For each player x stat, take MOST RECENT OOF prediction as proxy
    oof_sorted = oof.sort_values("game_date")
    oof_latest = (
        oof_sorted.drop_duplicates(subset=["name_key", "stat"], keep="last")[
            ["name_key", "stat", "oof_pred", "game_date"]
        ]
        .rename(columns={"oof_pred": "model_q50_proxy", "game_date": "proxy_date"})
    )
    print(f"  OOF latest (player x stat): {len(oof_latest)}")

    # Merge
    merged = pp_dedup.merge(oof_latest, on=["name_key", "stat"], how="inner")
    print(f"[probe_R12_F4] merged rows: {len(merged)}")
    if len(merged) == 0:
        print("  no overlap; aborting")
        sys.exit(1)

    # offset = pp_line - model_q50_proxy
    merged["offset"] = merged["line"].astype(float) - merged["model_q50_proxy"].astype(float)

    # Per-stat skew baseline (using OOF residuals) to sanity-check signal
    skew_baseline: Dict[str, float] = {}
    for stat, sdf in oof.groupby("stat"):
        resid = (sdf["actual"].astype(float) - sdf["oof_pred"].astype(float)).dropna()
        if len(resid) > 10:
            skew_baseline[str(stat)] = float(resid.mean())
        else:
            skew_baseline[str(stat)] = 0.0

    # Aggregate per stat
    rows = []
    profile: Dict[str, Dict] = {}
    for stat, sdf in merged.groupby("stat"):
        n = int(len(sdf))
        m = float(sdf["offset"].mean())
        sd = float(sdf["offset"].std(ddof=1)) if n > 1 else 0.0
        sterr = sd / np.sqrt(n) if n > 0 else 0.0
        if sterr > 0:
            z = m / sterr
            p = float(erfc(abs(z) / sqrt(2.0)))
        else:
            z = 0.0
            p = 1.0
        skew = skew_baseline.get(str(stat), 0.0)

        # ship gate: |mean_offset| >= 2 * sterr AND n >= 100
        ship = (abs(m) >= 2.0 * sterr) and (n >= 100)

        # Top 5 examples by abs(offset)
        top = (
            sdf.reindex(sdf["offset"].abs().sort_values(ascending=False).index)
            .head(5)[["player_name", "line", "model_q50_proxy", "offset", "proxy_date"]]
            .to_dict(orient="records")
        )
        for t in top:
            t["line"] = float(t["line"])
            t["model_q50_proxy"] = float(t["model_q50_proxy"])
            t["offset"] = float(t["offset"])
            t["proxy_date"] = str(t["proxy_date"])[:10]

        profile[str(stat)] = {
            "n_obs": n,
            "mean_offset_pp_minus_model": round(m, 4),
            "std_offset": round(sd, 4),
            "sterr_offset": round(sterr, 4),
            "z": round(z, 3),
            "p_value_vs_zero": round(p, 5),
            "skew_baseline_resid_mean": round(skew, 4),
            "systematic": bool(ship),
            "top_5_examples": top,
        }
        rows.append({
            "stat": str(stat),
            "n": n,
            "mean_offset": round(m, 4),
            "sterr": round(sterr, 4),
            "z": round(z, 3),
            "p": round(p, 5),
            "skew_base": round(skew, 4),
            "systematic": ship,
        })

    table = pd.DataFrame(rows).sort_values("stat")
    print()
    print("[probe_R12_F4] per-stat PP - model offset table:")
    print(table.to_string(index=False))

    systematic_stats = [r for r in rows if r["systematic"]]
    ship = len(systematic_stats) >= 1
    status = "SHIP" if ship else "REJECT"

    top_sig = None
    if systematic_stats:
        top_sig = max(systematic_stats, key=lambda r: abs(r["z"]))

    if top_sig:
        direction = "underprices" if top_sig["mean_offset"] < 0 else "overprices"
        headline = (
            f"PP {direction} {top_sig['stat'].upper()} by {abs(top_sig['mean_offset']):.3f} "
            f"(z={top_sig['z']}, n={top_sig['n']}, p={top_sig['p']})"
        )
    else:
        headline = "no stat met ship gate (|offset| >= 2*sterr AND n >= 100)"

    print()
    print(f"[probe_R12_F4] status: {status}")
    print(f"[probe_R12_F4] headline: {headline}")

    OUT_MODEL.parent.mkdir(parents=True, exist_ok=True)
    OUT_RESULT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_MODEL, "w", encoding="utf-8") as fh:
        json.dump(profile, fh, indent=2)
    print(f"[probe_R12_F4] wrote offset profile: {OUT_MODEL}")

    result = {
        "probe_id": "R12_F4_pp_systematic_offset",
        "status": status,
        "headline": headline,
        "per_stat": rows,
        "top_systematic": top_sig,
        "n_merged_total": int(len(merged)),
        "n_pp_dedup_total": int(len(pp_dedup)),
        "caveats": [
            "PP CSV has empty player_id; matched on NFKD-normalized name only",
            "OOF date range ends 2026-04-12; PP snapshot is 2026-05-25 (no game-level overlap)",
            "Proxy is each player's MOST RECENT OOF q50 -- not what the model would predict for the 2026-05-25 game specifically",
            "PP lines are theoretical medians; OOF q50 is also q50 -- closest comparable, but skill/usage may have drifted",
            "Stale player proxies (e.g. inactive players) included; results dominated by active high-volume players",
        ],
    }
    with open(OUT_RESULT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    print(f"[probe_R12_F4] wrote result: {OUT_RESULT}")


if __name__ == "__main__":
    main()
