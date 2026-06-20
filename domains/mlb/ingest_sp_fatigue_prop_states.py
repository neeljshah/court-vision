"""domains.mlb.ingest_sp_fatigue_prop_states -- leak-free SP fatigue/velo PROFILE
for a NEXT-start STRIKEOUT-prop prior (HYPOTHESIS TEST, expected REJECT-leaning).

HYPOTHESIS (distinct from the REJECTED game win-prob test): a pitcher's HISTORICAL
within-start fatigue/velo-decline PROFILE -- aggregated over PRIOR starts, leak-free --
may carry calibration signal for that pitcher's STRIKEOUT prop in the NEXT start,
beyond a simple recent-K-rate prior.

WHAT THIS MODULE BUILDS (all leak-free, on-disk only):
  1. PER-OUTING shape summary, one row per (game_id, pitching_side), from the
     materialized per-pitch parquet (data/cache/ingame/mlb_pitch_states__<season>.parquet):
       n_pitches, mean_early_velo (first N pitches of the side),
       velo_decline_slope (OLS slope of velo vs pitch index over the outing),
       pitch_mix_entropy (Shannon entropy of pitch_type distribution),
       mean_velo, frac_breaking. Each summary uses ONLY pitches IN THAT OUTING; the
       profile (step 2) then uses ONLY PRIOR outings -- so start-N pitches never enter
       start-N's profile.
  2. PRIOR-N PROFILE per (pitching team, side, date), shift1 over the team-side's
     PRIOR outings (last K, default 3) -- the leak-free feature set available BEFORE
     the start being predicted.
  3. RECENT-K-RATE BASE (the honest baseline to beat): prior-N mean of the per-start
     K LABEL, shift1. Requires a leak-free per-start K label (step 4).
  4. LABEL = start-N strikeout total, joined leak-free (as-of, post-game settle) from
     an on-disk per-pitcher boxscore source (player_gamelogs.parquet pitch_strikeOuts).

HONEST DATA VERDICT (measured 2026-06-19, do NOT 0-fill / fabricate around it):
  * The ONLY on-disk per-pitcher K source (player_gamelogs.parquet) covers 2026 ONLY;
    the pitch-state corpora are 2022 + 2023 -> ZERO season overlap -> the per-start K
    LABEL cannot be built leak-free for the corpora that carry the fatigue profile.
  * The pitch parquet has NO individual-pitcher id and NO SP/reliever-change marker, so
    a (game, side) outing block CONFLATES the starter with all relievers (relievers
    throw harder -> contaminates the velo-decline profile as the STARTER's). label_k
    join keys (pitcher identity) are therefore also unavailable per-start.
  Consequently build_label_join() returns status=INSUFFICIENT_DATA with reason codes.
  The PROFILE/base scaffold is still built + tested so the gate can run the day a
  2022/2023 per-pitcher K source (with SP isolation) lands on disk.

LEAK-FREENESS CONTRACT (enforced by the per-file test):
  - the profile for start N uses ONLY the pitcher-side's PRIOR outings (shift1); start
    N's own outing is NEVER in start N's profile feature row.
  - the K LABEL is the target ONLY -- never a feature; the recent-K-rate base is the
    shift1 prior mean (excludes start N's own K).
  - no season-final aggregate is merged onto a per-start row; the join is as-of.
ASCII only. <=300 LOC. No src/kernel/api imports. No data/registry write.
CLI: python -m domains.mlb.ingest_sp_fatigue_prop_states --season 2022
"""
from __future__ import annotations

import argparse
import logging
import math
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

log = logging.getLogger(__name__)
_REPO = Path(__file__).resolve().parents[2]
_PITCH_DIR = _REPO / "data" / "cache" / "ingame"
_GAMELOGS = _REPO / "data" / "domains" / "mlb" / "player_gamelogs.parquet"

# Earliest pitches (per outing) that establish the "fresh" velocity baseline.
_EARLY_N = 5
# Default prior-N window for the profile / recent-K-rate base.
_PRIOR_N = 3
# Breaking-ball pitch_type abbreviations (for frac_breaking).
_BREAKING = frozenset({"SL", "CU", "KC", "ST", "SV", "CS", "SC"})


# --------------------------------------------------------------------------- #
# Step 1: per-outing shape summary (uses ONLY pitches in that outing).
# --------------------------------------------------------------------------- #
def _ols_slope(idx: List[float], y: List[float]) -> float:
    """OLS slope of y on idx; NaN if <2 finite points or zero idx variance."""
    pts = [(x, v) for x, v in zip(idx, y) if not math.isnan(v)]
    if len(pts) < 2:
        return float("nan")
    n = float(len(pts))
    sx = sum(p[0] for p in pts)
    sy = sum(p[1] for p in pts)
    sxx = sum(p[0] * p[0] for p in pts)
    sxy = sum(p[0] * p[1] for p in pts)
    denom = n * sxx - sx * sx
    if denom == 0.0:
        return float("nan")
    return (n * sxy - sx * sy) / denom


def _entropy(types: List[str]) -> float:
    """Shannon entropy (nats) of the pitch_type distribution; '' ignored."""
    counts: Dict[str, int] = {}
    for t in types:
        if t:
            counts[t] = counts.get(t, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return float("nan")
    ent = 0.0
    for c in counts.values():
        p = c / total
        ent -= p * math.log(p)
    return ent


def _pitch_side(label: str) -> str:
    """top* -> home pitches; bottom* -> away pitches."""
    return "home" if str(label).startswith("top") else "away"


def per_outing_summary(pitch_df: pd.DataFrame) -> pd.DataFrame:
    """One row per (game_id, pitching_side, date, season, pitch_team) outing.

    Every column uses ONLY pitches within that outing. pitch_team is the TEAM whose
    staff is pitching (home_team for the top half, away_team for the bottom) -- this is
    the join key for the prior-N profile (NOT an individual SP id, which is absent).
    """
    if pitch_df.empty:
        return pd.DataFrame()
    df = pitch_df.copy()
    df["pitch_side"] = df["half_inning_label"].map(_pitch_side)
    df["pitch_team"] = df.apply(
        lambda r: r["home_team"] if r["pitch_side"] == "home" else r["away_team"], axis=1)
    rows: List[dict] = []
    for (gid, side), grp in df.groupby(["game_id", "pitch_side"], sort=False):
        grp = grp.sort_values("asof_idx")
        velos = grp["pitch_velocity"].tolist()
        finite = [v for v in velos if not math.isnan(v)]
        early = [v for v in velos[:_EARLY_N] if not math.isnan(v)]
        idx = list(range(len(velos)))
        types = [str(t) for t in grp["pitch_type"].tolist()]
        brk = sum(1 for t in types if t in _BREAKING)
        rows.append({
            "game_id": gid,
            "pitch_side": side,
            "pitch_team": grp["pitch_team"].iloc[0],
            "date": grp["date"].iloc[0],
            "season": int(grp["season"].iloc[0]),
            "n_pitches": int(len(grp)),
            "mean_velo": (sum(finite) / len(finite)) if finite else float("nan"),
            "mean_early_velo": (sum(early) / len(early)) if early else float("nan"),
            "velo_decline_slope": _ols_slope([float(i) for i in idx], velos),
            "pitch_mix_entropy": _entropy(types),
            "frac_breaking": (brk / len(types)) if types else float("nan"),
        })
    out = pd.DataFrame(rows)
    return out.sort_values(["date", "game_id", "pitch_side"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Step 2: prior-N leak-free PROFILE (shift1 over the team-side's PRIOR outings).
# --------------------------------------------------------------------------- #
_PROFILE_COLS = ("mean_early_velo", "velo_decline_slope", "pitch_mix_entropy",
                 "frac_breaking", "n_pitches")


def prior_n_profile(outings: pd.DataFrame, prior_n: int = _PRIOR_N) -> pd.DataFrame:
    """Add prof_<col> = rolling mean of the PRIOR `prior_n` outings (shift1).

    Grouped by (pitch_team, pitch_side) and ordered by date so start N's profile is
    built ONLY from that team-side's earlier outings. The current outing's own shape
    is shifted out -> start N never sees itself. Rows with <1 prior outing get NaN
    profile values (NOT 0-filled) and prof_n_prior records how many priors existed.
    """
    if outings.empty:
        return outings.assign(**{f"prof_{c}": [] for c in _PROFILE_COLS},
                              prof_n_prior=[])
    df = outings.sort_values(["pitch_team", "pitch_side", "date", "game_id"]).copy()
    g = df.groupby(["pitch_team", "pitch_side"], sort=False)
    for c in _PROFILE_COLS:
        df[f"prof_{c}"] = g[c].apply(
            lambda s: s.shift(1).rolling(prior_n, min_periods=1).mean()
        ).reset_index(level=[0, 1], drop=True)
    df["prof_n_prior"] = (g.cumcount()).clip(upper=prior_n)
    return df.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Step 4 + 3: leak-free K LABEL join + recent-K-rate BASE.
# --------------------------------------------------------------------------- #
def build_label_join(outings: pd.DataFrame,
                     gamelogs_path: Optional[Path] = None) -> dict:
    """Attempt the leak-free per-start K LABEL join. Returns a STATUS dict.

    Honest: returns status=INSUFFICIENT_DATA (no 0-fill, no fabrication) when no
    on-disk per-pitcher K source overlaps the profile corpora, or when per-start SP
    identity cannot be isolated from the (game, side) staff block. reason codes:
      NO_K_SOURCE        -- gamelogs parquet absent.
      NO_SEASON_OVERLAP  -- K source seasons disjoint from profile seasons.
      NO_SP_IDENTITY     -- pitch parquet lacks an individual-pitcher id / SP boundary,
                            so the (game, side) outing cannot be keyed to one starter's K.
    """
    glp = Path(gamelogs_path) if gamelogs_path else _GAMELOGS
    prof_seasons = set(int(s) for s in outings["season"].unique()) if not outings.empty else set()
    if not glp.exists():
        return {"status": "INSUFFICIENT_DATA", "reasons": ["NO_K_SOURCE"],
                "profile_seasons": sorted(prof_seasons), "k_seasons": []}
    gl = pd.read_parquet(glp)
    k_years: List[int] = []
    if "date" in gl.columns:
        k_years = sorted(set(pd.to_datetime(gl["date"], errors="coerce").dt.year.dropna().astype(int)))
    overlap = prof_seasons & set(k_years)
    reasons: List[str] = ["NO_SP_IDENTITY"]  # always true for this pitch schema
    if not overlap:
        reasons.append("NO_SEASON_OVERLAP")
    return {"status": "INSUFFICIENT_DATA", "reasons": reasons,
            "profile_seasons": sorted(prof_seasons), "k_seasons": k_years,
            "season_overlap": sorted(overlap)}


# --------------------------------------------------------------------------- #
# Orchestration.
# --------------------------------------------------------------------------- #
def build_profile(season: int, pitch_dir: Optional[Path] = None,
                  prior_n: int = _PRIOR_N) -> pd.DataFrame:
    """Load one season's pitch parquet -> per-outing summary -> prior-N profile."""
    d = Path(pitch_dir) if pitch_dir else _PITCH_DIR
    fp = d / f"mlb_pitch_states__{season}.parquet"
    if not fp.exists():
        log.warning("pitch parquet missing: %s", fp)
        return pd.DataFrame()
    pitch_df = pd.read_parquet(fp)
    outings = per_outing_summary(pitch_df)
    return prior_n_profile(outings, prior_n=prior_n)


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="MLB SP fatigue/velo PROFILE for K-prop prior.")
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--prior-n", type=int, default=_PRIOR_N)
    args = ap.parse_args(argv)
    prof = build_profile(args.season, prior_n=args.prior_n)
    if prof.empty:
        print(f"season={args.season} NO PROFILE (pitch parquet missing/empty)")
        return 0
    label = build_label_join(prof)
    have_prof = int(prof["prof_n_prior"].gt(0).sum())
    print(f"season={args.season} outings={len(prof)} "
          f"outings_with_prior_profile={have_prof} "
          f"label_status={label['status']} reasons={','.join(label['reasons'])} "
          f"profile_seasons={label['profile_seasons']} k_seasons={label['k_seasons']}")
    print("PER-START K LABEL: INSUFFICIENT_DATA -- NOT 0-filled, NOT fabricated. "
          "Gate cannot run until an overlapping per-pitcher K source + SP isolation lands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
