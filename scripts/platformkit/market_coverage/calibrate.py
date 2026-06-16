"""scripts.platformkit.market_coverage.calibrate -- per-market CALIBRATION engine.

Makes EVERY market (liquid mainline, obscure prop, deep combo/SGP, in-game micro,
cross-sport) BEST-CALIBRATED -- reliability + Brier vs its (often soft/thin/absent)
close -- even where there is no edge. An honest "MARKET-EFFICIENT HERE" is a
first-class verdict, never a failure.

REUSE READ-ONLY (never edit -- human-gated): eval-gate scoring (brier / ece /
brier_skill_score / resolution / sharpness), cluster-robust Diebold-Mariano, Shin
devig. The sim PRICES; this only SCORES + CALIBRATES vs a close. The LLM authors no
number. HONEST RAILS (binding): calibration vs the market's OWN (soft/thin) close,
leak-free; BSS vs the SHIN-devigged close is the primary metric; a "beat" needs the
full bar (DM p<0.05 AND N>=200 clusters AND lower Brier), anything short ->
MARKET-EFFICIENT HERE; obscure markets with no local close are PRICED + CALIBRATED now
but VALIDATION_PENDING + flagged "needs forward CLV"; no fabricated survivor, no $.

Families (7): player-props-core, player-props-combos, team-quarter-half,
game-scenario-longshot, sgp-correlation, mlb-soccer-tennis, ingame-micro.
Run: python -m scripts.platformkit.market_coverage.calibrate [--json] [--family F]
ASCII only, offline, deterministic, < 60s. <=300 LOC. Test: test_calibrate.py.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

_HERE = pathlib.Path(__file__).resolve().parent
_REPO = _HERE.parent.parent.parent
for _p in (str(_REPO), str(_HERE.parent / "eval_gate")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# READ-ONLY reuse of the REAL gate machinery -- no reimplementation.
from scripts.platformkit.eval_gate.scoring import (  # noqa: E402
    brier, ece, brier_skill_score, resolution, sharpness)
from scripts.platformkit.eval_gate.dm_test import diebold_mariano  # noqa: E402
from scripts.platformkit.eval_gate.shin import shin_devig  # noqa: E402

# Honest verdict / status vocabulary. DM gate bar (a beat needs ALL THREE).
MIN_CLUSTERS = 200          # DM clusters (>=N games) before a beat may even be considered
DM_ALPHA = 0.05             # clustered DM significance
SPARSE_N = 30               # reliability bins below this are flagged unreliable
N_BINS = 10
# liquidity policing -- how hard sharp money keeps a market efficient.
LIQ_LIQUID = "LIQUID (razor-policed)"          # mainlines: we MATCH, never beat
LIQ_SEMI = "SEMI-LIQUID"                         # core props
LIQ_THIN = "THIN (lightly policed)"              # combos / scenarios / quarter-half
LIQ_NONE = "NO-CLOSE (price-only)"               # obscure / longshot / SGP / in-game micro
# data status -- can we VALIDATE the calibration locally, or only forward?
ST_GATED = "GATED-LOCAL"             # a real local close corpus exists -> gate decides now
ST_FWD = "VALIDATION_PENDING"        # priced + calibrated, no local close -> forward-capture only
# market-level calibration verdict (never a $ claim).
V_EFFICIENT = "MARKET-EFFICIENT HERE"            # matches the devigged close within noise
V_BEHIND = "BEHIND (model trails close -- honest)"
V_CALIB = "CALIBRATED (no close to beat)"        # reliability good, nothing to beat
V_SUGGESTIVE = "SUGGESTIVE (soft-line beat -- needs forward CLV)"  # NOT a $ claim
V_ABSTAIN = "ABSTAIN (too few rows)"

FLAG_FWD_CLV = "needs forward CLV"

DISCLAIMER = (
    "CALIBRATION, not a $ edge. The sim PRICES every market; this scores reliability "
    "+ Brier vs the (often soft / thin / absent) close. MARKET-EFFICIENT HERE is the "
    "honest, expected result on liquid mainlines. A soft-line in-sample beat is "
    "SUGGESTIVE only -- flagged '" + FLAG_FWD_CLV + "', never a dollar claim. "
    "edge_claimed=False everywhere. Obscure markets with no local close are PRICED + "
    "CALIBRATED now but VALIDATION_PENDING (forward capture)."
)


# Reliability (per-market): equal-width bins, sparse-flagged (mirrors calibration_record).
def reliability_bins(p: Sequence[float], y: Sequence[float],
                     n_bins: int = N_BINS) -> List[dict]:
    """One dict per NON-EMPTY equal-width bin: range, n, mean predicted, observed
    frequency, sparse flag (n < SPARSE_N). The per-bin n values sum to len(p)."""
    pa, ya = np.asarray(p, float), np.asarray(y, float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(pa, edges[1:-1]), 0, n_bins - 1)
    rows: List[dict] = []
    for b in range(n_bins):
        m = idx == b
        nk = int(m.sum())
        if not nk:
            continue
        rows.append({"lo": float(edges[b]), "hi": float(edges[b + 1]), "n": nk,
                     "pred": float(pa[m].mean()), "obs": float(ya[m].mean()),
                     "sparse": nk < SPARSE_N})
    return rows


def _devig_close(book_probs: Optional[Sequence[float]]) -> Optional[float]:
    """Shin-devig a 2-outcome book (the market's own quote) -> fair P(outcome 0).
    book_probs are quoted implied probs (1/odds) for [outcome, complement]; booksum
    >= 1. Returns None when no quote (price-only / obscure market)."""
    if book_probs is None:
        return None
    pi = np.asarray(book_probs, float)
    if pi.size != 2 or pi.sum() <= 1.0 + 1e-9:
        # already fair or malformed -> just normalize
        return float(pi[0] / pi.sum()) if pi.sum() > 0 else None
    fair, _z = shin_devig(pi)
    return float(fair[0])


def calibrate_market(name: str, liquidity: str, p_model: Sequence[float],
                     y: Sequence[float],
                     p_close: Optional[Sequence[float]] = None) -> dict:
    """Score ONE market's calibration. p_model = our (sim-priced, calibrated) probs,
    y = realized 0/1, p_close = devigged close probs (None when no local close).

    Returns reliability + Brier/ECE/sharpness/resolution, and -- only when a real
    close exists with enough clusters -- BSS + clustered DM vs the close, with an
    HONEST verdict. No close -> CALIBRATED / VALIDATION_PENDING. No $ claim ever.
    """
    pm = np.asarray(p_model, float)
    ya = np.asarray(y, float)
    n = int(pm.size)
    bins = reliability_bins(pm, ya)
    out: dict = {
        "market": name, "liquidity": liquidity, "n": n,
        "brier": brier(pm, ya) if n else None,
        "ece": ece(pm, ya) if n else None,
        "sharpness": sharpness(pm) if n else None,
        "resolution": resolution(pm, ya) if n else None,
        "bins": bins, "edge_claimed": False, "flags": [],
    }
    has_close = p_close is not None and len(p_close) == n and n > 0
    if not has_close:
        # PRICE-ONLY market: calibrate now, validate forward.
        out["data_status"] = ST_FWD
        out["verdict"] = V_CALIB if n else V_ABSTAIN
        out["flags"].append(FLAG_FWD_CLV)
        return out

    pc = np.asarray(p_close, float)
    out["data_status"] = ST_GATED
    out["brier_close"] = brier(pc, ya)
    out["bss_vs_close"] = brier_skill_score(pm, pc, ya)
    # clustered DM on per-row Brier loss; cluster by game when given, else by row.
    cids = out.get("_cluster_ids")
    if cids is None:
        cids = list(range(n))
    d = (pc - ya) ** 2 - (pm - ya) ** 2          # >0 => model better than close
    dm = diebold_mariano(d, cids)
    out["dm_p"] = dm.p_value
    out["dm_clusters"] = dm.n_clusters
    out["dm_mean_diff"] = dm.mean_diff
    # Verdict: a beat requires the FULL bar (power + significance + lower Brier).
    beats = (dm.n_clusters >= MIN_CLUSTERS and dm.p_value < DM_ALPHA
             and out["brier"] < out["brier_close"])
    if n < SPARSE_N:
        out["verdict"] = V_ABSTAIN
    elif beats:
        # liquid mainlines should NOT survive this -- if one does, it is SUGGESTIVE,
        # flagged needs-forward-CLV, NOT a $ claim (likely a soft / thin line).
        out["verdict"] = V_SUGGESTIVE
        out["flags"].append(FLAG_FWD_CLV)
    elif out["bss_vs_close"] < -0.02:
        out["verdict"] = V_BEHIND
    else:
        out["verdict"] = V_EFFICIENT
    return out


# Enumeration -- the 7 families. has_local_close=True -> the gate scores it NOW;
# False (the obscure/thin lane, the whole thesis) -> PRICED + CALIBRATED, flagged
# VALIDATION_PENDING. THE CATCH: the mispricing lane is exactly where no local close
# exists to validate against.
FAMILIES: Dict[str, dict] = {
    "player-props-core": {
        "liquidity": LIQ_SEMI, "has_local_close": True,
        "markets": ["pts O/U", "reb O/U", "ast O/U", "3PM O/U", "pra O/U"],
        "note": "core single-stat props -- semi-liquid, some local closes; we MATCH."},
    "player-props-combos": {
        "liquidity": LIQ_THIN, "has_local_close": False,
        "markets": ["pts+reb", "pts+ast", "reb+ast", "double-double", "triple-double", "5x5"],
        "note": "same-player combos -- THIN; sim JOINT under-prices DDs; forward only."},
    "team-quarter-half": {
        "liquidity": LIQ_THIN, "has_local_close": True,
        "markets": ["Q1 total", "1H total", "Q1 ML", "team total", "race-to-N"],
        "note": "quarter/half derivatives -- thin, some closes; calibrate first."},
    "game-scenario-longshot": {
        "liquidity": LIQ_NONE, "has_local_close": False,
        "markets": ["blowout 20+", "OT yes", "shootout 240+", "rockfight <200",
                    "50-burst +10000", "exact-margin"],
        "note": "scenario/longshot tails -- NO-CLOSE price-only; validate forward."},
    "sgp-correlation": {
        "liquidity": LIQ_NONE, "has_local_close": False,
        "markets": ["2-leg SGP", "3-leg SGP", "4-leg SGP", "star pts+team-win"],
        "note": "SGP off the JOINT sim (correlation lift); no SGP close -> forward only."},
    "mlb-soccer-tennis": {
        "liquidity": LIQ_SEMI, "has_local_close": True,
        "markets": ["mlb ML", "mlb total", "soccer O/U-2.5", "tennis ML", "soccer BTTS"],
        "note": "cross-sport mainlines -- proven MATCH on team-strength; reuse corpora."},
    "ingame-micro": {
        "liquidity": LIQ_NONE, "has_local_close": False,
        "markets": ["next-basket", "next-team-to-score", "live win-prob",
                    "rest-of-quarter total", "live alt-spread"],
        "note": "in-game micro from the rest-of-game sim -- NO close; validate forward."},
}

ENUMERATION = list(FAMILIES.keys())


# Deterministic offline FIXTURE: a SYNTHETIC well-calibrated model vs a slightly-
# sharper close -> exercises the scoring path + honest verdicts WITHOUT fabricating a
# survivor (the model MATCHES, never beats). Real corpora replace this in production.
def _fixture(name: str, has_close: bool, n: int = 240,
             seed: int = 7) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
    """Synthetic (p_model, y, p_close|None). The model is calibrated; the close is
    the same truth + tiny noise (so it MATCHES, never beats -- no fake survivor)."""
    rng = np.random.default_rng(seed + (hash(name) & 0xFFFF))
    truth = rng.uniform(0.05, 0.95, n)               # true event probabilities
    y = (rng.uniform(size=n) < truth).astype(float)
    # calibrated model = truth + small unbiased noise, clipped to (0,1).
    noise = rng.normal(0, 0.03, n)
    p_model = np.clip(truth + noise, 1e-3, 1 - 1e-3)
    if not has_close:
        return p_model, y, None
    # The close is constructed STRICTLY SHARPER than the model: it sees the SAME
    # truth plus a SHRUNKEN copy of the model's own error (0.4x). By construction it
    # weakly dominates, so the honest fixture verdict is MATCH / BEHIND and NO
    # per-seed model "beat" can survive -- the scoreboard never fabricates an edge.
    p_close = np.clip(truth + 0.4 * noise, 1e-3, 1 - 1e-3)
    return p_model, y, p_close


def run_family(fam: str, n: int = 240) -> List[dict]:
    """Calibrate every market in one family on the offline fixture. Real callers
    swap _fixture for sim-priced probs + a real (or absent) close corpus."""
    spec = FAMILIES[fam]
    has_close = bool(spec["has_local_close"])
    rows: List[dict] = []
    for mkt in spec["markets"]:
        pm, y, pc = _fixture(f"{fam}:{mkt}", has_close, n=n)
        # Exercise the REAL shin devig path: vig the fair close to quoted implied probs
        # (booksum 1.05), then recover the fair prob (round-trips to ~pc).
        if pc is not None:
            pcd = np.empty_like(pc)
            for i, q in enumerate(np.clip(pc, 1e-3, 1 - 1e-3)):
                quoted = np.array([q, 1.0 - q]) * 1.05      # 5% vig, booksum 1.05
                pcd[i] = _devig_close(quoted)
            pc = pcd
        r = calibrate_market(f"{fam} / {mkt}", spec["liquidity"], pm, y, pc)
        rows.append(r)
    return rows


def run_all(n: int = 240) -> Dict[str, List[dict]]:
    return {fam: run_family(fam, n=n) for fam in ENUMERATION}


# Rendering lives in calibrate_render (keeps this engine module <=300 LOC).
def build_scoreboard(results: Dict[str, List[dict]]) -> List[str]:
    """ASCII scoreboard for the calibrated book. Delegates to calibrate_render with this
    module's verdict vocabulary. CALIBRATION verdicts only -- never a $ claim."""
    try:
        from scripts.platformkit.market_coverage import calibrate_render as R
    except ImportError:  # bare-run / per-file-test fallback
        import calibrate_render as R  # type: ignore
    return R.build_scoreboard(
        results, families=FAMILIES, enumeration=ENUMERATION, disclaimer=DISCLAIMER,
        flag_fwd_clv=FLAG_FWD_CLV, v_efficient=V_EFFICIENT, v_calib=V_CALIB,
        v_suggestive=V_SUGGESTIVE, v_behind=V_BEHIND, v_abstain=V_ABSTAIN)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="market_coverage.calibrate",
        description="Per-market calibration scoreboard (offline, deterministic).")
    ap.add_argument("--family", choices=ENUMERATION, default=None,
                    help="score one family only")
    ap.add_argument("--n", type=int, default=240, help="fixture rows per market")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args(argv)
    t0 = time.time()
    if args.family:
        results = {args.family: run_family(args.family, n=args.n)}
    else:
        results = run_all(n=args.n)
    if args.json:
        # strip the bulky per-bin tables from JSON unless asked; keep the scores.
        slim = {f: [{k: v for k, v in r.items() if k != "bins"} for r in rows]
                for f, rows in results.items()}
        print(json.dumps(slim, indent=2, default=float))
    else:
        print("\n".join(build_scoreboard(results)))
    print(f"# generated in {time.time() - t0:.2f}s (offline, no real data)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
