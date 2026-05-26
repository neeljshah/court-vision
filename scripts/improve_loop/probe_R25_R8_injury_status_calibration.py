"""probe_R25_R8_injury_status_calibration.py — empirical re-calibration of
the non-OUT injury status factors (DOUBTFUL / QUESTIONABLE / PROBABLE).

Background
----------
R22_O8 introduced today's authoritative parquet
(``data/cache/nba_injuries_<date>.parquet``).  R23_P2 confirmed that
``factor == 0.0`` (OUT / NOT WITH TEAM) correctly kills bets in every
ranker.  But OUT is the easy case — the non-OUT statuses are still
sourced from R14_H4's *literature anchor* rather than measured data:

    DOUBTFUL      → 0.30
    QUESTIONABLE  → 0.60
    PROBABLE      → 0.90

The hypothesis: QUESTIONABLE under-dampens.  Industry experience says
QUESTIONABLE players play ~85-92% of their season-average minutes when
they suit up — well above the 0.60 we apply.  If true, we over-cut
QUESTIONABLE props and miss EV; if PROBABLE players actually play 100%
we also leave dampening pennies on the table.

What this probe does
--------------------
1. Gathers every historical ``data/cache/nba_injuries_*.parquet`` AND
   legacy ``data/cache/injury_status_*.json`` snapshot.
2. For every (player_id, report_date, status) tuple with a non-empty
   status, joins to the actual game played on / immediately after the
   report date via the per-game minute aggregates derived from
   ``data/player_quarter_stats.parquet`` (true minutes) and
   ``data/player_adv_stats.parquet`` (extended minutes + 7-stat
   per-game).  Season-average minutes are computed *prior* to the
   report date (no leakage).
3. Computes the observed minute-factor (actual / season_avg) and
   stat-factor (actual_pts / season_avg_pts) per row, then aggregates
   per status: n, mean, median, q25, q75, std.
4. Compares observed median ratios against current ``_STATUS_FACTORS``
   and proposes new factors.
5. Persists the audit to ``data/cache/probe_R25_R8_results.json`` AND,
   when the SHIP gate passes (≥30 distinct report dates, ≥50 rows for
   each non-OUT status, ≥1 status delta ≥ 0.05), edits
   ``src/prediction/injury_availability.py`` with the new table.

SHIP gate
---------
  * ``≥ 30`` distinct (report_date) days of injury data analysed.
  * ``≥ 50`` joined samples for each of DOUBTFUL / QUESTIONABLE /
    PROBABLE (so the per-status median is stable).
  * ``≥ 1`` non-OUT status proposes a factor that differs from the
    current value by ``≥ 0.05`` in absolute value.
  * OUT remains pinned at 0.0 (R23_P2 invariant — never change).

When any gate fails the probe writes the audit JSON, prints the
``BLOCKED`` reason, and exits cleanly *without* editing source.  That
is by design: this probe must NOT fabricate a calibration when the
underlying data is absent (off-season, fresh clone, or the daemon has
not yet persisted enough days).
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date as _date_cls
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, PROJECT_DIR)

_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
_RESULTS_PATH = os.path.join(_CACHE_DIR, "probe_R25_R8_results.json")
_INJURY_SRC = os.path.join(PROJECT_DIR, "src", "prediction",
                           "injury_availability.py")

# R14_H4 / R22_O8 baseline (what's currently shipped).
_CURRENT_FACTORS: Dict[str, float] = {
    "OUT":           0.0,
    "NOT WITH TEAM": 0.0,
    "DOUBTFUL":      0.3,
    "QUESTIONABLE":  0.6,
    "PROBABLE":      0.9,
    "AVAILABLE":     1.0,
}

# SHIP gate thresholds.
_MIN_DAYS         = 30
_MIN_SAMPLES_EACH = 50
_MIN_DELTA        = 0.05


# ---------------------------------------------------------------------------
# Data discovery
# ---------------------------------------------------------------------------


def _list_injury_snapshots() -> Tuple[List[str], List[str]]:
    """Return (parquet_paths, json_paths) for every historical snapshot."""
    parquets: List[str] = []
    jsons:    List[str] = []
    if not os.path.isdir(_CACHE_DIR):
        return parquets, jsons
    for fname in sorted(os.listdir(_CACHE_DIR)):
        full = os.path.join(_CACHE_DIR, fname)
        if fname.startswith("nba_injuries_") and fname.endswith(".parquet"):
            parquets.append(full)
        elif (fname.startswith("injury_status_")
              and fname.endswith(".json")):
            jsons.append(full)
    return parquets, jsons


def _load_snapshot_rows() -> "List[dict]":
    """Flatten every parquet + json into one (player_id, report_date,
    status) list of dicts."""
    import pandas as pd
    rows: List[dict] = []
    parquets, jsons = _list_injury_snapshots()

    for path in parquets:
        try:
            df = pd.read_parquet(path)
        except Exception as exc:
            print(f"[R25_R8] parquet read failed {path}: {exc}")
            continue
        if df.empty:
            continue
        rdate = df["report_date"].iloc[0] if "report_date" in df.columns \
            else os.path.basename(path)[len("nba_injuries_"):-len(".parquet")]
        for _, rec in df.iterrows():
            status = str(rec.get("status") or "").upper().strip()
            if not status:
                continue
            pid = rec.get("player_id")
            try:
                pid = int(pid) if pid is not None else None
            except (TypeError, ValueError):
                pid = None
            rows.append({
                "player_id":   pid,
                "player_name": str(rec.get("player_name", "")).strip(),
                "report_date": str(rdate),
                "status":      status,
            })

    for path in jsons:
        try:
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception as exc:
            print(f"[R25_R8] json read failed {path}: {exc}")
            continue
        rdate = payload.get("date") or os.path.basename(path)[
            len("injury_status_"):-len(".json")]
        for rec in payload.get("players", []) or []:
            status = str(rec.get("status") or "").upper().strip()
            if not status:
                continue
            pid = rec.get("player_id")
            try:
                pid = int(pid) if pid is not None else None
            except (TypeError, ValueError):
                pid = None
            rows.append({
                "player_id":   pid,
                "player_name": str(rec.get("player_name", "")).strip(),
                "report_date": str(rdate),
                "status":      status,
            })

    return rows


# ---------------------------------------------------------------------------
# Per-game stats join
# ---------------------------------------------------------------------------


def _load_pergame_stats():
    """Return a long-form DataFrame with columns:
    player_id, game_date, min, pts, reb, ast.

    Built from ``data/player_adv_stats.parquet`` (has minutes + game_date)
    joined to per-game scoring derived from
    ``data/player_quarter_stats.parquet``.  Both files are read-only
    inputs — they are not modified.
    """
    import pandas as pd
    adv_path = os.path.join(PROJECT_DIR, "data", "player_adv_stats.parquet")
    qstats_path = os.path.join(
        PROJECT_DIR, "data", "player_quarter_stats.parquet")
    if not (os.path.exists(adv_path) and os.path.exists(qstats_path)):
        return None
    try:
        adv = pd.read_parquet(adv_path, columns=[
            "player_id", "game_id", "game_date", "minutes"])
        q = pd.read_parquet(qstats_path)
    except Exception as exc:
        print(f"[R25_R8] stats parquet load failed: {exc}")
        return None
    q_per_game = (q.groupby(["game_id", "player_id"])
                   .agg(pts=("pts", "sum"),
                        reb=("reb", "sum"),
                        ast=("ast", "sum"))
                   .reset_index())
    df = adv.merge(q_per_game, on=["game_id", "player_id"], how="left")
    df = df.rename(columns={"minutes": "min"})
    df["game_date"] = df["game_date"].astype(str)
    return df


# ---------------------------------------------------------------------------
# Calibration core
# ---------------------------------------------------------------------------


def _aggregate_per_status(joined) -> Dict[str, Dict[str, float]]:
    """Given the joined DataFrame, return per-status descriptive stats."""
    import pandas as pd
    out: Dict[str, Dict[str, float]] = {}
    for status, grp in joined.groupby("status"):
        ratios = grp["minute_ratio"].dropna()
        if ratios.empty:
            out[status] = {
                "n":      0,
                "mean":   None,
                "median": None,
                "q25":    None,
                "q75":    None,
                "std":    None,
            }
            continue
        out[status] = {
            "n":      int(len(ratios)),
            "mean":   float(ratios.mean()),
            "median": float(ratios.median()),
            "q25":    float(ratios.quantile(0.25)),
            "q75":    float(ratios.quantile(0.75)),
            "std":    float(ratios.std()),
        }
    return out


def _build_calibration() -> dict:
    """End-to-end audit returning the JSON-serialisable result dict."""
    rows = _load_snapshot_rows()
    distinct_dates = sorted({r["report_date"] for r in rows})
    per_status_counts: Dict[str, int] = {}
    for r in rows:
        per_status_counts[r["status"]] = per_status_counts.get(
            r["status"], 0) + 1

    result: dict = {
        "probe":              "R25_R8_injury_status_calibration",
        "run_date":           _date_cls.today().isoformat(),
        "run_ts":             datetime.now(timezone.utc).isoformat(),
        "n_snapshots":        len(distinct_dates),
        "distinct_dates":     distinct_dates,
        "n_rows_total":       len(rows),
        "status_distribution_raw": per_status_counts,
        "per_status_old_factor":   {
            k: v for k, v in _CURRENT_FACTORS.items() if k in (
                "OUT", "NOT WITH TEAM", "DOUBTFUL", "QUESTIONABLE",
                "PROBABLE", "AVAILABLE")
        },
        "per_status_new_factor":   None,
        "per_status_observed":     {},
        "n_samples_per_status":    {},
        "calibration_method":      "median(observed_minute_ratio) "
                                   "with floor[OUT]=0.0 (R23_P2 invariant)",
        "ship_status":             "BLOCKED",
        "ship_reason":             "",
    }

    # Hard gate: insufficient distinct days.
    if len(distinct_dates) < _MIN_DAYS:
        result["ship_reason"] = (
            f"only {len(distinct_dates)} distinct injury-report dates "
            f"in local cache; SHIP needs ≥ {_MIN_DAYS}. Off-season /"
            " daemon hasn't persisted history yet.")
        return result

    pergame = _load_pergame_stats()
    if pergame is None:
        result["ship_reason"] = (
            "stats parquets missing — cannot join report→played-minutes.")
        return result

    import pandas as pd
    # Build join: for each (player_id, report_date, status), find the
    # next played game on/after report_date and compute season-prior
    # average minutes.
    inj_df = pd.DataFrame([r for r in rows if r["player_id"] is not None])
    if inj_df.empty:
        result["ship_reason"] = "no player_id-tagged injury rows to join."
        return result

    pergame = pergame.sort_values(["player_id", "game_date"])
    joined_rows: List[dict] = []
    for pid, sub in pergame.groupby("player_id"):
        inj_for_pid = inj_df[inj_df["player_id"] == pid]
        if inj_for_pid.empty:
            continue
        for _, ir in inj_for_pid.iterrows():
            rd = ir["report_date"]
            future = sub[sub["game_date"] >= rd]
            if future.empty:
                continue
            game = future.iloc[0]
            prior = sub[sub["game_date"] < rd]
            if prior.empty:
                continue
            season_avg = prior["min"].mean()
            if season_avg <= 0:
                continue
            joined_rows.append({
                "player_id":     pid,
                "report_date":   rd,
                "status":        ir["status"],
                "actual_min":    float(game["min"]),
                "season_avg":    float(season_avg),
                "minute_ratio":  float(game["min"]) / float(season_avg),
            })

    if not joined_rows:
        result["ship_reason"] = (
            "0 rows joined report→played-game (status timestamps don't "
            "overlap the stats parquet date range).")
        return result

    joined = pd.DataFrame(joined_rows)
    per_status = _aggregate_per_status(joined)
    result["per_status_observed"]  = per_status
    result["n_samples_per_status"] = {k: v["n"] for k, v in per_status.items()}

    # Per-status sample-count gate.
    must_have = ("DOUBTFUL", "QUESTIONABLE", "PROBABLE")
    short = [s for s in must_have if per_status.get(s, {}).get("n", 0)
             < _MIN_SAMPLES_EACH]
    if short:
        result["ship_reason"] = (
            f"insufficient samples for {short} (need ≥ {_MIN_SAMPLES_EACH}"
            " each)")
        return result

    # Propose new factors.  Use observed median ratio, clipped to
    # [0.0, 1.0].  OUT / NOT WITH TEAM stay pinned at 0.0 (invariant).
    proposed = dict(_CURRENT_FACTORS)
    for status in must_have:
        med = per_status[status]["median"]
        if med is None:
            continue
        proposed[status] = round(max(0.0, min(1.0, float(med))), 3)

    result["per_status_new_factor"] = proposed

    deltas = {
        s: round(abs(proposed[s] - _CURRENT_FACTORS[s]), 3)
        for s in must_have
    }
    result["deltas"] = deltas
    if max(deltas.values(), default=0.0) < _MIN_DELTA:
        result["ship_status"] = "REJECT"
        result["ship_reason"] = (
            f"max delta {max(deltas.values()):.3f} < {_MIN_DELTA}: "
            "calibration matches current factors closely; no edit needed.")
        return result

    result["ship_status"] = "SHIP"
    result["ship_reason"] = (
        f"deltas {deltas} clear {_MIN_DELTA} threshold; edit source.")
    return result


# ---------------------------------------------------------------------------
# Source-table patcher
# ---------------------------------------------------------------------------


def _patch_factor_table(new_factors: Dict[str, float]) -> bool:
    """Re-write the AVAILABILITY_FACTOR table inside injury_availability.py.

    Preserves OUT/NOT WITH TEAM/AVAILABLE rows exactly (invariants).
    Returns True when a write happened.
    """
    with open(_INJURY_SRC, encoding="utf-8") as fh:
        src = fh.read()
    pattern = re.compile(
        r'(AVAILABILITY_FACTOR: Dict\[str, float\] = \{\n)(.*?)(\n\})',
        re.DOTALL,
    )
    m = pattern.search(src)
    if not m:
        print("[R25_R8] could not locate AVAILABILITY_FACTOR block")
        return False
    today = _date_cls.today().isoformat()
    new_body = (
        f'    # R25_R8 ({today}): factors re-calibrated from historical'
        f' injury-report → minutes data.\n'
        f'    # OUT / NOT WITH TEAM stay at 0.0 (R23_P2 invariant — '
        f'never relax).\n'
        f'    "OUT":           0.0,\n'
        f'    "NOT WITH TEAM": 0.0,\n'
        f'    "DOUBTFUL":      {new_factors["DOUBTFUL"]},\n'
        f'    "QUESTIONABLE":  {new_factors["QUESTIONABLE"]},\n'
        f'    "PROBABLE":      {new_factors["PROBABLE"]},\n'
        f'    "AVAILABLE":     1.0,'
    )
    patched = pattern.sub(m.group(1) + new_body + m.group(3), src)
    if patched == src:
        return False
    with open(_INJURY_SRC, "w", encoding="utf-8") as fh:
        fh.write(patched)
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    result = _build_calibration()

    if result["ship_status"] == "SHIP" and result.get(
            "per_status_new_factor"):
        wrote = _patch_factor_table(result["per_status_new_factor"])
        result["source_patched"] = bool(wrote)
    else:
        result["source_patched"] = False

    with open(_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)

    print(json.dumps({
        "ship_status":           result["ship_status"],
        "ship_reason":           result["ship_reason"],
        "n_days":                result["n_snapshots"],
        "n_samples_per_status":  result["n_samples_per_status"],
        "per_status_old_factor": result["per_status_old_factor"],
        "per_status_new_factor": result["per_status_new_factor"],
        "source_patched":        result["source_patched"],
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
