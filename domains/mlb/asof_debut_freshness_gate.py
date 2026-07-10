"""domains.mlb.asof_debut_freshness_gate -- MiLB roster-freshness / debut-watch
FIRST GATE (Gate Lane F3).

Question: on 2026-season MLB DEBUT games (a player's first local-corpus
appearance -- proxy for "first MLB appearance", caveat below), does a
CANDIDATE = base Elo + is_debut_game flag beat base Elo alone on held-out
Brier?  This is a COVERAGE-COMPLETENESS axis, not a signal hunt: a debut
game is where a naive Elo/profile layer has the LEAST information (a rookie
carries no MLB track record), so the honest frontier here is "a Brier win
at best on rare events" -- this gate measures exactly that, on a THIN,
explicitly-declared eval slice.

DEBUT DEFINITION (proxy, stated plainly): a batter/pitcher mlbam id counts
as a "2026 debut" if it appears in savant_full__2026.parquet but in NONE of
savant_full__2023/2024/2025.parquet (the full local savant window). A
player last active pre-2023 who sits out 2023-2025 and returns in 2026
would be a rare FALSE POSITIVE under this proxy -- the same honest
window-limited proxy debut_watch() already uses on the MiLB-roster side
(scripts/platformkit/data_frontier/milb_statsapi.py). is_debut_game flags a
GAME (not a team side) where >=1 debut batter/pitcher appears for either
club; home/away side-attribution is deferred (coarser, but avoids guessing
which side "owns" the debutant from pitch-level rows alone).

GAME IDENTITY: reuses domains.mlb.game_pk_bridge.build_game_pk_bridge
UNCHANGED (the proven date + unordered-team-pair dialect crosswalk) to map
savant game_pk -> games_current.event_id.

CORPUS / SPLIT: games_current.parquet season==2026 ONLY for the train/test
split. Debut games exist only in 2026 by definition; restricting the split
to season 2026 keeps the flag's TRAIN-time variance real (debuts land
Mar-Jul, not bunched at a tail) instead of an all-zero training column a
full 2022-2026 corpus would produce. Elo itself is still WARMED on the FULL
2022-2026 history via walk_forward_elo before the season filter -- no
2026-opening-day cold start.

GATE SHAPE mirrors the NBA ast_rate / MLB sp_ra_diff / WTA hold_pct asof
reclaim precedent: single-corpus 70/30 walk-forward, Platt(elo) BASE vs
2-feature logistic(elo_logit, flag) CANDIDATE, DM clustered by event_id,
planted-null + truncation-invariance controls. The one difference: Brier/DM
is scored ONLY on the debut-game rows in test (the declared EVAL SET), not
the whole test split.

SINGLE-CORPUS, PROVISIONAL (honest): local savant coverage starts at 2023,
so there is no second independent season to define "priors" for a true
cross-season replication of this specific debut proxy today. Verdict is
therefore capped at PROVISIONAL -- never a plain SHIP -- until a second
savant year (2022 or 2027) makes a second corpus buildable.

CANDIDATE-ONLY / DEFAULT-OFF: reads parquets additively, no adapter/flag
touched. NO $ / edge anywhere; verdict is CALIBRATION (held-out Brier). A
REJECT or INSUFFICIENT_DATA is an HONEST SUCCESS/closure, not a failure.

CLI: python -m domains.mlb.asof_debut_freshness_gate
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set, Tuple

import numpy as np
import pandas as pd

from domains.mlb.game_pk_bridge import build_game_pk_bridge
from domains.mlb.pregame_gate import BSS_MIN, _brier, _logit, _platt_fit, _sigmoid
from domains.mlb.ratings import walk_forward_elo
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.io_atomic import append_jsonl_atomic

_REPO = Path(__file__).resolve().parents[2]
_GAMES_CURRENT = _REPO / "data/domains/mlb/games_current.parquet"
_STATCAST_DIR = _REPO / "data/cache/statcast"
LEDGER_PATH = _REPO / "domains/mlb/knowledge/validation_ledger.jsonl"

TARGET_SEASON = 2026
PRIOR_SEASONS = (2023, 2024, 2025)
TRAIN_FRAC = 0.70      # leak-free time split, WITHIN season TARGET_SEASON only
EPS = 0.05             # DM significance threshold
MIN_TEST_N = 15        # below this the debut slice is INSUFFICIENT_DATA, not a verdict


# --------------------------------------------------------------------------- #
# Debut-id / debut-game_pk discovery (real savant reads; injectable for tests)
# --------------------------------------------------------------------------- #

def _season_batter_pitcher_ids(season: int) -> Tuple[Set[int], Set[int]]:
    """(batter ids, pitcher ids) touched anywhere in one local savant season."""
    fp = _STATCAST_DIR / ("savant_full__%d.parquet" % season)
    df = pd.read_parquet(fp, columns=["batter", "pitcher"])
    return (set(df["batter"].dropna().astype("int64")),
            set(df["pitcher"].dropna().astype("int64")))


def build_debut_game_pks(target_season: int = TARGET_SEASON,
                          prior_seasons: Iterable[int] = PRIOR_SEASONS) -> Set[int]:
    """game_pks that are a debut player's EARLIEST target_season appearance --
    NOT every later game that player also happens to appear in (a rookie who
    debuts in April and starts 50 more games through July must NOT have all
    50 flagged; only the debut game itself is the freshness event)."""
    prior_ids: Set[int] = set()
    for yr in prior_seasons:
        b, p = _season_batter_pitcher_ids(yr)
        prior_ids |= b | p
    tb, tp = _season_batter_pitcher_ids(target_season)
    debut_ids = (tb - prior_ids) | (tp - prior_ids)
    if not debut_ids:
        return set()
    fp = _STATCAST_DIR / ("savant_full__%d.parquet" % target_season)
    df = pd.read_parquet(fp, columns=["game_pk", "game_date", "batter", "pitcher"])
    out: Set[int] = set()
    for id_col in ("batter", "pitcher"):
        hit = df[df[id_col].isin(debut_ids)][[id_col, "game_pk", "game_date"]].drop_duplicates()
        first = hit.sort_values([id_col, "game_date", "game_pk"], kind="mergesort").groupby(id_col).first()
        out |= set(first["game_pk"].astype("int64"))
    return out


def build_team_game_rows(target_season: int = TARGET_SEASON) -> pd.DataFrame:
    """One row per (game_pk, team) -- the `player_gamelogs`-shape
    (game_pk, date, team) build_game_pk_bridge expects -- built from savant's
    per-pitch home_team/away_team instead of re-deriving the dialect crosswalk."""
    fp = _STATCAST_DIR / ("savant_full__%d.parquet" % target_season)
    df = pd.read_parquet(fp, columns=["game_pk", "game_date", "home_team", "away_team"])
    g = df.drop_duplicates("game_pk")[["game_pk", "game_date", "home_team", "away_team"]]
    home = g.rename(columns={"home_team": "team"})[["game_pk", "game_date", "team"]]
    away = g.rename(columns={"away_team": "team"})[["game_pk", "game_date", "team"]]
    return pd.concat([home, away], ignore_index=True).rename(columns={"game_date": "date"})


# --------------------------------------------------------------------------- #
# Build the candidate frame (synthetic-injectable for tests)
# --------------------------------------------------------------------------- #

def build_candidate_frame(
    target_season: int = TARGET_SEASON,
    games_current: Optional[pd.DataFrame] = None,
    debut_game_pks: Optional[Set[int]] = None,
    team_rows: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Elo (warmed on full games_current history) + is_debut_game flag,
    restricted to target_season rows only (the flag is only defined within
    that season -- see module docstring). Columns: event_id, date, season,
    target_home_win, p_base, is_debut_game."""
    gc = (games_current.copy() if isinstance(games_current, pd.DataFrame)
          else pd.read_parquet(_GAMES_CURRENT))
    gc = gc[gc["target_home_win"].notna()].reset_index(drop=True)
    elo = walk_forward_elo(gc)[["event_id", "p_home_elo", "date", "season"]].rename(
        columns={"p_home_elo": "p_base"})

    d_pks = debut_game_pks if debut_game_pks is not None else build_debut_game_pks(target_season)
    t_rows = team_rows if team_rows is not None else build_team_game_rows(target_season)
    bridge = build_game_pk_bridge(player_gamelogs=t_rows, games_current=gc)
    debut_event_ids = {bridge.mapping[gp] for gp in d_pks if gp in bridge.mapping}

    out = gc[["event_id", "target_home_win"]].merge(elo, on="event_id", how="left")
    out = out[out["season"] == target_season].sort_values("date").reset_index(drop=True)
    out["is_debut_game"] = out["event_id"].isin(debut_event_ids).astype(float)
    out.attrs["n_debut_game_pks"] = len(d_pks)
    out.attrs["n_debut_resolved"] = len(debut_event_ids)
    out.attrs["bridge_resolved_frac"] = bridge.resolved_frac
    return out


# --------------------------------------------------------------------------- #
# One single-corpus walk-forward DM gate, scored on the debut EVAL SET only
# --------------------------------------------------------------------------- #

def _fit_2feature(
    lz_tr: np.ndarray, fz_tr: np.ndarray, y_tr: np.ndarray,
    lz_te: np.ndarray, fz_te: np.ndarray,
) -> Tuple[np.ndarray, float]:
    """Fit p = sigmoid(w1*elo_logit + w2*feat_z + b) on train; predict on test."""
    from scipy.optimize import minimize

    def _nll(par: np.ndarray) -> float:
        w1, w2, b = par
        p = np.clip(_sigmoid(w1 * lz_tr + w2 * fz_tr + b), 1e-7, 1 - 1e-7)
        return float(-np.mean(y_tr * np.log(p) + (1 - y_tr) * np.log(1 - p)))

    res = minimize(_nll, x0=np.array([1.0, 0.1, 0.0]), method="L-BFGS-B",
                   bounds=[(0.05, 10), (-5, 5), (-3, 3)])
    w1, w2, b = res.x
    return _sigmoid(w1 * lz_te + w2 * fz_te + b), float(w2)


def _gate_once(
    df: pd.DataFrame, feat_col: str = "is_debut_game",
    train_frac: float = TRAIN_FRAC, eps: float = EPS,
) -> Dict[str, Any]:
    """Single-corpus 70/30 WF DM gate: Elo BASE vs Elo+debut-flag CAND, scored
    ONLY on rows where feat_col==1 in test (the declared debut EVAL SET)."""
    n = len(df)
    split = int(n * train_frac)
    tr, te = df.iloc[:split], df.iloc[split:]
    y_tr = tr["target_home_win"].values.astype(float)
    y_te = te["target_home_win"].values.astype(float)

    lz_tr = _logit(tr["p_base"].values.astype(float))
    lz_te = _logit(te["p_base"].values.astype(float))
    f_tr = tr[feat_col].values.astype(float)
    f_te = te[feat_col].values.astype(float)
    m, s = float(np.nanmean(f_tr)), max(float(np.nanstd(f_tr)), 1e-8)
    fz_tr = np.nan_to_num((f_tr - m) / s)
    fz_te = np.nan_to_num((f_te - m) / s)

    wb, bb_ = _platt_fit(lz_tr, y_tr)
    p_base = _sigmoid(wb * lz_te + bb_)
    p_cand, w2 = _fit_2feature(lz_tr, fz_tr, y_tr, lz_te, fz_te)

    cov = te[feat_col].values.astype(bool)  # the declared EVAL SET: debut games only
    n_cov = int(cov.sum())
    if n_cov < MIN_TEST_N:
        return {"n_cov_test": n_cov, "n_train_positive": int(tr[feat_col].sum()),
                "brier_base": None, "brier_cand": None, "brier_delta": None,
                "dm_stat": None, "dm_p": None, "dm_ci95": None,
                "feat_weight": round(w2, 5), "base_bss": None, "base_degenerate": None,
                "verdict": "INSUFFICIENT_DATA"}

    yb = y_te[cov]
    br_base = _brier(yb, p_base[cov])
    br_cand = _brier(yb, p_cand[cov])
    d = (p_base[cov] - yb) ** 2 - (p_cand[cov] - yb) ** 2
    dm = diebold_mariano(d, te["event_id"].astype(str).values[cov])

    base_rate = float(np.mean(y_tr))
    br_const = _brier(yb, np.full_like(yb, base_rate))
    bss = (br_const - br_base) / br_const if br_const > 0 else 0.0
    degen = bss < BSS_MIN
    beats = bool((br_cand < br_base) and (dm.p_value < eps) and not degen)
    return {
        "n_cov_test": n_cov, "n_train_positive": int(tr[feat_col].sum()),
        "brier_base": round(br_base, 6), "brier_cand": round(br_cand, 6),
        "brier_delta": round(br_base - br_cand, 6),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "dm_ci95": [round(dm.ci95[0], 6), round(dm.ci95[1], 6)],
        "feat_weight": round(w2, 5), "base_bss": round(bss, 5),
        "base_degenerate": degen,
        # PROVISIONAL, never a plain SHIP -- see module docstring (single-corpus).
        "verdict": "PROVISIONAL_SHIP_REVIEW" if beats else "REJECT",
    }


def _planted_null(df: pd.DataFrame, seed: int = 0, feat_col: str = "is_debut_game") -> Dict[str, Any]:
    """Shuffle the debut flag (break its game alignment) -> must collapse."""
    rng = np.random.default_rng(seed)
    nd = df.copy()
    nd[feat_col] = rng.permutation(nd[feat_col].values)
    return _gate_once(nd, feat_col=feat_col)


def run(target_season: int = TARGET_SEASON, seed: int = 0) -> Dict[str, Any]:
    """Full gate: real candidate + planted-null + truncation-invariance."""
    df = build_candidate_frame(target_season)
    real = _gate_once(df)
    null = _planted_null(df, seed=seed)
    # truncation invariance: drop the LAST 10% of TRAIN rows and re-gate; a real
    # effect should not flip verdict just because history got a bit shorter.
    trunc = _gate_once(df, train_frac=TRAIN_FRAC * 0.90)
    return {
        "target_season": target_season, "n_rows": int(len(df)),
        "n_debut_game_pks": df.attrs.get("n_debut_game_pks"),
        "n_debut_resolved": df.attrs.get("n_debut_resolved"),
        "bridge_resolved_frac": df.attrs.get("bridge_resolved_frac"),
        "real": real, "planted_null": null, "truncation": trunc,
    }


# --------------------------------------------------------------------------- #
# Ledger append (domains/mlb/knowledge/validation_ledger.jsonl row shape)
# --------------------------------------------------------------------------- #

def append_ledger_row(res: Dict[str, Any], ledger_path: Path = LEDGER_PATH) -> Dict[str, Any]:
    r = res["real"]
    row = {
        "sport": "mlb", "hypothesis": "milb_debut_freshness_flag",
        "corpus": "games_current_season_%d__savant_debut_proxy" % res["target_season"],
        "n": r["n_cov_test"], "effect": r["brier_delta"], "p": r["dm_p"],
        "verdict": r["verdict"], "edge_claimed": False,
        "note": (
            "COVERAGE-COMPLETENESS axis (not a signal hunt): base Elo vs Elo+is_debut_game, "
            "scored on the debut-game EVAL SET only (n=%s of %s resolved debut game_pks, "
            "bridge_resolved_frac=%s). brier_base=%s brier_cand=%s dm_p=%s feat_w=%s "
            "degen=%s. planted_null verdict=%s (must be REJECT). truncation verdict=%s "
            "(should match real). SINGLE-CORPUS/PROVISIONAL: local savant coverage starts "
            "2023 so no second independent season exists yet to replicate this debut proxy "
            "cross-season; frontier is 'a Brier win at best on rare events'."
            % (r["n_cov_test"], res["n_debut_resolved"], res["bridge_resolved_frac"],
               r["brier_base"], r["brier_cand"], r["dm_p"], r["feat_weight"], r["base_degenerate"],
               res["planted_null"]["verdict"], res["truncation"]["verdict"])
        ),
    }
    append_jsonl_atomic(ledger_path, row)
    return row


def main() -> int:
    res = run()
    print("=" * 72)
    print("MLB milb_debut_freshness_flag CANDIDATE -- season %d single-corpus WF gate"
          % res["target_season"])
    print("=" * 72)
    print("rows=%d  debut_game_pks=%s  resolved=%s (bridge_resolved_frac=%s)"
          % (res["n_rows"], res["n_debut_game_pks"], res["n_debut_resolved"],
             res["bridge_resolved_frac"]))
    r = res["real"]
    print("\nREAL     verdict=%s  n_cov_test=%d" % (r["verdict"], r["n_cov_test"]))
    if r["brier_base"] is not None:
        print("   Brier base %.6f  cand %.6f  delta %+.6f"
              % (r["brier_base"], r["brier_cand"], r["brier_delta"]))
        print("   DM p=%.4f  feat_w=%+.4f  base_bss=%.4f  degen=%s"
              % (r["dm_p"], r["feat_weight"], r["base_bss"], r["base_degenerate"]))
    nn = res["planted_null"]
    print("\nNULL     verdict=%s (must be REJECT)" % nn["verdict"])
    tr = res["truncation"]
    print("\nTRUNC    verdict=%s (should match REAL)" % tr["verdict"])
    print("\n(REJECT/INSUFFICIENT_DATA = honest success; calibration only; no edge claimed;")
    print(" verdict capped at PROVISIONAL -- single local corpus, see module docstring.)")
    row = append_ledger_row(res)
    print("\nledger row appended -> %s" % LEDGER_PATH)
    print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "build_debut_game_pks", "build_team_game_rows", "build_candidate_frame",
    "run", "append_ledger_row", "TARGET_SEASON", "PRIOR_SEASONS", "MIN_TEST_N",
]
