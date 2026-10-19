"""scripts.platformkit.eval_gate.mlb_frozen_vs_walkforward_elo -- S448, REPORT ONLY.

Measures whether a walk-forward-updated MLB Elo beats the Elo the served predictor
actually runs on (ingest_manifest.py:43 sla_minutes=1440; frozen 2026-07-12, past SLA).

FROZEN Elo: the single constant final_ratings(games through FROZEN_ASOF), reused
unchanged for every scored game (what is actually served today). WALK-FORWARD Elo:
for a game on date D, final_ratings(games strictly before D) -- rebuilt fresh per
date. Frozen replays the SAME served corpus -- the SAME two source parquets
load_combined_corpus() uses (1(c)), read via _ingress.read_games_parquet() (10(a)).
Both replay the SAME leak-free rule from beat_the_close_ml (no K/HFA refit).

io.clean_games_asof() refuses every non-final, tied, negative, non-numeric,
mis-dated, mis-keyed or duplicate row BEFORE either replay, scoped to EACH
snapshot's as-of slice (5(a)). _kalshi.select_kalshi_mid() returns a side-unaware
kalshi_yes_mid always, and kalshi_mid_home ONLY when a capture's own side field
validates -- never guessed (6(a)); neither feeds a Brier, bootstrap or verdict.

REPORT ONLY: no operational fix ships here; STEP 2 is a separate PROPOSED runbook.
Calibration language only (ACCEPT/REJECT/NULL/UNDERPOWERED).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from scripts.platformkit.eval_gate.mlb_frozen_vs_walkforward_elo_ingress import read_games_parquet
from scripts.platformkit.eval_gate.mlb_frozen_vs_walkforward_elo_io import (
    _brier, _p_home_of, _to_records, clean_games, clean_games_asof, clean_games_window,
    default_window_end, default_window_end_records, file_identity, ratings_digest, snapshot_entries,
)
from scripts.platformkit.eval_gate.mlb_frozen_vs_walkforward_elo_kalshi import (
    load_kalshi_captures, select_kalshi_mid,
)
from scripts.platformkit.eval_gate.mlb_frozen_vs_walkforward_elo_validate import (
    validate_window, verdict_of,
)
from scripts.platformkit.proof_mlb.beat_the_close_ml import _HFA, _INIT, _K, final_ratings

FROZEN_ASOF = "2026-07-12"   # games_current.parquet's own max date (S448 before-condition)
WINDOW_START = "2026-07-13"  # the day after FROZEN_ASOF
N_BOOT = 2000
SEED = 13
MIN_DATES = 5                # bootstrap floor; below this the verdict is UNDERPOWERED


def frozen_ratings(games, asof: str = FROZEN_ASOF) -> Dict[str, float]:
    """final_ratings() on the as-of slice (date <= asof) of RAW *games* -- row-level
    checks (incl. duplicates) scoped to that slice only (AMENDMENT 5(a)); ONE snapshot."""
    clean, _ = clean_games_asof(games, asof, inclusive=True)
    return final_ratings(clean)


def _walkforward_ratings_before(games, date_d) -> Dict[str, float]:
    """final_ratings() on the as-of slice of RAW *games* strictly before *date_d* --
    a record dated on/after *date_d* can never alter a prior training game (5(a))."""
    clean, _ = clean_games_asof(games, date_d, inclusive=False)
    return final_ratings(clean)


def score_window(
    games,
    window_start: str = WINDOW_START,
    window_end: Optional[str] = None,
    frozen_asof: str = FROZEN_ASOF,
    kalshi_yes_mid: Optional[Dict[str, float]] = None,
    kalshi_mid_home: Optional[Dict[str, float]] = None,
) -> Tuple[List[dict], List[dict]]:
    """Score every FINAL game in [window_start, window_end] (inclusive). Returns
    (scored_rows, refused_rows): refused_rows is every window row
    clean_games_window() refused, never imputed. *kalshi_yes_mid*/*kalshi_mid_home*
    are report-only, never read for a Brier/bootstrap/verdict (caller validates
    any side binding, 6(a)). 9(c): records are date-sliced to the window BEFORE
    duplicate validation, so a later duplicate outside it can't remove a scored game."""
    import pandas as pd  # noqa: PLC0415

    kalshi_yes_mid = kalshi_yes_mid or {}
    kalshi_mid_home = kalshi_mid_home or {}
    records = _to_records(games)
    start = validate_window(window_start, frozen_asof)
    end = pd.Timestamp(window_end) if window_end else default_window_end_records(records)
    win_clean, refused = clean_games_window(records, start, end)
    win = win_clean.sort_values(["date", "game_seq", "event_id"]).reset_index(drop=True)

    frozen = frozen_ratings(games, frozen_asof)   # ONE call, RAW games (AMENDMENT 5(a))
    scored: List[dict] = []
    wf_cache: Dict[object, Dict[str, float]] = {}
    for _, row in win.iterrows():
        d = row["date"]
        if d not in wf_cache:
            wf_cache[d] = _walkforward_ratings_before(games, d)   # RAW games, as-of scoped
        wf = wf_cache[d]
        home, away = str(row["home_team"]), str(row["away_team"])
        y = 1.0 if float(row["home_runs"]) > float(row["away_runs"]) else 0.0
        p_frozen = _p_home_of(frozen, home, away)
        p_fresh = _p_home_of(wf, home, away)
        b_frozen = _brier(p_frozen, y)
        b_fresh = _brier(p_fresh, y)
        scored.append({
            "event_id": row["event_id"],
            "date": str(row["date"].date()),
            "snapshot_cutoff": str(row["date"].date()),   # AMENDMENT 2(d): names its own snapshot
            "home_team": home, "away_team": away,
            "p_frozen": p_frozen, "p_fresh": p_fresh,
            "brier_frozen": b_frozen, "brier_fresh": b_fresh,
            "diff": b_fresh - b_frozen,   # fresh minus frozen; negative = fresh ahead
            "kalshi_yes_mid": kalshi_yes_mid.get(row["event_id"]),      # descriptive only
            "kalshi_mid_home": kalshi_mid_home.get(row["event_id"]),   # descriptive only
        })
    return scored, refused


def cluster_bootstrap_by_date(
    rows: List[dict], n_boot: int = N_BOOT, seed: int = SEED,
) -> Tuple[float, Optional[float], Optional[float], int]:
    """Paired per-game Brier difference (fresh - frozen), bootstrapped over DATES.

    One rating state per date: resampling draws whole dates with replacement, so a
    doubleheader's two games always move together under the same date-cluster.
    Fails closed (raises ValueError) on any non-finite paired difference instead of
    silently reporting a bogus point estimate or confidence interval.
    """
    dates = sorted({r["date"] for r in rows})
    n_dates = len(dates)
    sums = {d: 0.0 for d in dates}
    counts = {d: 0 for d in dates}
    for r in rows:
        diff = r["diff"]
        if not np.isfinite(diff):
            raise ValueError(f"non-finite diff on date {r['date']!r} -- refusing to bootstrap")
        sums[r["date"]] += diff
        counts[r["date"]] += 1
    sum_arr = np.array([sums[d] for d in dates])
    n_arr = np.array([counts[d] for d in dates])
    point = float(sum_arr.sum() / n_arr.sum()) if len(dates) else 0.0
    if len(dates) and not np.isfinite(point):
        raise ValueError("non-finite point estimate -- refusing to bootstrap")
    if n_dates < MIN_DATES:
        return point, None, None, n_dates
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, n_dates, n_dates)
        boots[i] = sum_arr[pick].sum() / n_arr[pick].sum()
    if not np.all(np.isfinite(boots)):   # AMENDMENT 2(a): every resampled mean checked
        raise ValueError("non-finite bootstrap draw -- refusing to bootstrap")
    lo, hi = (float(x) for x in np.percentile(boots, [2.5, 97.5]))
    if not (np.isfinite(lo) and np.isfinite(hi)):   # both percentile bounds checked
        raise ValueError("non-finite bootstrap bound -- refusing to bootstrap")
    return point, lo, hi, n_dates


def build_report(
    games,
    window_start: str = WINDOW_START,
    window_end: Optional[str] = None,
    frozen_asof: str = FROZEN_ASOF,
    kalshi_yes_mid: Optional[Dict[str, float]] = None,
    kalshi_mid_home: Optional[Dict[str, float]] = None,
    kalshi_counters: Optional[Dict[str, int]] = None,
    source_path: Optional[str] = None,
    input_identities: Optional[List[dict]] = None,
) -> dict:
    import pandas as pd  # noqa: PLC0415

    scored, refused = score_window(games, window_start, window_end, frozen_asof,
                                    kalshi_yes_mid, kalshi_mid_home)
    point, lo, hi, n_dates = cluster_bootstrap_by_date(scored)

    clean, refused_all = clean_games(games)   # full-corpus view: window_end default only
    # training facts below use RAW games via clean_games_asof(), never `clean` (5(a))
    frozen = frozen_ratings(games, frozen_asof)
    frozen_clean, _ = clean_games_asof(games, frozen_asof, inclusive=True)
    frozen_training_max_date = (str(frozen_clean["date"].max().date())
                                 if len(frozen_clean) else None)

    wf_digest = wf_training_max_date = None
    if scored:
        last_date = pd.Timestamp(max(r["date"] for r in scored))
        wf_last = _walkforward_ratings_before(games, last_date)
        wf_train, _ = clean_games_asof(games, last_date, inclusive=False)
        wf_training_max_date = str(wf_train["date"].max().date()) if len(wf_train) else None
        wf_digest = ratings_digest(wf_last)

    snapshots = [{"kind": "frozen", "cutoff": frozen_asof,   # one entry per date + frozen (2(d))
                  "training_max_date": frozen_training_max_date,
                  "ratings_digest": ratings_digest(frozen),
                  "games_trained": int(len(frozen_clean))}]
    if scored:
        by_date = {d: _walkforward_ratings_before(games, pd.Timestamp(d))
                   for d in sorted({r["date"] for r in scored})}
        snapshots += snapshot_entries(games, by_date)

    window_end_out = window_end
    if window_end_out is None:
        default_end = default_window_end(clean, refused_all)   # AMENDMENT 3(b): incl. refused dates
        window_end_out = str(default_end.date()) if pd.notna(default_end) else None

    return {
        "spec": "S448",
        "frozen_asof": frozen_asof,
        "frozen_training_max_date": frozen_training_max_date,
        "frozen_ratings_digest": ratings_digest(frozen),
        "walk_forward_asof": "rebuilt through the day strictly before each scored game",
        "walk_forward_last_training_max_date": wf_training_max_date,
        "walk_forward_last_ratings_digest": wf_digest,
        "window_start": window_start,
        "window_end": window_end_out,
        "update_rule": {"K": _K, "HFA": _HFA, "INIT": _INIT,
                         "source": "scripts.platformkit.proof_mlb.beat_the_close_ml (imported, unedited)"},
        "n_scored": int(len(scored)),
        "n_refused": int(len(refused)),
        "refused": refused,
        "n_dates": int(n_dates),
        "n_boot": int(N_BOOT) if n_dates >= MIN_DATES else 0,
        "seed": int(SEED),
        "point_diff_fresh_minus_frozen": point,
        "ci95_lo": lo,
        "ci95_hi": hi,
        "verdict": verdict_of(lo, hi, n_dates, MIN_DATES),
        "snapshots": snapshots,
        "per_game": scored,
        "source_path": source_path,
        "input_identities": input_identities or [],
        "kalshi_refused": dict(kalshi_counters) if kalshi_counters else {},   # AMENDMENT 6(b)
    }


def _main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="S448: frozen vs walk-forward MLB Elo (report only).")
    ap.add_argument("--games-parquet", default=None,
                     help="override: one parquet (CONSTRUCT/testing); default is "
                          "read_games_parquet(_FROZEN, _CURRENT), the two-path record reader")
    ap.add_argument("--frozen-asof", default=FROZEN_ASOF)
    ap.add_argument("--window-start", default=WINDOW_START)
    ap.add_argument("--window-end", default=None)
    ap.add_argument("--kalshi-json", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    identities: List[dict] = []
    source_path: str
    if args.games_parquet:
        path = Path(args.games_parquet)
        if not path.exists():
            print(json.dumps({"status": "NO_DATA", "reason": f"{path} not found"},
                              sort_keys=True, allow_nan=False))
            return 0
        games = read_games_parquet(path)   # 9(a): records via pyarrow, never a DataFrame
        identities.append(file_identity(path, "games_source_override"))
        source_path = str(path.resolve())
    else:
        from domains.mlb import refresh_ratings  # noqa: PLC0415

        if not refresh_ratings._FROZEN.exists() or not refresh_ratings._CURRENT.exists():
            print(json.dumps({"status": "NO_DATA",
                               "reason": "refresh_ratings combined corpus not present locally"},
                              sort_keys=True, allow_nan=False))
            return 0
        # 10(a): the SAME two source paths the served loader uses, read via
        # read_games_parquet() -- never load_combined_corpus() (pandas-first).
        games = read_games_parquet(refresh_ratings._FROZEN, refresh_ratings._CURRENT)
        identities.append(file_identity(refresh_ratings._FROZEN, "frozen_corpus_2010_2021"))
        identities.append(file_identity(refresh_ratings._CURRENT, "current_corpus_2022_plus"))
        source_path = "read_games_parquet(refresh_ratings._FROZEN, refresh_ratings._CURRENT)"

    kalshi_yes_mid = kalshi_mid_home = kalshi_counters = None
    if args.kalshi_json:
        kpath = Path(args.kalshi_json)
        # AMENDMENT 5(b): a bare event-to-value mapping is refused, never passed through.
        captures, first_pitch = load_kalshi_captures(json.loads(kpath.read_text(encoding="utf-8")))
        kalshi_yes_mid, kalshi_mid_home, kalshi_counters = select_kalshi_mid(captures, first_pitch)
        identities.append(file_identity(kpath, "kalshi_mid_json"))

    report = build_report(games, args.window_start, args.window_end, args.frozen_asof,
                           kalshi_yes_mid=kalshi_yes_mid, kalshi_mid_home=kalshi_mid_home,
                           kalshi_counters=kalshi_counters,
                           source_path=source_path, input_identities=identities)
    text = json.dumps(report, sort_keys=True, ensure_ascii=True, indent=2, allow_nan=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    print(f"VERDICT: {report['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
