"""probe_R28_U2_pace_drift.py — R28_U2 pace drift validation probe.

Investigates the R27_T3 headline finding that ``away_pace`` and ``home_pace``
appeared to drift +1.46σ / +1.26σ in 2025-26. The probe loads every
available season's stored ``home_pace`` values, cross-references the NBA
Stats ``leaguedashteamstats`` Advanced PACE (cached at
``data/nba/team_stats_{season}.json``), and emits a clear
real-vs-artifact verdict.

Procedure
---------
1. Resolve a data root containing the 2025-26 season + at least one
   historical season + team_stats cache.
2. Per season:
     * mean/std of stored ``home_pace``/``away_pace`` in season_games file
     * mean of NBA Stats ``PACE`` from team_stats cache (authoritative)
     * gap = stored - NBA_Stats (zero ⇒ same source; large ⇒ method mismatch)
3. Verdict logic:
     * If 2025-26 gap > 1.5 possessions AND historical gap < 0.5 ⇒
       ``computation_artifact`` (the new R25_R1 file uses a different
       possession formula than the historical files).
     * Else if 2025-26 NBA Stats PACE > historical NBA Stats PACE mean
       by > 1.5 ⇒ ``real_shift``.
     * Else ⇒ ``window_artifact``.
4. Write summary JSON to ``data/cache/probe_R28_U2_results.json``.

Safety
------
* No network. No subprocess.
* Read-only except a single results JSON.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

PROBE_RESULTS_PATH = _ROOT / "data" / "cache" / "probe_R28_U2_results.json"

_SEASONS = ("2021-22", "2022-23", "2023-24", "2024-25", "2025-26")
_CURRENT_SEASON = "2025-26"
_REFERENCE_SEASONS = ("2022-23", "2023-24", "2024-25")

# Realistic NBA league-average PACE range (per nba.com 2018-19 → 2025-26
# historical envelope). Outside this range is "unrealistic".
PLAUSIBLE_PACE_MIN = 95.0
PLAUSIBLE_PACE_MAX = 105.0


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_data_root(explicit: str = "") -> Path:
    cands: List[Path] = []
    if explicit:
        cands.append(Path(explicit))
    env = os.environ.get("NBA_AI_ROOT")
    if env:
        cands.append(Path(env) / "data")
    cands.append(_ROOT / "data")
    cands.append(Path(r"C:\Users\neelj\nba-ai-system") / "data")
    for c in cands:
        if (c / "nba" / f"season_games_{_CURRENT_SEASON}.json").exists():
            return c
    return _ROOT / "data"


def _load_season(season: str, root: Path) -> List[Dict[str, Any]]:
    p = root / "nba" / f"season_games_{season}.json"
    if not p.exists():
        return []
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    return payload["rows"] if isinstance(payload, dict) else list(payload)


def _load_team_stats(season: str, root: Path) -> Dict[str, Dict[str, Any]]:
    p = root / "nba" / f"team_stats_{season}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _pace_stats(rows: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    hp = [float(r["home_pace"]) for r in rows
          if isinstance(r.get("home_pace"), (int, float))]
    ap = [float(r["away_pace"]) for r in rows
          if isinstance(r.get("away_pace"), (int, float))]
    out: Dict[str, Optional[float]] = {
        "home_pace_n":    len(hp),
        "home_pace_mean": (mean(hp) if hp else None),
        "home_pace_std":  (pstdev(hp) if len(hp) > 1 else None),
        "home_pace_min":  (min(hp) if hp else None),
        "home_pace_max":  (max(hp) if hp else None),
        "away_pace_n":    len(ap),
        "away_pace_mean": (mean(ap) if ap else None),
        "away_pace_std":  (pstdev(ap) if len(ap) > 1 else None),
    }
    return out


def _team_stats_pace(ts: Dict[str, Dict[str, Any]]) -> Optional[float]:
    paces = [float(v["pace"]) for v in ts.values()
             if isinstance(v, dict) and isinstance(v.get("pace"), (int, float))]
    return (mean(paces) if paces else None)


def diagnose(
    per_season: Dict[str, Dict[str, Any]],
) -> Tuple[str, str]:
    """Return (verdict, explanation)."""
    cur = per_season.get(_CURRENT_SEASON, {})
    cur_stored = cur.get("stored_home_pace_mean")
    cur_truth = cur.get("nba_stats_pace_mean")
    if cur_stored is None or cur_truth is None:
        return "window_artifact", "missing values for verdict"

    # gap_now: how far is the stored file from NBA Stats truth?
    gap_now = abs(cur_stored - cur_truth)

    # historical gap: average |stored - truth| across reference seasons
    hist_gaps: List[float] = []
    for s in _REFERENCE_SEASONS:
        d = per_season.get(s, {})
        sh = d.get("stored_home_pace_mean")
        th = d.get("nba_stats_pace_mean")
        if sh is not None and th is not None:
            hist_gaps.append(abs(sh - th))
    hist_gap = (mean(hist_gaps) if hist_gaps else 0.0)

    # real shift size per NBA Stats
    hist_truth = [per_season.get(s, {}).get("nba_stats_pace_mean")
                  for s in _REFERENCE_SEASONS]
    hist_truth_vals = [v for v in hist_truth if v is not None]
    real_shift = (cur_truth - mean(hist_truth_vals)) if hist_truth_vals else 0.0

    if gap_now > 1.5 and hist_gap < 0.5:
        return ("computation_artifact",
                f"current file diverges from NBA Stats by {gap_now:.2f} "
                f"possessions while historical files diverge by {hist_gap:.2f}; "
                f"R25_R1 backfill uses a different possession formula. "
                f"Real NBA Stats shift this season is {real_shift:+.2f}.")
    if real_shift > 1.5:
        return ("real_shift",
                f"NBA Stats league-average PACE moved {real_shift:+.2f} "
                f"vs reference seasons — a real league-wide pace shift.")
    return ("window_artifact",
            f"current stored gap {gap_now:.2f}, hist gap {hist_gap:.2f}, "
            f"real shift {real_shift:+.2f} — neither method-mismatch nor "
            f"meaningful league shift; remaining z-score is window noise.")


def run(data_root: Path) -> Dict[str, Any]:
    per_season: Dict[str, Dict[str, Any]] = {}
    for s in _SEASONS:
        rows = _load_season(s, data_root)
        ts = _load_team_stats(s, data_root)
        pace = _pace_stats(rows)
        truth = _team_stats_pace(ts)
        per_season[s] = {
            "n_rows": len(rows),
            "stored_home_pace_mean": pace["home_pace_mean"],
            "stored_home_pace_std":  pace["home_pace_std"],
            "stored_home_pace_min":  pace["home_pace_min"],
            "stored_home_pace_max":  pace["home_pace_max"],
            "stored_away_pace_mean": pace["away_pace_mean"],
            "stored_away_pace_std":  pace["away_pace_std"],
            "nba_stats_pace_mean":   truth,
            "plausible":             (
                truth is not None
                and PLAUSIBLE_PACE_MIN <= truth <= PLAUSIBLE_PACE_MAX
            ),
        }
    verdict, why = diagnose(per_season)

    fix_applied = "no"
    pre_fix_pace: Optional[Dict[str, Any]] = None
    # If the current season's file already carries the R28_U2 calibration
    # marker, report that the fix is applied — and surface the pre-fix
    # pace numbers from the marker so the root-cause verdict is clear.
    cur_path = data_root / "nba" / f"season_games_{_CURRENT_SEASON}.json"
    if cur_path.exists():
        try:
            payload = json.loads(cur_path.read_text(encoding="utf-8"))
            marker = payload.get("pace_calibration_R28_U2") if isinstance(payload, dict) else None
            if isinstance(marker, dict):
                fix_applied = "yes (R28_U2 calibration marker present)"
                pre_fix_pace = {
                    "home_pace_mean_before": marker.get("home_pace_mean_before"),
                    "home_pace_mean_after":  marker.get("home_pace_mean_after"),
                    "away_pace_mean_before": marker.get("away_pace_mean_before"),
                    "away_pace_mean_after":  marker.get("away_pace_mean_after"),
                    "league_mean_ratio":     marker.get("league_mean_ratio"),
                    "n_rows_patched":        marker.get("n_rows_patched"),
                }
        except Exception:
            pass

    # If fix already applied, the root-cause verdict is the pre-fix state.
    root_cause_verdict = verdict
    if pre_fix_pace and pre_fix_pace.get("home_pace_mean_before") is not None:
        truth = per_season.get(_CURRENT_SEASON, {}).get("nba_stats_pace_mean")
        before = pre_fix_pace["home_pace_mean_before"]
        if truth is not None and abs(float(before) - float(truth)) > 1.5:
            root_cause_verdict = "computation_artifact"

    summary = {
        "probe":             "R28_U2",
        "ts":                _iso_now(),
        "data_root":         str(data_root),
        "per_season":        per_season,
        "verdict":           root_cause_verdict,
        "current_state_verdict": verdict,
        "explanation":       why,
        "pre_fix_pace":      pre_fix_pace,
        "fix_applied":       fix_applied,
        "current_season":    _CURRENT_SEASON,
        "plausible_pace_range": [PLAUSIBLE_PACE_MIN, PLAUSIBLE_PACE_MAX],
    }
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="", type=str)
    args = ap.parse_args()
    root = _resolve_data_root(args.data_root)

    summary = run(root)
    PROBE_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROBE_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
