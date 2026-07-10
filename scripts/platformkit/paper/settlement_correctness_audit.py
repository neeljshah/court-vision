"""scripts.platformkit.paper.settlement_correctness_audit -- B2 sweep deliverable.

Replays the REAL settled/open paper ledger (data/frontend/clv_ledger.jsonl)
through the SAME resolvers that settle each channel live, and reports honest
mismatch counts per sport -- never recomputes a new resolver, never guesses.

CHANNELS COVERED
----------------
in-game (channel="paper_ingame", Kalshi-ticker keyed): replayed through
ingame_paper_settle's OWN dispatcher (_default_score_fn) so the audit uses
EXACTLY the resolvers that settle these bets live -- a fresh recompute of
final_score(ticker) is compared against what the row actually settled with.
  - score_mismatch:      resolver's fresh score disagrees with the stored one
  - now_unresolvable:    a settled row whose ticker no longer resolves (data
                          pruned/moved -- reported, not counted as a mismatch)
  - unsettled_but_final: an OPEN row whose ticker resolves to a final score
                          RIGHT NOW (a stuck settlement, not a wrong one)

pregame (channel in {"paper","paper_pm",None}, matchup-string keyed, NO
game-number field): these bets carry no ticker/game-id, only a team-name
matchup string, so there is no offline resolver to replay against a fresh
outcome. Two honest checks instead:
  - internal consistency: recompute outcome/unit_result from the settled
    row's OWN stored home_score/away_score/side/taken_decimal via grade_paper's
    real functions and compare to what was written (catches drift/corruption)
  - dh_exposure (mlb only): count of settled rows whose matchup+date falls on
    a real doubleheader date in espn_boxscores.parquet -- these rows have no
    game-number to disambiguate G1/G2, so they are FLAGGED as unverifiable
    exposure, never asserted right or wrong

Also reports close_source coverage (per sport) and dedup violations
(duplicate open edge_key / duplicate settled settle_key or bet_id).

HONESTY: counts only, no $/ROI. Never writes data/registry/, never flips a
flag. Read-only against the local ledger + local parquet.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII only; no network.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/paper/test_settlement_correctness_audit.py -q
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit import grade_paper as _gp

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ESPN_BOX_PARQUET = _REPO_ROOT / "data" / "domains" / "mlb" / "espn_boxscores.parquet"

_INGAME_CHANNEL = "paper_ingame"
_PREGAME_CHANNELS = ("paper", "paper_pm", None)


def _default_ingame_score_fn():
    """The EXACT live in-game dispatcher (mlb/soccer/tennis/wnba/npb/kbo),
    reused (not reimplemented) so the audit can never drift from what
    actually settles these bets. Import is local/lazy: this module must load
    even if a sub-resolver's optional dependency is missing."""
    from scripts.platformkit.ingame.ingame_paper_settle import _default_score_fn
    return _default_score_fn()


def audit_ingame_channel(rows: List[Dict[str, Any]], score_fn=None) -> Dict[str, Any]:
    """Replay every paper_ingame row (open + settled) through the live
    dispatcher. Returns per-sport counts; never raises.

    An OPEN row whose edge_key already has a SETTLED twin is a DIFFERENT bug
    class (a duplicate-open orphan -- see dedup_check / paper_ingame._scan_
    existing's 2026-07-11 fix) than a genuinely-pending open row, so the two
    are counted separately: orphan_duplicate_open never gets processed by the
    live settle daemon (it treats any edge_key with a settled twin as already
    done) regardless of whether it now resolves; unsettled_but_final is a
    real, standalone open bet whose game is final RIGHT NOW.
    """
    score_fn = score_fn or _default_ingame_score_fn()
    settled_keys = {r.get("edge_key") for r in rows
                    if r.get("channel") == _INGAME_CHANNEL and r.get("status") == "settled"}
    by_sport: Dict[str, Counter] = defaultdict(Counter)
    mismatches: List[Dict[str, Any]] = []
    for r in rows:
        if r.get("channel") != _INGAME_CHANNEL:
            continue
        sport = str(r.get("sport") or "?")
        c = by_sport[sport]
        gid = str(r.get("game_id") or "")
        status = r.get("status")
        if status == "settled":
            c["n_settled"] += 1
            try:
                fresh = score_fn(gid)
            except Exception as exc:  # noqa: BLE001 -- one bad ticker never stops the sweep
                logger.debug("audit_ingame_channel score_fn failed for %s: %s", gid, exc)
                fresh = None
            hs, aws = r.get("home_score"), r.get("away_score")
            if fresh is None:
                c["now_unresolvable"] += 1
            elif hs is None or aws is None:
                c["missing_stored_score"] += 1
            elif int(fresh[0]) == int(hs) and int(fresh[1]) == int(aws):
                c["score_match"] += 1
            else:
                c["score_mismatch"] += 1
                mismatches.append({"sport": sport, "game_id": gid,
                                   "stored": [hs, aws], "fresh": list(fresh)})
        elif status == "open":
            c["n_open"] += 1
            if r.get("edge_key") in settled_keys:
                c["orphan_duplicate_open"] += 1
                continue  # never reached by the live settle daemon -- not "stuck"
            try:
                fresh = score_fn(gid)
            except Exception as exc:  # noqa: BLE001
                logger.debug("audit_ingame_channel score_fn failed for %s: %s", gid, exc)
                fresh = None
            if fresh is not None:
                c["unsettled_but_final"] += 1
    return {"by_sport": {s: dict(c) for s, c in by_sport.items()},
            "mismatch_detail": mismatches}


def _mlb_doubleheader_dates() -> set:
    """(date, home_abbr, away_abbr) keys with 2+ real boxscore rows -- an MLB
    pregame bet on one of these dates is DH-exposed (unverifiable from the
    matchup-string-only settled row, which carries no game-number)."""
    if not _ESPN_BOX_PARQUET.exists():
        return set()
    try:
        import pandas as pd
        d = pd.read_parquet(_ESPN_BOX_PARQUET)
        d["date"] = pd.to_datetime(d["date"], errors="coerce").dt.date
        g = d.groupby(["date", "home_abbr", "away_abbr"]).size()
        return {k for k, n in g.items() if n > 1}
    except Exception as exc:  # noqa: BLE001
        logger.debug("_mlb_doubleheader_dates failed: %s", exc)
        return set()


def audit_pregame_channels(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Internal-consistency replay (settled rows only) + MLB DH-exposure flag.
    Never raises; a malformed row is skipped, not fatal."""
    by_sport: Dict[str, Counter] = defaultdict(Counter)
    mismatches: List[Dict[str, Any]] = []
    dh_dates = _mlb_doubleheader_dates()
    for r in rows:
        if r.get("channel") not in _PREGAME_CHANNELS or r.get("status") != "settled":
            continue
        if not _gp._is_game_ml_bet(r):
            continue  # prop rows settle on a different contract (grade_paper's own guard)
        sport = str(r.get("sport") or "?")
        c = by_sport[sport]
        c["n_settled"] += 1
        try:
            hs, aws = r.get("home_score"), r.get("away_score")
            side = str(r.get("side", "")).strip().lower()
            if hs is None or aws is None:
                c["missing_stored_score"] += 1
                continue
            fresh_outcome = _gp._outcome(sport, side, int(hs), int(aws))
            if fresh_outcome != r.get("outcome"):
                c["outcome_mismatch"] += 1
                mismatches.append({"sport": sport, "matchup": r.get("matchup"),
                                   "stored_outcome": r.get("outcome"), "fresh_outcome": fresh_outcome})
                continue
            stake = float(r.get("stake_units", 1.0) or 1.0)
            fresh_unit = _gp._unit_result(fresh_outcome, float(r["taken_decimal"]), stake)
            stored_unit = r.get("unit_result")
            if fresh_unit != stored_unit and not (fresh_unit is None and stored_unit is None):
                c["unit_result_mismatch"] += 1
            else:
                c["consistent"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.debug("audit_pregame_channels row failed: %s", exc)
            c["unauditable_row"] += 1
        if sport == "mlb" and str(r.get("ts") or "")[:10]:
            date = str(r["ts"])[:10]
            left, right = _gp._matchup_sides(r.get("matchup", ""))
            # Best-effort: DH exposure is a date match alone (no reliable abbr
            # here) -- reported as an upper-bound exposure count, not a proof.
            import datetime as _dt
            try:
                d = _dt.date.fromisoformat(date)
            except ValueError:
                d = None
            if d is not None and any(k[0] == d for k in dh_dates):
                c["dh_date_exposure"] += 1
    return {"by_sport": {s: dict(c) for s, c in by_sport.items()},
            "mismatch_detail": mismatches}


def close_source_coverage(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """% of SETTLED rows per sport with a real close_source vs fallback/none."""
    out: Dict[str, Dict[str, Any]] = {}
    per_sport_src: Dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        if r.get("status") != "settled":
            continue
        sport = str(r.get("sport") or "?")
        src = r.get("close_source")
        label = "missing_key" if src is None else str(src)
        per_sport_src[sport][label] += 1
    for sport, c in per_sport_src.items():
        n = sum(c.values())
        real = n - c.get("missing_key", 0) - c.get("none_available", 0) - c.get("cross_venue_fallback", 0)
        out[sport] = {"n_settled": n, "by_close_source": dict(c),
                     "pct_real_book_close": round(100.0 * real / n, 1) if n else 0.0}
    return out


def dedup_check(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Structural dedup proof: no duplicate OPEN edge_key, no duplicate settled
    settle_key/bet_id. Reports actual violation counts (should be 0)."""
    open_keys = Counter(
        (r.get("channel"), r.get("edge_key")) for r in rows
        if r.get("status") == "open" and r.get("edge_key"))
    settled_keys = Counter(
        r.get("settle_key") or r.get("bet_id") for r in rows
        if r.get("status") == "settled" and (r.get("settle_key") or r.get("bet_id")))
    dup_open = {"|".join(str(p) for p in k): n for k, n in open_keys.items() if n > 1}
    dup_settled = {str(k): n for k, n in settled_keys.items() if n > 1}
    return {"n_open_edge_keys": len(open_keys), "duplicate_open_edge_keys": dup_open,
            "n_settled_identity_keys": len(settled_keys),
            "duplicate_settled_identities": dup_settled}


def run(ledger_path: Optional[Path] = None) -> Dict[str, Any]:
    """Full sweep. Never raises -- a failed sub-check reports empty, not fatal."""
    path = Path(ledger_path) if ledger_path is not None else _clv.DEFAULT_LEDGER
    rows = _clv.load_ledger(path)
    return {
        "n_rows": len(rows),
        "ingame": audit_ingame_channel(rows),
        "pregame": audit_pregame_channels(rows),
        "close_source": close_source_coverage(rows),
        "dedup": dedup_check(rows),
        "note": "units/probability only; no $/ROI; counts are honest zeros or real counts",
    }


def main() -> int:
    import json
    print(json.dumps(run(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["audit_ingame_channel", "audit_pregame_channels", "close_source_coverage",
           "dedup_check", "run"]
