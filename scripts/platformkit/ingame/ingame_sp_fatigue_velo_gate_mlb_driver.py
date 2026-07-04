"""scripts.platformkit.ingame.ingame_sp_fatigue_velo_gate_mlb_driver -- corpus loader
+ CLI report/write for the REDESIGNED SP velo-fatigue in-game gate (companion to
ingame_sp_fatigue_velo_gate_mlb.py, split out so the gate module itself stays <=300 LOC).

Loads the consolidated data/domains/mlb/sp_velo_states.parquet
(domains/mlb/sp_velo_materialize.py's output), TRAIN-fits fatigue-tercile quantile
edges ACROSS THE WHOLE CORPUS as a materialization-time banding convenience (the
per-FOLD beta fit inside the gate is always TRAIN-only regardless of which edges banded
the tercile labels -- identical convention to wave-29's driver), and runs the
walk-forward gate across the corpus's games in chronological order. Writes the verdict
JSON + prints a human report.

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy/pandas + stdlib.
CLI: python -m scripts.platformkit.ingame.ingame_sp_fatigue_velo_gate_mlb_driver
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from scripts.platformkit.ingame.ingame_sp_fatigue_velo_gate_mlb import (
    FatigueVerdict, gate, _MIN_FOLDS)
from scripts.platformkit.ingame.ingame_sp_fatigue_velo_gate_mlb_io import (
    OUT, find_corpus, fit_tercile_edges, load_states_df, to_states)


def _build_states(df) -> Tuple[Dict[str, List[dict]], List[str], Dict]:
    """Whole consolidated corpus -> leak-free states-by-game dict + chronological game
    order (expanding-window folds may span seasons, same convention as wave-29)."""
    edges = fit_tercile_edges(df)
    states = to_states(df, edges=edges)
    by_game: Dict[str, List[dict]] = {}
    for s in states:
        by_game.setdefault(s["game_id"], []).append(s)
    order = (df.drop_duplicates("game_id").sort_values("date")["game_id"]
             .astype(str).tolist())
    order = [g for g in order if g in by_game]
    cov = {
        "seasons": sorted(int(s) for s in df["season"].unique()) if "season" in df.columns else [],
        "n_states": int(len(df)), "n_games": len(by_game),
        "n_pitchers": int(df["proxy_pitcher"].nunique()),
        "corpus_id": str(df["corpus_id"].iloc[0]) if "corpus_id" in df.columns and not df.empty else None,
        "as_of": str(df["as_of"].iloc[0]) if "as_of" in df.columns and not df.empty else None,
        "velo_decline_coverage": round(float(df["velo_decline"].notna().mean()), 4) if not df.empty else 0.0,
    }
    return by_game, order, cov


def run() -> FatigueVerdict:
    """Load the consolidated sp_velo_states.parquet and run the gate. Honest
    INSUFFICIENT_DATA if it is not on disk (e.g. materialize() has not run / BLOCKED)."""
    path = find_corpus()
    if not path:
        return FatigueVerdict("INSUFFICIENT_DATA", {}, [], {}, {},
                              ["no data/domains/mlb/sp_velo_states.parquet on disk -- "
                               "run domains.mlb.sp_velo_materialize first; reported "
                               "honestly, not fabricated"])
    df = load_states_df(path)
    by_game, order, cov = _build_states(df)
    caveats = [
        f"corpus: data/domains/mlb/sp_velo_states.parquet "
        f"(seasons={cov['seasons']}, states={cov['n_states']}, games={cov['n_games']}, "
        f"real_pitchers={cov['n_pitchers']}, velo_decline_coverage={cov['velo_decline_coverage']}, "
        f"corpus_id={cov['corpus_id']}, as_of={cov['as_of']}).",
        "Leak-free: BASE (a,b) and fatigue beta[tercile] both fit on TRAIN fold only; "
        "tercile quantile edges fit across the whole corpus as a materialization-time "
        "banding choice, NOT the per-fold beta fit (identical convention to wave-29).",
        "proxy_pitcher = REAL Statcast pitcher id (a strictly tighter identity than "
        "wave-29's (game_id,side) staff-block proxy); DM clustering and the planted-null "
        "shuffle both use this real per-pitcher unit.",
        "velo_decline = trailing-last-15 minus first-15 release_speed, as-of per pitch "
        "(domains/mlb/sp_velo_materialize.py); NEGATIVE = more fatigued.",
        "No in-play odds -> verdict is CALIBRATION (held-out Brier) vs a (margin,time) "
        "BASE, never a market edge. No pregame claim: in-game conditioning ONLY.",
        "REDESIGN of H1_sp_fatigue_ingame (wave-29, NOT_TESTABLE): if the planted null "
        "replicates the real lift again here, the hypothesis class CLOSES per the "
        "pre-registration -- this is the terminal test for this proxy family.",
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
    lines = ["=" * 68,
             "MLB SP WITHIN-START VELO-DECLINE -- IN-GAME GATE (REDESIGN, wave-30)",
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
