"""dreb_challenger -- the ONLY replicated NBA mechanism (stint-continuity x
DREB: p=1e-16 on 2025-26, p=1.9e-17 on 2024-25) composed into a team-game
AS-OF feature and fed through the walk-forward game-level gate.

  feature = a team's strictly-prior as-of weighted mean continuity_s over its
            defensive-rebound opportunities (weight = n opportunities that
            game), home-minus-away diff, standardized on the TRAIN prefix.
  candidate = base Elo logit + intercept + beta * feature (same optimizer/
              train/test split as compose/challenger.py -- comparability rail).

PREREG BAR (declared before running):
  per-season MATTERS_PROVISIONAL = delta>0 AND dm_p<0.05 AND delta_t80>0
  (challenger.py's existing single-rung rule).
  cross-season REPLICATED = same-sign MATTERS on >=2 of the 3 seasons run
  (2023-24, 2024-25, 2025-26).

NO dollar/edge language: Brier / log-loss deltas only. An honest per-season
NULL is a catalogued success, not a failure.

CLI: python -m scripts.platformkit.compose.dreb_challenger
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from domains.basketball_nba.prereg.nba_hypotheses import build_continuity_dreb_tagged
from scripts.platformkit.compose.challenger import _base_logit_nba, _standardize
from scripts.platformkit.compose.team_form import _asof_weighted_mean, team_id_to_abbr
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.intel_weighting.relevance_gate import (
    GateResult, _DM_ALPHA, _MIN_TEST, _TRAIN_FRAC, _brier, _fit, _sigmoid,
)
from scripts.platformkit.intel_weighting.weight_ledger import LEDGER, _key

METHOD = "composed_dreb_continuity_walkforward"

_REPO = Path(__file__).resolve().parents[3]
_GAMES = _REPO / "data" / "domains" / "basketball_nba" / "games.parquet"
_TEAM_SYS = _REPO / "data" / "cache" / "team_system"

# season -> (stints parquet, pbp dir). 2025-26's pbp dir is plain "pbp"
# (no season suffix) -- matches the naming every other lane in this repo uses.
SEASONS: Dict[str, Tuple[Path, Path]] = {
    "2023-24": (_TEAM_SYS / "lineups" / "stints_2023_24.parquet", _TEAM_SYS / "pbp_2023_24"),
    "2024-25": (_TEAM_SYS / "lineups" / "stints_2024_25.parquet", _TEAM_SYS / "pbp_2024_25"),
    "2025-26": (_TEAM_SYS / "lineups" / "stints_2025_26.parquet", _TEAM_SYS / "pbp"),
}


def _asof_dreb_feature(stints_path: Path, pbp_dir: Path) -> pd.Series:
    """Strictly-prior weighted mean continuity_s per (game_id, team abbr),
    weight = n D-reb opportunities that game (_asof_weighted_mean's pattern)."""
    tagged = build_continuity_dreb_tagged(pd.read_parquet(stints_path), pbp_dir=pbp_dir)
    per_game = tagged.groupby(["game_id", "team_id"]).agg(
        v=("continuity_s", "mean"), w=("continuity_s", "size")).reset_index()
    abbr = team_id_to_abbr()
    per_game["team"] = per_game["team_id"].map(abbr)
    per_game = per_game[per_game["team"].notna()].copy()
    games = pd.read_parquet(_GAMES)[["game_id", "date"]]
    games["date"] = pd.to_datetime(games["date"])
    per_game = per_game.merge(games, on="game_id", how="inner")
    return _asof_weighted_mean(per_game, "v", "w")


def run_dreb_challenger(season: str) -> GateResult:
    """One season's gate rung: elo_base vs +dreb_continuity."""
    stints_path, pbp_dir = SEASONS[season]
    feat = _asof_dreb_feature(stints_path, pbp_dir)

    games_all, base_logit_all = _base_logit_nba()
    idx = games_all.reset_index().set_index("game_id")["index"]
    ev = games_all[games_all["season"].astype(str) == season].sort_values(
        ["date", "game_id"]).reset_index(drop=True)
    order = [int(idx[g]) for g in ev["game_id"]]
    base_logit = base_logit_all[order]
    y = ev["home_win"].to_numpy(dtype=float)
    gid = ev["game_id"].astype(str).to_numpy()

    def look(g: str, t: str) -> float:
        return float(feat.get((g, t), np.nan))

    diff = pd.DataFrame({"dreb_cont": [
        look(g, h) - look(g, a)
        for g, h, a in zip(ev["game_id"], ev["home_team"], ev["away_team"])
    ]})

    n = len(ev)
    n_tr = int(n * _TRAIN_FRAC)
    n_te = n - n_tr
    metric = f"dreb_continuity_{season}"  # season-tagged: 3 seasons must not collide in the ledger key
    if n_te < _MIN_TEST:
        return GateResult("composed", "nba", metric, "team_asof", n,
                          0.0, 0.0, 0.0, 0.0, 1.0, "UNTESTABLE", [f"only {n_te} OOS games"])

    tr, te = slice(0, n_tr), slice(n_tr, n)
    z = _standardize(diff, tr)
    ones_tr, ones_te = np.ones((n_tr, 1)), np.ones((n_te, 1))
    yb = y[te]

    a_base = _fit(base_logit[tr], ones_tr, y[tr])
    p_base = _sigmoid(base_logit[te] + a_base[0])
    brier_base = _brier(p_base, yb)

    Xtr = np.column_stack([ones_tr, z["dreb_cont"].to_numpy()[tr]])
    Xte = np.column_stack([ones_te, z["dreb_cont"].to_numpy()[te]])
    theta = _fit(base_logit[tr], Xtr, y[tr])   # same optimizer as base
    p_cond = _sigmoid(base_logit[te] + Xte @ theta)
    brier_cond = _brier(p_cond, yb)

    delta = brier_base - brier_cond
    d = (p_base - yb) ** 2 - (p_cond - yb) ** 2
    dm_p = diebold_mariano(d, gid[te]).p_value
    cut = int(n_te * 0.8)
    delta_t80 = _brier(p_base[:cut], yb[:cut]) - _brier(p_cond[:cut], yb[:cut])

    verdict, caveats = _verdict(delta, dm_p, delta_t80)
    return GateResult("composed", "nba", metric, "team_asof", n,
                      round(brier_base, 6), round(brier_cond, 6), round(delta, 6),
                      round(delta_t80, 6), round(dm_p, 4), verdict, caveats)


def _verdict(delta: float, dm_p: float, delta_t80: float) -> Tuple[str, List[str]]:
    """PREREG BAR: MATTERS_PROVISIONAL iff delta>0 AND dm_p<0.05 AND delta_t80>0."""
    if delta > 0 and dm_p < _DM_ALPHA and delta_t80 > 0:
        return "MATTERS_PROVISIONAL", [
            "single-fold within one season; PROVISIONAL until cross-season replication"]
    return "NULL", []


def _append_ledger(results: List[GateResult], ledger: Path = LEDGER) -> Path:
    """Same upsert-by-(family, metric, method) discipline as compose/cli.py's
    _append_ledger, stamping THIS method (that one hardcodes challenger.METHOD,
    so it cannot be reused verbatim without clobbering the wrong key)."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if ledger.exists():
        for line in ledger.read_text(encoding="ascii", errors="replace").splitlines():
            line = line.strip()
            if line:
                try:
                    r = json.loads(line)
                    existing[_key(r)] = r
                except json.JSONDecodeError:
                    continue
    for g in results:
        r = {
            "family": g.family, "metric": g.metric, "sport": g.sport,
            "entity_mapping": g.entity_mapping, "n_games": g.n_games,
            "brier_base": g.brier_base, "brier_cond": g.brier_cond,
            "delta": g.delta, "delta_trunc80": g.delta_trunc80, "dm_p": g.dm_p,
            "verdict": g.verdict,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "method": METHOD, "edge_claimed": False, "caveats": g.caveats,
        }
        existing[_key(r)] = r
    tmp = ledger.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="ascii", errors="strict") as f:
        for r in existing.values():
            f.write(json.dumps(r) + "\n")
    tmp.replace(ledger)
    return ledger


def run_all() -> Dict[str, GateResult]:
    return {season: run_dreb_challenger(season) for season in SEASONS}


def main() -> int:
    by_season = run_all()
    print("COMPOSED dreb_continuity vs Elo -- walk-forward per season "
          f"(method={METHOD})\ncalibration only; NO edge/$ -- an honest NULL is a success\n")
    hdr = f"{'season':<10}{'n':>6}{'brier':>10}{'delta':>12}{'delta_t80':>12}{'dm_p':>8}  verdict"
    print(hdr)
    print("-" * len(hdr))
    matters = []
    for season, r in by_season.items():
        print(f"{season:<10}{r.n_games:>6}{r.brier_cond:>10.5f}{r.delta:>+12.5f}"
              f"{r.delta_trunc80:>+12.5f}{r.dm_p:>8.4f}  {r.verdict}")
        if r.verdict == "MATTERS_PROVISIONAL":
            matters.append((season, np.sign(r.delta)))
    signs = {s for _, s in matters}
    replicated = len(matters) >= 2 and len(signs) == 1
    print(f"\ncross-season: {len(matters)}/3 seasons MATTERS_PROVISIONAL -> "
          f"{'REPLICATED' if replicated else 'NOT REPLICATED (at game level)'}")
    path = _append_ledger(list(by_season.values()))
    print(f"appended {len(by_season)} rows -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
