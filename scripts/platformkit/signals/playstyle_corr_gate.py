"""scripts.platformkit.signals.playstyle_corr_gate -- the CORRECT validation gate for
archetype/playstyle-conditioned correlation specs (the gap Wave 3 documented).

PROTOCOL OF RECORD (memory: project_playstyle_correlation_edge + feedback_retro_full_
surface_validation + the gated CV_ARCHETYPE_CORR). A `playstyle_corr` spec conditions a
stat-pair residual CORRELATION on an archetype NAME. Validated by: (1) bind the spec's
archetype NAME to AS-OF leak-free MEMBERSHIP (a slowly-varying player TRAIT label, NOT a
per-game season-final predictor; planted-null controls for it; unresolved -> NOT-BINDABLE,
never forced); (2) leak-free residual = actual - pregame OOF (player-mean fallback) ->
co-movement around expectation; (3) the FULL real stat-pair surface (all C(7,2)=21 pts/reb/
ast/fg3m/stl/blk/tov pairs, NEVER a cherry-picked pair, NEVER the registry-leaf "pairs");
(4) SPLIT-HALF stable; (5) CROSS-CORPUS(>=2) BOTH directions (disjoint game partitions A,B;
A->B AND B->A); (6) CELL-LEVEL LABEL-PERMUTATION null clustered BY PLAYER (shuffle the archetype LABEL across
whole-player blocks, recompute the IN-CELL correlation on a random equal-size player set, cell
size held fixed -> tests CONDITIONING; the prior game-membership permutation was invariant to a
true same-player correlation and merely tracked archetype game-coverage); (7) FWER/Bonferroni
across ALL K cells; (8) a family PLANTED-NULL (shuffled labels) that MUST reject (else FREEZE).

VERDICT: REPLICATED-STABLE (a STABLE archetype-conditioned correlation = JOINT/CORRELATION-
PRICING structure, explicitly NOT a $ or marginal-prediction edge) vs REJECT. HONEST EXPECTATION:
most/all REJECT. scheme_prior / archetype_matchup do not map onto this same-
player surface -> NOT-YET-BINDABLE (not forced). INVARIANTS: never edits MEMORY.md / writes
data/registry/ / flips a flag-sentinel / serves a signal / builds a candidate. Calibration
NOT edge (no $/pnl/roi field). Read-only over data/cache + data/models. ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.improve.candidate_families import FAMILY_PLAYSTYLE_CORR

logger = logging.getLogger("playstyle_corr_gate")

# The FULL real stat-pair surface (NOT registry-leaf name-pairs).
_STATS: Tuple[str, ...] = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
_STAT_PAIRS: Tuple[Tuple[str, str], ...] = tuple(
    tuple(sorted(p)) for p in combinations(_STATS, 2))  # 21 pairs

# Resolve a vault archetype NAME (slug) to a corpus rule-based archetype label by keyword.
# Name-stable: keyed on descriptive tokens, never a KMeans cluster-id.
_NAME_TO_CORPUS: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (("playmak", "lead_guard", "initiator", "primary_init", "high_ast"), "HIGH_AST_PLAYMAKER"),
    (("pnr", "ball", "creator", "high_usage_creator", "high_usage_shot"), "PNR_BALLHANDLER"),
    (("iso", "high_usage_scor", "scoring_guard"), "ISO_SCORER"),
    (("post", "interior_scor", "playmaking_big", "dominant_two_way"), "POST_UP_BIG"),
    (("rim_running", "rim_roll", "rebounding_big", "big"), "RIM_ROLL_BIG"),
    (("spot", "floor_spacing", "movement_shoot", "stretch", "shooter"), "SPOT_UP_SHOOTER"),
    (("3_and_d", "3_d", "3d", "wing", "role_player", "low_usage", "connector",
      "bench", "versatile_forward"), "THREE_AND_D_WING"),
    (("defensive_anchor", "anchor"), "RIM_ROLL_BIG"),
)

# Gate thresholds (calibration honesty stack): min pooled obs / split-half tol / perm count
# / base alpha (Bonferroni / K) / cross-corpus tol / min |r| to be a non-trivial cell.
_MIN_OBS_PER_CELL, _SPLITHALF_TOL, _PERM_N = 200, 0.15, 400
_ALPHA, _CROSS_TOL, _MIN_ABS_R = 0.05, 0.15, 0.05


@dataclass(frozen=True)
class CellResult:
    archetype: str
    pair: Tuple[str, str]
    n_obs: int
    r_all: float; r_a: float; r_b: float; r_early: float; r_late: float  # noqa: E702
    perm_p: float
    splithalf_stable: bool; cross_both: bool; significant_raw: bool  # noqa: E702


@dataclass(frozen=True)
class SpecVerdict:
    candidate_id: str
    archetype_name: str
    corpus_archetype: Optional[str]
    bindable: bool
    verdict: str                 # REPLICATED-STABLE | REJECT | NOT-BINDABLE
    n_cells_tested: int
    n_cells_survive: int
    fwer_threshold: float
    survivor_cells: Tuple[CellResult, ...] = ()
    note: str = "correlation/joint-pricing, not a $ edge"


def _load_corpus():
    """Real player-game residual + AS-OF archetype-membership corpus (or None on cold
    start). Leak-free de-trend by pregame OOF lives in playstyle_corr_corpus.load_corpus."""
    from scripts.platformkit.signals.playstyle_corr_corpus import load_corpus
    return load_corpus()


def _pearson(x: np.ndarray, y: np.ndarray) -> float:
    mask = np.isfinite(x) & np.isfinite(y)
    if int(mask.sum()) < 10:
        return float("nan")
    xm = x[mask] - x[mask].mean()
    ym = y[mask] - y[mask].mean()
    den = float(np.sqrt((xm ** 2).sum() * (ym ** 2).sum()))
    return float(np.dot(xm, ym) / den) if den > 1e-12 else float("nan")


def _label_perm_p(sub, ra: str, rb: str, r_obs: float, *, n_perm: int,
                  seed: int) -> float:
    """Label-permutation null at the CELL level, clustered BY PLAYER (must-fix: the prior
    game-membership permutation was invariant to a true same-player archetype-conditioned
    correlation -> it could NEVER ship a real cell and was mechanically driven by archetype
    game-COVERAGE). Here we shuffle the archetype LABEL across PLAYERS (whole-player blocks,
    preserving same-player row clustering), recompute the IN-CELL correlation on the relabeled
    in-cell set holding the in-cell player COUNT fixed, and ask: does THIS archetype's in-cell
    |r| exceed the |r| of a RANDOM equal-size set of players? If the conditioning is real, the
    real label beats the shuffled labels (small p); if the co-movement is a subset/role artifact
    that any equal-size player set inherits, the shuffled labels match it (p -> ~1)."""
    x = sub[ra].to_numpy(float)
    y = sub[rb].to_numpy(float)
    pids = sub["player_id"].to_numpy()
    in_cell = sub["_in_cell"].to_numpy(bool)
    # players in-cell (fixed-size draw) vs the full player universe.
    cell_players = np.unique(pids[in_cell])
    all_players = np.unique(pids)
    k = int(len(cell_players))
    if k == 0 or k >= len(all_players):
        return 1.0
    abs_obs = abs(r_obs)
    rng = np.random.default_rng(seed)
    ge = 1  # +1 for the observed (conservative, never zero)
    for _ in range(n_perm):
        # relabel: choose k random players as the "in-cell" set, holding cell size fixed.
        chosen = set(all_players[rng.permutation(len(all_players))[:k]])
        sel = np.isin(pids, list(chosen))
        rp = _pearson(x[sel], y[sel])
        if np.isfinite(rp) and abs(rp) >= abs_obs:
            ge += 1
    return ge / float(n_perm + 1)


def _eval_cell(corpus, archetype: str, pair: Tuple[str, str], *, seed: int,
               n_perm: int) -> Optional[CellResult]:
    sa, sb = pair
    ra, rb = "resid_%s" % sa, "resid_%s" % sb
    sub = corpus.copy()
    sub["_in_cell"] = sub["archetype"] == archetype
    cell = sub[sub["_in_cell"]]
    x = cell[ra].to_numpy(float)
    y = cell[rb].to_numpy(float)
    n_obs = int((np.isfinite(x) & np.isfinite(y)).sum())
    if n_obs < _MIN_OBS_PER_CELL:
        return None
    r_all = _pearson(x, y)
    if not np.isfinite(r_all):
        return None
    def _r2(mask):  # pearson on a boolean-masked slice of `cell`
        s = cell[mask]
        return _pearson(s[ra].to_numpy(float), s[rb].to_numpy(float))
    r_a = _r2(cell["corpus"] == "A")
    r_b = _r2(cell["corpus"] == "B")
    med = cell["game_date"].median()
    r_e = _r2(cell["game_date"] <= med)
    r_l = _r2(cell["game_date"] > med)
    splithalf = bool(np.isfinite(r_e) and np.isfinite(r_l)
                     and (np.sign(r_e) == np.sign(r_l)
                          or (abs(r_e) < 0.05 and abs(r_l) < 0.05))
                     and abs(r_e - r_l) <= _SPLITHALF_TOL)
    cross_both = bool(np.isfinite(r_a) and np.isfinite(r_b)
                      and np.sign(r_a) == np.sign(r_b)
                      and abs(r_a - r_b) <= _CROSS_TOL
                      and abs(r_a) >= _MIN_ABS_R and abs(r_b) >= _MIN_ABS_R)
    perm_p = _label_perm_p(sub, ra, rb, r_all, n_perm=n_perm, seed=seed)
    _r = lambda v: round(v, 4) if np.isfinite(v) else float("nan")  # noqa: E731
    return CellResult(
        archetype=archetype, pair=pair, n_obs=n_obs, r_all=_r(r_all),
        r_a=_r(r_a), r_b=_r(r_b), r_early=_r(r_e), r_late=_r(r_l),
        perm_p=round(perm_p, 5), splithalf_stable=splithalf, cross_both=cross_both,
        significant_raw=(perm_p < _ALPHA))


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_") or "x"


def resolve_archetype(name_or_slug: str) -> Optional[str]:
    """Map a vault archetype NAME (or its slug) to a corpus rule-based archetype label.
    Returns None when no keyword matches (-> spec is honestly NOT-BINDABLE, not forced)."""
    s = _slug(name_or_slug)
    for toks, corpus_arch in _NAME_TO_CORPUS:
        if any(t in s for t in toks):
            return corpus_arch
    return None


def parse_spec_archetype(signature: str) -> Optional[str]:
    """Extract the archetype slug from a playstyle_corr spec signature."""
    m = re.match(r"playstyle_corr=arch:(.+?)\|pair:", str(signature))
    return m.group(1) if m else None


def fwer_threshold(k_tests: int, alpha: float = _ALPHA) -> float:
    """Bonferroni threshold: alpha / K. Wider search (larger K) -> stricter bar."""
    return alpha / float(max(int(k_tests), 1))


def _count_fwer_survivors(corpus, arches, thr: float, *, n_perm: int, seed: int) -> int:
    """Cells passing split-half + cross-corpus-both-dirs + game-clustered-perm < thr."""
    n = 0
    for ci, ca in enumerate(arches):
        for pi, pair in enumerate(_STAT_PAIRS):
            r = _eval_cell(corpus, ca, pair, seed=seed + 31 * ci + pi, n_perm=n_perm)
            if r is not None and r.splithalf_stable and r.cross_both and r.perm_p < thr:
                n += 1
    return n


def planted_null_survivors(corpus, arches, thr: float, *, n_perm: int, seed: int) -> int:
    """FROZEN-family tripwire: shuffle archetype labels ACROSS PLAYERS, recount FWER
    survivors. If a shuffled-label corpus still yields survivors, the per-cell test detects
    subset structure (not archetype conditioning) -> the family FREEZES. The planted null
    MUST reject (yield ~0) for any real spec to ship."""
    rng = np.random.default_rng(seed + 9001)
    players = corpus[["player_id", "archetype"]].drop_duplicates("player_id")
    pmap = dict(zip(players["player_id"].to_numpy(),
                    rng.permutation(players["archetype"].to_numpy())))
    null = corpus.copy()
    null["archetype"] = null["player_id"].map(pmap)
    return _count_fwer_survivors(null, sorted(null["archetype"].dropna().unique()),
                                 thr, n_perm=n_perm, seed=seed)


def run_playstyle_corr_gate(specs: Sequence, *, corpus=None, n_perm: int = _PERM_N,
                            seed: int = 1234) -> Tuple[List[SpecVerdict], Dict[str, object]]:
    """Run playstyle_corr specs through the validation-of-record. Returns
    (per-spec verdicts, summary dict). corpus=None loads the on-disk corpus; a missing
    corpus -> every spec NOT-BINDABLE (cold start, never fabricated)."""
    ps = [s for s in specs if getattr(s, "family", None) == FAMILY_PLAYSTYLE_CORR]
    if corpus is None:
        corpus = _load_corpus()

    def _nb(s, thr):  # NOT-BINDABLE verdict factory
        return SpecVerdict(candidate_id=_slug(s.signature),
                           archetype_name=parse_spec_archetype(s.signature) or "?",
                           corpus_archetype=None, bindable=False, verdict="NOT-BINDABLE",
                           n_cells_tested=0, n_cells_survive=0, fwer_threshold=thr)

    if corpus is None or len(corpus) == 0:
        return [_nb(s, 0.0) for s in ps], {"corpus_present": False, "n_specs": len(ps)}

    # bind each spec's archetype NAME -> corpus archetype; unresolved -> NOT-BINDABLE.
    bind = {s.signature: (resolve_archetype(parse_spec_archetype(s.signature))
                          if parse_spec_archetype(s.signature) else None) for s in ps}
    corpus_arches = sorted({c for c in bind.values() if c is not None})

    # evaluate every (corpus_archetype x FULL stat-pair) cell ONCE; K = total cells tested.
    cells: Dict[Tuple[str, Tuple[str, str]], CellResult] = {}
    for ci, ca in enumerate(corpus_arches):
        for pi, pair in enumerate(_STAT_PAIRS):
            res = _eval_cell(corpus, ca, pair, seed=seed + 31 * ci + pi, n_perm=n_perm)
            if res is not None:
                cells[(ca, pair)] = res
    k_tests = len(cells)
    thr = fwer_threshold(k_tests)

    # FAMILY PLANTED-NULL TRIPWIRE (decisive): a shuffled-label corpus must yield ~0 FWER
    # survivors; any survivors => subset-structure artifact, not conditioning => FREEZE.
    null_surv = planted_null_survivors(corpus, corpus_arches, thr, n_perm=n_perm, seed=seed)
    family_frozen = null_surv > 0  # planted null MUST reject (yield zero) to allow a ship.

    verdicts: List[SpecVerdict] = []
    for s in ps:
        a_name = parse_spec_archetype(s.signature) or "?"
        ca = bind[s.signature]
        if ca is None:
            verdicts.append(_nb(s, thr))
            continue
        my = [cells[(ca, p)] for p in _STAT_PAIRS if (ca, p) in cells]
        survivors = tuple(c for c in my if c.splithalf_stable and c.cross_both
                          and c.perm_p < thr)
        # A spec ships ONLY if it has a per-cell survivor AND the family is not frozen.
        verdict = "REPLICATED-STABLE" if (survivors and not family_frozen) else "REJECT"
        verdicts.append(SpecVerdict(
            candidate_id=_slug(s.signature), archetype_name=a_name, corpus_archetype=ca,
            bindable=True, verdict=verdict, n_cells_tested=len(my),
            n_cells_survive=len(survivors), fwer_threshold=thr, survivor_cells=survivors))

    dist: Dict[str, int] = {}
    for v in verdicts:
        dist[v.verdict] = dist.get(v.verdict, 0) + 1
    summary = {"corpus_present": True, "n_specs": len(ps), "n_corpus_rows": int(len(corpus)),
               "k_cells_tested": k_tests, "fwer_threshold": thr,
               "corpus_archetypes": corpus_arches, "verdict_distribution": dist,
               "planted_null_survivors": null_surv, "family_frozen": family_frozen,
               "planted_null_rejects": (null_surv == 0)}
    return verdicts, summary


__all__ = [
    "CellResult", "SpecVerdict", "run_playstyle_corr_gate", "resolve_archetype",
    "parse_spec_archetype", "fwer_threshold", "planted_null_survivors",
    "_STAT_PAIRS", "_load_corpus"]
