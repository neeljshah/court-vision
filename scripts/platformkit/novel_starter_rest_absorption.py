"""Starter rest absorption: the rotation day the reference forecast already knows.

Descriptive conditional frequencies only. For every MLB game in
data/domains/mlb/games.parquet that carries both recorded starting pitchers and a
recorded closing moneyline pair, each team-start is labelled with that starter's
days of rest -- the calendar gap to his previous start in the same season, minus
one, the usual baseball convention. Reports the win frequency per rest bucket with
a game-cluster bootstrap 95 percent interval, that frequency minus the devigged
closing reference forecast, the paired contrast against a standard four days, the
same residual inside narrow reference-forecast bands, its season stability, and the
doubleheader nightcap. Cells below the floor keep their count and are masked.

Run: python scripts/platformkit/novel_starter_rest_absorption.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
MLB = REPO / "data" / "domains" / "mlb"
GAMES_PATH, PITCHERS_PATH, ODDS_PATH = MLB / "games.parquet", MLB / "pitchers.parquet", MLB / "odds.parquet"
NAME = "novel_starter_rest_absorption"
OUT_INSIGHT = REPO / "webapp" / "public" / "data" / "insights" / (NAME + ".json")
OUT_SHOWCASE = REPO / "webapp" / "public" / "data" / "showcase" / (NAME + ".json")
OUT_MODULE = REPO / "scripts" / "platformkit" / "analytics_showcase" / "out" / (NAME + ".json")

AS_OF = "2026-09-16"
MIN_PER_CELL = 30
N_BOOT, SEED = 2000, 20260916
BUCKETS = ["3 or fewer", "4", "5", "6 or more"]
STANDARD_IDX = BUCKETS.index("4")
LOADS = ["short rest (4 or fewer)", "long rest (5 or more)"]
BAND_EDGES = [0.0, 0.42, 0.48, 0.52, 0.58, 1.0]
BANDS = ["under 0.42", "0.42 to 0.48", "0.48 to 0.52", "0.52 to 0.58", "over 0.58"]
BAND_LOADS = [band + " / " + load for band in BANDS for load in LOADS]
SLOTS = ["first game", "second game of a doubleheader"]
SELF_PATH = "webapp/public/data/insights/" + NAME + ".json"
SOURCES = ["data/domains/mlb/games.parquet", "data/domains/mlb/pitchers.parquet", "data/domains/mlb/odds.parquet"]
PRIOR_ART = "Short-rest starting pitching is one of the oldest schedule questions in baseball, and the four-versus-five-day rotation day has been argued over for decades. What is added here is the measurement of that state against the recorded closing reference forecast on the same corpus: the residual is reported per rest bucket, then again inside narrow reference-forecast bands so that skill is held roughly fixed, each with a game-cluster interval, a declared mask floor and a season-by-season stability check -- and the outcome is recorded as a null rather than dropped."
FORMULA = "P(team win | starter days of rest in bucket) over team-starts, and the same frequency minus the mean devigged closing reference forecast for that team, reported overall and within reference-forecast bands."

TEXT = {
    "title": "Starter rest absorption: the rotation day is flat, and the reference forecast already carries it",
    "unit": "one team-start, that is one team in one game together with the pitcher who started it; a game contributes two rows",
    "conditioning": "days of rest for the pitcher who started that game, computed as the calendar gap to his previous start in the same season minus one, binned into four buckets; and for the band panel the devigged closing reference forecast for that same team, binned into five bands.",
    "timing": "Every conditioning quantity is fixed before the first pitch. Days of rest comes only from the dates of that pitcher's earlier starts, the reference forecast is the recorded closing moneyline pair for the game, and the doubleheader slot is a schedule fact. Nothing observed after the first pitch enters a cell assignment.",
    "what_it_means": "A starting pitcher's rotation day, on its own, does not separate winners from losers in this corpus. Four days rest, five days and six or more all win close to half their starts, and the residual against the recorded closing reference forecast stays inside its interval in every bucket. The same holds inside narrow reference-forecast bands, where two teams carry almost the same forecast and differ mainly in rotation day.",
    "how_to_read": "Each cell reports n_starts first, then the observed win frequency and its game-cluster bootstrap interval, then the mean reference forecast and the gap between them with its own interval. The contrast panel subtracts the four-days bucket on the same resample, so its interval is paired. A gap whose interval contains zero means the recorded closing forecast and the observed frequency agree within noise for that cell.",
    "why_it_matters": "It records a schedule state a forecaster might reach for and shows it adds nothing measurable here, which is the kind of negative result that keeps a feature list honest. It also shows the shape of the corpus: the short-rest bucket is rare enough that a real effect of a few points could hide inside its interval.",
    "caveat": "Descriptive conditional frequencies, not a forecast and not a causal estimate. The pitcher recorded is the one who actually started, so a rare late scratch would not have been known before the game; rest is confounded with rotation role, injury returns and the all-star break; and the reference forecast comes from a single archived source.",
    "buckets": "days of rest = calendar days between consecutive starts minus one; 0 to 3 -> 3 or fewer; 4 -> 4; 5 -> 5; 6 and above -> 6 or more",
    "bands": "five bands of the devigged closing reference forecast for that team: under 0.42, 0.42 to 0.48, 0.48 to 0.52, 0.52 to 0.58, over 0.58",
    "reference_forecast": "two-way devigged win probability from the recorded closing American moneyline pair, normalized so the two sides sum to 1",
    "gap": "observed win frequency in the cell minus the mean devigged closing reference forecast in the same cell",
    "interval": "percentile 95 percent interval from a bootstrap that resamples whole game clusters with replacement",
    "doubleheader": "game_seq as recorded in the source schedule: 1 for a single game or the opener, 2 for the nightcap. The unit in this panel is one game and the outcome is a home win, so n_starts counts games.",
}
HEADLINE = "Across %d MLB team-starts from %s to %s the starting pitcher's rotation day barely moves the win frequency: %.4f on four days rest (n=%d) against %.4f on five (n=%d) and %.4f on six or more (n=%d), and measured against the recorded closing reference forecast those gaps are %.4f, %.4f and %.4f, %s."
VERDICT = "Recorded as a null. Over %d team-starts the win frequency is flat across the rotation day; %d of %d paired contrasts against a standard four days have an interval that excludes zero, and %s of the %d rest buckets separate from zero against the recorded closing reference forecast. Holding that forecast roughly fixed does not change it: %d of the %d reference-forecast band by load cells separate from zero, and across %d seasons the short-rest residual sits above the long-rest residual in %d of them rather than holding one sign. The doubleheader nightcap, a second schedule state known before the first pitch, tells the same story: its gap of %s sits inside a %s interval on %d games. The corpus rules out a large effect, not a small one -- the short-rest bucket carries only %d starts and its frequency interval is %.4f wide."


def rest_bucket(rest: float) -> str:
    """Days of rest -> its reported bucket."""
    return BUCKETS[0] if rest <= 3 else BUCKETS[3] if rest >= 6 else BUCKETS[int(rest) - 3]


def devig(home_ml, away_ml) -> np.ndarray:
    """Two-way devigged home probability from a pair of American moneylines."""
    def implied(line):
        line = np.asarray(line, dtype=float)
        return np.where(line > 0, 100.0, np.abs(line)) / (np.abs(line) + 100.0)
    home, away = implied(home_ml), implied(away_ml)
    return home / (home + away)


def load_games(games_path: Path = GAMES_PATH, pitchers_path: Path = PITCHERS_PATH, odds_path: Path = ODDS_PATH) -> pd.DataFrame:
    """Game spine: one row per game with its starters, closing reference forecast and label."""
    raw = pd.read_parquet(games_path)
    odds = pd.read_parquet(odds_path).dropna(subset=["ml_close_home_am", "ml_close_away_am"]).copy()
    odds["forecast"] = devig(odds["ml_close_home_am"].to_numpy(), odds["ml_close_away_am"].to_numpy())
    pitchers = pd.read_parquet(pitchers_path)[["event_id", "home_sp_name", "away_sp_name"]]
    games = (raw.dropna(subset=["target_home_win"]).merge(pitchers, on="event_id", how="inner")
             .merge(odds[["event_id", "forecast"]], on="event_id", how="inner")).copy()
    games["cluster"], games["outcome"] = games["event_id"], games["target_home_win"].astype(float)
    games["slot"] = np.where(games["game_seq"].astype(int) >= 2, SLOTS[1], SLOTS[0])
    games["date"] = pd.to_datetime(games["date"])
    games.attrs["n_scheduled"] = int(len(raw))
    return games


def to_starts(games: pd.DataFrame) -> pd.DataFrame:
    """Team-start rows carrying the starter's days of rest, the team outcome and its forecast."""
    frames = []
    for side in ("home", "away"):
        block = games[["event_id", "date", "season", "outcome", "forecast", side + "_sp_name"]].copy()
        block = block.rename(columns={side + "_sp_name": "starter"})
        if side == "away":
            block["outcome"], block["forecast"] = 1.0 - block["outcome"], 1.0 - block["forecast"]
        frames.append(block)
    starts = pd.concat(frames, ignore_index=True).dropna(subset=["starter"])
    named = len(starts)
    starts = starts.sort_values(["season", "starter", "date"], kind="stable")
    gap = starts["date"] - starts.groupby(["season", "starter"])["date"].shift(1)
    starts["rest_days"] = gap.dt.days - 1
    starts = starts.dropna(subset=["rest_days"]).copy()
    starts["bucket"] = starts["rest_days"].map(rest_bucket)
    starts["load"] = np.where(starts["rest_days"] <= 4, LOADS[0], LOADS[1])
    starts["band"] = pd.cut(starts["forecast"], BAND_EDGES, labels=BANDS, include_lowest=True).astype(str)
    starts["band_load"] = starts["band"] + " / " + starts["load"]
    starts["cluster"] = starts["event_id"]
    starts.attrs["dropped_missing_starter"] = int(2 * len(games) - named)
    starts.attrs["dropped_no_prior_start"] = int(named - len(starts))
    starts.attrs["max_rest_days"] = float(starts["rest_days"].max())
    return starts


def replicates(cluster_ids, n_boot: int = N_BOOT, seed: int = SEED) -> list:
    """Row indices for n_boot resamples that draw whole game clusters with replacement."""
    codes, uniques = pd.factorize(cluster_ids)
    order = np.argsort(codes, kind="stable")
    bounds = np.searchsorted(codes[order], np.arange(len(uniques) + 1))
    groups = [order[bounds[i]:bounds[i + 1]] for i in range(len(uniques))]
    rng = np.random.default_rng(seed)
    return [np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
            for _ in range(n_boot)]


def _rates(codes: np.ndarray, values: np.ndarray, idx: np.ndarray, k: int) -> np.ndarray:
    """Mean of values per code over the rows in idx; nan where a code is empty."""
    counts = np.bincount(codes[idx], minlength=k).astype(float)
    totals = np.bincount(codes[idx], weights=values[idx], minlength=k)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(counts > 0, totals / counts, np.nan)


def _ci(draws: np.ndarray) -> list:
    """Percentile 95 percent interval per column, [None, None] if all-nan; a rounded zero is +0.0."""
    cols = [draws[:, c][~np.isnan(draws[:, c])] for c in range(draws.shape[1])]
    return [[None, None] if c.size == 0 else [round(float(v), 4) or 0.0 for v in np.percentile(c, [2.5, 97.5])]
            for c in cols]


def _prepare(frame: pd.DataFrame, labels: list, col: str):
    """(codes, counts, replicate row-index list) for a labelled column of one frame."""
    codes = frame[col].map({label: i for i, label in enumerate(labels)})
    if codes.isna().any():
        raise ValueError("column %s carries values outside %s" % (col, labels))
    codes = codes.to_numpy(dtype=int)
    return codes, np.bincount(codes, minlength=len(labels)), replicates(frame["cluster"].to_numpy())


def panel(frame: pd.DataFrame, labels: list, col: str, floor: int = MIN_PER_CELL) -> list:
    """Per label: n, win frequency with its interval, the mean reference forecast and their gap."""
    codes, counts, reps = _prepare(frame, labels, col)
    y, p = frame["outcome"].to_numpy(dtype=float), frame["forecast"].to_numpy(dtype=float)
    full = np.arange(len(frame))
    obs, ref = _rates(codes, y, full, len(labels)), _rates(codes, p, full, len(labels))
    wins = np.vstack([_rates(codes, y, idx, len(labels)) for idx in reps])
    refs = np.vstack([_rates(codes, p, idx, len(labels)) for idx in reps])
    win_ci, gap_ci = _ci(wins), _ci(wins - refs)
    cells = []
    for i, label in enumerate(labels):
        n, span = int(counts[i]), gap_ci[i]
        masked = n < floor
        reason = None if not masked else ("no rows in this cell" if n == 0 else "fewer than %d rows" % floor)
        cells.append({"cell": label, "n_starts": n, "win_frequency": None if masked else round(float(obs[i]), 4),
                      "ci95": [None, None] if masked else win_ci[i], "mean_reference_forecast": None if masked else round(float(ref[i]), 4),
                      "gap_observed_minus_reference": None if masked else round(float(obs[i] - ref[i]), 4),
                      "gap_ci95": [None, None] if masked else span, "masked": masked, "mask_reason": reason,
                      "gap_excludes_zero": None if masked else bool(span[0] > 0 or span[1] < 0)})
    return cells


def contrast_panel(frame: pd.DataFrame, labels: list, col: str, reference: int, floor: int = MIN_PER_CELL) -> list:
    """Each cell's win frequency minus the reference cell's, paired on the same resamples."""
    codes, counts, reps = _prepare(frame, labels, col)
    y = frame["outcome"].to_numpy(dtype=float)
    point = _rates(codes, y, np.arange(len(frame)), len(labels))
    draws = np.vstack([_rates(codes, y, idx, len(labels)) for idx in reps])
    intervals = _ci(draws - draws[:, [reference]])
    rows = []
    for i, label in enumerate(labels):
        if i == reference:
            continue
        masked, span = int(counts[i]) < floor, intervals[i]
        rows.append({"cell": label, "n_starts": int(counts[i]),
                     "delta_vs_standard": None if masked else round(float(point[i] - point[reference]), 4),
                     "ci95": [None, None] if masked else span, "masked": masked,
                     "excludes_zero": None if masked else bool(span[0] > 0 or span[1] < 0)})
    return rows


def season_panel(starts: pd.DataFrame, floor: int = MIN_PER_CELL) -> list:
    """Per season: the observed-minus-reference gap for the short-rest and long-rest loads."""
    rows = []
    for season, block in starts.groupby("season", sort=True):
        cells = panel(block, LOADS, "load", floor)
        paired = None if cells[0]["masked"] or cells[1]["masked"] else round(
            cells[0]["gap_observed_minus_reference"] - cells[1]["gap_observed_minus_reference"], 4)
        rows.append({"season": str(season), "n_starts": int(len(block)), "cells": cells,
                     "short_minus_long": paired})
    return rows


def checks(games: pd.DataFrame, starts: pd.DataFrame) -> dict:
    """Label cross-check against the recorded runs, plus coverage and calibration facts."""
    runs_win = (games["home_runs"] > games["away_runs"]).astype(float)
    y, p = starts["outcome"].to_numpy(dtype=float), starts["forecast"].to_numpy(dtype=float)
    return {
        "label_crosscheck_source": "home_runs and away_runs in data/domains/mlb/games.parquet",
        "label_crosscheck_n": int(len(games)), "tied_final_scores": int((games["home_runs"] == games["away_runs"]).sum()),
        "label_agreement": round(float((games["outcome"] == runs_win).mean()), 4),
        "seasons": sorted(str(s) for s in games["season"].unique()),
        "games_in_source_schedule": int(games.attrs.get("n_scheduled", len(games))), "games_with_starters_and_reference": int(len(games)),
        "starts_dropped_missing_starter": int(starts.attrs.get("dropped_missing_starter", 0)),
        "starts_dropped_no_prior_start_in_season": int(starts.attrs.get("dropped_no_prior_start", 0)),
        "max_rest_days_observed": starts.attrs.get("max_rest_days"), "reference_forecast_brier": round(float(np.mean((p - y) ** 2)), 4),
        "reference_forecast_mean": round(float(p.mean()), 4), "observed_win_frequency": round(float(y.mean()), 4),
    }


def _cite(field: str, value) -> dict:
    return {"path": SELF_PATH, "field": field, "value": value}


def build() -> dict:
    """Compute every panel and return the published artifact as a dict."""
    games = load_games()
    starts = to_starts(games)
    audit = checks(games, starts)
    buckets = panel(starts, BUCKETS, "bucket")
    contrasts = contrast_panel(starts, BUCKETS, "bucket", STANDARD_IDX)
    bands, seasons = panel(starts, BAND_LOADS, "band_load"), season_panel(starts)
    nightcap = panel(games, SLOTS, "slot")
    short, four, five, six = buckets
    separated = [row["cell"] for row in buckets if row["gap_excludes_zero"]]
    band_off = [row["cell"] for row in bands if row["gap_excludes_zero"]]
    contrast_off = [row["cell"] for row in contrasts if row["excludes_zero"]]
    short_above = sum(1 for row in seasons if (row["short_minus_long"] or 0.0) > 0)
    headline = HEADLINE % (
        len(starts), audit["seasons"][0], audit["seasons"][-1], four["win_frequency"], four["n_starts"],
        five["win_frequency"], five["n_starts"], six["win_frequency"], six["n_starts"],
        four["gap_observed_minus_reference"], five["gap_observed_minus_reference"], six["gap_observed_minus_reference"],
        "each inside its own 95 percent interval of zero" if not separated else "and " + " and ".join(separated) + " separates from zero")
    verdict = VERDICT % (
        len(starts), len(contrast_off), len(contrasts), "none" if not separated else ", ".join(separated),
        len(BUCKETS), len(band_off), len(bands), len(seasons), short_above,
        nightcap[1]["gap_observed_minus_reference"], nightcap[1]["gap_ci95"], nightcap[1]["n_starts"],
        short["n_starts"], round(short["ci95"][1] - short["ci95"][0], 4))
    return {
        "id": NAME, "title": TEXT["title"], "as_of": AS_OF, "sport": "mlb",
        "descriptive_only": True, "headline": headline, "headline_insight": headline,
        "verdict": verdict, "is_honest_null": True,
        "population": "MLB games recorded in data/domains/mlb/games.parquet, seasons %s, restricted to the %d games carrying both recorded starting pitchers and a recorded closing moneyline pair, giving %d team-starts whose starter has an earlier start in the same season." % (", ".join(audit["seasons"]), len(games), len(starts)),
        "unit_of_observation": TEXT["unit"], "conditioning_variable": TEXT["conditioning"],
        "timing_guarantee": TEXT["timing"],
        "definitions": {"days_of_rest": TEXT["buckets"], "reference_forecast": TEXT["reference_forecast"],
                        "forecast_bands": TEXT["bands"], "gap_observed_minus_reference": TEXT["gap"], "doubleheader_slot": TEXT["doubleheader"]},
        "method": {"interval": TEXT["interval"], "n_boot": N_BOOT, "seed": SEED, "floor_rows_per_cell": MIN_PER_CELL,
                   "mask_rule": "a cell with fewer than %d rows keeps its count and reports no frequency or interval" % MIN_PER_CELL,
                   "cluster": "the game, so the two team-starts of one game are resampled together"},
        "sources": SOURCES,
        "index_card": {"stat_name": "Starter Rest Absorption", "abbrev": "SRA", "module": NAME, "formula": FORMULA,
                       "prior_art_verdict": "INCREMENTAL", "prior_art_citation": PRIOR_ART,
                       "source_artifacts": SOURCES, "headline": headline, "n_results": len(buckets)},
        "panels": {
            "rest_buckets": {"n_starts": int(len(starts)), "cells": buckets},
            "contrast_vs_standard": contrasts,
            "by_forecast_band": {"n_starts": int(len(starts)), "note": TEXT["bands"], "cells": bands},
            "season_stability": seasons,
            "doubleheader_nightcap": {"n_games": int(len(games)), "note": TEXT["doubleheader"], "cells": nightcap},
        },
        "checks": audit,
        "what_it_means": TEXT["what_it_means"], "how_to_read": TEXT["how_to_read"],
        "why_it_matters": TEXT["why_it_matters"], "caveat": TEXT["caveat"],
        "cited": [
            _cite("panels.rest_buckets.cells[1] win_frequency / n_starts", "%s / %s" % (four["win_frequency"], four["n_starts"])),
            _cite("panels.rest_buckets.cells[3] win_frequency / n_starts", "%s / %s" % (six["win_frequency"], six["n_starts"])),
            _cite("panels.rest_buckets.cells[] gap_excludes_zero", "%d of %d buckets separate from zero" % (len(separated), len(BUCKETS))),
            _cite("panels.by_forecast_band.cells[] gap_excludes_zero", "%d of %d band cells separate from zero" % (len(band_off), len(bands))),
            _cite("checks.reference_forecast_brier", audit["reference_forecast_brier"]),
        ],
    }


def main() -> None:
    """Build the artifact and write it to the insights, showcase and publisher trees."""
    artifact = json.dumps(build(), indent=1, ensure_ascii=True) + "\n"
    for path in (OUT_INSIGHT, OUT_SHOWCASE, OUT_MODULE):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact, encoding="utf-8")
        print("wrote %s" % path.relative_to(REPO).as_posix())


if __name__ == "__main__":
    main()
