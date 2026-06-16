"""market_coverage.edge_finder -- the OBSCURE-MARKET EDGE-FINDER.

THESIS (the honest edge lane): liquid mainlines (sides/totals on major games) are razor-
efficient -- our model MATCHES them (proven). The edge, if any, lives in EXTREME / OBSCURE /
PROP / DEEP-COMBO (SGP) / IN-GAME-MICRO markets that little/no sharp money polices. This module
ENUMERATES every imaginable bet bucket and, for each market WITH real local close data, runs the
REAL eval_gate.walk_forward vs the SHIN-devigged close (leak-free, clustered DM, BSS), then RANKS
markets by model-beats-soft-line. Honest SHIP / REJECT / MATCH.

THE CATCH (binding honesty): almost every obscure/prop/SGP/in-game-micro market has NO real
historical close data locally -> it can be PRICED + CALIBRATED now (see markets.py) but only
VALIDATED via forward capture. Those are flagged NEEDS_FORWARD_CLV -- a soft-line in-sample beat
is SUGGESTIVE, NOT a $ claim, and real $ is capped by book limits regardless. NO fabricated
survivor: a market with no close cannot SHIP here, by construction.

REUSE READ-ONLY (never edited -- all human-gated): eval_gate.walk_forward / scoring / dm_test /
shin (via corpora.py). The sim/market_intelligence/predict_matchup price; this module JUDGES.
Buckets: player-props-core, player-props-combos, team-quarter-half, game-scenario-longshot,
sgp-correlation, mlb-soccer-tennis, ingame-micro. ASCII only. <=300 LOC.
Per-file test: tests/test_edge_finder.py.  Run: python -m scripts.platformkit.market_coverage.edge_finder
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# --- READ-ONLY reuse of the REAL eval gate (the JUDGE). Package + bare-run fallbacks. -------
try:
    from scripts.platformkit.eval_gate.walkforward import walk_forward
    from scripts.platformkit.eval_gate import scoring as S
    from scripts.platformkit.eval_gate.dm_test import diebold_mariano
    from scripts.platformkit.market_coverage.corpora import (
        devig_two_way, nba_ml_states, mlb_ml_states, soccer_ou25_states)
except ImportError:  # direct-script / per-file-test fallback
    _EG = Path(__file__).resolve().parents[1] / "eval_gate"
    sys.path.insert(0, str(_EG))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from walkforward import walk_forward  # type: ignore
    import scoring as S  # type: ignore
    from dm_test import diebold_mariano  # type: ignore
    from corpora import (  # type: ignore
        devig_two_way, nba_ml_states, mlb_ml_states, soccer_ou25_states)

# Pre-registered SHIP rule -- mirrors the eval gate's BEATS_CLOSE bar (no $).
ALPHA = 0.05
MIN_N = 200
MIN_CORPORA = 2          # a single-corpus lift is an artifact; require >=2 independent corpora
MATCH_BSS = 0.01         # |BSS| within this of 0 -> "MATCH" (efficient), not a beat
SOCCER_CAP = 2500        # cap the soccer corpus slice (walk_forward is O(n^2)); recent + >MIN_N

# The 7 enumeration buckets (ASCII, fixed order).
BUCKETS = [
    "player-props-core", "player-props-combos", "team-quarter-half",
    "game-scenario-longshot", "sgp-correlation", "mlb-soccer-tennis", "ingame-micro",
]


# ===========================================================================
# A market is a (name, bucket, sport) + optionally a corpus state-builder.
# has_close=False markets are PRICEABLE (markets.py) but NOT validatable locally:
# they get verdict NEEDS_FORWARD_CLV and can NEVER ship here -> no fabricated survivor.
# ===========================================================================
@dataclass
class MarketSpec:
    name: str
    bucket: str
    sport: str
    has_close: bool
    builder: Optional[Callable[[Path], List[dict]]] = None   # corpus_root -> eval-gate states
    note: str = ""


@dataclass
class MarketResult:
    name: str
    bucket: str
    sport: str
    verdict: str             # SHIP | REJECT | MATCH | NEEDS_FORWARD_CLV | DATA_LIMITED
    n: int = 0
    n_corpora: int = 0
    bss: float = 0.0         # Brier skill score vs the SHIN-devigged close (pooled)
    brier_model: float = 0.0
    brier_close: float = 0.0
    ece: float = 0.0
    sharpness: float = 0.0
    dm_p: float = 1.0
    dm_stat: float = 0.0
    reason: str = ""
    needs_forward_clv: bool = False
    meta: Dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d.pop("meta", None)
        return d


# The leak-free has-close predict_fn: a deliberately weak own-data forecaster (train-slice base
# rate shrunk toward the close) fit ONLY on the train slice -- the point is the GATE verdict (do
# we beat the soft close?), not a tuned engine. walk_forward enforces no-lookahead.
def _shrink_to_close_predict(train: List[dict], test: dict, select_inside: bool) -> float:
    pc = float(test["devig_close_prob"])
    base = float(np.mean([t["outcome"] for t in train])) if train else 0.5  # leak-free past only
    w = 0.15                                            # fixed inside-window weight (no test tuning)
    p = (1.0 - w) * pc + w * base
    return float(min(max(p, 1e-4), 1.0 - 1e-4))


# ===========================================================================
# ENUMERATION -- every bucket. Mainlines (has_close=True) get real gate runs;
# obscure/prop/SGP/in-game-micro (has_close=False) are PRICEABLE-ONLY -> NEEDS_FORWARD_CLV.
# This is the honest census: ~all the obscure buckets have no local close.
# ===========================================================================
def enumerate_markets() -> List[MarketSpec]:
    M: List[MarketSpec] = []
    # --- mlb-soccer-tennis + the NBA mainline reference: the ONLY has-close markets ---
    M.append(MarketSpec("nba_moneyline", "mlb-soccer-tennis", "nba", True,
                        nba_ml_states, "NBA moneyline -- liquid mainline, expect MATCH"))
    M.append(MarketSpec("mlb_moneyline", "mlb-soccer-tennis", "mlb", True,
                        mlb_ml_states, "MLB moneyline -- liquid mainline, expect MATCH"))

    # --- player-props-core: priceable from the sim, NO local close -> forward CLV only ---
    for st in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        M.append(MarketSpec(f"player_{st}_ou", "player-props-core", "nba", False,
                            note="soft prop line; priceable+calibratable, no local close"))
    # --- player-props-combos: PRA/PR/PA/RA/stocks + milestone ladders ---
    for st in ("pra", "pr", "pa", "ra", "stocks", "pts_30plus", "ast_10plus", "reb_15plus"):
        M.append(MarketSpec(f"player_{st}", "player-props-combos", "nba", False,
                            note="combo/milestone; thin line, forward CLV only"))
    # --- team-quarter-half: quarter/half team totals + sides ---
    for seg in ("q1", "q2", "q3", "q4", "h1", "h2"):
        M.append(MarketSpec(f"team_total_{seg}", "team-quarter-half", "nba", False,
                            note="quarter/half total; thinly policed, no local close"))
        M.append(MarketSpec(f"side_{seg}", "team-quarter-half", "nba", False,
                            note="quarter/half side; forward CLV only"))
    # --- game-scenario-longshot: exotics / tails ---
    for sc in ("double_double", "triple_double", "5x5", "player_50plus_pts",
               "team_150plus", "race_to_20", "winning_margin_band"):
        M.append(MarketSpec(sc, "game-scenario-longshot", "nba", False,
                            note="longshot/scenario; tail price, forward CLV only"))
    # --- sgp-correlation: joint baskets (the whole sim edge is correlation pricing) ---
    for sgp in ("sgp_2leg_sameplayer", "sgp_2leg_teammates", "sgp_3leg_mixed",
                "sgp_star_plus_total"):
        M.append(MarketSpec(sgp, "sgp-correlation", "nba", False,
                            note="joint SGP; correlation lift priceable, NO SGP close locally"))
    # --- the other two of the mlb-soccer-tennis trio (no devigged close builder yet) ---
    M.append(MarketSpec("soccer_ou25", "mlb-soccer-tennis", "soccer", True,
                        soccer_ou25_states, "soccer O/U 2.5 -- REAL has-close totals market"))
    M.append(MarketSpec("tennis_matchwin", "mlb-soccer-tennis", "tennis", False,
                        note="tennis match-win -- close exists; proof harness owns it; priced here"))
    # --- ingame-micro: live re-priced micro markets, NO historical micro close locally ---
    for mic in ("next_basket", "next_team_to_score", "live_winprob_band",
                "race_to_next_5", "in_game_player_milestone"):
        M.append(MarketSpec(mic, "ingame-micro", "nba", False,
                            note="in-game micro; live-repriceable, validation = forward capture"))
    return M


# ===========================================================================
# The GATE run for ONE has-close market across (potentially) several corpora.
# ===========================================================================
def _gate_one_corpus(states: List[dict]) -> Optional[dict]:
    if len(states) < MIN_N:
        return None
    res = walk_forward(states, _shrink_to_close_predict, select_inside=True)
    if res.select_inside is not True:
        return None
    pm = np.array([r["p_model"] for r in res.records], dtype=float)
    pc = np.array([r["p_close"] for r in res.records], dtype=float)
    y = np.array([r["y"] for r in res.records], dtype=float)
    gid = [r["game_id"] for r in res.records]
    return {"pm": pm, "pc": pc, "y": y, "gid": gid}


def evaluate_market(spec: MarketSpec, corpora: Dict[str, Path]) -> MarketResult:
    """Run the REAL gate for a has-close market across all matching corpora and POOL them.

    Pooling several independent corpora is how we satisfy the >=2-corpora rule: a single-fold
    lift is an artifact. For has_close=False markets we never run a gate -> NEEDS_FORWARD_CLV.
    """
    if not spec.has_close or spec.builder is None:
        return MarketResult(
            spec.name, spec.bucket, spec.sport, "NEEDS_FORWARD_CLV", needs_forward_clv=True,
            reason=("priceable + calibratable from the sim, but NO real historical close locally "
                    "-> validate only via forward capture (soft-line beats are suggestive, not $)"))
    folds: List[dict] = []
    for cname, root in corpora.items():
        if not (root / "odds.parquet").exists():
            continue
        try:
            states = spec.builder(root)
        except Exception:
            states = []
        g = _gate_one_corpus(states)
        if g is not None:
            folds.append({"corpus": cname, **g})
    if not folds:
        return MarketResult(spec.name, spec.bucket, spec.sport, "DATA_LIMITED",
                            reason="no corpus produced >=MIN_N leak-free states with a devigged close")
    pm = np.concatenate([f["pm"] for f in folds])
    pc = np.concatenate([f["pc"] for f in folds])
    y = np.concatenate([f["y"] for f in folds])
    gid = [g for f in folds for g in f["gid"]]
    n = len(y)
    bss = S.brier_skill_score(pm, pc, y)
    bm, bc = S.brier(pm, y), S.brier(pc, y)
    ece, sharp = S.ece(pm, y), S.sharpness(pm)
    d = (pc - y) ** 2 - (pm - y) ** 2          # close loss - model loss (>0 => model better)
    dm = diebold_mariano(d, gid)
    n_corp = len(folds)
    ship = (bss > MATCH_BSS) and (dm.p_value < ALPHA) and (n >= MIN_N) and (n_corp >= MIN_CORPORA)
    if ship:
        verdict, reason = "SHIP", (
            f"BEATS the soft close (BSS={bss:.4f}, clustered DM p={dm.p_value:.4f}, n={n}, "
            f"corpora={n_corp}) -- SUGGESTIVE, needs forward CLV to claim $")
        nfc = True
    elif abs(bss) <= MATCH_BSS:
        verdict, reason = "MATCH", (
            f"MATCHES the close within noise (BSS={bss:+.4f}) -- efficient mainline, honest null")
        nfc = False
    else:
        verdict, reason = "REJECT", (
            f"does NOT beat the close (BSS={bss:+.4f}, DM p={dm.p_value:.4f}, corpora={n_corp}) "
            "-- single-fold/insignificant lift is an artifact")
        nfc = False
    return MarketResult(spec.name, spec.bucket, spec.sport, verdict, n=n, n_corpora=n_corp,
                        bss=float(bss), brier_model=float(bm), brier_close=float(bc),
                        ece=float(ece), sharpness=float(sharp), dm_p=float(dm.p_value),
                        dm_stat=float(dm.dm_stat), reason=reason, needs_forward_clv=nfc)


def _default_corpora() -> Dict[str, Path]:
    base = _REPO / "data" / "domains"
    env = os.environ.get("PROOF_CORPUS_ROOT")
    if env:
        base = Path(env)
    return {"nba": base / "basketball_nba", "mlb": base / "mlb",
            "soccer": base / "soccer"}


def hunt(corpora: Optional[Dict[str, Path]] = None) -> List[MarketResult]:
    """Run the full edge-hunt over every enumerated market; RANK by model-beats-soft-line.

    Ranking key: SHIP first, then by BSS desc, then DM p asc, then N desc. NEEDS_FORWARD_CLV /
    MATCH / DATA_LIMITED sort below any real gate result -- they are not (and cannot be) survivors.
    """
    corpora = corpora or _default_corpora()
    by_sport: Dict[str, Dict[str, Path]] = {}
    for name, root in corpora.items():
        by_sport.setdefault(name, {})[name] = root
    results: List[MarketResult] = []
    for spec in enumerate_markets():
        if spec.has_close:
            # a moneyline market scores against ITS sport's corpus; pool same-family corpora
            relevant = {k: v for k, v in corpora.items() if k == spec.sport}
            results.append(evaluate_market(spec, relevant or corpora))
        else:
            results.append(evaluate_market(spec, {}))
    rank = {"SHIP": 0, "MATCH": 2, "REJECT": 3, "NEEDS_FORWARD_CLV": 4, "DATA_LIMITED": 5}
    results.sort(key=lambda r: (rank.get(r.verdict, 9), -r.bss, r.dm_p, -r.n))
    return results


def _main() -> int:
    res = hunt()
    buckets = {b: [] for b in BUCKETS}
    for r in res:
        buckets.setdefault(r.bucket, []).append(r)
    print("=== OBSCURE-MARKET EDGE-FINDER -- model vs the (often soft) close ===")
    print(f"{'market':>26}  {'bucket':>22}  {'verdict':>17}  {'BSS':>8}  {'DMp':>6}  {'N':>5}")
    for r in res:
        bss = f"{r.bss:+.4f}" if r.verdict in ("SHIP", "MATCH", "REJECT") else "   -    "
        dmp = f"{r.dm_p:.3f}" if r.verdict in ("SHIP", "MATCH", "REJECT") else "  -   "
        n = str(r.n) if r.n else "  -  "
        print(f"{r.name:>26}  {r.bucket:>22}  {r.verdict:>17}  {bss:>8}  {dmp:>6}  {n:>5}")
    ships = [r for r in res if r.verdict == "SHIP"]
    nfc = [r for r in res if r.verdict == "NEEDS_FORWARD_CLV"]
    print(f"\nSHIP (soft-line beats, SUGGESTIVE -- need forward CLV): {len(ships)}")
    print(f"NEEDS_FORWARD_CLV (priceable, no local close, cannot ship here): {len(nfc)}")
    print("HONEST RAIL: no obscure market can SHIP without a real close; soft-line in-sample")
    print("beats are SUGGESTIVE only, never a $ claim; real $ capped by book limits.")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
