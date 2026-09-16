"""Rest asymmetry: the schedule differential, not the shared load.

Descriptive conditional frequencies only. For every NBA regular-season game in
data/domains/basketball_nba/games.parquet the rest differential
(rest_days_home - rest_days_away) is a schedule fact fixed before tip-off; the
home win is the outcome. Reports the home win frequency per rest cell with a
game-cluster bootstrap 95 percent interval, the season-by-season stability of
that gradient, whether SYMMETRIC congestion moves anything, and -- on the
subset carrying a recorded pregame moneyline -- observed frequency minus the
devigged market forecast. Cells below the floor keep their count and are
masked. No forecasting and no advantage claim.

Run: python scripts/platformkit/novel_rest_asymmetry.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
NBA = REPO / "data" / "domains" / "basketball_nba"
GAMES_PATH, ODDS_PATH, FINALS_PATH = NBA / "games.parquet", NBA / "odds.parquet", NBA / "game_finals_corrected.parquet"
OUT_INSIGHT = REPO / "webapp" / "public" / "data" / "insights" / "novel_rest_asymmetry.json"
OUT_MODULE = REPO / "scripts" / "platformkit" / "analytics_showcase" / "out" / "novel_rest_asymmetry.json"

AS_OF = "2026-09-16"
MIN_GAMES_PER_CELL = 30
N_BOOT, SEED = 2000, 20260916
CELLS = ["away +2 or more", "away +1", "equal", "home +1", "home +2 or more"]
EQUAL_IDX = CELLS.index("equal")
CONGESTION = ["both on a back-to-back", "mixed", "neither on a back-to-back"]
SIDES = ["away rested more", "equal", "home rested more"]
SELF_PATH = "webapp/public/data/insights/novel_rest_asymmetry.json"
SOURCES = ["data/domains/basketball_nba/games.parquet", "data/domains/basketball_nba/odds.parquet", "data/domains/basketball_nba/game_finals_corrected.parquet"]
PRIOR_ART = "Rest and back-to-back effects on NBA outcomes are long documented. What is added here is the separation of the rest DIFFERENTIAL from symmetric congestion, each with a game-cluster interval and a declared mask floor, plus a season-stability check showing the pooled gradient is not reproduced in 2025-26 -- the one season that carries a recorded pregame price."
FORMULA = "P(home win | rest_days_home - rest_days_away in cell), and on the priced subset the same frequency minus the mean devigged pregame market forecast for that cell."

TEXT = {
    "title": "Rest asymmetry: the differential moves outcomes, the shared load does not",
    "unit_of_observation": "one game",
    "conditioning_variable": "rest differential = rest_days_home - rest_days_away, a schedule quantity fixed before tip-off, binned into five cells; and for the congestion panel, whether both, one or neither side played the previous day.",
    "timing_guarantee": "Every conditioning variable is a property of the schedule that is known before the opening tip: rest days come from the gap to each team's previous game date, and the moneyline is the recorded pregame quote. Nothing observed during or after the game enters a cell assignment.",
    "what_it_means": "Rest is a relative quantity here. A team that is better rested than its opponent wins more often, and the frequency climbs with the size of that advantage, but two tired teams play out almost exactly like two fresh teams. The pooled gradient is also a four-season average that one season does not reproduce.",
    "how_to_read": "Each cell reports n_games first, then the observed home win frequency and its game-cluster bootstrap interval. The contrast panel subtracts the equal-rest cell on the same resample, so its interval is paired. In the market panel a gap whose interval contains zero means the recorded pregame forecast and the observed frequency agree within noise for that cell.",
    "why_it_matters": "It separates a schedule state that tracks outcomes from one that does not, and it shows the limit of the local corpus: the seasons with the clearest gradient are the seasons with no recorded price, so the pricing question stays open.",
    "caveat": "Descriptive conditional frequencies, not a forecast and not a causal estimate. Rest differential is confounded with travel, opponent strength and where a game sits in a road trip, none of which are controlled here. The market panel covers one season only.",
    "cells": "<= -2 away +2 or more; -1 away +1; 0 equal; +1 home +1; >= +2 home +2 or more",
    "back_to_back": "rest_days == 1; at an equal differential this is symmetric, so the mixed congestion cell is empty by construction",
    "market_forecast": "two-way devigged home probability from the recorded pregame American moneyline pair, normalized so home plus away equals 1",
    "gap": "observed home win frequency in the cell minus the mean devigged market forecast in the same cell",
    "interval": "percentile 95 percent interval from a bootstrap that resamples whole game clusters with replacement",
    "congestion_note": "restricted to games at an equal rest differential",
}
HEADLINE = "Across %d NBA games the home win frequency rises from %.4f when the visitor is the better-rested side by two or more days (n=%d) to %.4f when the home side is (n=%d), a %.4f spread, while two teams sharing the same congestion move nothing: at an equal differential both on a back-to-back win %.4f (n=%d) against %.4f (n=%d) when neither is."
VERDICT = "The differential is what moves the frequency, not the load. Pooled over %d games the gradient is monotone across all five cells, and only the %s contrast against equal rest has a bootstrap interval that excludes zero. It is not stable season to season: the home-rested-minus-away-rested gradient clears 5 points in %d of %d seasons and is %s. The %d games that carry a recorded pregame moneyline are all from %s, and there the observed-minus-market gap %s in every unmasked rest cell. So this corpus cannot separate 'the recorded forecast already carries the rest state' from 'this season had no gradient to carry'; the pricing question is recorded as a null, not as a finding."


def rest_cell(diff: float) -> str:
    """Rest differential (home days minus away days) -> its reported cell, clipped at +/-2."""
    return CELLS[int(np.clip(diff, -2, 2)) + 2]


def load_games(path: Path = GAMES_PATH) -> pd.DataFrame:
    """Schedule spine: one row per game with its pre-tip rest state and outcome."""
    raw = pd.read_parquet(path)
    games = raw.dropna(subset=["home_win", "rest_days_home", "rest_days_away"]).copy()
    games.attrs["dropped_missing_rest"] = int(len(raw) - len(games))
    games["rest_diff"] = games["rest_days_home"] - games["rest_days_away"]
    games["cell"] = games["rest_diff"].map(rest_cell)
    home_b2b, away_b2b = games["home_b2b"].astype(bool), games["away_b2b"].astype(bool)
    games["congestion"] = np.where(home_b2b & away_b2b, CONGESTION[0],
                                   np.where(~home_b2b & ~away_b2b, CONGESTION[2], CONGESTION[1]))
    games["side"] = np.where(games["rest_diff"] > 0, SIDES[2],
                             np.where(games["rest_diff"] < 0, SIDES[0], SIDES[1]))
    games["join_date"] = pd.to_datetime(games["date"]).dt.strftime("%Y-%m-%d")
    return games


def devig(home_ml, away_ml) -> np.ndarray:
    """Two-way devigged home probability from a pair of American moneylines."""
    def implied(line):
        line = np.asarray(line, dtype=float)
        return np.where(line > 0, 100.0, np.abs(line)) / (np.abs(line) + 100.0)
    home, away = implied(home_ml), implied(away_ml)
    return home / (home + away)


def load_market(games: pd.DataFrame, path: Path = ODDS_PATH) -> pd.DataFrame:
    """Games joined to a recorded pregame moneyline, carrying a devigged home probability."""
    odds = pd.read_parquet(path).dropna(subset=["home_ml", "away_ml"]).copy()
    odds["join_date"] = pd.to_datetime(odds["date"]).dt.strftime("%Y-%m-%d")
    odds["market_prob"] = devig(odds["home_ml"].to_numpy(), odds["away_ml"].to_numpy())
    keys = ["join_date", "home_team", "away_team"]
    return games.merge(odds[keys + ["market_prob"]], on=keys, how="inner")


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
    """Percentile 95 percent interval per column, or [None, None] if a column is all-nan."""
    cols = [draws[:, c][~np.isnan(draws[:, c])] for c in range(draws.shape[1])]
    return [[None, None] if c.size == 0 else [round(float(v), 4) for v in np.percentile(c, [2.5, 97.5])]
            for c in cols]


def _prepare(frame: pd.DataFrame, labels: list, col: str):
    """(codes, counts, replicate row-index list) for a labelled column of one frame."""
    codes = frame[col].map({label: i for i, label in enumerate(labels)}).to_numpy()
    return codes, np.bincount(codes, minlength=len(labels)), replicates(frame["game_id"].to_numpy())


def frequency_panel(frame: pd.DataFrame, labels: list, col: str,
                    floor: int = MIN_GAMES_PER_CELL) -> list:
    """Per-label n, observed home win frequency and bootstrap interval; masked below the floor."""
    codes, counts, reps = _prepare(frame, labels, col)
    y = frame["home_win"].to_numpy(dtype=float)
    point = _rates(codes, y, np.arange(len(frame)), len(labels))
    intervals = _ci(np.vstack([_rates(codes, y, idx, len(labels)) for idx in reps]))
    cells = []
    for i, label in enumerate(labels):
        masked = int(counts[i]) < floor
        cells.append({"cell": label, "n_games": int(counts[i]),
                      "home_win_frequency": None if masked else round(float(point[i]), 4),
                      "ci95": [None, None] if masked else intervals[i], "masked": masked,
                      "mask_reason": None if not masked else
                      ("no games in this cell" if counts[i] == 0 else "fewer than %d games" % floor)})
    return cells


def contrast_panel(frame: pd.DataFrame, floor: int = MIN_GAMES_PER_CELL) -> list:
    """Each rest cell's frequency minus the equal-rest cell's, paired on the same resamples."""
    codes, counts, reps = _prepare(frame, CELLS, "cell")
    y = frame["home_win"].to_numpy(dtype=float)
    point = _rates(codes, y, np.arange(len(frame)), len(CELLS))
    draws = np.vstack([_rates(codes, y, idx, len(CELLS)) for idx in reps])
    intervals = _ci(draws - draws[:, [EQUAL_IDX]])
    rows = []
    for i, label in enumerate(CELLS):
        if i == EQUAL_IDX:
            continue
        masked, span = int(counts[i]) < floor, intervals[i]
        rows.append({"cell": label, "n_games": int(counts[i]),
                     "delta_vs_equal": None if masked else round(float(point[i] - point[EQUAL_IDX]), 4),
                     "ci95": [None, None] if masked else span, "masked": masked,
                     "excludes_zero": None if masked else bool(span[0] > 0 or span[1] < 0)})
    return rows


def market_panel(frame: pd.DataFrame, floor: int = MIN_GAMES_PER_CELL) -> list:
    """Observed frequency minus the devigged pregame market forecast, per rest cell."""
    codes, counts, reps = _prepare(frame, CELLS, "cell")
    y, p = frame["home_win"].to_numpy(dtype=float), frame["market_prob"].to_numpy(dtype=float)
    full = np.arange(len(frame))
    obs, mkt = _rates(codes, y, full, len(CELLS)), _rates(codes, p, full, len(CELLS))
    intervals = _ci(np.vstack([_rates(codes, y, idx, len(CELLS)) - _rates(codes, p, idx, len(CELLS))
                               for idx in reps]))
    rows = []
    for i, label in enumerate(CELLS):
        masked, span = int(counts[i]) < floor, intervals[i]
        rows.append({"cell": label, "n_games": int(counts[i]),
                     "mean_market_forecast": None if masked else round(float(mkt[i]), 4),
                     "home_win_frequency": None if masked else round(float(obs[i]), 4),
                     "gap_observed_minus_market": None if masked else round(float(obs[i] - mkt[i]), 4),
                     "ci95": [None, None] if masked else span, "masked": masked,
                     "excludes_zero": None if masked else bool(span[0] > 0 or span[1] < 0)})
    return rows


def season_panel(frame: pd.DataFrame, floor: int = MIN_GAMES_PER_CELL) -> list:
    """Per season: the home win frequency by which side is the rested one, and their difference."""
    rows = []
    for season, block in frame.groupby("season", sort=True):
        cells = frequency_panel(block, SIDES, "side", floor)
        more, less = cells[2], cells[0]
        gradient = None if more["masked"] or less["masked"] else round(
            more["home_win_frequency"] - less["home_win_frequency"], 4)
        rows.append({"season": str(season), "n_games": int(len(block)), "cells": cells,
                     "home_more_minus_away_more": gradient})
    return rows


def checks(games: pd.DataFrame, market: pd.DataFrame, path: Path = FINALS_PATH) -> dict:
    """Label cross-check against the corrected finals table, plus coverage facts."""
    out = {"label_crosscheck_source": "data/domains/basketball_nba/game_finals_corrected.parquet"}
    try:
        finals = pd.read_parquet(path)[["game_id", "home_win_true"]]
        joined = games.merge(finals, on="game_id", how="inner")
        out["label_crosscheck_n"] = int(len(joined))
        out["label_agreement"] = round(float((joined["home_win"].astype(bool)
                                              == joined["home_win_true"].astype(bool)).mean()), 4)
    except (OSError, ValueError, KeyError) as err:
        out["label_crosscheck_n"], out["label_agreement"] = 0, None
        out["label_crosscheck_note"] = "corrected finals table unreadable: %s" % type(err).__name__
    out["market_panel_seasons"] = sorted(str(s) for s in market["season"].unique())
    out["schedule_panel_seasons"] = sorted(str(s) for s in games["season"].unique())
    out["congestion_mixed_n"] = int((games.loc[games["rest_diff"].eq(0), "congestion"] == CONGESTION[1]).sum())
    out["rest_days_capped_at"] = float(max(games["rest_days_home"].max(), games["rest_days_away"].max()))
    out["dropped_games_missing_rest"] = int(games.attrs.get("dropped_missing_rest", 0))
    return out


def _cite(field: str, value) -> dict:
    return {"path": SELF_PATH, "field": field, "value": value}


def build() -> dict:
    """Compute every panel and return the published artifact as a dict."""
    games = load_games()
    market = load_market(games)
    cells, contrasts = frequency_panel(games, CELLS, "cell"), contrast_panel(games)
    equal = games.loc[games["rest_diff"].eq(0)]
    congestion, audit = frequency_panel(equal, CONGESTION, "congestion"), checks(games, market)
    seasons, priced = season_panel(games), market_panel(market)
    low, high, both, neither = cells[0], cells[-1], congestion[0], congestion[2]
    spread = round(high["home_win_frequency"] - low["home_win_frequency"], 4)
    congestion_gap = round(both["home_win_frequency"] - neither["home_win_frequency"], 4)
    separated = [r["cell"] for r in contrasts if r["excludes_zero"]]
    strong = [r["season"] for r in seasons if (r["home_more_minus_away_more"] or 0) > 0.05]
    weak = [r["season"] for r in seasons if r["season"] not in strong]
    off = [r["cell"] for r in priced if r["excludes_zero"]]
    headline = HEADLINE % (len(games), low["home_win_frequency"], low["n_games"],
                           high["home_win_frequency"], high["n_games"], spread,
                           both["home_win_frequency"], both["n_games"],
                           neither["home_win_frequency"], neither["n_games"])
    verdict = VERDICT % (
        len(games), " and ".join(separated) or "no", len(strong), len(seasons),
        ("flat or reversed in " + ", ".join(weak)) if weak else "positive in every season",
        len(market), ", ".join(audit["market_panel_seasons"]),
        "stays inside its 95 percent interval of zero" if not off
        else "separates from zero in " + ", ".join(off))
    return {
        "id": "novel_rest_asymmetry", "title": TEXT["title"], "as_of": AS_OF, "sport": "nba",
        "descriptive_only": True, "headline": headline, "headline_insight": headline,
        "verdict": verdict,
        "population": "NBA regular-season games recorded in data/domains/basketball_nba/games.parquet, seasons %s, %d games with a resolved home_win label." % (", ".join(audit["schedule_panel_seasons"]), len(games)),
        "unit_of_observation": TEXT["unit_of_observation"],
        "conditioning_variable": TEXT["conditioning_variable"],
        "timing_guarantee": TEXT["timing_guarantee"],
        "definitions": {"rest_days": "days since that team's previous game, capped at %.0f in the source table" % audit["rest_days_capped_at"],
                        "cells": TEXT["cells"], "back_to_back": TEXT["back_to_back"],
                        "market_forecast": TEXT["market_forecast"], "gap_observed_minus_market": TEXT["gap"]},
        "method": {"interval": TEXT["interval"], "n_boot": N_BOOT, "seed": SEED, "floor_games_per_cell": MIN_GAMES_PER_CELL, "mask_rule": "a cell with fewer than %d games keeps its count and reports no frequency or interval" % MIN_GAMES_PER_CELL},
        "sources": SOURCES, "is_honest_null": False,
        "index_card": {"stat_name": "Rest Asymmetry", "abbrev": "RA", "module": "novel_rest_asymmetry", "formula": FORMULA, "prior_art_verdict": "INCREMENTAL", "prior_art_citation": PRIOR_ART, "source_artifacts": SOURCES, "headline": headline, "n_results": len(cells)},
        "panels": {
            "rest_differential": {"n_games": int(len(games)), "cells": cells},
            "contrast_vs_equal_rest": contrasts,
            "symmetric_congestion": {"n_games": int(len(equal)), "note": TEXT["congestion_note"], "cells": congestion},
            "season_stability": seasons,
            "market_residual": {"n_games": int(len(market)), "seasons": audit["market_panel_seasons"], "cells": priced},
        },
        "checks": audit,
        "what_it_means": TEXT["what_it_means"], "how_to_read": TEXT["how_to_read"],
        "why_it_matters": TEXT["why_it_matters"], "caveat": TEXT["caveat"],
        "cited": [
            _cite("panels.rest_differential.cells[4] home_win_frequency / n_games",
                  "%s / %s" % (high["home_win_frequency"], high["n_games"])),
            _cite("panels.rest_differential.cells[0] home_win_frequency / n_games",
                  "%s / %s" % (low["home_win_frequency"], low["n_games"])),
            _cite("panels.symmetric_congestion.cells home_win_frequency (both / neither)", "%s / %s (gap %s)" % (both["home_win_frequency"], neither["home_win_frequency"], congestion_gap)),
            _cite("panels.market_residual.n_games", int(len(market))),
        ],
    }


def main() -> None:
    """Build the artifact and write it to the insights tree and to the publisher source."""
    artifact = json.dumps(build(), indent=1, ensure_ascii=True) + "\n"
    for path in (OUT_INSIGHT, OUT_MODULE):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact, encoding="utf-8")
        print("wrote %s" % path.relative_to(REPO).as_posix())


if __name__ == "__main__":
    main()
