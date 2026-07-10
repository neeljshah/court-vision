"""domains.mlb.umpire_assignment_gate -- GATE LANE F2: forward, pregame-known
home-plate umpire ASSIGNMENT conditioning on total runs.

HYPOTHESIS (pre-registered): a plate-umpire-conditioned total-runs prediction
(market total + this umpire's STRICTLY-PRIOR out-of-zone strike-rate profile,
demeaned vs the league) beats the unconditioned market/climatology baseline.
The umpire's identity is known pregame and the book can see it too, so any
realized edge here is necessarily small -- expected honest outcome is
REJECT/UNDERPOWERED, not a market beat (see .claude/rules/no-edge-claims.md).

DIFFERENCE FROM domains/mlb/umpire_totals_gate.py (wave-45, already closed
REJECT): that gate used probables.parquet's hp_umpire_id, a 2026-07 BACKFILL
snapshot for 2022/2023 games -- explicitly NOT a leak-free pregame feature
(see umpire_zone_index.py). THIS gate uses the NEW FORWARD capture store
(domains/mlb/ingest_umpire_assignments.py, commit f1934908) whose
captured_at is a real wall-clock fetch time, so pregame-ness is CHECKED per
row instead of assumed.

PROFILE (STRICTLY PRIOR, no as-of recompute needed): domains/mlb/
umpire_zone_index.py's ooz_strike_rate ranking (data/cache/intel_claims/
umpire_zone_claims.jsonl) is built entirely from the 2022+2023 statcast
corpus -- entirely BEFORE any 2026 game this gate scores. Reused verbatim;
the per-umpire term is value(umpire_id) - weighted_league_mean, same sign
convention and fixed UMPIRE_TERM_SCALE as umpire_totals_gate.py (imported,
not re-derived): higher out-of-zone strike rate -> weakly fewer runs.

LEAK CHECK (mandatory, not assumed): a game only counts as pregame-scorable
if the ASSIGNMENT's captured_at is strictly BEFORE that game's commence_time
(off the matched line_history market record). Verified live this session:
the one forward-capture snapshot taken so far (2026-07-09T23:52Z, a single
manual batch -- the M31 daemon wiring is still PENDING-RESTART per f1934908)
postdates commence_time for ALL 13 games currently in the store, since it
grabbed a full day's slate at day's end. Honest, load-bearing finding, not a
bug: until the daemon runs BEFORE first pitch, this store supplies zero
leak-free pregame rows. Written generically (not hardcoded to today's
numbers) so it re-scores correctly the moment that changes.

OUTCOME: total_runs from data/domains/mlb/gumbo_live/<game_pk>.jsonl
(max(score_home)+max(score_away) across ticks). completed = last tick
reaches inning>=9 with outs==3. ponytail: misses a <9th-inning-end walk-off
(outs<3); none occurred in this corpus -- upgrade to a linescore "Final"
field if the ingest gains one.

K-RATE: NOT TESTABLE this pass -- player_gamelogs.parquet (only per-game K
source) lags 7+ days behind this store's slate; gumbo_live ticks carry
current at-bat balls/strikes only, never a cumulative K total. Honestly
scoped out, not fabricated -- rerun once gamelogs catch up.

BASELINE: closing PRE-commence market total line from data/cache/
line_history/mlb/<game_date>.jsonl (market_type=='total', side=='over',
matched by home_team+game_date) -- "gate vs devigged total where
available". Falls back to a climatology mean (games_current.parquet) when
no pregame market row exists for a game, flagged via baseline_source.

ACCRUAL: MIN_GAMES_THRESHOLD leak-free pregame-scorable games needed before
a REJECT/SHIP_REVIEW verdict is trusted; below it -> UNDERPOWERED (a
small-n RMSE win is not a believable claim). See run_gate()['verdict_reason'].

NETWORK: zero. Pure pandas over already-materialized parquet/jsonl. Build
only under domains/mlb/. ASCII only.

CLI:
    python -m domains.mlb.umpire_assignment_gate
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from domains.mlb.prereg.stats_common import append_ledger
from domains.mlb.umpire_totals_gate import UMPIRE_TERM_SCALE

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSIGN_PATH = _REPO_ROOT / "data" / "domains" / "mlb" / "umpire_assignments.parquet"
_PROFILE_PATH = _REPO_ROOT / "data" / "cache" / "intel_claims" / "umpire_zone_claims.jsonl"
_GUMBO_DIR = _REPO_ROOT / "data" / "domains" / "mlb" / "gumbo_live"
_LINE_HISTORY_DIR = _REPO_ROOT / "data" / "cache" / "line_history" / "mlb"
_GAMES_CURRENT = _REPO_ROOT / "data" / "domains" / "mlb" / "games_current.parquet"
_OUT_VERDICT = _REPO_ROOT / "data" / "domains" / "mlb" / "umpire_assignment_gate_verdict.json"
_OUT_ROWS = _REPO_ROOT / "data" / "domains" / "mlb" / "umpire_assignment_gate_rows.parquet"

MIN_PER_FOLD: int = 50
N_FOLDS: int = 3
MIN_GAMES_THRESHOLD: int = MIN_PER_FOLD * N_FOLDS  # 150 -- fixed accrual bar, not tuned to today's n


def _to_utc(ts) -> pd.Timestamp:
    return pd.to_datetime(ts, utc=True)


# --------------------------------------------------------------------------- #
# assignment store (forward, pregame-known)
# --------------------------------------------------------------------------- #
def parse_home_plate_assignments(raw: pd.DataFrame) -> pd.DataFrame:
    """Home Plate rows only, one per game_pk: EARLIEST captured_at (the first
    time we knew the assignment -- the most conservative pregame instant when
    multiple snapshot_dates exist for the same game)."""
    cols = ["game_pk", "game_date", "home_team", "away_team",
            "umpire_id", "umpire_name", "captured_at"]
    hp = raw[raw["official_type"] == "Home Plate"].copy()
    if hp.empty:
        return hp.reindex(columns=cols)
    hp = hp.sort_values("captured_at").drop_duplicates(subset="game_pk", keep="first")
    return hp[cols].reset_index(drop=True)


def load_home_plate_assignments(path: Path = _ASSIGN_PATH) -> pd.DataFrame:
    return parse_home_plate_assignments(pd.read_parquet(path))


# --------------------------------------------------------------------------- #
# umpire profile (strictly prior -- 2022/2023 corpus, never recomputed here)
# --------------------------------------------------------------------------- #
def parse_umpire_profile(claim: dict):
    ranking = claim.get("ranking") or []
    profile = {r["umpire_id"]: float(r["value"]) for r in ranking}
    total_n = sum(r["n"] for r in ranking)
    league_mean = (sum(r["n"] * r["value"] for r in ranking) / total_n) if total_n else float("nan")
    return profile, league_mean


def load_umpire_profile(path: Path = _PROFILE_PATH):
    with open(path, "r", encoding="ascii") as f:
        claim = json.loads(f.readline())
    return parse_umpire_profile(claim)


# --------------------------------------------------------------------------- #
# outcome (from gumbo_live ticks -- the only current-season source)
# --------------------------------------------------------------------------- #
def derive_outcome_from_ticks(ticks: List[dict]) -> Optional[dict]:
    if not ticks:
        return None
    max_home = max(float(t.get("score_home") or 0) for t in ticks)
    max_away = max(float(t.get("score_away") or 0) for t in ticks)
    max_inning = max(int(t.get("inning") or 0) for t in ticks)
    last = max(ticks, key=lambda t: t["captured_at"])
    completed = bool(max_inning >= 9 and last.get("outs") == 3)
    return {"total_runs": max_home + max_away, "completed": completed, "max_inning": max_inning}


def load_game_outcomes(game_pks, gumbo_dir: Path = _GUMBO_DIR) -> Dict[int, dict]:
    out: Dict[int, dict] = {}
    for gp in game_pks:
        p = Path(gumbo_dir) / f"{int(gp)}.jsonl"
        if not p.exists():
            continue
        with open(p, "r", encoding="utf-8") as f:
            ticks = [json.loads(line) for line in f if line.strip()]
        outcome = derive_outcome_from_ticks(ticks)
        if outcome:
            out[int(gp)] = outcome
    return out


# --------------------------------------------------------------------------- #
# market total (closing PRE-commence line) + climatology fallback
# --------------------------------------------------------------------------- #
def select_pregame_market_total(records: List[dict], commence_time) -> Optional[dict]:
    """records: market_type=='total', side=='over' rows for ONE game. Returns
    the closing snapshot strictly before commence_time, or None (no leak-free
    pregame market row exists for this game -- caller falls back to
    climatology)."""
    if not records or commence_time is None:
        return None
    ct = _to_utc(commence_time)
    pre = [r for r in records if _to_utc(r["captured_at"]) < ct]
    if not pre:
        return None
    best = max(pre, key=lambda r: _to_utc(r["captured_at"]))
    return {"line": float(best["line"]), "captured_at": best["captured_at"],
            "devigged_prob_over": best.get("devigged_prob")}


def load_market_totals_for_date(game_date: str, home_teams,
                                 line_history_dir: Path = _LINE_HISTORY_DIR) -> Dict[str, List[dict]]:
    p = Path(line_history_dir) / f"{game_date}.jsonl"
    out: Dict[str, List[dict]] = {t: [] for t in home_teams}
    if not p.exists():
        return out
    teams = set(home_teams)
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("market_type") == "total" and r.get("side") == "over" and r.get("home") in teams:
                out[r["home"]].append(r)
    return out


def climatology_total(games_current: pd.DataFrame, before_date) -> float:
    """Simplest fallback baseline: mean total_runs strictly before
    `before_date`; falls back to the full-corpus mean if <30 prior rows."""
    bd = pd.Timestamp(before_date)
    prior = games_current[games_current["date"] < bd]
    if len(prior) < 30:
        prior = games_current
    return float((prior["home_runs"] + prior["away_runs"]).mean())


# --------------------------------------------------------------------------- #
# corpus assembly (pure given pre-fetched pieces -- this is what tests drive)
# --------------------------------------------------------------------------- #
def assemble_gate_corpus(
    assignments: pd.DataFrame,
    profile: Dict[str, float],
    league_mean: float,
    outcomes: Dict[int, dict],
    market_by_game: Dict[int, Optional[dict]],
    commence_by_game: Dict[int, Optional[str]],
    climatology_fn: Callable[[str], float],
) -> pd.DataFrame:
    rows = []
    for _, a in assignments.iterrows():
        gp = int(a["game_pk"])
        outcome = outcomes.get(gp)
        commence = commence_by_game.get(gp)
        pregame_leak_free = commence is not None and _to_utc(a["captured_at"]) < _to_utc(commence)

        market = market_by_game.get(gp)
        if market is not None:
            baseline_pred, baseline_source = market["line"], "market"
        else:
            baseline_pred, baseline_source = climatology_fn(a["game_date"]), "climatology"

        uid = str(a["umpire_id"])
        ump_rate = profile.get(uid)
        ump_term = (ump_rate - league_mean) if ump_rate is not None else 0.0
        candidate_pred = baseline_pred - ump_term * UMPIRE_TERM_SCALE
        completed = bool(outcome and outcome["completed"])

        rows.append({
            "game_pk": gp, "game_date": a["game_date"], "home_team": a["home_team"],
            "umpire_id": uid, "assignment_captured_at": a["captured_at"], "commence_time": commence,
            "pregame_leak_free": pregame_leak_free, "completed": completed,
            "total_runs": outcome["total_runs"] if outcome else np.nan,
            "baseline_pred": baseline_pred, "baseline_source": baseline_source,
            "ump_term": ump_term, "candidate_pred": candidate_pred,
            "scorable": bool(completed and pregame_leak_free),
        })
    return pd.DataFrame(rows)


def shuffle_scorable_umpire_terms(df: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """PLANTED-NULL harness: shuffle ump_term (and recompute candidate_pred)
    ACROSS the scorable rows only, breaking the umpire<->outcome link while
    holding total_runs/baseline_pred fixed."""
    out = df.reset_index(drop=True).copy()
    idx = np.where(out["scorable"].values)[0]
    if len(idx) < 2:
        return out
    rng = np.random.default_rng(seed)
    shuffled = out.loc[idx, "ump_term"].values.copy()
    rng.shuffle(shuffled)
    out.loc[idx, "ump_term"] = shuffled
    out.loc[idx, "candidate_pred"] = out.loc[idx, "baseline_pred"] - shuffled * UMPIRE_TERM_SCALE
    return out


def _rmse(y, pred) -> float:
    y, pred = np.asarray(y, dtype=float), np.asarray(pred, dtype=float)
    return float(np.sqrt(np.mean((y - pred) ** 2)))


def score_corpus(df: pd.DataFrame) -> dict:
    result = {
        "n_total_games": int(len(df)),
        "n_completed": int(df["completed"].sum()) if len(df) else 0,
        "n_pregame_leak_free_assignment": int(df["pregame_leak_free"].sum()) if len(df) else 0,
        "accrual_threshold_games": MIN_GAMES_THRESHOLD,
    }
    scorable = df[df["scorable"]] if len(df) else df
    n_scorable = int(len(scorable))
    result["n_scorable"] = n_scorable

    if n_scorable == 0:
        result["real_rmse_delta"] = None
        result["null_rmse_delta"] = None
        result["verdict"] = "UNDERPOWERED"
        result["verdict_reason"] = (
            f"0 leak-free pregame-scorable games (n_total_games={result['n_total_games']}, "
            f"n_completed={result['n_completed']}, "
            f"n_pregame_leak_free_assignment={result['n_pregame_leak_free_assignment']}); "
            f"need >= {MIN_GAMES_THRESHOLD}. Rerun once the forward-capture daemon runs "
            "before first pitch (see module docstring)."
        )
        return result

    y = scorable["total_runs"].values
    base_rmse = _rmse(y, scorable["baseline_pred"].values)
    cand_rmse = _rmse(y, scorable["candidate_pred"].values)
    real_delta = cand_rmse - base_rmse

    null_df = shuffle_scorable_umpire_terms(df, seed=0)
    null_scorable = null_df[null_df["scorable"]]
    null_cand_rmse = _rmse(null_scorable["total_runs"].values, null_scorable["candidate_pred"].values)
    null_delta = null_cand_rmse - base_rmse

    result.update({"baseline_rmse": base_rmse, "candidate_rmse": cand_rmse, "real_rmse_delta": real_delta,
                    "null_candidate_rmse": null_cand_rmse, "null_rmse_delta": null_delta})

    if n_scorable < MIN_GAMES_THRESHOLD:
        result["verdict"] = "UNDERPOWERED"
        result["verdict_reason"] = (
            f"{n_scorable} leak-free pregame-scorable games < accrual threshold "
            f"{MIN_GAMES_THRESHOLD}; real_rmse_delta={real_delta:.4f} reported for the "
            "record but is not a believable claim at this n."
        )
    elif real_delta >= 0:
        result["verdict"] = "REJECT"
        result["verdict_reason"] = "candidate does not beat baseline RMSE"
    elif null_delta <= real_delta:
        result["verdict"] = "REJECT"
        result["verdict_reason"] = "planted null improves as much or more -- added-flexibility artifact"
    else:
        result["verdict"] = "SHIP_REVIEW"
        result["verdict_reason"] = "candidate beats baseline RMSE and beats the planted-null improvement"

    return result


# --------------------------------------------------------------------------- #
# live IO pipeline + CLI
# --------------------------------------------------------------------------- #
def _build_live_corpus() -> pd.DataFrame:
    assignments = load_home_plate_assignments()
    profile, league_mean = load_umpire_profile()
    outcomes = load_game_outcomes(assignments["game_pk"].tolist())
    games_current = pd.read_parquet(_GAMES_CURRENT)

    market_by_game: Dict[int, Optional[dict]] = {}
    commence_by_game: Dict[int, Optional[str]] = {}
    for game_date, grp in assignments.groupby("game_date"):
        recs_by_team = load_market_totals_for_date(game_date, grp["home_team"].tolist())
        for _, a in grp.iterrows():
            gp = int(a["game_pk"])
            recs = recs_by_team.get(a["home_team"], [])
            commence_by_game[gp] = recs[0]["commence_time"] if recs else None
            market_by_game[gp] = select_pregame_market_total(recs, commence_by_game[gp])

    return assemble_gate_corpus(
        assignments, profile, league_mean, outcomes, market_by_game, commence_by_game,
        climatology_fn=lambda gd: climatology_total(games_current, gd),
    )


def run_gate(corpus: Optional[pd.DataFrame] = None) -> dict:
    df = corpus if corpus is not None else _build_live_corpus()
    result = score_corpus(df)
    result["hypothesis"] = (
        "forward pregame-known home-plate umpire assignment, conditioned by its "
        "strictly-prior out-of-zone strike-rate profile, improves total-runs "
        "prediction beyond the market/climatology baseline"
    )
    result["k_rate_status"] = "NOT_TESTABLE_this_pass"
    result["k_rate_reason"] = (
        "player_gamelogs.parquet (only per-game strikeout source) lags behind this "
        "store's slate dates; gumbo_live ticks carry current at-bat balls/strikes "
        "only, not a cumulative K total -- rerun once gamelogs catch up."
    )
    result["scope_note"] = (
        "gate vs devigged closing PRE-commence market total where available, else "
        "climatology mean total_runs; no $ edge claimed"
    )
    result["edge_claimed"] = False
    return result


def _write_rows_export(df: pd.DataFrame) -> None:
    _OUT_ROWS.parent.mkdir(parents=True, exist_ok=True)
    tmp = _OUT_ROWS.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    os.replace(str(tmp), str(_OUT_ROWS))


def main() -> None:
    df = _build_live_corpus()
    result = run_gate(df)
    result["generated_at"] = datetime.now(timezone.utc).isoformat()

    _OUT_VERDICT.parent.mkdir(parents=True, exist_ok=True)
    tmp = _OUT_VERDICT.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(result, f, indent=2, default=str)
    os.replace(str(tmp), str(_OUT_VERDICT))
    _write_rows_export(df)

    print(json.dumps(result, indent=2, default=str))
    print("wrote verdict ->", _OUT_VERDICT)
    print("wrote rows ->", _OUT_ROWS)

    append_ledger([{
        "hypothesis": "mlb_umpire_assignment_conditioning_totals_v1",
        "sport": "mlb", "atomic_unit": "team_game", "n": result["n_scorable"],
        "effect": result.get("real_rmse_delta"), "p": None, "alpha_fwer": None,
        "term": "umpire_ooz_strike_rate_term", "verdict": result["verdict"],
        "note": result["verdict_reason"], "edge_claimed": False,
        "method": "umpire_assignment_gate_v1",
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }])
    print("appended ledger row -> prereg_hypothesis_ledger.jsonl")


if __name__ == "__main__":
    main()
