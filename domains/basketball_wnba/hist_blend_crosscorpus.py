"""domains.basketball_wnba.hist_blend_crosscorpus -- LANE 3 sub-task (A): refit the
in-game blend family choice using TWO INDEPENDENT, provenance-separated WNBA
states corpora as mutual holdouts (user directive: "use old odds and data to
keep getting better" -- queued since sprint wake 2).

THE GAP THIS CLOSES
-------------------
ingame_blend_families.py already fit+validated the 4 pre-declared families
(fixed/naive/time_scaled/anchored) on a SINGLE data path: linescores.parquet
(ESPN scoreboard API, 2024 train -> 2025 validate -> 2026 OOS). That is one
provenance end-to-end -- a systematic bug in the ESPN scoreboard extraction
would show up identically in all three splits. This module adds a SECOND,
independently-sourced corpus (the CDN boxscore+playbyplay backfill, provenance
"cdn_backfill", a different API + different extraction code path entirely --
see cdn_states_extract.py) and runs the SAME 4 families as a genuine two-way
holdout: fit on corpus A only -> validate OOS on corpus B, then swap roles
(fit on B -> validate on A). A family is adopted here only if it wins EVERY
checkpoint (end_q1/half/end_q3) on THE CORPUS IT WAS NOT FIT ON, in BOTH
directions -- a stronger bar than the single-corpus wake-4 result, which this
module either CONFIRMS (adopt, default-OFF, no flag flip) or REJECTS (record
honestly, no diagram, no code deleted).

CORPUS A (linescores.parquet, provenance="espn_scoreboard" implicit): restrict
to the 2026 season slice (166 games) to match corpus B's single-season 2026
window (Apr 25 - Jul 3) -- pooling 2024/2025 into A would bias the swap
(corpus A would simply be "more data", not "an independent source").
CORPUS B (cdn_backfill_states.parquet, provenance="cdn_backfill"): 168 games x
3 checkpoints = 504 rows shipped wave 14, but that file has NO home_win outcome
column (see cdn_states_extract.py -- extraction was checkpoint-state only). This
module (via hist_blend_corpus_io.py) derives home_win PER GAME directly from
each game's OWN boxscore JSON (game.homeTeam.score / game.awayTeam.score --
the CDN's own final-score field, independent of the linescore/scoreboard path
entirely), and excludes exhibition/national-team legs (Commissioner's Cup
All-Star, Japan/Nigeria friendlies -- 5 of 168 games) since they are not part
of either corpus's franchise Elo ladder.

WHY EACH CORPUS GETS ITS OWN WALK-FORWARD ELO (not one shared rating stream):
corpus A's linescores.parquet event_ids are ESPN numeric ids; corpus B's CDN
game_ids are a disjoint id space (verified: zero overlap) and team names are
recorded in a different string convention (mascot-only "Fever" vs full "Indiana
Fever"). Rather than build a fragile cross-corpus team-name-alias table just to
share one Elo stream, each corpus computes p0 from ITS OWN chronological game
log (both are single-season 2026, so no between-season regression is needed
either way) -- standard, and exactly what makes this a genuine OUT-OF-SAMPLE
test of the FAMILY SHAPE (not a test of shared rating continuity).

HONESTY: EDGE_CLAIMED=False. This is a calibration (Brier) comparison only.
REJECT-on-disagreement is a designed, expected, non-failure outcome.

FILE SPLIT: corpus loading + Row-construction lives in hist_blend_corpus_io.py
(same directory) purely to respect the <=300 LOC/file cap; this module owns
fit/validate/adopt only and imports that module's functions.

INVARIANTS: domains/basketball_wnba/ only; <=300 LOC; ASCII only; no network at
import time (CDN boxscores are read from the already-backfilled local files);
never writes data/registry/; never flips a flag; reuses ingame_blend_families'
predict_* functions verbatim (no reimplementation of the family formulas).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_hist_blend_crosscorpus.py -q
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from domains.basketball_wnba.hist_blend_corpus_io import (
    CDN_BACKFILL_DIR,
    CHECKPOINTS,
    LINESCORES_PARQUET,
    build_rows_corpus_a,
    build_rows_corpus_b,
    load_corpus_a_2026,
    load_corpus_b_games,
    load_corpus_b_states,
    walk_forward_elo_simple as _walk_forward_elo_simple,
)
from domains.basketball_wnba.ingame_blend_families import (
    FAMILY_NAMES,
    Row,
    brier,
    fit_all_families,
    predict_family,
)

logger = logging.getLogger(__name__)

EDGE_CLAIMED = False


# ---------------------------------------------------------------------------
# Cross-corpus fit / validate / swap
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DirectionResult:
    """One fit-on-X, validate-on-Y direction's per-checkpoint Brier table."""
    fit_on: str
    validate_on: str
    per_family_brier: Dict[str, Dict[str, Optional[float]]]  # family -> cp -> brier
    n_fit: int
    n_validate: int


def _pooled_rows(by_cp: Dict[str, List[Row]]) -> List[Row]:
    rows: List[Row] = []
    for cp in CHECKPOINTS:
        rows.extend(by_cp[cp])
    return rows


def run_direction(fit_rows_by_cp: Dict[str, List[Row]],
                   validate_rows_by_cp: Dict[str, List[Row]],
                   fit_name: str, validate_name: str) -> DirectionResult:
    """Fit all 4 families on fit_rows_by_cp (pooled across checkpoints), score
    each family's per-checkpoint Brier on validate_rows_by_cp. Reuses
    ingame_blend_families.fit_all_families / predict_family verbatim."""
    fitted = fit_all_families(_pooled_rows(fit_rows_by_cp))
    per_family: Dict[str, Dict[str, Optional[float]]] = {name: {} for name in FAMILY_NAMES}
    for cp in CHECKPOINTS:
        rows = validate_rows_by_cp[cp]
        outcomes = [r.outcome for r in rows]
        for name in FAMILY_NAMES:
            preds = [predict_family(name, r, fitted) for r in rows]
            per_family[name][cp] = brier(preds, outcomes)
    return DirectionResult(
        fit_on=fit_name, validate_on=validate_name,
        per_family_brier=per_family,
        n_fit=len(_pooled_rows(fit_rows_by_cp)) // max(1, len(CHECKPOINTS)),
        n_validate=len(_pooled_rows(validate_rows_by_cp)) // max(1, len(CHECKPOINTS)),
    )


def _family_wins_every_checkpoint(name: str, result: DirectionResult) -> bool:
    """True iff *name* has the strictly-lowest Brier among ALL families at
    EVERY checkpoint in this direction's validate corpus."""
    for cp in CHECKPOINTS:
        target = result.per_family_brier[name][cp]
        if target is None:
            return False
        for other in FAMILY_NAMES:
            if other == name:
                continue
            rival = result.per_family_brier[other][cp]
            if rival is not None and rival <= target:
                return False
    return True


def adopt_verdict(a_to_b: DirectionResult, b_to_a: DirectionResult) -> Dict[str, object]:
    """A family is ADOPTED only if it wins every checkpoint in BOTH directions
    (A->B AND B->A) -- a stronger bar than a single fit/validate/OOS chain on
    one corpus. Else honest REJECT (recorded with the numbers, not silence)."""
    winners_ab = [n for n in FAMILY_NAMES if _family_wins_every_checkpoint(n, a_to_b)]
    winners_ba = [n for n in FAMILY_NAMES if _family_wins_every_checkpoint(n, b_to_a)]
    both = sorted(set(winners_ab) & set(winners_ba))
    verdict = "ADOPT" if len(both) == 1 else "REJECT"
    return {
        "verdict": verdict,
        "winners_a_to_b": winners_ab,
        "winners_b_to_a": winners_ba,
        "cross_corpus_winner": both[0] if len(both) == 1 else None,
        "reason": (
            f"unique family {both[0]!r} wins every checkpoint in both directions"
            if verdict == "ADOPT" else
            "no single family swept every checkpoint in BOTH directions "
            f"(A->B winners={winners_ab}, B->A winners={winners_ba})"
        ),
    }


def run_cross_corpus_check() -> Dict[str, object]:
    """Full pipeline: load both corpora, fit A->validate B, fit B->validate A,
    adjudicate. Returns a JSON-serializable report dict. Never raises --
    missing/empty corpus yields an honest INSUFFICIENT_DATA verdict."""
    a_games = load_corpus_a_2026()
    b_games = load_corpus_b_games()
    b_states = load_corpus_b_states()

    if a_games.empty or b_games.empty or b_states.empty:
        return {
            "edge_claimed": EDGE_CLAIMED,
            "verdict": "INSUFFICIENT_DATA",
            "reason": "one or both corpora absent on disk",
            "n_corpus_a": int(len(a_games)), "n_corpus_b_games": int(len(b_games)),
        }

    a_with_p0 = _walk_forward_elo_simple(a_games)
    b_with_p0 = _walk_forward_elo_simple(b_games)

    a_by_cp = build_rows_corpus_a(a_with_p0)
    b_by_cp = build_rows_corpus_b(b_with_p0, b_states)

    if any(len(a_by_cp[cp]) == 0 for cp in CHECKPOINTS) or \
       any(len(b_by_cp[cp]) == 0 for cp in CHECKPOINTS):
        return {
            "edge_claimed": EDGE_CLAIMED,
            "verdict": "INSUFFICIENT_DATA",
            "reason": "one or more checkpoints has zero joined rows in a corpus",
            "n_corpus_a_games": int(len(a_games)), "n_corpus_b_games": int(len(b_games)),
        }

    a_to_b = run_direction(a_by_cp, b_by_cp, "corpus_a_2026_linescores", "corpus_b_cdn_backfill")
    b_to_a = run_direction(b_by_cp, a_by_cp, "corpus_b_cdn_backfill", "corpus_a_2026_linescores")
    verdict = adopt_verdict(a_to_b, b_to_a)

    return {
        "edge_claimed": EDGE_CLAIMED,
        "note": "calibration (Brier) comparison only; REJECT is a designed, non-failure outcome",
        "n_corpus_a_games": int(len(a_games)),
        "n_corpus_b_games": int(len(b_games)),
        "a_to_b": {
            "fit_on": a_to_b.fit_on, "validate_on": a_to_b.validate_on,
            "n_fit": a_to_b.n_fit, "n_validate": a_to_b.n_validate,
            "per_family_brier": a_to_b.per_family_brier,
        },
        "b_to_a": {
            "fit_on": b_to_a.fit_on, "validate_on": b_to_a.validate_on,
            "n_fit": b_to_a.n_fit, "n_validate": b_to_a.n_validate,
            "per_family_brier": b_to_a.per_family_brier,
        },
        **verdict,
    }


def _main() -> int:
    logging.basicConfig(level=logging.INFO)
    report = run_cross_corpus_check()
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "EDGE_CLAIMED", "CHECKPOINTS", "LINESCORES_PARQUET", "CDN_BACKFILL_DIR",
    "load_corpus_a_2026", "load_corpus_b_games", "load_corpus_b_states",
    "build_rows_corpus_a", "build_rows_corpus_b",
    "DirectionResult", "run_direction", "adopt_verdict", "run_cross_corpus_check",
]
