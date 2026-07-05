"""scripts.platformkit.ingame.npb_kbo_wire_proof -- LANE npbkbo-live-model (wire-dispatch).

CORRECTED FINDING: neither NPB nor KBO is wired into live_board.live_model_home_prob.
Both sports' BASE fits are HONEST_NEGATIVE, disqualified by the same planted
pure-noise control (data/domains/{npb,kbo}/ingame_base_fit_verdict.json,
disqualified_by_noise_control=true, params_persisted=false) -- a positive BSS on the real
corpus cannot be distinguished from the synthesis (endpoint-pin) artifact the control
reproduces on zero-signal data, so neither fit is trusted as in-game skill.

Replays real captured npb/kbo in-play ticks (data/cache/inplay_history/{npb,kbo}/*.jsonl,
the wave-40-mapped capture files) through the REAL live_board.live_model_home_prob path and
counts real-prob vs None (expected: 100% None for BOTH sports, symmetrically -- no branch
is dispatched for either). Writes data/domains/npb_kbo_model_wire_proof.json.

HONEST FINDING (why none_rate is 1.0 for both sports): even setting the disqualified fits
aside, the captured tick files are Kalshi MARKET-PRICE rows ({sport, game_id, venue, side,
ticker, prob, ts, phase}) -- they carry NO score, clock, or frac_elapsed field at all,
because that is genuinely all the in-play capture loop persists for these two sports.
Feeding them through live_model_home_prob (as a live_board-shaped state dict, using the
only fields present) exercises the REAL dispatch path and its REAL guards; it cannot
manufacture a state_diff/frac_elapsed that was never captured, and there is no dispatch
branch for either sport regardless. This is the same data-availability wall the prior
lane's gap test already found (scripts/platformkit/ingame/test_npb_kbo_live_model_gap.py)
-- this proof re-confirms it against the actual (unwired) code path, on real ticks, not a
synthetic assertion.

Per-file test: this proof script has no separate test file -- it is exercised by
test_kbo_live_model.py, which drives the same live_model_home_prob seam with synthetic
and real-shaped states.
"""
from __future__ import annotations

import glob
import json
import os
import random
from typing import Any, Dict, List

from scripts.platformkit.frontend import live_board as lb

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_OUT_PATH = os.path.join(_REPO, "data", "domains", "npb_kbo_model_wire_proof.json")
_MIN_TICKS = 500


def _load_ticks(sport: str, n: int, seed: int) -> List[Dict[str, Any]]:
    """Read every captured in-play tick for *sport* (both dated files), sample *n*."""
    paths = sorted(glob.glob(os.path.join(_REPO, "data", "cache", "inplay_history",
                                           sport, "*.jsonl")))
    rows: List[Dict[str, Any]] = []
    for p in paths:
        with open(p, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except (ValueError, TypeError):
                    continue
    rnd = random.Random(seed)
    if len(rows) > n:
        rows = rnd.sample(rows, n)
    return rows


def _tick_to_state(row: Dict[str, Any]) -> Dict[str, Any]:
    """Real captured tick -> the state shape live_model_home_prob expects. The captured
    rows carry no score/clock, so home_score/away_score/frac_elapsed are honestly absent
    (not fabricated) -- this exercises the real dispatch + its real missing-field guard."""
    return {
        "home": row.get("game_id"),  # id-only; these rows never carried a resolvable team
        "away": row.get("side"),
        "home_score": None, "away_score": None,
        "state_diff": None, "frac_elapsed": None,
        "status": "in_progress_or_scheduled",
    }


def run_proof(n_per_sport: int = _MIN_TICKS, seed: int = 40) -> Dict[str, Any]:
    wired: List[str] = []
    skipped_honest_negative = ["npb", "kbo"]
    per_sport: Dict[str, Any] = {}
    sample_probs: List[Any] = []
    total_ticks = 0
    total_none = 0
    for sport in ("npb", "kbo"):
        rows = _load_ticks(sport, n_per_sport, seed)
        n = len(rows)
        none_ct = 0
        probs_this_sport: List[float] = []
        for row in rows:
            state = _tick_to_state(row)
            p = lb.live_model_home_prob(sport, state)
            if p is None:
                none_ct += 1
            else:
                probs_this_sport.append(p)
        total_ticks += n
        total_none += none_ct
        per_sport[sport] = {
            "n_replayed": n,
            "n_real_prob": n - none_ct,
            "n_none": none_ct,
            "none_rate": (none_ct / n) if n else None,
        }
        sample_probs.extend(probs_this_sport[:10])
    out = {
        "lane": "npbkbo-live-model wire-dispatch",
        "wired_sports": wired,
        "skipped_honest_negative": skipped_honest_negative,
        "replay_ticks_scored": total_ticks,
        "none_rate": (total_none / total_ticks) if total_ticks else None,
        "per_sport": per_sport,
        "sample_probs": sample_probs[:10],
        "params_used": None,
        "honest_note": (
            "Neither npb nor kbo is wired into live_board.live_model_home_prob: both "
            "sports' BASE fits are HONEST_NEGATIVE, disqualified by the same planted "
            "pure-noise control (params_persisted=false for both -- see "
            "data/domains/{npb,kbo}/ingame_base_fit_verdict.json). none_rate==1.0 here "
            "is the CORRECT result of the real (unwired) dispatch path on real data, not "
            "a bug -- there is no branch for either sport, so no state shape can ever "
            "produce a real prob today. Captured inplay_history ticks also carry no "
            "score/clock/frac_elapsed field for npb/kbo (market-price rows only), an "
            "independent reason none_rate would be 1.0 even if either fit had cleared "
            "the noise control. No $ edge claimed."),
    }
    with open(_OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    return out


if __name__ == "__main__":
    result = run_proof()
    print(json.dumps(result, indent=2))
