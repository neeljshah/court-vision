"""scripts.platformkit.ingame.enrichment_rows_soccer -- LANE 4: GATE A's real
rows_fn producer (soccer xG conditioning judge, ingame_enrichment_gates.run_gate_a).

THE GAP: GATE A has a fixture-proven judge (judge_enrichment) but its default
rows_fn (_default_rows_soccer_xg) honestly returned [] -- no producer existed
that AS-OF-JOINS captured soccer_intl grade ticks with fotmob xG sidecars into
the {game_id, y, model_prob, model_prob_enriched} shape the judge expects.
This module is that producer.

JOIN (STRICT AS-OF, leak-free): (a) grade ticks
data/cache/ingame_grade/soccer_intl/<ticker>.jsonl (live_grade._load_pairs:
{game_id, ts, model_prob, market_prob}); (b) fotmob snapshots (live dir by
default, or the LANE 2 backfill dir -- see PROVENANCE below) matched via
ingame_fotmob.match_to_fixture on the ticker's team names (soccer_outcome.
parse_wc_ticker + the SAME code->name resolution the outcome resolver uses,
so xG matching never disagrees with settlement). A snapshot joins a tick only
if fetch_ts <= tick ts (never future); latest eligible one wins. No eligible
snapshot -> model_prob_enriched=None -> row skipped, never imputed.

model_prob_enriched IS A NAIVE, MEASUREMENT-ONLY REFERENCE CONDITIONING: no
live xG-conditioned model exists yet, so this producer nudges the baseline
model_prob in logit space by as-of xg_diff/sot_diff (fixed-form, clipped, NOT
fitted/trained, NEVER wired to any decision path) purely so GATE A has a
genuine (if crude) enriched arm to judge WORSE/MATCH/BETTER against.

HONESTY: probability/Brier space only; no $/roi/pnl field; a join miss /
resolver miss / bad tick is skipped, never fabricated or imputed.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no network (reads local
jsonl only); no data/registry write; no flag flip; never raises.

LOC SPLIT (wave-22, non-behavioral): the pure/low-level helpers (jsonl
reading, fotmob matching, as-of snapshot pick, ticker/name resolution, the
naive xG logit conditioning fn, and their tuning constants) live in the
sibling module enrichment_rows_soccer_helpers.py and are re-exported here
unchanged so `enrichment_rows_soccer.<name>` keeps working for any existing
caller/test. This module keeps build_rows/rows_fn/rows_fn_backfill/main --
the producer's public surface -- plus all provenance/caveat documentation.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_enrichment_rows_soccer.py -q
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.ingame.enrichment_rows_soccer_helpers import (
    _XG_LOGIT_SCALE,
    _SOT_LOGIT_SCALE,
    _MAX_LOGIT_SHIFT,
    _read_jsonl,
    _fotmob_matches,
    _asof_snapshot,
    _ticker_team_names,
    _home_win_from_resolver,
    _resolve_via_index,
    _xg_conditioned_prob,
)

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade" / "soccer_intl"
DEFAULT_FOTMOB_DIR = _REPO_ROOT / "data" / "domains" / "soccer_intl" / "fotmob_live"
DEFAULT_FOTMOB_BACKFILL_DIR = _REPO_ROOT / "data" / "domains" / "soccer_intl" / "fotmob_backfill"

SPORT = "soccer_intl"

# LANE 2 addition: row provenance selector. "live" (default, unchanged) reads
# DEFAULT_FOTMOB_DIR, no extra field. "backfill" reads DEFAULT_FOTMOB_BACKFILL_DIR
# and tags rows provenance="backfill_validation" -- never pool with GATE A's
# forward verdict (see ingame_enrichment_gates.run_gate_a); the backfill
# validation pass writes its own separate verdict file.
PROVENANCE_LIVE = "live"
PROVENANCE_BACKFILL = "backfill"
_ROW_TAG_BACKFILL = "backfill_validation"


def build_rows(*, grade_dir: Optional[Path] = None,
              fotmob_dir: Optional[Path] = None,
              outcome_fn: Optional[Any] = None,
              resolver: Optional[Any] = None,
              provenance: str = PROVENANCE_LIVE) -> List[Dict[str, Any]]:
    """GATE A production rows: as-of-joined {game_id, y, model_prob,
    model_prob_enriched} for every graded soccer_intl tick with a resolvable
    outcome AND a strict as-of fotmob match. *resolver* is injectable for
    hermetic tests; defaults to the real parquet-backed resolver.

    *provenance*: "live" (default, unchanged -- reads fotmob_dir or
    DEFAULT_FOTMOB_DIR, no extra row field) or "backfill" (reads fotmob_dir or
    DEFAULT_FOTMOB_BACKFILL_DIR, tags every row provenance="backfill_validation";
    see module docstring -- never pool with the forward gate). An explicit
    *fotmob_dir* always wins over the provenance default. Never raises."""
    rows: List[Dict[str, Any]] = []
    try:
        gdir = Path(grade_dir) if grade_dir is not None else DEFAULT_GRADE_DIR
        if fotmob_dir is not None:
            fdir = Path(fotmob_dir)
        elif provenance == PROVENANCE_BACKFILL:
            fdir = DEFAULT_FOTMOB_BACKFILL_DIR
        else:
            fdir = DEFAULT_FOTMOB_DIR
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
                row = {
                    "game_id": ticker, "ts": ts, "y": float(y),
                    "model_prob": float(mp), "model_prob_enriched": enriched,
                    "xg_home": xg_home, "xg_away": xg_away,
                    "xg_asof_min": snap.get("cutoff_min"),
                }
                if provenance == PROVENANCE_BACKFILL:
                    row["provenance"] = _ROW_TAG_BACKFILL
                rows.append(row)
    except Exception as exc:  # noqa: BLE001 -- a producer failure yields honest [] rows
        logger.warning("enrichment_rows_soccer.build_rows failed: %s", exc)
        return []
    return rows


def rows_fn() -> List[Dict[str, Any]]:
    """Zero-arg entry point matching ingame_enrichment_gates.RowsFn's contract
    (used by run_gate_a(rows_fn=enrichment_rows_soccer.rows_fn))."""
    return build_rows()


def rows_fn_backfill() -> List[Dict[str, Any]]:
    """LANE 2 VALIDATION pass: as-of-joins against the backfill sidecar dir,
    rows tagged provenance="backfill_validation". NEVER pass to run_gate_a
    (forward verdict file) -- use judge_enrichment(rows) + a separate
    validation verdict path (see fotmob_backfill_validation)."""
    return build_rows(provenance=PROVENANCE_BACKFILL)


def main() -> None:
    rows = build_rows()
    n_games = len({r["game_id"] for r in rows})
    print("enrichment_rows_soccer | n_joined_rows=%d n_games=%d" % (len(rows), n_games))


if __name__ == "__main__":
    main()


__all__ = [
    "DEFAULT_GRADE_DIR", "DEFAULT_FOTMOB_DIR", "DEFAULT_FOTMOB_BACKFILL_DIR", "SPORT",
    "PROVENANCE_LIVE", "PROVENANCE_BACKFILL",
    "build_rows", "rows_fn", "rows_fn_backfill",
    # re-exported from enrichment_rows_soccer_helpers for backward compatibility
    "_XG_LOGIT_SCALE", "_SOT_LOGIT_SCALE", "_MAX_LOGIT_SHIFT",
    "_read_jsonl", "_fotmob_matches", "_asof_snapshot", "_ticker_team_names",
    "_home_win_from_resolver", "_resolve_via_index", "_xg_conditioned_prob",
]
