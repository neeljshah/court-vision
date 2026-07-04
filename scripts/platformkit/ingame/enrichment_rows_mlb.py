"""scripts.platformkit.ingame.enrichment_rows_mlb -- GATE B's PRODUCER (LANE 5).

Wires ingame_enrichment_gates_mlb.run_gate_b's rows_fn: an AS-OF join between
(a) captured MLB in-play grade ticks (data/cache/ingame_grade/mlb/<game_id>.jsonl,
game_id = ESPN numeric id OR a Kalshi KXMLBGAME ticker -- both keys coexist in that
dir) and (b) the deep GUMBO live sidecars (data/domains/mlb/gumbo_live/<game_pk>.jsonl,
GATE B's enrichment source: outs/base_state/runners straight from statsapi, not the
lighter ESPN-situation-derived bos already embedded in state_summary).

BRIDGE: game_pk_bridge_live.build_bridge(date) resolves game_pk <-> espn_id <->
kalshi_ticker_stem for a date's slate (never guessed -- ambiguous/unresolved ids are
left None by that module and skipped here, honestly, never guessed here either).

JOIN: for each bridged game_pk with a gumbo sidecar, find its grade file (matched by
either resolved id), then AS-OF join each grade tick's ts to the LATEST gumbo row with
ts <= the tick's ts (strict as-of -- never a future gumbo row). A grade tick with no
gumbo row at or before it (pregame gap) is skipped, honestly, never imputed.

ROW SHAPE emitted (matches GATE B's judge_enrichment contract in
ingame_enrichment_gates.py: {game_id, model_prob, model_prob_enriched, y}, plus
descriptive extras {ts, base_out_state, count_state, market_prob} for inspection):
  game_id            -- the grade file's own key (ticker or espn id; whichever exists)
  ts                 -- the grade tick's timestamp (ISO8601 str)
  model_prob          -- the grade tick's own captured model_prob (score+inning baseline)
  market_prob         -- the grade tick's own captured market_prob (context only, not
                         scored by the judge)
  base_out_state      -- gumbo's base_state*3+outs in [0,23] (int), from the AS-OF gumbo row
  count_state         -- "<balls>-<strikes>" string from the AS-OF gumbo row, or None
  model_prob_enriched -- model_prob logit-shifted by a FIXED (not fit here), standard
                         published RE24 run-expectancy delta vs. the bases-empty/0-out
                         RE24 anchor (0.481) -- deterministic, no data-fit; this is a
                         thin, honest conditioning transform for the judge to score, NOT
                         a claim that this specific transform is the right one.
  outcome / y         -- MlbOutcomeResolver.home_win(ticker) when the game_id (or its
                         bridged kalshi_ticker_stem) parses as a ticker; None if
                         unresolvable/not-final (row still emitted; judge_enrichment
                         skips y=None rows itself, so this stays additive/honest).

STRICT AS-OF / GUARDS (never guessed):
  * An unbridgeable ticker (bridge has no kalshi_ticker_stem/espn_id for this game_pk,
    or a doubleheader-ambiguous key) -> that game_pk is SKIPPED entirely, never guessed.
  * A grade tick strictly before the gumbo sidecar's first row -> skipped (no as-of
    gumbo state exists yet).
  * Malformed / partial JSON lines in either source are skipped, never raise.

INVARIANTS: scripts/platformkit/ingame/ only; <=300 LOC; ASCII only; no src/kernel/api
imports; no network at import; no data/registry write; no flag flip; measurement-only
(no $/roi/pnl; edge_claimed always False downstream via GATE B).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/ingame/test_enrichment_rows_mlb.py -q
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.ingame.game_pk_bridge_live import BridgeRow, build_bridge
from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade" / "mlb"
GUMBO_DIR = _REPO_ROOT / "data" / "domains" / "mlb" / "gumbo_live"

# Standard published base-out RUN EXPECTANCY (RE24), same frozen table as
# ingame_baseout_mlb._RE24 -- duplicated (not imported) because that module's table is
# private; keeping the SAME published constants here, never re-derived from data.
_RE24 = {
    0: (0.481, 0.254, 0.098), 1: (0.859, 0.509, 0.224), 2: (1.100, 0.664, 0.319),
    3: (1.437, 0.884, 0.429), 4: (1.350, 0.950, 0.353), 5: (1.784, 1.130, 0.478),
    6: (1.964, 1.376, 0.580), 7: (2.292, 1.541, 0.752),
}
_RE24_ANCHOR = _RE24[0][0]  # bases-empty, 0-out: the neutral reference point
_ENRICH_BETA = 0.15         # fixed, small, pre-specified logit-shift-per-run scale


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Every parsed JSON-object line of *path*; [] if absent/unreadable. Never raises."""
    out: List[Dict[str, Any]] = []
    if not path.is_file():
        return out
    try:
        with path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except OSError as exc:  # noqa: BLE001 -- a read failure is an honest empty corpus
        logger.debug("enrichment_rows_mlb: read failed for %s: %s", path, exc)
    return out


def _gumbo_ticks_to_utc(gumbo_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Parse each gumbo row's 'ts' ("YYYYMMDD_HHMMSS", poller's own local write clock,
    UTC per gumbo_mlb_poller) into a comparable ISO8601 UTC string under '_ts_iso'.
    Rows with an unparseable ts are dropped (never guessed); ordered by ts ascending."""
    out: List[Dict[str, Any]] = []
    for r in gumbo_rows:
        ts = r.get("ts")
        try:
            dt = datetime.strptime(str(ts), "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        rr = dict(r)
        rr["_ts_iso"] = dt.isoformat().replace("+00:00", "Z")
        out.append(rr)
    out.sort(key=lambda r: r["_ts_iso"])
    return out


def _asof_gumbo(gumbo_sorted: List[Dict[str, Any]], tick_ts: str) -> Optional[Dict[str, Any]]:
    """LATEST gumbo row with ts <= tick_ts (strict as-of; never a future row). None if
    tick_ts precedes every gumbo row (no as-of state exists yet -- an honest gap)."""
    best: Optional[Dict[str, Any]] = None
    for r in gumbo_sorted:
        if r["_ts_iso"] <= tick_ts:
            best = r
        else:
            break
    return best


def _enrich(model_prob: float, run_expectancy: float) -> float:
    """Deterministic, FIXED (not fit here) logit-shift of *model_prob* by the RE24
    delta vs the bases-empty/0-out anchor. A small, pre-specified beta -- this is a
    thin conditioning transform for GATE B to judge, not a fitted/claimed model."""
    import math
    p = min(1.0 - 1e-6, max(1e-6, float(model_prob)))
    logit = math.log(p / (1.0 - p))
    delta_re = float(run_expectancy) - _RE24_ANCHOR
    shifted = logit + _ENRICH_BETA * delta_re
    return 1.0 / (1.0 + math.exp(-shifted))


def build_rows(date_str: Optional[str] = None, *,
              grade_dir: Optional[Path] = None,
              gumbo_dir: Optional[Path] = None,
              bridge_rows: Optional[List[BridgeRow]] = None,
              outcome_resolver: Optional[MlbOutcomeResolver] = None) -> List[Dict[str, Any]]:
    """Build GATE B's rows for *date_str* (default: today UTC). Never raises -- any
    per-game failure just yields fewer rows, honestly.

    Injectable *bridge_rows*/*grade_dir*/*gumbo_dir*/*outcome_resolver* make this
    hermetically testable without hitting the network or the real data/ tree.
    """
    date_str = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    gdir = Path(grade_dir) if grade_dir is not None else GRADE_DIR
    gudir = Path(gumbo_dir) if gumbo_dir is not None else GUMBO_DIR
    bridges = bridge_rows if bridge_rows is not None else build_bridge(date_str)
    resolver = outcome_resolver if outcome_resolver is not None else _safe_resolver()

    rows: List[Dict[str, Any]] = []
    for b in bridges:
        gumbo_path = gudir / ("%s.jsonl" % b.game_pk)
        gumbo_raw = _read_jsonl(gumbo_path)
        if not gumbo_raw:
            continue  # no gumbo accrual for this game yet -- honest skip
        grade_path = _grade_file_for_dir(b, gdir)
        if grade_path is None:
            continue  # unbridgeable / not-yet-captured -- never guessed
        grade_rows = _read_jsonl(grade_path)
        if not grade_rows:
            continue
        gumbo_sorted = _gumbo_ticks_to_utc(gumbo_raw)
        if not gumbo_sorted:
            continue
        ticker = b.kalshi_ticker_stem
        outcome = resolver.home_win(ticker) if (resolver is not None and ticker) else None
        game_id = grade_path.stem
        for g in grade_rows:
            ts = g.get("ts")
            mp = g.get("model_prob")
            if not ts or mp is None:
                continue
            asof = _asof_gumbo(gumbo_sorted, str(ts))
            if asof is None:
                continue  # tick precedes any gumbo state -- honest gap, never imputed
            try:
                outs = int(asof.get("outs"))
                base_state = int(asof.get("base_state"))
            except (TypeError, ValueError):
                continue
            if outs < 0 or outs > 2 or base_state < 0 or base_state > 7:
                continue
            bos = base_state * 3 + outs
            re = _RE24[base_state][outs]
            balls, strikes = asof.get("balls"), asof.get("strikes")
            count_state = ("%s-%s" % (balls, strikes)
                          if balls is not None and strikes is not None else None)
            try:
                model_prob = float(mp)
            except (TypeError, ValueError):
                continue
            rows.append({
                "game_id": game_id, "game_pk": b.game_pk, "ts": str(ts),
                "model_prob": model_prob,
                "market_prob": g.get("market_prob"),
                "base_out_state": bos, "count_state": count_state,
                "model_prob_enriched": _enrich(model_prob, re),
                "outcome": outcome, "y": outcome,
            })
    return rows


def _grade_file_for_dir(bridge: BridgeRow, grade_dir: Path) -> Optional[Path]:
    for key in (bridge.kalshi_ticker_stem, bridge.espn_id):
        if key:
            p = grade_dir / ("%s.jsonl" % key)
            if p.is_file():
                return p
    return None


def _safe_resolver() -> Optional[MlbOutcomeResolver]:
    try:
        return MlbOutcomeResolver()
    except Exception as exc:  # noqa: BLE001 -- an unavailable box parquet -> no outcomes
        logger.debug("enrichment_rows_mlb: MlbOutcomeResolver init failed: %s", exc)
        return None


def rows_fn_today() -> List[Dict[str, Any]]:
    """GATE B production rows_fn: today's UTC-date bridged rows. Never raises."""
    try:
        return build_rows()
    except Exception as exc:  # noqa: BLE001
        logger.debug("enrichment_rows_mlb.rows_fn_today failed: %s", exc)
        return []


def _main() -> int:  # pragma: no cover -- CLI smoke, not exercised by tests
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today UTC)")
    args = ap.parse_args()
    rows = build_rows(args.date)
    n_with_outcome = sum(1 for r in rows if r.get("outcome") is not None)
    print(json.dumps({"date": args.date or "today", "n_joined": len(rows),
                      "n_with_outcome": n_with_outcome,
                      "n_games": len(set(r["game_id"] for r in rows))}, indent=1))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["build_rows", "rows_fn_today", "GRADE_DIR", "GUMBO_DIR"]
