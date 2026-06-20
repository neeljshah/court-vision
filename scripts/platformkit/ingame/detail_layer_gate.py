"""scripts.platformkit.ingame.detail_layer_gate -- the NEGATIVE-CONTROL backbone for
DETAIL-layer in-game signals. A thin merge + dispatch wrapper that adds NO new scoring
math: it INHERITS DM-clustered-by-game + the degenerate-base guard + graceful-degrade
from ingame_gate_generic.gate_cross (verified import path -- MUST-FIX #1).

THE JOB: given a BASE in-game-state corpus (rows keyed (game_id, asof_idx) carrying
state_diff, frac_elapsed, outcome) and a DETAIL parquet (rows keyed (game_id, asof_idx)
carrying ONE candidate detail column), does adding that detail column as a blended
DETAIL LAYER beat a (state_diff, frac_elapsed) BASE on held-out Brier, replicated
cross-corpus A<->B?

HOW IT INHERITS THE HONESTY MACHINERY (no new math here):
  * The merged detail column is mapped into the gate's p0 slot via a FIXED, deterministic
    [0,1] squash (clip if already a probability, else logistic of a z-score using the
    detail's OWN mean/spread). This is a pure transform, NOT a fit -- it adds no scoring
    parameter and is computed per-row, so it cannot leak the outcome.
  * gate_cross then fits the BASE slope (a,b) and the blend weight-surface w on TRAIN
    ONLY and scores BASE vs BASE+detail on the held-out OTHER corpus, with DM clustered
    by game_id and the degenerate-base guard -- exactly as for a pregame prior.
  * GRACEFUL DEGRADE (the negative control): a pure-noise / constant / leak-free-useless
    detail -> the TRAIN weight surface fits w->0 (trust BASE) -> BASE+detail == BASE ->
    REJECT. The harness can therefore FAIL a signal, not only pass one.

A detail that is IDENTICAL to base state_diff is degenerate (no new information) and the
honesty guard / graceful-degrade route it away from a false SHIP. A detail that trivially
LEAKS the outcome is NOT a valid in-game signal: it is not a real held-out predictor and
the cross-corpus design still routes it through the same gate; the merge layer additionally
refuses to special-case it, so it surfaces as a (guarded) result, never a silent SHIP of a
leaking column.

NO $ anywhere; verdict is CALIBRATION (held-out Brier), never a market edge.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + stdlib + pandas.
CLI: python -m scripts.platformkit.ingame.detail_layer_gate <base.parquet> <detail.parquet>
                                                              <base2.parquet> <detail2.parquet>
                                                              [--col NAME] [--sport S]
"""
from __future__ import annotations

import argparse
import math
from typing import Dict, List, Optional, Sequence

# MUST-FIX #1: the gate lives in ingame_gate_generic (NOT an improve/ path). gate_cross
# applies DM-clustered-by-game + the degenerate-base guard via cross_direction.
from scripts.platformkit.ingame.ingame_gate_generic import GenericVerdict, gate_cross

_BASE_REQUIRED = ("game_id", "asof_idx", "state_diff", "frac_elapsed", "outcome")


# --------------------------------------------------------------------- detail -> p0
def _squash_to_unit(values: Sequence[float]) -> List[float]:
    """Map a raw detail column into [0,1] with a FIXED, per-row deterministic transform.

    If the column already looks like a probability (all in [0,1]) it is clipped through
    unchanged. Otherwise each value is logistic(z) where z = (x - mean)/spread over the
    column. This is NOT a fitted model -- it has no free parameter chosen by any score and
    no outcome dependence -- so it adds no scoring math and cannot leak the label. Its only
    job is to put the detail on the [0,1] axis the gate's blend surface expects; the gate
    then decides (on TRAIN only) how much weight w the detail earns.
    """
    xs = [float(v) for v in values]
    if xs and all(0.0 <= x <= 1.0 for x in xs):
        return [min(1.0, max(0.0, x)) for x in xs]
    n = len(xs) or 1
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / n
    spread = math.sqrt(var) or 1.0
    out: List[float] = []
    for x in xs:
        z = (x - mean) / spread
        out.append(1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z)))))
    return out


# ------------------------------------------------------------------- leak guard
# A cross-corpus held-out gate does NOT protect against a detail column that IS the
# outcome (or a near-deterministic function of it): such a leak is present identically
# in BOTH train and held-out corpora, so it "replicates". leak-free is a PRECONDITION of
# the RAILS, so we refuse such a column at the merge boundary rather than let the gate
# mistake a future-leak for a real in-game signal. Deterministic, scoring-free checks:
#   (1) correlation : |Pearson(detail, outcome)| at the ceiling (>= _LEAK_CORR_EPS).
#   (2) separation  : detail is constant within each outcome class AND the two class
#                     constants differ -> the column perfectly encodes the label.
_LEAK_CORR_EPS = 0.999


def _detail_leaks_outcome(detail_vals: Sequence[float],
                          outcome_vals: Sequence[int]) -> bool:
    """True iff the detail column is (near-)perfectly determined by the outcome label."""
    x = [float(v) for v in detail_vals]
    y = [float(v) for v in outcome_vals]
    n = len(x)
    if n == 0:
        return False
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    syy = sum((yi - my) ** 2 for yi in y)
    if sxx == 0.0 or syy == 0.0:
        return False  # constant detail or single-class outcome -> not a leak signal
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    corr = sxy / math.sqrt(sxx * syy)
    if abs(corr) >= _LEAK_CORR_EPS:
        return True
    vals0 = {round(xi, 9) for xi, yi in zip(x, y) if yi == 0.0}
    vals1 = {round(xi, 9) for xi, yi in zip(x, y) if yi == 1.0}
    return len(vals0) == 1 and len(vals1) == 1 and vals0 != vals1


# --------------------------------------------------------------------- merge
def merge_detail_onto_base(base_df, detail_df, col: str) -> List[dict]:
    """Inner-merge a DETAIL parquet onto BASE state rows on (game_id, asof_idx).

    Returns a list of gate-ready state dicts {game_id, state_diff, frac_elapsed, p0,
    outcome} where p0 = squash(detail[col]). Raises ValueError on a malformed corpus
    (fail honest, not silent) so a missing key/column never silently 0-fills.
    """
    missing = [c for c in _BASE_REQUIRED if c not in base_df.columns]
    if missing:
        raise ValueError(f"base corpus missing required columns {missing}")
    if "game_id" not in detail_df.columns or "asof_idx" not in detail_df.columns:
        raise ValueError("detail corpus missing join keys (game_id, asof_idx)")
    if col not in detail_df.columns:
        raise ValueError(f"detail corpus missing detail column {col!r}")
    keep = detail_df[["game_id", "asof_idx", col]].copy()
    merged = base_df.merge(keep, on=["game_id", "asof_idx"], how="inner")
    if len(merged) == 0:
        raise ValueError("no rows after merge on (game_id, asof_idx) -- keys disjoint")
    raw = list(merged[col].astype(float))
    if _detail_leaks_outcome(raw, list(merged["outcome"].astype(int))):
        raise ValueError(
            f"LEAK GUARD: detail column {col!r} is (near-)perfectly determined by the "
            "outcome label -- a future-leak, not a leak-free in-game signal. leak-free "
            "is a precondition; refusing to gate it (a cross-corpus gate cannot catch a "
            "column that IS the label, since the leak is identical in both corpora).")
    p0 = _squash_to_unit(raw)
    states: List[dict] = []
    for i, r in enumerate(merged.itertuples(index=False)):
        fe = float(r.frac_elapsed)
        y = int(r.outcome)
        if not (0.0 <= fe <= 1.0):
            raise ValueError(f"frac_elapsed out of [0,1]: {fe}")
        if y not in (0, 1):
            raise ValueError(f"outcome not in {{0,1}}: {y}")
        states.append({
            "game_id": r.game_id, "state_diff": float(r.state_diff),
            "frac_elapsed": fe, "p0": p0[i], "outcome": y,
        })
    return states


def _load(path: str):
    import pandas as pd
    return pd.read_parquet(path)


# --------------------------------------------------------------------- gate
def gate_detail_layer(base_a, detail_a, base_b, detail_b, *, col: str = "detail",
                      sport: str = "", min_ticks: int = 200,
                      eps: float = 0.05) -> GenericVerdict:
    """Merge detail onto base for BOTH corpora, then hand (base+detail) vs base-only to
    the EXISTING cross-corpus gate. All scoring (BASE fit, blend surface, DM-by-game,
    degenerate guard) is inherited from gate_cross -- this function adds none.
    """
    states_a = merge_detail_onto_base(base_a, detail_a, col)
    states_b = merge_detail_onto_base(base_b, detail_b, col)
    caveats = [
        f"DETAIL column {col!r} mapped to the gate's p0 slot via a fixed per-row [0,1] "
        "squash (no fitted parameter, no outcome dependence) -- adds no scoring math.",
        "BASE = sigmoid((a+b*frac)*state_diff) fit on TRAIN only; BASE+detail blends the "
        "squashed detail via a TRAIN-fit weight surface. DM clustered by game_id.",
        "GRACEFUL DEGRADE: a noise/constant/useless detail fits w->0 (trust BASE) so "
        "BASE+detail can only MATCH BASE -> REJECT. The negative control can FAIL.",
        "No in-play odds -> CALIBRATION (held-out Brier) only, never a market edge. No $.",
    ]
    return gate_cross(states_a, states_b, min_ticks=min_ticks, eps=eps,
                      sport=sport or "detail", caveats=caveats)


# --------------------------------------------------------------------- report / CLI
def _report(v: GenericVerdict, col: str) -> str:
    c = v.coverage
    lines = ["=" * 72,
             f"IN-GAME DETAIL-LAYER GATE [{v.sport}]: detail={col!r} vs (state,time) BASE",
             "=" * 72, f"VERDICT  : {v.verdict}",
             f"coverage : A {c.get('a_games')} games / {c.get('a_states')} states ; "
             f"B {c.get('b_games')} games / {c.get('b_states')} states", "-" * 72]
    for name, d in (("A->B", v.a_to_b), ("B->A", v.b_to_a)):
        if not d:
            lines.append(f"  {name}: (none)")
            continue
        lines.append(
            f"  {name}: BASE {d.get('brier_base')} -> +detail {d.get('brier_prior')}"
            f"  (delta {d.get('brier_delta')})  DM p {d.get('dm_p')}  "
            f"detail_beats_base={d.get('prior_beats_base')}  "
            f"base_degenerate={d.get('base_degenerate')}")
    for cv in v.caveats:
        lines.append(f"  - {cv}")
    lines.append("=" * 72)
    return "\n".join(lines)


def run(base_a_path: str, detail_a_path: str, base_b_path: str, detail_b_path: str,
        *, col: str = "detail", sport: str = "") -> GenericVerdict:
    """CLI entrypoint: load four parquets, gate the detail layer, print the verdict."""
    v = gate_detail_layer(_load(base_a_path), _load(detail_a_path),
                          _load(base_b_path), _load(detail_b_path),
                          col=col, sport=sport)
    print(_report(v, col))
    return v


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Gate an in-game DETAIL layer (negative-control backbone).")
    ap.add_argument("base_a")
    ap.add_argument("detail_a")
    ap.add_argument("base_b")
    ap.add_argument("detail_b")
    ap.add_argument("--col", default="detail")
    ap.add_argument("--sport", default="")
    a = ap.parse_args(argv)
    run(a.base_a, a.detail_a, a.base_b, a.detail_b, col=a.col, sport=a.sport)


if __name__ == "__main__":
    main()
