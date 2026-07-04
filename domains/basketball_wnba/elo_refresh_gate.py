"""domains.basketball_wnba.elo_refresh_gate -- WNBA frozen-Elo-base refresh gate.

MOTIVATION (wave-30): rest_covariate_gate reported the FROZEN Elo base
DEGENERATE (bss_vs_coin_base ~ -0.006 to -0.012) on its 2026 within-season
walk-forward fold, while pregame_gate_verdict.json reports it healthy on 2026
(bss_vs_coin 0.0634-0.0826). Both correct; DIFFERENT constructions --
SEASON-POOLED (raw p_home_elo, whole season) vs WITHIN-SEASON SPLIT
(chronological 70/30 cut + logistic refit on train, ~49-51-game tail). See
elo_refresh_gate_io.reproduce_fold_discrepancy() for the reconciled numbers.

CANDIDATES (pre-registered, fit nothing on eval data; standalone in THIS
module -- ratings.py / elo_config.py stay FROZEN):
  C1 = MOV multiplier Elo: mult = log(1+|margin|) *
       (2.2/((elo_diff_pregame*0.001)+2.2)); delta = ELO_K * mult * (s_home-p).
  C2 = neutral_site-aware HFA (HFA=0 when neutral_site, else ELO_HFA).
  C3 = C1 + C2. BASELINE per fold = cold-started, single-season replay of the
  frozen update rule (apples-to-apples -- see _within_season_fold docstring).

EVAL: within-season walk-forward (matching rest_covariate_gate's fold; 0.70
chronological cut, score on held-out tail) on 2025 AND 2026 separately (2024
= warmup only). Metric: Brier + BSS vs coin. Adoption floor: delta BSS >=
ADOPTION_BSS_FLOOR on BOTH seasons, SAME sign (split = REJECT). PLANTED NULL:
shuffle the margin col within-season; C1 still improving comparably ->
NOT_TESTABLE. No WNBA close corpus -- close_comparison PENDING, calibration
never $/edge (.claude/rules/no-edge-claims.md). DOES NOT EDIT ratings.py /
elo_config.py -- a winning candidate's params are RECORDED in the verdict
only; the swap is a later, separately-reviewed lane. F5: no src.*/kernel.*/
other-domain imports. ASCII stdout only.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from domains.basketball_wnba.elo_config import ELO_K, ELO_MEAN, ELO_HFA, SEASON_REGRESS
from domains.basketball_wnba.ratings import walk_forward_elo, _sorted
from domains.basketball_wnba import elo_refresh_gate_spec as _spec

_REPO = Path(__file__).resolve().parents[2]
_SCOREBOARD = _REPO / "data" / "domains" / "wnba" / "espn_scoreboard.parquet"
_OUT = _REPO / "data" / "domains" / "wnba" / "elo_refresh_verdict.json"
_ROWS_OUT = _REPO / "data" / "domains" / "wnba" / "elo_refresh_rows.parquet"

EVAL_SEASONS = ("2025", "2026")   # 2024 = warmup replay only, never scored (spec)
TRAIN_FRAC = 0.70                 # matches rest_covariate_gate's within-season split
BSS_MIN = 0.003                   # degenerate-base guard (shared convention)
ADOPTION_BSS_FLOOR = 0.003        # min delta BSS required on BOTH seasons, same sign
_NULL_SEED = 20260704
CANDIDATES = ("C1_mov", "C2_neutral_hfa", "C3_mov_neutral")


def _brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _bss_vs_coin(y: np.ndarray, p: np.ndarray) -> float:
    br, br_coin = _brier(y, p), _brier(y, np.full(len(y), 0.5))
    return (br_coin - br) / br_coin if br_coin > 0 else 0.0


# ---------------------------------------------------------------------------
# Candidate replay engines (standalone; elo_config constants reused, unmodified)
# ---------------------------------------------------------------------------


def _replay_candidate(df: pd.DataFrame, use_mov: bool, neutral_aware: bool) -> pd.DataFrame:
    """Walk-forward replay mirroring ratings.walk_forward_elo's snapshot-before-
    update contract. use_mov multiplies the K-update by a MOV factor (reads
    margin_for_replay col); neutral_aware zeroes HFA on neutral_site rows.
    Emits leak-free p_home_candidate the same way the frozen baseline does."""
    d = _sorted(df)
    state_elo: Dict[str, float] = {}
    state_last_season: Dict[str, int] = {}
    p_homes: List[float] = []

    margin_col = "margin_for_replay" if "margin_for_replay" in d.columns else None

    for i in range(len(d)):
        home = str(d["home_team"].iloc[i])
        away = str(d["away_team"].iloc[i])
        season = int(d["season"].iloc[i])
        home_win = float(d["home_win"].iloc[i])
        neutral = bool(d["neutral_site"].iloc[i]) if "neutral_site" in d.columns else False

        for team in (home, away):
            if team not in state_elo:
                state_elo[team] = ELO_MEAN
                state_last_season[team] = season
            else:
                prev = state_last_season.get(team)
                if prev is not None and prev != season:
                    state_elo[team] += SEASON_REGRESS * (ELO_MEAN - state_elo[team])
                    state_last_season[team] = season

        hfa = 0.0 if (neutral_aware and neutral) else ELO_HFA
        elo_diff_hfa = (state_elo[home] + hfa) - state_elo[away]
        p = 1.0 / (1.0 + math.pow(10.0, -elo_diff_hfa / 400.0))
        p_homes.append(p)

        s_home = 1.0 if home_win >= 0.5 else 0.0
        k_mult = 1.0
        if use_mov and margin_col is not None:
            margin = abs(float(d[margin_col].iloc[i]))
            k_mult = math.log(1.0 + margin) * (2.2 / ((abs(elo_diff_hfa) * 0.001) + 2.2))
            k_mult = max(k_mult, 0.10)  # floor: a 0-margin shuffled draw must not zero the update
        delta = ELO_K * k_mult * (s_home - p)
        state_elo[home] += delta
        state_elo[away] -= delta
        state_last_season[home] = season
        state_last_season[away] = season

    out = d.copy()
    out["p_home_candidate"] = p_homes
    return out


def build_corpus(scoreboard_path: Optional[Path] = None) -> pd.DataFrame:
    """Load ESPN scoreboard; attach FROZEN baseline p_home_elo + true margin +
    a season-shuffled planted-null margin column (for the C1 null check)."""
    path = scoreboard_path or _SCOREBOARD
    df = pd.read_parquet(path)
    df = df[df["home_win"].notna()].copy()
    df["date"] = pd.to_datetime(df["date"])

    base = walk_forward_elo(df)
    base["margin_true"] = (base["home_score"] - base["away_score"]).abs()

    rng = np.random.default_rng(_NULL_SEED)
    shuffled = np.full(len(base), np.nan)
    for s in base["season"].dropna().unique():
        mask = (base["season"] == s).to_numpy()
        vals = base.loc[mask, "margin_true"].to_numpy()
        shuffled[mask] = rng.permutation(vals)
    base["margin_null"] = shuffled
    return base


@dataclass
class FoldResult:
    season: str
    candidate: str
    n_train: int
    n_test: int
    brier_base: float
    brier_cand: float
    brier_delta: float
    bss_base: float
    bss_cand: float
    bss_delta: float
    base_degenerate: bool
    cand_improves: bool

    def to_dict(self) -> Dict:
        return {k: (round(v, 6) if isinstance(v, float) else v)
                for k, v in self.__dict__.items()}


def _within_season_fold(full_df: pd.DataFrame, season: str, use_mov: bool,
                         neutral_aware: bool, candidate_name: str,
                         margin_col: str = "margin_true") -> Optional[FoldResult]:
    """Within-season TRAIN_FRAC/rest chronological split (matches
    rest_covariate_gate._fold exactly): replay over the full season so ratings
    accumulate correctly, score both models on the held-out TEST tail only.

    p_base is NOT full_df's warm, multi-season-accumulated p_home_elo column
    (carries cross-season Elo/regress state the candidate never sees) -- it is
    _replay_candidate(use_mov=False, neutral_aware=False) COLD-started on this
    SAME single-season slice, so base and candidate share an identical
    accumulation start and bss_delta isolates only the update-rule change."""
    sdf = full_df[full_df["season"] == season].copy()
    sdf = sdf.sort_values("date", kind="mergesort").reset_index(drop=True)
    n = len(sdf)
    if n < 40:
        return None
    cut = int(n * TRAIN_FRAC)
    n_train, n_test = cut, n - cut
    if n_train < 20 or n_test < 15:
        return None

    sdf = sdf.rename(columns={margin_col: "margin_for_replay"})
    test_base = _replay_candidate(sdf, use_mov=False, neutral_aware=False).iloc[cut:]
    test = _replay_candidate(sdf, use_mov=use_mov, neutral_aware=neutral_aware).iloc[cut:]

    y_te = test["home_win"].to_numpy(dtype=float)
    p_base = test_base["p_home_candidate"].to_numpy(dtype=float)
    p_cand = test["p_home_candidate"].to_numpy(dtype=float)

    br_base, br_cand = _brier(y_te, p_base), _brier(y_te, p_cand)
    bss_base, bss_cand = _bss_vs_coin(y_te, p_base), _bss_vs_coin(y_te, p_cand)

    return FoldResult(
        season=season, candidate=candidate_name, n_train=n_train, n_test=n_test,
        brier_base=br_base, brier_cand=br_cand, brier_delta=br_base - br_cand,
        bss_base=bss_base, bss_cand=bss_cand, bss_delta=bss_cand - bss_base,
        base_degenerate=bool(bss_base < BSS_MIN),
        cand_improves=bool(br_cand < br_base))


_CAND_SPEC = _spec.CAND_SPEC
_CAVEATS = _spec.build_caveats(TRAIN_FRAC, ADOPTION_BSS_FLOOR)


def _candidate_verdict(folds: List[Dict], nfolds: List[Dict]) -> str:
    """SHIP_CANDIDATE requires: both seasons scorable, base non-degenerate, BSS
    delta >= floor on BOTH seasons w/ the SAME positive sign, and (for MOV
    candidates) the planted-null margin failing to replicate >=50% of the lift."""
    if len(folds) < len(EVAL_SEASONS):
        return "INSUFFICIENT_DATA"
    if any(f["base_degenerate"] for f in folds):
        return "INVALID_BASE"
    deltas = [f["bss_delta"] for f in folds]
    if not ({d > 0 for d in deltas} == {True} and
            all(abs(d) >= ADOPTION_BSS_FLOOR for d in deltas)):
        return "REJECT"
    if nfolds and len(nfolds) == len(folds):
        real_mean = float(np.mean(deltas))
        null_mean = float(np.mean([nf["bss_delta"] for nf in nfolds]))
        if real_mean > 0 and null_mean >= 0.5 * real_mean:
            return "NOT_TESTABLE"
    return "SHIP_CANDIDATE"


def run(scoreboard_path: Optional[Path] = None) -> Dict:
    if not (scoreboard_path or _SCOREBOARD).exists():
        return {"verdict": "INSUFFICIENT_DATA",
                "caveats": ["espn_scoreboard.parquet not on disk"]}

    from domains.basketball_wnba.elo_refresh_gate_io import reproduce_fold_discrepancy
    feat = build_corpus(scoreboard_path)
    discrepancy = reproduce_fold_discrepancy(feat, TRAIN_FRAC, _bss_vs_coin)

    results: Dict[str, List[Dict]] = {c: [] for c in CANDIDATES}
    null_results: Dict[str, List[Dict]] = {c: [] for c in CANDIDATES}
    for cname, spec in _CAND_SPEC.items():
        for s in EVAL_SEASONS:
            fr = _within_season_fold(feat, s, candidate_name=cname,
                                      margin_col="margin_true", **spec)
            if fr is not None:
                results[cname].append(fr.to_dict())
            if spec["use_mov"]:
                nfr = _within_season_fold(feat, s, candidate_name=cname + "_NULL",
                                           margin_col="margin_null", **spec)
                if nfr is not None:
                    null_results[cname].append(nfr.to_dict())

    verdicts: Dict[str, str] = {}
    recommended = None
    for cname in CANDIDATES:
        verdicts[cname] = _candidate_verdict(results[cname], null_results.get(cname, []))
        if verdicts[cname] == "SHIP_CANDIDATE" and recommended is None:
            recommended = cname

    overall = "SHIP_CANDIDATE" if recommended else (
        "NOT_TESTABLE" if "NOT_TESTABLE" in verdicts.values() else
        "REJECT" if all(v in ("REJECT", "INVALID_BASE") for v in verdicts.values()) else
        "INSUFFICIENT_DATA")

    return {
        "verdict": overall,
        "recommended_candidate": recommended,
        "candidate_verdicts": verdicts,
        "candidate_folds": results,
        "candidate_null_folds": null_results,
        "fold_discrepancy_explained": discrepancy,
        "eval_seasons": list(EVAL_SEASONS),
        "train_frac": TRAIN_FRAC,
        "adoption_bss_floor": ADOPTION_BSS_FLOOR,
        "close_comparison": "PENDING_CLOSE_COMPARISON",
        "caveats": _CAVEATS,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    from domains.basketball_wnba.elo_refresh_gate_io import report, write, write_rows
    ap = argparse.ArgumentParser(description="Gate WNBA frozen-Elo-base refresh candidates.")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    payload = run()
    print(report(payload))
    if not a.no_write:
        print("wrote %s" % write(payload, _OUT))
        if _SCOREBOARD.exists():
            print("wrote %s" % write_rows(build_corpus(), _ROWS_OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_corpus", "run", "FoldResult", "EVAL_SEASONS", "TRAIN_FRAC",
           "BSS_MIN", "ADOPTION_BSS_FLOOR", "CANDIDATES", "_bss_vs_coin",
           "_brier", "_OUT", "_ROWS_OUT", "_SCOREBOARD"]
