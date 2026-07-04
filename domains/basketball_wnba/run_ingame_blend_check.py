"""domains.basketball_wnba.run_ingame_blend_check -- honest cross-corpus family check (v2).

LANE 4 v2: settles the in-game blend family choice properly, leak-free. Wave 2
(v1, see the "legacy_v1" block in the JSON output for the exact numbers this
superseded) checked ONE blend (the fixed-constant formula) against ONE naive
baseline on 150 2026 games only, and found the naive baseline winning at
half/end_q3 -- an honest signal that the fixed constant needed replacing, not a
full settlement. v2 fits domains.basketball_wnba.ingame_blend_families.py's 4
pre-declared candidate families (fixed / naive / time_scaled / anchored) ONLY
on 2024, validates on 2025, and takes a final OOS read on 2026 -- reporting the
FULL per-checkpoint Brier table for all 4 families across all 3 corpora, plus
the decision trail (which family won, on what basis).

DATA: reads data/domains/wnba/linescores.parquet (built by
domains.basketball_wnba.ingest_linescores.py -- run that first, or this script
raises FileNotFoundError rather than silently falling back to a live re-fetch).
Leak-free by construction: p0 is walk-forward Elo over the FULL 2024-2026
games corpus (so 2025/2026 ratings correctly build on 2024 history), and the
family FIT itself only ever sees 2024 ROWS (see ingame_blend_families.py
docstring for the no-leak argument in full; the property test in
test_ingame_blend_families.py additionally proves 2026 games cannot move the
2024-fit constants at all).

DECISION RULE (step 4 of the brief): a family is adopted as the cross-corpus
winner ONLY if it has the lowest Brier at EVERY checkpoint (end_q1/half/
end_q3) on BOTH 2025 AND 2026 independently. If no family separates that
cleanly, the naive sigmoid (wave 2's own comparison baseline) is kept and the
tie is recorded honestly -- this is model choice inside a domain not yet wired
to any live surface, so a tie is flagged for review, not silently resolved.

Writes data/domains/wnba/ingame_blend_check.json (v2 schema). EDGE_CLAIMED =
False; calibration/coherence only. No network at import/run time (this script
only reads parquet -- ingest_linescores.py is the one that hits the network).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from domains.basketball_wnba.ingame_blend_families import (
    CHECKPOINTS,
    FAMILY_NAMES,
    FittedFamilies,
    build_corpus_with_p0,
    build_rows,
    fit_all_families,
    score_family_by_checkpoint,
)

log = logging.getLogger(__name__)
EDGE_CLAIMED = False

_REPO = Path(__file__).resolve().parents[2]
_GAMES_PARQUET = _REPO / "data" / "domains" / "wnba" / "espn_scoreboard.parquet"
_LINESCORES_PARQUET = _REPO / "data" / "domains" / "wnba" / "linescores.parquet"
_OUT = _REPO / "data" / "domains" / "wnba" / "ingame_blend_check.json"

# The exact wave-2 (v1) numbers this check supersedes, preserved verbatim in
# the v2 output for the honest before/after record (NOT recomputed -- these
# are frozen historical values from the v1 run on 150 2026 games).
_LEGACY_V1 = {
    "n_games_in_window": 150,
    "n_games_matched_linescores": 150,
    "checkpoints": {
        "end_q1": {"brier_blend": 0.2298326434757711, "brier_naive_score_diff_only": 0.229403948325563},
        "half": {"brier_blend": 0.23159615259713243, "brier_naive_score_diff_only": 0.19145050701393937},
        "end_q3": {"brier_blend": 0.23183032840738987, "brier_naive_score_diff_only": 0.16058258398377706},
    },
    "note": "wave-2 check: fixed blend vs a fixed-guess naive sigmoid (k=0.06, not fit) on 150 2026 games only. Superseded by v2's fit/validate/OOS cross-corpus settlement below.",
}


def _family_wins_every_checkpoint(
    family: str,
    scores_by_family: Dict[str, Dict[str, Dict[str, object]]],
) -> bool:
    """True iff *family* has the strictly-lowest Brier at every checkpoint,
    among all families in scores_by_family, on this one corpus."""
    for cp in CHECKPOINTS:
        briers = {
            fam: scores_by_family[fam][cp]["brier"]
            for fam in scores_by_family
            if scores_by_family[fam][cp]["brier"] is not None
        }
        if not briers:
            return False
        winner = min(briers, key=briers.get)  # type: ignore[arg-type]
        if winner != family:
            return False
    return True


def run_check(
    games_df: Optional[pd.DataFrame] = None,
    linescores_df: Optional[pd.DataFrame] = None,
) -> Dict:
    """Build the v2 cross-corpus family settlement. Returns the dict written to
    data/domains/wnba/ingame_blend_check.json."""
    games = games_df if games_df is not None else pd.read_parquet(_GAMES_PARQUET)
    games = games.copy()
    games["season"] = games["season"].astype(str)
    lines = linescores_df if linescores_df is not None else pd.read_parquet(_LINESCORES_PARQUET)
    lines = lines.copy()
    lines["event_id"] = lines["event_id"].astype(str)

    train_2024 = build_corpus_with_p0(games, "2024")
    val_2025 = build_corpus_with_p0(games, "2025")
    oos_2026 = build_corpus_with_p0(games, "2026")

    train_rows = build_rows(train_2024, lines)
    fitted: FittedFamilies = fit_all_families(train_rows)

    corpora = {"2024_train": train_2024, "2025_validate": val_2025, "2026_oos": oos_2026}
    per_corpus_scores: Dict[str, Dict[str, Dict[str, Dict[str, object]]]] = {}
    for corpus_name, df in corpora.items():
        per_corpus_scores[corpus_name] = {
            fam: score_family_by_checkpoint(fam, df, lines, fitted) for fam in FAMILY_NAMES
        }

    # Decision: family must win EVERY checkpoint on BOTH 2025 AND 2026 to be adopted.
    val_winners = {fam: _family_wins_every_checkpoint(fam, per_corpus_scores["2025_validate"])
                   for fam in FAMILY_NAMES}
    oos_winners = {fam: _family_wins_every_checkpoint(fam, per_corpus_scores["2026_oos"])
                   for fam in FAMILY_NAMES}
    cross_corpus_winners = [fam for fam in FAMILY_NAMES if val_winners[fam] and oos_winners[fam]]

    if len(cross_corpus_winners) == 1:
        decision = cross_corpus_winners[0]
        verdict = "cross_corpus_winner_adopted"
    elif len(cross_corpus_winners) > 1:
        # Should not happen (a checkpoint can only have one strict min), kept
        # as a defensive honest branch rather than silently picking [0].
        decision = "naive"
        verdict = "multiple_families_tied__kept_naive__HONEST"
    else:
        decision = "naive"
        verdict = "no_family_swept_both_corpora__kept_naive__HONEST"

    result: Dict[str, object] = {
        "edge_claimed": False,
        "schema_version": 2,
        "data_source": "data/domains/wnba/linescores.parquet (ingest_linescores.py)",
        "corpus_sizes": {name: int(len(df)) for name, df in corpora.items()},
        "fit_split": "2024 (fit only) -> 2025 (validate) -> 2026 (OOS)",
        "fitted_params": {
            "naive_k": fitted.naive_k,
            "time_scaled_k": fitted.time_scaled_k,
            "anchored_k": fitted.anchored_k,
            "anchored_w0": fitted.anchored_w0,
        },
        "per_corpus_brier": {
            corpus_name: {
                fam: {
                    cp: {"n": v["n"], "brier": v["brier"]}
                    for cp, v in per_corpus_scores[corpus_name][fam].items()
                }
                for fam in FAMILY_NAMES
            }
            for corpus_name in corpora
        },
        "checkpoint_winners": {
            "2025_validate": {
                cp: min(
                    (fam for fam in FAMILY_NAMES),
                    key=lambda f: per_corpus_scores["2025_validate"][f][cp]["brier"],
                )
                for cp in CHECKPOINTS
            },
            "2026_oos": {
                cp: min(
                    (fam for fam in FAMILY_NAMES),
                    key=lambda f: per_corpus_scores["2026_oos"][f][cp]["brier"],
                )
                for cp in CHECKPOINTS
            },
        },
        "family_sweeps_all_checkpoints": {
            "2025_validate": val_winners,
            "2026_oos": oos_winners,
        },
        "decision": {
            "adopted_family": decision,
            "verdict": verdict,
            "rule": (
                "A family is adopted only if it has the strictly-lowest Brier "
                "at end_q1, half, AND end_q3 on BOTH 2025 and 2026 independently. "
                "Otherwise the naive sigmoid (simplest wave-2 baseline) is kept "
                "and the tie/inconsistency is recorded honestly."
            ),
        },
        "legacy_v1": _LEGACY_V1,
    }
    return result


def write_check(result: Dict, out_path: Optional[Path] = None) -> Path:
    out = out_path or _OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        json.dump(result, fh, indent=2)
    return out


def _main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run_check()
    out = write_check(result)
    print(json.dumps(result, indent=2))
    print(f"Wrote {out}")
    print(f"DECISION: adopted_family={result['decision']['adopted_family']} "  # type: ignore[index]
          f"verdict={result['decision']['verdict']}")  # type: ignore[index]
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["run_check", "write_check"]
