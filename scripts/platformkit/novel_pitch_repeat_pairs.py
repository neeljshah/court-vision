"""Adjacent pitch pairs, the leave-one-out repeat baseline and the cluster bootstrap.

Shared machinery for novel_pitch_repeat_excess. Builds one row per ADJACENT pair of
pitches inside the same plate appearance, attaches each destination pitch's PRE-pitch
count, marks whether it repeats the previous pitch type, and computes the expected
repeat probability under that same pitcher's own count-conditioned mix with the
destination pitch itself left out. Every interval published by the producer comes from
the resampler here, which draws whole games with replacement.

The count columns are verified rather than assumed: Statcast records balls and strikes
as the count BEFORE the pitch, so on every adjacent pair the destination count must
equal the previous count advanced by the previous pitch's own result.
check_prepitch_count measures that agreement and the producer publishes it.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "data" / "cache" / "statcast"
PITCH_PATH = CACHE / "statcast_fuller__2025.parquet"
DESCRIPTION_PATH = CACHE / "savant_full__2025.parquet"
KEY = ["game_pk", "at_bat_number", "pitch_number"]
PITCH_COLUMNS = ["game_pk", "game_date", "at_bat_number", "pitch_number", "pitcher",
                 "pitch_type", "balls", "strikes", "type", "launch_speed"]

EXCLUDED_TYPES = ["PO", "IN", "UN"]
FAMILY_MEMBERS = {
    "fastball": ["FF", "FA", "FT", "SI", "FC"],
    "breaking": ["SL", "ST", "SV", "CU", "KC", "CS", "SC"],
    "offspeed": ["CH", "FS", "FO", "EP", "KN"],
}
FAMILIES = ["fastball", "breaking", "offspeed"]
FAMILY_OF = {code: family for family, codes in FAMILY_MEMBERS.items() for code in codes}
COUNT_CLASSES = ["pitcher behind", "even", "pitcher ahead"]
COUNTS = ["%d-%d" % (b, s) for b in range(4) for s in range(3)]
WHIFF_CODES = ["swinging_strike", "swinging_strike_blocked"]
CALLED_STRIKE_CODES = ["called_strike"]
HARD_HIT_MPH = 95.0
N_BOOT, SEED = 2000, 20260916
MIN_PAIRS_PER_CELL = 500
OUTCOME_LABELS = [c + " / " + r for c in COUNT_CLASSES for r in ("repeat", "switch")]
FAMILY_LABELS = [c + " / " + f + " / " + r for c in COUNT_CLASSES for f in FAMILIES
                 for r in ("repeat", "switch")]


def count_class(balls: int, strikes: int) -> str:
    """A pre-pitch count -> the class the pitcher is in when he throws the next pitch."""
    if strikes > balls:
        return COUNT_CLASSES[2]
    return COUNT_CLASSES[0] if balls > strikes else COUNT_CLASSES[1]


def pitch_family(code) -> str:
    """A Statcast pitch_type code -> its reported family, or 'other' when unmapped."""
    return FAMILY_OF.get(code, "other")


def load_pitches(pitch_path: Path = PITCH_PATH,
                 description_path: Path = DESCRIPTION_PATH) -> pd.DataFrame:
    """Every pitch in order, carrying the per-pitch outcome code joined one to one."""
    pitches = pd.read_parquet(pitch_path, columns=PITCH_COLUMNS)
    codes = pd.read_parquet(description_path, columns=KEY + ["description"])
    duplicated = int(codes.duplicated(KEY).sum())
    if duplicated:
        raise ValueError("outcome-code table is not one row per pitch: %d duplicate keys" % duplicated)
    merged = pitches.merge(codes, on=KEY, how="left")
    if len(merged) != len(pitches):
        raise ValueError("the outcome-code join changed the pitch count")
    merged = merged.sort_values(KEY, kind="stable").reset_index(drop=True)
    merged.attrs["pitches_in_source"] = int(len(pitches))
    merged.attrs["pitches_without_outcome_code"] = int(merged["description"].isna().sum())
    return merged


def check_prepitch_count(pairs: pd.DataFrame) -> dict:
    """Agreement between each destination count and the previous count advanced by its result."""
    expected_balls = pairs["prev_balls"] + pairs["prev_result"].eq("B").astype(int)
    expected_strikes = np.where(pairs["prev_result"].eq("S"),
                                np.minimum(pairs["prev_strikes"] + 1, 2), pairs["prev_strikes"])
    balls_ok = pairs["balls"] == expected_balls
    strikes_ok = pairs["strikes"] == expected_strikes
    return {
        "rule": "on an adjacent pair the destination balls and strikes must equal the previous"
                " count advanced by the previous pitch's own result: a ball adds one ball, a"
                " strike adds one strike capped at two, a pitch put in play ends the plate"
                " appearance so it can never be the first half of a pair",
        "n_pairs_checked": int(len(pairs)),
        "balls_advance_agreement": round(float(balls_ok.mean()), 4),
        "strikes_advance_agreement": round(float(strikes_ok.mean()), 4),
        "verified": bool(balls_ok.all() and strikes_ok.all()),
    }


def build_pairs(pitches: pd.DataFrame) -> pd.DataFrame:
    """One row per adjacent pitch pair inside a plate appearance, with its labels."""
    grouped = pitches.groupby(["game_pk", "at_bat_number"], sort=False)
    previous = pd.DataFrame({
        "prev_pitch_number": grouped["pitch_number"].shift(1),
        "prev_pitch_type": grouped["pitch_type"].shift(1),
        "prev_pitcher": grouped["pitcher"].shift(1),
        "prev_balls": grouped["balls"].shift(1),
        "prev_strikes": grouped["strikes"].shift(1),
        "prev_result": grouped["type"].shift(1),
    })
    adjacent = (pitches["pitch_number"] - previous["prev_pitch_number"]).eq(1)
    pairs = pd.concat([pitches[adjacent], previous[adjacent]], axis=1)
    coverage = {
        "pitches_in_source": int(pitches.attrs.get("pitches_in_source", len(pitches))),
        "adjacent_pairs": int(adjacent.sum()),
        "pitches_that_start_no_pair": int(len(pitches) - int(adjacent.sum())),
    }
    check = check_prepitch_count(pairs)
    same_pitcher = pairs["prev_pitcher"].eq(pairs["pitcher"])
    coverage["dropped_pitcher_changed_mid_plate_appearance"] = int((~same_pitcher).sum())
    pairs = pairs[same_pitcher]
    unknown = (pairs["pitch_type"].isna() | pairs["prev_pitch_type"].isna()
               | pairs["pitch_type"].isin(EXCLUDED_TYPES)
               | pairs["prev_pitch_type"].isin(EXCLUDED_TYPES))
    coverage["dropped_unknown_or_non_pitch_type"] = int(unknown.sum())
    pairs = pairs[~unknown].copy()
    pairs["is_repeat"] = (pairs["pitch_type"] == pairs["prev_pitch_type"]).astype(float)
    pairs["count_class"] = [count_class(b, s) for b, s in zip(pairs["balls"], pairs["strikes"])]
    pairs["count"] = pairs["balls"].astype(str) + "-" + pairs["strikes"].astype(str)
    pairs["prev_family"] = pairs["prev_pitch_type"].map(pitch_family)
    pairs["family"] = pairs["pitch_type"].map(pitch_family)
    pairs["repeat_label"] = np.where(pairs["is_repeat"] > 0, "repeat", "switch")
    pairs["all"] = "all pairs"
    pairs["outcome_group"] = pairs["count_class"] + " / " + pairs["repeat_label"]
    pairs["family_group"] = (pairs["count_class"] + " / " + pairs["family"] + " / "
                             + pairs["repeat_label"])
    pairs["is_whiff"] = pairs["description"].isin(WHIFF_CODES).astype(float)
    pairs["is_called_or_whiff"] = pairs["description"].isin(
        CALLED_STRIKE_CODES + WHIFF_CODES).astype(float)
    pairs["is_weak_contact"] = (pairs["launch_speed"] < HARD_HIT_MPH).astype(float)
    pairs.attrs["coverage"] = coverage
    pairs.attrs["prepitch_count_check"] = check
    return pairs


def add_expectation(pairs: pd.DataFrame) -> pd.DataFrame:
    """Attach the leave-one-out expected repeat probability and the per-pair excess."""
    size = pairs.groupby(["pitcher", "balls", "strikes"], sort=False)["is_repeat"].transform("size")
    typed = (pairs.groupby(["pitcher", "balls", "strikes", "pitch_type"], sort=False)
             .size().rename("n_same_type").reset_index()
             .rename(columns={"pitch_type": "prev_pitch_type"}))
    frame = pairs.copy()
    frame["n_pitcher_count"] = size.to_numpy(dtype=float)
    frame = frame.merge(typed, on=["pitcher", "balls", "strikes", "prev_pitch_type"], how="left")
    frame["n_same_type"] = frame["n_same_type"].fillna(0.0)
    usable = frame["n_pitcher_count"] >= 2
    coverage = dict(pairs.attrs.get("coverage", {}))
    coverage["dropped_only_pitch_at_that_count_for_that_pitcher"] = int((~usable).sum())
    frame = frame[usable].copy()
    frame["expected_repeat"] = ((frame["n_same_type"] - frame["is_repeat"])
                                / (frame["n_pitcher_count"] - 1.0))
    frame["excess"] = frame["is_repeat"] - frame["expected_repeat"]
    coverage["pairs_measured"] = int(len(frame))
    frame.attrs["coverage"] = coverage
    frame.attrs["prepitch_count_check"] = pairs.attrs.get("prepitch_count_check", {})
    return frame.reset_index(drop=True)


def multiplicities(n_clusters: int, n_boot: int = N_BOOT, seed: int = SEED) -> np.ndarray:
    """(n_clusters, n_boot) draw weights: each column resamples whole games with replacement."""
    rng = np.random.default_rng(seed)
    weights = np.empty((n_clusters, n_boot), dtype=float)
    for column in range(n_boot):
        weights[:, column] = np.bincount(rng.integers(0, n_clusters, n_clusters),
                                         minlength=n_clusters)
    return weights


def cluster_means(values: np.ndarray, group_codes: np.ndarray, cluster_codes: np.ndarray,
                  n_groups: int, weights: np.ndarray):
    """(point means, counts, replicate means) per group under a game-cluster resample."""
    n_clusters = weights.shape[0]
    flat = group_codes.astype(np.int64) * n_clusters + cluster_codes.astype(np.int64)
    size = n_groups * n_clusters
    sums = np.bincount(flat, weights=values, minlength=size).reshape(n_groups, n_clusters)
    counts = np.bincount(flat, minlength=size).reshape(n_groups, n_clusters).astype(float)
    totals = counts.sum(axis=1)
    denominator = counts @ weights
    with np.errstate(invalid="ignore", divide="ignore"):
        point = np.where(totals > 0, sums.sum(axis=1) / totals, np.nan)
        draws = np.where(denominator > 0, (sums @ weights) / denominator, np.nan)
    return point, totals, draws.T


def interval(column: np.ndarray) -> list:
    """Percentile 95 percent interval for one replicate column, [None, None] if all-nan."""
    finite = column[~np.isnan(column)]
    if finite.size == 0:
        return [None, None]
    return [round(float(value), 4) for value in np.percentile(finite, [2.5, 97.5])]


def excludes_zero(span: list):
    """True when a published interval sits wholly above or wholly below zero."""
    if span[0] is None or span[1] is None:
        return None
    return bool(span[0] > 0 or span[1] < 0)


def codes_of(frame: pd.DataFrame, labels: list, column: str) -> np.ndarray:
    """Row-wise index into labels for a labelled column; unknown labels fail loudly."""
    mapped = frame[column].map({label: index for index, label in enumerate(labels)})
    if mapped.isna().any():
        raise ValueError("column %s carries values outside %s" % (column, labels))
    return mapped.to_numpy(dtype=np.int64)


def clustered(frame: pd.DataFrame):
    """(frame with a dense game-cluster code, the resample weights for those games)."""
    codes, uniques = pd.factorize(frame["game_pk"])
    block = frame.copy()
    block["cluster"] = codes
    return block, multiplicities(len(uniques))


def boot(frame: pd.DataFrame, labels: list, column: str, value: str, weights: np.ndarray):
    """(point, counts, replicate draws) for one value column split by one labelled column."""
    return cluster_means(frame[value].to_numpy(dtype=float), codes_of(frame, labels, column),
                         frame["cluster"].to_numpy(), len(labels), weights)


def masked(count) -> bool:
    """A cell below the published floor keeps its count and publishes no estimate."""
    return int(count) < MIN_PAIRS_PER_CELL


def excess_panel(frame: pd.DataFrame, labels: list, column: str, weights: np.ndarray):
    """Per label: n, repeat rate, leave-one-out expectation, excess with its interval."""
    repeat, counts, _ = boot(frame, labels, column, "is_repeat", weights)
    expected, _, _ = boot(frame, labels, column, "expected_repeat", weights)
    excess, _, draws = boot(frame, labels, column, "excess", weights)
    cells = []
    for index, label in enumerate(labels):
        n, span = int(counts[index]), interval(draws[:, index])
        hidden = masked(n)
        cells.append({
            "cell": label, "n_pairs": n,
            "repeat_rate": None if hidden else round(float(repeat[index]), 4),
            "expected_repeat_rate": None if hidden else round(float(expected[index]), 4),
            "excess": None if hidden else round(float(excess[index]), 4),
            "ci95": [None, None] if hidden else span,
            "excludes_zero": None if hidden else excludes_zero(span),
            "masked": hidden,
            "mask_reason": None if not hidden else
            ("no pairs in this cell" if n == 0 else "fewer than %d pairs" % MIN_PAIRS_PER_CELL),
        })
    return cells, draws


def difference(point: np.ndarray, counts: np.ndarray, draws: np.ndarray,
               left: int, right: int) -> dict:
    """The paired left-minus-right difference of two bootstrapped groups."""
    span = interval(draws[:, left] - draws[:, right])
    hidden = masked(counts[left]) or masked(counts[right])
    return {"n_left": int(counts[left]), "n_right": int(counts[right]),
            "difference": None if hidden else round(float(point[left] - point[right]), 4),
            "rate_left": None if hidden else round(float(point[left]), 4),
            "rate_right": None if hidden else round(float(point[right]), 4),
            "ci95": [None, None] if hidden else span,
            "excludes_zero": None if hidden else excludes_zero(span), "masked": hidden}


def outcome_panel(frame: pd.DataFrame, value: str, column: str, labels: list,
                  weights: np.ndarray):
    """Repeat-minus-switch rows for one outcome, plus the class-standardized pooled difference."""
    point, counts, draws = boot(frame, labels, column, value, weights)
    pairs_per_cell = counts.reshape(-1, 2).sum(axis=1)
    share = pairs_per_cell / pairs_per_cell.sum() if pairs_per_cell.sum() else pairs_per_cell
    rows = []
    for index in range(0, len(labels), 2):
        row = difference(point, counts, draws, index, index + 1)
        row["cell"] = labels[index].rsplit(" / ", 1)[0]
        rows.append(row)
    pooled_draws = sum(share[i] * (draws[:, 2 * i] - draws[:, 2 * i + 1])
                       for i in range(len(share)))
    pooled_point = float(sum(share[i] * (point[2 * i] - point[2 * i + 1])
                             for i in range(len(share))))
    span = interval(pooled_draws)
    pooled = {"cell": "standardized over the cells above", "difference": round(pooled_point, 4),
              "ci95": span, "excludes_zero": excludes_zero(span), "n_pairs": int(counts.sum()),
              "masked": False, "note": "each cell weighted by its share of the pairs in this panel"}
    return rows, pooled
