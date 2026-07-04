"""scripts.platformkit.ingame.sp_fatigue_gate_mlb_driver -- corpus loader + CLI
report/write for the SP fatigue in-game gate (companion to sp_fatigue_gate_mlb.py,
split out so the gate module itself stays <=300 LOC).

Loads ALL on-disk data/cache/ingame/mlb_pitch_states__<season>.parquet corpora,
TRAIN-fits fatigue-tercile quantile edges PER SEASON (a materialization-time banding
convenience; the per-FOLD beta fit inside the gate is always TRAIN-only regardless of
which edges banded the tercile labels), and runs the walk-forward gate across seasons
in chronological order. Writes the verdict JSON + prints a human report.

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy/pandas + stdlib.
CLI: python -m scripts.platformkit.ingame.sp_fatigue_gate_mlb_driver
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from scripts.platformkit.ingame.sp_fatigue_gate_mlb import FatigueVerdict, gate, _MIN_FOLDS
from scripts.platformkit.ingame.sp_fatigue_gate_mlb_io import (
    OUT, find_season_corpora, fit_tercile_edges, load_pitch_states, to_states)


def _build_states(paths: List[str]) -> Tuple[Dict[str, List[dict]], List[str], Dict]:
    """Load ALL on-disk season corpora -> one leak-free states-by-game dict + the
    chronological game order spanning all seasons (season boundary is not special-
    cased: expanding-window folds may span seasons, exactly like the NBA gate spans
    a season's games)."""
    by_game: Dict[str, List[dict]] = {}
    order: List[str] = []
    cov = {"seasons": [], "n_states": {}, "n_games": {}}
    for p in paths:
        df = load_pitch_states(p)
        season = int(df["season"].iloc[0]) if not df.empty else -1
        edges = fit_tercile_edges(df)
        states = to_states(df, edges=edges)
        season_by_game: Dict[str, List[dict]] = {}
        for s in states:
            season_by_game.setdefault(s["game_id"], []).append(s)
        season_order = (df.drop_duplicates("game_id").sort_values("date")["game_id"]
                        .astype(str).tolist())
        for gid in season_order:
            if gid in season_by_game:
                by_game[gid] = season_by_game[gid]
                order.append(gid)
        cov["seasons"].append(season)
        cov["n_states"][season] = len(states)
        cov["n_games"][season] = len(season_by_game)
    return by_game, order, cov


def run() -> FatigueVerdict:
    """Load ALL materialized mlb_pitch_states__<season>.parquet corpora on disk and
    run the gate. Honest INSUFFICIENT_DATA if none are on disk."""
    paths = find_season_corpora()
    if not paths:
        return FatigueVerdict("INSUFFICIENT_DATA", {}, [], {}, {},
                              ["no mlb_pitch_states__*.parquet on disk at "
                               "data/cache/ingame/ -- reported honestly, not fabricated"])
    by_game, order, cov = _build_states(paths)
    caveats = [
        f"corpus: {len(paths)} season(s) of data/cache/ingame/mlb_pitch_states__*.parquet "
        f"(seasons={cov['seasons']}, states={cov['n_states']}, games={cov['n_games']}).",
        "Leak-free: BASE (a,b) and fatigue beta[tercile] both fit on TRAIN fold only; "
        "tercile quantile edges fit per-season on that season's full distribution "
        "(a materialization-time banding choice, NOT the per-fold beta fit).",
        "proxy_pitcher = (game_id, pitch_side): this corpus has NO individual pitcher "
        "id (documented in domains/mlb/ingest_sp_fatigue_prop_states.py); DM clustering "
        "and the planted-null shuffle both use this proxy unit.",
        "No in-play odds -> verdict is CALIBRATION (held-out Brier) vs a (margin,time) "
        "BASE, never a market edge. No pregame claim: in-game conditioning ONLY.",
    ]
    return gate(by_game, order, n_folds=_MIN_FOLDS, caveats=caveats)


def write(verdict: FatigueVerdict, out: str = OUT) -> str:
    os.makedirs(os.path.dirname(out), exist_ok=True)
    d = verdict.to_dict()
    d["pre_registered_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(out, "w", encoding="ascii") as f:
        json.dump(d, f, indent=2, sort_keys=True)
    return out


def _report(v: FatigueVerdict) -> str:
    m = v.metrics
    lines = ["=" * 68, "MLB SP WITHIN-START FATIGUE -- IN-GAME GATE (H1_sp_fatigue_ingame)",
             "=" * 68, f"verdict           : {v.verdict}"]
    if m:
        lines += [
            f"pooled OOS Brier  : BASE {m.get('brier_base')}  +FATIGUE {m.get('brier_fatigue')}"
            f"  (delta {m.get('brier_delta')})",
            f"DM (clustered)    : stat {m.get('dm_stat')}  p {m.get('dm_p')}"
            f"  clusters {m.get('n_clusters')}",
            f"fold consistency  : {m.get('folds_fatigue_better')}/{m.get('n_folds')} "
            f"folds fatigue<base  consistent={m.get('fold_sign_consistent')}",
        ]
    if v.planted_null:
        lines.append(f"planted-null      : rejected={v.planted_null.get('null_rejected')}")
    lines.append("-" * 68)
    for f in v.per_fold:
        lines.append(f"  fold {f['fold']}  n={f['n']:5d}  "
                     f"{f['brier_base']:.4f} -> {f['brier_fatigue']:.4f}  "
                     f"delta {f['delta']:+.5f}  fatigue_better={f['fatigue_beats_base']}")
    lines.append("-" * 68)
    for t, d in v.per_tercile.items():
        lines.append(f"  {t:10s} n={d['n']:6d}  base {d['brier_base']:.4f} -> "
                     f"fatigue {d['brier_fatigue']:.4f}  delta {d['delta']:+.5f}")
    lines.append("=" * 68)
    return "\n".join(lines)


def main() -> None:
    v = run()
    p = write(v)
    print(_report(v))
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
