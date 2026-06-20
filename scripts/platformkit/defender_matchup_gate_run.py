"""scripts.platformkit.defender_matchup_gate_run -- run the leak-free as-of
DEFENDER-MATCHUP layer (domains/basketball_nba/ingest_defender_matchup_states.py)
through the PROVEN cross-corpus gate machinery and produce an HONEST verdict.

GATE REUSED (no new scoring math): scripts.platformkit.ingame.detail_layer_gate
.gate_detail_layer -> ingame_gate_generic.gate_cross -> cross_direction, which
INHERITS DM-clustered-by-game + the degenerate-base guard + graceful-degrade. We
add NOTHING to the scoring; we only ADAPT the per-defender-game layer onto the
gate's FROZEN schema (game_id, asof_idx, state_diff, frac_elapsed, p0, outcome).

WHAT THE LAYER IS (and is NOT): the defender layer is a PER-DEFENDER-GAME, as-of
feature predicting a CONTINUOUS realized matchup outcome (FG% allowed). It has NO
score/clock in-game micro-state. The proven gate is an IN-GAME conditioning gate
whose BASE is sigmoid((a+b*frac_elapsed)*state_diff). A per-game defender row has
no state_diff / frac_elapsed, so we set them to a constant -- which makes the gate's
BASE the constant TRAIN base-rate and DELIBERATELY trips the degenerate-base guard.
That is the HONEST outcome: the in-game conditioning gate is NOT_TESTABLE on a
layer with no in-game state, and the gate says so itself (base_degenerate=True).

So we ALSO run the FAITHFUL test the gate's own primitives support for a prior-vs-
base-rate layer: using the SAME diebold_mariano (DM clustered by game_id), does the
defender's as-of feature (as p0) beat the constant base-rate on held-out Brier of a
BINARY realized-matchup label, REPLICATED in BOTH cross-corpus directions (2024-25 vs
2025-26)? A PLANTED-NULL pure-noise column is pushed through the IDENTICAL path and
MUST REJECT -- proving the gate can FAIL a signal.

LEAK-FREE: p0 = the layer's *_asof column (shift1 prior-N, snapshot-before-update --
never reads the current game). The BINARY label is built from THIS-game realized
diagnostics ONLY (the label surface), never used as a feature. The close/market is
never present. Train/inference parity: one column, one transform, both corpora.

NO $ / ROI / edge field anywhere -- CALIBRATION (held-out Brier) only. PROPOSAL-only:
writes a JSON verdict under data/frontend/ NOT data/registry/; flips no flag.
INVARIANTS: never edit src/ kernel/ api/; numpy+pandas+stdlib; <=300 LOC; ASCII.
CLI: python -m scripts.platformkit.defender_matchup_gate_run [--col NAME] [--min-prior 5]
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.ingame.detail_layer_gate import gate_detail_layer

_REPO = Path(__file__).resolve().parents[2]
_LAYER = _REPO / "data" / "domains" / "basketball_nba" / "defender_matchup_states.parquet"
_OUT = _REPO / "data" / "frontend" / "defender_matchup_gate.json"

# The as-of feature under test (lower allowed-FG% = a better defender) and its
# realized counterpart (the binary label surface).
_DEFAULT_COL = "def_priorN_fg_pct_allowed_asof"
_REALIZED = "realized_fg_pct_allowed"
_MIN_PRIOR = 5            # support floor: a defender needs >= this many prior games
_EPS = 0.05               # DM significance bar (both directions must clear it)


def _season(dates) -> np.ndarray:
    """NBA season label: year if month>=8 else year-1 (so two clean season corpora)."""
    import pandas as pd
    d = pd.to_datetime(dates)
    return np.where(d.dt.month >= 8, d.dt.year, d.dt.year - 1)


def load_layer(path: Optional[Path] = None):
    """Load the PROPOSAL parquet emitted by the ingest layer (zero new computation)."""
    import pandas as pd
    p = Path(path) if path is not None else _LAYER
    if not p.exists():
        raise FileNotFoundError(f"defender-matchup layer parquet not on disk: {p}")
    return pd.read_parquet(p)


def _adapt_corpus(df, col: str, *, planted_null: bool, seed: int = 0):
    """ADAPT per-defender-game rows onto the gate's FROZEN in-game schema.

    Frozen schema rows: {game_id, asof_idx, state_diff, frac_elapsed, p0, outcome}.
    - outcome  = 1 iff the defender allowed BELOW the corpus-median realized FG% this
                 game (a "good matchup" / stop) -- a binary realized label. Built from
                 THIS-game realized diagnostics only; never a feature.
    - p0       = the leak-free as-of feature mapped to [0,1] as P(stop): lower allowed
                 FG% expected => higher stop prob, so p0 = 1 - asof (asof already ~[0,1]).
                 For the PLANTED NULL, p0 is replaced by a pure-noise U(0,1) column.
    - state_diff/frac_elapsed = 0.0 (a per-game row HAS no in-game micro-state). This
      makes the gate's BASE the constant base-rate and trips its degenerate guard --
      honest: the in-game gate is not applicable to a no-state layer.
    Leak-free: rows with def_n_prior < _MIN_PRIOR (as-of feature NaN/unsupported) are
    dropped; never 0-filled into a win.
    """
    import pandas as pd
    m = (df["def_n_prior"] >= _MIN_PRIOR) & df[col].notna() & df[_REALIZED].notna()
    sub = df.loc[m].copy()
    med = float(sub[_REALIZED].median())
    outcome = (sub[_REALIZED] < med).astype(int).to_numpy()  # stop = below-median FG%
    if planted_null:
        rng = np.random.default_rng(seed)
        p0 = rng.uniform(0.0, 1.0, size=len(sub))            # pure noise -- MUST reject
    else:
        asof = np.clip(sub[col].to_numpy(dtype=float), 0.0, 1.0)
        p0 = 1.0 - asof                                      # lower allowed FG% => stop
    base = pd.DataFrame({
        "game_id": sub["game_id"].astype(str).to_numpy(),
        "asof_idx": np.arange(len(sub)),
        "state_diff": np.zeros(len(sub)),
        "frac_elapsed": np.zeros(len(sub)),
        "outcome": outcome,
    })
    detail = pd.DataFrame({
        "game_id": sub["game_id"].astype(str).to_numpy(),
        "asof_idx": base["asof_idx"].to_numpy(),
        "detail": np.clip(p0, 0.0, 1.0),
    })
    return base, detail


# --------------------------------------------------------------------------- faithful
def _prior_vs_baserate(p0_a, y_a, gid_a, p0_b, y_b, gid_b, *, eps=_EPS) -> Dict:
    """FAITHFUL prior-vs-base-rate test using the gate's OWN DM (clustered by game_id).

    Fit the constant base-rate on TRAIN (corpus A), score BASE (=that constant) vs
    +PRIOR (=p0) on held-out TEST (corpus B) by Brier; DM clustered by game_id. Both
    directions. prior beats base iff Brier(+PRIOR) < Brier(BASE) AND DM p<eps. This is
    exactly the cross_direction logic for the no-in-game-state case (BASE is the base
    rate by construction), reusing the IDENTICAL diebold_mariano.
    """
    def one(p0_tr, y_tr, p0_te, y_te, gid_te) -> Dict:
        const = float(np.mean(y_tr))                       # base-rate fit on TRAIN only
        base = np.full(len(y_te), const)
        bb, bp = float(brier(base, y_te)), float(brier(p0_te, y_te))
        d = (base - y_te) ** 2 - (p0_te - y_te) ** 2       # +ve => prior beats base
        dm = diebold_mariano(d, gid_te)
        beats = bool(bp < bb and dm.p_value < eps)
        return {"brier_base": round(bb, 5), "brier_prior": round(bp, 5),
                "brier_delta": round(bb - bp, 6), "dm_stat": round(dm.dm_stat, 4),
                "dm_p": round(dm.p_value, 6), "n_clusters": dm.n_clusters,
                "prior_beats_base": beats}
    a2b = one(p0_a, y_a, p0_b, y_b, gid_b)
    b2a = one(p0_b, y_b, p0_a, y_a, gid_a)
    repl = "REPLICATED" if (a2b["prior_beats_base"] and b2a["prior_beats_base"]) else (
        "PARTIAL" if (a2b["prior_beats_base"] or b2a["prior_beats_base"]) else "REJECT")
    return {"a_to_b": a2b, "b_to_a": b2a, "verdict": repl}


@dataclass
class DefenderGateVerdict:
    verdict: str
    col: str
    n_corpora: int
    gate_ingame: Dict = field(default_factory=dict)      # the proven in-game gate result
    faithful: Dict = field(default_factory=dict)          # prior-vs-base-rate (real signal)
    planted_null: Dict = field(default_factory=dict)
    deciding_stat: str = ""
    caveats: List[str] = field(default_factory=list)
    vs_close: str = "UNPROVEN -- CALIBRATION only (held-out Brier), NOT a market edge"
    proposal_only: bool = True

    def to_dict(self) -> Dict:
        return {k: getattr(self, k) for k in
                ("verdict", "col", "n_corpora", "gate_ingame", "faithful",
                 "planted_null", "deciding_stat", "caveats", "vs_close", "proposal_only")}


def _corpora(df, col: str, *, planted_null: bool):
    """Split the layer into the two season corpora and adapt each onto the gate schema."""
    seasons = _season(df["game_date"])
    uniq = sorted(set(int(s) for s in seasons))
    out = []
    for s in uniq:
        base, detail = _adapt_corpus(df[seasons == s], col, planted_null=planted_null,
                                     seed=1000 + s)
        out.append((s, base, detail))
    return out


def _real_arrays(df, col: str, *, planted_null: bool, seed: int):
    base, detail = _adapt_corpus(df, col, planted_null=planted_null, seed=seed)
    return (detail["detail"].to_numpy(dtype=float), base["outcome"].to_numpy(dtype=float),
            base["game_id"].to_numpy())


def run(col: str = _DEFAULT_COL, layer_path: Optional[Path] = None) -> DefenderGateVerdict:
    """Load the layer, run the proven in-game gate + the faithful prior-vs-base-rate
    test (both DM-clustered-by-game, 2 season corpora, both directions) + the planted
    null through the IDENTICAL faithful path; return an HONEST verdict."""
    df = load_layer(layer_path)
    corp = _corpora(df, col, planted_null=False)
    n_corpora = len(corp)
    caveats = [
        "GATE REUSED: detail_layer_gate.gate_detail_layer (DM clustered by game_id, "
        "degenerate-base guard, graceful degrade) -- NO new scoring math added.",
        "The in-game gate's BASE = sigmoid((a+b*frac)*state_diff); a per-defender-game "
        "row has NO in-game state, so state_diff/frac_elapsed=0 -> BASE collapses to the "
        "base-rate and base_degenerate=True. The in-game gate is NOT_TESTABLE here, and "
        "it says so itself -- we report that honestly, not as a SHIP.",
        "FAITHFUL test reuses the IDENTICAL diebold_mariano (clustered by game_id): does "
        "the as-of feature (as p0) beat the constant base-rate on a BINARY realized-FG%-"
        "allowed label, OOS, REPLICATED both directions across the two seasons?",
        "Leak-free: p0 = shift1 prior-N as-of feature; label = THIS-game realized "
        "diagnostic (never a feature); def_n_prior>=%d support floor; close never present."
        % _MIN_PRIOR,
        "PLANTED-NULL pure-noise column run through the IDENTICAL faithful path MUST "
        "REJECT -- proves the gate can FAIL a signal. NO $ field anywhere.",
    ]
    if n_corpora < 2:
        return DefenderGateVerdict(
            "INSUFFICIENT_DATA", col, n_corpora, {}, {}, {},
            "only %d season corpus on disk; need >=2 independent corpora" % n_corpora,
            caveats)

    # ---- proven in-game gate (expected: base_degenerate -> capped below REPLICATED) ----
    (_, base_a, det_a), (_, base_b, det_b) = corp[0], corp[1]
    try:
        gv = gate_detail_layer(base_a, det_a, base_b, det_b, col="detail",
                               sport="defender_matchup", min_ticks=10, eps=_EPS)
        gate_ingame = {"verdict": gv.verdict,
                       "a_base_degenerate": bool(gv.a_to_b.get("base_degenerate")),
                       "b_base_degenerate": bool(gv.b_to_a.get("base_degenerate")),
                       "a_to_b": gv.a_to_b, "b_to_a": gv.b_to_a}
    except ValueError as exc:
        gate_ingame = {"verdict": "REJECT", "error": f"{type(exc).__name__}: {exc}"}

    # ---- faithful prior-vs-base-rate (real signal vs the base-rate, DM-clustered) ----
    pa, ya, ga = _real_arrays(df[_season(df["game_date"]) == corp[0][0]], col,
                              planted_null=False, seed=1)
    pb, yb, gb = _real_arrays(df[_season(df["game_date"]) == corp[1][0]], col,
                              planted_null=False, seed=2)
    faithful = _prior_vs_baserate(pa, ya, ga, pb, yb, gb)

    # ---- PLANTED-NULL control through the IDENTICAL faithful path ----
    na = _real_arrays(df[_season(df["game_date"]) == corp[0][0]], col,
                      planted_null=True, seed=101)
    nb = _real_arrays(df[_season(df["game_date"]) == corp[1][0]], col,
                      planted_null=True, seed=202)
    planted = _prior_vs_baserate(na[0], na[1], na[2], nb[0], nb[1], nb[2])
    null_rejects = planted["verdict"] == "REJECT"

    # ---- honest verdict ----
    if not null_rejects:
        verdict = "NOT_TESTABLE"
        deciding = ("planted-null did NOT reject (verdict=%s) -- gate cannot be trusted "
                    "to FAIL a signal; result void" % planted["verdict"])
    else:
        # the in-game gate is structurally NOT_TESTABLE (no in-game state); the binding
        # honest signal verdict is the faithful cross-corpus replication.
        verdict = faithful["verdict"]  # REPLICATED->SHIP-candidate / PARTIAL / REJECT
        if verdict == "REPLICATED":
            verdict = "SHIP"
        deciding = ("faithful both-direction prior-vs-base-rate (DM clustered by game): "
                    "A->B beats=%s dm_p=%s ; B->A beats=%s dm_p=%s ; in-game gate "
                    "base_degenerate=%s (NOT_TESTABLE by the in-game gate)" % (
                        faithful["a_to_b"]["prior_beats_base"], faithful["a_to_b"]["dm_p"],
                        faithful["b_to_a"]["prior_beats_base"], faithful["b_to_a"]["dm_p"],
                        gate_ingame.get("a_base_degenerate")))
    return DefenderGateVerdict(verdict, col, n_corpora, gate_ingame, faithful,
                               {**planted, "rejects": null_rejects}, deciding, caveats)


def write(v: DefenderGateVerdict, out: Optional[Path] = None) -> str:
    dest = Path(out) if out is not None else _OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="ascii") as f:
        json.dump(v.to_dict(), f, indent=2, sort_keys=True)
    return str(dest)


def _report(v: DefenderGateVerdict) -> str:
    f = v.faithful
    a, b = f.get("a_to_b", {}), f.get("b_to_a", {})
    lines = [
        "=" * 72,
        "DEFENDER-MATCHUP LAYER GATE: as-of %r vs base-rate (proven gate machinery)" % v.col,
        "=" * 72,
        "VERDICT        : %s" % v.verdict,
        "corpora        : %d (two NBA seasons)" % v.n_corpora,
        "in-game gate   : %s  (a_base_degenerate=%s b_base_degenerate=%s)" % (
            v.gate_ingame.get("verdict"), v.gate_ingame.get("a_base_degenerate"),
            v.gate_ingame.get("b_base_degenerate")),
        "-" * 72,
        "FAITHFUL prior-vs-base-rate (DM clustered by game_id), both directions:",
        "  A->B: BASE %s -> +PRIOR %s (delta %s)  DM p %s  beats=%s" % (
            a.get("brier_base"), a.get("brier_prior"), a.get("brier_delta"),
            a.get("dm_p"), a.get("prior_beats_base")),
        "  B->A: BASE %s -> +PRIOR %s (delta %s)  DM p %s  beats=%s" % (
            b.get("brier_base"), b.get("brier_prior"), b.get("brier_delta"),
            b.get("dm_p"), b.get("prior_beats_base")),
        "  faithful replication: %s" % f.get("verdict"),
        "-" * 72,
        "PLANTED-NULL (pure noise) through IDENTICAL path: verdict=%s  REJECTS=%s" % (
            v.planted_null.get("verdict"), v.planted_null.get("rejects")),
        "deciding stat  : %s" % v.deciding_stat,
        "vs_close       : %s" % v.vs_close,
        "=" * 72,
    ]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Gate the defender-matchup as-of layer.")
    ap.add_argument("--col", default=_DEFAULT_COL)
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)
    try:
        v = run(col=args.col)
    except FileNotFoundError as exc:
        print("BLOCKED (layer parquet missing): %s" % exc)
        return 1
    print(_report(v))
    if not args.no_write:
        print("wrote %s" % write(v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
