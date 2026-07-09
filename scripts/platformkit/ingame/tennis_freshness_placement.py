"""scripts.platformkit.ingame.tennis_freshness_placement -- tennis leg of
freshness_model_placement.py (Lane A item 7 follow-up).

Closes the tennis NOT_TESTABLE gap: domains/tennis/matches.parquet (Sackmann,
dated Elo's only input) ended 2025-12-17 with zero overlap against the Kalshi
tennis corpus (2026-05-27..07-05). domains.tennis.results_2026_bridge now
supplies 2026 ESPN results joined to Sackmann player_id, letting the SAME
walk-forward Elo (domains.tennis.elo_walkforward.walk_forward_elo, unedited)
carry through into the overlap window.

TICKER -> PLAYER IDENTITY: reuses tennis_ticker_match.py's own
parse_tennis_ticker/surname_codes AS-IS (already live-verified 92/100 against
real settled tickers for the outcome-resolver use case) instead of inventing
a fresh code scheme. The one adaptation is match_tail_ids: same split+match
search, but returns the matched PLAYER_IDs instead of a win/loss bool, because
here the settlement outcome is already known independently (from the price
series' own result_where_known) -- what's missing is the pre-game MODEL
probability, which needs player identity, not the label.

Candidate pool per (tour, date) is the ACTUAL matches_2026 rows for that day
(a handful of real matches), not the whole ATP/WTA player universe -- far
lower collision risk than a global code index.

Output: merged into data/frontend/ops/freshness_model_placement.json by
freshness_model_placement.build(). edge_claimed: false.
Per-file test: python -m pytest scripts/platformkit/ingame/test_tennis_freshness_placement.py -q
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from domains.tennis.elo_walkforward import walk_forward_elo
from domains.tennis.ingest_sackmann import load_matches
from domains.tennis.results_2026_bridge import build_matches_2026
from scripts.platformkit.ingame.freshness_premium import HORIZONS, _devig, _last_at_or_before, load_games
from scripts.platformkit.ingame.tennis_ticker_match import MAX_CODE_WIDTH, MIN_CODE_WIDTH, parse_tennis_ticker, surname_codes

_ROOT = Path(__file__).resolve().parents[3]
_TENNIS_DIR = _ROOT / "data" / "domains" / "tennis"
_BASE_MATCHES = {"atp": _TENNIS_DIR / "matches.parquet", "wta": _TENNIS_DIR / "wta_matches.parquet"}

Candidate = Tuple[str, int, str, int]  # (name_a, id_a, name_b, id_b)


def _candidates_by_day(matches_2026: pd.DataFrame) -> Dict[Tuple[str, dt.date], List[Candidate]]:
    out: Dict[Tuple[str, dt.date], List[Candidate]] = {}
    for r in matches_2026.itertuples(index=False):
        key = (str(r.tour), r.date if isinstance(r.date, dt.date) else pd.Timestamp(r.date).date())
        out.setdefault(key, []).append((str(r.p1_name), int(r.p1_id), str(r.p2_name), int(r.p2_id)))
    return out


def match_tail_ids(candidates: List[Candidate], tail: str) -> Optional[Tuple[str, int, str, int]]:
    """tennis_ticker_match.match_tail's own split+match search, adapted to return
    the matched (code_a, id_a, code_b, id_b) instead of a win/loss bool -- see
    module docstring for why (outcome is already known here; identity is not)."""
    found = []
    n = len(tail)
    for i in range(MIN_CODE_WIDTH, n - MIN_CODE_WIDTH + 1):
        code_a, code_b = tail[:i], tail[i:]
        if not (MIN_CODE_WIDTH <= len(code_a) <= MAX_CODE_WIDTH):
            continue
        if not (MIN_CODE_WIDTH <= len(code_b) <= MAX_CODE_WIDTH):
            continue
        for na, ida, nb, idb in candidates:
            ca, cb = surname_codes(na), surname_codes(nb)
            if code_a in ca and code_b in cb:
                found.append((code_a, ida, code_b, idb))
            elif code_a in cb and code_b in ca:
                found.append((code_a, idb, code_b, ida))
    uniq = list({f for f in found})
    if len(uniq) != 1:
        return None
    return uniq[0]


def _elo_lut(base_path: Path, matches_2026: pd.DataFrame, tour: str) -> dict:
    base = load_matches(base_path)
    ext_2026 = matches_2026[matches_2026["tour"] == tour]
    ext = pd.concat([base, ext_2026], ignore_index=True) if len(ext_2026) else base
    priced = walk_forward_elo(ext)
    lut: dict = {}
    for r in priced.itertuples(index=False):
        d = r.date if isinstance(r.date, dt.date) else pd.Timestamp(r.date).date()
        lut[(d, frozenset({int(r.p1_id), int(r.p2_id)}))] = {
            int(r.p1_id): float(r.win_prob_p1), int(r.p2_id): 1.0 - float(r.win_prob_p1),
        }
    return lut


def _resolve_model_prob(event_key: str, candidates_by_day: dict, elo_luts: dict) -> Optional[float]:
    parsed = parse_tennis_ticker(event_key)
    if parsed is None:
        return None
    league, date, tail = parsed
    for delta in (0, -1, 1):
        d = date + dt.timedelta(days=delta)
        cands = candidates_by_day.get((league, d))
        if not cands:
            continue
        m = match_tail_ids(cands, tail)
        if m is None:
            continue
        code_a, id_a, code_b, id_b = m
        ref_id = id_a if code_a <= code_b else id_b
        probs = elo_luts.get(league, {}).get((d, frozenset({id_a, id_b})))
        if probs is None:
            continue
        return probs.get(ref_id)
    return None


def tennis_placement() -> dict:
    matches_2026, join_diag = build_matches_2026()
    candidates_by_day = _candidates_by_day(matches_2026)
    elo_luts = {tour: _elo_lut(_BASE_MATCHES[tour], matches_2026, tour) for tour in ("atp", "wta")}

    games, diag = load_games("tennis")
    model_probs_by_game = {gm["event_key"]: _resolve_model_prob(gm["event_key"], candidates_by_day, elo_luts)
                            for gm in games}
    n_resolved = sum(1 for v in model_probs_by_game.values() if v is not None)

    rows = []
    for lbl, sec in HORIZONS:
        m_probs, mo_probs, outs = [], [], []
        for gm in games:
            model_p = model_probs_by_game[gm["event_key"]]
            if model_p is None:
                continue
            cutoff = gm["start"] - sec
            r = _last_at_or_before(gm["ref_ts"], gm["ref_p"], cutoff)
            o = _last_at_or_before(gm["oth_ts"], gm["oth_p"], cutoff) if len(gm["oth_ts"]) else None
            mkt = _devig(r, o)
            if mkt is None:
                continue
            mkt = min(max(mkt, 1e-6), 1 - 1e-6)
            model_p = min(max(model_p, 1e-6), 1 - 1e-6)
            m_probs.append(mkt)
            mo_probs.append(model_p)
            outs.append(gm["outcome"])
        m_probs, mo_probs, outs = np.asarray(m_probs), np.asarray(mo_probs), np.asarray(outs)
        n = len(outs)
        if n == 0:
            rows.append({"horizon": lbl, "n": 0, "market_brier": None, "model_brier": None,
                         "delta_model_minus_market": None, "delta_ci95": [None, None]})
            continue
        mkt_se = (m_probs - outs) ** 2
        mod_se = (mo_probs - outs) ** 2
        delta = mod_se - mkt_se
        rng = np.random.default_rng(0)
        boots = [delta[rng.integers(0, n, n)].mean() for _ in range(1000)] if n >= 3 else [float("nan")]
        lo, hi = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
        rows.append({
            "horizon": lbl, "n": int(n),
            "market_brier": round(float(mkt_se.mean()), 5),
            "model_brier": round(float(mod_se.mean()), 5),
            "delta_model_minus_market": round(float(delta.mean()), 5),
            "delta_ci95": [round(lo, 5), round(hi, 5)],
        })
    join_rate = join_diag.get("join_rate")
    return {
        "sport": "tennis", "status": "TESTED" if games and n_resolved else "LOW_JOIN",
        "games_in_market_corpus": diag["games_kept"],
        "espn_2026_join_rate": join_rate, "espn_2026_join_diag": join_diag,
        "n_tickers_resolved_to_players": n_resolved if games else 0,
        "horizons": rows, "edge_claimed": False,
    }
