"""scripts.platformkit.benchmarks.crps_market.ingame_mlb -- IN-GAME distributional
CRPS: pitch engine's conditional total/margin ENSEMBLE (conditioned on the real
end-of-inning-N score, N in CHECKPOINTS, via game_sim.py's existing GameStart
seam) vs the in-play market's own implied distribution at that same wall-clock
moment. CHECKPOINTS scans the moat's shape across game states (early/mid/late).

EXTENDS run_mlb.py (pregame harness) -- same engine fit, same crps_ensemble/
crps_gaussian, same fit_market_gaussian guard. New glue only: (1) Kalshi ticker
-> game_pk join (reuses parse_kalshi_mlb_ticker), (2) live-state timeline
(ingame_grade_joined/mlb/*.jsonl) parsed ONLY for a wall-clock checkpoint anchor
(never the score), (3) in-play total/spread ladder (inplay_odds/mlb_price_series
.parquet) read as-of that anchor.

SUBSTRATE: Kalshi KXMLBTOTAL/KXMLBSPREAD are per-strike ladders -- each `side` is
an independent contract, `prob` its own implied probability (no vig-pairing).
KXMLBTOTAL side = total-runs threshold; KXMLBSPREAD side = "<team_abbr><margin>",
converted to the model's home_margin=(home-away) axis via the join's away/home split.

PLAUSIBILITY GUARD: fit_market_gaussian's degenerate-sigma guard is reused
UNCHANGED, but sigma_fallback = the MODEL's own conditional ensemble sigma at
that checkpoint (not pregame climatology, which is the wrong scale once 3-7
innings are already fixed and would mis-fire the guard either direction).

SHAPE CONTROL: a raw MODEL_SHARPER verdict is downgraded to UNDERPOWERED
unless a shape-matched market baseline agrees -- see shape_control.py.

LEAK AUDIT: conditioning score reads the game's own Statcast rows strictly
before the checkpoint inning (same as validate.py panel D); market points are
the last tick at-or-before the checkpoint within _ASOF_TOL (never after).

CLI: python -m scripts.platformkit.benchmarks.crps_market.ingame_mlb --max-games 200
Tests: python -m pytest tests/platformkit/test_ingame_crps_mlb.py -q
"""
from __future__ import annotations

import argparse
import glob
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine import corpus as C
from domains.mlb.pitch_engine.game_sim import GameStart, simulate_game
from domains.mlb.pitch_engine.validate import _lineups, _slot_dists
from domains.basketball_nba.sim2.simulator import crps_ensemble, crps_gaussian

from scripts.platformkit.benchmarks.crps_market.run_mlb import _fit_engine, _bootstrap_ci
from scripts.platformkit.benchmarks.crps_market.market_dist import fit_market_gaussian
from scripts.platformkit.benchmarks.crps_market.shape_control import (
    market_crps_discretized as _market_crps_discretized,
    shape_controlled_verdict as _shape_controlled_verdict,
)
from scripts.platformkit.ingame.ingame_id_resolver_mlb import parse_kalshi_mlb_ticker

_REPO = Path(__file__).resolve().parents[4]
_GAME_DIR = _REPO / "data" / "cache" / "ingame_grade_joined" / "mlb"
_INPLAY = _REPO / "data" / "cache" / "inplay_odds" / "mlb_price_series.parquet"
_STATCAST = _REPO / "data" / "cache" / "statcast"
_LEDGER = _REPO / "data" / "cache" / "intel_claims" / "ingame_distributional_crps_ledger.jsonl"
_OUT = Path(__file__).resolve().parent / "last_run_ingame_mlb.json"

CHECKPOINTS = (3, 5, 6, 7, 8)   # "end of inning N" -- moat-shape scan across game states
N_SIM = 1500
_ASOF_TOL = pd.Timedelta(minutes=10)   # max staleness for a market tick vs checkpoint
_MONTH = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6, "JUL": 7,
          "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
_STATE_RE = re.compile(r"(\w+)=(\S+)")
_SPREAD_SIDE_RE = re.compile(r"^([A-Za-z]+)(\d+(?:\.\d+)?)$")


# --- Statcast index + Kalshi ticker -> game_pk join -------------------------
def load_statcast_index(season: int) -> Tuple[Dict[Tuple, List[int]], pd.DataFrame]:
    """by_key[(date, away_abbr, home_abbr)] -> [game_pk,...]; games df keyed by
    game_pk with final scores. Statcast's own home_team/away_team codes already
    match the Kalshi ticker's abbrev dialect (AZ/ATH/SD/TB/KC/CWS/WSH, verified)
    -- no team_name_resolver canonicalization needed for this join."""
    df = pd.read_parquet(_STATCAST / ("savant_full__%d.parquet" % season),
                         columns=["game_pk", "game_date", "home_team", "away_team",
                                  "post_home_score", "post_away_score"])
    g = df.groupby("game_pk").agg(
        game_date=("game_date", "first"), home_team=("home_team", "first"),
        away_team=("away_team", "first"),
        home_score=("post_home_score", "max"), away_score=("post_away_score", "max"),
    ).reset_index()
    g["game_date"] = pd.to_datetime(g["game_date"]).dt.date
    by_key: Dict[Tuple, List[int]] = {}
    for pk, dt_, h, a in zip(g["game_pk"], g["game_date"], g["home_team"], g["away_team"]):
        by_key.setdefault((dt_, a, h), []).append(int(pk))
    return by_key, g.set_index("game_pk")


def resolve_game_pk(ticker_suffix: str, by_key: Dict[Tuple, List[int]]
                    ) -> Optional[Tuple[int, str, str]]:
    """(game_pk, away_abbr, home_abbr) for one unambiguous match, or None. Tries the
    ticker's own date, then the day before (Kalshi date can roll relative to the
    Statcast home-local game_date); never guesses on ambiguity."""
    parsed = parse_kalshi_mlb_ticker("KXMLBGAME-" + ticker_suffix)
    if parsed is None:
        return None
    mo = _MONTH.get(parsed["mon"])
    if mo is None:
        return None
    d0 = date(2000 + int(parsed["yy"]), mo, int(parsed["dd"]))
    blob = parsed["blob"]
    for cand_date in (d0, d0 - timedelta(days=1)):
        hits = [(a, h) for (dt_, a, h) in by_key if dt_ == cand_date and a + h == blob]
        if len(hits) == 1:
            away, home = hits[0]
            pks = by_key[(cand_date, away, home)]
            if len(pks) == 1:
                return pks[0], away, home
        if hits:
            break  # ambiguous split or doubleheader on the exact date -- skip, never guess
    return None


# --- live-state timeline (wall-clock anchor only, never the score) ----------
def load_state_timeline(path: Path) -> pd.DataFrame:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                kv = dict(_STATE_RE.findall(r.get("state_summary", "")))
                rows.append({"ts": r["ts"], "inning": int(kv["inning"])})
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    df = pd.DataFrame(rows, columns=["ts", "inning"])
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], utc=True, format="ISO8601")
    return df.sort_values("ts").reset_index(drop=True)


def checkpoint_ts(timeline: pd.DataFrame, end_inning: int) -> Optional[pd.Timestamp]:
    """Wall-clock ts of the first observed state past end_inning (checkpoint
    anchor for the market lookup only -- the model's conditioning score comes
    from the game's own Statcast rows, not this noisy live feed)."""
    if timeline.empty:
        return None
    hit = timeline[timeline["inning"] > end_inning]
    return None if hit.empty else hit["ts"].iloc[0]


# --- in-play market points at a checkpoint ----------------------------------
def _asof_points(df_event: pd.DataFrame, ts_cp: pd.Timestamp) -> Dict[str, float]:
    """Per `side`, the last prob at-or-before ts_cp within _ASOF_TOL (no lookahead)."""
    win = df_event[(df_event["ts"] <= ts_cp) & (df_event["ts"] >= ts_cp - _ASOF_TOL)]
    out: Dict[str, float] = {}
    for side, grp in win.groupby("side"):
        out[side] = float(grp.sort_values("ts")["prob"].iloc[-1])
    return out


def total_market_points(df_event: pd.DataFrame, ts_cp: pd.Timestamp
                        ) -> List[Tuple[float, float]]:
    return sorted((float(side), p) for side, p in _asof_points(df_event, ts_cp).items())


def margin_market_points(df_event: pd.DataFrame, ts_cp: pd.Timestamp, away_abbr: str
                         ) -> List[Tuple[float, float]]:
    """Convert "<team>N" (P(team wins by > N)) to the model's home_margin axis."""
    pts = []
    for side, p in _asof_points(df_event, ts_cp).items():
        m = _SPREAD_SIDE_RE.match(side)
        if not m:
            continue
        team, n = m.group(1), float(m.group(2))
        if team == away_abbr:
            pts.append((-n, 1.0 - p))          # P(home_margin < -n) = 1 - p
        else:
            pts.append((n, p))                  # P(home_margin > n) = p
    return sorted(pts)


def _crps_bucket(model_v: np.ndarray, mu: float, sigma: float, realized: float,
                  n_used: int, disc_seed: int) -> Dict[str, float]:
    return {"model_crps": crps_ensemble(model_v, realized),
            "market_crps": crps_gaussian(mu, sigma, realized),
            "market_crps_discretized": _market_crps_discretized(
                mu, sigma, realized, len(model_v), disc_seed),
            "n_lines_used": n_used}


def _verdict(delta: np.ndarray) -> Tuple[str, List[float]]:
    """Same rule as run_mlb.py's pregame harness: CI is always reported (even
    when n<30) so an UNDERPOWERED bucket still shows its trend direction."""
    ci = _bootstrap_ci(delta)
    if len(delta) < 30:
        return "UNDERPOWERED", ci
    if ci[0] > 0:
        return "MODEL_SHARPER", ci
    if ci[1] < 0:
        return "MARKET_SHARPER", ci
    return "UNDERPOWERED", ci


def _ledger_append(rows: List[dict]) -> None:
    _LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(_LEDGER, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=True) + "\n")


def run(max_games: int = 300, seed: int = 0) -> dict:
    by_key, gt = load_statcast_index(2026)
    sel, out, tiers, trans, _sigma_clim_pregame = _fit_engine()
    te_pa = C.build_pa_frame(C.load_pitch_frame(2026))

    inplay = pd.read_parquet(_INPLAY, columns=["event_key", "market_type", "side", "ts", "prob"])
    inplay = inplay[inplay["market_type"].isin(("total", "spread"))].copy()
    inplay["ts"] = pd.to_datetime(inplay["ts"], unit="s", utc=True)

    game_files = sorted(glob.glob(str(_GAME_DIR / "*.jsonl")))[:max_games]
    buckets: Dict[str, List[dict]] = {}
    n_join_fail = n_lineup_fail = 0

    for fp in game_files:
        suffix = Path(fp).stem.replace("KXMLBGAME-", "")
        resolved = resolve_game_pk(suffix, by_key)
        if resolved is None:
            n_join_fail += 1
            continue
        gpk, away_abbr, home_abbr = resolved
        gpa = te_pa[te_pa["game_pk"] == gpk].sort_values("at_bat_number")
        if gpa.empty:
            n_join_fail += 1
            continue
        ab, hb, hp, ap, stand, throw = _lineups(gpa)
        if hp < 0 or ap < 0 or not ab or not hb:
            n_lineup_fail += 1
            continue
        fh = int(gt.loc[gpk, "home_score"]); fa = int(gt.loc[gpk, "away_score"])
        pa_away = _slot_dists(sel, out, tiers, ab, hp, throw, stand)
        pa_home = _slot_dists(sel, out, tiers, hb, ap, throw, stand)

        timeline = load_state_timeline(Path(fp))
        tot_ev = inplay[(inplay["market_type"] == "total")
                        & (inplay["event_key"] == "KXMLBTOTAL-" + suffix)]
        spr_ev = inplay[(inplay["market_type"] == "spread")
                        & (inplay["event_key"] == "KXMLBSPREAD-" + suffix)]

        for end_inn in CHECKPOINTS:
            cp = checkpoint_ts(timeline, end_inn)
            if cp is None:
                continue
            pre = gpa[gpa["inning"] < end_inn + 1]
            if pre.empty:
                continue
            sh = int(pre["post_home_score"].iloc[-1]); sa = int(pre["post_away_score"].iloc[-1])
            h, a = simulate_game(pa_away, pa_home, trans, n=N_SIM, seed=(gpk * 10 + end_inn),
                                 start=GameStart(inning=end_inn + 1, half=0,
                                                 home_score=sh, away_score=sa))
            model_total = (h + a).astype(float); model_margin = (h - a).astype(float)

            if not tot_ev.empty:
                pts = total_market_points(tot_ev, cp)
                if pts:
                    mu, sigma, n_used = fit_market_gaussian(pts, float(np.std(model_total)))
                    key = "total_runs|end_inning_%d" % end_inn
                    buckets.setdefault(key, []).append(
                        _crps_bucket(model_total, mu, sigma, float(fh + fa), n_used,
                                     disc_seed=gpk * 10 + end_inn))

            if not spr_ev.empty:
                pts = margin_market_points(spr_ev, cp, away_abbr)
                if pts:
                    mu, sigma, n_used = fit_market_gaussian(pts, float(np.std(model_margin)))
                    key = "home_margin|end_inning_%d" % end_inn
                    buckets.setdefault(key, []).append(
                        _crps_bucket(model_margin, mu, sigma, float(fh - fa), n_used,
                                     disc_seed=gpk * 10 + end_inn + 500_000))

    checkpoints_out: Dict[str, dict] = {}
    ledger_rows: List[dict] = []
    now = pd.Timestamp.utcnow().isoformat()
    for key, rows in sorted(buckets.items()):
        market, bucket = key.split("|")
        mc = np.array([r["model_crps"] for r in rows]); kc = np.array([r["market_crps"] for r in rows])
        kcd = np.array([r["market_crps_discretized"] for r in rows])
        delta = kc - mc
        delta_disc = kcd - mc
        raw_verdict, ci = _verdict(delta)
        disc_verdict, ci_disc = _verdict(delta_disc)
        verdict, shape_note = _shape_controlled_verdict(raw_verdict, disc_verdict)
        # single capture window -- any non-null verdict is PROVISIONAL until a
        # disjoint corpus replicates it; the token itself carries the qualifier
        # (interaction_factory convention) so `verdict` alone is never durable.
        provisional = verdict != "UNDERPOWERED"
        verdict_token = verdict + "_PROVISIONAL" if provisional else verdict
        doc = {
            "n": len(rows), "model_crps_mean": round(float(mc.mean()), 4),
            "market_crps_mean": round(float(kc.mean()), 4),
            "market_crps_discretized_mean": round(float(kcd.mean()), 4),
            "paired_delta_mean": round(float(delta.mean()), 4),
            "paired_delta_discretized_mean": round(float(delta_disc.mean()), 4),
            "paired_delta_95ci": ci, "shape_control_verdict": disc_verdict,
            "verdict": verdict_token, "provisional": provisional,
            "n_multi_line": int(sum(1 for r in rows if r["n_lines_used"] >= 2)),
        }
        checkpoints_out[key] = doc
        note = ("paired CRPS delta (market_crps - model_crps); market sigma_fallback "
                "= model's own conditional ensemble sigma at this checkpoint, not "
                "pregame climatology; game-clustered (1 row/game/bucket); "
                "shape-controlled baseline = crps_ensemble on integer-rounded "
                "N(mu,sigma) market samples (guards vs a continuous-vs-integer "
                "distribution-family artifact).")
        note += ((" " + shape_note) if shape_note else "")
        note += (" PROVISIONAL -- single capture-window corpus, needs "
                  "independent-corpus replication.") if provisional else ""
        ledger_rows.append({
            "sport": "mlb", "market": market, "bucket": bucket, "edge_claimed": False,
            "template_id": "ingame_distributional_crps_mlb",
            "candidate_id": "mlb_ingame_crps::%s::%s" % (market, bucket),
            "n": doc["n"], "effect": doc["paired_delta_mean"], "p": None,
            "alpha_fwer": None, "verdict": verdict_token, "provisional": provisional,
            "computed_at": now, "note": note,
        })

    result = {
        "sport": "mlb", "edge_claimed": False,
        "n_game_files": len(game_files), "n_join_fail": n_join_fail,
        "n_lineup_fail": n_lineup_fail, "checkpoints": checkpoints_out,
        "other_sports_joinable": {
            "soccer_intl": "NOT_TESTABLE -- ingame_grade_joined state-timeline exists "
                           "but no soccer conditional-distribution engine (no game_sim "
                           "analogue) to condition on it",
            "wnba": "NOT_TESTABLE -- in-play total market exists (59 events) but no "
                    "wall-clock live-state timeline captured to anchor a checkpoint",
            "kbo": "NOT_TESTABLE -- same gap as wnba (213 total events, no state timeline)",
            "nba/tennis": "NOT_TESTABLE -- in-play total market_type does not exist",
        },
        "honest_note": ("Distributional CRPS sharpness only, never a $/ROI claim. "
                        "Checkpoints are end-of-inning %s; model conditions on the "
                        "game's own Statcast score as-of that inning (leak-free); market "
                        "points are the last in-play tick at-or-before the checkpoint "
                        "(<=10min stale, never after).") % "/".join(str(c) for c in CHECKPOINTS),
    }
    _OUT.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    if ledger_rows:
        _ledger_append(ledger_rows)
    return result


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=300)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    doc = run(a.max_games, a.seed)
    print(json.dumps(doc, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
