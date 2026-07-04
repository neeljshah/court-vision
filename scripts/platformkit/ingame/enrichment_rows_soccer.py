"""scripts.platformkit.ingame.enrichment_rows_soccer -- LANE 4: GATE A's real
rows_fn producer (soccer xG conditioning judge, ingame_enrichment_gates.run_gate_a).

THE GAP: GATE A has a fixture-proven judge (judge_enrichment) but its default
rows_fn (_default_rows_soccer_xg) honestly returned [] -- no producer existed
that AS-OF-JOINS captured soccer_intl grade ticks with fotmob xG sidecars into
the {game_id, y, model_prob, model_prob_enriched} shape the judge expects.
This module is that producer.

JOIN (STRICT AS-OF, leak-free): (a) grade ticks
data/cache/ingame_grade/soccer_intl/<ticker>.jsonl (live_grade._load_pairs:
{game_id, ts, model_prob, market_prob}); (b) fotmob snapshots
data/domains/soccer_intl/fotmob_live/<matchId>.jsonl (ingame_fotmob
append_snapshot rows: {home, away, fetch_ts, xg_home, xg_away, sot_diff,
cutoff_min}), matched via ingame_fotmob.match_to_fixture on the ticker's
team names (soccer_outcome.parse_wc_ticker + the SAME code->name resolution
the outcome resolver uses, so xG matching never disagrees with settlement).
A snapshot joins a tick only if fetch_ts <= tick ts (never a future
snapshot); the LATEST eligible one wins. No eligible snapshot ->
model_prob_enriched=None -> row skipped by the judge, never imputed.

model_prob_enriched IS A NAIVE, MEASUREMENT-ONLY REFERENCE CONDITIONING: no
live xG-conditioned model exists yet, so this producer nudges the baseline
model_prob in logit space by as-of xg_diff/sot_diff (fixed-form, clipped, NOT
fitted/trained, NEVER wired to any decision path) purely so GATE A has a
genuine (if crude) enriched arm to judge WORSE/MATCH/BETTER against. A future
lane may replace this with a properly fit model without changing the row-shape
contract.

HONESTY: probability/Brier space only; no $/roi/pnl field; a join miss /
resolver miss / bad tick is skipped, never fabricated or imputed.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no network (reads local
jsonl only); no data/registry write; no flag flip; never raises.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_enrichment_rows_soccer.py -q
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade" / "soccer_intl"
DEFAULT_FOTMOB_DIR = _REPO_ROOT / "data" / "domains" / "soccer_intl" / "fotmob_live"

SPORT = "soccer_intl"

# Naive reference-conditioning magnitude cap (logit space) -- crude on purpose,
# see module docstring. Never tuned against outcome data (that would leak into
# the gate it is meant to be judged by).
_XG_LOGIT_SCALE = 0.15
_SOT_LOGIT_SCALE = 0.03
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
    See module docstring: crude reference conditioning, measurement-only.
    None if inputs are unusable (never a guess)."""
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


def build_rows(*, grade_dir: Optional[Path] = None,
              fotmob_dir: Optional[Path] = None,
              outcome_fn: Optional[Any] = None,
              resolver: Optional[Any] = None) -> List[Dict[str, Any]]:
    """GATE A production rows: as-of-joined {game_id, y, model_prob,
    model_prob_enriched} for every graded soccer_intl tick with a resolvable
    outcome AND a strict as-of fotmob match. *resolver* is injectable for
    hermetic tests; defaults to the real parquet-backed resolver. Never
    raises (bad inputs just yield fewer/zero rows)."""
    rows: List[Dict[str, Any]] = []
    try:
        gdir = Path(grade_dir) if grade_dir is not None else DEFAULT_GRADE_DIR
        fdir = Path(fotmob_dir) if fotmob_dir is not None else DEFAULT_FOTMOB_DIR
        if not gdir.is_dir():
            return rows

        from scripts.platformkit.ingame import live_grade as lg
        from domains.soccer.ingame_fotmob import match_to_fixture

        res = resolver
        if res is None:
            from scripts.platformkit.ingame.soccer_outcome import SoccerOutcomeResolver
            res = SoccerOutcomeResolver()

        # IMPORTANT: the default outcome_fn is derived from the SAME resolver
        # instance used for team-name matching (never a second, independently
        # constructed resolver) -- otherwise an injected test resolver would
        # silently disagree with a real-parquet-backed outcome_fn.
        ofn = outcome_fn
        if ofn is None:
            ofn = _home_win_from_resolver(res)

        matches = _fotmob_matches(fdir)
        if not matches:
            return rows

        for gf in sorted(gdir.glob("*.jsonl")):
            if gf.name.startswith("_"):
                continue
            ticker = gf.stem
            try:
                y = ofn(ticker)
            except Exception:  # noqa: BLE001 -- unresolvable outcome is an honest skip
                y = None
            if y is None:
                continue
            names = _ticker_team_names(ticker, res)
            if names is None:
                continue
            home_name, away_name = names
            fx = match_to_fixture(matches, home_name, away_name)
            if fx is None:
                continue
            snapshots = fx.get("snapshots") or []
            try:
                ticks = lg._load_pairs(gf)  # noqa: SLF001 -- shared leak-free loader
            except Exception:  # noqa: BLE001
                ticks = []
            for t in ticks:
                mp = t.get("model_prob")
                ts = str(t.get("ts", ""))
                if mp is None or not ts:
                    continue
                snap = _asof_snapshot(snapshots, ts)
                if snap is None:
                    continue
                xg_home, xg_away = snap.get("xg_home"), snap.get("xg_away")
                xg_diff = (float(xg_home) - float(xg_away)) if (
                    xg_home is not None and xg_away is not None) else None
                sot_diff = snap.get("sot_diff")
                enriched = _xg_conditioned_prob(float(mp), xg_diff, sot_diff)
                if enriched is None:
                    continue
                rows.append({
                    "game_id": ticker, "ts": ts, "y": float(y),
                    "model_prob": float(mp), "model_prob_enriched": enriched,
                    "xg_home": xg_home, "xg_away": xg_away,
                    "xg_asof_min": snap.get("cutoff_min"),
                })
    except Exception as exc:  # noqa: BLE001 -- a producer failure yields honest [] rows
        logger.warning("enrichment_rows_soccer.build_rows failed: %s", exc)
        return []
    return rows


def rows_fn() -> List[Dict[str, Any]]:
    """Zero-arg entry point matching ingame_enrichment_gates.RowsFn's contract
    (used by run_gate_a(rows_fn=enrichment_rows_soccer.rows_fn))."""
    return build_rows()


def main() -> None:
    rows = build_rows()
    n_games = len({r["game_id"] for r in rows})
    print("enrichment_rows_soccer | n_joined_rows=%d n_games=%d" % (len(rows), n_games))


if __name__ == "__main__":
    main()


__all__ = [
    "DEFAULT_GRADE_DIR", "DEFAULT_FOTMOB_DIR", "SPORT",
    "build_rows", "rows_fn",
]
