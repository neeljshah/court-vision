"""MLB v1 menu of predictive-validity MetricTests, player grain (catcher +
pitcher). Two walk-forward tests reusing REAL claim-family derivations,
zero reimplementation:

a. mlb_framing / borderline_called_strike_rate_asof: reuses
   domains.mlb.prereg_shift_framing's build_taken_pitches/classify_borderline/
   load_savant -- the SAME functions domains.mlb.claims_shift_framing's
   mlb_framing_claims family calls -- on savant_full__2023/2024.parquet, NOT
   statcast_fuller__2022/2023 (see CORPUS DEVIATION below). Pre-cutoff
   borderline called-strike rate per catcher predicts FORWARD borderline
   called-strike rate; baseline = pre-cutoff called-strike rate over ALL
   taken pitches (not just borderline) -- a naive, non-borderline-aware
   proxy, the "declare which" baseline the brief asked for.

b. mlb_pitcher_putaway / putaway_swinging_rate_asof: reuses
   domains.mlb.matchup.pitch_mix_profiles.classify_terminal_k -- the SAME
   function scripts.platformkit.intel_validation.mlb_pitcher_putaway_claims
   calls -- on statcast_fuller__2022/2023.parquet. Pre-cutoff RECENT-form
   putaway_swinging_rate (last N_RECENT_GAMES games with >=1 recorded K)
   predicts FORWARD putaway_swinging_rate; baseline = pre-cutoff FULL
   HISTORY-TO-DATE putaway_swinging_rate (all games with a K) -- recent form
   vs career-to-date, mirroring nba_adapters.rest_adjusted_form_test's
   l10-vs-season pattern exactly.

CORPUS DEVIATION (framing only): the brief named statcast_fuller__2022/2023
as the source, but that corpus's `type` column (S/B/X) cannot isolate a
called strike from a swinging strike/foul (independently confirmed by
catcher_framing_index.py, mlb_plate_discipline_claims.py, and
prereg_shift_framing.py) -- a borderline CALLED-strike rate needs the real
`description` column, which exists ONLY on savant_full__2023/2024.parquet
(the corpus mlb_framing_claims already uses). Per the brief's own fallback
("use the family's own snapshot recompute path and declare the caveat"),
this adapter recomputes via that family's real functions on its real corpus
-- cutoffs below are shifted one season (2023/2024 boundary) to match data
that actually exists, not invented on absent columns.

CORPUS_ABSENT (putaway/whiff): a true whiff rate (swing-and-miss/all
swings) needs a per-pitch swing/take column that exists nowhere in this
corpus (mlb_plate_discipline_claims.py's BLOCKED_DIMENSIONS,
mlb_pitcher_putaway_claims.py's own docstring) -- `des` only isolates
swinging-vs-looking on PA-TERMINAL strikeout pitches. putaway_swinging_rate
(swinging-K share of a pitcher's own Ks) is the corpus's real, honestly-
scoped whiff proxy; metric/baseline/forward_outcome are ALL this same proxy
at different windows, never a fabricated "overall whiff rate".

Leak-free by construction: every metric_asof/baseline_asof reads ONLY rows
with game_date < cutoff; every forward_outcome reads ONLY each entity's next
N games (distinct game_pk) with game_date >= cutoff, restricted to games
carrying the relevant opportunity (a borderline take / a recorded K).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from domains.mlb.matchup.pitch_mix_profiles import classify_terminal_k
from domains.mlb.prereg_shift_framing import build_taken_pitches, classify_borderline, load_savant
from scripts.platformkit.intel_validation.mlb_batter_context_claims import (
    FASTBALL_FAMILY,
    HI_VELO_MPH,
    LO_VELO_MPH,
)
from scripts.platformkit.predictive_validity.harness import MetricTest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STATCAST_DIR = _REPO_ROOT / "data" / "cache" / "statcast"
PUTAWAY_STATCAST_PATHS = {
    2022: _STATCAST_DIR / "statcast_fuller__2022.parquet",
    2023: _STATCAST_DIR / "statcast_fuller__2023.parquet",
}
FRAMING_SEASONS = ("2023", "2024")

FRAMING_CUTOFFS = ["2023-08-01", "2023-09-01", "2024-06-01", "2024-07-01", "2024-08-01"]
PUTAWAY_CUTOFFS = ["2022-08-01", "2022-09-01", "2023-06-01", "2023-07-01", "2023-08-01"]
FORWARD_GAMES = 20
MIN_FORWARD_GAMES = 12
FRAMING_MIN_ENTITIES_PER_FOLD = 20
PUTAWAY_MIN_ENTITIES_PER_FOLD = 40
MIN_BORDERLINE_PRECUTOFF = 20  # metric-side floor, catcher's own pre-cutoff borderline takes
MIN_N_K_BASELINE = 30  # matches mlb_pitcher_putaway_claims.py's MIN_N_K floor
N_RECENT_GAMES_PUTAWAY = 15  # "recent form" window, games-with-a-K grain (mirrors NBA's L10)

FRAMING_CAVEAT = (
    "CORPUS DEVIATION: statcast_fuller__2022/2023 has no `description` column, so "
    "borderline called-strike rate is recomputed here via prereg_shift_framing.py's real "
    "build_taken_pitches/classify_borderline/load_savant on savant_full__2023/2024.parquet "
    "(the same corpus+functions mlb_framing_claims already uses) -- cutoffs shifted one "
    "season (2023/2024, not 2022/2023) to match data that exists. baseline = plain "
    "called-strike rate over ALL taken pitches (not just borderline), a declared naive "
    "non-borderline-aware proxy, not a trailing mean of the same outcome."
)
PUTAWAY_CAVEAT = (
    "CORPUS_ABSENT: a true whiff rate (swing-and-miss/all swings) needs a per-pitch "
    "swing/take column absent from this corpus (see mlb_plate_discipline_claims.py's "
    "BLOCKED_DIMENSIONS); putaway_swinging_rate (swinging-K share of a pitcher's own "
    "strikeouts, mlb_pitcher_putaway_claims.py's own metric) stands in for metric, "
    "baseline, AND forward outcome alike -- recent-form (last "
    f"{N_RECENT_GAMES_PUTAWAY} games with a K) vs full-history-to-date, never a "
    "fabricated broader whiff rate."
)


def _pre_cutoff(df: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    return df[df["game_date"] < pd.Timestamp(cutoff)]


def _last_n_games(df: pd.DataFrame, cutoff: str, n: int) -> pd.DataFrame:
    """Rows from each entity's LAST n distinct pre-cutoff games (by game_pk,
    ordered by game_date) -- trailing-form window, games-with-opportunity grain."""
    pre = _pre_cutoff(df, cutoff)
    games = (pre[["entity_id", "game_pk", "game_date"]].drop_duplicates()
             .sort_values(["entity_id", "game_date", "game_pk"]))
    games["rank_from_end"] = games.groupby("entity_id").cumcount(ascending=False)
    keep = games[games["rank_from_end"] < n][["entity_id", "game_pk"]]
    return pre.merge(keep, on=["entity_id", "game_pk"], how="inner")


def _forward_window(df: pd.DataFrame, cutoff: str, n: int) -> pd.DataFrame:
    """Rows from each entity's NEXT n distinct games (by game_pk) with
    game_date >= cutoff -- row-count window, games-with-opportunity grain
    (mirrors nba_adapters._forward_n_games, generalized off game_pk)."""
    t0 = pd.Timestamp(cutoff)
    rows = df[df["game_date"] >= t0]
    games = (rows[["entity_id", "game_pk", "game_date"]].drop_duplicates()
             .sort_values(["entity_id", "game_date", "game_pk"]))
    games["rank"] = games.groupby("entity_id").cumcount()
    keep = games[games["rank"] < n][["entity_id", "game_pk"]]
    return rows.merge(keep, on=["entity_id", "game_pk"], how="inner")


def _rate(df: pd.DataFrame, value_col: str, min_n: int = 0) -> pd.DataFrame:
    g = df.groupby("entity_id")[value_col].agg(n="size", rate="mean").reset_index()
    g = g[g["n"] >= min_n]
    return g[["entity_id", "rate"]].rename(columns={"rate": "value"})


def _with_n_forward(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    g = df.groupby("entity_id")[value_col].agg(outcome="mean").reset_index()
    n_fwd = df.groupby("entity_id")["game_pk"].nunique().rename("n_forward").reset_index()
    return g.merge(n_fwd, on="entity_id")


# --------------------------------------------------------------------------- #
# a. mlb_framing
# --------------------------------------------------------------------------- #
def load_framing_source(seasons: tuple = FRAMING_SEASONS) -> pd.DataFrame:
    frames = [load_savant(s) for s in seasons]
    df = pd.concat(frames, ignore_index=True)
    df["game_date"] = pd.to_datetime(df["game_date"])
    taken = build_taken_pitches(df)  # description in {called_strike,ball}, geometry+catcher present
    taken = taken.copy()
    taken["borderline"] = classify_borderline(taken)
    taken = taken.rename(columns={"fielder_2": "entity_id"})
    return taken[["entity_id", "game_pk", "game_date", "is_strike", "borderline"]]


def _framing_metric_asof(taken: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    pre = _pre_cutoff(taken[taken["borderline"]], cutoff)
    return _rate(pre, "is_strike", min_n=MIN_BORDERLINE_PRECUTOFF)


def _framing_baseline_asof(taken: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    pre = _pre_cutoff(taken, cutoff)
    return _rate(pre, "is_strike")


def _framing_forward_outcome(taken: pd.DataFrame, cutoff: str, forward_games: int) -> pd.DataFrame:
    fwd = _forward_window(taken[taken["borderline"]], cutoff, forward_games)
    return _with_n_forward(fwd, "is_strike")


def framing_test(taken: pd.DataFrame, forward_games: int = FORWARD_GAMES) -> MetricTest:
    return MetricTest(
        family="mlb_framing", sport="mlb", metric_name="borderline_called_strike_rate_asof",
        baseline_name="plain_called_strike_rate_asof", cutoffs=list(FRAMING_CUTOFFS),
        forward_games=forward_games, min_forward_games=MIN_FORWARD_GAMES,
        min_entities_per_fold=FRAMING_MIN_ENTITIES_PER_FOLD,
        metric_asof=lambda c: _framing_metric_asof(taken, c),
        baseline_asof=lambda c: _framing_baseline_asof(taken, c),
        forward_outcome=lambda c: _framing_forward_outcome(taken, c, forward_games),
        caveat=FRAMING_CAVEAT,
    )


# --------------------------------------------------------------------------- #
# b. mlb_pitcher_putaway
# --------------------------------------------------------------------------- #
def load_putaway_source(paths: dict = PUTAWAY_STATCAST_PATHS) -> pd.DataFrame:
    cols = ["pitcher", "game_pk", "game_date", "des", "events"]
    frames = [pd.read_parquet(p, columns=cols) for p in paths.values()]
    df = pd.concat(frames, ignore_index=True)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df["k_class"] = classify_terminal_k(df["des"], df["events"])
    k = df[df["k_class"].notna()].copy()
    k["is_swinging"] = (k["k_class"] == "swinging").astype(int)
    return k.rename(columns={"pitcher": "entity_id"})[["entity_id", "game_pk", "game_date", "is_swinging"]]


def _putaway_metric_asof(k: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    recent = _last_n_games(k, cutoff, N_RECENT_GAMES_PUTAWAY)
    return _rate(recent, "is_swinging")


def _putaway_baseline_asof(k: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    pre = _pre_cutoff(k, cutoff)
    return _rate(pre, "is_swinging", min_n=MIN_N_K_BASELINE)


def _putaway_forward_outcome(k: pd.DataFrame, cutoff: str, forward_games: int) -> pd.DataFrame:
    fwd = _forward_window(k, cutoff, forward_games)
    return _with_n_forward(fwd, "is_swinging")


def putaway_test(k: pd.DataFrame, forward_games: int = FORWARD_GAMES) -> MetricTest:
    return MetricTest(
        family="mlb_pitcher_putaway", sport="mlb", metric_name="putaway_swinging_rate_asof",
        baseline_name="putaway_swinging_rate_full_history_asof", cutoffs=list(PUTAWAY_CUTOFFS),
        forward_games=forward_games, min_forward_games=MIN_FORWARD_GAMES,
        min_entities_per_fold=PUTAWAY_MIN_ENTITIES_PER_FOLD,
        metric_asof=lambda c: _putaway_metric_asof(k, c),
        baseline_asof=lambda c: _putaway_baseline_asof(k, c),
        forward_outcome=lambda c: _putaway_forward_outcome(k, c, forward_games),
        caveat=PUTAWAY_CAVEAT,
    )


# --------------------------------------------------------------------------- #
# c. mlb_batter_context -- does an as-of vs-velocity split predict the SAME
#    batter's forward vs-velocity split, vs a literal "assume zero split"
#    baseline? Reuses mlb_batter_context_claims.py's own FASTBALL_FAMILY/
#    HI_VELO_MPH/LO_VELO_MPH bucket definitions (imported, not re-derived) on
#    statcast_fuller__2022/2023.parquet -- the SAME corpus/floors family used
#    by the descriptive claim producer.
# --------------------------------------------------------------------------- #
BATTER_CONTEXT_STATCAST_PATHS = PUTAWAY_STATCAST_PATHS
BATTER_CONTEXT_CUTOFFS = ["2022-06-01", "2022-07-01", "2022-08-01", "2022-09-01"]
FORWARD_GAMES_CONTEXT = 200  # deliberately large -- these within-2022 cutoffs need to reach into 2023
MIN_FORWARD_GAMES_CONTEXT = 12
CONTEXT_MIN_ENTITIES_PER_FOLD = 15
CONTEXT_MIN_VELO_PA_ASOF = 20  # looser than the claim family's MIN_VELO_PA=40 -- partial-season asof grain

BATTER_CONTEXT_CAVEAT = (
    "BASELINE = a literal 'assume zero split' constant (0.0 for every batter), NOT a trailing "
    "mean of the same outcome -- this is degenerate for Spearman rank correlation (zero "
    "variance), so rho_baseline is NaN by construction and PREDICTIVE_VERIFIED cannot fire on "
    "a baseline artifact; the metric's own forward skill is read from rho_metric_bootstrap "
    "(single-arm CI) instead. Reuses mlb_batter_context_claims.py's FASTBALL_FAMILY/"
    "HI_VELO_MPH/LO_VELO_MPH bucket definitions -- same corpus, looser asof-side floor "
    f"(n>={CONTEXT_MIN_VELO_PA_ASOF}/bucket vs the claim family's 40, since a partial-season "
    "as-of window has less data than the full-season claim)."
)


def load_batter_context_source(paths: dict = BATTER_CONTEXT_STATCAST_PATHS) -> pd.DataFrame:
    cols = ["batter", "game_pk", "game_date", "release_speed", "pitch_type",
            "events", "estimated_woba_using_speedangle"]
    frames = [pd.read_parquet(p, columns=cols) for p in paths.values()]
    df = pd.concat(frames, ignore_index=True)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df[df["events"].notna() & df["estimated_woba_using_speedangle"].notna()].copy()
    is_fastball = df["pitch_type"].isin(FASTBALL_FAMILY)
    velo = df["release_speed"].astype("float64")
    df["velo_bucket"] = pd.Series(pd.NA, index=df.index, dtype="object")
    df.loc[is_fastball & (velo >= HI_VELO_MPH), "velo_bucket"] = "hi"
    df.loc[is_fastball & (velo < LO_VELO_MPH), "velo_bucket"] = "lo"
    df["xwoba"] = df["estimated_woba_using_speedangle"].astype("float64")
    return df.rename(columns={"batter": "entity_id"})[
        ["entity_id", "game_pk", "game_date", "xwoba", "velo_bucket"]
    ]


def _context_bucket_delta(df: pd.DataFrame, min_n: int) -> pd.DataFrame:
    hi = df[df["velo_bucket"] == "hi"].groupby("entity_id")["xwoba"].agg(n_hi="size", mean_hi="mean")
    lo = df[df["velo_bucket"] == "lo"].groupby("entity_id")["xwoba"].agg(n_lo="size", mean_lo="mean")
    joined = hi.join(lo, how="inner").reset_index()
    joined = joined[(joined["n_hi"] >= min_n) & (joined["n_lo"] >= min_n)]
    joined["value"] = joined["mean_hi"] - joined["mean_lo"]
    return joined[["entity_id", "value"]]


def _context_metric_asof(df: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    return _context_bucket_delta(_pre_cutoff(df, cutoff), CONTEXT_MIN_VELO_PA_ASOF)


def _context_baseline_asof(df: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    """Literal 'assume zero split' baseline: same entities as metric_asof, value forced to 0.0."""
    m = _context_metric_asof(df, cutoff)
    return m.assign(value=0.0)


def _context_forward_outcome(df: pd.DataFrame, cutoff: str, forward_games: int) -> pd.DataFrame:
    fwd = _forward_window(df, cutoff, forward_games)
    delta = _context_bucket_delta(fwd, CONTEXT_MIN_VELO_PA_ASOF).rename(columns={"value": "outcome"})
    n_fwd = fwd.groupby("entity_id")["game_pk"].nunique().rename("n_forward").reset_index()
    return delta.merge(n_fwd, on="entity_id")


def batter_context_test(df: pd.DataFrame, forward_games: int = FORWARD_GAMES_CONTEXT) -> MetricTest:
    return MetricTest(
        family="mlb_batter_context", sport="mlb", metric_name="vs_velocity_delta_asof",
        baseline_name="assume_zero_split", cutoffs=list(BATTER_CONTEXT_CUTOFFS),
        forward_games=forward_games, min_forward_games=MIN_FORWARD_GAMES_CONTEXT,
        min_entities_per_fold=CONTEXT_MIN_ENTITIES_PER_FOLD,
        metric_asof=lambda c: _context_metric_asof(df, c),
        baseline_asof=lambda c: _context_baseline_asof(df, c),
        forward_outcome=lambda c: _context_forward_outcome(df, c, forward_games),
        caveat=BATTER_CONTEXT_CAVEAT,
    )
