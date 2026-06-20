"""scripts.platformkit.ingame.ingame_gate_generic -- SPORT-AGNOSTIC in-game
DETAIL-LAYER gate: does a pregame-prior layer beat a (state,elapsed) BASE model on
held-out Brier, replicated cross-corpus? Generalizes the PROVEN NBA result so MLB /
soccer / tennis plug in with ZERO re-derivation.

THE QUESTION (sport-blind): given as-of in-game states
  {sport, game_id, asof_idx, state_diff (signed, + favors ref side), frac_elapsed in
   [0,1], p0 (leak-free pregame P(ref win)), outcome in {0,1}},
does adding the pregame prior p0 as a DETAIL LAYER beat a BASE win-prob model built
from (state_diff, frac_elapsed) ALONE, on held-out Brier, in BOTH cross-corpus
directions (A->B and B->A)?

TWO MODELS (everything fit on TRAIN only -- never the test corpus):
  BASE   = sigmoid((a + b*frac_elapsed) * state_diff)   # (state,time) only, NO prior
           a,b FIT per corpus by Brier on TRAIN -> works for run-diff / goal-diff /
           point-diff scales (NO basketball slope hardcoded).
  +PRIOR = blend(p0, p_live=BASE, w(time,margin))        # w fit on TRAIN (eval_gate)
           margin-bucket edges are DERIVED from the train state_diff scale, so a
           +/-1..3 goal-diff corpus and a +/-10 point corpus both bucket sanely.

DISCIPLINE (hard-learned):
  * TRUE cross-corpus: fit on ALL of A, test on held-out B (and reverse) -- disjoint
    games, leak-free by construction.
  * DM CLUSTERED BY game_id (CRITICAL): many states per game; per-state iid SE inflates
    significance (the NBA run showed a ~3.3x shrink under clustering).
  * REPLICATED iff +PRIOR<BASE Brier AND DM p<eps in BOTH directions; PARTIAL if one;
    REJECT/NOT_REPLICATED if neither. INSUFFICIENT_DATA if a corpus is too thin.
  * GRACEFUL DEGRADE: a constant / missing p0 is a noise prior -- the weight surface
    fits w->0 (trust BASE), so +PRIOR can only MATCH BASE, never beat it -> REJECT.

NO $ anywhere; verdict is CALIBRATION (Brier), never a market edge.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + stdlib.
CLI: python -m scripts.platformkit.ingame.ingame_gate_generic <sport>
"""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# fit_base + cross_direction are re-exported here (the offline test imports them from
# this module); cross_direction's scoring math lives in ingame_gate_generic_models
# (sibling-split for <=300 LOC).
from scripts.platformkit.ingame.ingame_gate_generic_models import (
    cross_direction,
    fit_base,
    load_states,
)

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_STATE_DIR = os.path.join(_REPO, "data", "cache", "ingame")
_OUT_DIR = os.path.join(_REPO, "data", "frontend", "ingame")

# Minimum games that qualify a corpus as "rich enough" to overwrite a production verdict.
_MIN_GAMES_TO_OVERWRITE = 50


def _existing_verdict_games(path: str) -> int:
    """Return the total games in an existing verdict file (sum of a+b coverage), or 0."""
    try:
        with open(path, encoding="ascii") as f:
            d = json.load(f)
        cov = d.get("coverage", {})
        return int(cov.get("a_games", 0)) + int(cov.get("b_games", 0))
    except (OSError, ValueError, KeyError):
        return 0


def _should_skip_write(v: "GenericVerdict", out: str) -> bool:
    """Return True when this run is thin/insufficient AND an existing richer file is present.

    A thin/INSUFFICIENT_DATA run (or any run with < _MIN_GAMES_TO_OVERWRITE total games)
    must NOT clobber a production verdict file that already has a richer verdict. Tests and
    offline/sandbox runs should inject a different out_dir rather than writing here.
    """
    new_games = (v.coverage.get("a_games", 0) + v.coverage.get("b_games", 0))
    thin = v.verdict == "INSUFFICIENT_DATA" or new_games < _MIN_GAMES_TO_OVERWRITE
    if not thin:
        return False  # rich run -> always write
    if not os.path.exists(out):
        return False  # no existing file -> safe to create even if thin
    existing_games = _existing_verdict_games(out)
    if existing_games > new_games:
        return True   # existing file is richer -> skip
    return False


# --------------------------------------------------------------------------- verdict
@dataclass
class GenericVerdict:
    verdict: str
    sport: str = ""
    a_to_b: Dict = field(default_factory=dict)
    b_to_a: Dict = field(default_factory=dict)
    coverage: Dict = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict, "sport": self.sport,
            "layer": "pregame_prior",
            "base_model": "sigmoid((a+b*frac_elapsed)*state_diff); a,b FIT per corpus",
            "prior_model": "blend(p0, BASE, w(time,margin)); w fit on TRAIN only",
            "design": "true cross-corpus A<->B; DM clustered by game_id",
            "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
            "a_to_b": self.a_to_b, "b_to_a": self.b_to_a,
            "coverage": self.coverage, "caveats": list(self.caveats),
        }


def decide(a_to_b: Dict, b_to_a: Dict) -> str:
    """Honest replication verdict over both cross-corpus directions.

    HONESTY GUARD: if EITHER direction's BASE is degenerate (a vacuous (state,time)
    model that barely beats a constant base-rate), there is NO in-game state result
    for the prior to improve -- a "+PRIOR beats BASE" there is a trivial prior-beats-
    coinflip, not an in-game conditioning win. So the verdict can NEVER be REPLICATED:
    it is at most INVALID_BASE (if no direction has a genuine non-degenerate beat) or
    PARTIAL (if the OTHER, non-degenerate direction is a genuine beat).
    """
    a, b = bool(a_to_b.get("prior_beats_base")), bool(b_to_a.get("prior_beats_base"))
    degen = bool(a_to_b.get("base_degenerate")) or bool(b_to_a.get("base_degenerate"))
    if degen:
        # a genuine beat can only come from a NON-degenerate direction
        return "PARTIAL" if (a or b) else "INVALID_BASE"
    if a and b:
        return "REPLICATED"
    if a or b:
        return "PARTIAL"
    return "REJECT"


def _thin(states: List[dict], min_ticks: int) -> bool:
    games = len({s["game_id"] for s in states})
    return len(states) < min_ticks or games < 8


def gate_cross(states_a: List[dict], states_b: List[dict], *, min_ticks: int = 200,
               eps: float = 0.05, sport: str = "",
               caveats: Optional[List[str]] = None) -> GenericVerdict:
    """Run A->B and B->A cross-corpus; return an honest replication verdict.

    INSUFFICIENT_DATA (honest) if either corpus is too thin to gate reliably.
    """
    cov = {
        "a_states": len(states_a), "a_games": len({s["game_id"] for s in states_a}),
        "b_states": len(states_b), "b_games": len({s["game_id"] for s in states_b}),
    }
    if _thin(states_a, min_ticks) or _thin(states_b, min_ticks):
        return GenericVerdict("INSUFFICIENT_DATA", sport, {}, {}, cov,
                              list(caveats or []) + ["corpus too thin to gate"])
    a_to_b = cross_direction(states_a, states_b, eps=eps)
    b_to_a = cross_direction(states_b, states_a, eps=eps)
    cav = list(caveats or [])
    if a_to_b.get("base_degenerate") or b_to_a.get("base_degenerate"):
        cav.append(
            "HONESTY GUARD tripped: a BASE direction is DEGENERATE -- the (state,time) "
            "model barely beats a constant base-rate (near-zero slope / BSS), so any "
            "+PRIOR 'beat' there is a prior-beats-coinflip, NOT an in-game conditioning "
            "win. Verdict capped below REPLICATED; the in-game state model is vacuous "
            "for this corpus (data-limited).")
    return GenericVerdict(decide(a_to_b, b_to_a), sport, a_to_b, b_to_a, cov, cav)


# --------------------------------------------------------------------------- CLI
def _find_corpora(sport: str) -> List[str]:
    return sorted(glob.glob(os.path.join(_STATE_DIR, f"{sport}_states__*.parquet")))


def _dir_report(name: str, d: Dict) -> List[str]:
    if not d:
        return [f"  {name}: (none)"]
    lines = [
        f"  {name}: train n={d.get('n_train_states')} -> test n={d.get('n_test_states')}"
        f" ({d.get('n_test_games')} games)  base_slope={d.get('base_slope')}",
        f"    pooled OOS Brier : BASE {d.get('brier_base')}  +PRIOR {d.get('brier_prior')}"
        f"  (delta {d.get('brier_delta')})",
        f"    DM (clustered)   : stat {d.get('dm_stat')}  p {d.get('dm_p')}",
        f"    prior_beats_base : {d.get('prior_beats_base')}   "
        f"early_helps_most : {d.get('early_helps_most')}",
    ]
    chk = d.get("base_check") or {}
    if chk:
        lines.append(
            f"    base honesty     : degenerate={d.get('base_degenerate')}  "
            f"eff_slope={chk.get('eff_slope')}  base_BSS_vs_baserate="
            f"{chk.get('base_bss_vs_baserate')}  (base {chk.get('base_brier')} vs "
            f"baserate {chk.get('baserate_brier')})")
    for k in ("t0", "t1", "t2", "t3"):
        r = (d.get("elapsed_breakdown") or {}).get(k)
        if r:
            lines.append(f"      {k} n={r['n']:6d}  base {r['brier_base']:.4f} -> "
                         f"prior {r['brier_prior']:.4f}  delta {r['delta']:+.5f}")
    return lines


def _report(v: GenericVerdict) -> str:
    c = v.coverage
    lines = ["=" * 72,
             f"IN-GAME DETAIL-LAYER GENERIC GATE [{v.sport}]: pregame prior vs base",
             "=" * 72, f"VERDICT  : {v.verdict}",
             f"coverage : A {c.get('a_games')} games / {c.get('a_states')} states ; "
             f"B {c.get('b_games')} games / {c.get('b_states')} states", "-" * 72]
    lines += _dir_report("A->B", v.a_to_b)
    lines.append("-" * 72)
    lines += _dir_report("B->A", v.b_to_a)
    lines.append("=" * 72)
    return "\n".join(lines)


def run(sport: str, out_dir: Optional[str] = None) -> GenericVerdict:
    """Find the sport's two corpora, run gate_cross, write data/frontend/ingame JSON.

    out_dir: override the production _OUT_DIR (inject in tests/offline runs to keep
    thin/synthetic verdicts out of the real data/frontend/ingame path). When out_dir is
    None, the production path is used and a thin run (INSUFFICIENT_DATA or < 50 games)
    will NOT clobber an existing richer verdict file.
    """
    paths = _find_corpora(sport)
    caveats = [
        "True cross-corpus: BASE slope (a,b) and blend surface w fit on the WHOLE train "
        "corpus, tested on the held-out OTHER corpus -- leak-free by construction.",
        "BASE slope FIT per corpus (scale-normalized) -- works for run/goal/point-diff; "
        "NO basketball constant.",
        "DM clustered by game_id -- per-state iid SE would over-state significance.",
        "No in-play odds -> verdict is CALIBRATION (held-out Brier) vs a (state,time) "
        "BASE, never a market edge. No $ anywhere.",
    ]
    if len(paths) < 2:
        v = GenericVerdict("INSUFFICIENT_DATA", sport, {}, {},
                           {"corpora_found": len(paths)},
                           caveats + [f"need 2 corpora at {_STATE_DIR}; found {len(paths)}"])
    else:
        a, b = load_states(paths[0]), load_states(paths[1])
        v = gate_cross(a, b, sport=sport, caveats=caveats)
    target_dir = out_dir if out_dir is not None else _OUT_DIR
    os.makedirs(target_dir, exist_ok=True)
    out = os.path.join(target_dir, f"gate_{sport}.json")
    # WRITE-GUARD: never clobber a richer production verdict with a thin/INSUFFICIENT run.
    # Tests/offline callers must use out_dir (a tmp path) instead of the production dir.
    if out_dir is None and _should_skip_write(v, out):
        print(f"WRITE-GUARD: thin run ({v.verdict}, "
              f"{v.coverage.get('a_games', 0) + v.coverage.get('b_games', 0)} games) "
              f"did NOT overwrite richer production file: {out}")
        return v
    with open(out, "w", encoding="ascii") as f:
        json.dump(v.to_dict(), f, indent=2, sort_keys=True)
    print(_report(v))
    print(f"wrote {out}")
    return v


def main() -> None:
    import sys
    run(sys.argv[1] if len(sys.argv) > 1 else "nba")


if __name__ == "__main__":
    main()
