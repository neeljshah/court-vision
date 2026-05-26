"""probe_R30_W3_cache_rebuild.py — verify the predictions_cache rebuild.

R30_W3. Compares the .bak_R30_W3 (pre-rebuild) parquet to the rebuilt
parquet for today's date. Reports:
  * old vs new mtime + age
  * row count delta
  * 3 sample player_ids — q50/q10/q90 for stat=pts side-by-side
  * mean |delta_q50| across all (player_id, stat) pairs in the join

Note on the prop-cache vs game-cache split (see refresh_predictions_cache.py
docstring): predictions_cache_<date>.parquet is the PLAYER-PROP cache. It
has no total_pts/spread/home_pts columns — those live in the m2_family
JSON cache (game-level, NOT this artifact). The probe therefore reports
q50 deltas for stat=pts (the PLAYER point prediction) as the per-player
analogue of "total_pts" called out in the W3 task spec.

Persists results to ``data/cache/probe_R30_W3_results.json``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
_TODAY = datetime.now().date().isoformat()
_NEW = os.path.join(_CACHE_DIR, f"predictions_cache_{_TODAY}.parquet")
_OLD = _NEW + ".bak_R30_W3"
_OUT = os.path.join(_CACHE_DIR, "probe_R30_W3_results.json")


def _age_min(path: str) -> float:
    if not os.path.exists(path):
        return float("nan")
    return round((datetime.now().timestamp() - os.path.getmtime(path)) / 60.0, 2)


def _sample_for_pid(df, pid: int, stat: str = "pts") -> dict:
    sub = df[(df["player_id"] == pid) & (df["stat"] == stat)]
    if sub.empty:
        return {}
    r = sub.iloc[0]
    return {
        "player_id":   int(r["player_id"]),
        "player_name": str(r.get("player_name", "")),
        "team":        str(r.get("team", "")),
        "stat":        stat,
        "q10":         float(r["q10"]),
        "q50":         float(r["q50"]),
        "q90":         float(r["q90"]),
    }


def run() -> dict:
    import pandas as pd  # noqa: PLC0415

    if not os.path.exists(_NEW):
        raise FileNotFoundError(f"rebuilt cache absent: {_NEW}")
    new = pd.read_parquet(_NEW)
    has_old = os.path.exists(_OLD)
    old = pd.read_parquet(_OLD) if has_old else None

    res: dict = {
        "probe":            "R30_W3",
        "today":            _TODAY,
        "new_path":         _NEW,
        "old_path":         _OLD if has_old else None,
        "cache_new_mtime":  os.path.getmtime(_NEW) if os.path.exists(_NEW) else None,
        "cache_old_mtime":  os.path.getmtime(_OLD) if has_old else None,
        "cache_new_age_min": _age_min(_NEW),
        "cache_old_age_min": _age_min(_OLD) if has_old else None,
        "n_predictions_new": int(len(new)),
        "n_predictions_old": int(len(old)) if has_old else None,
        "n_players_new":     int(new["player_id"].nunique()),
        "n_players_old":     int(old["player_id"].nunique()) if has_old else None,
        "schema_preserved":  list(new.columns) == list(old.columns) if has_old else None,
        "new_mtime_gt_old":  (
            (os.path.getmtime(_NEW) > os.path.getmtime(_OLD)) if has_old else None
        ),
        "computed_at":       datetime.now(timezone.utc).isoformat(),
    }

    # Pick 3 sample player_ids common to both for side-by-side comparison.
    if has_old:
        common = sorted(set(new["player_id"]) & set(old["player_id"]))
        # Spread the sample across the player range so we see diverse stats.
        n = len(common)
        picks = ([common[0], common[n // 2], common[-1]] if n >= 3
                 else common[:3])
        samples = []
        for pid in picks:
            samples.append({
                "player_id": int(pid),
                "old": _sample_for_pid(old, int(pid), "pts"),
                "new": _sample_for_pid(new, int(pid), "pts"),
                "delta_q50": (
                    _sample_for_pid(new, int(pid), "pts").get("q50", 0.0)
                    - _sample_for_pid(old, int(pid), "pts").get("q50", 0.0)
                ),
            })
        res["sample_predictions_old_vs_new"] = samples

        # Mean absolute delta_q50 across the joined (pid, stat) pairs.
        merged = new.merge(
            old[["player_id", "stat", "q50"]],
            on=["player_id", "stat"],
            suffixes=("_new", "_old"),
        )
        if not merged.empty:
            merged["delta"] = (merged["q50_new"] - merged["q50_old"]).abs()
            res["mean_abs_delta_q50"] = float(merged["delta"].mean())
            res["max_abs_delta_q50"] = float(merged["delta"].max())
            res["n_pairs_joined"] = int(len(merged))
            # Per-stat breakdown (the task wants total_pts; we surface pts).
            per_stat = {}
            for stat in sorted(merged["stat"].unique()):
                sub = merged[merged["stat"] == stat]
                per_stat[stat] = {
                    "mean_abs_delta": round(float(sub["delta"].mean()), 4),
                    "n":              int(len(sub)),
                }
            res["per_stat_delta"] = per_stat

    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(_OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, default=str)
    return res


def _print_summary(res: dict) -> None:
    print(f"[R30_W3] today={res['today']}")
    print(f"[R30_W3] n_predictions_old={res.get('n_predictions_old')} "
          f"n_predictions_new={res.get('n_predictions_new')}")
    print(f"[R30_W3] cache_old_age_min={res.get('cache_old_age_min')}  "
          f"cache_new_age_min={res.get('cache_new_age_min')}")
    print(f"[R30_W3] new_mtime > old_mtime: {res.get('new_mtime_gt_old')}")
    print(f"[R30_W3] schema_preserved:      {res.get('schema_preserved')}")
    if "mean_abs_delta_q50" in res:
        print(f"[R30_W3] mean_abs_delta_q50: {res['mean_abs_delta_q50']:.4f} "
              f"(max {res['max_abs_delta_q50']:.4f}, "
              f"n_pairs {res['n_pairs_joined']})")
    if "sample_predictions_old_vs_new" in res:
        print("[R30_W3] sample player_ids (pts q50 old -> new, delta):")
        for s in res["sample_predictions_old_vs_new"]:
            old_q = s["old"].get("q50", float("nan"))
            new_q = s["new"].get("q50", float("nan"))
            name = s["old"].get("player_name") or s["new"].get("player_name") or "?"
            print(f"  pid={s['player_id']:>7d} {name:<22s} "
                  f"{old_q:>6.2f} -> {new_q:>6.2f}  (d={s['delta_q50']:+.4f})")
    print(f"[R30_W3] wrote {_OUT}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    res = run()
    if not args.quiet:
        _print_summary(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
