"""scripts.platformkit.ingame.nba_mechanism_ladder -- NBA in-game MECHANISM
LADDER vs the live market (nba_checkpoints_full.parquet, READ-ONLY, 1,593
games, two seasons, Polymarket in-play). ONE question: score+time is saturated
(GRU NULL; the margin/sqrt(time) logistic captures it, market still leads) --
do IDENTITY / FRESHNESS mechanisms close any of the model-market gap?

PREREGISTRATION (K=4 DECLARED BEFORE ANY FIT; Bonferroni alpha=0.05/4=0.0125).
BASE (identical across rungs; each candidate differs by ONLY its rung feature):
logistic on standardized [logit(p0_first_traded), signed margin, margin/
sqrt(rem_frac)] -- "margin+time logistic + first-traded prior". Each rung ADDS
ONE feature family:
  R1 pregame Elo diff, AS-OF game date (elo_state_asof, strictly-prior). Per-
     game scalar, all ticks eligible.
  R2 endQ1 x star_minutes_load (2/3-replicated live-state): top-3 minutes-load
     diff AT endQ1 (t=720s), net48-weighted, strictly-prior net48/top3
     (conditional_gate_v2._load_v2_states, reused wholesale). Per-game scalar;
     eligible ticks POST-endQ1 only (period>=2) since the value is unknown
     before endQ1; base RE-FIT on that subset so isolation holds.
  R3 stint-continuity x DREB -- NOT_TESTABLE (verdict note).
  R4 lineup spacing x transition -- NOT_TESTABLE (verdict note).

FIT/EVAL (walk-forward, leak-free): fit 2024-25 ticks, eval 2025-26 (cutoff =
NBA season_label). Standardize on TRAIN, apply to TEST. Per rung on TEST:
pooled + per-phase Brier(base) vs Brier(cand); GAME-CLUSTERED Diebold-Mariano p
on the per-game paired loss diff; gap-to-market change. A rung beating base but
trailing market is still MATTERS (both columns recorded). Verdict: MATTERS if
pooled delta>0 AND mean per-game delta>0 AND dm_p<0.0125; else NULL. Corpus is
ESPN-id keyed, Elo/stints NBA-stats-id keyed -- bridged offline via
games.parquet (see build_crosswalk).

HONESTY (binding): calibration measurement only; edge_claimed always False; no
$/ROI field. INVARIANTS: platformkit-only; ASCII; CPU threads<=4; local commits
only; never data/registry/; never flips a flag; corpora READ-ONLY; reuses
existing Elo/mechanism builders, never reimplements.

  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_nba_mechanism_ladder.py -q
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")

import numpy as np
import pandas as pd
from scipy.stats import t as _tdist

from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.ingame.nba_checkpoint_benchmark import _elapsed_minutes, phase_bucket

_REPO = Path(__file__).resolve().parents[3]
CORPUS = _REPO / "data" / "cache" / "inplay_odds" / "nba_checkpoints_full.parquet"
GAMES = _REPO / "data" / "domains" / "basketball_nba" / "games.parquet"
OUT_PATH = _REPO / "data" / "frontend" / "ops" / "nba_mechanism_ladder_v1.json"
LEDGER = _REPO / "data" / "cache" / "intel_claims" / "prereg_hypothesis_ledger.jsonl"
K_DECLARED = 4
ALPHA_FWER = 0.05 / K_DECLARED
TRAIN_SEASON, TEST_SEASON = "2024-25", "2025-26"
_EPS = 1e-6
_BASE_COLS = ["logit_p0", "margin_s", "z"]


def _season_label(date_str: str) -> str:
    y, m = int(str(date_str)[:4]), int(str(date_str)[5:7])
    start = y if m >= 8 else y - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _logit(p: float) -> float:
    p = min(max(float(p), _EPS), 1.0 - _EPS)
    return float(np.log(p / (1.0 - p)))


def load_corpus(path: Path = CORPUS) -> pd.DataFrame:
    """Traded ticks with base features (logit_p0, signed margin, z=margin/
    sqrt(rem_frac)), phase, and season_label. Pure per-tick transform -- never
    reads outcome for a feature."""
    raw = pd.read_parquet(path)
    df = raw[raw["traded"] == True].copy()  # noqa: E712
    first_p0 = df.sort_values("ts").groupby("game_id")["market_prob"].first()
    df["p0"] = df["game_id"].map(first_p0)
    elapsed = np.array([_elapsed_minutes(int(p), c) for p, c in
                        zip(df["period"], df["game_clock_s"])])
    rem = np.clip(1.0 - elapsed / 48.0, 1.0 / 96.0, 1.0)
    df["logit_p0"] = df["p0"].apply(_logit)
    df["margin_s"] = df["margin"].astype(float)
    df["z"] = df["margin"].astype(float) / np.sqrt(rem)
    df["phase"] = df["period"].apply(phase_bucket)
    df["season"] = df["game_date"].apply(_season_label)
    return df


def _team_pair(ticker: str) -> Optional[frozenset]:
    m = re.match(r"nba-([a-z]{2,3})-([a-z]{2,3})-", str(ticker))
    return frozenset([m.group(1).upper(), m.group(2).upper()]) if m else None


def build_crosswalk(df: pd.DataFrame) -> pd.DataFrame:
    """corpus game_id -> (nba_game_id, home, away) via games.parquet:
    frozenset(market_ticker tricodes) + date within +/-1 day, kept only when
    orientation-confirmed (corpus outcome_home_win == games.home_win). Leak-free
    identity join (both final outcomes; agreement confirms the match)."""
    g = pd.read_parquet(GAMES)
    g["date"] = pd.to_datetime(g["date"])
    idx: Dict[frozenset, list] = {}
    for r in g.itertuples(index=False):
        idx.setdefault(frozenset([r.home_team, r.away_team]), []).append(
            (r.date, str(r.game_id), r.home_team, r.away_team, int(r.home_win)))
    meta = df.groupby("game_id").agg(
        game_date=("game_date", "first"), ticker=("market_ticker", "first"),
        outcome=("outcome_home_win", "first")).reset_index()
    meta["game_date"] = pd.to_datetime(meta["game_date"])
    rows = []
    for r in meta.itertuples(index=False):
        pair = _team_pair(r.ticker)
        best = None
        for (d, gid, h, a, hw) in idx.get(pair, []) if pair else []:
            if abs((d - r.game_date).days) <= 1:
                best = (gid, h, a, hw)
                break
        if best is None or int(best[3]) != int(r.outcome):
            continue
        rows.append({"game_id": r.game_id, "nba_game_id": best[0],
                     "home": best[1], "away": best[2]})
    return pd.DataFrame(rows)


def attach_elo(cw: pd.DataFrame, df: pd.DataFrame) -> Dict[int, float]:
    """R1 feature: elo_home - elo_away AS-OF each game's date (strictly-prior,
    walk-forward). Reuses ratings.elo_state_asof -- no reimplementation."""
    import datetime as dt
    from domains.basketball_nba.ratings import elo_state_asof
    from domains.basketball_nba.elo_config import ELO_MEAN
    games = pd.read_parquet(GAMES)
    # replay() needs int season codes; games.season is already "YYYY-YY".
    # Rank sorted unique -> 0,1,2,3 (monotonic, +1 per boundary so between-
    # season regression fires exactly once per new season).
    smap = {s: i for i, s in enumerate(sorted(games["season"].astype(str).unique()))}
    games["season"] = games["season"].astype(str).map(smap)
    date_by_gid = df.groupby("game_id")["game_date"].first()
    out: Dict[int, float] = {}
    cache: Dict[Any, Any] = {}
    for r in cw.itertuples(index=False):
        d = pd.to_datetime(date_by_gid[r.game_id]).date()
        st = cache.get(d)
        if st is None:
            st = elo_state_asof(games, d)
            cache[d] = st
        out[r.game_id] = (st.elo.get(r.home, ELO_MEAN) - st.elo.get(r.away, ELO_MEAN))
    return out


def attach_star_load(cw: pd.DataFrame) -> Dict[int, float]:
    """R2 feature: endQ1 star_minutes_load per game, from _load_v2_states
    (reused wholesale). states[nba_gid]['endQ1'] = (score_diff, floor_q,
    star_minutes, luck, bench) -> index 2. Keyed back to corpus game_id."""
    from scripts.platformkit.ingame_compose.conditional_gate_v2 import _load_v2_states
    nba_star: Dict[str, float] = {}
    for season in (TRAIN_SEASON, TEST_SEASON):
        _ev, states, _elo, _sk = _load_v2_states(season)
        for gid, row in states.items():
            st = row.get("endQ1")
            if st is not None:
                nba_star[str(gid)] = float(st[2])
    out: Dict[int, float] = {}
    for r in cw.itertuples(index=False):
        v = nba_star.get(str(r.nba_game_id))
        if v is not None:
            out[r.game_id] = v
    return out


def _fit_predict(train: pd.DataFrame, test: pd.DataFrame, cols: List[str]) -> np.ndarray:
    """Standardize on TRAIN, fit logistic, predict on TEST (train/inference
    parity). Returns P(home win) for each test tick."""
    from sklearn.linear_model import LogisticRegression
    mu = train[cols].mean()
    sd = train[cols].std(ddof=0).replace(0.0, 1.0)
    Xtr = ((train[cols] - mu) / sd).to_numpy()
    Xte = ((test[cols] - mu) / sd).to_numpy()
    ytr = train["outcome_home_win"].astype(int).to_numpy()
    clf = LogisticRegression(C=1e6, max_iter=2000)
    clf.fit(Xtr, ytr)
    return clf.predict_proba(Xte)[:, 1]


def _dm_gameclustered(test: pd.DataFrame, lb: np.ndarray, lc: np.ndarray) -> Tuple[float, float, int]:
    """Game-clustered Diebold-Mariano on the per-game mean loss differential
    d_g = mean(loss_base - loss_cand). Returns (mean_d, two-sided p, n_games).
    Positive mean_d => candidate better. t-distribution (g-1 df) not normal --
    strictly more conservative on thin post-endQ1 phase subsets."""
    diff = lb - lc
    per_game = pd.Series(diff).groupby(test["game_id"].to_numpy()).mean().to_numpy()
    g = len(per_game)
    md = float(per_game.mean())
    sd = float(per_game.std(ddof=1)) if g > 1 else 0.0
    if sd == 0.0 or g < 2:
        return md, 1.0, g
    tstat = md * np.sqrt(g) / sd
    return md, float(2.0 * _tdist.sf(abs(tstat), g - 1)), g


def _phase_deltas(test: pd.DataFrame, pb: np.ndarray, pc: np.ndarray) -> Dict[str, Any]:
    y = test["outcome_home_win"].astype(float).to_numpy()
    out = {}
    for ph in ["P1-2", "P3", "P4+OT"]:
        m = (test["phase"] == ph).to_numpy()
        if m.sum() == 0:
            continue
        bb, bc = brier(pb[m].tolist(), y[m].tolist()), brier(pc[m].tolist(), y[m].tolist())
        out[ph] = {"n": int(m.sum()), "brier_base": round(bb, 6),
                   "brier_cand": round(bc, 6), "delta": round(bb - bc, 6)}
    return out


def eval_rung(df: pd.DataFrame, feat: Dict[int, float], col: str,
              post_endq1: bool) -> Dict[str, Any]:
    """Fit base and base+col walk-forward; return the full metric row for one
    testable rung. base and candidate use the SAME eligible ticks, differ only
    by *col*."""
    d = df[df["game_id"].isin(feat.keys())].copy()
    d[col] = d["game_id"].map(feat)
    if post_endq1:
        d = d[d["period"] >= 2].copy()
    tr, te = d[d["season"] == TRAIN_SEASON], d[d["season"] == TEST_SEASON]
    if len(tr) == 0 or len(te) == 0:
        return {"verdict": "NOT_TESTABLE", "note": "empty train or test split"}
    y = te["outcome_home_win"].astype(float).to_numpy()
    pb = _fit_predict(tr, te, _BASE_COLS)
    pc = _fit_predict(tr, te, _BASE_COLS + [col])
    mk = te["market_prob"].to_numpy()
    bb, bc, bm = (brier(pb.tolist(), y.tolist()), brier(pc.tolist(), y.tolist()),
                  brier(mk.tolist(), y.tolist()))
    lb, lc = (y - pb) ** 2, (y - pc) ** 2
    md, dm_p, g = _dm_gameclustered(te, lb, lc)
    delta = bb - bc
    verdict = "MATTERS" if (delta > 0 and md > 0 and dm_p < ALPHA_FWER) else "NULL"
    return {
        "n_train_ticks": int(len(tr)), "n_test_ticks": int(len(te)),
        "n_test_games": g, "brier_base": round(bb, 6), "brier_cand": round(bc, 6),
        "brier_market": round(bm, 6), "delta_base_minus_cand": round(delta, 6),
        "per_game_mean_delta": round(md, 8), "dm_p_gameclustered": round(dm_p, 6),
        "base_gap_to_market": round(bb - bm, 6), "cand_gap_to_market": round(bc - bm, 6),
        "gap_closed": round(delta, 6), "cand_beats_market": bool(bc < bm),
        "phase": _phase_deltas(te, pb, pc), "alpha_fwer": ALPHA_FWER,
        "replication": "single_fold_provisional", "verdict": verdict,
    }


_NT_R3 = ("stint-continuity x DREB is an EVENT-LEVEL rebound-outcome mechanism "
          "(predicts is_dreb from continuity_s at rebound events), not a per-tick "
          "win-prob feature; no leak-free projection to a win-prob conditioner at an "
          "arbitrary PM candle ts exists. NOT_TESTABLE on this corpus, not approximated.")
_NT_R4 = ("lineup spacing x transition uses spacing_mean_dist, a SEASON-AGGREGATED "
          "per-lineup average (pools all games incl. future ones) -- a season-final "
          "aggregate, a future leak as a per-game feature (forbidden); transition is "
          "per-shot only. No leak-free as-of spacing exists. NOT_TESTABLE, not approximated.")
_H1 = "pregame Elo differential (identity), as-of game date"
_H2 = "endQ1 x star_minutes_load (freshness live-state)"
_HONEST = ("Calibration measurement only vs the live Polymarket in-play price, not a "
           "devigged close. Walk-forward: fit 2024-25, eval 2025-26; each rung adds ONE "
           "feature over an identical base on the same ticks. A rung may beat base yet "
           "trail market (both recorded). Elo/star builders reused, not reimplemented; "
           "strictly-prior/as-of. No $/edge claim.")


def build_ladder() -> Dict[str, Any]:
    df = load_corpus()
    cw = build_crosswalk(df)
    rungs = {
        "R1_elo_diff_asof": {**eval_rung(df, attach_elo(cw, df), "elo_diff", False),
                             "hypothesis": _H1, "eligible_ticks": "all"},
        "R2_endQ1_x_star_minutes_load": {**eval_rung(df, attach_star_load(cw), "star_load", True),
                                         "hypothesis": _H2, "eligible_ticks": "post_endQ1 (period>=2)"},
        "R3_stint_continuity_x_dreb": {"verdict": "NOT_TESTABLE", "note": _NT_R3,
                                       "hypothesis": "stint-continuity x DREB conditioning"},
        "R4_lineup_spacing_x_transition": {"verdict": "NOT_TESTABLE", "note": _NT_R4,
                                           "hypothesis": "lineup spacing x transition"},
    }
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sport": "nba", "benchmark": "nba_mechanism_ladder_v1_checkpoints_full",
        "corpus": str(CORPUS.name), "n_games_corpus": int(df["game_id"].nunique()),
        "n_games_matched": int(len(cw)), "k_declared": K_DECLARED, "alpha_fwer": ALPHA_FWER,
        "walk_forward": {"train_season": TRAIN_SEASON, "test_season": TEST_SEASON,
                         "cutoff": "NBA season_label; no game spans both seasons"},
        "base_model": "logistic on std [logit(p0_first_traded), signed margin, margin/sqrt(rem_frac)]",
        "rungs": rungs, "units": "probability (Brier; no dollars)", "edge_claimed": False,
        "honest_note": _HONEST,
    }


def _ledger_rows(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    cp = {"R1_elo_diff_asof": "all_ticks", "R2_endQ1_x_star_minutes_load": "post_endQ1"}
    for key, r in doc["rungs"].items():
        rows.append({
            "hypothesis": r.get("hypothesis", key), "sport": "nba",
            "atomic_unit": "game_tick_asof_ingame", "method": "nba_mechanism_ladder_v1",
            "season": "walkforward_2024-25_train_2025-26_test", "checkpoint": cp.get(key, "n/a"),
            "n": r.get("n_test_ticks", 0), "effect": r.get("delta_base_minus_cand", 0.0),
            "p": r.get("dm_p_gameclustered", 1.0), "alpha_fwer": ALPHA_FWER,
            "term": "dm_gameclustered_brier_base_minus_cand", "verdict": r["verdict"],
            "note": r.get("note", "walk-forward brier vs base; gap_closed=%s cand_beats_market=%s"
                          % (r.get("gap_closed"), r.get("cand_beats_market"))),
            "edge_claimed": False, "computed_at": doc["generated_at"],
        })
    return rows


def write(out_path: Path = OUT_PATH, ledger: Path = LEDGER) -> Dict[str, Any]:
    doc = build_ladder()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(str(tmp), str(out_path))
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        for row in _ledger_rows(doc):
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")
    return doc


if __name__ == "__main__":
    d = write()
    for k, r in d["rungs"].items():
        print("%-34s %-13s delta=%s p=%s gap_closed=%s" % (
            k, r["verdict"], r.get("delta_base_minus_cand"),
            r.get("dm_p_gameclustered"), r.get("gap_closed")))


__all__ = ["CORPUS", "GAMES", "OUT_PATH", "K_DECLARED", "ALPHA_FWER", "load_corpus",
           "build_crosswalk", "attach_elo", "attach_star_load", "eval_rung",
           "build_ladder", "write"]
