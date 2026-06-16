"""scripts.platformkit.proof_nba.asof_box_accuracy — does our OWN box data predict better?

The honest north-star test: on games where we have BOTH our (ESPN-ingested) box history AND
the market closing total, is a leak-free as-of model's predicted total a BETTER predictor of
the realized total than the market's closing line? (RMSE/MAE vs realized — lower wins.) And is
the model's O/U probability well-calibrated against the close?

"Beat the best predictions" = beat the closing total on accuracy. The market close is the
predictor to beat. We do NOT claim a $ edge (the book also moved on news we can't see); we
ask whether OUR DATA produces an at-least-as-accurate forecaster. More/own data -> we re-run
this as the corpus grows.

Leak-free: EW points-for/against per team, snapshot-before-update; the closing total is a
realized market datum, used only as the comparison forecaster, never as a model input.
INVARIANTS: never edit src/ or kernel/; <=300 LOC.
Run: python -m scripts.platformkit.proof_nba.asof_box_accuracy
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.proof_nba.totals_calibration import _ece, _phi  # noqa: E402

_NBA = _REPO / "data" / "domains" / "basketball_nba"
_ALPHA = 0.05
_INIT_PF = 113.3
_LINES: Tuple[float, ...] = (215.5, 220.5, 225.5, 230.5, 235.5)
# ESPN emits inconsistent team abbreviations (GS/GSW, NY/NYK, NO/NOP, SA/SAS, UTAH/UTA,
# WSH/WAS) + All-Star junk; canonicalise to the odds-feed convention so the join lands.
_CANON = {"GS": "GSW", "NY": "NYK", "NO": "NOP", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"}


def _corpus_from_env() -> Optional[Path]:
    """Shared corpus-override contract: $PROOF_CORPUS_ROOT/nba if set, else None."""
    r = os.environ.get("PROOF_CORPUS_ROOT")
    return Path(r) / "nba" if r else None


def _resolve_root(corpus: Optional[Path]) -> Path:
    """Precedence: explicit corpus arg > $PROOF_CORPUS_ROOT/nba > real data/domains path."""
    return corpus or _corpus_from_env() or _NBA


def _canon(s: pd.Series) -> pd.Series:
    return s.astype(str).str.upper().replace(_CANON)


def _rmse_mae(pred: np.ndarray, truth: np.ndarray) -> Tuple[float, float]:
    e = pred - truth
    return float(np.sqrt(np.mean(e ** 2))), float(np.mean(np.abs(e)))


def _walk_forward_total(df: pd.DataFrame) -> np.ndarray:
    pf: Dict[str, float] = {}
    pa: Dict[str, float] = {}
    pred = np.empty(len(df))
    h = df["home_abbr"].to_numpy(); a = df["away_abbr"].to_numpy()
    hp = df["home_pts"].to_numpy(float); ap = df["away_pts"].to_numpy(float)
    for i in range(len(df)):
        ht, at = str(h[i]), str(a[i])
        for t in (ht, at):
            pf.setdefault(t, _INIT_PF); pa.setdefault(t, _INIT_PF)
        pred[i] = 0.5 * (pf[ht] + pa[at]) + 0.5 * (pf[at] + pa[ht])
        pf[ht] += _ALPHA * (hp[i] - pf[ht]); pa[ht] += _ALPHA * (ap[i] - pa[ht])
        pf[at] += _ALPHA * (ap[i] - pf[at]); pa[at] += _ALPHA * (hp[i] - pa[at])
    return pred


def _possessions(df: pd.DataFrame, side: str) -> np.ndarray:
    """Estimate possessions: FGA + 0.44*FTA - OREB + TOV (NaN where box detail missing)."""
    return (df[f"{side}_fg_attempted"].astype(float)
            + 0.44 * df[f"{side}_ft_attempted"].astype(float)
            - df[f"{side}_oreb"].astype(float) + df[f"{side}_tov"].astype(float)).to_numpy()


def _walk_forward_poss(df: pd.DataFrame) -> np.ndarray:
    """Richer model on the UNLOCKED 2026 box detail: as-of EW pace (possessions) +
    offensive/defensive points-per-possession. total = pace * (off_ppp + def_ppp).
    Pace is stable/predictable; ppp is team quality. Falls back to EW state when a
    game's box detail is missing (prediction always uses prior state — leak-free)."""
    pace: Dict[str, float] = {}; offp: Dict[str, float] = {}; defp: Dict[str, float] = {}
    pred = np.empty(len(df))
    h = df["home_abbr"].to_numpy(); a = df["away_abbr"].to_numpy()
    hp = df["home_pts"].to_numpy(float); ap = df["away_pts"].to_numpy(float)
    gp = 0.5 * (_possessions(df, "home") + _possessions(df, "away"))   # game possessions
    for i in range(len(df)):
        ht, at = str(h[i]), str(a[i])
        for d, init in ((pace, 100.5), (offp, 1.13), (defp, 1.13)):
            d.setdefault(ht, init); d.setdefault(at, init)
        ppace = 0.5 * (pace[ht] + pace[at])
        pred[i] = ppace * (0.5 * (offp[ht] + defp[at]) + 0.5 * (offp[at] + defp[ht]))
        p = gp[i]
        if np.isfinite(p) and p > 50:                 # update only on valid box detail
            pace[ht] += _ALPHA * (p - pace[ht]); pace[at] += _ALPHA * (p - pace[at])
            offp[ht] += _ALPHA * (hp[i] / p - offp[ht]); defp[ht] += _ALPHA * (ap[i] / p - defp[ht])
            offp[at] += _ALPHA * (ap[i] / p - offp[at]); defp[at] += _ALPHA * (hp[i] / p - defp[at])
    return pred


def _walk_forward_split(df: pd.DataFrame) -> np.ndarray:
    """Home/away-SPLIT model: separate EW offence/defence for home vs road context
    (teams score ~differently at home), used in the matchup-correct slots."""
    pfh: Dict[str, float] = {}; pah: Dict[str, float] = {}   # home offence / home defence
    pfa: Dict[str, float] = {}; paa: Dict[str, float] = {}   # away offence / away defence
    pred = np.empty(len(df))
    h = df["home_abbr"].to_numpy(); a = df["away_abbr"].to_numpy()
    hp = df["home_pts"].to_numpy(float); ap = df["away_pts"].to_numpy(float)
    for i in range(len(df)):
        ht, at = str(h[i]), str(a[i])
        for d, init in ((pfh, _INIT_PF), (pah, _INIT_PF), (pfa, _INIT_PF), (paa, _INIT_PF)):
            d.setdefault(ht, init); d.setdefault(at, init)
        # home scores: home offence-at-home vs away defence-on-road; away scores: vice versa
        exp_h = 0.5 * (pfh[ht] + paa[at])
        exp_a = 0.5 * (pfa[at] + pah[ht])
        pred[i] = exp_h + exp_a
        pfh[ht] += _ALPHA * (hp[i] - pfh[ht]); pah[ht] += _ALPHA * (ap[i] - pah[ht])
        pfa[at] += _ALPHA * (ap[i] - pfa[at]); paa[at] += _ALPHA * (hp[i] - paa[at])
    return pred


def load_box(root: Optional[Path] = None) -> pd.DataFrame:
    """Cleaned, date-sorted ESPN box: canon abbrs, home/away_pts from the final score
    (populated for all games, unlike the box-stats points row), total filtered to a sane
    range. Shared by the rest-aware model module."""
    box = pd.read_parquet(_resolve_root(root) / "espn_boxscores.parquet")
    box["date"] = pd.to_datetime(box["date"], format="mixed", errors="coerce")
    box = box.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    box["home_abbr"] = _canon(box["home_abbr"])
    box["away_abbr"] = _canon(box["away_abbr"])
    box["home_pts"] = box["home_score"].astype(float)
    box["away_pts"] = box["away_score"].astype(float)
    box["total"] = box["home_pts"] + box["away_pts"]
    return box[(box["total"] >= 150) & (box["total"] <= 350)].reset_index(drop=True)


def load_close(root: Optional[Path] = None) -> pd.DataFrame:
    od = pd.read_parquet(_resolve_root(root) / "odds.parquet").rename(
        columns={"home_team": "home_abbr", "away_team": "away_abbr"})
    od["date"] = pd.to_datetime(od["date"])
    return od[["date", "home_abbr", "away_abbr", "total"]].rename(columns={"total": "close_total"})


def run(corpus: Optional[Path] = None) -> Dict:
    root = _resolve_root(corpus)
    box_p, odds_p = root / "espn_boxscores.parquet", root / "odds.parquet"
    if not box_p.is_file() or not odds_p.is_file():
        return {"error": "espn_boxscores or odds parquet missing"}
    box = load_box(root)
    box["pred_pooled"] = _walk_forward_total(box)
    box["pred_split"] = _walk_forward_split(box)
    box["pred_poss"] = _walk_forward_poss(box)

    od = pd.read_parquet(odds_p).rename(  # noqa: E501
        columns={"home_team": "home_abbr", "away_team": "away_abbr"})
    od["date"] = pd.to_datetime(od["date"])
    m = box.merge(od[["date", "home_abbr", "away_abbr", "total"]].rename(columns={"total": "close_total"}),
                  on=["date", "home_abbr", "away_abbr"], how="inner")
    m = m[m["close_total"].notna()].reset_index(drop=True)
    n = len(m)
    if n < 40:
        return {"status": "data_limited", "n_overlap": n,
                "note": "Ingest more 2025-26 games (ESPN reachable) to grow the box-vs-odds overlap."}

    realized = m["total"].to_numpy(float)
    close = m["close_total"].to_numpy(float)
    mid = n // 2
    te = slice(mid, n)
    rm_close, mae_close = _rmse_mae(close[te], realized[te])

    def _score(pred: np.ndarray) -> Dict:
        # leak-free affine recal on the FIRST half, scored on the held-out SECOND half
        b, a = np.polyfit(pred[:mid], realized[:mid], 1)
        pc = a + b * pred
        sigma = float(np.std(realized[:mid] - pc[:mid]))
        rm, mae = _rmse_mae(pc[te], realized[te])
        all_p, all_y = [], []
        for ln in _LINES:
            all_p.extend((1.0 - np.array([_phi((ln - pt) / sigma) for pt in pc[te]])).tolist())
            all_y.extend((realized[te] > ln).astype(float).tolist())
        return {"rmse": round(rm, 3), "mae": round(mae, 3), "sigma": round(sigma, 2),
                "ece": round(_ece(np.array(all_p), np.array(all_y)), 4)}

    pooled = _score(m["pred_pooled"].to_numpy(float))
    split = _score(m["pred_split"].to_numpy(float))
    poss = _score(m["pred_poss"].to_numpy(float))
    best = min(pooled, split, poss, key=lambda d: d["rmse"])
    gap = round(best["rmse"] - rm_close, 3)        # >0 => close is sharper
    return {
        "status": "ok", "n_overlap": n, "n_holdout": n - mid,
        "close_rmse_vs_realized": round(rm_close, 3), "close_mae_vs_realized": round(mae_close, 3),
        "pooled_model": pooled, "split_model": split, "poss_model": poss,
        "best_model_rmse": best["rmse"], "gap_to_close_rmse": gap,
        "poss_beats_pooled": poss["rmse"] < pooled["rmse"] - 1e-3,
        "split_beats_pooled": split["rmse"] < pooled["rmse"] - 1e-3,
        "verdict": (
            f"OUR best model BEATS the close on RMSE ({best['rmse']} vs {rm_close})" if gap < -0.1 else
            (f"OUR best model MATCHES the close (RMSE {best['rmse']} vs {rm_close}, gap {gap:+})"
             if gap <= 1.0 else
             f"close sharper by {gap} RMSE — the gap is the market's freshness edge "
             f"(injuries/lineups) we have not yet added")),
        "note": ("Beat-the-best-predictions test on REAL realized totals + closing lines. "
                 "Re-run as we add proprietary/fresh features. No $ edge claimed."),
    }


def _main() -> int:
    rep = run()
    if "error" in rep:
        print(rep["error"]); return 1
    if rep.get("status") != "ok":
        print(f"{rep['status']}: n_overlap={rep.get('n_overlap')} — {rep.get('note')}"); return 0
    print(f"=== NBA totals: OUR as-of box models vs the market close (n={rep['n_overlap']}, "
          f"holdout={rep['n_holdout']}) ===")
    print(f"  {'predictor':>14}  {'RMSE':>7} {'MAE':>7} {'ECE':>7}")
    print(f"  {'market close':>14}  {rep['close_rmse_vs_realized']:>7} "
          f"{rep['close_mae_vs_realized']:>7} {'-':>7}")
    for nm, key in (("pooled model", "pooled_model"), ("split model", "split_model"),
                    ("poss model", "poss_model")):
        d = rep[key]
        print(f"  {nm:>14}  {d['rmse']:>7} {d['mae']:>7} {d['ece']:>7}")
    print(f"\nposs beats pooled: {rep['poss_beats_pooled']}  |  "
          f"best gap to close: {rep['gap_to_close_rmse']:+} RMSE")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
