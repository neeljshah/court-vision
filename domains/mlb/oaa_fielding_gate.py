"""domains.mlb.oaa_fielding_gate -- team fielding-alignment gate (Gate Lane A4).

Question: beyond contact-quality alone (estimated_woba_using_speedangle, the
batted-ball-level xwOBA statcast already computes from exit velo + launch
angle), does a team's TRAILING-season fielding quality (domains.mlb.
oaa_asof_builder, OAA + catch-probability, year == target_season - 1, leak-
free) condition whether a batted ball becomes an out? Target = out_converted:
1 for a fielded/defended out on a ball in play, 0 for a hit or fielding
error, home runs and ambiguous events (fielder's-choice-no-out, catcher's
interference) EXCLUDED (not a fieldable defensive opportunity / not a clean
binary). Fielding team on the play = home_team if inning_topbot=='Top' else
away_team (the team on defense).

GATE SHAPE mirrors domains.mlb.asof_debut_freshness_gate: single-corpus 70/30
walk-forward split (chronological, no shuffle), Platt(xwoba) BASE vs
2-feature logistic(xwoba_z, fielding_quality_z) CANDIDATE (reuses
asof_debut_freshness_gate._fit_2feature unchanged), DM clustered by game_pk,
planted-null + truncation-invariance controls. TWO independent corpora are
run (target_season=2025 trailing 2024, target_season=2026 trailing 2025 --
both fielding-leaderboard years available locally) so an affirmative does not
rest on a single fold.

THIN-DATA HONESTY: the play-level row count is large (tens of thousands per
season), but the true information cardinality of fielding_quality_z is only
~30 team-season values repeated across every play by that team -- MIN_TEAMS
below is a distinct, pre-stated power floor on top of MIN_TEST_N (raw row
count alone would overstate how powered this is).

CANDIDATE-ONLY / DEFAULT-OFF: reads parquets additively, no adapter/flag
touched. Calibration verdict only (held-out Brier); no $/edge. REJECT or
INSUFFICIENT_DATA is an honest success, not a failure.

CLI: python -m domains.mlb.oaa_fielding_gate
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from domains.mlb.asof_debut_freshness_gate import _fit_2feature
from domains.mlb.oaa_asof_builder import build_team_fielding_trailing
from domains.mlb.pregame_gate import BSS_MIN, _brier, _platt_fit, _sigmoid
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.io_atomic import append_jsonl_atomic

_REPO = Path(__file__).resolve().parents[2]
_STATCAST_DIR = _REPO / "data/cache/statcast"
LEDGER_PATH = _REPO / "domains/mlb/knowledge/validation_ledger.jsonl"

TARGET_SEASONS = (2025, 2026)   # trailing = target-1 (2024, 2025) -- both exist locally
TRAIN_FRAC = 0.70
EPS = 0.05
MIN_TEST_N = 500      # test-split play-row floor
MIN_TEAMS = 20         # test-split unique-fielding-team floor (true info cardinality)

OUT_EVENTS = frozenset({
    "field_out", "force_out", "grounded_into_double_play", "double_play",
    "fielders_choice_out", "sac_fly", "sac_bunt", "sac_fly_double_play", "triple_play",
})
NOTOUT_EVENTS = frozenset({"single", "double", "triple", "field_error"})

_SAVANT_COLS = ["game_pk", "game_date", "inning_topbot", "home_team", "away_team",
                "events", "type", "estimated_woba_using_speedangle"]


def build_play_frame(
    target_season: int,
    savant_df: Optional[pd.DataFrame] = None,
    team_feat: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """One row per fieldable batted ball in target_season: game_pk, date,
    team (fielding side), out_converted, xwoba, fielding_quality_z (trailing,
    leak-free). Rows join to team_feat by fielding team code -- rows with no
    trailing team feature (All-Star Game 'AL'/'NL' rows) are dropped."""
    df = (savant_df if savant_df is not None else
          pd.read_parquet(_STATCAST_DIR / ("savant_full__%d.parquet" % target_season),
                           columns=_SAVANT_COLS))
    x = df[df["type"] == "X"].copy()
    x["out_converted"] = np.where(x["events"].isin(OUT_EVENTS), 1.0,
                                   np.where(x["events"].isin(NOTOUT_EVENTS), 0.0, np.nan))
    x = x.dropna(subset=["out_converted", "estimated_woba_using_speedangle"])
    x["team"] = np.where(x["inning_topbot"] == "Top", x["home_team"], x["away_team"])

    tf = team_feat if team_feat is not None else build_team_fielding_trailing(target_season)
    out = x.merge(tf[["team", "fielding_quality_z"]], on="team", how="inner")
    out = out.rename(columns={"game_date": "date",
                               "estimated_woba_using_speedangle": "xwoba"})
    out = out.sort_values("date", kind="mergesort").reset_index(drop=True)
    return out[["game_pk", "date", "team", "out_converted", "xwoba", "fielding_quality_z"]]


def _gate_once(df: pd.DataFrame, train_frac: float = TRAIN_FRAC, eps: float = EPS) -> Dict[str, Any]:
    n = len(df)
    split = int(n * train_frac)
    tr, te = df.iloc[:split], df.iloc[split:]
    n_teams_te = int(te["team"].nunique())
    if len(te) < MIN_TEST_N or n_teams_te < MIN_TEAMS:
        return {"n_test": len(te), "n_teams_test": n_teams_te,
                "brier_base": None, "brier_cand": None, "brier_delta": None,
                "dm_stat": None, "dm_p": None, "feat_weight": None, "base_bss": None,
                "base_degenerate": None, "verdict": "INSUFFICIENT_DATA"}

    y_tr = tr["out_converted"].values.astype(float)
    y_te = te["out_converted"].values.astype(float)
    m, s = float(np.nanmean(tr["xwoba"].values)), max(float(np.nanstd(tr["xwoba"].values)), 1e-8)
    # NEGATED z-score: _platt_fit/_fit_2feature constrain the base-feature
    # weight >= 0.05 (positive-only, inherited from Elo-logit features that
    # are already positively oriented toward the target). Raw xwOBA is
    # NEGATIVELY correlated with out_converted (higher xwOBA = more likely a
    # hit) -- flip sign so higher xz = more out-likely, matching the bound.
    xz_tr = -(tr["xwoba"].values.astype(float) - m) / s
    xz_te = -(te["xwoba"].values.astype(float) - m) / s
    fz_tr = tr["fielding_quality_z"].values.astype(float)
    fz_te = te["fielding_quality_z"].values.astype(float)

    wb, bb_ = _platt_fit(xz_tr, y_tr)
    p_base = _sigmoid(wb * xz_te + bb_)
    p_cand, w2 = _fit_2feature(xz_tr, fz_tr, y_tr, xz_te, fz_te)

    br_base = _brier(y_te, p_base)
    br_cand = _brier(y_te, p_cand)
    d = (p_base - y_te) ** 2 - (p_cand - y_te) ** 2
    dm = diebold_mariano(d, te["game_pk"].astype(str).values)

    base_rate = float(np.mean(y_tr))
    br_const = _brier(y_te, np.full_like(y_te, base_rate))
    bss = (br_const - br_base) / br_const if br_const > 0 else 0.0
    degen = bss < BSS_MIN
    beats = bool((br_cand < br_base) and (dm.p_value < eps) and not degen)
    return {
        "n_test": len(te), "n_teams_test": n_teams_te,
        "brier_base": round(br_base, 6), "brier_cand": round(br_cand, 6),
        "brier_delta": round(br_base - br_cand, 6),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "feat_weight": round(w2, 5), "base_bss": round(bss, 5), "base_degenerate": degen,
        "verdict": "PROVISIONAL_SHIP_REVIEW" if beats else "REJECT",
    }


def _planted_null(df: pd.DataFrame, seed: int = 0) -> Dict[str, Any]:
    """Shuffle fielding_quality_z (break its team alignment) -> must collapse."""
    rng = np.random.default_rng(seed)
    nd = df.copy()
    nd["fielding_quality_z"] = rng.permutation(nd["fielding_quality_z"].values)
    return _gate_once(nd)


def _one_corpus(target_season: int, seed: int) -> Dict[str, Any]:
    df = build_play_frame(target_season)
    real = _gate_once(df)
    null = _planted_null(df, seed=seed)
    trunc = _gate_once(df, train_frac=TRAIN_FRAC * 0.90)
    return {"target_season": target_season, "trailing_year": target_season - 1,
            "n_rows": int(len(df)), "real": real, "planted_null": null, "truncation": trunc}


def run(target_seasons: Tuple[int, ...] = TARGET_SEASONS, seed: int = 0) -> Dict[str, Any]:
    """Two independent single-corpus gates (2025 & 2026 target seasons, each
    with its own trailing fielding year). Overall verdict is honest about
    partial agreement -- MIXED is a real outcome, not smoothed to a pass."""
    corpora = [_one_corpus(s, seed) for s in target_seasons]
    verdicts = [c["real"]["verdict"] for c in corpora]
    if all(v == "INSUFFICIENT_DATA" for v in verdicts):
        overall = "INSUFFICIENT_DATA"
    elif all(v == "PROVISIONAL_SHIP_REVIEW" for v in verdicts) and len(corpora) >= 2:
        overall = "PROVISIONAL_SHIP_REVIEW"  # 2/2 corpora agree -- still capped PROVISIONAL
    elif all(v in ("REJECT", "INSUFFICIENT_DATA") for v in verdicts):
        overall = "REJECT"
    else:
        overall = "MIXED"  # corpora disagree -- honest, not a passing grade
    return {"corpora": corpora, "overall_verdict": overall}


def append_ledger_row(res: Dict[str, Any], ledger_path: Path = LEDGER_PATH) -> Dict[str, Any]:
    parts = []
    for c in res["corpora"]:
        r = c["real"]
        parts.append(
            "season=%d(trail=%d) n_test=%s teams=%s brier_delta=%s dm_p=%s degen=%s verdict=%s "
            "null=%s trunc=%s" % (
                c["target_season"], c["trailing_year"], r["n_test"], r["n_teams_test"],
                r["brier_delta"], r["dm_p"], r["base_degenerate"], r["verdict"],
                c["planted_null"]["verdict"], c["truncation"]["verdict"]))
    row = {
        "sport": "mlb", "hypothesis": "oaa_trailing_fielding_quality_babip_conversion",
        "corpus": "savant_playlevel__%s" % "_".join(str(c["target_season"]) for c in res["corpora"]),
        "n": sum(c["real"]["n_test"] or 0 for c in res["corpora"]),
        "effect": None, "p": None, "verdict": res["overall_verdict"], "edge_claimed": False,
        "note": ("Trailing team OAA+catch-prob fielding_quality_z vs xwOBA-only baseline on "
                  "out_converted (batted-ball out conversion, HR/ambiguous excluded). "
                  "MIN_TEAMS=%d floor on top of MIN_TEST_N (true info cardinality is ~30 "
                  "team-seasons, not raw play count). Per-corpus: %s"
                  % (MIN_TEAMS, " || ".join(parts))),
    }
    append_jsonl_atomic(ledger_path, row)
    return row


def main() -> int:
    res = run()
    print("=" * 72)
    print("MLB oaa_trailing_fielding_quality_babip_conversion -- 2-corpus WF gate")
    print("=" * 72)
    for c in res["corpora"]:
        r = c["real"]
        print("\ntarget_season=%d (trailing=%d) rows=%d" % (c["target_season"], c["trailing_year"], c["n_rows"]))
        print("  REAL  verdict=%s n_test=%s teams=%s" % (r["verdict"], r["n_test"], r["n_teams_test"]))
        if r["brier_base"] is not None:
            print("    Brier base %.6f cand %.6f delta %+.6f  DM p=%.4f  feat_w=%+.4f  bss=%.4f degen=%s"
                  % (r["brier_base"], r["brier_cand"], r["brier_delta"], r["dm_p"],
                     r["feat_weight"], r["base_bss"], r["base_degenerate"]))
        print("  NULL  verdict=%s (must be REJECT)" % c["planted_null"]["verdict"])
        print("  TRUNC verdict=%s (should match REAL)" % c["truncation"]["verdict"])
    print("\nOVERALL verdict=%s" % res["overall_verdict"])
    print("\n(REJECT/INSUFFICIENT_DATA/MIXED = honest outcomes; calibration only; no edge claimed.)")
    row = append_ledger_row(res)
    print("\nledger row appended -> %s" % LEDGER_PATH)
    print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_play_frame", "run", "append_ledger_row", "TARGET_SEASONS",
           "MIN_TEST_N", "MIN_TEAMS", "OUT_EVENTS", "NOTOUT_EVENTS"]
