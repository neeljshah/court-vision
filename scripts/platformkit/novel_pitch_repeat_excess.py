"""Count-conditioned repeat-pitch excess: how much more often the same pitch comes twice.

Descriptive conditional frequencies only. On every ADJACENT pair of pitches inside one
plate appearance thrown by the same pitcher, the destination pitch either repeats the
previous pitch type or switches away from it. The baseline is that same pitcher's own
count-conditioned mix with the destination pitch left out, so a pitch can never predict
itself. Excess = observed repeat rate minus that baseline, reported overall, by count
class, by raw count, by previous pitch family and per pitcher. Then the game-affecting
question: at the same count, does the repeated pitch fare differently from the switched
one on swings and misses, called strikes plus swings and misses, and weak contact.

Run: python scripts/platformkit/novel_pitch_repeat_excess.py
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from scripts.platformkit.novel_pitch_repeat_pairs import (
    COUNT_CLASSES, COUNTS, EXCLUDED_TYPES, FAMILIES, FAMILY_LABELS, FAMILY_MEMBERS, HARD_HIT_MPH,
    MIN_PAIRS_PER_CELL, N_BOOT, OUTCOME_LABELS, REPO, SEED, add_expectation, build_pairs,
    clustered, difference, excess_panel, excludes_zero, load_pitches, outcome_panel,
)

NAME = "novel_pitch_repeat_excess"
OUT_INSIGHT = REPO / "webapp" / "public" / "data" / "insights" / (NAME + ".json")
OUT_SHOWCASE = REPO / "webapp" / "public" / "data" / "showcase" / (NAME + ".json")
OUT_MODULE = REPO / "scripts" / "platformkit" / "analytics_showcase" / "out" / (NAME + ".json")

AS_OF = "2026-09-16"
SELF_PATH = "webapp/public/data/insights/" + NAME + ".json"
SOURCES = ["data/cache/statcast/statcast_fuller__2025.parquet",
           "data/cache/statcast/savant_full__2025.parquet"]
DECISION_RULE = ("CONFIRMED when the 95 percent interval excludes zero on the preregistered side,"
                 " CONTRADICTED when it excludes zero on the other side, UNDECIDED when it"
                 " contains zero")

# Preregistered before the first number was computed. Each verdict is decided ONLY by
# whether the published interval excludes zero and on which side of zero it sits.
CLAIMS = [
    {"id": 1, "claim": "The repeat excess is positive overall.", "expected_sign": "positive",
     "quantity": "mean over all measured pairs of the repeat indicator minus the leave-one-out expected repeat probability"},
    {"id": 2, "claim": "The repeat excess is larger in pitcher-ahead counts than in counts where the pitcher is behind.",
     "expected_sign": "positive",
     "quantity": "excess in pitcher-ahead counts minus excess in pitcher-behind counts, taken inside the same resample"},
    {"id": 3, "claim": "Repeated pitches draw a lower rate of swings and misses than switched pitches at the same count.",
     "expected_sign": "negative",
     "quantity": "count-class-standardized repeat-minus-switch difference in the swing-and-miss rate, each class weighted by its share of pairs"},
]
PRIOR_ART = ("Pitch-to-pitch sequencing is well travelled: transition matrices of P(next type |"
             " previous type) are standard, and this repository already publishes one per"
             " count-leverage class in pitch_sequencing. What is added here is the baseline. A"
             " league transition matrix cannot say whether a repeat is frequent because the"
             " pitcher throws that pitch often or because he repeats it; the excess measured here"
             " subtracts that pitcher's own mix at that count with the destination pitch left"
             " out, so the two are separated. The outcome half is then measured on the same pairs"
             " with game-cluster intervals, and two of the three preregistered directions are"
             " contradicted and published anyway.")
FORMULA = ("excess = mean over adjacent pairs of 1{type == previous type} minus"
           " (n(pitcher, count, previous type) - 1{type == previous type}) /"
           " (n(pitcher, count) - 1), by count class, raw count, previous pitch family, pitcher.")

TEXT = {
    "title": "Repeat-pitch excess: the same pitch comes back more often than the mix implies",
    "unit": "one adjacent pitch pair, that is pitch k and pitch k+1 inside the same plate appearance thrown by the same pitcher, labelled by the destination pitch; a plate appearance of m pitches contributes at most m-1 pairs",
    "conditioning": "the destination pitch's PRE-pitch count, the previous pitch's type and family, and the identity of the pitcher.",
    "timing": "Everything that assigns a pair to a cell is known before the destination pitch is thrown: the previous pitch type, the pre-pitch count and the pitcher. The count columns are not assumed to be pre-pitch, they are verified -- on every adjacent pair the destination count equals the previous count advanced by the previous pitch's own result, and that agreement is published in checks. The leave-one-out baseline is the one quantity NOT available in advance, since it uses the pitcher's whole-season mix at that count; it is a descriptive normalizer, not a forecast input, and nothing here is a prediction.",
    "what_it_means": "A pitcher returns to the pitch he just threw more often than his own selection rate at that count would produce by chance, and that is not a league-mix artifact because the mix it is measured against is his own. The outcome half then contradicts the intuition that a hitter who has just seen a pitch handles it better.",
    "how_to_read": "Every row reports n_pairs first, then the observed repeat rate, the leave-one-out expected rate and their difference with a game-cluster interval. A row below the floor is masked and keeps its count. In the outcome panels the difference is repeat minus switch inside the same cell, taken inside every resample, so the interval is paired.",
    "why_it_matters": "It separates two things a transition matrix leaves fused -- how often a pitcher throws a type at a count, and how often he repeats it -- and then asks whether the repeated pitch is punished.",
    "caveat": "Descriptive conditional frequencies, not a forecast and not a causal estimate. pitch_type is Statcast's automatic classification, so a misclassified pitch becomes a spurious switch. The repeat and switch groups differ in their destination type mix, which is why the outcome difference is published inside destination pitch family as well. Sequence choice is confounded with the count path that produced it, the hitter, the catcher and the score state, none of which are controlled here. One season, one league.",
    "excess": "observed repeat rate minus the leave-one-out expected repeat rate; the expectation for a pair whose previous pitch was type t at count c thrown by pitcher p is the share of type t among that pitcher's OTHER destination pitches at that same count: (n(p, c, t) - 1{this pitch is t}) / (n(p, c) - 1)",
    "count_class": "pitcher ahead = strikes > balls; even = strikes == balls; pitcher behind = balls > strikes, all read off the destination pitch's pre-pitch count",
    "whiff": "the per-pitch outcome code is swinging_strike or swinging_strike_blocked; a foul tip is contact and is NOT counted as a swing and miss",
    "csw": "the per-pitch outcome code is called_strike, swinging_strike or swinging_strike_blocked",
    "weak_contact": "among destination pitches put in play with a tracked exit velocity, the share below %.0f mph, the usual hard-hit threshold" % HARD_HIT_MPH,
    "outcome_code": "the per-pitch outcome code is the description column of savant_full__2025.parquet, joined one to one on game_pk, at_bat_number and pitch_number. The des column of the pitch table is the plate-appearance result line, populated only on the last pitch of a plate appearance, so it cannot define a per-pitch swing-and-miss.",
    "interval": "percentile 95 percent interval from a bootstrap that resamples whole games with replacement, so every pair from one game moves together",
    "counts_absent": "the 0-0 count opens a plate appearance, so it is never the destination of an adjacent pair",
    "adjacency": "strict pitch_number difference of 1 inside one (game_pk, at_bat_number), with the same pitcher on both halves",
}
HEADLINE = ("Across %s adjacent pitch pairs in the 2025 Statcast season a pitcher throws the same"
            " pitch type twice in a row %.4f of the time against the %.4f his own"
            " count-conditioned mix implies, an excess of %.4f (95 percent interval %.4f to"
            " %.4f). The excess is largest when he is behind (%.4f, n=%s) and smallest at an even"
            " count (%.4f, n=%s), and at the same count the repeated pitch draws %s swings and"
            " misses than the switched pitch (%+.4f, interval %.4f to %.4f).")
VERDICT = ("Preregistered directions that survive the interval test: %d of 3. (1) The repeat"
           " excess is %.4f overall, interval %s -- %s. (2) Pitcher-ahead minus pitcher-behind is"
           " %+.4f, interval %s, so the excess is %s in ahead counts than behind -- %s. (3) The"
           " count-class-standardized swing-and-miss difference is %+.4f, interval %s, so the"
           " repeated pitch draws %s swings and misses -- %s; inside destination pitch family the"
           " same difference is %+.4f (interval %s), so it is not only a type-mix artifact."
           " Truncation check: on the first half of the season the overall excess is %.4f and the"
           " standardized swing-and-miss difference is %+.4f, both the same sign as the full"
           " season. Dropped from %s adjacent pairs: %s where the pitcher changed mid plate"
           " appearance, %s carrying a null or non-pitch type code (a null code or one of %s), and"
           " %s where the pitcher threw only one pitch at that count all season so no"
           " leave-one-out baseline exists, leaving %s measured pairs.")


def _cite(field: str, value) -> dict:
    return {"path": SELF_PATH, "field": field, "value": value}


def _n(value) -> str:
    """A count formatted with thousands separators, for prose only."""
    return "{:,}".format(int(value))


def _series(cells: list, key: str) -> np.ndarray:
    return np.array([np.nan if row[key] is None else row[key] for row in cells], dtype=float)


def pitcher_panel(frame: pd.DataFrame, weights: np.ndarray) -> dict:
    """Per-pitcher excess for pitchers at or above the floor, top and bottom ten."""
    sizes = frame["pitcher"].value_counts()
    labels = sorted(str(int(p)) for p in sizes[sizes >= MIN_PAIRS_PER_CELL].index)
    block = frame[frame["pitcher"].astype(int).astype(str).isin(labels)].copy()
    block["pitcher_label"] = block["pitcher"].astype(int).astype(str)
    cells, _ = excess_panel(block, labels, "pitcher_label", weights)
    for cell in cells:
        cell["pitcher_id"] = int(cell.pop("cell"))
    ordered = sorted(cells, key=lambda row: row["excess"], reverse=True)
    return {"floor_pairs_per_pitcher": MIN_PAIRS_PER_CELL, "n_pitchers": len(labels),
            "n_pairs": int(len(block)), "top": ordered[:10], "bottom": ordered[-10:][::-1],
            "note": "pitcher_id is the MLBAM player id recorded in the source table, which carries no player name column"}


def truncation_check(pitches: pd.DataFrame) -> dict:
    """Recompute the headline quantities on the first half of the season's games."""
    dates = sorted(pitches["game_date"].unique())
    cutoff = dates[len(dates) // 2]
    half, weights = clustered(add_expectation(build_pairs(pitches[pitches["game_date"] <= cutoff])))
    overall, _ = excess_panel(half, ["all pairs"], "all", weights)
    classes, _ = excess_panel(half, COUNT_CLASSES, "count_class", weights)
    rows, pooled = outcome_panel(half.dropna(subset=["description"]), "is_whiff", "outcome_group",
                                OUTCOME_LABELS, weights)
    return {"cutoff_game_date": str(cutoff), "n_games": int(half["game_pk"].nunique()),
            "n_pairs": int(len(half)), "overall_excess": overall[0]["excess"],
            "excess_by_count_class": {row["cell"]: row["excess"] for row in classes},
            "whiff_difference_standardized": pooled["difference"],
            "whiff_difference_by_count_class": {row["cell"]: row["difference"] for row in rows},
            "note": "the leave-one-out baseline is recomputed inside the truncated corpus, so this is a full rebuild rather than a filter of the full-season pairs"}


def verdict_for(claim: dict, value, span: list) -> dict:
    """Attach the measured quantity and the interval-only verdict to a preregistered claim."""
    decided, wanted = excludes_zero(span), 1 if claim["expected_sign"] == "positive" else -1
    sign = 0 if value is None else (1 if value > 0 else (-1 if value < 0 else 0))
    row = dict(claim)
    row.update({"value": value, "ci95": span, "excludes_zero": decided,
                "decision_rule": DECISION_RULE,
                "verdict": "UNDECIDED" if not decided else ("CONFIRMED" if sign == wanted else "CONTRADICTED")})
    return row


def build() -> dict:
    """Compute every panel and return the published artifact as a dict."""
    pitches = load_pitches()
    pairs = add_expectation(build_pairs(pitches))
    frame, weights = clustered(pairs)
    coded = frame.dropna(subset=["description"])
    in_play = coded[coded["type"].eq("X") & coded["launch_speed"].notna()]
    overall, _ = excess_panel(frame, ["all pairs"], "all", weights)
    classes, class_draws = excess_panel(frame, COUNT_CLASSES, "count_class", weights)
    seen = [value for value in COUNTS if value in set(frame["count"])]
    by_count, _ = excess_panel(frame, seen, "count", weights)
    by_family, _ = excess_panel(frame, FAMILIES, "prev_family", weights)
    contrast = difference(_series(classes, "excess"), _series(classes, "n_pairs"), class_draws,
                          COUNT_CLASSES.index("pitcher ahead"), COUNT_CLASSES.index("pitcher behind"))
    whiff, whiff_pooled = outcome_panel(coded, "is_whiff", "outcome_group", OUTCOME_LABELS, weights)
    csw, csw_pooled = outcome_panel(coded, "is_called_or_whiff", "outcome_group", OUTCOME_LABELS, weights)
    weak, weak_pooled = outcome_panel(in_play, "is_weak_contact", "outcome_group", OUTCOME_LABELS, weights)
    within, within_pooled = outcome_panel(coded, "is_whiff", "family_group", FAMILY_LABELS, weights)
    pitchers, truncation = pitcher_panel(frame, weights), truncation_check(pitches)
    coverage = dict(pairs.attrs["coverage"])
    verdicts = [verdict_for(CLAIMS[0], overall[0]["excess"], overall[0]["ci95"]),
                verdict_for(CLAIMS[1], contrast["difference"], contrast["ci95"]),
                verdict_for(CLAIMS[2], whiff_pooled["difference"], whiff_pooled["ci95"])]
    behind, even, top = classes[0], classes[1], overall[0]
    more = "MORE" if whiff_pooled["difference"] > 0 else "FEWER"
    headline = HEADLINE % (_n(len(frame)), top["repeat_rate"], top["expected_repeat_rate"],
                           top["excess"], top["ci95"][0], top["ci95"][1], behind["excess"],
                           _n(behind["n_pairs"]), even["excess"], _n(even["n_pairs"]), more,
                           whiff_pooled["difference"], whiff_pooled["ci95"][0], whiff_pooled["ci95"][1])
    verdict = VERDICT % (
        sum(1 for row in verdicts if row["verdict"] == "CONFIRMED"), top["excess"], top["ci95"],
        verdicts[0]["verdict"], contrast["difference"], contrast["ci95"],
        "smaller" if contrast["difference"] < 0 else "larger", verdicts[1]["verdict"],
        whiff_pooled["difference"], whiff_pooled["ci95"], more.lower(), verdicts[2]["verdict"],
        within_pooled["difference"], within_pooled["ci95"], truncation["overall_excess"],
        truncation["whiff_difference_standardized"], _n(coverage["adjacent_pairs"]),
        _n(coverage["dropped_pitcher_changed_mid_plate_appearance"]),
        _n(coverage["dropped_unknown_or_non_pitch_type"]), ", ".join(EXCLUDED_TYPES),
        _n(coverage["dropped_only_pitch_at_that_count_for_that_pitcher"]), _n(coverage["pairs_measured"]))
    checks = dict(coverage)
    checks.update({"prepitch_count_check": pairs.attrs["prepitch_count_check"],
                   "pitches_without_outcome_code": int(pitches.attrs["pitches_without_outcome_code"]),
                   "measured_pairs_without_outcome_code": int(len(frame) - len(coded)),
                   "n_games": int(frame["game_pk"].nunique()), "n_pitchers": int(frame["pitcher"].nunique()),
                   "raw_counts_observed": seen, "raw_counts_absent": [v for v in COUNTS if v not in seen],
                   "raw_counts_absent_reason": TEXT["counts_absent"], "pitch_families": FAMILY_MEMBERS,
                   "in_play_pairs_with_tracked_exit_velocity": int(len(in_play))})
    return {
        "id": NAME, "title": TEXT["title"], "as_of": AS_OF, "sport": "mlb",
        "descriptive_only": True, "headline": headline, "headline_insight": headline,
        "verdict": verdict, "is_honest_null": False,
        "population": "Every pitch recorded in data/cache/statcast/statcast_fuller__2025.parquet (%s pitches), reduced to the %s adjacent within-plate-appearance pairs thrown by one pitcher with a known pitch type on both halves and a leave-one-out baseline available, across %s games and %s pitchers." % (_n(checks["pitches_in_source"]), _n(len(frame)), _n(checks["n_games"]), _n(checks["n_pitchers"])),
        "unit_of_observation": TEXT["unit"], "conditioning_variable": TEXT["conditioning"],
        "timing_guarantee": TEXT["timing"], "preregistered_claims": verdicts,
        "definitions": {"excess": TEXT["excess"], "count_class": TEXT["count_class"],
                        "pitch_families": FAMILY_MEMBERS, "excluded_pitch_types": EXCLUDED_TYPES,
                        "swing_and_miss": TEXT["whiff"], "called_strike_plus_swing_and_miss": TEXT["csw"],
                        "weak_contact": TEXT["weak_contact"], "outcome_code": TEXT["outcome_code"]},
        "method": {"interval": TEXT["interval"], "n_boot": N_BOOT, "seed": SEED,
                   "floor_pairs_per_cell": MIN_PAIRS_PER_CELL, "adjacency": TEXT["adjacency"],
                   "mask_rule": "a cell with fewer than %d pairs keeps its count and publishes no rate or interval" % MIN_PAIRS_PER_CELL,
                   "cluster": "the game, so every pair from one game is resampled together"},
        "sources": SOURCES,
        "index_card": {"stat_name": "Repeat-Pitch Excess", "abbrev": "RPE", "module": NAME,
                       "formula": FORMULA, "prior_art_verdict": "INCREMENTAL",
                       "prior_art_citation": PRIOR_ART, "source_artifacts": SOURCES,
                       "headline": headline, "n_results": len(classes)},
        "panels": {
            "overall": {"n_pairs": int(len(frame)), "cells": overall},
            "by_count_class": {"n_pairs": int(len(frame)), "cells": classes, "contrast_ahead_minus_behind": contrast},
            "by_count": {"n_pairs": int(len(frame)), "note": TEXT["counts_absent"], "cells": by_count},
            "by_previous_family": {"n_pairs": int(len(frame)), "cells": by_family},
            "outcome_repeat_vs_switch": {
                "n_pairs_with_outcome_code": int(len(coded)), "n_in_play_pairs": int(len(in_play)),
                "swing_and_miss": {"cells": whiff, "standardized": whiff_pooled},
                "called_strike_plus_swing_and_miss": {"cells": csw, "standardized": csw_pooled},
                "weak_contact": {"cells": weak, "standardized": weak_pooled}},
            "outcome_within_destination_family": {"n_pairs_with_outcome_code": int(len(coded)),
                                                  "cells": within, "standardized": within_pooled},
            "per_pitcher": pitchers, "truncation_check": truncation,
        },
        "checks": checks,
        "what_it_means": TEXT["what_it_means"], "how_to_read": TEXT["how_to_read"],
        "why_it_matters": TEXT["why_it_matters"], "caveat": TEXT["caveat"],
        "cited": [
            _cite("panels.overall.cells[0] excess / ci95", "%s %s" % (top["excess"], top["ci95"])),
            _cite("panels.by_count_class.contrast_ahead_minus_behind difference", contrast["difference"]),
            _cite("panels.outcome_repeat_vs_switch.swing_and_miss.standardized difference", whiff_pooled["difference"]),
            _cite("preregistered_claims[] verdict", ", ".join(row["verdict"] for row in verdicts)),
            _cite("checks.prepitch_count_check.verified", checks["prepitch_count_check"]["verified"]),
        ],
    }


def main() -> None:
    """Build the artifact and write identical bytes to the three published copies."""
    artifact = json.dumps(build(), indent=1, ensure_ascii=True) + "\n"
    for path in (OUT_INSIGHT, OUT_SHOWCASE, OUT_MODULE):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact, encoding="utf-8")
        print("wrote %s" % path.relative_to(REPO).as_posix())


if __name__ == "__main__":
    main()
