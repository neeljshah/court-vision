"""domains.basketball_wnba.rest_covariate_gate -- WNBA rest-differential pregame
calibration gate (logit-additive covariate on the FROZEN walk-forward Elo base).

QUESTION: does rest_diff = days_since_last_game(home) - days_since_last_game(away)
(strictly-prior, from data/domains/wnba/espn_scoreboard.parquet) improve held-out
calibration OVER the FROZEN walk-forward Elo baseline (domains.basketball_wnba.
ratings.walk_forward_elo -- REUSED, not rebuilt)?

DESIGN (mirrors scripts/platformkit/nba_travel_gate_run.py's logit-additive
pattern; within-season-only since only 2 independent corpora exist, 2024 held
out per lane spec): BASE = logistic(z=logit(p_home_elo)); +REST =
logistic([z, zstd(rest_diff)]). Both fit on the first TRAIN_FRAC of each season
(chronological), scored on the rest of that SAME season -- leak-free, never
pooling seasons. rest_diff itself: date(g) - date(team's most recent STRICTLY-
EARLIER game, any season) -- pure schedule quantity; first appearance -> NaN.

PLANTED NULL (mandatory): rest_diff shuffled WITHIN each season. If the null
captures a comparable Brier lift to the real column, the gate cannot
distinguish signal from noise here -> NOT_TESTABLE (reported, not hidden).

NO CLOSE COMPARISON: no WNBA close corpus exists (see pregame_gate.py) --
close_comparison stays PENDING; MATCH-not-beat internal-baseline framing only.
CALIBRATION ONLY, never a market edge. See .claude/rules/no-edge-claims.md.

F5: no src.*/kernel.*/other-domain imports; scipy-free. <=300 LOC. ASCII stdout.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from domains.basketball_wnba.ratings import walk_forward_elo

_REPO = Path(__file__).resolve().parents[2]
_SCOREBOARD = _REPO / "data" / "domains" / "wnba" / "espn_scoreboard.parquet"
_OUT = _REPO / "data" / "domains" / "wnba" / "rest_covariate_verdict.json"

SEASONS = ("2025", "2026")   # >=2 independent corpora; 2024 held out (spec)
TRAIN_FRAC = 0.70            # leak-free chronological split within-season
BSS_MIN = 0.003              # adoption floor: min Brier-skill-vs-coin-flip
_NULL_SEED = 20260704


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1.0 - 1e-6)
    return np.log(p / (1.0 - p))

def _zstd(x: np.ndarray, mu: float, sd: float) -> np.ndarray:
    return (np.asarray(x, dtype=float) - mu) / (sd if sd > 0 else 1.0)

def _fit_logistic(X: np.ndarray, y: np.ndarray, iters: int = 200,
                   lr: float = 0.2, l2: float = 1e-4) -> np.ndarray:
    """Batch-GD logistic w/ intercept (deterministic, no scipy; mirrors nba_travel_gate_run)."""
    n, d = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(d + 1)
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(Xb @ w, -30, 30)))
        grad = Xb.T @ (p - y) / n + l2 * np.concatenate([[0.0], w[1:]])
        w -= lr * grad
    return w

def _predict(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    Xb = np.hstack([np.ones((len(X), 1)), X])
    return 1.0 / (1.0 + np.exp(-np.clip(Xb @ w, -30, 30)))

def _brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))

def _log_loss(y: np.ndarray, p: np.ndarray, eps: float = 1e-7) -> float:
    pc = np.clip(p, eps, 1.0 - eps)
    return float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)))


def _days_since_last_game(df: pd.DataFrame) -> pd.DataFrame:
    """Per-team strictly-prior days-since-last-game across ALL seasons on disk (a
    team's rest before its season-opener legitimately depends on its last game of
    the prior season -- a schedule fact, not a leak). First appearance -> NaN."""
    base = df[["event_id", "date", "home_team", "away_team"]]
    long_df = pd.concat([
        base.rename(columns={"home_team": "team"})[["event_id", "date", "team"]],
        base.rename(columns={"away_team": "team"})[["event_id", "date", "team"]],
    ], ignore_index=True).sort_values(["team", "date"], kind="mergesort")
    long_df["prev_date"] = long_df.groupby("team")["date"].shift(1)
    long_df["days_rest"] = (long_df["date"] - long_df["prev_date"]).dt.days.astype(float)

    home_rest = long_df.rename(columns={"team": "home_team", "days_rest": "home_rest"})
    home_rest = home_rest[["event_id", "home_team", "home_rest"]]
    away_rest = long_df.rename(columns={"team": "away_team", "days_rest": "away_rest"})
    away_rest = away_rest[["event_id", "away_team", "away_rest"]]

    out = df.merge(home_rest, on=["event_id", "home_team"], how="left")
    out = out.merge(away_rest, on=["event_id", "away_team"], how="left")
    out["rest_diff"] = out["home_rest"] - out["away_rest"]
    return out

def build_corpus() -> pd.DataFrame:
    """Load ESPN scoreboard; attach FROZEN walk-forward Elo + rest_diff + a
    within-season-shuffled planted-null control column."""
    df = pd.read_parquet(_SCOREBOARD)
    df = df[df["home_win"].notna()].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = _days_since_last_game(df)

    feat = walk_forward_elo(df)  # season col stays the string label ("2024"/"2025"/"2026")

    rng = np.random.default_rng(_NULL_SEED)
    shuffled = np.full(len(feat), np.nan)
    for s in feat["season"].dropna().unique():
        mask = (feat["season"] == s).to_numpy()
        vals = feat.loc[mask, "rest_diff"].to_numpy()
        shuffled[mask] = rng.permutation(vals)
    feat["rest_diff_null"] = shuffled
    return feat

@dataclass
class FoldResult:
    season: str
    n_train: int
    n_test: int
    brier_base: float
    brier_feat: float
    brier_delta: float
    logloss_base: float
    logloss_feat: float
    bss_vs_coin_base: float
    base_degenerate: bool
    feat_improves: bool

    def to_dict(self) -> Dict:
        return {k: (round(v, 6) if isinstance(v, float) else v)
                for k, v in self.__dict__.items()}

def _fold(season_df: pd.DataFrame, season: str, col: str) -> Optional[FoldResult]:
    """Chronological TRAIN_FRAC/rest split WITHIN one season (leak-free walk-forward)."""
    sdf = season_df.dropna(subset=[col, "p_home_elo", "home_win"]).copy()
    sdf = sdf.sort_values("date", kind="mergesort").reset_index(drop=True)
    n = len(sdf)
    if n < 40:
        return None
    cut = int(n * TRAIN_FRAC)
    train, test = sdf.iloc[:cut], sdf.iloc[cut:]
    if len(train) < 20 or len(test) < 15:
        return None

    z_tr = _logit(train["p_home_elo"].to_numpy())
    z_te = _logit(test["p_home_elo"].to_numpy())
    fmu, fsd = float(train[col].mean()), float(train[col].std())
    f_tr = _zstd(train[col].to_numpy(), fmu, fsd)
    f_te = _zstd(test[col].to_numpy(), fmu, fsd)
    y_tr = train["home_win"].to_numpy(dtype=float)
    y_te = test["home_win"].to_numpy(dtype=float)

    w_base = _fit_logistic(z_tr.reshape(-1, 1), y_tr)
    w_feat = _fit_logistic(np.column_stack([z_tr, f_tr]), y_tr)
    p_base = _predict(w_base, z_te.reshape(-1, 1))
    p_feat = _predict(w_feat, np.column_stack([z_te, f_te]))

    br_base, br_feat = _brier(y_te, p_base), _brier(y_te, p_feat)
    ll_base, ll_feat = _log_loss(y_te, p_base), _log_loss(y_te, p_feat)
    br_coin = _brier(y_te, np.full(len(y_te), 0.5))
    bss_base = (br_coin - br_base) / br_coin if br_coin > 0 else 0.0

    return FoldResult(
        season=season, n_train=len(train), n_test=len(test),
        brier_base=br_base, brier_feat=br_feat, brier_delta=br_base - br_feat,
        logloss_base=ll_base, logloss_feat=ll_feat, bss_vs_coin_base=bss_base,
        base_degenerate=bool(bss_base < BSS_MIN),
        feat_improves=bool(br_feat < br_base and ll_feat < ll_base))


@dataclass
class RestGateVerdict:
    verdict: str
    folds: List[Dict] = field(default_factory=list)
    null_folds: List[Dict] = field(default_factory=list)
    null_comparable: bool = False
    caveats: List[str] = field(default_factory=list)
    close_comparison: str = "PENDING_CLOSE_COMPARISON"

    def to_dict(self) -> Dict:
        return {"verdict": self.verdict, "folds": self.folds,
                "null_folds": self.null_folds,
                "null_comparable": self.null_comparable,
                "caveats": list(self.caveats),
                "close_comparison": self.close_comparison}

def _decide(folds: List[FoldResult], null_folds: List[FoldResult]) -> tuple:
    """REJECT/INVALID_BASE take priority; else compare the null's Brier lift to the
    real column's -- a null capturing >=50% of it means the gate cannot tell signal
    from noise here (NOT_TESTABLE, an added-flexibility artifact, not a real find)."""
    if not folds:
        return "INSUFFICIENT_DATA", False
    if any(f.base_degenerate for f in folds):
        return "INVALID_BASE", False
    if not all(f.feat_improves for f in folds):
        return "REJECT", False
    null_comparable = False
    if null_folds and len(null_folds) == len(folds):
        real_mean = float(np.mean([f.brier_delta for f in folds]))
        null_mean = float(np.mean([nf.brier_delta for nf in null_folds]))
        null_comparable = bool(all(nf.feat_improves for nf in null_folds) and
                                real_mean > 0 and null_mean >= 0.5 * real_mean)
    if null_comparable:
        return "NOT_TESTABLE", True
    return "SHIP_CANDIDATE", False

def run() -> RestGateVerdict:
    caveats = [
        "BASE = FROZEN walk-forward Elo logit (domains.basketball_wnba.ratings, "
        "unmodified). +REST = logistic on [elo_logit, zstd(rest_diff)]; leak-free "
        "schedule quantity (strictly-earlier games only).",
        "Within-season chronological %.0f/%.0f split, 2024 held out per lane spec, "
        "no pooling across seasons." % (TRAIN_FRAC * 100, (1 - TRAIN_FRAC) * 100),
        "No WNBA close corpus exists -- close_comparison is PENDING; MATCH-not-beat "
        "vs INTERNAL Elo baseline only, calibration never edge.",
        "PLANTED NULL: rest_diff shuffled WITHIN each season; null capturing >=50% "
        "of the real Brier lift -> NOT_TESTABLE (added-flexibility artifact).",
    ]
    if not _SCOREBOARD.exists():
        return RestGateVerdict("INSUFFICIENT_DATA", caveats=caveats + [
            "espn_scoreboard.parquet not on disk"])

    feat = build_corpus()
    folds, null_folds = [], []
    for s in SEASONS:
        sdf = feat[feat["season"] == s].copy()
        f = _fold(sdf, s, "rest_diff")
        nf = _fold(sdf, s, "rest_diff_null")
        if f is not None:
            folds.append(f)
        if nf is not None:
            null_folds.append(nf)

    if len(folds) < len(SEASONS):
        return RestGateVerdict("INSUFFICIENT_DATA",
                               [f.to_dict() for f in folds],
                               [nf.to_dict() for nf in null_folds],
                               caveats=caveats + ["need >=2 scorable season folds"])

    verdict, null_comparable = _decide(folds, null_folds)
    if any(f.base_degenerate for f in folds):
        caveats.append(
            "DEGENERATE-BASE GUARD tripped: Elo BASE Brier-skill-vs-coin-flip < "
            "%.3f on >=1 season fold -- too little separable signal for a "
            "'+REST improves' claim to mean much." % BSS_MIN)
    return RestGateVerdict(verdict, [f.to_dict() for f in folds],
                           [nf.to_dict() for nf in null_folds],
                           null_comparable, caveats)

def write(v: RestGateVerdict, out: Optional[Path] = None) -> str:
    dest = Path(out) if out is not None else _OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = v.to_dict()
    payload["corpus_source"] = "data/domains/wnba/espn_scoreboard.parquet"
    payload["seasons"] = list(SEASONS)
    payload["bss_min"] = BSS_MIN
    with open(dest, "w", encoding="ascii") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    return str(dest)

def _report(v: RestGateVerdict) -> str:
    lines = ["=" * 76, "WNBA REST-DIFF PREGAME COVARIATE GATE", "=" * 76,
             "VERDICT: %s" % v.verdict, "-" * 76]
    for f in v.folds:
        lines.append("season %s: Brier %.6f -> %.6f (d %.7f)  base_BSS=%.5f  "
                      "degenerate=%s  improves=%s" % (
                          f["season"], f["brier_base"], f["brier_feat"],
                          f["brier_delta"], f["bss_vs_coin_base"],
                          f["base_degenerate"], f["feat_improves"]))
    lines.append("-" * 76 + "\nPLANTED NULL (rest_diff shuffled within season):")
    for nf in v.null_folds:
        lines.append("season %s: Brier delta %.7f  improves=%s" % (
            nf["season"], nf["brier_delta"], nf["feat_improves"]))
    lines += ["null_comparable_to_real=%s" % v.null_comparable, "-" * 76,
             "close_comparison: %s -- calibration only, NO $/edge/ROI." % v.close_comparison,
             "=" * 76]
    return "\n".join(lines)

def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Gate the WNBA rest-diff pregame covariate.")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    v = run()
    print(_report(v))
    if not a.no_write:
        print("wrote %s" % write(v))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

__all__ = ["build_corpus", "run", "write", "main", "RestGateVerdict", "FoldResult",
           "SEASONS", "TRAIN_FRAC", "BSS_MIN"]
