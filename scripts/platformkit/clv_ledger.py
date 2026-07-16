"""scripts.platformkit.clv_ledger -- append-only bet ledger + closing-line value.

The honest track-record layer. A bet is recorded WHEN PLACED with the price the
human actually got; later, when the market closes, the bet is settled against the
two-way closing line and its closing-line value (CLV) is computed.

Honesty contract (binding):
  * This is the PROOF GATE before any real money. We do NOT claim a model edge.
    CLV is the one honest yardstick: did you lock a BETTER NUMBER than the close?
  * Append-only, mirroring data/frontend/bet_intents.jsonl: every record is a new
    line; nothing is ever overwritten. Settlement appends a settled twin, it does
    not mutate the open row.
  * Devig is NEVER reimplemented here -- we reuse the vetted Shin solver via
    scripts.platformkit.odds_shop.devig_twoway (which wraps eval_gate.shin).

CLV SIGN (stated explicitly -- the repo has a documented 'record_clv backwards'
gotcha, so this is deliberate):
  CLV is POSITIVE when you GOT A BETTER NUMBER than the close. For a moneyline /
  two-way market we devig the closing line to a no-vig FAIR probability for the
  side you bet (fair_close). Your taken decimal price implies taken_p = 1/decimal.
  You beat the close iff your taken price implies a LOWER probability than the
  fair close -- you are being paid as if the outcome is less likely than the
  market's settled estimate. Hence:

      clv_pct = (fair_close - taken_p) / taken_p * 100.0

  taken_p < fair_close  -> clv_pct > 0  (better number than the close = good)
  taken_p > fair_close  -> clv_pct < 0  (worse number than the close = bad)

  Equivalently in price space: fair decimal at the close is 1/fair_close; you beat
  it when your taken decimal > that fair decimal. Same sign, by construction.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; no secrets; reuse vetted devig.
"""
from __future__ import annotations

import json
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scripts.platformkit.odds_shop import devig_twoway

# Append-only ledger lives under the gitignored data/ tree -- the human's own
# record, never sent anywhere. Override with FRONTEND_CLV_LEDGER env or `path=`.
_HERE = Path(__file__).resolve().parent
DEFAULT_LEDGER = _HERE.parents[1] / "data" / "frontend" / "clv_ledger.jsonl"

_SIDE_HOME = "home"
_SIDE_AWAY = "away"

# Dollar / pnl / roi / bankroll($) keys that must NEVER reach the canonical ledger.
# UNITS ONLY is the binding rail; stripping HERE closes EVERY settlement path
# (including the manual/grade path that historically wrote a `pnl` field) at the
# single raw write primitive, not just the dedup-guarded wrappers.
_BANNED_KEYS = (
    "stake", "pnl", "total_pnl", "total_stake", "paper_roi", "roi",
    "bankroll", "profit", "dollars",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_banned(record: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *record* with every banned dollar/pnl/roi key removed.

    ``stake`` is relabelled to ``stake_units`` (the magnitude is a unit count -- we
    never stored a bankroll) when no explicit stake_units is present, so a legacy
    caller passing a dollar ``stake`` still yields a units row, never a dollar one.
    """
    out = dict(record)
    if "stake" in out and out.get("stake_units") is None:
        try:
            out["stake_units"] = float(out["stake"])
        except (TypeError, ValueError):
            pass
    for k in _BANNED_KEYS:
        out.pop(k, None)
    return out


def _append_line(record: Dict[str, Any], target: Path) -> None:
    """Append one JSON record via lock-guarded IO; falls back through dedup guard.

    Import order (all lazy -- clv_ledger_dedup imports this module, so they
    must be deferred to break the cycle):
      1. clv_ledger_io.append_row     -- lock-guarded, preferred.
      2. clv_ledger_dedup.append_if_new -- status-folded dedup guard (fallback 1).
      3. open("a")                    -- bare write, last resort; never loses a row.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    record = _strip_banned(record)  # UNITS ONLY -- close the $ leak on every path
    # 1. Lock-guarded path (preferred).
    try:
        from scripts.platformkit.clv_ledger_io import append_row as _append_row
        _append_row(record, path=target)
        return
    except Exception:  # noqa: BLE001
        pass
    # 2. Status-folded dedup guard (lazy import breaks circular dep).
    try:
        from scripts.platformkit.clv_ledger_dedup import append_if_new as _aifn
        _aifn(record, target)
        return
    except Exception:  # noqa: BLE001
        pass
    # 3. Bare write: last resort.
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def _game_date(record: Dict[str, Any]) -> str:
    """Stable game-date token for a bet: explicit game_date, else ts date (UTC)."""
    gd = str(record.get("game_date") or "").strip()
    if gd:
        return gd[:10]
    ts = str(record.get("ts") or "")
    return ts[:10]


def bet_id(record: Dict[str, Any]) -> str:
    """Durable identity: sport|event_id-or-matchup|market|side|book|game_date.
    Excludes ts and taken_price so open/settled twins collapse to the same id.
    """
    anchor = str(record.get("event_id") or record.get("matchup") or "")
    market = str(record.get("market") or record.get("market_type") or "moneyline")
    book = str(record.get("taken_book") or record.get("book") or "")
    return "|".join([str(record.get("sport") or ""), anchor, market,
                     str(record.get("side") or ""), book, _game_date(record)])


def event_ckey(record: Dict[str, Any]) -> Optional[str]:
    """Canonical CROSS-LEDGER event key for *record*: the stable str form of
    make_event_key(sport, game_date, home, away, market). Additive join spine so a
    clv bet and a graded prediction on the SAME game+market collapse to one token
    even though bet_id/pred_key stay independent (event_id overlap = 0).

    matchup is 'Away@Home' (ESPN convention); split so home/away canonicalize
    correctly. Absent-tolerant and never raises -- a row that cannot be keyed just
    gets no ckey, exactly like a pre-fix row.
    """
    try:
        from scripts.platformkit.live_edge.paper.event_key import make_event_key
        away, _, home = str(record.get("matchup") or "").partition("@")
        if not home:  # not an 'Away@Home' spelling -> single-token best effort
            home, away = away, ""
        market = str(record.get("market") or record.get("market_type") or "").lower()
        ek = make_event_key(record.get("sport"), _game_date(record),
                            home, away, market)
        return "|".join(ek)
    except Exception:  # noqa: BLE001 -- ckey is best-effort; never block a write
        return None


def record_bet(
    sport: str,
    matchup: str,
    side: str,
    taken_book: str,
    taken_decimal: float,
    model_prob: Optional[float] = None,
    stake_units: float = 1.0,
    *,
    market: Optional[str] = None,
    event_id: Optional[str] = None,
    game_date: Optional[str] = None,
    game_number: Optional[int] = None,
    game_pk: Optional[int] = None,
    path: Optional[Path] = None,
    stake: Optional[float] = None,  # deprecated alias -> treated as UNITS, never $
    claim_tags: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """Append one open bet to the CLV ledger and return the stored record.

    UNITS ONLY -- no dollar/bankroll/pnl field. side must be 'home' or 'away'.
    The legacy stake kwarg is treated as units; a dollar stake field is NEVER written.

    game_number/game_pk (optional, MLB doubleheader disambiguation): stamped only
    when the caller resolved them at placement time (see pm_trading.paper_today_
    support.mlb_dh_stamp); omitted -> field absent, exactly like a pre-fix row, so
    settle-side code that does not yet look for them is unaffected.

    claim_tags (optional, claims-engine persistence fix): {card_id: bool} computed by
    condition_tagger.tag at placement time. Additive, backward-compat -- omitted or
    empty means the field is left off the record entirely, so every pre-fix row and
    every caller that never passes it is unaffected. This is the on-disk source
    card_grader needs to grade pregame cards (it currently finds none because no
    caller persisted this field).
    """
    s = str(side).strip().lower()
    if s not in (_SIDE_HOME, _SIDE_AWAY):
        raise ValueError("side must be 'home' or 'away', got %r" % (side,))
    dec = float(taken_decimal)
    if dec <= 1.0:
        raise ValueError("taken_decimal must be > 1.0, got %r" % (taken_decimal,))
    units = float(stake if stake is not None else stake_units)
    record: Dict[str, Any] = {
        "ts": _now_iso(),
        "sport": str(sport),
        "matchup": str(matchup),
        "side": s,
        "taken_book": str(taken_book),
        "taken_decimal": dec,
        "model_prob": (float(model_prob) if model_prob is not None else None),
        "stake_units": units,
        "status": "open",
        "executed": False,  # invariant: this tool NEVER places a real bet
    }
    # ML placers (run_paper_today / the /api/clv/record endpoint) omit market ->
    # persist bet_id()'s resolved value (default 'moneyline') as market + market_type
    # so the row is never an unlabelled '?' in the board / settler / grade summary.
    resolved_market = str(market) if market is not None else "moneyline"
    record["market"] = record["market_type"] = resolved_market
    if event_id is not None:
        record["event_id"] = str(event_id)
    if game_date is not None:
        record["game_date"] = str(game_date)
    if game_number is not None:
        record["game_number"] = int(game_number)
    if game_pk is not None:
        record["game_pk"] = int(game_pk)
    if claim_tags:
        record["claim_tags"] = dict(claim_tags)
    ck = event_ckey(record)
    if ck:
        record["ckey"] = ck  # additive cross-ledger join key (new rows only)
    record["bet_id"] = bet_id(record)
    target = Path(path) if path is not None else DEFAULT_LEDGER
    _append_line(record, target)
    return record


def compute_clv(
    side: str,
    taken_decimal: float,
    closing_decimal_home: float,
    closing_decimal_away: float,
) -> Dict[str, Any]:
    """Pure CLV math for one two-way bet. No I/O.

    Devigs via Shin solver; positive CLV = better number than the close.
    Returns {taken_p, fair_close, clv_pct, fair_close_decimal, beat_close}.
    """
    s = str(side).strip().lower()
    if s not in (_SIDE_HOME, _SIDE_AWAY):
        raise ValueError("side must be 'home' or 'away', got %r" % (side,))
    fair_home, fair_away = devig_twoway(closing_decimal_home, closing_decimal_away)
    fair_close = fair_home if s == _SIDE_HOME else fair_away
    taken_p = 1.0 / float(taken_decimal)
    # Positive when taken price implies a LOWER prob than the fair close = better number.
    clv_pct = (fair_close - taken_p) / taken_p * 100.0
    fair_close_decimal = (1.0 / fair_close) if fair_close > 0 else None
    return {
        "taken_p": round(taken_p, 8),
        "fair_close": round(fair_close, 8),
        "fair_close_decimal": (round(fair_close_decimal, 6)
                               if fair_close_decimal is not None else None),
        "clv_pct": round(clv_pct, 6),
        "beat_close": clv_pct > 0.0,
    }


def settle_closing_line(
    bet: Dict[str, Any],
    closing_decimal_home: float,
    closing_decimal_away: float,
    *,
    close_source: Optional[str] = None,
    close_venue: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a settled twin of *bet* with CLV fields filled in. Pure, no I/O.

    close_source/close_venue are OPTIONAL and stamped on the settled row only
    when the caller passes them (e.g. pm_close_capture's same-venue Kalshi
    resolution) -- omitted for every pre-existing caller, so this is additive
    and never disturbs a caller that doesn't know its close's provenance.
    """
    clv = compute_clv(
        bet["side"], bet["taken_decimal"],
        closing_decimal_home, closing_decimal_away,
    )
    settled = dict(bet)
    settled["status"] = "settled"
    settled["settled_at"] = _now_iso()
    settled["closing_decimal_home"] = float(closing_decimal_home)
    settled["closing_decimal_away"] = float(closing_decimal_away)
    settled["fair_close_prob"] = clv["fair_close"]
    settled["taken_implied_prob"] = clv["taken_p"]
    settled["clv_pct"] = clv["clv_pct"]
    settled["beat_close"] = clv["beat_close"]
    if close_source is not None:
        settled["close_source"] = close_source
    if close_venue is not None:
        settled["close_venue"] = close_venue
    return settled


def append_settlement(
    settled: Dict[str, Any], *, path: Optional[Path] = None
) -> Dict[str, Any]:
    """Append a settled record to the ledger (append-only; never overwrites)."""
    target = Path(path) if path is not None else DEFAULT_LEDGER
    _append_line(settled, target)
    return settled


_MIN_GAME_ID_LEN = 3  # e.g. "gg" (len=2) is malformed; real IDs are e.g. "401859967"

# A taken price more than this many times longer (in DECIMAL odds) than where its
# OWN side actually closed is OFF-MARKET: no book offered it, so it is a misparsed /
# stale line. Computing CLV from it fabricates a huge fake +CLV (a "taken" 12.0 on a
# game that closed ~1.95 -> +497% CLV), which would dishonestly inflate the headline
# mean. Such rows are EXCLUDED from the CLV aggregate (read-time only -- the on-disk
# ledger is never mutated, mirroring _is_synthetic_row) and counted as suspect so the
# exclusion stays transparent. Tune via CLV_MAX_TAKEN_CLOSE_RATIO.
_MAX_TAKEN_CLOSE_RATIO = float(
    os.environ.get("CLV_MAX_TAKEN_CLOSE_RATIO", "2.5") or 2.5)

# --- suspect_close write-time guard (pre-registered 2026-07-15) --------------
# A settled row whose |clv_pct| exceeds SUSPECT_CLV_PCT *AND* whose implied fair-
# close decimal (1/fair_close_prob) is implausible vs the taken decimal (ratio
# outside [1/RATIO, RATIO]) is stamped clv_status="suspect_close" at grade time.
# BOTH conditions are required: |clv_pct|>50 alone would wrongly flag legit
# longshots (audit moneyline_clv_mean_audit.md: legit p95 = +119.9). The decimal-
# ratio gate is what separates a real longshot (fair 6.0 taken 10.0, ratio 0.6 ->
# kept) from a degenerate join (fair 1.86 taken 56.0, ratio 0.03 -> suspect) or a
# collapsed close (fair 1.01 taken 6.25, ratio 0.16 -> suspect). See
# docs/research/execution-quality/suspect_close_audit.md for the full rule.
SUSPECT_CLV_PCT = float(os.environ.get("CLV_SUSPECT_PCT", "50") or 50)
SUSPECT_DECIMAL_RATIO = float(os.environ.get("CLV_SUSPECT_RATIO", "3") or 3)


def is_suspect_close(
    taken_decimal: Any, clv_pct: Any, fair_close_prob: Any,
) -> bool:
    """True iff a graded row's CLV is a degenerate-close artifact per the
    pre-registered rule: |clv_pct| > SUSPECT_CLV_PCT AND the fair-close decimal is
    implausible vs the taken decimal (ratio > RATIO or < 1/RATIO).

    Requires BOTH signals; when either input is missing/unusable we cannot confirm
    implausibility, so the row is NOT flagged (kept). Pure; never raises.
    """
    try:
        clv = abs(float(clv_pct))
        taken = float(taken_decimal)
        fair_p = float(fair_close_prob)
    except (TypeError, ValueError):
        return False
    if clv <= SUSPECT_CLV_PCT:
        return False
    if not (taken > 0.0 and 0.0 < fair_p <= 1.0):
        return False
    fair_dec = 1.0 / fair_p
    ratio = fair_dec / taken
    return ratio > SUSPECT_DECIMAL_RATIO or ratio < (1.0 / SUSPECT_DECIMAL_RATIO)


def is_clv_suspect(row: Dict[str, Any]) -> bool:
    """True iff a settled row's taken price is implausibly longer than its side's
    close -- an off-market / misparsed line that would fabricate a fake CLV.

    Judged ONLY when the bet side's closing decimal is present and valid; otherwise
    we cannot tell, so the row is NOT flagged (kept). Pure; never raises.

    A row already stamped clv_status="suspect_close" (write-time guard or backfill)
    is ALWAYS suspect, so every read-time aggregate that routes through this
    predicate excludes it without a separate clause.
    """
    if str(row.get("clv_status")) == "suspect_close":
        return True
    try:
        taken = float(row.get("taken_decimal"))
        side = str(row.get("side", "")).strip().lower()
        if side == _SIDE_HOME:
            close_dec = float(row.get("closing_decimal_home"))
        elif side == _SIDE_AWAY:
            close_dec = float(row.get("closing_decimal_away"))
        else:
            return False
    except (TypeError, ValueError):
        return False
    if not (taken > 1.0 and close_dec > 1.0):
        return False
    return taken > close_dec * _MAX_TAKEN_CLOSE_RATIO


def _is_synthetic_row(row: Dict[str, Any]) -> bool:
    """True for synthetic (test_*) or malformed (short game_id) rows.

    Read-time only -- the on-disk ledger is never mutated.
    """
    sport = str(row.get("sport") or "")
    bet_id_val = str(row.get("bet_id") or "")
    if sport.startswith("test_") or bet_id_val.startswith("test_"):
        return True
    game_id = row.get("game_id")
    if game_id is not None and len(str(game_id)) < _MIN_GAME_ID_LEN:
        return True
    return False


def load_ledger(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read every JSONL line from the ledger. Missing file -> empty list.

    Applies _is_synthetic_row at read time: test-sport rows and short game_id
    rows are dropped before returning. On-disk file is never mutated.

    Uncached -- for a memoized read use clv_summary_cache.cached_load_ledger,
    which wraps this with an (path, mtime, size) memo (PERF 2026-07-15).
    """
    target = Path(path) if path is not None else DEFAULT_LEDGER
    if not target.exists():
        return []
    out: List[Dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # tolerate a partial trailing write, never crash
            if _is_synthetic_row(row):
                continue  # read-time filter: synthetic/malformed rows never reach consumers
            out.append(row)
    return out


def clv_summary(ledger: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate CLV over settled bets: n_bets, pct_beat_close, mean/median, by_sport.

    Off-market / misparsed rows (is_clv_suspect -- a taken price implausibly longer
    than its side's close, which fabricates a fake +CLV) are EXCLUDED from every
    statistic and reported as ``n_suspect_excluded`` so the headline mean can never
    be inflated by a corrupt line.

    Proxy-close rows (clv_is_proxy=True -- an estimated close, not a real captured
    one) are counted separately as ``n_proxy`` (also ``clv_is_proxy``, a bool: True
    iff any settled row is a proxy) and EXCLUDED from ``median_clv_pct`` whenever at
    least one true-close row exists (``basis``: "true_close"); the median falls back
    to all rows only when zero true-close rows exist yet (``basis``: "proxy_only").
    ``mean_clv_pct`` stays the all-(non-suspect)-rows mean -- CONTEXT ONLY, may
    include proxy closes; prefer ``median_clv_pct`` / ``basis`` for the honest
    headline. The same true/proxy split is reported per-sport in ``by_sport``.
    """
    settled_all = [
        b for b in ledger
        if b.get("status") == "settled" and b.get("clv_pct") is not None
    ]
    settled = [b for b in settled_all if not is_clv_suspect(b)]
    n_suspect = len(settled_all) - len(settled)
    n = len(settled)
    if n == 0:
        return {"n_bets": 0, "pct_beat_close": None, "mean_clv_pct": None,
                "median_clv_pct": None, "basis": None, "n_proxy": 0,
                "clv_is_proxy": False, "n_suspect_excluded": n_suspect,
                "by_sport": {}}
    clvs = [float(b["clv_pct"]) for b in settled]
    beats = sum(1 for c in clvs if c > 0.0)
    n_proxy = sum(1 for b in settled if bool(b.get("clv_is_proxy", False)))
    true_clvs = [float(b["clv_pct"]) for b in settled
                 if not bool(b.get("clv_is_proxy", False))]
    if true_clvs:
        median = round(statistics.median(true_clvs), 6)
        basis = "true_close"
    else:
        median = round(statistics.median(clvs), 6)
        basis = "proxy_only"
    by_sport: Dict[str, Any] = {}
    for b in settled:
        sport = str(b.get("sport", "unknown"))
        bucket = by_sport.setdefault(sport, {"n": 0, "_sum": 0.0, "_beats": 0,
                                             "_clvs": [], "_true_clvs": [],
                                             "n_proxy": 0})
        c = float(b["clv_pct"])
        bucket["n"] += 1
        bucket["_sum"] += c
        bucket["_beats"] += 1 if c > 0.0 else 0
        bucket["_clvs"].append(c)
        if bool(b.get("clv_is_proxy", False)):
            bucket["n_proxy"] += 1
        else:
            bucket["_true_clvs"].append(c)
    for sport, bucket in by_sport.items():
        cnt = bucket["n"]
        bucket["mean_clv_pct"] = round(bucket.pop("_sum") / cnt, 6)
        all_vals = bucket.pop("_clvs")
        true_vals = bucket.pop("_true_clvs")
        if true_vals:
            bucket["median_clv_pct"] = round(statistics.median(true_vals), 6)
            bucket["basis"] = "true_close"
        else:
            bucket["median_clv_pct"] = round(statistics.median(all_vals), 6)
            bucket["basis"] = "proxy_only"
        bucket["pct_beat_close"] = round(100.0 * bucket.pop("_beats") / cnt, 4)
    return {
        "n_bets": n,
        "pct_beat_close": round(100.0 * beats / n, 4),
        "mean_clv_pct": round(sum(clvs) / n, 6),
        "median_clv_pct": median,
        "basis": basis,
        "n_proxy": n_proxy,
        "clv_is_proxy": n_proxy > 0,
        "n_suspect_excluded": n_suspect,
        "by_sport": by_sport,
    }


__all__ = [
    "record_bet", "bet_id", "event_ckey", "compute_clv", "settle_closing_line",
    "append_settlement", "load_ledger", "clv_summary", "is_clv_suspect",
    "is_suspect_close",
]
