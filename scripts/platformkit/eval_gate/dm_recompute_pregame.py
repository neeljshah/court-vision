"""Recompute the pregame beat-the-close rows with a clustered Diebold-Mariano interval.

Rebuilds the per-game rows behind three rows of docs/MARKET_EFFICIENCY_PROOF.md by calling
the SAME proof-harness functions (read-only reuse, no reimplementation of any model):

  MLB moneyline   proof_mlb/beat_the_close_ml.py     (walk-forward MOV-Elo; held-out 2nd half)
  Soccer O/U-2.5  proof_soccer/beat_the_close_ou.py  (EW Poisson + Platt fit on 1st half)
  NBA moneyline   proof_nba/ml_accuracy.py           (walk-forward MOV-Elo; held-out 2nd half)

For each row on the holdout: d = loss_model - loss_close (squared error per game), the
game-clustered 95 pct interval + two-tailed DM p from eval_gate/dm_test.py, BSS vs the close,
the post-hoc MDE = 1.429 * half-width (docs/evidence/POWER_PAGE_2026-09-22.md), and the verdict
rule: MATCHES_CLOSE only if the CI includes 0, else TRAILS_CLOSE (d > 0) or BEATS_CLOSE (d < 0).
The close is the harness's own devig (proportional); a Shin-devigged close is a sensitivity.
Calibration measurement only.

Run: python -m scripts.platformkit.eval_gate.dm_recompute_pregame [--json OUT] [--dump-nba CSV]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.eval_gate.dm_test import diebold_mariano  # noqa: E402
from scripts.platformkit.eval_gate.shin import shin_devig  # noqa: E402

MDE_FACTOR = 1.429          # (z_0.975 + z_0.80) / z_0.975, POWER_PAGE_2026-09-22.md
_EPS = 1e-6                 # the harnesses clip at 1e-6 before Brier; keep parity


def verdict(lo: float, hi: float) -> str:
    """Written rule: MATCHES_CLOSE only if the CI on (model - close) loss includes 0."""
    if lo <= 0.0 <= hi:
        return "MATCHES_CLOSE"
    return "TRAILS_CLOSE" if lo > 0.0 else "BEATS_CLOSE"


def _shin_one(h: float, a: float) -> float:
    try:
        return float(shin_devig([h, a])[0][0])
    except ValueError:          # booksum < 1 or a non-price: no Shin fair prob, row dropped
        return float("nan")


def _shin_home(imp_h: np.ndarray, imp_a: np.ndarray) -> np.ndarray:
    return np.array([_shin_one(h, a) for h, a in zip(imp_h, imp_a)])


def summarize(rows: pd.DataFrame, close_col: str = "p_close") -> Dict:
    """Score the holdout rows: Brier, gap, clustered DM interval, BSS, MDE, verdict."""
    h = rows[(rows["split"] == "holdout") & rows[close_col].notna()]
    y = h["y"].to_numpy(float)
    pm = np.clip(h["p_model"].to_numpy(float), _EPS, 1 - _EPS)
    pc = np.clip(h[close_col].to_numpy(float), _EPS, 1 - _EPS)
    lm, lc = (pm - y) ** 2, (pc - y) ** 2
    d = lm - lc                                   # > 0 => the close is sharper
    res = diebold_mariano(d, h["cluster_id"].astype(str).tolist())
    lo, hi = res.ci95
    hw = (hi - lo) / 2.0
    by_date = diebold_mariano(d, h["date"].astype(str).tolist())
    return {
        "n": int(len(h)), "n_clusters": res.n_clusters,
        "model_brier": float(lm.mean()), "close_brier": float(lc.mean()),
        "gap": float(d.mean()), "ci95": [float(lo), float(hi)], "dm_p": res.p_value,
        "dm_stat": res.dm_stat, "bss_vs_close": float(1.0 - lm.mean() / lc.mean()),
        "half_width": float(hw), "mde": float(MDE_FACTOR * hw),
        "verdict": verdict(lo, hi),
        "date_clustered_ci95": [float(x) for x in by_date.ci95],
        "date_clusters": by_date.n_clusters,
    }


def _split(n: int) -> List[str]:
    mid = n // 2
    return ["fit"] * mid + ["holdout"] * (n - mid)


def rows_mlb() -> pd.DataFrame:
    from scripts.platformkit.proof_mlb import beat_the_close_ml as h
    games = pd.read_parquet(h._GAMES)
    odds = pd.read_parquet(h._ODDS)[["event_id", "ml_close_home_am", "ml_close_away_am"]]
    games = games.sort_values(["date", "game_seq", "event_id"]).reset_index(drop=True)
    games["p_model"] = h._walk_forward_elo(games)
    odds = odds.dropna(subset=["ml_close_home_am", "ml_close_away_am"]).copy()
    ih = odds["ml_close_home_am"].map(h.american_to_prob).to_numpy(float)
    ia = odds["ml_close_away_am"].map(h.american_to_prob).to_numpy(float)
    odds["p_close"] = ih / (ih + ia)
    odds["p_close_shin"] = _shin_home(ih, ia)
    m = games.merge(odds[["event_id", "p_close", "p_close_shin"]], on="event_id", how="inner")
    m = m.sort_values(["date", "game_seq", "event_id"]).reset_index(drop=True)
    m["y"] = (m["home_runs"] > m["away_runs"]).astype(float)
    m["cluster_id"] = m["event_id"].astype(str)
    m["split"] = _split(len(m))
    return m


def rows_soccer() -> pd.DataFrame:
    from scripts.platformkit.proof_soccer import beat_the_close_ou as h
    model = h._build_model_forecast(h._MATCHES, h._STATS)
    odds = pd.read_parquet(h._ODDS).dropna(subset=["pc_over", "pc_under"]).copy()
    odds = odds[(odds["pc_over"] > 1.0) & (odds["pc_under"] > 1.0)]
    io, iu = 1.0 / odds["pc_over"].to_numpy(float), 1.0 / odds["pc_under"].to_numpy(float)
    odds["p_close"] = io / (io + iu)
    odds["p_close_shin"] = _shin_home(io, iu)
    m = model.merge(odds[["event_id", "p_close", "p_close_shin"]], on="event_id", how="inner")
    m["date"] = pd.to_datetime(m["date"])
    m = m.sort_values("date", kind="mergesort").reset_index(drop=True)
    m = m.dropna(subset=["p_model_raw", "p_close", "target_over25"]).reset_index(drop=True)
    m["y"] = m["target_over25"].astype(float)
    m["split"] = _split(len(m))
    tr = m["split"] == "fit"
    a, b = h._fit_platt(m.loc[tr, "p_model_raw"].to_numpy(float), m.loc[tr, "y"].to_numpy(float))
    m["p_model"] = h._apply_platt(m["p_model_raw"].to_numpy(float), a, b)
    m["cluster_id"] = m["event_id"].astype(str)
    return m


def rows_nba() -> pd.DataFrame:
    from scripts.platformkit.proof_nba import ml_accuracy as h
    box = h.load_box(h._NBA)
    box["p_model"] = h._walk_forward_elo(box)
    raw = pd.read_parquet(h._NBA / "odds.parquet").rename(
        columns={"home_team": "home_abbr", "away_team": "away_abbr"})
    raw["date"] = pd.to_datetime(raw["date"])
    raw = raw.dropna(subset=["home_ml", "away_ml"]).copy()
    ih = raw["home_ml"].map(h.american_to_prob).to_numpy(float)
    ia = raw["away_ml"].map(h.american_to_prob).to_numpy(float)
    raw["p_close"] = ih / (ih + ia)
    raw["p_close_shin"] = _shin_home(ih, ia)
    m = box.merge(raw[["date", "home_abbr", "away_abbr", "p_close", "p_close_shin"]],
                  on=["date", "home_abbr", "away_abbr"], how="inner").reset_index(drop=True)
    m["y"] = (m["home_pts"] > m["away_pts"]).astype(float)
    m["cluster_id"] = (m["date"].dt.strftime("%Y-%m-%d") + "_" + m["away_abbr"] + "@"
                       + m["home_abbr"])
    m["split"] = _split(len(m))
    return m


INPUTS = {
    "mlb_moneyline": ["data/domains/mlb/games.parquet", "data/domains/mlb/odds.parquet"],
    "soccer_ou25": ["data/domains/soccer/matches.parquet",
                    "data/domains/soccer/match_stats.parquet", "data/domains/soccer/odds.parquet"],
    "nba_moneyline": ["data/domains/basketball_nba/espn_boxscores.parquet",
                      "data/domains/basketball_nba/odds.parquet"],
}
BUILDERS = {"mlb_moneyline": rows_mlb, "soccer_ou25": rows_soccer, "nba_moneyline": rows_nba}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="write the full result dict here")
    ap.add_argument("--dump-nba", help="write NBA per-game rows (devigged probs only) here")
    args = ap.parse_args(argv)
    out: Dict = {}
    for key, build in BUILDERS.items():
        paths = [_REPO / p for p in INPUTS[key]]
        missing = [str(p.relative_to(_REPO)) for p in paths if not p.is_file()]
        if missing:
            out[key] = {"status": "corpus_missing", "missing": missing}
            print(f"{key}: CORPUS MISSING {missing}")
            continue
        rows = build()
        rep = summarize(rows)
        rep["shin_close"] = summarize(rows, "p_close_shin")
        rep["inputs"] = {str(p.relative_to(_REPO)).replace("\\", "/"): sha256(p) for p in paths}
        out[key] = rep
        print(f"{key}: n={rep['n']} model={rep['model_brier']:.4f} close={rep['close_brier']:.4f}"
              f" gap={rep['gap']:+.4f} ci=[{rep['ci95'][0]:+.4f},{rep['ci95'][1]:+.4f}]"
              f" p={rep['dm_p']:.4g} bss={rep['bss_vs_close']:+.4f} mde={rep['mde']:.4f}"
              f" {rep['verdict']} | shin gap={rep['shin_close']['gap']:+.4f}"
              f" ci=[{rep['shin_close']['ci95'][0]:+.4f},{rep['shin_close']['ci95'][1]:+.4f}]"
              f" {rep['shin_close']['verdict']}")
        if key == "nba_moneyline" and args.dump_nba:
            dump = rows.assign(date=rows["date"].dt.strftime("%Y-%m-%d"))[
                ["date", "cluster_id", "home_abbr", "away_abbr", "split", "p_model",
                 "p_close_shin", "p_close", "y"]].rename(columns={
                    "cluster_id": "game_key", "p_model": "p_model_home",
                    "p_close_shin": "p_close_shin_home", "p_close": "p_close_prop_home",
                    "y": "home_win"})
            dump.insert(7, "close_source", "data/domains/basketball_nba/odds.parquet")
            dump.to_csv(args.dump_nba, index=False, float_format="%.6f", lineterminator="\n")
            print(f"wrote {len(dump)} rows -> {args.dump_nba}")
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2) + "\n", encoding="ascii")
    return 0


if __name__ == "__main__":
    sys.exit(main())
