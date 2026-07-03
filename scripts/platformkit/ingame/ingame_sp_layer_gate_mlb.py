"""scripts.platformkit.ingame.ingame_sp_layer_gate_mlb -- GATE: does the PREGAME
starting-pitcher form prior (sp_diff_ew) improve in-game MLB win-prob on held-out
Brier, and does its value DECAY as the game progresses?

Pregame SP adjustment was just REJECTED (Brier 0.24438 -> 0.24446 at n=5731;
data/domains/mlb/sp_adjust_verdict.json). DIFFERENT question here: conditioned
on REALIZED in-game state, does the SP prior carry residual value, and does it
decay as frac_elapsed -> 1? Skeptical prior.

TWO LAYERS over the proven BASE (ingame_gate_generic_models pattern):
BASE      = sigmoid((a+b*frac_elapsed)*state_diff); a,b fit per fold.
+SP       = sigmoid(logit(BASE) + beta*z_sp)                  -- flat shift.
+SP_DECAY = sigmoid(logit(BASE) + beta*z_sp*(1-frac_elapsed)) -- shrinks to 0
            as the game becomes realized. beta fit on TRAIN only (grid search).

DATA: data/cache/ingame/mlb_pitch_states__{2024,2025,2026}.parquet. sp_diff_ew
from domains.mlb.sp_adjust_current, bridged game_pk -> event_id via
domains.mlb.game_pk_bridge (pitch corpus's game_id IS that event_id). Rows
with no resolved SP form are EXCLUDED from BOTH models (identical row-set).
WALK-FORWARD: expanding-window WITHIN each season, chronological by date.
VERDICT: SHIP iff Brier(+layer)<Brier(BASE) (DM p<0.05) EVERY corpus (>=2
required). PARTIAL some-not-all. REJECT none. NOISE CONTROL: permuted
sp_diff_ew must NOT improve Brier anywhere; else UNTRUSTWORTHY. NO $
anywhere; CALIBRATION only. PROPOSAL-ONLY: writes only
data/domains/mlb/ingame_sp_layer_verdict.json, never data/registry/, never a
flag. Never edit src/kernel/api/domains. <=300 LOC; ASCII-only.
CLI: python -m scripts.platformkit.ingame.ingame_sp_layer_gate_mlb
"""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.ingame.ingame_gate_generic_models import base_predict, fit_base
from scripts.platformkit.ingame.ingame_ladder_mlb_layers import logit, sigmoid

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_STATE_DIR = os.path.join(_REPO, "data", "cache", "ingame")
_MLB_DIR = os.path.join(_REPO, "data", "domains", "mlb")
OUT = os.path.join(_MLB_DIR, "ingame_sp_layer_verdict.json")

TERCILES = (("early", 0.0, 1.0 / 3.0), ("mid", 1.0 / 3.0, 2.0 / 3.0), ("late", 2.0 / 3.0, 1.0))
_GRID = np.linspace(-0.50, 0.50, 21)
_MIN_GAMES_PER_FOLD = 8
_N_FOLDS = 3

# --------------------------------------------------------------------------- load + join
def build_sp_form_by_event() -> pd.DataFrame:
    """Leak-free EW SP-form (sp_diff_ew) keyed by event_id, via game_pk_bridge. Rows
    with an ambiguous/unresolved game_pk or NaN sp_diff_ew are dropped honestly."""
    from domains.mlb.game_pk_bridge import build_game_pk_bridge
    from domains.mlb.sp_adjust_current import build_current_sp_form

    gamelogs = pd.read_parquet(os.path.join(_MLB_DIR, "player_gamelogs.parquet"))
    probables = pd.read_parquet(os.path.join(_MLB_DIR, "probables.parquet"))
    games_current = pd.read_parquet(os.path.join(_MLB_DIR, "games_current.parquet"))
    bridge = build_game_pk_bridge(player_gamelogs=gamelogs, games_current=games_current)
    sp = build_current_sp_form(gamelogs, probables).copy()
    sp["event_id"] = sp["game_pk"].map(bridge.mapping)
    sp = sp[sp["event_id"].notna() & sp["sp_diff_ew"].notna()]
    return sp[["event_id", "sp_diff_ew"]].drop_duplicates("event_id")

def load_pitch_states(path: str, sp_by_event: pd.DataFrame) -> List[dict]:
    """Load one per-pitch corpus, join sp_diff_ew by event_id (== game_id here).
    Rows without a resolved SP form are EXCLUDED from BOTH models' scoring."""
    df = pd.read_parquet(path)
    df = df.merge(sp_by_event, left_on="game_id", right_on="event_id", how="inner")
    df = df.sort_values(["date", "game_id", "asof_idx"], kind="mergesort")
    return [{
        "game_id": str(r.game_id), "date": str(r.date), "state_diff": float(r.state_diff),
        "frac_elapsed": max(0.0, min(1.0, float(r.frac_elapsed))),
        "outcome": int(r.outcome), "sp_diff_ew": float(r.sp_diff_ew),
    } for r in df.itertuples(index=False)]

def _permuted_sp(states: List[dict], seed: int = 20260702) -> List[dict]:
    """Cross-game permutation of sp_diff_ew (noise control) -- MUST fail to improve Brier."""
    rng = np.random.RandomState(seed)
    perm = rng.permutation([s["sp_diff_ew"] for s in states])
    return [dict(s, sp_diff_ew=float(v)) for s, v in zip(states, perm)]


# --------------------------------------------------------------------------- layers
def _standardize(x: np.ndarray) -> Tuple[np.ndarray, float, float]:
    mu, sd = float(x.mean()), float(x.std()) + 1e-9
    return (x - mu) / sd, mu, sd

def _decay_mult(states: List[dict], decay: bool) -> np.ndarray:
    """1.0 (flat) or (1-frac_elapsed) (decay: shrinks to 0 as game becomes realized)."""
    if not decay:
        return np.ones(len(states), float)
    return 1.0 - np.array([s["frac_elapsed"] for s in states], float)

def fit_sp_layer(train: List[dict], base_tr: np.ndarray, decay: bool):
    """sigmoid(logit(BASE) + beta*z_sp*mult); beta grid-fit on TRAIN Brier only."""
    y = np.array([s["outcome"] for s in train], float)
    z, mu, sd = _standardize(np.array([s["sp_diff_ew"] for s in train], float))
    mult = _decay_mult(train, decay)
    lo = logit(base_tr)
    best, best_b = 0.0, float(np.mean((base_tr - y) ** 2))
    for beta in _GRID:
        sc = float(np.mean((sigmoid(lo + beta * z * mult) - y) ** 2))
        if sc < best_b:
            best_b, best = sc, float(beta)
    return (best, mu, sd, decay)

def apply_sp_layer(test: List[dict], base_te: np.ndarray, params) -> np.ndarray:
    beta, mu, sd, decay = params
    z = (np.array([s["sp_diff_ew"] for s in test], float) - mu) / sd
    return sigmoid(logit(base_te) + beta * z * _decay_mult(test, decay))


# --------------------------------------------------------------------------- walk-forward
def _by_game(states: List[dict]) -> Tuple[Dict[str, List[dict]], List[str]]:
    by_game: Dict[str, List[dict]] = {}
    first_date: Dict[str, str] = {}
    for s in states:
        by_game.setdefault(s["game_id"], []).append(s)
        first_date.setdefault(s["game_id"], s["date"])
    return by_game, sorted(by_game.keys(), key=lambda g: (first_date[g], g))

def walk_forward_folds(states: List[dict], n_folds: int = _N_FOLDS):
    """Expanding-window chronological folds; yields (train, test) per usable fold."""
    by_game, order = _by_game(states)
    n = len(order)
    if n < (n_folds + 1) * 2:
        n_folds = max(1, n // 2 - 1)
    bounds = [int(round(i * n / (n_folds + 1))) for i in range(n_folds + 2)]
    for k in range(1, n_folds + 1):
        train_g, test_g = order[:bounds[k]], order[bounds[k]:bounds[k + 1]]
        if len(train_g) < _MIN_GAMES_PER_FOLD or len(test_g) < _MIN_GAMES_PER_FOLD:
            continue
        yield ([s for g in train_g for s in by_game[g]],
               [s for g in test_g for s in by_game[g]])

def _score_variant(states: List[dict], decay: bool) -> Optional[Dict]:
    """Walk-forward score one layer over one corpus; pooled OOS Brier(BASE) vs
    Brier(+layer), DM clustered by game_id, per-tercile breakdown."""
    ys, bases, layers, gids, fracs, per_fold = [], [], [], [], [], []
    for i, (train, test) in enumerate(walk_forward_folds(states)):
        ab = fit_base(train)
        base_tr, base_te = base_predict(train, ab), base_predict(test, ab)
        layer_te = apply_sp_layer(test, base_te, fit_sp_layer(train, base_tr, decay))
        y = np.array([s["outcome"] for s in test], float)
        bb, bl = float(brier(base_te, y)), float(brier(layer_te, y))
        per_fold.append({"fold": i, "n": int(len(y)), "brier_base": round(bb, 4),
                         "brier_layer": round(bl, 4), "delta": round(bb - bl, 5),
                         "layer_beats_base": bool(bl < bb)})
        ys.append(y); bases.append(base_te); layers.append(layer_te)
        gids += [s["game_id"] for s in test]; fracs += [s["frac_elapsed"] for s in test]
    if not ys:
        return None
    y, base, layer = np.concatenate(ys), np.concatenate(bases), np.concatenate(layers)
    fracs = np.asarray(fracs)
    bb, bl = float(brier(base, y)), float(brier(layer, y))
    dm = diebold_mariano((base - y) ** 2 - (layer - y) ** 2, gids)
    per_tercile = {}
    for name, lo, hi in TERCILES:
        m = (fracs >= lo) & (fracs < hi) if name != "late" else (fracs >= lo) & (fracs <= hi)
        if not m.any():
            continue
        tb, tl = float(brier(base[m], y[m])), float(brier(layer[m], y[m]))
        per_tercile[name] = {"n": int(m.sum()), "brier_base": round(tb, 4),
                             "brier_layer": round(tl, 4), "delta": round(tb - tl, 5)}
    return {
        "n_states": int(len(y)), "n_folds": len(per_fold),
        "brier_base": round(bb, 4), "brier_layer": round(bl, 4),
        "brier_delta": round(bb - bl, 5),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "n_games": dm.n_clusters, "layer_beats_base": bool(bl < bb and dm.p_value < 0.05),
        "per_fold": per_fold, "per_tercile": per_tercile,
    }


# --------------------------------------------------------------------------- verdict
@dataclass
class SpLayerVerdict:
    verdict: str
    per_corpus: Dict[str, Dict] = field(default_factory=dict)
    noise_control: Dict[str, Dict] = field(default_factory=dict)
    noise_ok: bool = False
    coverage: Dict[str, Dict] = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict,
            "layers": {"flat": "sigmoid(logit(BASE) + beta*z_sp)",
                      "decay": "sigmoid(logit(BASE) + beta*z_sp*(1-frac_elapsed))"},
            "base_model": "sigmoid((a+b*frac_elapsed)*state_diff); a,b fit per fold",
            "prior": "sp_diff_ew (leak-free EW SP form, domains.mlb.sp_adjust_current)",
            "pregame_context": "pregame SP layer REJECTED at n=5731 (0.24438->0.24446); "
                                "this gate is IN-GAME conditioning -- see caveats.",
            "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
            "proposal_only": True, "no_dollar_field": True,
            "per_corpus": self.per_corpus, "noise_control": self.noise_control,
            "noise_ok": self.noise_ok, "coverage": self.coverage, "caveats": list(self.caveats),
        }

def _layer_verdict(results: Dict[str, Optional[Dict]]) -> str:
    usable = {k: v for k, v in results.items() if v is not None}
    if len(usable) < 2:
        return "INSUFFICIENT_DATA"
    beats = [v["layer_beats_base"] for v in usable.values()]
    if all(beats):
        return "SHIP"
    return "PARTIAL" if any(beats) else "REJECT"

def gate(corpora: Dict[str, List[dict]]) -> SpLayerVerdict:
    """Full gate: flat + decay layers over every corpus, plus the mandatory noise
    control (permuted sp_diff_ew, must NOT ship)."""
    coverage = {k: {"n_states": len(v), "n_games": len({s["game_id"] for s in v})}
               for k, v in corpora.items()}
    caveats = [
        "Leak-free: beta fit on TRAIN fold only; sp_diff_ew is a strictly-prior EW snapshot.",
        "Rows without a resolved SP form are EXCLUDED from BOTH models -- identical row-set.",
        "Expanding-window walk-forward WITHIN each season; >=2 corpora required before SHIP.",
        "SKEPTICAL PRIOR: pregame SP layer REJECTED at n=5731 (Brier 0.24438->0.24446).",
    ]
    usable = {k: v for k, v in corpora.items() if len(v) >= 200 and
              len({s["game_id"] for s in v}) >= _MIN_GAMES_PER_FOLD * 2}
    if len(usable) < 2:
        return SpLayerVerdict("INSUFFICIENT_DATA", {}, {}, False, coverage,
                              caveats + ["fewer than 2 usable corpora on disk"])

    flat_r = {k: _score_variant(v, decay=False) for k, v in corpora.items()}
    decay_r = {k: _score_variant(v, decay=True) for k, v in corpora.items()}
    noise_r = {k: _score_variant(_permuted_sp(v), decay=True) for k, v in corpora.items()}
    noise_usable = {k: v for k, v in noise_r.items() if v is not None}
    noise_ok = len(noise_usable) >= 1 and not any(
        v["layer_beats_base"] for v in noise_usable.values())
    flat_v, decay_v = _layer_verdict(flat_r), _layer_verdict(decay_r)
    if not noise_ok:
        final = "UNTRUSTWORTHY"
        caveats.append("NOISE CONTROL FAILED: a permuted sp_diff_ew column improved "
                        "held-out Brier -- the harness is broken; verdict discarded.")
    elif decay_v == "INSUFFICIENT_DATA" and flat_v == "INSUFFICIENT_DATA":
        final = "INSUFFICIENT_DATA"
    else:
        final = decay_v if decay_v != "INSUFFICIENT_DATA" else flat_v

    per_corpus = {k: {"flat": flat_r.get(k), "decay": decay_r.get(k)} for k in corpora}
    return SpLayerVerdict(final, per_corpus, noise_r, noise_ok, coverage, caveats)


# --------------------------------------------------------------------------- driver
def _find_corpora() -> List[str]:
    return sorted(glob.glob(os.path.join(_STATE_DIR, "mlb_pitch_states__*.parquet")))

def run() -> SpLayerVerdict:
    paths = _find_corpora()
    if len(paths) < 2:
        return SpLayerVerdict("INSUFFICIENT_DATA", {}, {}, False,
                              {"corpora_found": len(paths)},
                              [f"need >=2 mlb_pitch_states__*.parquet; found {len(paths)}"])
    sp_by_event = build_sp_form_by_event()
    corpora = {os.path.basename(p).split("__")[1].replace(".parquet", ""):
              load_pitch_states(p, sp_by_event) for p in paths}
    return gate(corpora)

def write(v: SpLayerVerdict, out: str = OUT) -> str:
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="ascii") as f:
        json.dump(v.to_dict(), f, indent=2, sort_keys=True)
    return out

def _report(v: SpLayerVerdict) -> str:
    lines = ["=" * 72, "IN-GAME SP-FORM PRIOR LAYER GATE (MLB): flat vs decay vs BASE",
             "=" * 72, f"VERDICT: {v.verdict}", f"noise control OK: {v.noise_ok}",
             "-" * 72]
    for corpus, d in v.per_corpus.items():
        lines.append(f"corpus {corpus}: coverage {v.coverage.get(corpus)}")
        for tag in ("flat", "decay"):
            r = d.get(tag)
            if not r:
                lines.append(f"  {tag}: no usable folds")
                continue
            lines.append(f"  {tag}: BASE {r['brier_base']} -> +{tag.upper()} {r['brier_layer']}"
                         f" (delta {r['brier_delta']:+.5f}) DM p={r['dm_p']} beats={r['layer_beats_base']}")
            for tname, td in r["per_tercile"].items():
                lines.append(f"      {tname:5s} n={td['n']:5d} base {td['brier_base']} -> "
                             f"layer {td['brier_layer']} delta {td['delta']:+.5f}")
    lines.append("=" * 72)
    return "\n".join(lines)

def main() -> None:
    v = run()
    p = write(v)
    print(_report(v))
    print(f"wrote {p}")

if __name__ == "__main__":
    main()
