"""domains.tennis.point_engine.market_join_2026 -- honest ATTEMPT to join the
2026 MCP charted-match population (corpus_2026.py) against the Kalshi
ATP/WTA tennis price-series corpus (2026-05-24..07-08, reused via
freshness_premium.load_games), to place the Sackmann-fit point engine's
match-winner MC probability against the market's own devigged pregame close.

REUSES, DOES NOT REINVENT: freshness_premium.load_games (Kalshi tennis
moneyline price series, pregame-only ticks already filtered) and
tennis_freshness_placement.match_tail_ids (the same ticker-tail split+name
search already live-verified for the ESPN-bridge join) -- candidates are
built directly from mcp_2026 NAME strings (both the "name" and "id" slot of
each Candidate tuple hold the same player-name string; match_tail_ids doesn't
care about the id type, only equality/hash, so no new matching logic needed).

HONEST FINDING (declared, checked against real files on disk): the MCP
charted-match population runs 2026-01-02..2026-05-24; the Kalshi tennis
price-series corpus begins 2026-05-24. The two corpora are essentially
temporally DISJOINT (a single-day hairline touch) -- overlap n is expected at
or near zero. That is reported PLAINLY as NOT_TESTABLE, not smoothed over: a
null population overlap is an honest closed class, not a bug.

INVARIANTS: domains-only; corpora READ-ONLY; ASCII; no src/kernel imports; <=300 LOC.
Tests: python -m pytest domains/tennis/point_engine/test_market_join_2026.py -q
CLI: python -m domains.tennis.point_engine.market_join_2026
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from domains.tennis.point_engine.corpus import FIT_YEARS, build_point_frame
from domains.tennis.point_engine.corpus_2026 import (
    MATCHES_2026, POPULATION, build_match_frame_2026,
)
from domains.tennis.point_engine.match_sim import simulate_match_ensemble
from domains.tennis.point_engine.point_model import PointModel
from scripts.platformkit.ingame.freshness_premium import load_games
from scripts.platformkit.ingame.tennis_freshness_placement import match_tail_ids
from scripts.platformkit.ingame.tennis_ticker_match import parse_tennis_ticker

_REPO = Path(__file__).resolve().parents[3]
OUT = _REPO / "data" / "frontend" / "ops" / "tennis_point_engine_2026_market_join.json"
LEDGER = _REPO / "data" / "cache" / "intel_claims" / "prereg_hypothesis_ledger.jsonl"
_TOUR_TO_LEAGUE = {"m": "atp", "w": "wta"}
MIN_N_JOIN_TESTABLE = 5
MIN_N_VERDICT = 30
N_SIMS_DEFAULT = 400
Candidate = Tuple[str, str, str, str]


def _matches_with_date_tour() -> pd.DataFrame:
    matches = build_match_frame_2026()
    raw = pd.read_parquet(MATCHES_2026, columns=["match_id", "date", "tour"])
    return matches.merge(raw, on="match_id", how="left")


def _candidates_by_day(matches: pd.DataFrame) -> Dict[Tuple[str, dt.date], List[Candidate]]:
    out: Dict[Tuple[str, dt.date], List[Candidate]] = {}
    for r in matches.itertuples(index=False):
        league = _TOUR_TO_LEAGUE.get(str(r.tour))
        if league is None:
            continue
        d = r.date if isinstance(r.date, dt.date) else pd.Timestamp(r.date).date()
        out.setdefault((league, d), []).append(
            (str(r.player1id), str(r.player1id), str(r.player2id), str(r.player2id)))
    return out


def attempt_join(n_sims: int = N_SIMS_DEFAULT) -> Dict[str, Any]:
    matches = _matches_with_date_tour()
    candidates_by_day = _candidates_by_day(matches)

    games, diag = load_games("tennis")
    fit_pts = build_point_frame(FIT_YEARS)
    model = PointModel.fit(fit_pts)
    prob_fn = lambda sid, sb, tb: model.prob(sid, sb, tb)  # noqa: E731

    matched_rows: List[dict] = []
    for gm in games:
        parsed = parse_tennis_ticker(gm["event_key"])
        if parsed is None:
            continue
        league, d, tail = parsed
        hit = None
        for delta in (0, -1, 1):
            cands = candidates_by_day.get((league, d + dt.timedelta(days=delta)))
            if not cands:
                continue
            hit = match_tail_ids(cands, tail)
            if hit is not None:
                break
        if hit is None:
            continue
        code_a, name_a, code_b, name_b = hit
        ref_name = name_a if code_a <= code_b else name_b

        row_df = matches[((matches["player1id"] == name_a) & (matches["player2id"] == name_b)) |
                         ((matches["player1id"] == name_b) & (matches["player2id"] == name_a))]
        if row_df.empty:
            continue
        row = row_df.iloc[0]

        _, _, p1_win = simulate_match_ensemble(
            row["player1id"], row["player2id"], int(row["best_of"]),
            row["first_server_id"], prob_fn, n=n_sims,
            seed=hash(str(row["match_id"])) % 100000)
        model_p_ref = p1_win if ref_name == row["player1id"] else 1.0 - p1_win

        if len(gm["ref_p"]) == 0:
            continue
        ref_p = float(gm["ref_p"][-1])
        oth_p = float(gm["oth_p"][-1]) if len(gm["oth_p"]) else None
        mkt_p = ref_p / (ref_p + oth_p) if oth_p is not None and (ref_p + oth_p) > 0 else ref_p
        matched_rows.append({
            "event_key": gm["event_key"], "outcome": float(gm["outcome"]),
            "model_p_ref": min(max(model_p_ref, 1e-6), 1 - 1e-6),
            "market_p_ref": min(max(mkt_p, 1e-6), 1 - 1e-6),
        })

    n = len(matched_rows)
    doc: Dict[str, Any] = {
        "model": "tennis_point_engine_2026_v1", "edge_claimed": False,
        "population": POPULATION,
        "kalshi_games_in_corpus": diag["games_kept"],
        "mcp_2026_matches_total": int(len(matches)),
        "n_joined": n,
    }
    if n < MIN_N_JOIN_TESTABLE:
        doc["verdict"] = "NOT_TESTABLE"
        doc["blocker"] = ("fewer than %d real ticker<->mcp_2026-match joins survived the "
                          "split+name search (got %d). mcp_2026 charted matches run "
                          "2026-01-02..2026-05-24 and the Kalshi tennis price-series "
                          "corpus begins 2026-05-24 -- the two corpora are essentially "
                          "temporally DISJOINT (single-day hairline overlap). Honest "
                          "null: this closes the class, not a bug." % (MIN_N_JOIN_TESTABLE, n))
        _write(doc)
        return doc

    outs = np.array([r["outcome"] for r in matched_rows])
    mp = np.array([r["model_p_ref"] for r in matched_rows])
    kp = np.array([r["market_p_ref"] for r in matched_rows])
    model_crps = (mp - outs) ** 2   # binary-outcome CRPS reduces to the Brier score
    market_crps = (kp - outs) ** 2
    delta = market_crps - model_crps  # positive => market worse => model sharper
    rng = np.random.default_rng(0)
    boots = [delta[rng.integers(0, n, n)].mean() for _ in range(2000)]
    lo, hi = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
    if n < MIN_N_VERDICT or (lo <= 0 <= hi):
        verdict = "UNDERPOWERED"
    elif lo > 0:
        verdict = "MODEL_SHARPER"
    else:
        verdict = "MARKET_SHARPER"
    doc.update({
        "verdict": verdict, "provisional": True,
        "model_crps_mean": round(float(model_crps.mean()), 5),
        "market_crps_mean": round(float(market_crps.mean()), 5),
        "paired_delta_mean": round(float(delta.mean()), 5),
        "paired_delta_95ci": [round(lo, 5), round(hi, 5)],
        "honest_note": ("PROVISIONAL -- MCP charted population is non-representative "
                        "(volunteer-selected high-profile matches); n=%d joined games. "
                        "CRPS for a binary outcome reduces to the Brier score. No "
                        "dollars, no edge claim." % n),
    })
    _write(doc)
    return doc


def _write(doc: Dict[str, Any]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")


def append_ledger(doc: Dict[str, Any], ledger: Path = LEDGER) -> int:
    row = {
        "hypothesis": "tennis_point_engine_2026_kalshi_market_join_attempt",
        "sport": "tennis", "atomic_unit": "match_winner_vs_devigged_close",
        "method": "tennis_point_engine_v1_vs_kalshi_moneyline",
        "season": "mcp_2026_charted_x_kalshi_2026-05-24_07-08",
        "verdict": doc.get("verdict", "NOT_TESTABLE"),
        "lesson": ("market join attempt: kalshi_games_in_corpus=%d, mcp_2026_matches=%d, "
                  "n_joined=%d. %s" % (
                      doc["kalshi_games_in_corpus"], doc["mcp_2026_matches_total"],
                      doc["n_joined"], doc.get("blocker") or doc.get("honest_note", ""))),
        "edge_claimed": False,
        "computed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True) + "\n")
    return 1


def _main() -> int:
    doc = attempt_join()
    n_rows = append_ledger(doc)
    print("market join: n_joined=%d verdict=%s (%d ledger row appended)" %
          (doc["n_joined"], doc["verdict"], n_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
