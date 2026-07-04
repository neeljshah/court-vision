"""scripts.platformkit.ingame.enrichment_rows_soccer_helpers -- pure/low-level
helpers split out of enrichment_rows_soccer.py to keep both files <=300 LOC
(wave-22 Opus review flagged the pre-split module at 345 LOC, non-blocking).

NO BEHAVIOR CHANGE: this is a pure code-motion split. Every function here is
byte-identical to its former body in enrichment_rows_soccer.py; the facade
module re-exports all of them (`from .enrichment_rows_soccer_helpers import *`
equivalent via explicit names) so `enrichment_rows_soccer.<name>` keeps
working for any caller/test that references the old single-module path.

Per-file test (shares the same test file as the facade -- both are exercised
through the public build_rows()/rows_fn() surface):
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_enrichment_rows_soccer.py -q
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# Naive reference-conditioning magnitude cap (logit space) -- crude on purpose,
# see enrichment_rows_soccer module docstring. Never tuned against outcome
# data (that would leak into the gate it is meant to be judged by).
#
# XG-APPLY (2026-07-04, human-ratified, docs/research/organization-sprint/
# PROPOSED_soccer_xg_wiring.md): _XG_LOGIT_SCALE is now a SHRUNK cross-fit beta
# (0.25 * the SMALLER of the two xg_crossfit_conditioning.py cross-fit betas:
# fit0->eval1 beta=4.354042, fit1->eval0 beta=7.454383 -> 0.25 * 4.354042 =
# 1.0885105, rounded to 1.0885). Still fixed-form / not adaptively retrained.
# This constant change conditions the LIVE forward gate (rows_fn ->
# ingame_enrichment_gates.run_gate_a); it does NOT itself constitute a beat-
# the-market claim -- the backfill market-awareness read (xg_market_awareness.
# json) was NO_ADD_BEYOND_MARKET (CI crosses zero). Re-run run_gate_a FORWARD
# on live ticks for >=2 independent corpora before drawing any new conclusion;
# see the PROPOSED doc's "why this is not applied automatically" section for
# the full caveat (reconstructed-corpus beta, not a live-in-play magnitude).
_XG_LOGIT_SCALE = 1.0885
# sot_diff intentionally left UNWIRED (0.0): the cross-fit lane deliberately
# isolated xg_diff alone; a joint 2-parameter fit is a separate, un-pre-
# declared family per the PROPOSED doc step 2.
_SOT_LOGIT_SCALE = 0.0
_MAX_LOGIT_SHIFT = 1.5


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        if not path.is_file():
            return out
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except Exception as exc:  # noqa: BLE001 -- a bad sidecar is an honest miss
        logger.debug("enrichment_rows_soccer: read failed %s: %s", path, exc)
    return out


def _fotmob_matches(fotmob_dir: Path) -> List[Dict[str, Any]]:
    """One entry per sidecar file: {id, home, away, snapshots (fetch_ts-sorted)}.
    Never raises."""
    out: List[Dict[str, Any]] = []
    try:
        if not fotmob_dir.is_dir():
            return out
        for jf in sorted(fotmob_dir.glob("*.jsonl")):
            rows = _read_jsonl(jf)
            if not rows:
                continue
            rows.sort(key=lambda r: str(r.get("fetch_ts", "")))
            last = rows[-1]
            out.append({
                "id": jf.stem,
                "home": {"name": last.get("home")},
                "away": {"name": last.get("away")},
                "snapshots": rows,
            })
    except Exception as exc:  # noqa: BLE001
        logger.debug("enrichment_rows_soccer: fotmob scan failed: %s", exc)
    return out


def _asof_snapshot(snapshots: Sequence[Dict[str, Any]], tick_ts: str) -> Optional[Dict[str, Any]]:
    """Latest snapshot with fetch_ts <= tick_ts (strict as-of; ISO-8601 UTC
    strings compare correctly). None if no eligible snapshot -- never a leak."""
    best: Optional[Dict[str, Any]] = None
    best_ts = ""
    for snap in snapshots:
        sts = str(snap.get("fetch_ts", ""))
        if not sts or sts > tick_ts:
            continue
        if sts >= best_ts:
            best_ts = sts
            best = snap
    return best


def _ticker_team_names(ticker: str, resolver: Any) -> Optional[Any]:
    """Resolve a Kalshi WC ticker's two team names via the injected
    SoccerOutcomeResolver, so xG matching never disagrees with settlement.
    None if unresolvable."""
    try:
        from scripts.platformkit.ingame.soccer_outcome import parse_wc_ticker
        parsed = parse_wc_ticker(ticker)
        if parsed is None:
            return None
        _date, code_a, code_b = parsed
        if not resolver.available:
            return None
        name_a = _resolve_via_index(code_a, resolver)
        name_b = _resolve_via_index(code_b, resolver)
        if name_a is None or name_b is None:
            return None
        return (name_a, name_b)
    except Exception as exc:  # noqa: BLE001
        logger.debug("enrichment_rows_soccer: ticker resolve failed %s: %s", ticker, exc)
        return None


def _home_win_from_resolver(res: Any):
    """Wrap one SoccerOutcomeResolver's final_score into a binary home_win
    outcome_fn (draw -> None, matches ingame_outcome_verdict_multi's
    _soccer_outcome_fn draw-handling). Local so the default outcome_fn always
    matches the SAME resolver instance used for team-name matching."""
    def _fn(ticker: str) -> Optional[float]:
        if not res.available:
            return None
        try:
            score = res.final_score(ticker)
        except Exception:  # noqa: BLE001
            return None
        if score is None:
            return None
        hs, as_ = score
        if hs == as_:
            return None  # draw: not a binary home_win outcome
        return 1.0 if hs > as_ else 0.0
    return _fn


def _resolve_via_index(code: str, res: Any) -> Optional[str]:
    """Reuse SoccerOutcomeResolver's name index/override logic (single source
    of truth for the FIFA-code table stays in soccer_outcome.py)."""
    from scripts.platformkit.ingame.soccer_outcome import _resolve_code
    return _resolve_code(code, res._name_index)  # noqa: SLF001 -- intentional reuse


def _xg_conditioned_prob(model_prob: float, xg_diff: Optional[float],
                          sot_diff: Optional[float]) -> Optional[float]:
    """Naive logit-space nudge of the baseline prob by as-of xg_diff/sot_diff.
    See enrichment_rows_soccer module docstring: crude reference conditioning,
    measurement-only. None if inputs are unusable (never a guess)."""
    if xg_diff is None and sot_diff is None:
        return None
    try:
        p = min(max(float(model_prob), 1e-6), 1 - 1e-6)
        logit = math.log(p / (1 - p))
        shift = 0.0
        if xg_diff is not None:
            shift += _XG_LOGIT_SCALE * float(xg_diff)
        if sot_diff is not None:
            shift += _SOT_LOGIT_SCALE * float(sot_diff)
        shift = max(-_MAX_LOGIT_SHIFT, min(_MAX_LOGIT_SHIFT, shift))
        new_logit = logit + shift
        return 1.0 / (1.0 + math.exp(-new_logit))
    except Exception as exc:  # noqa: BLE001
        logger.debug("enrichment_rows_soccer: conditioning failed: %s", exc)
        return None


__all__ = [
    "_XG_LOGIT_SCALE", "_SOT_LOGIT_SCALE", "_MAX_LOGIT_SHIFT",
    "_read_jsonl", "_fotmob_matches", "_asof_snapshot", "_ticker_team_names",
    "_home_win_from_resolver", "_resolve_via_index", "_xg_conditioned_prob",
]
