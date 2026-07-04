"""scripts.platformkit.l4.context_gate -- L4 LLM-context pre-registration gate.

PRE-REGISTRATION DISCIPLINE (mirrors the tail gates, see kalshi_tail_validation.py /
ingame_tail_gate.py): this gate is built and frozen BEFORE any LLM-context layer is
wired to predictions. It is a fixture-driven evaluator for ANY future L4 layer --
"LLM-extracted context (injuries/lineups/news) improves in-game repricing" -- and it
is the ONLY door a context layer may walk through to reach predictions. Charter (lane
v): L4 = in-game repricing first; a MANDATORY shuffled-context PLANTED-NULL runs on
every eval; ANY fail routes the layer to SCOUTING_ONLY, never wired to predictions.

INPUT CONTRACT (the only shape this module accepts):
    rows: List[dict], each row one (game, as-of-timestamp) observation:
        game_id      : str|int   -- unique per game
        state_ts     : str|int   -- in-game as-of timestamp/tick (for provenance only;
                                    not used in scoring -- one row per (game_id, state_ts))
        base_prob    : float in [0,1]  -- current model's probability (no context)
        context_prob : float in [0,1]  -- LLM-context-conditioned probability
        context_id   : str|int   -- identifies which context artifact produced context_prob
                                    (provenance only; not scored)
        outcome      : int in {0,1}    -- realized binary result for this game

No LLM calls anywhere in this module -- harness + fixtures only. Every number the gate
prints must be recomputable from `rows` alone; nothing here estimates or recalls a
basketball fact -- rows not meeting the sample floors are EXCLUDED and counted, not
guessed.

SCORING:
  (a) Brier delta = brier(base_prob) - brier(context_prob), per-game CLUSTERED bootstrap
      (each resample draws whole games, all that game's rows travel together) -> 95% CI.
      Positive delta = context reduces Brier (context "improves" on base).
  (b) PLANTED-NULL: context_prob values are SHUFFLED ACROSS GAMES (a fixed permutation of
      games, not of rows within a game -- preserves within-game structure, destroys the
      game-level link between context and outcome) and the IDENTICAL scoring is re-run.
      The permutation seed is DERIVED FROM ROW CONTENT (a stable hash of the sorted
      game_ids), never from `random` at runtime or wall-clock -- reruns on the same rows
      always shuffle identically, so the null is reproducible and auditable.
      If the shuffled variant ALSO shows a CI-positive Brier delta, the "improvement" is a
      flexibility/leak artifact, not real skill -> PLANTED_NULL_FAIL -> label SCOUTING_ONLY.
  (c) verdict vocabulary (exactly one, in this priority order):
      INSUFFICIENT       -- below the pre-registered sample floors (see PREREG_FLOORS)
      PLANTED_NULL_FAIL  -- shuffled variant also CI-positive -> SCOUTING_ONLY, never wired
      ADDS_SKILL         -- real CI positive AND planted-null CI not positive
      NO_ADD              -- real CI not positive (context does not beat base)

INVARIANTS: no LLM calls; no data/registry writes; no flag flips; stdlib + optional numpy
(falls back to pure python if numpy is absent); ASCII only; <=300 LOC.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/l4/test_context_gate.py -q
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Pre-registered floors (mirror the JSON stamp in data/frontend/ops/l4_gate_prereg.json).
# Any change to these numbers must be re-pre-registered, not silently edited.
# ---------------------------------------------------------------------------
MIN_GAMES = 30
MIN_ROWS = 300
BOOTSTRAP_ITERS = 2000

VERDICT_INSUFFICIENT = "INSUFFICIENT"
VERDICT_NO_ADD = "NO_ADD"
VERDICT_ADDS_SKILL = "ADDS_SKILL"
VERDICT_PLANTED_NULL_FAIL = "PLANTED_NULL_FAIL"

_REQUIRED_KEYS = ("game_id", "state_ts", "base_prob", "context_prob", "context_id", "outcome")


@dataclass(frozen=True)
class GateResult:
    """Full result of one context_gate.evaluate() call -- every field traceable to rows."""

    verdict: str
    label: str                      # "SCOUTING_ONLY" or "" (empty = eligible to progress)
    n_games: int
    n_rows: int
    n_excluded_rows: int
    real_delta: float
    real_ci95: Tuple[float, float]
    null_delta: float
    null_ci95: Tuple[float, float]
    seed_used: int
    edge_claimed: bool = False
    note: str = "calibration measurement only; no LLM calls in this gate"
    caveats: List[str] = field(default_factory=list)


def _validate_row(row: Dict[str, Any]) -> bool:
    if not all(k in row for k in _REQUIRED_KEYS):
        return False
    try:
        bp, cp, out = float(row["base_prob"]), float(row["context_prob"]), int(row["outcome"])
    except (TypeError, ValueError):
        return False
    if not (0.0 <= bp <= 1.0 and 0.0 <= cp <= 1.0 and out in (0, 1)):
        return False
    return True


def _clean_rows(rows: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """Split rows into (valid, n_excluded). Excluded rows are COUNTED, never guessed."""
    valid = [r for r in rows if _validate_row(r)]
    return valid, len(rows) - len(valid)


def _derive_seed(game_ids: Sequence[str]) -> int:
    """Deterministic seed from row content (sorted unique game_ids), NOT runtime random.

    Reruns on the identical rows always produce the identical permutation -- this is
    what makes the planted-null reproducible and auditable rather than a fresh roll
    each time. Uses sha256 (stdlib hashlib) truncated to 8 hex chars -> a stable int.
    """
    key = ",".join(sorted(set(str(g) for g in game_ids)))
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _brier(prob: float, outcome: int) -> float:
    return (prob - outcome) ** 2


def _per_game_agg(rows: Sequence[Dict[str, Any]], prob_key: str) -> Dict[str, Tuple[float, int]]:
    """game_id -> (sum of per-row brier deltas base-vs-prob_key, n_rows) for that game."""
    agg: Dict[str, List[float]] = {}
    for r in rows:
        gid = str(r["game_id"])
        out = int(r["outcome"])
        d = _brier(float(r["base_prob"]), out) - _brier(float(r[prob_key]), out)
        agg.setdefault(gid, [0.0, 0])
        agg[gid][0] += d
        agg[gid][1] += 1
    return {g: (s, n) for g, (s, n) in agg.items()}


def _delta_and_ci(rows: Sequence[Dict[str, Any]], prob_key: str, seed: int,
                   iters: int = BOOTSTRAP_ITERS) -> Tuple[float, Tuple[float, float]]:
    """Mean per-row Brier delta (base - prob_key) and its game-clustered bootstrap 95% CI.

    Positive delta means prob_key beats base (lower Brier). Resampling draws WHOLE
    GAMES with replacement so within-game correlation never inflates apparent precision.
    """
    per_game = _per_game_agg(rows, prob_key)
    games = sorted(per_game.keys())
    n_g = len(games)
    total_sum = sum(s for s, _ in per_game.values())
    total_n = sum(n for _, n in per_game.values())
    point = total_sum / total_n if total_n else 0.0

    if n_g == 0:
        return 0.0, (0.0, 0.0)

    rng = random.Random(seed)
    deltas: List[float] = []
    game_stats = [per_game[g] for g in games]
    for _ in range(iters):
        s_tot = n_tot = 0
        s_sum = 0.0
        for _ in range(n_g):
            s, n = game_stats[rng.randrange(n_g)]
            s_sum += s
            n_tot += n
        deltas.append(s_sum / n_tot if n_tot else 0.0)
    deltas.sort()
    lo_i = int(0.025 * iters)
    hi_i = min(int(0.975 * iters), iters - 1)
    return round(point, 6), (round(deltas[lo_i], 6), round(deltas[hi_i], 6))


def _shuffle_context_across_games(rows: Sequence[Dict[str, Any]], seed: int) -> List[Dict[str, Any]]:
    """Return rows with context_prob PERMUTED ACROSS GAMES (whole-game blocks swapped).

    Preserves within-game structure (a game's own sequence of context_prob values moves
    together) while destroying any real game-level link between context and outcome.
    Deterministic given `seed` -- see _derive_seed.
    """
    games = sorted({str(r["game_id"]) for r in rows})
    rng = random.Random(seed)
    shuffled_order = games[:]
    rng.shuffle(shuffled_order)
    game_map = dict(zip(games, shuffled_order))

    by_game: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_game.setdefault(str(r["game_id"]), []).append(r)

    out: List[Dict[str, Any]] = []
    for gid, grows in by_game.items():
        donor_gid = game_map[gid]
        donor_rows = by_game[donor_gid]
        # Pair rows by position within each game's own row list (ties break deterministically
        # by state_ts to avoid depending on input row order).
        own_sorted = sorted(range(len(grows)), key=lambda i: str(grows[i]["state_ts"]))
        donor_sorted = sorted(range(len(donor_rows)), key=lambda i: str(donor_rows[i]["state_ts"]))
        for k, own_idx in enumerate(own_sorted):
            donor_idx = donor_sorted[k % len(donor_sorted)]
            new_row = dict(grows[own_idx])
            new_row["context_prob"] = donor_rows[donor_idx]["context_prob"]
            out.append(new_row)
    return out


def evaluate(rows: Sequence[Dict[str, Any]], *, iters: int = BOOTSTRAP_ITERS,
             min_games: int = MIN_GAMES, min_rows: int = MIN_ROWS) -> GateResult:
    """Run the full L4 pre-registration gate on `rows` (see module docstring for contract).

    Never raises on malformed input rows -- they are validated, excluded, and counted;
    a crash-free conservative path always returns a GateResult.
    """
    valid, n_excluded = _clean_rows(rows)
    n_games = len({str(r["game_id"]) for r in valid})
    n_rows = len(valid)
    caveats: List[str] = []
    if n_excluded:
        caveats.append("%d row(s) excluded for missing/out-of-range fields" % n_excluded)

    if n_games < min_games or n_rows < min_rows:
        caveats.append("floors: min_games=%d min_rows=%d (got games=%d rows=%d)" %
                        (min_games, min_rows, n_games, n_rows))
        return GateResult(verdict=VERDICT_INSUFFICIENT, label="", n_games=n_games,
                           n_rows=n_rows, n_excluded_rows=n_excluded, real_delta=0.0,
                           real_ci95=(0.0, 0.0), null_delta=0.0, null_ci95=(0.0, 0.0),
                           seed_used=0, caveats=caveats)

    seed = _derive_seed([r["game_id"] for r in valid])
    real_delta, real_ci = _delta_and_ci(valid, "context_prob", seed=seed, iters=iters)

    shuffled = _shuffle_context_across_games(valid, seed=seed)
    null_delta, null_ci = _delta_and_ci(shuffled, "context_prob", seed=seed + 1, iters=iters)

    null_positive = null_ci[0] > 0.0
    real_positive = real_ci[0] > 0.0

    if null_positive:
        verdict, label = VERDICT_PLANTED_NULL_FAIL, "SCOUTING_ONLY"
        caveats.append("planted-null (shuffled-context) ALSO CI-positive -> flexibility/"
                        "leak artifact, not real skill; layer routed to SCOUTING_ONLY")
    elif real_positive:
        verdict, label = VERDICT_ADDS_SKILL, ""
    else:
        verdict, label = VERDICT_NO_ADD, ""

    return GateResult(verdict=verdict, label=label, n_games=n_games, n_rows=n_rows,
                       n_excluded_rows=n_excluded, real_delta=real_delta, real_ci95=real_ci,
                       null_delta=null_delta, null_ci95=null_ci, seed_used=seed,
                       caveats=caveats)


def main() -> None:
    print("context_gate: fixture-driven harness -- no default corpus wired (pre-"
          "registration only). Import evaluate(rows) from your own fixture/eval script.")
    print("NOTE: calibration measurement only; no LLM calls in this gate; no edge claimed.")


if __name__ == "__main__":
    main()


__all__ = [
    "GateResult", "evaluate", "MIN_GAMES", "MIN_ROWS", "BOOTSTRAP_ITERS",
    "VERDICT_INSUFFICIENT", "VERDICT_NO_ADD", "VERDICT_ADDS_SKILL", "VERDICT_PLANTED_NULL_FAIL",
]
